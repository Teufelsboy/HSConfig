from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


OPERATOR_SUMMARY_RELATIVE_PATH = Path("reports") / "operator_summary.json"

PARTIAL_STOP_CONDITIONS = {
    "Boarlock": {
        "allowed_actions": {"add_boarlock_fracking_mulligan_source"},
        "reason": "checked public context does not expose explicit Fracking keep/discard text",
    },
    "Kingslayer": {
        "allowed_actions": {"add_kingslayer_quick_pick_mulligan_source"},
        "reason": "checked public context does not expose explicit Quick Pick mulligan text",
    },
}


def build_source_closure_optimizer_report(
    package_dir: str | Path,
    *,
    candidate_proof_path: str | Path | None = None,
    dossier: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    package_path = Path(package_dir)
    operator_summary = _read_json(package_path / OPERATOR_SUMMARY_RELATIVE_PATH)
    deck_name = _deck_name(operator_summary, package_path)
    research_dossier = dict(dossier or {})
    candidate_row = _candidate_row(deck_name, candidate_proof_path)
    decision_payload = _classify(
        deck_name=deck_name,
        operator_summary=operator_summary,
        candidate_row=candidate_row,
    )

    runtime_package_usable = (
        operator_summary.get("technical_status") == "VALID_PACKAGE"
        and operator_summary.get("runtime_load_safe") is not False
    )
    closure = operator_summary.get("source_backed_strong_closure") or {}
    first_missing_source_action = _first_missing_source_action(
        operator_summary,
        closure,
    )

    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "normal_apply_authority": str(OPERATOR_SUMMARY_RELATIVE_PATH),
        "deck_name": deck_name,
        "package_dir": str(package_path),
        "decision": decision_payload["decision"],
        "decision_reason": decision_payload["reason"],
        "recommended_operator_action": decision_payload["action"],
        "technical_status": operator_summary.get("technical_status"),
        "runtime_package_usable": runtime_package_usable,
        "source_status_apply_blocking": bool(
            operator_summary.get("source_status_apply_blocking", False)
        ),
        "source_backed_status": operator_summary.get("source_backed_status"),
        "semantic_status": operator_summary.get("semantic_status"),
        "source_backed_strong_closed": _source_backed_strong_closed(closure),
        "first_missing_source_action": first_missing_source_action,
        "default_only_runtime_surfaces": list(
            operator_summary.get("default_only_runtime_surfaces") or []
        ),
        "default_only_blocks_strong": decision_payload["default_only_blocks_strong"],
        "blocking_reasons": decision_payload["blocking_reasons"],
        "candidate_strength_ceiling": candidate_row.get("expected_strength_ceiling"),
        "candidate_manifest_row_found": bool(candidate_row),
        "research_result_found": bool(research_dossier),
        "research_source_strength": research_dossier.get("source_strength"),
        "research_first_missing_source_action": research_dossier.get(
            "first_missing_source_action"
        ),
    }


def build_source_closure_priority_queue(
    package_dirs: list[str | Path],
    *,
    candidate_proof_path: str | Path | None = None,
    research_results_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = [
        build_source_closure_optimizer_report(
            package_dir,
            candidate_proof_path=candidate_proof_path,
            dossier=_research_dossier_for_package(package_dir, research_results_dir),
        )
        for package_dir in package_dirs
    ]
    priority_rows = [record for record in records if record["decision"] != "strong"]
    priority_rows.sort(
        key=lambda row: (
            _priority_bucket(row),
            str(row.get("deck_name") or ""),
        )
    )
    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "normal_apply_authority": str(OPERATOR_SUMMARY_RELATIVE_PATH),
        "summary": {
            "deck_count": len(records),
            "strong_count": sum(1 for row in records if row["decision"] == "strong"),
            "partial_count": sum(1 for row in records if row["decision"] != "strong"),
            "apply_blocker_count": sum(
                1 for row in records if row["source_status_apply_blocking"] is True
            ),
            "default_only_count": sum(
                1 for row in records if row["default_only_runtime_surfaces"]
            ),
        },
        "records": records,
        "priority_rows": priority_rows,
    }


def _classify(
    *,
    deck_name: str,
    operator_summary: Mapping[str, Any],
    candidate_row: Mapping[str, Any],
) -> dict[str, Any]:
    default_only_surfaces = list(operator_summary.get("default_only_runtime_surfaces") or [])
    closure = operator_summary.get("source_backed_strong_closure") or {}
    first_action = _first_missing_source_action(operator_summary, closure)
    candidate_ceiling = str(candidate_row.get("expected_strength_ceiling") or "")

    if operator_summary.get("technical_status") != "VALID_PACKAGE":
        return _decision(
            "invalid_package",
            "technical package status is not VALID_PACKAGE",
            "fix package validity before source-depth closure",
        )

    if default_only_surfaces:
        return _decision(
            "partial_source_action_needed",
            "default-only runtime surfaces are visible and cannot prove Strong",
            "replace default-only runtime surfaces with source-backed, policy-backed, or static-semantics-backed rows",
            default_only_blocks_strong=True,
            blocking_reasons=["default_only_runtime_surfaces_present"],
        )

    if (
        operator_summary.get("source_backed_status") == "SOURCE_BACKED_STRONG"
        and operator_summary.get("semantic_status") == "SOURCE_BACKED_STRONG"
        and _source_backed_strong_closed(closure)
        and first_action == "none"
    ):
        return _decision(
            "strong",
            "operator summary closes Strong without default-only runtime surfaces",
            "none",
        )

    stop_condition = PARTIAL_STOP_CONDITIONS.get(deck_name)
    if stop_condition and first_action in stop_condition["allowed_actions"]:
        return _decision(
            "preserved_partial_stop_condition",
            stop_condition["reason"],
            first_action,
        )

    if candidate_ceiling == "context_only":
        return _decision(
            "context_only_load_safe",
            "candidate manifest exposes context only and cannot close runtime surfaces",
            first_action,
        )

    return _decision(
        "partial_source_action_needed",
        "source-depth closure still has an explicit missing source action",
        first_action,
    )


def _decision(
    decision: str,
    reason: str,
    action: str,
    *,
    default_only_blocks_strong: bool = False,
    blocking_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "reason": reason,
        "action": action,
        "default_only_blocks_strong": default_only_blocks_strong,
        "blocking_reasons": list(blocking_reasons or []),
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _deck_name(operator_summary: Mapping[str, Any], package_path: Path) -> str:
    value = operator_summary.get("deck_name") or operator_summary.get("deck")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Mapping):
        nested_name = value.get("name")
        if isinstance(nested_name, str) and nested_name.strip():
            return nested_name.strip()
    return package_path.parent.name or package_path.name


def _source_backed_strong_closed(closure: Mapping[str, Any]) -> bool:
    if closure.get("closed") is True:
        return True
    if closure.get("promotion_ready") is True:
        return True
    return (
        closure.get("closure_profile_closed") is True
        and str(closure.get("status") or "") == "ready"
    )


def _first_missing_source_action(
    operator_summary: Mapping[str, Any],
    closure: Mapping[str, Any],
) -> str:
    action = closure.get("first_missing_source_action")
    if action is None:
        action = operator_summary.get("first_missing_source_action")
    return str(action or "unknown")


def _candidate_row(
    deck_name: str,
    candidate_proof_path: str | Path | None,
) -> dict[str, Any]:
    if candidate_proof_path is None:
        return {}
    payload = _read_json(Path(candidate_proof_path))
    for row in payload.get("decks", []):
        if row.get("deck_name") == deck_name:
            return dict(row)
    return {}


def _priority_bucket(row: Mapping[str, Any]) -> int:
    if row.get("default_only_runtime_surfaces"):
        return 0
    if row.get("decision") == "partial_source_action_needed":
        return 1
    if row.get("decision") == "preserved_partial_stop_condition":
        return 2
    if row.get("decision") == "context_only_load_safe":
        return 3
    return 4


def _research_dossier_for_package(
    package_dir: str | Path,
    research_results_dir: str | Path | None,
) -> dict[str, Any]:
    if research_results_dir is None:
        return {}

    package_path = Path(package_dir)
    operator = _read_json(package_path / OPERATOR_SUMMARY_RELATIVE_PATH)
    deck = _deck_name(operator, package_path)
    result_path = Path(research_results_dir) / f"{deck}.json"
    if not result_path.exists():
        return {}
    return _read_json(result_path)
