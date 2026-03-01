import asyncio
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import json

load_dotenv()

async def test_analysis():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not found in .env")
        return

    client = genai.Client(api_key=api_key)
    
    document = """
    LEASE AGREEMENT
    This agreement is made on Jan 1, 2024 between John Doe and Jane Smith.
    Rent is $1000 per month.
    """
    
    prompt = f"""
    Analyze the following legal document and return a strictly valid JSON object.
    
    REQUIRED JSON STRUCTURE:
    {{
      "summary": "Plain-language summary",
      "document_type": "Classification",
      "parties": [{{"role": "Role", "name": "Name"}}],
      "key_clauses": [
        {{
          "clause_title": "Title",
          "clause_text": "Text",
          "plain_english": "Explanation",
          "importance": "standard"
        }}
      ],
      "risks": [],
      "obligations": [],
      "missing_clauses": [],
      "overall_risk_score": 10
    }}
    
    Document:
    {document}
    """
    
    print("Sending request to Gemini...")
    response = None
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )
        print("Response received:")
        print(f"--- TEXT START ---\n{response.text}\n--- TEXT END ---")
        
        data = json.loads(response.text)
        print("Successfully parsed JSON!")
        print(json.dumps(data, indent=2))
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        if response and hasattr(response, 'candidates'):
             print(f"Finish Reason: {response.candidates[0].finish_reason}")

if __name__ == "__main__":
    asyncio.run(test_analysis())
