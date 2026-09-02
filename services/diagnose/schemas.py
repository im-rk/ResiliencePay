# pyrefly: ignore [missing-import]
from pydantic import BaseModel
from typing import Literal, Optional
from packages.domain_constants.cause_categories import CauseCategoryEnum

class DiagnosisResult(BaseModel):
    cause_category: CauseCategoryEnum
    confidence: float
    method: Literal["rule_based", "llm_fallback", "fallback_failed", "semantic_cache_hit"]
    justification: Optional[str] = None
    model_version: Optional[str] = None
