from google import genai
from google.genai import types
from app.core.config import settings
from typing import Dict, Any, List
import asyncio
import json
import logging
import re

# ── Groq fallback (used when Gemini 503s/429s) ───────────────────────────────
_GROQ_MODEL = "llama-3.3-70b-versatile"         # chat / HTOC (fast, free)
_GROQ_ANALYSIS_MODEL = "llama-3.3-70b-versatile"  # analysis (deepseek r1 models decommissioned on Groq)
_groq_client = None

_OPENAI_MODEL = "gpt-4o-mini"
_openai_client = None

_CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # fast + cheap; swap to claude-sonnet-4-6 for max quality
_claude_client = None

def _get_groq():
    global _groq_client
    if _groq_client is None:
        from openai import OpenAI
        _groq_client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY,
        )
    return _groq_client

def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=settings.OPEN_AI_API_KEY)
    return _openai_client

def _openai_generate_json_sync(prompt: str, force_json_mode: bool = True) -> Dict[str, Any]:
    kwargs = dict(
        messages=[{"role": "user", "content": prompt}],
        model=_OPENAI_MODEL,
        temperature=0,
    )
    if force_json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _get_openai().chat.completions.create(**kwargs)
    raw = (resp.choices[0].message.content or "").strip()

    if force_json_mode:
        return json.loads(raw, strict=False)

    # Free-form: strip markdown fences then extract outermost { ... }
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw.strip())
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end > start:
        candidate = raw[start:end + 1]
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
        return json.loads(candidate, strict=False)
    return json.loads(raw, strict=False)

def _openai_chat_sync(system_prompt: str, history: list, question: str) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    for turn in history:
        messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
    messages.append({"role": "user", "content": question})
    resp = _get_openai().chat.completions.create(
        messages=messages,
        model=_OPENAI_MODEL,
        temperature=0.3,
    )
    return (resp.choices[0].message.content or "").strip()

async def _openai_chat_stream(system_prompt: str, history: list, question: str):
    messages = [{"role": "system", "content": system_prompt}]
    for turn in history:
        messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
    messages.append({"role": "user", "content": question})

    def _collect():
        resp = _get_openai().chat.completions.create(
            messages=messages,
            model=_OPENAI_MODEL,
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()

    full_text = await asyncio.get_event_loop().run_in_executor(None, _collect)
    CHUNK_SIZE = 60
    for i in range(0, len(full_text), CHUNK_SIZE):
        yield full_text[i:i + CHUNK_SIZE]
        await asyncio.sleep(0)

def _get_claude():
    global _claude_client
    if _claude_client is None:
        import anthropic
        _claude_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _claude_client

def _claude_generate_json_sync(prompt: str, max_tokens: int = 16000) -> Dict[str, Any]:
    resp = _get_claude().messages.create(
        model=_CLAUDE_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = (resp.content[0].text or "").strip()
    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw.strip())
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end > start:
        candidate = raw[start:end + 1]
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
        return json.loads(candidate, strict=False)
    return json.loads(raw, strict=False)

def _claude_chat_sync(
    system_prompt: str, history: list, question: str) -> str:
    messages = []
    for turn in history:
        messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
    messages.append({"role": "user", "content": question})
    resp = _get_claude().messages.create(
        model=_CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    )
    return (resp.content[0].text or "").strip()

async def _claude_chat_stream(system_prompt: str, history: list, question: str):
    messages = []
    for turn in history:
        messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
    messages.append({"role": "user", "content": question})

    def _collect():
        resp = _get_claude().messages.create(
            model=_CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )
        return (resp.content[0].text or "").strip()

    full_text = await asyncio.get_event_loop().run_in_executor(None, _collect)
    CHUNK_SIZE = 60
    for i in range(0, len(full_text), CHUNK_SIZE):
        yield full_text[i:i + CHUNK_SIZE]
        await asyncio.sleep(0)

def _groq_generate_json_sync(prompt: str, force_json_mode: bool = True, model: str = None) -> Dict[str, Any]:
    """Call Groq and return parsed JSON.
    force_json_mode=True: use response_format json_object (good for HTOC — pure structure).
    force_json_mode=False: let model reason freely, then extract JSON from response text
                           (required for analysis + reasoning models).
    model: override the default _GROQ_MODEL (e.g. use _GROQ_ANALYSIS_MODEL for analysis).
    """
    use_model = model or _GROQ_MODEL
    kwargs = dict(
        messages=[{"role": "user", "content": prompt}],
        model=use_model,
        temperature=0,
    )
    if force_json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = _get_groq().chat.completions.create(**kwargs)
    raw = (resp.choices[0].message.content or "").strip()

    if force_json_mode:
        return json.loads(raw, strict=False)

    # Strip any <think>...</think> blocks (legacy reasoning model output)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Free-form mode: extract the JSON object from the response
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw.strip())
    # Find outermost { ... }
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end > start:
        candidate = raw[start:end + 1]
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
        return json.loads(candidate, strict=False)
    return json.loads(raw, strict=False)

def _groq_chat_sync(system_prompt: str, history: list, question: str) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    for turn in history:
        role = turn.get("role", "user")
        messages.append({"role": role, "content": turn.get("content", "")})
    messages.append({"role": "user", "content": question})
    resp = _get_groq().chat.completions.create(
        messages=messages,
        model=_GROQ_MODEL,
        temperature=0.3,
    )
    return (resp.choices[0].message.content or "").strip()

async def _groq_chat_stream(system_prompt: str, history: list, question: str):
    """Yield text chunks from Groq by collecting the full response and chunking it."""
    # Groq streaming is synchronous; collect full response in executor then yield in ~50-char chunks
    messages = [{"role": "system", "content": system_prompt}]
    for turn in history:
        role = turn.get("role", "user")
        messages.append({"role": role, "content": turn.get("content", "")})
    messages.append({"role": "user", "content": question})

    def _collect():
        resp = _get_groq().chat.completions.create(
            messages=messages,
            model=_GROQ_MODEL,
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()

    full_text = await asyncio.get_event_loop().run_in_executor(None, _collect)
    # Yield in word-boundary chunks to simulate streaming
    CHUNK_SIZE = 60
    for i in range(0, len(full_text), CHUNK_SIZE):
        yield full_text[i:i + CHUNK_SIZE]
        await asyncio.sleep(0)  # yield control so other coroutines can run

# Separate clients per task — each API key gets its own RPM/RPD quota
# 3 keys = 3x the rate limit headroom, no task starves another
analysis_client = genai.Client(api_key=settings.GEMINI_API_KEY)
htoc_client = genai.Client(api_key=settings.GEMINI_HTOC_API_KEY) if settings.GEMINI_HTOC_API_KEY else analysis_client
chat_client = genai.Client(api_key=settings.GEMINI_CHAT_API_KEY) if settings.GEMINI_CHAT_API_KEY else analysis_client

MODEL = settings.GEMINI_MODEL

# Rate limit retry settings
MAX_RETRIES = 2
BASE_RETRY_DELAY = 15  # seconds — free tier allows 5 req/min


async def _retry_on_rate_limit(coro_fn, max_retries=MAX_RETRIES):
    """Retry a Gemini API call with exponential backoff on 429 errors."""
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.wait_for(
                coro_fn(),
                timeout=settings.GEMINI_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logging.error(
                "Gemini call timed out after %ss using model %s (attempt %s/%s)",
                settings.GEMINI_TIMEOUT,
                MODEL,
                attempt + 1,
                max_retries + 1,
            )
            if attempt < max_retries:
                continue
            raise Exception(f"AI request timed out after {settings.GEMINI_TIMEOUT}s")
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
                if attempt < max_retries:
                    delay = BASE_RETRY_DELAY * (attempt + 1)
                    logging.warning(
                        "Retryable Gemini error using model %s (attempt %s/%s, retry in %ss): %s: %s",
                        MODEL,
                        attempt + 1,
                        max_retries + 1,
                        delay,
                        type(e).__name__,
                        err_str,
                    )
                    await asyncio.sleep(delay)
                    continue
            logging.error(
                "Non-retryable Gemini error using model %s (attempt %s/%s): %s: %s",
                MODEL,
                attempt + 1,
                max_retries + 1,
                type(e).__name__,
                err_str,
            )
            raise


class GeminiClient:
    def __init__(self):
        self.client = analysis_client   # analysis (primary key)
        self.htoc_client = htoc_client  # HTOC + tree search (separate key)
        self.chat_client = chat_client  # chat (separate key)

    async def analyze_document(self, anonymized_text: str, analysis_type: str, provider: str = "gemini") -> Dict[str, Any]:
        prompt = self._get_analysis_prompt(analysis_type, anonymized_text)

        if provider == "groq":
            logging.info("analyze_document: using llama-3.3-70b on Groq")
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: _groq_generate_json_sync(prompt, force_json_mode=False, model=_GROQ_ANALYSIS_MODEL)
            )

        if provider == "openai":
            logging.info("analyze_document: using GPT-4o-mini (OpenAI)")
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: _openai_generate_json_sync(prompt, force_json_mode=False)
            )

        if provider == "claude":
            logging.info("analyze_document: using Claude (Anthropic)")
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: _claude_generate_json_sync(prompt, max_tokens=16000)
            )

        # Analysis needs more time than chat — large docs produce massive JSON output
        analysis_timeout = settings.GEMINI_TIMEOUT * 2

        async def _call():
            return await self.client.aio.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                    ],
                ),
            )

        try:
            response = await _retry_on_rate_limit(_call)

            if not response.text:
                finish_reason = response.candidates[0].finish_reason if response.candidates else "unknown"
                logging.error(f"Gemini returned empty response. Finish reason: {finish_reason}")
                raise Exception(f"AI returned empty response (Finish reason: {finish_reason})")

            clean_text = self._clean_json_response(response.text)
            try:
                return json.loads(clean_text, strict=False)
            except json.JSONDecodeError:
                repaired = self._extract_json_bruteforce(response.text)
                if repaired is not None:
                    return repaired
                raise

        except json.JSONDecodeError as e:
            logging.warning("JSON parse failed on first attempt: %s — retrying", e)
            try:
                response2 = await _retry_on_rate_limit(_call)
                if response2.text:
                    clean_text2 = self._clean_json_response(response2.text)
                    try:
                        return json.loads(clean_text2, strict=False)
                    except json.JSONDecodeError:
                        repaired2 = self._extract_json_bruteforce(response2.text)
                        if repaired2 is not None:
                            return repaired2
            except Exception:
                pass
            snippet = response.text[:500] if response and response.text else "NO TEXT"
            logging.error("JSON Decode Error after retry: %s\nSnippet: %s", e, snippet)
            raise Exception("AI returned invalid JSON: {}".format(str(e)))
        except Exception as e:
            err_str = str(e)
            if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                logging.warning(f"Gemini analyze_document unavailable, falling back to Groq")
                try:
                    fallback_prompt = self._get_analysis_prompt(analysis_type, anonymized_text)
                    return await asyncio.get_event_loop().run_in_executor(
                        None, lambda: _groq_generate_json_sync(fallback_prompt, force_json_mode=False, model=_GROQ_ANALYSIS_MODEL)
                    )
                except Exception as se:
                    logging.error(f"Groq fallback also failed: {se}")
            logging.error("Gemini analysis error: %s", str(e))
            raise

    def _extract_json_bruteforce(self, text: str) -> Any:
        """Last-resort: find the outermost { ... } or [ ... ] and parse it."""
        text = text.strip()
        # Strip markdown fences
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
        # Find first { and last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            candidate = text[start:end + 1]
            # Fix trailing commas
            candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
            try:
                return json.loads(candidate, strict=False)
            except json.JSONDecodeError:
                pass

        # Handle truncated JSON — close unclosed strings/brackets
        if start != -1:
            candidate = text[start:]
            result = self._repair_truncated_json(candidate)
            if result is not None:
                return result
        return None

    def _repair_truncated_json(self, text: str) -> Any:
        """Attempt to repair JSON truncated mid-output by closing open structures."""
        # Fix trailing commas
        text = re.sub(r',\s*([}\]])', r'\1', text)

        # Check if we're inside an unclosed string — close it
        in_string = False
        escaped = False
        for ch in text:
            if escaped:
                escaped = False
                continue
            if ch == '\\':
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string

        if in_string:
            # Truncate back to the last clean line before the broken string,
            # or just close the string
            text = text.rstrip()
            # Remove the partial string value — find the last complete key-value
            last_quote = text.rfind('"')
            if last_quote > 0:
                # Close the string and truncate any trailing partial value
                text = text[:last_quote + 1]
                # If we ended on a key (with : after), drop the key too
                if text.rstrip().endswith(':'):
                    # Remove the dangling key
                    text = text[:text.rfind('"', 0, last_quote)]
                    last_quote2 = text.rfind('"')
                    if last_quote2 >= 0:
                        text = text[:last_quote2 + 1]

        # Remove any trailing comma
        text = text.rstrip().rstrip(',')

        # Close any unclosed brackets/braces
        stack = []
        in_str = False
        esc = False
        for ch in text:
            if esc:
                esc = False
                continue
            if ch == '\\' and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch in ('{', '['):
                stack.append('}' if ch == '{' else ']')
            elif ch in ('}', ']'):
                if stack:
                    stack.pop()

        # Close unclosed structures
        text += ''.join(reversed(stack))

        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            return None

    def _clean_json_response(self, text: str) -> str:
        """Clean and repair Gemini JSON output."""
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        text = text.strip()

        # Remove control characters that break JSON (except \n, \r, \t)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)

        # Fix trailing commas before } or ] (common Gemini mistake)
        text = re.sub(r',\s*([}\]])', r'\1', text)

        # Fix unescaped newlines inside string values by replacing actual
        # newlines that are NOT part of JSON structure with \\n
        # This is a best-effort repair: split by lines, rejoin
        lines = text.split('\n')
        repaired = []
        for line in lines:
            stripped = line.strip()
            # Keep structural lines as-is
            if stripped in ('', '{', '}', '[', ']', '},', '],') or stripped.startswith('"') or stripped.startswith('{') or stripped.startswith('[') or stripped.startswith('}') or stripped.startswith(']'):
                repaired.append(line)
            else:
                # Likely a continuation of a string value — escape it
                if repaired:
                    repaired[-1] = repaired[-1].rstrip() + '\\n' + line.lstrip()
                else:
                    repaired.append(line)

        return '\n'.join(repaired)

    # Max chars for full-text fallback to avoid exceeding Gemini context limits
    MAX_FULLTEXT_CHARS = 200_000

    async def chat(self, anonymized_question: str, anonymized_context: str, chat_history: List[Dict[str, str]], provider: str = "gemini") -> str:
        # Truncate very large documents to avoid token limit errors
        context = anonymized_context
        if len(context) > self.MAX_FULLTEXT_CHARS:
            context = context[:self.MAX_FULLTEXT_CHARS] + "\n\n[... Document truncated for length ...]"
            logging.warning("Chat full-text context truncated from %d to %d chars", len(anonymized_context), self.MAX_FULLTEXT_CHARS)

        system_context = f"""You are **Legal Assist**, an AI legal document assistant built for Indian users.

YOUR ROLE:
You help everyday people — tenants, employees, small business owners, freelancers — understand legal documents they've uploaded. You are NOT a lawyer and must never give legal advice. You explain what the document says, flag what matters, and tell users when they should consult a lawyer.

THE DOCUMENT:
Below is the full text of the user's uploaded legal document. This is the ONLY source of truth — do not rely on outside legal knowledge, assumptions, or general legal principles.

--- BEGIN DOCUMENT ---
{context}
--- END DOCUMENT ---

HOW TO ANSWER:
1. **Ground every answer in the document.** Cite using plain text only — e.g. "(Clause 5.2, Page 3)" or "(Page 2)". Never use markdown links, URLs, or [link] syntax.
2. **Quote when it helps.** For important points, include a short direct quote: "The agreement states: '...exact text...' (Clause 4, Page 2)."
3. **Explain like the user is not a lawyer.** Replace jargon with plain language. If a term like "indemnification" or "force majeure" appears, explain what it actually means for the user in 1 line.
4. **Be structured.** Use bullet points for lists, bold for key terms, and keep paragraphs short. If the answer has multiple parts, number them.
5. **Flag what matters.** If a clause is unusually risky, one-sided, or missing standard protections, proactively mention it. Example: "Note: This clause allows the landlord to terminate without notice — this is unusual and worth discussing with a lawyer."
6. **Say when you don't know.** If the answer isn't in the document, say: "I couldn't find this information in the document. It may not be covered, or you may want to ask the other party / consult a lawyer."
7. **Never fabricate.** Do not invent clauses, dates, amounts, or obligations that are not in the document.
8. **No markdown links ever.** Do not output [text](url), [link], or any hyperlink syntax. Citations are plain text in parentheses only.
9. **List requests — reproduce verbatim.** If the user asks to "list all" items (allegations, clauses, parties, counts, etc.), reproduce each numbered item from the document as a numbered list. Do NOT group, summarize, or collapse them. If the document has 16 numbered allegations, output all 16. Preserve the original numbering.

PRIVACY:
The document uses anonymized placeholders like [PERSON_1], [ORG_1], [AADHAAR_1]. Use these exactly as-is — never attempt to guess the real values.

TONE:
Helpful, clear, and approachable — like a knowledgeable friend who reads legal documents for you. Not robotic, not overly formal. Use Indian English conventions where appropriate (e.g., ₹ for currency, "lakh/crore" for amounts)."""

        if provider == "groq":
            logging.info("chat: using Groq directly")
            return await asyncio.get_event_loop().run_in_executor(
                None, _groq_chat_sync, system_context, chat_history, anonymized_question
            )

        if provider == "openai":
            logging.info("chat: using GPT-4o-mini (OpenAI)")
            return await asyncio.get_event_loop().run_in_executor(
                None, _openai_chat_sync, system_context, chat_history, anonymized_question
            )

        if provider == "claude":
            logging.info("chat: using Claude (Anthropic)")
            return await asyncio.get_event_loop().run_in_executor(
                None, _claude_chat_sync, system_context, chat_history, anonymized_question
            )

        messages = self._build_chat_messages(system_context, chat_history, anonymized_question)

        response = await asyncio.wait_for(self.chat_client.aio.models.generate_content(
            model=MODEL,
            contents=messages,
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                ],
            ),
        ), timeout=settings.GEMINI_TIMEOUT)
        return response.text

    async def generate_json(self, prompt: str, provider: str = "gemini") -> Dict[str, Any]:
        """Generic JSON generation method used by HTOC builder and tree search.
        Uses htoc_client (separate API key) to avoid starving analysis/chat.
        Includes automatic retry on 429 rate limit errors.
        When provider='groq', skips Gemini entirely and goes straight to Groq."""

        if provider == "groq":
            logging.info("generate_json: using Groq directly (provider=groq)")
            return await asyncio.get_event_loop().run_in_executor(
                None, _groq_generate_json_sync, prompt
            )

        if provider == "openai":
            logging.info("generate_json: using GPT-4o-mini (OpenAI)")
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: _openai_generate_json_sync(prompt)
            )

        if provider == "claude":
            logging.info("generate_json: using Claude (Anthropic)")
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: _claude_generate_json_sync(prompt, max_tokens=8192)
            )

        async def _call():
            response = await self.htoc_client.aio.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                    max_output_tokens=65536,
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                    ],
                ),
            )
            if not response.text:
                raise Exception("AI returned empty response")
            return response

        # Gemini gets up to 2 attempts total; any failure on the 2nd attempt falls back to Groq.
        last_response = None
        last_error = None
        for attempt in range(1, 3):
            try:
                response = await _retry_on_rate_limit(_call)
                last_response = response
                clean_text = self._clean_json_response(response.text)
                return json.loads(clean_text, strict=False)
            except json.JSONDecodeError as e:
                last_error = e
                logging.warning(f"JSON parse failed in generate_json (attempt {attempt}/2): {e}")
                continue
            except Exception as e:
                last_error = e
                logging.warning(f"Gemini generate_json error (attempt {attempt}/2): {e}")
                continue

        # Both Gemini attempts failed.
        if isinstance(last_error, json.JSONDecodeError):
            # Last resort: try to extract JSON object/array from the messy response
            raw = last_response.text if last_response and last_response.text else ""
            extracted = self._extract_json_bruteforce(raw)
            if extracted is not None:
                return extracted

        logging.warning("Gemini generate_json failed twice, falling back to Groq (HTOC/tree-search)")
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, _groq_generate_json_sync, prompt
            )
        except Exception as se:
            logging.error(f"Groq fallback also failed: {se}")

        logging.error(f"Gemini generate_json error after 2 attempts: {last_error}")
        raise Exception(f"AI generation failed after Gemini retries and Groq fallback: {last_error}")

    async def chat_with_context(self, question: str, context: str, chat_history: List[Dict[str, str]], source_info: str = "", provider: str = "gemini") -> str:
        """Chat using targeted context from tree search (vectorless RAG)."""
        system_context = f"""You are **Legal Assist**, an AI legal document assistant built for Indian users.

YOUR ROLE:
You help everyday people — tenants, employees, small business owners, freelancers — understand legal documents they've uploaded. You are NOT a lawyer and must never give legal advice. You explain what the document says, flag what matters, and tell users when they should consult a lawyer.

IMPORTANT — PARTIAL CONTEXT:
You do NOT have the full document. You have been given only the sections most likely to answer the user's question. If the answer isn't here, it may exist in other parts of the document you cannot see right now.

RELEVANT DOCUMENT SECTIONS:
{context}

{f"These sections come from: {source_info}" if source_info else ""}

HOW TO ANSWER:
1. **Ground every answer in the sections above.** Cite inline using plain text only — e.g. "(Termination Clause, Page 5)" or "(Page 3)". Never use markdown links, URLs, or [link] syntax.
2. **Quote when it helps.** For critical points, include a short direct quote: "The agreement states: '...exact text...' (Section Name, Page X)."
3. **Explain like the user is not a lawyer.** Replace jargon with plain language. If a term like "indemnification", "force majeure", or "lien" appears, explain what it practically means for the user in 1 line.
4. **Be structured.** Use bullet points for lists, bold for key terms, and keep paragraphs short. If the answer has multiple parts, number them.
5. **Flag what matters.** If a clause is unusually risky, one-sided, or missing standard protections, proactively mention it. Example: "⚠️ This clause allows termination without any notice — this is unusual and may be worth discussing with a lawyer."
6. **Handle missing information honestly.** If the answer isn't in the provided sections, say: "This information isn't in the sections I can see right now. Try asking about it directly or rephrase your question."
   Do NOT guess, infer, or use general legal knowledge to fill gaps.
7. **Never fabricate.** Do not invent clauses, dates, amounts, or obligations that are not explicitly in the sections above.
8. **Follow-up awareness.** If the user is asking a follow-up ("tell me more", "what about that"), connect your answer to the previous conversation context.
9. **No markdown links ever.** Do not output [text](url), [link], or any hyperlink syntax. Citations are plain text in parentheses only.
10. **List requests — reproduce verbatim.** If the user asks to "list all" items (allegations, clauses, parties, counts, etc.), reproduce each numbered item from the document as a numbered list. Do NOT group, summarize, or collapse them. If the document has 16 numbered allegations, output all 16. Preserve the original numbering.

PRIVACY:
The document uses anonymized placeholders like [PERSON_1], [ORG_1], [AADHAAR_1]. Use these exactly as-is — never attempt to guess the real values.

TONE:
Helpful, clear, and approachable — like a knowledgeable friend who reads legal documents for you. Not robotic, not overly formal. Use Indian English conventions where appropriate (e.g., ₹ for currency, "lakh/crore" for amounts)."""

        if provider == "groq":
            logging.info("chat_with_context: using Groq directly")
            return await asyncio.get_event_loop().run_in_executor(
                None, _groq_chat_sync, system_context, chat_history, question
            )

        if provider == "openai":
            logging.info("chat_with_context: using GPT-4o-mini (OpenAI)")
            return await asyncio.get_event_loop().run_in_executor(
                None, _openai_chat_sync, system_context, chat_history, question
            )

        if provider == "claude":
            logging.info("chat_with_context: using Claude (Anthropic)")
            return await asyncio.get_event_loop().run_in_executor(
                None, _claude_chat_sync, system_context, chat_history, question
            )

        messages = self._build_chat_messages(system_context, chat_history, question)

        response = await asyncio.wait_for(self.chat_client.aio.models.generate_content(
            model=MODEL,
            contents=messages,
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                ],
            ),
        ), timeout=settings.GEMINI_TIMEOUT)
        return response.text

    async def ocr_page_image(self, image_bytes: bytes, language_hint: str = "English") -> str:
        """Extract text from a scanned page image using Gemini Vision."""
        prompt = f"""Extract ALL text from this scanned document page.
Language hint: {language_hint}. However, auto-detect the actual language(s) on the page — Indian legal documents often mix English with Hindi, Marathi, or other regional languages even on the same page. Extract text in whatever language it appears.
Rules:
- Preserve the original layout and paragraph structure as much as possible.
- Include all text: headers, footers, stamps, handwritten notes, table contents.
- For tables, output rows separated by newlines with columns separated by | pipes.
- Do NOT add any commentary, just return the extracted text exactly as it appears.
- If the page is mostly a decorative stamp paper, government seal, or watermark with minimal readable text, extract only the readable text and ignore decorative elements.
- If the page is blank or unreadable, return an empty string."""

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        text_part = types.Part.from_text(text=prompt)

        async def _call():
            return await self.client.aio.models.generate_content(
                model=MODEL,
                contents=[types.Content(role="user", parts=[image_part, text_part])],
                config=types.GenerateContentConfig(
                    temperature=0,
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                    ],
                ),
            )

        try:
            response = await _retry_on_rate_limit(_call)
            return response.text.strip() if response.text else ""
        except Exception as e:
            logging.error(f"Gemini Vision OCR failed: {e}")
            return ""

    def _get_analysis_prompt(self, analysis_type: str, document: str) -> str:
        if analysis_type == "short":
            ANALYSIS_PROMPT = f"""
You are legal-assist AI, an expert legal document analyst.
Analyze the following legal document and return a strictly valid JSON object. Keep your analysis very brief and concise.

REQUIRED JSON STRUCTURE:
{{
  "summary": "Very concise plain-language summary (1-2 sentences)",
  "document_type": "Classification (e.g., lease, NDA, etc.)",
  "parties": [
    {{"role": "Role (e.g., Landlord)", "name": "Name (e.g., [PERSON_1])"}}
  ],
  "key_clauses": [
    {{
      "clause_title": "Clause Name",
      "clause_text": "Short excerpt",
      "plain_english": "1 sentence simplified explanation",
      "importance": "critical | important | standard",
      "risk_rank": 1
    }}
  ],
  "risks": [
    {{
      "risk_title": "Brief risk description",
      "severity": "high | medium | low",
      "description": "1 sentence of what could go wrong",
      "recommendation": "1 sentence of recommendation"
    }}
  ],
  "obligations": [
    {{"type": "Obligation type", "description": "Short obligation detail"}}
  ],
  "missing_clauses": ["Standard clauses that are missing"],
  "overall_risk_score": 0
}}

CLAUSE EXTRACTION GUIDELINES:
- A "clause" includes any term, consent, authorization, waiver, or declaration — not just named sections.
- Prioritize: penalties with exact amounts, consent/authorization terms (data sharing, privacy waivers, marketing consent), default/termination, interest rates.
- For loan docs: extract charges (e.g., "EMI bounce: Rs.500 + GST"), consent points (data sharing with credit bureaus, Aadhaar access), and waivers as separate critical clauses.

IMPORTANT:
- Escape any double quotes inside string values with a backslash.
- Do NOT use unescaped newline characters inside strings.
- overall_risk_score: You MUST calculate this using the 4-component formula below.

  COMPONENT A — Risk Severity (max 40 points):
    Count high_count, medium_count, low_count from your risks array above.
    A = min(40,
        (min(high_count,5)*6 + max(0,high_count-5)*2)
      + (min(medium_count,5)*3 + max(0,medium_count-5)*1)
      + (min(low_count,5)*1)
    )

  COMPONENT B — Missing Clauses (max 25 points):
    Classify each missing clause you listed above as critical or important:
    Critical (5 pts each, count max 3): indemnification, limitation of liability, termination rights, dispute resolution, data protection/privacy, title warranty/encumbrance check, right of redemption.
    Important (2 pts each, count max 5): force majeure, insurance, notice provisions, renewal terms, assignment restrictions, confidentiality, governing law, possession handover terms, prepayment rights, security deposit return terms.
    B = min(25, critical_count*5 + important_count*2)

  COMPONENT C — One-sidedness (max 20 points):
    Rate the contract balance: 0=balanced, 1=slightly favors one party, 2=moderately one-sided, 3=heavily one-sided, 4=extremely one-sided/unconscionable.
    C = rating * 5

  COMPONENT D — Protective Clause Credit (max 15 points, SUBTRACTED):
    Count how many of these protections are meaningfully present in the document:
    liability cap, mutual indemnification, reasonable termination/exit clause, notice period, dispute resolution mechanism, force majeure, confidentiality, cure/remedy period before default, free-from-encumbrance warranty, right to prepay without penalty, clear redemption/release path, security deposit return timeline.
    D = min(15, count * 2)

  FINAL: overall_risk_score = max(5, min(95, A + B + C - D))

  Expected ranges: well-drafted contract = 10-30, moderate gaps = 35-50, one-sided with serious gaps = 55-75, truly dangerous = 80-95.
- RETURN ONLY THE JSON OBJECT.

Document:
{document}
"""
        else:
            ANALYSIS_PROMPT = f"""
You are legal-assist AI, an expert legal document analyst.
Analyze the following legal document and return a strictly valid JSON object.

REQUIRED JSON STRUCTURE:
{{
  "summary": "Plain-language summary (3-5 paragraphs, no legal jargon)",
  "document_type": "Classification (e.g., lease, NDA, employment, sale, loan, etc.)",
  "parties": [
    {{"role": "The role of the party (e.g., Landlord, Tenant, Employer)", "name": "The person/org name as it appears in the document (could be anonymized like [PERSON_1] or the actual name)"}}
  ],
  "key_clauses": [
    {{
      "clause_title": "Name of the clause",
      "clause_text": "Exact text from the document",
      "plain_english": "Simplified explanation",
      "importance": "critical | important | standard",
      "risk_rank": 1
    }}
  ],
  "risks": [
    {{
      "risk_title": "Brief description",
      "severity": "high | medium | low",
      "description": "What could go wrong",
      "recommendation": "What the user should do"
    }}
  ],
  "obligations": [
    {{"type": "Payment | Deadline | Notice | etc.", "description": "Details of the obligation"}}
  ],
  "missing_clauses": ["Standard clauses that should be present but are not"],
  "overall_risk_score": 0
}}

CLAUSE EXTRACTION GUIDELINES:
- A "clause" is ANY term, condition, consent, authorization, waiver, declaration, or obligation — not just named sections.
- Extract EVERY clause that affects the user's rights, money, privacy, or obligations.
- MUST include these categories if present in the document:

  RISK TO MONEY (mark as "critical"):
  * Penalty/penal charges — extract exact amounts (e.g., "EMI bounce: Rs.500 + GST", "2% penal interest per month")
  * Interest rate and calculation method
  * Prepayment/foreclosure charges
  * Processing fees, stamp duty, legal costs (especially if non-refundable)
  * Default and remedies (what happens on missed payment)
  * Liability for costs — who pays legal fees, recovery charges, valuation fees
  * Non-refundable fees — fees you lose even if application is rejected/withdrawn

  RISK TO PROPERTY & ASSETS (mark as "critical"):
  * Lien/charge/mortgage/hypothecation — bank's claim on your property/assets until loan is repaid
  * Transfer of property/title — ownership stays with bank until full repayment
  * Repossession/seizure rights — bank's right to take your property, vehicle, or goods on default
  * Sale of collateral/security — bank's right to sell your pledged assets without court order
  * Attachment of property — conditions under which assets can be frozen or attached
  * Right of set-off — bank can debit your savings/other accounts to recover dues
  * Personal guarantee — you are personally liable beyond just the collateral

  RISK OF LEGAL ACTION / CRIMINAL LIABILITY (mark as "critical"):
  * Criminal proceedings — conditions that could lead to criminal charges (cheque bounce under NI Act, fraud, misrepresentation)
  * SARFAESI Act powers — bank's right to enforce security without court intervention
  * Arbitration clause — waiver of right to go to civil court
  * Declaration of false information — consequences if submitted info is found untrue
  * Willful default consequences — classification as willful defaulter, CIBIL impact
  * Recovery proceedings — DRT (Debt Recovery Tribunal), lok adalat, or other legal forums mentioned
  * Jurisdiction clause — which court/city has authority (user may have to travel)

  CONSENT & AUTHORIZATION (mark as "critical" or "important"):
  * Information disclosure — who your data is shared with (credit bureaus, third parties, government)
  * Aadhaar/KYC consent and data access
  * Marketing consent (calls, SMS, emails)
  * Bank statement access authorization
  * Income tax / government data access authorization
  * Waiver of privacy rights
  * Authorization to approach references or third parties
  * CIBIL/credit bureau reporting — your default will be reported

  DECLARATIONS & WAIVERS (mark as "important"):
  * What the user certifies as true (accuracy of information, no pending cases)
  * What the user gives up (right to privacy, right to get documents back, right to sue)
  * Co-applicant/guarantor responsibilities — they are equally liable
  * Restrictions on fund usage (e.g., "not for capital market investment")
  * Undertakings to provide periodic information (quarterly turnover, address changes)

  RIGHTS & TERMINATION (mark as "critical"):
  * Termination/foreclosure/repossession rights
  * Bank's discretion to approve/reject/recall loan at any time
  * Acceleration clause — bank can demand full repayment immediately on default
  * Dispute resolution/arbitration/jurisdiction
  * Governing law

  STANDARD (mark as "standard"):
  * Indemnification and liability
  * Confidentiality/non-disclosure
  * Force majeure
  * Assignment/transfer of rights — bank can sell your loan to another entity
  * Notice period and method
  * Insurance requirements — mandatory insurance you must pay for
  * Guarantee/security/collateral terms

- For consent/declaration sections: extract EACH individual consent point as a separate clause, not one combined clause. Do NOT combine "data sharing + marketing + Aadhaar consent" into one clause — they are separate agreements with different implications.
- If the document has a "Customer Declaration" or "Customer Consent" section, extract EVERY point that involves the user giving up a right, authorizing access, or accepting liability.
- MINIMUM EXTRACTION: For a full analysis, extract at least 15 clauses. For financial/loan documents, extract at least 20. If the document genuinely has fewer, extract all of them.
- Think from the user's perspective: "What am I agreeing to that could cost me money, my property, my privacy, or my freedom?" Every such point is a clause.
- risk_rank: Assign a rank (1 = most dangerous) WITHIN each importance level. Rank by real-world impact to the user:
  * Rank 1-3: Loss of property, seizure of assets, repossession, lien, mortgage enforcement
  * Rank 4-6: Direct monetary loss — penalties, charges, non-refundable fees, interest, EMI bounce fees
  * Rank 7-9: Criminal/legal consequences — fraud charges, false declaration liability, DRT proceedings, willful defaulter
  * Rank 10-12: Privacy and data — sharing with third parties, credit bureau reporting, Aadhaar/KYC consent, marketing
  * Rank 13+: Everything else (declarations, undertakings, standard terms)
  Clauses within the same sub-category should be ranked by severity (higher penalty amount = lower rank number = higher danger).

INDIAN PROPERTY LAW — DOCUMENT-SPECIFIC CHECKS:
When the document is an Indian legal document, apply these domain-specific checks:

  For SALE DEED / AGREEMENT TO SELL:
  - Must have: "free from encumbrances" clause, delivery of title deeds, marketable title warranty, delivery of possession, consideration amount, property description with boundaries
  - Flag if missing: encumbrance certificate reference, title chain verification, possession handover date, stamp duty/registration mention
  - Flag risk if: conditional sale (sale deeds cannot be conditional under TP Act), unregistered (no legal effect per Sec 54 TP Act), executed in breach of court order, seller lacks clear title
  - Note: Agreement to sell only gives right to enforce, NOT title — title passes only on sale deed execution

  For LEASE / LEAVE & LICENSE AGREEMENT:
  - Must have: parties, rent/license fee amount, duration, security deposit terms, termination/notice clause, maintenance responsibilities, permitted use
  - Flag if missing: lock-in period terms, rent escalation clause, sub-letting restriction, dispute resolution, property condition at handover
  - Know the difference: Lease = transfer of interest in property (Sec 105 TP Act), License = mere permission (Sec 52 Indian Easement Act). License is revocable, creates no estate.
  - Monthly lease needs only 15 days notice for termination (Sec 106 TP Act)
  - Lease must be registered if > 1 year (Sec 107 TP Act)

  For MORTGAGE DEED:
  - Must have: mortgagor/mortgagee details, property description, loan amount, interest rate, repayment schedule, redemption/release terms, foreclosure conditions
  - Flag if missing: right of redemption, foreclosure notice period, surplus sale proceeds clause
  - Types: Simple mortgage, mortgage by conditional sale, usufructuary, English mortgage, equitable (deposit of title deeds)
  - Flag risk if: no clear redemption path, bank can sell without court order (SARFAESI), personal guarantee extends beyond collateral

  For POWER OF ATTORNEY:
  - Must flag: whether General (broad) or Special (limited) POA
  - Must flag: whether revocable or irrevocable — irrevocable POA for property is HIGH RISK
  - Must flag: scope — can the agent sell property, mortgage it, collect rent, litigate?
  - Note: POA ceases on death of grantor, POA for property should be registered

  For GIFT DEED:
  - Must have: "out of love and affection" statement, donor-donee details, unconditional transfer, donee acceptance
  - Flag if: conditions attached (gifts must be unconditional except for specific purpose), no registration (mandatory for immovable property), no attestation by 2 witnesses
  - Flag risk if: appears coerced, made during illness/old age without independent advice

  For RELINQUISHMENT/RELEASE DEED:
  - Flag if: in favour of stranger (full stamp duty applies, may be disguised sale), no consideration mentioned, joint owner rights not clearly defined

  For LOAN/FINANCIAL DOCUMENTS:
  - Must have: sanction letter terms, EMI schedule, charges table, prepayment terms, default consequences
  - Flag if missing: moratorium/grace period, dispute resolution, borrower's right to prepay, loan recall conditions
  - Flag risk: SARFAESI powers (bank seizes property without court), CIBIL/credit bureau reporting on default, acceleration clause (full amount due immediately), right of set-off (bank debits your other accounts)

  For ALL Indian documents:
  - Check stamp duty adequacy — understamped documents may be inadmissible as evidence
  - Check registration — unregistered documents for immovable property > Rs.100 have no legal effect
  - Check jurisdiction clause — which court/city, is it reasonable for the user?
  - Check arbitration clause — user may be waiving right to civil court
  - Check governing law — should be Indian law for Indian property

MISSING CLAUSES — flag these in "missing_clauses" if they SHOULD be present but are NOT:
  Standard (all documents): dispute resolution, governing law, notice provisions, force majeure, confidentiality
  Property-specific: encumbrance certificate, title warranty, possession handover, property inspection right
  Financial: prepayment right, moratorium period, loan recall notice, surplus proceeds return, no-penalty prepayment option
  Tenant-specific: rent receipt obligation, landlord's repair duty, security deposit return timeline, subletting terms

IMPORTANT:
- Escape any double quotes inside string values with a backslash.
- Do NOT use unescaped newline characters inside strings.
- If the document uses anonymized placeholders like [PERSON_1], [AADHAAR_1], use them as-is.
- If the document contains actual names (e.g., in non-English documents), use the actual names as they appear in the document.
- overall_risk_score: You MUST calculate this using the 4-component formula below.

  COMPONENT A — Risk Severity (max 40 points):
    Count high_count, medium_count, low_count from your risks array above.
    A = min(40,
        (min(high_count,5)*6 + max(0,high_count-5)*2)
      + (min(medium_count,5)*3 + max(0,medium_count-5)*1)
      + (min(low_count,5)*1)
    )

  COMPONENT B — Missing Clauses (max 25 points):
    Classify each missing clause you listed above as critical or important:
    Critical (5 pts each, count max 3): indemnification, limitation of liability, termination rights, dispute resolution, data protection/privacy, title warranty/encumbrance check, right of redemption.
    Important (2 pts each, count max 5): force majeure, insurance, notice provisions, renewal terms, assignment restrictions, confidentiality, governing law, possession handover terms, prepayment rights, security deposit return terms.
    B = min(25, critical_count*5 + important_count*2)

  COMPONENT C — One-sidedness (max 20 points):
    Rate the contract balance: 0=balanced, 1=slightly favors one party, 2=moderately one-sided, 3=heavily one-sided, 4=extremely one-sided/unconscionable.
    C = rating * 5

  COMPONENT D — Protective Clause Credit (max 15 points, SUBTRACTED):
    Count how many of these protections are meaningfully present in the document:
    liability cap, mutual indemnification, reasonable termination/exit clause, notice period, dispute resolution mechanism, force majeure, confidentiality, cure/remedy period before default, free-from-encumbrance warranty, right to prepay without penalty, clear redemption/release path, security deposit return timeline.
    D = min(15, count * 2)

  FINAL: overall_risk_score = max(5, min(95, A + B + C - D))

  Expected ranges: well-drafted contract = 10-30, moderate gaps = 35-50, one-sided with serious gaps = 55-75, truly dangerous = 80-95.
- RETURN ONLY THE JSON OBJECT.

Document:
{document}
"""
        return ANALYSIS_PROMPT

    async def chat_with_context_stream(self, question: str, context: str, chat_history: List[Dict[str, str]], source_info: str = "", provider: str = "gemini"):
        """Streaming version of chat_with_context. Yields text chunks as they arrive."""
        system_context = f"""You are **Legal Assist**, an AI legal document assistant built for Indian users.

YOUR ROLE:
You help everyday people — tenants, employees, small business owners, freelancers — understand legal documents they've uploaded. You are NOT a lawyer and must never give legal advice. You explain what the document says, flag what matters, and tell users when they should consult a lawyer.

IMPORTANT — PARTIAL CONTEXT:
You do NOT have the full document. You have been given only the sections most likely to answer the user's question. If the answer isn't here, it may exist in other parts of the document you cannot see right now.

RELEVANT DOCUMENT SECTIONS:
{context}

{f"These sections come from: {source_info}" if source_info else ""}

HOW TO ANSWER:
1. **Ground every answer in the sections above.** Cite using plain text only — e.g. "(Termination Clause, Page 5)" or "(Page 3)". Never use markdown links, URLs, or [link] syntax.
2. **Quote when it helps.** For critical points, include a short direct quote: "The agreement states: '...exact text...' (Section Name, Page X)."
3. **Explain like the user is not a lawyer.** Replace jargon with plain language. If a term like "indemnification", "force majeure", or "lien" appears, explain what it practically means for the user in 1 line.
4. **Be structured.** Use bullet points for lists, bold for key terms, and keep paragraphs short. If the answer has multiple parts, number them.
5. **Flag what matters.** If a clause is unusually risky, one-sided, or missing standard protections, proactively mention it.
6. **Handle missing information honestly.** If the answer isn't in the provided sections, say: "This information isn't in the sections I can see right now. Try asking about it directly or rephrase your question."
   Do NOT guess, infer, or use general legal knowledge to fill gaps.
7. **Never fabricate.** Do not invent clauses, dates, amounts, or obligations that are not explicitly in the sections above.
8. **Follow-up awareness.** If the user is asking a follow-up ("tell me more", "what about that"), connect your answer to the previous conversation context.
9. **No markdown links ever.** Do not output [text](url), [link], or any hyperlink syntax. Citations are plain text in parentheses only.
10. **List requests — reproduce verbatim.** If the user asks to "list all" items (allegations, clauses, parties, counts, etc.), reproduce each numbered item from the document as a numbered list. Do NOT group, summarize, or collapse them. If the document has 16 numbered allegations, output all 16. Preserve the original numbering.

PRIVACY:
The document uses anonymized placeholders like [PERSON_1], [ORG_1], [AADHAAR_1]. Use these exactly as-is — never attempt to guess the real values.

TONE:
Helpful, clear, and approachable — like a knowledgeable friend who reads legal documents for you. Not robotic, not overly formal. Use Indian English conventions where appropriate (e.g., ₹ for currency, "lakh/crore" for amounts)."""

        if provider == "groq":
            logging.info("chat_with_context_stream: using Groq directly")
            async for chunk in _groq_chat_stream(system_context, chat_history, question):
                yield chunk
            return

        if provider == "openai":
            logging.info("chat_with_context_stream: using GPT-4o-mini (OpenAI)")
            async for chunk in _openai_chat_stream(system_context, chat_history, question):
                yield chunk
            return

        if provider == "claude":
            logging.info("chat_with_context_stream: using Claude (Anthropic)")
            async for chunk in _claude_chat_stream(system_context, chat_history, question):
                yield chunk
            return

        messages = self._build_chat_messages(system_context, chat_history, question)

        stream = await self.chat_client.aio.models.generate_content_stream(
            model=MODEL,
            contents=messages,
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                ],
            ),
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text

    async def chat_stream(self, anonymized_question: str, anonymized_context: str, chat_history: List[Dict[str, str]], provider: str = "gemini"):
        """Streaming version of chat (full-text fallback). Yields text chunks."""
        # Truncate very large documents to avoid token limit errors
        context = anonymized_context
        if len(context) > self.MAX_FULLTEXT_CHARS:
            context = context[:self.MAX_FULLTEXT_CHARS] + "\n\n[... Document truncated for length ...]"

        system_context = f"""You are **Legal Assist**, an AI legal document assistant built for Indian users.

YOUR ROLE:
You help everyday people — tenants, employees, small business owners, freelancers — understand legal documents they've uploaded. You are NOT a lawyer and must never give legal advice. You explain what the document says, flag what matters, and tell users when they should consult a lawyer.

THE DOCUMENT:
Below is the full text of the user's uploaded legal document. This is the ONLY source of truth — do not rely on outside legal knowledge, assumptions, or general legal principles.

--- BEGIN DOCUMENT ---
{context}
--- END DOCUMENT ---

HOW TO ANSWER:
1. **Ground every answer in the document.** Cite the specific clause, section, or page. Example: "According to Clause 5.2 (Page 3), the notice period is 30 days."
2. **Quote when it helps.** For important points, include a short direct quote: "The agreement states: '...exact text...' (Clause 4, Page 2)."
3. **Explain like the user is not a lawyer.** Replace jargon with plain language. If a term like "indemnification" or "force majeure" appears, explain what it actually means for the user in 1 line.
4. **Be structured.** Use bullet points for lists, bold for key terms, and keep paragraphs short. If the answer has multiple parts, number them.
5. **Flag what matters.** If a clause is unusually risky, one-sided, or missing standard protections, proactively mention it.
6. **Say when you don't know.** If the answer isn't in the document, say: "I couldn't find this information in the document. It may not be covered, or you may want to ask the other party / consult a lawyer."
7. **Never fabricate.** Do not invent clauses, dates, amounts, or obligations that are not in the document.

PRIVACY:
The document uses anonymized placeholders like [PERSON_1], [ORG_1], [AADHAAR_1]. Use these exactly as-is — never attempt to guess the real values.

TONE:
Helpful, clear, and approachable — like a knowledgeable friend who reads legal documents for you. Not robotic, not overly formal. Use Indian English conventions where appropriate (e.g., ₹ for currency, "lakh/crore" for amounts)."""

        if provider == "groq":
            logging.info("chat_stream: using Groq directly")
            async for chunk in _groq_chat_stream(system_context, chat_history, anonymized_question):
                yield chunk
            return

        if provider == "openai":
            logging.info("chat_stream: using GPT-4o-mini (OpenAI)")
            async for chunk in _openai_chat_stream(system_context, chat_history, anonymized_question):
                yield chunk
            return

        if provider == "claude":
            logging.info("chat_stream: using Claude (Anthropic)")
            async for chunk in _claude_chat_stream(system_context, chat_history, anonymized_question):
                yield chunk
            return

        messages = self._build_chat_messages(system_context, chat_history, anonymized_question)

        stream = await self.chat_client.aio.models.generate_content_stream(
            model=MODEL,
            contents=messages,
            config=types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                ],
            ),
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text

    def _build_chat_messages(self, context: str, history: List[Dict[str, str]], question: str) -> list:
        # Send system context as user message, with a model acknowledgment
        # so the LLM treats it as grounding rather than a user query
        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=f"System Instructions & Document Context:\n{context}")]),
            types.Content(role="model", parts=[types.Part.from_text(text="Understood. I have the document context and will answer based only on the provided sections. How can I help you?")]),
        ]

        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])])
            )

        contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=question)])
        )
        return contents
