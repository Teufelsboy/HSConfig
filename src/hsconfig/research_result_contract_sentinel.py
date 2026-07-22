from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from hsconfig.io import read_json
from hsconfig.research_result_contract import classify_research_result_contract
from hsconfig.research_result_validator import (
    validate_fields_yaml_payload,
    validate_research_result_payload,
)

NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"
DIAGNOSTIC_AUTHORITY = "diagnostic_only"


def build_research_result_contract_sentinel(
    fields_path: str | Path,
    results_dir: str | Path,
) -> dict[str, Any]:
    fields_file = Path(fields_path)
    result_root = Path(results_dir)
    fields_payload = _read_yaml_mapping(fields_file)
    fields_contract = validate_fields_yaml_payload(fields_payload)
    rows = [_result_row(path) for path in sorted(result_root.glob("*.json"))]
    strict_invalid_count = sum(
        1 for row in rows if row["strict_research_result_valid"] is False
    )
    contract_invalid_count = sum(1 for row in rows if row["contract_valid"] is False)
    seed_only_count = sum(1 for row in rows if row["snapshot_kind"] == "seed_only")
    strong_promoting_count = sum(
        1 for row in rows if row["canonical_promotion_allowed"] is True
    )
    freshness_missing_count = sum(
        1
        for row in rows
        if "strong_requires_current_or_evergreen_freshness"
        in row["strict_research_result_errors"]
    )
    current_or_evergreen_count = sum(
        1 for row in rows if row["current_or_evergreen"] is True
    )
    no_op_validation_risk = (
        fields_contract["valid"] is False
        or int(fields_contract.get("field_count") or 0) == 0
    )
    status = (
        "clean"
        if (
            fields_contract["valid"] is True
            and rows
            and strict_invalid_count == 0
            and contract_invalid_count == 0
            and no_op_validation_risk is False
        )
        else "attention"
    )
    return {
        "schema_version": 1,
        "authority": DIAGNOSTIC_AUTHORITY,
        "operator_gate_impact": DIAGNOSTIC_AUTHORITY,
        "normal_apply_authority": NORMAL_APPLY_AUTHORITY,
        "fields_path": str(fields_file),
        "results_dir": str(result_root),
        "fields_contract": fields_contract,
        "result_rows": rows,
        "summary": {
            "status": status,
            "field_contract_valid": bool(fields_contract["valid"]),
            "result_count": len(rows),
            "strict_valid_count": len(rows) - strict_invalid_count,
            "strict_invalid_count": strict_invalid_count,
            "contract_invalid_count": contract_invalid_count,
            "seed_only_count": seed_only_count,
            "strong_promoting_count": strong_promoting_count,
            "freshness_missing_count": freshness_missing_count,
            "current_or_evergreen_count": current_or_evergreen_count,
            "no_op_validation_risk": no_op_validation_risk,
            "source_status_apply_blocking": False,
        },
        "source_status_apply_blocking": False,
    }


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _result_row(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        payload = {}
    strict = validate_research_result_payload(payload)
    contract = classify_research_result_contract(payload)
    return {
        "path": str(path),
        "deck_name": str(payload.get("deck_name") or ""),
        "source_strength": str(payload.get("source_strength") or ""),
        "first_missing_source_action": str(
            payload.get("first_missing_source_action") or ""
        ),
        "snapshot_kind": str(contract["snapshot_kind"]),
        "contract_valid": bool(contract["contract_valid"]),
        "canonical_promotion_allowed": bool(
            strict["valid"] and contract["canonical_promotion_allowed"]
        ),
        "canonical_downgrade_allowed": False,
        "strict_research_result_valid": bool(strict["valid"]),
        "strict_research_result_errors": list(strict["errors"]),
        "strict_research_result_warnings": list(strict["warnings"]),
        "strict_research_result_field_count": int(strict["field_count"]),
        "lowerable_claim_kinds": list(strict["lowerable_claim_kinds"]),
        "freshness_status": str(strict.get("freshness_status") or ""),
        "current_or_evergreen": bool(strict.get("current_or_evergreen", False)),
        "current_or_evergreen_reason": str(
            strict.get("current_or_evergreen_reason") or ""
        ),
        "source_status_apply_blocking": False,
    }
