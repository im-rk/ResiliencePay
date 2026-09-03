from fastapi import APIRouter, Header, HTTPException, Depends
import os

router = APIRouter()

def require_admin_secret(x_admin_secret: str = Header(...)):
    admin_secret = os.environ.get("ADMIN_SECRET", "hackathon_secret")
    if x_admin_secret != admin_secret:
        raise HTTPException(status_code=403, detail="forbidden")

from pydantic import BaseModel

class FaultInjectionPayload(BaseModel):
    enabled: bool
    rate: float = 0.0

@router.post("/admin/fault-injection", dependencies=[Depends(require_admin_secret)])
def toggle_fault_injection(payload: FaultInjectionPayload):
    """Live trigger for admin fault injection."""
    from packages.config.settings import settings
    settings.fault_injection_enabled = payload.enabled
    settings.fault_injection_rate = payload.rate
    return {"status": "ok", "message": "Fault injection toggled", "enabled": payload.enabled, "rate": payload.rate}
