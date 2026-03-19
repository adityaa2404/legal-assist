from google import genai
from google.genai import types
from app.core.config import settings
from typing import Dict, Any, List
import json
import logging
import re

# Create a global async client instance
client = genai.Client(api_key=settings.GEMINI_API_KEY)

MODEL = "gemini-2.5-flash"


class GeminiClient:
    def __init__(self):
        self.client = client

    async def analyze_document(self, anonymized_text: str, analysis_type: str) -> Dict[str, Any]:
        prompt = self._get_analysis_prompt(analysis_type, anonymized_text)

        try:
            response = await self.client.aio.models.generate_content(
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
                response2 = await self.client.aio.models.generate_content(
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

    async def chat(self, anonymized_question: str, anonymized_context: str, chat_history: List[Dict[str, str]]) -> str:
        messages = self._build_chat_messages(anonymized_context, chat_history, anonymized_question)

        response = await self.client.aio.models.generate_content(
            model=MODEL,
            contents=messages,
        )
        return response.text

    async def generate_json(self, prompt: str) -> Dict[str, Any]:
        """Generic JSON generation method used by HTOC builder and tree search."""
        try:
            response = await self.client.aio.models.generate_content(
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

            if not response.text:
                raise Exception("AI returned empty response")

            clean_text = self._clean_json_response(response.text)
            return json.loads(clean_text, strict=False)
        except json.JSONDecodeError as e:
            logging.error(f"JSON Decode Error in generate_json: {e}")
            raise Exception(f"AI returned invalid JSON: {str(e)}")
        except Exception as e:
            logging.error(f"Gemini generate_json error: {str(e)}")
            raise

    async def chat_with_context(self, question: str, context: str, chat_history: List[Dict[str, str]], source_info: str = "") -> str:
        """Chat using targeted context from tree search (vectorless RAG)."""
        system_context = f"""You are legal-assist AI, an expert legal document assistant.
You have been provided with SPECIFIC SECTIONS of a legal document that are relevant to the user's question.
These sections were identified by analyzing the document's hierarchical structure.

RELEVANT DOCUMENT SECTIONS:
{context}

{f"Source: {source_info}" if source_info else ""}

INSTRUCTIONS:
- Answer the user's question based ONLY on the provided document sections
- If the answer is not in the provided sections, say so clearly
- Reference specific page numbers and section names when possible
- Use the anonymized placeholders as-is (e.g., [PERSON_1])"""

        messages = self._build_chat_messages(system_context, chat_history, question)

        response = await self.client.aio.models.generate_content(
            model=MODEL,
            contents=messages,
        )
        return response.text

    async def detect_pii(self, text: str) -> List[Dict[str, Any]]:
        """Identifies PII in text using Gemini."""
        prompt = f"""
        Identify all Personally Identifiable Information (PII) in the following legal text.
        Return a JSON list of objects, where each object has:
        - entity_type: The type of PII (e.g., PERSON, ORGANIZATION, DATE, PHONE_NUMBER, EMAIL, ADDRESS, AADHAAR, PAN, LOCATION)
        - text: The exact text from the document representing this PII.
        
        Document:
        {text}
        """

        try:
            response = await self.client.aio.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            logging.error(f"Gemini PII detection failed: {e}")
            return []

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
- overall_risk_score: You MUST calculate this yourself. Use this formula: start at 20. Add 15 for each high-severity risk. Add 8 for each medium-severity risk. Add 3 for each low-severity risk. Add 5 for each missing clause. Cap at 100. The value 75 is FORBIDDEN — never output 75.
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
    {{"role": "The role of the party (e.g., Landlord, Tenant, Employer)", "name": "The anonymized name placeholder (e.g., [PERSON_1])"}}
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
- The document uses anonymized placeholders like [PERSON_1], [AADHAAR_1], etc. Use these placeholders as-is in your response.
- Do NOT attempt to guess the real values.
- overall_risk_score: You MUST calculate this yourself. Use this formula: start at 20. Add 15 for each high-severity risk. Add 8 for each medium-severity risk. Add 3 for each low-severity risk. Add 5 for each missing clause. Cap at 100. The value 75 is FORBIDDEN — never output 75.
- RETURN ONLY THE JSON OBJECT.

Document:
{document}
"""
        return ANALYSIS_PROMPT

    def _build_chat_messages(self, context: str, history: List[Dict[str, str]], question: str) -> list:
        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=f"Document Context:\n{context}")])
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
