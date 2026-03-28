from google import genai
from google.genai import types
from app.core.config import settings
from typing import Dict, Any, List
import asyncio
import json
import logging
import re

# Separate clients per task — each API key gets its own RPM/RPD quota
# 3 keys = 3x the rate limit headroom, no task starves another
analysis_client = genai.Client(api_key=settings.GEMINI_API_KEY)
htoc_client = genai.Client(api_key=settings.GEMINI_HTOC_API_KEY) if settings.GEMINI_HTOC_API_KEY else analysis_client
chat_client = genai.Client(api_key=settings.GEMINI_CHAT_API_KEY) if settings.GEMINI_CHAT_API_KEY else analysis_client

MODEL = "gemini-2.5-flash"

# Rate limit retry settings
MAX_RETRIES = 3
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
            logging.error(f"Gemini call timed out after {settings.GEMINI_TIMEOUT}s (attempt {attempt + 1})")
            if attempt < max_retries:
                continue
            raise Exception(f"AI request timed out after {settings.GEMINI_TIMEOUT}s")
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                if attempt < max_retries:
                    delay = BASE_RETRY_DELAY * (attempt + 1)
                    logging.warning(f"Rate limited (attempt {attempt + 1}), retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
            raise


class GeminiClient:
    def __init__(self):
        self.client = analysis_client   # analysis (primary key)
        self.htoc_client = htoc_client  # HTOC + tree search (separate key)
        self.chat_client = chat_client  # chat (separate key)

    async def analyze_document(self, anonymized_text: str, analysis_type: str) -> Dict[str, Any]:
        prompt = self._get_analysis_prompt(analysis_type, anonymized_text)

        # Analysis needs more time than chat — large docs produce massive JSON output
        analysis_timeout = settings.GEMINI_TIMEOUT * 2

        try:
            response = await asyncio.wait_for(self.client.aio.models.generate_content(
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
            ), timeout=analysis_timeout)

            if not response.text:
                finish_reason = response.candidates[0].finish_reason if response.candidates else "unknown"
                logging.error(f"Gemini returned empty response. Finish reason: {finish_reason}")
                raise Exception(f"AI returned empty response (Finish reason: {finish_reason})")

            clean_text = self._clean_json_response(response.text)
            return json.loads(clean_text, strict=False)

        except json.JSONDecodeError as e:
            logging.warning("JSON parse failed on first attempt: %s — retrying", e)
            # One retry: Gemini is non-deterministic, second call often succeeds
            try:
                response2 = await asyncio.wait_for(self.client.aio.models.generate_content(
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
                ), timeout=analysis_timeout)
                if response2.text:
                    clean_text2 = self._clean_json_response(response2.text)
                    return json.loads(clean_text2, strict=False)
            except Exception:
                pass
            snippet = response.text[:500] if response and response.text else "NO TEXT"
            logging.error("JSON Decode Error after retry: %s\nSnippet: %s", e, snippet)
            raise Exception("AI returned invalid JSON: {}".format(str(e)))
        except Exception as e:
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

    async def chat(self, anonymized_question: str, anonymized_context: str, chat_history: List[Dict[str, str]]) -> str:
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
1. **Ground every answer in the document.** Cite the specific clause, section, or page. Example: "According to Clause 5.2 (Page 3), the notice period is 30 days."
2. **Quote when it helps.** For important points, include a short direct quote: "The agreement states: '...exact text...' (Clause 4, Page 2)."
3. **Explain like the user is not a lawyer.** Replace jargon with plain language. If a term like "indemnification" or "force majeure" appears, explain what it actually means for the user in 1 line.
4. **Be structured.** Use bullet points for lists, bold for key terms, and keep paragraphs short. If the answer has multiple parts, number them.
5. **Flag what matters.** If a clause is unusually risky, one-sided, or missing standard protections, proactively mention it. Example: "Note: This clause allows the landlord to terminate without notice — this is unusual and worth discussing with a lawyer."
6. **Say when you don't know.** If the answer isn't in the document, say: "I couldn't find this information in the document. It may not be covered, or you may want to ask the other party / consult a lawyer."
7. **Never fabricate.** Do not invent clauses, dates, amounts, or obligations that are not in the document.

PRIVACY:
The document uses anonymized placeholders like [PERSON_1], [ORG_1], [AADHAAR_1]. Use these exactly as-is — never attempt to guess the real values.

TONE:
Helpful, clear, and approachable — like a knowledgeable friend who reads legal documents for you. Not robotic, not overly formal. Use Indian English conventions where appropriate (e.g., ₹ for currency, "lakh/crore" for amounts)."""

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

    async def generate_json(self, prompt: str) -> Dict[str, Any]:
        """Generic JSON generation method used by HTOC builder and tree search.
        Uses htoc_client (separate API key) to avoid starving analysis/chat.
        Includes automatic retry on 429 rate limit errors."""
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

        try:
            response = await _retry_on_rate_limit(_call)

            clean_text = self._clean_json_response(response.text)
            return json.loads(clean_text, strict=False)
        except json.JSONDecodeError as e:
            logging.warning(f"JSON parse failed in generate_json: {e} — retrying")
            # Retry once: Gemini is non-deterministic, second call often produces valid JSON
            try:
                response2 = await _retry_on_rate_limit(_call)
                clean_text2 = self._clean_json_response(response2.text)
                return json.loads(clean_text2, strict=False)
            except json.JSONDecodeError as e2:
                # Last resort: try to extract JSON object/array from the messy response
                raw = response.text if response and response.text else ""
                extracted = self._extract_json_bruteforce(raw)
                if extracted is not None:
                    return extracted
                logging.error(f"JSON Decode Error after retry in generate_json: {e2}")
                raise Exception(f"AI returned invalid JSON: {str(e2)}")
            except Exception:
                raise
        except Exception as e:
            logging.error(f"Gemini generate_json error: {str(e)}")
            raise

    async def chat_with_context(self, question: str, context: str, chat_history: List[Dict[str, str]], source_info: str = "") -> str:
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
1. **Ground every answer in the sections above.** Cite the specific section name and page number inline. Example: "According to the Termination Clause (Page 5), either party can exit with 30 days' written notice."
2. **Quote when it helps.** For critical points, include a short direct quote: "The agreement states: '...exact text...' (Section Name, Page X)."
3. **Explain like the user is not a lawyer.** Replace jargon with plain language. If a term like "indemnification", "force majeure", or "lien" appears, explain what it practically means for the user in 1 line.
4. **Be structured.** Use bullet points for lists, bold for key terms, and keep paragraphs short. If the answer has multiple parts, number them.
5. **Flag what matters.** If a clause is unusually risky, one-sided, or missing standard protections, proactively mention it. Example: "⚠️ This clause allows termination without any notice — this is unusual and may be worth discussing with a lawyer."
6. **Handle missing information honestly.** If the answer isn't in the provided sections, say: "This information isn't in the sections I can see right now. Try asking about it directly (e.g., 'What does Clause X say?') or rephrase your question."
   Do NOT guess, infer, or use general legal knowledge to fill gaps.
7. **Never fabricate.** Do not invent clauses, dates, amounts, or obligations that are not explicitly in the sections above.
8. **Follow-up awareness.** If the user is asking a follow-up ("tell me more", "what about that"), connect your answer to the previous conversation context.

PRIVACY:
The document uses anonymized placeholders like [PERSON_1], [ORG_1], [AADHAAR_1]. Use these exactly as-is — never attempt to guess the real values.

TONE:
Helpful, clear, and approachable — like a knowledgeable friend who reads legal documents for you. Not robotic, not overly formal. Use Indian English conventions where appropriate (e.g., ₹ for currency, "lakh/crore" for amounts)."""

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
Language hint: {language_hint}.
Rules:
- Preserve the original layout and paragraph structure as much as possible.
- Include all text: headers, footers, stamps, handwritten notes, table contents.
- For tables, output rows separated by newlines with columns separated by | pipes.
- Do NOT add any commentary, just return the extracted text exactly as it appears.
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
      "importance": "critical | important | standard"
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
    Critical (5 pts each, count max 3): indemnification, limitation of liability, termination rights, dispute resolution, data protection/privacy.
    Important (2 pts each, count max 5): force majeure, insurance, notice provisions, renewal terms, assignment restrictions, confidentiality, governing law.
    B = min(25, critical_count*5 + important_count*2)

  COMPONENT C — One-sidedness (max 20 points):
    Rate the contract balance: 0=balanced, 1=slightly favors one party, 2=moderately one-sided, 3=heavily one-sided, 4=extremely one-sided/unconscionable.
    C = rating * 5

  COMPONENT D — Protective Clause Credit (max 15 points, SUBTRACTED):
    Count how many of these protections are meaningfully present in the document:
    liability cap, mutual indemnification, reasonable termination/exit clause, notice period, dispute resolution mechanism, force majeure, confidentiality, cure/remedy period before default.
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
      "importance": "critical | important | standard"
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
    Critical (5 pts each, count max 3): indemnification, limitation of liability, termination rights, dispute resolution, data protection/privacy.
    Important (2 pts each, count max 5): force majeure, insurance, notice provisions, renewal terms, assignment restrictions, confidentiality, governing law.
    B = min(25, critical_count*5 + important_count*2)

  COMPONENT C — One-sidedness (max 20 points):
    Rate the contract balance: 0=balanced, 1=slightly favors one party, 2=moderately one-sided, 3=heavily one-sided, 4=extremely one-sided/unconscionable.
    C = rating * 5

  COMPONENT D — Protective Clause Credit (max 15 points, SUBTRACTED):
    Count how many of these protections are meaningfully present in the document:
    liability cap, mutual indemnification, reasonable termination/exit clause, notice period, dispute resolution mechanism, force majeure, confidentiality, cure/remedy period before default.
    D = min(15, count * 2)

  FINAL: overall_risk_score = max(5, min(95, A + B + C - D))

  Expected ranges: well-drafted contract = 10-30, moderate gaps = 35-50, one-sided with serious gaps = 55-75, truly dangerous = 80-95.
- RETURN ONLY THE JSON OBJECT.

Document:
{document}
"""
        return ANALYSIS_PROMPT

    async def chat_with_context_stream(self, question: str, context: str, chat_history: List[Dict[str, str]], source_info: str = ""):
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
1. **Ground every answer in the sections above.** Cite the specific section name and page number inline. Example: "According to the Termination Clause (Page 5), either party can exit with 30 days' written notice."
2. **Quote when it helps.** For critical points, include a short direct quote: "The agreement states: '...exact text...' (Section Name, Page X)."
3. **Explain like the user is not a lawyer.** Replace jargon with plain language. If a term like "indemnification", "force majeure", or "lien" appears, explain what it practically means for the user in 1 line.
4. **Be structured.** Use bullet points for lists, bold for key terms, and keep paragraphs short. If the answer has multiple parts, number them.
5. **Flag what matters.** If a clause is unusually risky, one-sided, or missing standard protections, proactively mention it.
6. **Handle missing information honestly.** If the answer isn't in the provided sections, say: "This information isn't in the sections I can see right now. Try asking about it directly (e.g., 'What does Clause X say?') or rephrase your question."
   Do NOT guess, infer, or use general legal knowledge to fill gaps.
7. **Never fabricate.** Do not invent clauses, dates, amounts, or obligations that are not explicitly in the sections above.
8. **Follow-up awareness.** If the user is asking a follow-up ("tell me more", "what about that"), connect your answer to the previous conversation context.

PRIVACY:
The document uses anonymized placeholders like [PERSON_1], [ORG_1], [AADHAAR_1]. Use these exactly as-is — never attempt to guess the real values.

TONE:
Helpful, clear, and approachable — like a knowledgeable friend who reads legal documents for you. Not robotic, not overly formal. Use Indian English conventions where appropriate (e.g., ₹ for currency, "lakh/crore" for amounts)."""

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

    async def chat_stream(self, anonymized_question: str, anonymized_context: str, chat_history: List[Dict[str, str]]):
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
