from pydantic import BaseModel
from typing import Optional

class GateResult(BaseModel):
    passed: bool
    reason: Optional[str] = None
    rule_name: Optional[str] = None
