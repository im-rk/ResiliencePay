import numpy as np
from packages.domain_constants.cause_categories import CauseCategoryEnum

ERROR_CODE_POOLS = {
    CauseCategoryEnum.INSUFFICIENT_FUNDS.value: ["BAD_REQUEST_ERROR", "INSUFFICIENT_FUNDS", "FUNDS_NOT_AVAILABLE"],
    CauseCategoryEnum.EXPIRED_CARD.value: ["CARD_EXPIRED", "EXPIRED_CARD", "EXPIRY_DATE_PASSED"],
    CauseCategoryEnum.OTP_FAILURE.value: ["OTP_FAILED", "AUTHENTICATION_FAILED", "INVALID_OTP"],
    CauseCategoryEnum.BANK_TIMEOUT.value: ["GATEWAY_TIMEOUT", "BANK_TIMEOUT", "REQUEST_TIMEOUT"],
    CauseCategoryEnum.MANDATE_INACTIVE.value: ["MANDATE_INACTIVE", "MANDATE_REVOKED"],
    CauseCategoryEnum.HARD_DECLINE.value: ["DECLINED_BY_ISSUER", "DO_NOT_HONOR", "RESTRICTED_CARD"],
    CauseCategoryEnum.CUSTOMER_CANCELLED.value: ["CANCELLED_BY_USER", "USER_ABORTED"],
}

def sample_error_code(cause_category: str, rng: np.random.Generator) -> str:
    pool = ERROR_CODE_POOLS.get(cause_category, ["UNKNOWN_ERROR"])
    return str(rng.choice(pool))
