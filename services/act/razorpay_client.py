import time
import logging
from dataclasses import dataclass
import razorpay
import requests

logger = logging.getLogger(__name__)

class RazorpayPermanentError(Exception):
    """Raised when a Razorpay call fails in a way that retrying will not fix
    (e.g., 4xx validation errors). Distinct from transient errors so callers
    know not to retry."""

class RazorpayTransientError(Exception):
    """Raised after retries are exhausted on a transient (5xx/timeout) failure."""

@dataclass(frozen=True)
class PaymentLinkResult:
    id: str
    short_url: str
    status: str

class RazorpayClient:
    """Idempotency-key-aware, retrying wrapper over the Razorpay SDK.
    NOTHING outside this file should import razorpay directly — this is the
    single seam Phase 11's fault injection wraps, and the single place
    retry/timeout policy lives.
    
    Idempotency Implementation:
    The Python Razorpay SDK does not natively expose an Idempotency-Key 
    header argument for payment_link.create. Therefore, we use an 
    **application-level idempotency guard** implemented inside `service.py` 
    before calling this client. The `idempotency_key` is also passed here 
    and stored in `notes` for audit trails and reconciliation.
    """

    def __init__(self, key_id: str, key_secret: str, max_retries: int = 3,
                 base_backoff_seconds: float = 0.5):
        self._client = razorpay.Client(auth=(key_id, key_secret))
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds

    def create_retry_payment_link(self, episode, idempotency_key: str) -> PaymentLinkResult:
        payload = {
            "amount": int(episode.original_amount),
            "currency": episode.currency,
            "description": f"Payment retry for episode {episode.episode_id}",
            "notes": {"idempotency_key": idempotency_key, "episode_id": str(episode.episode_id)},
        }
        return self._call_with_retry(
            lambda: self._client.payment_link.create(payload),
            result_mapper=lambda r: PaymentLinkResult(id=r["id"], short_url=r.get("short_url", ""), status=r.get("status", "")),
            idempotency_key=idempotency_key,
        )

    def get_payment_status(self, payment_id: str) -> dict:
        return self._call_with_retry(
            lambda: self._client.payment.fetch(payment_id),
            result_mapper=lambda r: r,
            idempotency_key=f"fetch:{payment_id}",
        )

    def find_payment_link_by_idempotency_key(self, idempotency_key: str) -> PaymentLinkResult | None:
        """
        Since Razorpay does not natively index by idempotency_key in their fetch API,
        we scan recent links. In a production system, this could be optimized by 
        searching within a time-window.
        """
        return self._call_with_retry(
            lambda: self._search_links_for_idempotency_key(idempotency_key),
            result_mapper=lambda r: r,
            idempotency_key=f"search:{idempotency_key}",
        )

    def _search_links_for_idempotency_key(self, idempotency_key: str) -> PaymentLinkResult | None:
        response = self._client.payment_link.all({"count": 100})
        links = response.get("items", [])
        for link in links:
            notes = link.get("notes", {})
            if isinstance(notes, dict) and notes.get("idempotency_key") == idempotency_key:
                return PaymentLinkResult(id=link["id"], short_url=link.get("short_url", ""), status=link.get("status", ""))
        return None

    def _call_with_retry(self, fn, result_mapper, idempotency_key: str):
        from services.act.fault_injection import with_fault_injection
        injected_fn = with_fault_injection(fn)
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                raw_result = injected_fn()
                return result_mapper(raw_result)
            except razorpay.errors.BadRequestError as e:
                # 4xx-class — retrying will not help, fail fast and loud
                raise RazorpayPermanentError(str(e)) from e
            except Exception as e:
                # Catching Exception here generically to ensure SimulatedFault 
                # (which does not inherit from razorpay errors) triggers retry logic.
                # In production, you would catch (razorpay.errors.ServerError, ConnectionError, TimeoutError, requests.exceptions.RequestException, SimulatedFault)
                from services.act.fault_injection import SimulatedFault
                if not isinstance(e, (razorpay.errors.ServerError, ConnectionError, TimeoutError, requests.exceptions.RequestException, SimulatedFault)):
                    raise e
                last_exc = e
                backoff = self.base_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "razorpay_transient_error", extra={
                        "idempotency_key": idempotency_key, 
                        "attempt": attempt, 
                        "backoff_seconds": backoff,
                    })
                time.sleep(backoff)
        raise RazorpayTransientError(
            f"exhausted {self.max_retries} retries for idempotency_key={idempotency_key}"
        ) from last_exc
