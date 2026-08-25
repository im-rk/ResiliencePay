from enum import Enum

class CauseCategoryEnum(str, Enum):
    INSUFFICIENT_FUNDS = "insufficient_funds"
    EXPIRED_CARD = "expired_card"
    OTP_FAILURE = "otp_failure"
    BANK_TIMEOUT = "bank_timeout"
    MANDATE_INACTIVE = "mandate_inactive"
    HARD_DECLINE = "hard_decline"
    CUSTOMER_CANCELLED = "customer_cancelled"
