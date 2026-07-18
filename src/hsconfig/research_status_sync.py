from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import re
from typing import Any

from hsconfig.io import read_json
from hsconfig.research_result_contract import classify_research_result_contract
from hsconfig.research_result_validator import validate_research_result_payload


NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"
DIAGNOSTIC_AUTHORITY = "diagnostic_only"
STRONG_STATUS = "SOURCE_BACKED_STRONG"
PARTIAL_STATUS = "SOURCE_BACKED_PARTIAL"
SEED_STRENGTHS = {
    "candidate_url_only",
    "decklist_or_stats_only",
    "decklist_only",
    "missing",
    "snippet_only",
    "stats_only",
    "unfetched_acquisition_seed",
}


def build_research_status_sync_report(
    package_dir: str | Path,
    research_result_paths: Sequence[str | Path],
) -> dict[str, Any]:
    package_path = Path(package_dir)
    operator_summary = _read_json(package_path / NORMAL_APPLY_AUTHORITY)
    canonical = _canonical_status(operator_summary)
    rows = [
        _research_snapshot_row(canonical, Path(path))
        for path in sorted(research_result_paths, key=lambda path: str(path))
    ]
    return {
        "schema_version": 1,
        "authority": DIAGNOSTIC_AUTHORITY,
        "operator_gate_impact": DIAGNOSTIC_AUTHORITY,
        "normal_apply_authority": NORMAL_APPLY_AUTHORITY,
        "package": str(package_path),
        "canonical_package_status": canonical,
        "research_snapshot_rows": rows,
        "summary": _summary(canonical, rows),
    }


def _read_json(path: Path) -> dict[str, Any]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _canonical_status(operator_summary: Mapping[str, Any]) -> dict[str, Any]:
    deck = operator_summary.get("deck", {})
    deck_name = deck.get("name", "") if isinstance(deck, Mapping) else ""
    return {
        "deck_name": str(deck_name),
        "technical_status": str(operator_summary.get("technical_status") or ""),
        "semantic_status": str(operator_summary.get("semantic_status") or ""),
        "source_backed_status": str(
            operator_summary.get("source_backed_status")
            or operator_summary.get("source_status")
            or operator_summary.get("static_contract_status")
            or ""
        ),
        "source_strong_ready": bool(operator_summary.get("source_strong_ready", False)),
        "first_missing_source_action": str(
            operator_summary.get("first_missing_source_action") or ""
        ),
        "source_status_apply_blocking": bool(
            operator_summary.get("source_status_apply_blocking", False)
        ),
        "source_status_diagnostic_only": bool(
            operator_summary.get("source_status_diagnostic_only", True)
        ),
        "default_only_runtime_surfaces": list(
            operator_summary.get("default_only_runtime_surfaces") or []
        ),
        "no_default_only_runtime_status": str(
            operator_summary.get("no_default_only_runtime_status") or ""
        ),
    }


def _research_snapshot_row(
    canonical: Mapping[str, Any],
    path: Path,
) -> dict[str, Any]:
    data = _read_json(path)
    contract = classify_research_result_contract(data)
    strict_validation = validate_research_result_payload(data)
    research_status = _research_status(data)
    research_strength = str(data.get("source_strength") or research_status or "")
    research_kind = str(contract["snapshot_kind"])
    research_deck_name = str(data.get("deck_name") or "")
    relation = _snapshot_relation(
        deck_names_match=_deck_names_match(canonical["deck_name"], research_deck_name),
        canonical_status=str(canonical["source_backed_status"]),
        research_status=research_status,
        research_kind=research_kind,
    )
    return {
        "path": str(path),
        "deck_name": research_deck_name,
        "canonical_deck_name": canonical["deck_name"],
        "research_source_backed_status": research_status,
        "research_source_strength": research_strength,
        "research_snapshot_kind": research_kind,
        "research_contract_valid": contract["contract_valid"],
        "research_canonical_promotion_allowed": contract[
            "canonical_promotion_allowed"
        ],
        "research_canonical_downgrade_allowed": contract[
            "canonical_downgrade_allowed"
        ],
        "research_contract_errors": contract["errors"],
        "strict_research_result_valid": strict_validation["valid"],
        "strict_research_result_errors": strict_validation["errors"],
        "strict_research_result_warnings": strict_validation["warnings"],
        "strict_research_result_field_count": strict_validation["field_count"],
        "research_first_missing_source_action": str(
            data.get("first_missing_source_action") or ""
        ),
        "canonical_source_backed_status": canonical["source_backed_status"],
        "canonical_first_missing_source_action": canonical[
            "first_missing_source_action"
        ],
        "snapshot_relation": relation,
        "canonical_downgrade_allowed": False,
        "canonical_promotion_allowed": False,
        "source_status_apply_blocking": False,
        "recommended_refresh_action": _recommended_refresh_action(relation),
    }


def _research_status(data: Mapping[str, Any]) -> str:
    explicit = str(
        data.get("source_backed_status")
        or data.get("source_status")
        or data.get("static_contract_status")
        or ""
    ).strip()
    if explicit:
        return explicit
    strength = str(data.get("source_strength") or "").strip()
    if strength == STRONG_STATUS:
        return STRONG_STATUS
    if strength in SEED_STRENGTHS:
        return PARTIAL_STATUS
    return strength or "unknown"


def _research_snapshot_kind(source_strength: str, research_status: str) -> str:
    normalized = source_strength.strip()
    if normalized in SEED_STRENGTHS:
        return "seed_only"
    if normalized == STRONG_STATUS or research_status == STRONG_STATUS:
        return "canonical_like"
    if not normalized:
        return "unknown"
    return "status_snapshot"


def _snapshot_relation(
    *,
    deck_names_match: bool,
    canonical_status: str,
    research_status: str,
    research_kind: str,
) -> str:
    if not deck_names_match:
        return "different_deck_snapshot"
    if research_kind == "seed_only" and canonical_status == STRONG_STATUS:
        return "stale_or_seed_only"
    if (
        canonical_status == STRONG_STATUS
        and research_status == STRONG_STATUS
        and research_kind != "strong"
    ):
        return "stale_or_seed_only"
    if canonical_status == research_status:
        return "current_with_canonical"
    if canonical_status == STRONG_STATUS and research_status != STRONG_STATUS:
        return "stale_or_seed_only"
    if canonical_status != research_status:
        return "conflicts_with_canonical"
    return "current_with_canonical"


def _recommended_refresh_action(relation: str) -> str:
    if relation == "current_with_canonical":
        return "none"
    if relation == "stale_or_seed_only":
        return "refresh_research_snapshot_from_canonical_package"
    if relation == "conflicts_with_canonical":
        return "inspect_package_and_research_snapshot_before_updating_docs"
    if relation == "different_deck_snapshot":
        return "inspect_research_snapshot_deck_identity"
    return "inspect_research_snapshot"


def _deck_names_match(canonical_deck_name: object, research_deck_name: object) -> bool:
    canonical_identity = _normalized_deck_identity(canonical_deck_name)
    research_identity = _normalized_deck_identity(research_deck_name)
    return bool(canonical_identity and research_identity and canonical_identity == research_identity)


def _normalized_deck_identity(deck_name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(deck_name).casefold())


def _summary(
    canonical: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    matching_rows = [
        row
        for row in rows
        if row["snapshot_relation"] != "different_deck_snapshot"
    ]
    stale_or_seed_count = sum(
        1
        for row in matching_rows
        if row["snapshot_relation"] == "stale_or_seed_only"
    )
    mismatch_count = sum(
        1
        for row in matching_rows
        if row["snapshot_relation"] == "conflicts_with_canonical"
    )
    different_deck_count = len(rows) - len(matching_rows)
    refresh_actions = sorted(
        {
            str(row["recommended_refresh_action"])
            for row in rows
            if row["recommended_refresh_action"] != "none"
        }
    )
    return {
        "canonical_deck_name": canonical["deck_name"],
        "canonical_source_backed_status": canonical["source_backed_status"],
        "canonical_source_strong_ready": canonical["source_strong_ready"],
        "canonical_first_missing_source_action": canonical[
            "first_missing_source_action"
        ],
        "missing_research_snapshot": not matching_rows,
        "research_snapshot_count": len(rows),
        "matching_research_snapshot_count": len(matching_rows),
        "different_deck_snapshot_count": different_deck_count,
        "stale_or_seed_snapshot_count": stale_or_seed_count,
        "status_mismatch_count": mismatch_count,
        "canonical_downgrade_allowed": False,
        "canonical_promotion_allowed": False,
        "source_status_apply_blocking": False,
        "recommended_refresh_actions": refresh_actions,
    }
