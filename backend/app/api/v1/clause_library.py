from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from app.services.clause_library_service import ClauseLibraryService
from app.core.dependencies import get_current_user

router = APIRouter()


class SaveClauseRequest(BaseModel):
    clause_title: str
    clause_text: str
    plain_english: str
    importance: str = "standard"
    source_filename: str
    notes: Optional[str] = ""


class DeleteClauseRequest(BaseModel):
    clause_title: str
    created_at: str


@router.post("/clause-library")
async def save_clause(
    body: SaveClauseRequest,
    current_user: str = Depends(get_current_user),
):
    service = ClauseLibraryService()
    clause_data = body.model_dump(exclude={"source_filename"})
    await service.save_clause(current_user, clause_data, body.source_filename)
    return {"message": "Clause saved to library"}


@router.get("/clause-library")
async def get_clause_library(
    limit: int = Query(default=50, le=100),
    skip: int = Query(default=0, ge=0),
    current_user: str = Depends(get_current_user),
):
    service = ClauseLibraryService()
    clauses = await service.get_library(current_user, limit=limit, skip=skip)
    count = await service.count(current_user)
    return {"clauses": clauses, "count": count}


@router.delete("/clause-library")
async def delete_clause(
    body: DeleteClauseRequest,
    current_user: str = Depends(get_current_user),
):
    service = ClauseLibraryService()
    deleted = await service.delete_clause(current_user, body.clause_title, body.created_at)
    if not deleted:
        raise HTTPException(404, "Clause not found")
    return {"message": "Clause deleted"}
