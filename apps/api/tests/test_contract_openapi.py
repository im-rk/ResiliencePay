import json
from pathlib import Path
from apps.api.src.main import app


def test_openapi_schema_matches_checked_in_contract():
    current_schema = app.openapi()
    contract_path = Path("packages/api-contracts/openapi.json")

    assert contract_path.exists(), "packages/api-contracts/openapi.json must exist"

    with open(contract_path, "r") as f:
        checked_in_schema = json.load(f)

    assert current_schema == checked_in_schema, (
        "OpenAPI schema has drifted from packages/api-contracts/openapi.json — "
        "re-export it to keep generated dashboard contracts in sync."
    )
