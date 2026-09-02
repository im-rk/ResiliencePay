from pydantic import BaseModel
from typing import Optional
from datetime import date

class PTPExtractionSchema(BaseModel):
    promised_date: Optional[date] = None
    confidence: float

class PTPExtractionResult(BaseModel):
    promised_date: date
    confidence: float
