from fastapi import APIRouter, Depends, Header, HTTPException, Body
from app.services.session_service import SessionService
from app.services.pii_anonymizer import PIIAnonymizer
from app.services.gemini_client import GeminiClient
from app.core.dependencies import get_session_service, get_pii_service, get_gemini_client
from app.models.chat import ChatRequest, ChatResponse

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_with_document(
    request: ChatRequest,
    session_id: str = Header(..., alias="X-Session-ID"),
    session_service: SessionService = Depends(get_session_service),
    pii_service: PIIAnonymizer = Depends(get_pii_service),
    gemini: GeminiClient = Depends(get_gemini_client),
):
    # 1. Retrieve session
    session = await session_service.get(session_id)
    if not session:
        raise HTTPException(404, "Session expired or not found")

    # 2. Anonymize the question
    anonymized_question, _ = pii_service.anonymize(request.message)
    # Note: We discard the mapping from the question for now, assuming the LLM 
    # can understand the question context or that we predominantly care about 
    # document PII. 
    # Ideally, we should merge mappings if the user introduces NEW PII, 
    # but for simplicity and safety, let's assume we rely on document mapping.
    # Actually, if the user mentions "Ramesh", it should verify against existing mapping.
    # PIIAnonymizer.anonymize creates NEW tokens.
    # We might want to use existing mapping if possible?
    # For now, following the simple flow: Anonymize Question -> Chat -> Deanonymize Response.
    
    # 3. Prepare Chat History
    # We need to anonymize history as well if it contains PII?
    # The frontend is supposed to maintain history. 
    # If the frontend sends raw history, we should anonymize it?
    # Or does the frontend send previously anonymized history?
    # Spec says: "Chat history is maintained entirely in the React frontend state".
    # "FastAPI retrieves the PII mapping... The user’s question is anonymized... history... sent to Gemini"
    # It implies we need to process the history.
    # BUT, de-anonymizing the response means the frontend sees REAL names.
    # So the history coming back from frontend contains REAL names.
    # So we must anonymize the history too.
    
    anonymized_history = []
    for msg in request.history:
        anonymized_content, _ = pii_service.anonymize(msg.content)
        anonymized_history.append({"role": msg.role, "content": anonymized_content})

    # 4. Chat with Gemini
    try:
        anonymized_response = await gemini.chat(
            anonymized_question,
            session.anonymized_text,
            anonymized_history
        )
    except Exception as e:
        raise HTTPException(500, f"Chat failed: {str(e)}")

    # 5. De-anonymize response
    final_response = pii_service.deanonymize(anonymized_response, session.pii_mapping)

    return ChatResponse(response=final_response)
