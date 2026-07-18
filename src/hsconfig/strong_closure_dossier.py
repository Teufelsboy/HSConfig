from __future__ import annotations

from collections.abc import Sequence
import hashlib
from pathlib import Path
import re
from typing import Any

from hsconfig.io import read_json
from hsconfig.research_result_contract import classify_research_result_contract
from hsconfig.research_result_validator import validate_research_result_payload
from hsconfig.strong_promotion_report import build_strong_promotion_report

NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"
DIAGNOSTIC_AUTHORITY = "diagnostic_only"


def build_strong_closure_dossier(
    package_dir: str | Path,
    research_result_paths: Sequence[str | Path] = (),
    source_autopilot_report_path: str | Path | None = None,
) -> dict[str, Any]:
    package_path = Path(package_dir)
    operator_summary = _read_required_json(package_path / NORMAL_APPLY_AUTHORITY)
    package_deck_identity = _package_deck_identity(package_path, operator_summary)
    source_claim_gap_report = _read_optional_json(
        package_path / "reports" / "source_claim_gap_report.json",
        default={"summary": {"blocked_cards": 0}, "cards": {}},
    )
    deck_name = str(package_deck_identity["deck_name"])
    promotion_report = build_strong_promotion_report(
        deck_name=deck_name,
        fixture_stage=_fixture_stage(operator_summary),
        operator_summary=operator_summary,
        source_claim_gap_report=source_claim_gap_report,
    )
    research_rows = [
        _research_row(Path(path), package_deck_identity=package_deck_identity)
        for path in sorted(research_result_paths, key=lambda item: str(item))
    ]
    autopilot_report = (
        _read_required_json(source_autopilot_report_path)
        if source_autopilot_report_path is not None
        else None
    )
    source_backed_status = str(promotion_report["source_backed_status"])
    runtime_package_usable = _runtime_package_usable(operator_summary)
    default_only_runtime_surfaces = list(
        promotion_report["default_only_runtime_surfaces"]
    )
    promotion_ready = bool(promotion_report["promotion_ready"])
    return {
        "schema_version": 1,
        "authority": DIAGNOSTIC_AUTHORITY,
        "operator_gate_impact": DIAGNOSTIC_AUTHORITY,
        "normal_apply_authority": NORMAL_APPLY_AUTHORITY,
        "package": str(package_path),
        "deck_name": deck_name,
        "technical_status": operator_summary.get("technical_status"),
        "semantic_status": operator_summary.get("semantic_status"),
        "source_backed_status": source_backed_status,
        "source_strong_ready": bool(promotion_report["source_strong_ready"]),
        "strong_contract_closed": promotion_ready,
        "promotion_verdict": promotion_report["verdict"],
        "runtime_package_usable": runtime_package_usable,
        "runtime_apply_mode": operator_summary.get("runtime_apply_mode"),
        "runtime_apply_allowed": operator_summary.get("runtime_apply_allowed"),
        "source_status_apply_blocking": False,
        "source_status_diagnostic_only": True,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "first_missing_source_action": promotion_report[
            "first_missing_source_action"
        ],
        "first_missing_chain": promotion_report["first_missing_chain"],
        "source_status_reasons": promotion_report["source_status_reasons"],
        "source_missing_source_actions": promotion_report[
            "source_missing_source_actions"
        ],
        "autopilot_preflight": _autopilot_summary(autopilot_report),
        "research_snapshot_rows": research_rows,
        "summary": _summary(
            source_backed_status=source_backed_status,
            promotion_ready=promotion_ready,
            runtime_package_usable=runtime_package_usable,
            default_only_runtime_surfaces=default_only_runtime_surfaces,
            research_rows=research_rows,
        ),
    }


def _read_required_json(path: str | Path) -> dict[str, Any]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _read_optional_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return _read_required_json(path)


def _deck_name(operator_summary: dict[str, Any]) -> str:
    deck = operator_summary.get("deck", {})
    if isinstance(deck, dict):
        return str(deck.get("name") or "")
    return ""


def _package_deck_identity(
    package_path: Path,
    operator_summary: dict[str, Any],
) -> dict[str, str]:
    deck = operator_summary.get("deck", {})
    if not isinstance(deck, dict):
        deck = {}
    deck_identity = _read_optional_json(
        package_path / "reports" / "deck_identity.json",
        default={},
    )
    deck_fingerprint = _read_optional_json(
        package_path / "reports" / "deck_fingerprint.json",
        default={},
    )
    return {
        "deck_name": str(deck.get("name") or deck_identity.get("deck_name") or ""),
        "deck_code_hash": _normalized_hash(
            deck.get("deck_code_hash")
            or deck_identity.get("deck_code_hash")
            or deck_fingerprint.get("deck_code_hash")
        ),
        "deck_fingerprint": _normalized_hash(
            deck_identity.get("deck_fingerprint")
            or deck_fingerprint.get("deck_fingerprint")
        ),
    }


def _fixture_stage(operator_summary: dict[str, Any]) -> str:
    return (
        "core_source_backed_fixture"
        if operator_summary.get("source_backed_status") == "SOURCE_BACKED_STRONG"
        else "source_informed_valid_fixture"
    )


def _runtime_package_usable(operator_summary: dict[str, Any]) -> bool:
    return (
        operator_summary.get("technical_status") == "VALID_PACKAGE"
        and operator_summary.get("runtime_apply_allowed") is True
        and str(operator_summary.get("runtime_apply_mode") or "") == "load_safe_apply"
    )


def _autopilot_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {"status": "not_provided"}
    return {
        "status": "provided",
        "strong_candidate": bool(report.get("strong_candidate", False)),
        "default_only_runtime_surfaces": list(
            report.get("default_only_runtime_surfaces") or []
        ),
        "first_missing_source_action_by_card": dict(
            report.get("first_missing_source_action_by_card") or {}
        ),
        "first_missing_source_action_by_surface": dict(
            report.get("first_missing_source_action_by_surface") or {}
        ),
    }


def _research_row(
    path: Path,
    *,
    package_deck_identity: dict[str, str],
) -> dict[str, Any]:
    data = _read_required_json(path)
    contract = classify_research_result_contract(data)
    strict_validation = validate_research_result_payload(data)
    research_deck_identity = _research_deck_identity(data)
    deck_name = research_deck_identity["deck_name"]
    package_deck_name_match = _deck_names_match(
        package_deck_identity["deck_name"],
        deck_name,
    )
    package_deck_match = _package_deck_identity_matches(
        package_deck_identity,
        research_deck_identity,
    )
    canonical_promotion_allowed = bool(
        package_deck_match
        and strict_validation["valid"]
        and contract["contract_valid"]
        and contract["canonical_promotion_allowed"]
    )
    return {
        "path": str(path),
        "deck_name": deck_name,
        "package_deck_match": package_deck_match,
        "package_deck_name_match": package_deck_name_match,
        "deck_identity_match_basis": _deck_identity_match_basis(
            package_deck_identity,
            research_deck_identity,
        ),
        "snapshot_relation": _snapshot_relation(
            package_deck_match=package_deck_match,
            package_deck_name_match=package_deck_name_match,
            strict_research_result_valid=bool(strict_validation["valid"]),
        ),
        "source_strength": str(data.get("source_strength") or ""),
        "snapshot_kind": contract["snapshot_kind"],
        "contract_valid": contract["contract_valid"],
        "strict_research_result_valid": strict_validation["valid"],
        "strict_research_result_errors": strict_validation["errors"],
        "strict_research_result_warnings": strict_validation["warnings"],
        "canonical_promotion_allowed": canonical_promotion_allowed,
        "canonical_downgrade_allowed": False,
        "source_status_apply_blocking": False,
        "errors": contract["errors"],
        "warnings": contract["warnings"],
        "lowerable_claim_kinds": contract["lowerable_claim_kinds"],
        "first_missing_source_action": str(
            data.get("first_missing_source_action") or ""
        ),
    }


def _summary(
    *,
    source_backed_status: str,
    promotion_ready: bool,
    runtime_package_usable: bool,
    default_only_runtime_surfaces: Sequence[str],
    research_rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "source_backed_status": source_backed_status,
        "strong_contract_closed": promotion_ready,
        "runtime_package_usable": runtime_package_usable,
        "default_only_runtime_surface_count": len(default_only_runtime_surfaces),
        "research_snapshot_count": len(research_rows),
        "research_promoting_snapshot_count": sum(
            1 for row in research_rows if row["canonical_promotion_allowed"]
        ),
        "different_deck_research_snapshot_count": sum(
            1
            for row in research_rows
            if row["snapshot_relation"] == "different_deck_snapshot"
        ),
        "unverified_deck_research_snapshot_count": sum(
            1
            for row in research_rows
            if row["snapshot_relation"] == "unverified_package_deck_snapshot"
        ),
        "source_status_apply_blocking": False,
        "operator_action": (
            "ready"
            if promotion_ready
            else "use_package_and_close_first_missing_source_action"
        ),
    }


def _deck_names_match(package_deck_name: object, research_deck_name: object) -> bool:
    package_identity = _normalized_deck_identity(package_deck_name)
    research_identity = _normalized_deck_identity(research_deck_name)
    return bool(package_identity and research_identity and package_identity == research_identity)


def _normalized_deck_identity(deck_name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(deck_name).casefold())


def _research_deck_identity(data: dict[str, Any]) -> dict[str, str]:
    deck_code_hash = _normalized_hash(data.get("deck_code_hash"))
    deck_code = str(data.get("deck_code") or "").strip()
    if not deck_code_hash and deck_code:
        deck_code_hash = hashlib.sha256(deck_code.encode("utf-8")).hexdigest()
    return {
        "deck_name": str(data.get("deck_name") or ""),
        "deck_code_hash": deck_code_hash,
        "deck_fingerprint": _normalized_hash(data.get("deck_fingerprint")),
    }


def _package_deck_identity_matches(
    package_deck_identity: dict[str, str],
    research_deck_identity: dict[str, str],
) -> bool:
    comparisons: list[bool] = []
    for field in ("deck_code_hash", "deck_fingerprint"):
        package_value = package_deck_identity.get(field, "")
        research_value = research_deck_identity.get(field, "")
        if package_value and research_value:
            comparisons.append(package_value == research_value)
    return bool(comparisons and all(comparisons))


def _deck_identity_match_basis(
    package_deck_identity: dict[str, str],
    research_deck_identity: dict[str, str],
) -> str:
    matches = [
        field
        for field in ("deck_code_hash", "deck_fingerprint")
        if package_deck_identity.get(field)
        and package_deck_identity.get(field) == research_deck_identity.get(field)
    ]
    return "+".join(matches) if matches else "none"


def _snapshot_relation(
    *,
    package_deck_match: bool,
    package_deck_name_match: bool,
    strict_research_result_valid: bool,
) -> str:
    if package_deck_match:
        if not strict_research_result_valid:
            return "requires_research_result_repair"
        return "current_package_deck_snapshot"
    if package_deck_name_match:
        return "unverified_package_deck_snapshot"
    return "different_deck_snapshot"


def _normalized_hash(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized.removeprefix("sha256:")
    return normalized
