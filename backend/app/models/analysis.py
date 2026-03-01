from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class Party(BaseModel):
    role: str
    name: str

class RulebookReference(BaseModel):
    text: str
    score: float

class Clause(BaseModel):
    clause_title: str
    clause_text: str
    plain_english: str
    importance: str
    rulebook_references: Optional[List[RulebookReference]] = []

class Risk(BaseModel):
    risk_title: str
    severity: str
    description: str
    recommendation: str

class Obligation(BaseModel):
    type: Optional[str] = None
    description: str

class AnalysisResult(BaseModel):
    summary: str
    document_type: str
    parties: List[Party]
    key_clauses: List[Clause]
    risks: List[Risk]
    obligations: List[Obligation]
    missing_clauses: List[str]
    overall_risk_score: int

class AnalysisResponse(AnalysisResult):
    pass
