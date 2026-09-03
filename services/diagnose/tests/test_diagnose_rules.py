from services.diagnose.rules import RULES
from data.error_code_samples import ERROR_CODE_POOLS
from packages.domain_constants.cause_categories import CauseCategoryEnum

def test_all_codes_mapped():
    """Ensure 100% rule table coverage for all codes in Phase 2 dataset."""
    for cause_str, codes in ERROR_CODE_POOLS.items():
        expected_enum = CauseCategoryEnum(cause_str)
        for code in codes:
            assert code in RULES
            assert RULES[code] == expected_enum
