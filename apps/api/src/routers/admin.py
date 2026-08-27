from fastapi import APIRouter, Header, HTTPException, Depends
import os

router = APIRouter()

def require_admin_secret(x_admin_secret: str = Header(...)):
    admin_secret = os.environ.get("ADMIN_SECRET", "hackathon_secret")
    if x_admin_secret != admin_secret:
        raise HTTPException(status_code=403, detail="forbidden")

@router.post("/v1/admin/fault-injection", dependencies=[Depends(require_admin_secret)])
def toggle_fault_injection():
    """Live trigger for admin fault injection."""
    return {"status": "ok", "message": "Fault injection toggled"}
