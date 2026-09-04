from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger(__name__)


class DomainError(Exception):
    """Base class for all business-logic errors raised by services/*.
    Route handlers never construct HTTPException directly for domain failures —
    they let a DomainError propagate and this handler converts it, keeping the
    error-shaping logic in exactly one place."""

    def __init__(self, code: str, reason: str, status_code: int = 422, **context):
        self.code = code
        self.reason = reason
        self.status_code = status_code
        self.context = context
        super().__init__(f"{code}: {reason}")


class NotFoundError(DomainError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            code="NOT_FOUND",
            reason=f"{resource} not found",
            status_code=404,
            resource=resource,
            resource_id=resource_id,
        )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError):
        origin = request.headers.get("origin", "*")
        return JSONResponse(
            status_code=exc.status_code,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
            },
            content={"error": True, "code": exc.code, "reason": exc.reason, **exc.context},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception("unhandled_exception", extra={"request_id": request_id})
        origin = request.headers.get("origin", "*")
        return JSONResponse(
            status_code=500,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
            },
            content={
                "error": True,
                "code": "INTERNAL_ERROR",
                "reason": "An unexpected error occurred.",
                "request_id": request_id,
            },
        )
