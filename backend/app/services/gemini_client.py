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
            return json.loads(clean_text)

        except json.JSONDecodeError as e:
            snippet = response.text if response and response.text else "NO TEXT"
            logging.error(f"JSON Decode Error: {e}\nFull Text: {snippet}")
            raise Exception(f"AI returned invalid JSON: {str(e)}")
        except Exception as e:
            logging.error(f"Gemini analysis error: {str(e)}")
            raise

    def _clean_json_response(self, text: str) -> str:
        """Removes markdown code blocks and whitespace from AI response."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return text.strip()

    async def chat(self, anonymized_question: str, anonymized_context: str, chat_history: List[Dict[str, str]]) -> str:
        messages = self._build_chat_messages(anonymized_context, chat_history, anonymized_question)

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
  "overall_risk_score": 75
}}

IMPORTANT: 
- The document uses anonymized placeholders like [PERSON_1], [AADHAAR_1], etc. Use these placeholders as-is in your response.
- Do NOT attempt to guess the real values.
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
