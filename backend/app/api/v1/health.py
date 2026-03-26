from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class HealthResponse(BaseModel):
    status: str

@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
async def health_check():
    return {"status": "ok"}
