from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

from hsconfig.compile_cardid import _is_effect_only_start_of_game_card
from hsconfig.default_only_runtime_surfaces import (
    default_only_runtime_surface_errors,
    has_default_only_runtime_surfaces,
)
from hsconfig.mechanic_support import (
    MECHANIC_SUPPORT,
    NON_MECHANIC_ROLES,
    ROLE_ALIASES,
    mechanic_lowering_policy,
    normalize_role_token,
)
from hsconfig.package_derivation_receipt import verify_package_derivation_receipt
from hsconfig.role_tokens import has_explicit_opening_hand_mulligan_intent
from hsconfig.runtime_surface_ledger import (
    rederive_runtime_surface_ledger_from_package,
)
from hsconfig.source_document_model import claim_can_lower_to_runtime
from hsconfig.visionai_registry import (
    CARDID_SURFACE_FAMILY,
    FORBIDDEN_RUNTIME_SURFACES,
    NORMAL_APPLY_AUTHORITY,
    NORMAL_RUNTIME_SURFACE_BOUNDARY,
    RUNTIME_SURFACE_ALIASES,
    classify_runtime_surface,
    expected_game_card_id,
    runtime_row_keys,
)
INTENTIONAL_OPERATOR_LEDGER_STATUSES = {
    "emitted",
    "source_backed",
    "policy_backed",
    "static_semantics",
    "static_semantics_backed",
}
RUNTIME_INTENT_DECISIONS = {
    "emitted",
    "runtime_emitted",
    "runtime_lowered",
}
RUNTIME_INTENT_LOWERING_STATUSES = {
    "emitted",
    "runtime_emitted",
    "runtime_lowered",
    "source_backed_runtime",
    "policy_backed_runtime",
}
RUNTIME_INTENT_RESOLUTION_REASONS = {
    "emitted",
    "source_backed_runtime",
    "policy_backed_runtime",
}
NON_EMITTED_RUNTIME_INTENT_MARKERS = {
    "missing_timing",
    "not_emitted",
    "not_seen_by_builder",
    "report_only",
    "suppressed",
    "suppressed_with_reason",
}
SOURCE_TRACE_LANES = {
    "runtime_lowered",
    "runtime_lowerable",
    "deck_matched_public_guide",
    "archetype_matched_public_guide",
    "evergreen_wild_archetype",
    "official_static_semantics",
    "source_backed_static_semantics",
}
SOURCE_TRACE_TYPES = {
    "deck_matched_public_guide",
    "archetype_matched_public_guide",
    "evergreen_wild_archetype",
    "official_static_semantics",
    "static_semantics",
}
PUBLIC_GUIDE_SOURCE_FAMILIES = {
    "guide",
    "guide_fixture",
    "matchup_guide",
    "mulligan_guide",
}
PUBLIC_GUIDE_SOURCE_LANES = {
    "archetype_matched_public_guide",
    "deck_matched_public_guide",
    "evergreen_wild_archetype",
}
PUBLIC_GUIDE_SOURCE_TYPES = {
    "archetype_matched_public_guide",
    "community_guide",
    "deck_matched_public_guide",
    "evergreen_wild_archetype",
    "public_guide",
}
DARKBISHOP_CARD_ID = "SW_448"
SEMANTIC_HANDOFF_STATUSES = {"closed", "attention", "insufficient_evidence"}
SEMANTIC_FALLBACK_SOURCE_LANES = {
    "default_runtime",
    "decklist_only",
    "generic_low_confidence",
    "policy_fallback",
    "source_unclassified",
    "statistical_enrichment",
}


class _LinkedRuntimeOwnerEvidence(NamedTuple):
    runtime_owner_card_id: str
    runtime_emitted: bool


def semantic_handoff_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    existing_status = str(report.get("semantic_handoff_status", ""))
    existing_reasons = report.get("semantic_handoff_reasons")
    if existing_status in SEMANTIC_HANDOFF_STATUSES and isinstance(
        existing_reasons, list
    ):
        return {
            "semantic_handoff_status": existing_status,
            "semantic_handoff_reasons": sorted(
                {str(reason) for reason in existing_reasons if str(reason)}
            ),
        }

    checks = report.get("checks", {})
    if not isinstance(checks, Mapping):
        checks = {}

    reasons: list[str] = []
    trace = checks.get("runtime_row_trace_inventory", {})
    if isinstance(trace, Mapping):
        if trace.get("unreported_runtime_rows"):
            reasons.append("unreported_runtime_rows")
        if trace.get("reported_rows_missing_runtime"):
            reasons.append("reported_rows_missing_runtime")

    surface = checks.get("visionai_semantic_surface", {})
    if isinstance(surface, Mapping):
        attention = surface.get("attention", [])
        if isinstance(attention, list):
            reasons.extend(str(item) for item in attention if str(item))
        for reason in (
            "non_targeted_battlecry_target_rows",
            "effect_only_body_rows",
            "unsupported_report_only_runtime_rows",
            "semantic_default_runtime_rows",
        ):
            if surface.get(reason):
                reasons.append(reason)

    globalvalues = checks.get("globalvalues", {})
    if isinstance(globalvalues, Mapping) and globalvalues.get("missing_overlay_keys"):
        reasons.append("missing_globalvalues_overlay_keys")

    status = "closed" if not reasons else "attention"
    operator = checks.get("operator_summary")
    if isinstance(operator, Mapping) and operator.get("present") is False:
        status = "insufficient_evidence"
        reasons.append("operator_summary_missing_or_invalid")

    problems = report.get("problems", [])
    if isinstance(problems, list) and any(
        isinstance(problem, Mapping)
        and str(problem.get("check", "")) == "config_quality_exception"
        for problem in problems
    ):
        status = "insufficient_evidence"
        reasons.append("config_quality_exception")

    source_evidence = checks.get("source_evidence")
    if isinstance(source_evidence, Mapping):
        source_lanes = {
            str(item)
            for item in _string_list(source_evidence.get("source_lanes"))
            if str(item)
        }
        semantic_runtime_rows = _int_value(
            source_evidence.get("semantic_runtime_rows", 0)
        )
        if (
            (not source_lanes or source_lanes <= SEMANTIC_FALLBACK_SOURCE_LANES)
            and semantic_runtime_rows == 0
        ):
            status = "insufficient_evidence"
            reasons.append("semantic_runtime_evidence_missing")

    return {
        "semantic_handoff_status": status,
        "semantic_handoff_reasons": sorted(set(reasons)),
    }


def build_config_quality_report(package: str | Path) -> dict[str, Any]:
    package = Path(package)
    operator = _read_json(package / "reports" / "operator_summary.json")
    if not isinstance(operator, Mapping):
        report = {
            "schema_version": 1,
            "status": "attention",
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "runtime_write_performed": False,
            "package": str(package),
            "checks": {
                "operator_summary": {
                    "present": False,
                    "path": "reports/operator_summary.json",
                }
            },
            "problems": [
                {
                    "check": "operator_summary_missing_or_invalid",
                    "value": "reports/operator_summary.json",
                }
            ],
        }
        report.update(semantic_handoff_projection(report))
        return report

    card_behavior = _read_json(package / "reports" / "card_behavior_plan_report.json")
    if not isinstance(card_behavior, Mapping):
        card_behavior = {}

    explainability = _read_json(
        package / "reports" / "source_to_runtime_explainability.json"
    )
    if not isinstance(explainability, Mapping):
        explainability = {}

    deck_identity = _read_json(package / "reports" / "deck_identity.json")
    if not isinstance(deck_identity, Mapping):
        deck_identity = {}

    semantic_enrichment = _read_json(
        package / "reports" / "semantic_enrichment_report.json"
    )
    if not isinstance(semantic_enrichment, Mapping):
        semantic_enrichment = {}

    surface_intent = _read_json(package / "reports" / "surface_intent.json")
    if not isinstance(surface_intent, Mapping):
        surface_intent = {}

    gameplan_contract = _read_json(package / "reports" / "gameplan_contract.json")
    if not isinstance(gameplan_contract, Mapping):
        gameplan_contract = {}

    guide_claim_bundle = _read_json(package / "reports" / "guide_claim_bundle.json")
    if not isinstance(guide_claim_bundle, Mapping):
        guide_claim_bundle = {}

    globalvalues_profile = _read_json(
        package / "reports" / "globalvalues_profile.json"
    )
    if not isinstance(globalvalues_profile, Mapping):
        globalvalues_profile = {}

    checks = {
        "operator_summary": _operator_summary_check(operator),
        "card_behavior": _card_behavior_check(card_behavior),
        "source_to_runtime_explainability": _explainability_check(explainability),
        "trace_completeness": _trace_completeness_check(card_behavior, explainability),
        "runtime_row_trace_inventory": _runtime_row_trace_inventory_check(
            package,
            card_behavior,
        ),
        "closure_freshness": _closure_freshness_check(operator),
        "mechanic_runtime_discipline": _mechanic_runtime_discipline_check(
            card_behavior
        ),
        "runtime_json": _runtime_json_check(
            package,
            deck_identity,
            card_behavior,
            explainability,
        ),
        "legacy_surfaces": _legacy_surface_check(package),
        "darkbishop_boundary": _darkbishop_boundary_check(package),
        "config_intent_self_audit": _config_intent_self_audit_check(
            package=package,
            operator=operator,
            deck_identity=deck_identity,
            card_behavior=card_behavior,
            explainability=explainability,
            surface_intent=surface_intent,
        ),
        "surface_intent_projection": _surface_intent_projection_check(
            surface_intent
        ),
        "visionai_semantic_surface": _visionai_semantic_surface_check(
            package=package,
            card_behavior=card_behavior,
            gameplan_contract=gameplan_contract,
            guide_claim_bundle=guide_claim_bundle,
            semantic_enrichment=semantic_enrichment,
        ),
        "globalvalues": _globalvalues_handoff_check(globalvalues_profile),
        "source_evidence": _source_evidence_handoff_check(
            guide_claim_bundle=guide_claim_bundle,
            explainability=explainability,
            card_behavior=card_behavior,
        ),
    }
    checks["semantic_intent_coverage"] = _semantic_intent_coverage_check(
        card_behavior_check=checks["card_behavior"],
        trace_check=checks["trace_completeness"],
        mechanic_check=checks["mechanic_runtime_discipline"],
        semantic_enrichment=semantic_enrichment,
    )
    problems = _problems(checks)
    report = {
        "schema_version": 1,
        "status": "clean" if not problems else "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "package": str(package),
        "checks": checks,
        "problems": problems,
    }
    report.update(semantic_handoff_projection(report))
    return report


def _globalvalues_handoff_check(
    globalvalues_profile: Mapping[str, Any],
) -> dict[str, Any]:
    missing_overlay_keys = _string_list(
        globalvalues_profile.get("missing_overlay_keys")
    )
    return {
        "present": bool(globalvalues_profile),
        "missing_overlay_keys": missing_overlay_keys,
    }


def _source_evidence_handoff_check(
    *,
    guide_claim_bundle: Mapping[str, Any],
    explainability: Mapping[str, Any],
    card_behavior: Mapping[str, Any],
) -> dict[str, Any]:
    source_lanes = sorted(
        _collect_source_lanes(guide_claim_bundle)
        | _collect_source_lanes(explainability)
    )
    return {
        "source_lanes": source_lanes,
        "semantic_runtime_rows": len(_meaningful_cardid_rows(card_behavior)),
    }


def _collect_source_lanes(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        source_lane = str(value.get("source_lane", "")).strip()
        lanes = {source_lane} if source_lane else set()
        for nested in value.values():
            lanes.update(_collect_source_lanes(nested))
        return lanes
    if isinstance(value, list):
        lanes: set[str] = set()
        for nested in value:
            lanes.update(_collect_source_lanes(nested))
        return lanes
    return set()


def _operator_summary_check(operator: Mapping[str, Any]) -> dict[str, Any]:
    default_only = operator.get("default_only_runtime_surfaces", [])
    if not isinstance(default_only, list):
        default_only = ["__invalid_default_only_runtime_surfaces__"]
    no_default_status = operator.get("no_default_only_runtime_status", {})
    normalized_no_default_status: dict[str, Any] | str
    if isinstance(no_default_status, Mapping):
        normalized_no_default_status = dict(no_default_status)
    else:
        normalized_no_default_status = str(no_default_status or "")
    return {
        "present": True,
        "technical_status": str(operator.get("technical_status", "")),
        "semantic_status": str(operator.get("semantic_status", "")),
        "source_status_apply_blocking": bool(
            operator.get("source_status_apply_blocking", False)
        ),
        "default_only_runtime_surfaces": [
            str(surface) for surface in default_only if str(surface).strip()
        ],
        "no_default_only_runtime_status": normalized_no_default_status,
    }


def _card_behavior_check(card_behavior: Mapping[str, Any]) -> dict[str, Any]:
    rows = card_behavior.get("rows", [])
    if not isinstance(rows, list):
        rows = []

    accepted_rows = []
    semantic_missing_rows = []
    semantic_default_rows = []
    semantic_score_rows = []
    out_of_range_rows = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if not _is_meaningful_cardid_row(row):
            continue
        compact = _compact_behavior_row(row)
        accepted_rows.append(compact)
        semantic_score = row.get("semantic_score")
        if not isinstance(semantic_score, Mapping):
            semantic_missing_rows.append(compact)
        else:
            reason = str(semantic_score.get("reason", "")).strip()
            if reason:
                semantic_score_rows.append({**compact, "reason": reason})
            if reason == "semantic_default":
                semantic_default_rows.append({**compact, "reason": "semantic_default"})
        if _numeric_value_out_of_runtime_range(row.get("value")):
            out_of_range_rows.append(compact)

    return {
        "present": bool(card_behavior),
        "accepted_cardid_runtime_rows": len(accepted_rows),
        "semantic_score_missing_rows": semantic_missing_rows,
        "semantic_default_rows": semantic_default_rows,
        "semantic_score_rows": semantic_score_rows,
        "out_of_range_value_rows": out_of_range_rows,
    }


def _is_meaningful_cardid_row(row: Mapping[str, Any]) -> bool:
    surface_family = str(row.get("surface_family", ""))
    surface = str(row.get("surface", "") or row.get("runtime_surface", ""))
    if surface_family != "CARDID.json" and not _looks_like_cardid_surface(surface):
        return False
    if not str(row.get("behavior_block", "")).strip():
        return False
    return row.get("meaningful_runtime_surface", True) is not False


def _looks_like_cardid_surface(surface: str) -> bool:
    try:
        return classify_runtime_surface(surface) == "conditional_card_surface"
    except KeyError:
        return False


def _numeric_value_out_of_runtime_range(value: Any) -> bool:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return False
    return number < 4 or number > 12


def _explainability_check(explainability: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(explainability),
        "has_default_only_runtime_surfaces": has_default_only_runtime_surfaces(
            explainability
        ),
        "default_only_runtime_surface_errors": default_only_runtime_surface_errors(
            explainability
        ),
    }


def _trace_completeness_check(
    card_behavior: Mapping[str, Any],
    explainability: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_rows = _meaningful_cardid_rows(card_behavior)
    traced = _traced_card_ids(explainability)
    traced_claims_by_card = _traced_claim_ids_by_card(explainability)
    missing = [
        _compact_behavior_row(row)
        for row in runtime_rows
        if not _runtime_row_has_trace(row, traced, traced_claims_by_card)
    ]
    return {
        "runtime_rows_missing_trace": missing,
        "traced_card_ids": sorted(traced),
        "runtime_card_ids": sorted(
            {_runtime_owner_card_id(row) for row in runtime_rows}
        ),
    }


def _closure_freshness_check(operator: Mapping[str, Any]) -> dict[str, Any]:
    summary = operator.get("source_to_runtime_explainability_summary")
    if not isinstance(summary, Mapping):
        return {
            "present": False,
            "closure_schema_current": False,
            "cards_missing_closure": 0,
            "cards_total": 0,
            "cards_with_closure": 0,
        }
    return {
        "present": True,
        "closure_schema_current": bool(summary.get("closure_schema_current", False)),
        "cards_missing_closure": _int_value(summary.get("cards_missing_closure", 0)),
        "cards_total": _int_value(summary.get("cards_total", 0)),
        "cards_with_closure": _int_value(summary.get("cards_with_closure", 0)),
    }


def _meaningful_cardid_rows(card_behavior: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = card_behavior.get("rows", [])
    if not isinstance(rows, list):
        return []
    return [
        row for row in rows if isinstance(row, Mapping) and _is_meaningful_cardid_row(row)
    ]


def _runtime_row_signature(
    card_id: str,
    behavior_block: str,
    row: Mapping[str, Any],
) -> tuple[str, str, str, str]:
    return (
        card_id,
        behavior_block,
        str(row.get("condition", "")),
        str(row.get("value", "")),
    )


def _runtime_row_trace_inventory_check(
    package: Path,
    card_behavior: Mapping[str, Any],
) -> dict[str, Any]:
    physical_rows = _runtime_cardid_value_rows(package)
    reported_rows = _meaningful_cardid_rows(card_behavior)
    physical = Counter(
        _runtime_row_signature(
            str(row["card_id"]),
            str(row["behavior_block"]),
            row,
        )
        for row in physical_rows
    )
    reported = Counter(
        _runtime_row_signature(
            _runtime_owner_card_id(row),
            str(row.get("behavior_block", "")),
            row,
        )
        for row in reported_rows
    )
    unreported = [
        _runtime_row_from_signature(signature)
        for signature in sorted((physical - reported).elements())
    ]
    missing_runtime = [
        _runtime_row_from_signature(signature)
        for signature in sorted((reported - physical).elements())
    ]
    return {
        "status": "clean" if not unreported and not missing_runtime else "attention",
        "physical_cardid_runtime_rows": len(physical_rows),
        "reported_cardid_runtime_rows": len(reported_rows),
        "unreported_runtime_rows": unreported,
        "reported_rows_missing_runtime": missing_runtime,
    }


def _runtime_row_from_signature(
    signature: tuple[str, str, str, str],
) -> dict[str, str]:
    card_id, behavior_block, condition, value = signature
    return {
        "card_id": card_id,
        "behavior_block": behavior_block,
        "condition": condition,
        "value": value,
    }


def _compact_behavior_row(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        "card_id": _runtime_owner_card_id(row),
        "behavior_block": str(row.get("behavior_block", "")),
        "value": str(row.get("value", "")),
    }


def _traced_card_ids(explainability: Mapping[str, Any]) -> set[str]:
    traced: set[str] = set()

    claim_rows = explainability.get("claim_rows", [])
    if isinstance(claim_rows, list):
        for row in claim_rows:
            if not isinstance(row, Mapping):
                continue
            if str(row.get("builder_or_router_decision", "")) != "emitted":
                continue
            for emitted_file in _string_list(row.get("emitted_runtime_files")):
                card_id = _file_card_id(emitted_file)
                if card_id:
                    traced.add(card_id)

    card_rows = explainability.get("card_rows", [])
    if isinstance(card_rows, list):
        for row in card_rows:
            if not isinstance(row, Mapping):
                continue
            if not _card_row_has_source_trace(row):
                continue
            card_id = _row_card_id(row)
            if card_id:
                traced.add(card_id)
            for emitted_file in _string_list(row.get("emitted_runtime_files")):
                file_card_id = _file_card_id(emitted_file)
                if file_card_id:
                    traced.add(file_card_id)

    return traced


def _traced_claim_ids_by_card(explainability: Mapping[str, Any]) -> dict[str, set[str]]:
    traced: dict[str, set[str]] = {}

    claim_rows = explainability.get("claim_rows", [])
    if isinstance(claim_rows, list):
        for row in claim_rows:
            if not isinstance(row, Mapping):
                continue
            if str(row.get("builder_or_router_decision", "")) != "emitted":
                continue
            claim_id = _claim_id(row)
            if not claim_id:
                continue
            for emitted_file in _string_list(row.get("emitted_runtime_files")):
                card_id = _file_card_id(emitted_file)
                if card_id:
                    traced.setdefault(card_id, set()).add(claim_id)

    card_rows = explainability.get("card_rows", [])
    if isinstance(card_rows, list):
        for row in card_rows:
            if not isinstance(row, Mapping):
                continue
            evidence_chain = row.get("evidence_chain", [])
            if not isinstance(evidence_chain, list):
                continue
            for item in evidence_chain:
                if not isinstance(item, Mapping):
                    continue
                claim_id = _claim_id(item)
                if not claim_id:
                    continue
                for runtime_file in _string_list(item.get("runtime_files")):
                    card_id = _file_card_id(runtime_file)
                    if card_id:
                        traced.setdefault(card_id, set()).add(claim_id)

    return traced


def _runtime_row_has_trace(
    row: Mapping[str, Any],
    traced_card_ids: set[str],
    traced_claims_by_card: Mapping[str, set[str]],
) -> bool:
    card_id = _runtime_owner_card_id(row)
    row_claim_ids = _runtime_row_claim_ids(row)
    if not row_claim_ids:
        return card_id in traced_card_ids
    return bool(row_claim_ids & traced_claims_by_card.get(card_id, set()))


def _runtime_row_claim_ids(row: Mapping[str, Any]) -> set[str]:
    claim_ids = set()
    claim_id = _claim_id(row)
    if claim_id:
        claim_ids.add(claim_id)
    for source_claim_id in _string_list(row.get("source_claim_ids")):
        source_claim_id = source_claim_id.strip()
        if source_claim_id:
            claim_ids.add(source_claim_id)
    return claim_ids


def _claim_id(row: Mapping[str, Any]) -> str:
    return str(row.get("claim_id", "") or "").strip()


def _card_row_has_source_trace(row: Mapping[str, Any]) -> bool:
    if _source_trace_value(row.get("source_lane")):
        return True
    closure = row.get("closure")
    if isinstance(closure, Mapping) and _source_trace_value(closure.get("lane")):
        return True
    evidence_chain = row.get("evidence_chain", [])
    if not isinstance(evidence_chain, list):
        return False
    return any(
        isinstance(item, Mapping)
        and (
            _source_trace_value(item.get("source_lane"))
            or _source_trace_type(item.get("source_type"))
            or str(item.get("resolution_reason", "")) == "emitted"
        )
        and _string_list(item.get("runtime_files"))
        for item in evidence_chain
    )


def _source_trace_value(value: Any) -> bool:
    return str(value or "") in SOURCE_TRACE_LANES


def _source_trace_type(value: Any) -> bool:
    return str(value or "") in SOURCE_TRACE_TYPES


def _row_card_id(row: Mapping[str, Any]) -> str:
    return str(row.get("card_id", "") or row.get("card", "")).strip()


def _runtime_owner_card_id(row: Mapping[str, Any]) -> str:
    return str(row.get("runtime_card_id") or _row_card_id(row)).strip()


def _file_card_id(value: Any) -> str:
    name = Path(str(value or "")).name
    try:
        if classify_runtime_surface(name) != "conditional_card_surface":
            return ""
    except KeyError:
        return ""
    return expected_game_card_id(name) or ""


def _runtime_value_row_keys(file_name: str) -> set[str]:
    return set(runtime_row_keys(file_name))


_HISTORICAL_SYNTHETIC_CARDID_DIAGNOSTIC_FILES = frozenset(
    {"CARD_DEFAULT.json"}
)


def _diagnostic_card_id(value: Any) -> str:
    card_id = _file_card_id(value)
    if card_id:
        return card_id
    name = Path(str(value or "")).name
    if name in _HISTORICAL_SYNTHETIC_CARDID_DIAGNOSTIC_FILES:
        return name.removesuffix(".json")
    return ""


def _diagnostic_runtime_value_row_keys(file_name: str) -> set[str]:
    try:
        return _runtime_value_row_keys(file_name)
    except KeyError:
        if (
            Path(file_name).name
            not in _HISTORICAL_SYNTHETIC_CARDID_DIAGNOSTIC_FILES
        ):
            raise
        return set(runtime_row_keys(CARDID_SURFACE_FAMILY))


def _expected_cardid_runtime_files(
    deck_identity: Mapping[str, Any],
    card_behavior: Mapping[str, Any],
    explainability: Mapping[str, Any],
) -> set[str]:
    expected = _deck_identity_card_ids(deck_identity)
    expected.update(
        _runtime_owner_card_id(row)
        for row in _meaningful_cardid_rows(card_behavior)
    )
    expected.update(_traced_card_ids(explainability))
    return {card_id for card_id in expected if card_id}


def _deck_identity_card_ids(deck_identity: Mapping[str, Any]) -> set[str]:
    card_ids: set[str] = set()
    for key in ("cards", "main_deck"):
        card_ids.update(_card_ids_from_rows(deck_identity.get(key, [])))

    sideboards = deck_identity.get("sideboards", [])
    if isinstance(sideboards, list):
        for sideboard in sideboards:
            if isinstance(sideboard, Mapping):
                card_ids.update(_card_ids_from_rows(sideboard.get("cards", [])))

    return card_ids


def _card_ids_from_rows(rows: Any) -> set[str]:
    if not isinstance(rows, list):
        return set()
    card_ids: set[str] = set()
    for row in rows:
        if isinstance(row, Mapping):
            card_id = _row_card_id(row)
        else:
            card_id = str(row or "").strip()
        if card_id:
            card_ids.add(card_id)
    return card_ids


def _mechanic_runtime_discipline_check(
    card_behavior: Mapping[str, Any],
) -> dict[str, Any]:
    rows = _meaningful_cardid_rows(card_behavior)
    report_only_rows: list[dict[str, str]] = []
    unregistered: set[str] = set()

    for row in rows:
        for mechanic in _report_only_mechanics_from_row(row):
            policy = mechanic_lowering_policy(mechanic)
            if (
                policy.get("suppression_reason")
                == "unregistered_mechanic_runtime_surface"
            ):
                unregistered.add(mechanic)
            report_only_rows.append(
                {
                    "card_id": _row_card_id(row),
                    "mechanic": mechanic,
                    "behavior_block": str(row.get("behavior_block", "")),
                    "value": str(row.get("value", "")),
                }
            )

    return {
        "status": "attention" if report_only_rows or unregistered else "clean",
        "report_only_runtime_rows": report_only_rows,
        "unregistered_mechanics": sorted(unregistered),
    }


def _semantic_intent_coverage_check(
    *,
    card_behavior_check: Mapping[str, Any],
    trace_check: Mapping[str, Any],
    mechanic_check: Mapping[str, Any],
    semantic_enrichment: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_rows_missing_trace = _list_of_mappings(
        trace_check.get("runtime_rows_missing_trace")
    )
    semantic_score_missing_rows = _list_of_mappings(
        card_behavior_check.get("semantic_score_missing_rows")
    )
    semantic_default_rows = _list_of_mappings(
        card_behavior_check.get("semantic_default_rows")
    )
    report_only_runtime_rows = _list_of_mappings(
        mechanic_check.get("report_only_runtime_rows")
    )
    warning_only = _semantic_warning_only_summary(semantic_enrichment)

    attention: list[dict[str, Any]] = []
    if runtime_rows_missing_trace:
        attention.append(
            {
                "check": "card_behavior_runtime_row_missing_trace",
                "count": len(runtime_rows_missing_trace),
            }
        )
    if semantic_score_missing_rows:
        attention.append(
            {
                "check": "card_behavior_semantic_score_missing",
                "count": len(semantic_score_missing_rows),
            }
        )
    if semantic_default_rows:
        attention.append(
            {
                "check": "card_behavior_semantic_default_visible",
                "count": len(semantic_default_rows),
            }
        )
    if report_only_runtime_rows:
        attention.append(
            {
                "check": "report_only_mechanic_emitted_runtime",
                "count": len(report_only_runtime_rows),
            }
        )

    return {
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "status": "clean" if not attention else "attention",
        "meaningful_cardid_runtime_rows": _int_value(
            card_behavior_check.get("accepted_cardid_runtime_rows", 0)
        ),
        "taxonomy_reason_counts": _taxonomy_reason_counts(card_behavior_check),
        "runtime_rows_missing_trace": runtime_rows_missing_trace,
        "semantic_score_missing_rows": semantic_score_missing_rows,
        "semantic_default_rows": semantic_default_rows,
        "report_only_runtime_rows": report_only_runtime_rows,
        "warning_only_card_count": warning_only["card_count"],
        "warning_only_mechanics": warning_only["mechanics"],
        "attention": attention,
        "first_attention": attention[0]["check"] if attention else None,
    }


def _surface_intent_projection_check(
    surface_intent: Mapping[str, Any],
) -> dict[str, Any]:
    if not surface_intent:
        return {
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "runtime_write_performed": False,
            "present": False,
            "status": "missing",
            "surface_count": 0,
            "row_count": 0,
            "required_surfaces": [],
            "optional_surfaces": [],
            "rich_optional_runtime_surfaces": [],
            "fallback_intent_rows": [],
            "legacy_policy_surface_rows": [],
            "attention": [],
            "first_attention": None,
        }

    rows = _list_of_mappings(surface_intent.get("rows"))
    fallback_rows = [
        {
            "card_id": str(row.get("card_id") or ""),
            "surface": str(row.get("surface") or ""),
            "intent": str(row.get("intent") or ""),
        }
        for row in rows
        if str(row.get("intent_source") or "") == "fallback"
    ]
    legacy_policy_rows = [
        {
            "card_id": str(row.get("card_id") or ""),
            "surface": str(row.get("surface") or ""),
            "intent": str(row.get("intent") or ""),
        }
        for row in rows
        if str(row.get("surface") or "") in {"Presume.json", "Concede.json"}
    ]
    malformed_rows = [
        _surface_intent_row_summary(row)
        for row in rows
        if str(row.get("surface") or "") not in FORBIDDEN_RUNTIME_SURFACES
        and not _is_canonical_surface_intent_row(surface_intent, row)
    ]

    attention: list[dict[str, Any]] = []
    if fallback_rows:
        attention.append(
            {
                "check": "surface_intent_fallback_visible",
                "count": len(fallback_rows),
            }
        )
    if legacy_policy_rows:
        attention.append(
            {
                "check": "surface_intent_legacy_policy_surface_visible",
                "count": len(legacy_policy_rows),
            }
        )
    if malformed_rows:
        attention.append(
            {
                "check": "surface_intent_malformed_row_visible",
                "count": len(malformed_rows),
            }
        )

    return {
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "present": True,
        "status": "clean" if not attention else "attention",
        "surface_count": _int_value(surface_intent.get("surface_count")),
        "row_count": len(rows),
        "required_surfaces": _string_list(surface_intent.get("required_surfaces")),
        "optional_surfaces": _string_list(surface_intent.get("optional_surfaces")),
        "rich_optional_runtime_surfaces": _string_list(
            surface_intent.get("rich_optional_runtime_surfaces")
        ),
        "fallback_intent_rows": fallback_rows,
        "legacy_policy_surface_rows": legacy_policy_rows,
        "malformed_rows": malformed_rows,
        "attention": attention,
        "first_attention": attention[0]["check"] if attention else None,
    }


def _visionai_semantic_surface_check(
    *,
    package: Path,
    card_behavior: Mapping[str, Any],
    gameplan_contract: Mapping[str, Any],
    guide_claim_bundle: Mapping[str, Any],
    semantic_enrichment: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_rows = _runtime_cardid_value_rows(package)
    runtime_blocks = {
        (row["card_id"], row["behavior_block"])
        for row in runtime_rows
        if row["card_id"] and row["behavior_block"]
    }
    report_rows = _meaningful_cardid_rows(card_behavior)
    source_rows_by_claim = _source_rows_by_claim_id(
        gameplan_contract,
        guide_claim_bundle,
    )
    card_roles = _semantic_surface_roles_by_card(
        card_behavior,
        gameplan_contract,
        semantic_enrichment,
    )
    card_specific_source_metadata = _card_specific_source_metadata_cards(
        gameplan_contract,
        semantic_enrichment,
    )

    non_targeted_battlecry_target_rows: list[dict[str, str]] = []
    unsupported_report_only_runtime_rows: list[dict[str, str]] = []
    semantic_default_runtime_rows: list[dict[str, str]] = []
    explicit_before_play_body_authority_cards: set[str] = set()

    for row in report_rows:
        if not _card_behavior_row_is_emitted(row, runtime_blocks):
            continue
        card_id = _row_card_id(row)
        behavior_block = str(row.get("behavior_block", ""))
        linked_source_rows = _linked_source_rows(row, source_rows_by_claim)

        if (
            behavior_block == "BeforeBattlecryTargetBonus"
            and _has_only_non_targeted_battlecry_authority(row, linked_source_rows)
        ):
            non_targeted_battlecry_target_rows.append(_compact_behavior_row(row))

        for mechanic in _report_only_mechanics_from_row(row):
            unsupported_report_only_runtime_rows.append(
                {
                    **_compact_behavior_row(row),
                    "mechanic": mechanic,
                }
            )

        if (
            behavior_block == "BeforePlayCardBonus"
            and _has_explicit_behavior_row_authority(row)
        ):
            explicit_before_play_body_authority_cards.add(card_id)

        semantic_score = row.get("semantic_score")
        if (
            isinstance(semantic_score, Mapping)
            and str(semantic_score.get("reason", "")).strip() == "semantic_default"
            and card_id in card_specific_source_metadata
        ):
            semantic_default_runtime_rows.append(
                {**_compact_behavior_row(row), "reason": "semantic_default"}
            )

    effect_only_body_rows: list[dict[str, str]] = []
    for runtime_row in runtime_rows:
        card_id = runtime_row["card_id"]
        behavior_block = runtime_row["behavior_block"]
        if not _is_effect_only_start_of_game_card(card_roles.get(card_id, set())):
            continue
        if behavior_block == "InHandPlayPriority":
            effect_only_body_rows.append(_compact_runtime_row(runtime_row))
        elif (
            behavior_block == "BeforePlayCardBonus"
            and card_id not in explicit_before_play_body_authority_cards
        ):
            effect_only_body_rows.append(_compact_runtime_row(runtime_row))

    non_targeted_battlecry_target_rows = _dedupe_sorted_rows(
        non_targeted_battlecry_target_rows
    )
    effect_only_body_rows = _dedupe_sorted_rows(effect_only_body_rows)
    unsupported_report_only_runtime_rows = _dedupe_sorted_rows(
        unsupported_report_only_runtime_rows
    )
    semantic_default_runtime_rows = _dedupe_sorted_rows(semantic_default_runtime_rows)
    attention = sorted(
        {
            str(row.get("reason"))
            for row in card_behavior.get("suppressed", [])
            if isinstance(row, Mapping) and str(row.get("reason", "")).strip()
        }
    )
    failed = bool(
        non_targeted_battlecry_target_rows
        or effect_only_body_rows
        or unsupported_report_only_runtime_rows
        or semantic_default_runtime_rows
    )
    return {
        "status": "failed" if failed else "attention" if attention else "clean",
        "non_targeted_battlecry_target_rows": non_targeted_battlecry_target_rows,
        "effect_only_body_rows": effect_only_body_rows,
        "unsupported_report_only_runtime_rows": unsupported_report_only_runtime_rows,
        "semantic_default_runtime_rows": semantic_default_runtime_rows,
        "attention": attention,
    }


def _runtime_cardid_value_rows(package: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for deck_dir in _custom_config_deck_dirs(package):
        for path in sorted(deck_dir.glob("*.json")):
            card_id = _diagnostic_card_id(path.name)
            if not card_id:
                continue
            payload = _read_json(path)
            if not isinstance(payload, Mapping):
                continue
            for block, block_payload in payload.items():
                if block in {"GameCardId", "ConfigComment"}:
                    continue
                values: Any
                if isinstance(block_payload, Mapping):
                    values = block_payload.get("values", [])
                elif isinstance(block_payload, list):
                    values = block_payload
                else:
                    continue
                if not isinstance(values, list):
                    continue
                for value_row in values:
                    if not isinstance(value_row, Mapping):
                        continue
                    rows.append(
                        {
                            "card_id": card_id,
                            "behavior_block": str(block),
                            "condition": str(value_row.get("condition", "")),
                            "value": str(value_row.get("value", "")),
                        }
                    )
    return rows


def _card_behavior_row_is_emitted(
    row: Mapping[str, Any],
    runtime_blocks: set[tuple[str, str]],
) -> bool:
    return (
        _runtime_owner_card_id(row),
        str(row.get("behavior_block", "")),
    ) in runtime_blocks


def _report_only_mechanics_from_row(row: Mapping[str, Any]) -> list[str]:
    mechanics: set[str] = set()

    mechanics.update(
        _report_only_mechanics_from_value(
            row.get("mechanic"),
            source_key="mechanic",
        )
    )
    mechanics.update(
        _report_only_mechanics_from_value(
            row.get("mechanic_families"),
            source_key="mechanic_families",
        )
    )
    mechanics.update(
        _report_only_mechanics_from_value(
            row.get("semantic_families"),
            source_key="semantic_families",
        )
    )
    mechanics.update(
        _report_only_mechanics_from_value(
            row.get("roles"),
            source_key="roles",
        )
    )
    return sorted(mechanics)


def _report_only_mechanics_from_value(value: Any, *, source_key: str) -> set[str]:
    mechanics: set[str] = set()
    for token in _normalized_tokens(value):
        mechanic = _canonical_mechanic_token(token)
        if not _is_report_only_mechanic_token(
            token,
            mechanic,
            source_key=source_key,
        ):
            continue
        mechanics.add(mechanic)
    return mechanics


def _canonical_mechanic_token(token: str) -> str:
    normalized = normalize_role_token(token)
    return ROLE_ALIASES.get(normalized, normalized)


def _is_report_only_mechanic_token(
    token: str,
    mechanic: str,
    *,
    source_key: str,
) -> bool:
    if source_key == "roles" and token in NON_MECHANIC_ROLES:
        return False

    policy = mechanic_lowering_policy(mechanic)
    if policy.get("policy") != "report_only":
        return False

    if source_key == "mechanic":
        return True
    if source_key == "mechanic_families":
        return True
    if source_key == "roles":
        return mechanic in MECHANIC_SUPPORT or token in ROLE_ALIASES
    if source_key == "semantic_families":
        return mechanic in MECHANIC_SUPPORT or token in ROLE_ALIASES
    return False


def _source_rows_by_claim_id(
    gameplan_contract: Mapping[str, Any],
    guide_claim_bundle: Mapping[str, Any],
) -> dict[str, list[Mapping[str, Any]]]:
    rows: list[Mapping[str, Any]] = []
    rows.extend(
        _report_rows(
            gameplan_contract,
            (
                "source_claims",
                "source_backed_actions",
                "static_semantic_actions",
                "unsupported_or_review_only_claims",
            ),
        )
    )
    rows.extend(_report_rows(guide_claim_bundle, ("claims", "unsupported_claims")))
    nested_bundle = gameplan_contract.get("guide_claim_bundle")
    rows.extend(_report_rows(nested_bundle, ("claims", "unsupported_claims")))

    by_claim: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        for claim_id in _row_claim_ids(row):
            by_claim.setdefault(claim_id, []).append(row)
    return by_claim


def _linked_source_rows(
    row: Mapping[str, Any],
    source_rows_by_claim: Mapping[str, list[Mapping[str, Any]]],
) -> list[Mapping[str, Any]]:
    linked: list[Mapping[str, Any]] = []
    seen: set[int] = set()
    for claim_id in _runtime_row_claim_ids(row) | _row_claim_ids(row):
        for source_row in source_rows_by_claim.get(claim_id, []):
            marker = id(source_row)
            if marker in seen:
                continue
            seen.add(marker)
            linked.append(source_row)
    return linked


def _has_only_non_targeted_battlecry_authority(
    row: Mapping[str, Any],
    linked_source_rows: list[Mapping[str, Any]],
) -> bool:
    if not linked_source_rows and not (
        _runtime_row_claim_ids(row) | _row_claim_ids(row)
    ):
        return False
    evidence_rows = [row, *linked_source_rows]
    if _has_target_authority(evidence_rows):
        return False
    return any(_mentions_battlecry(row) for row in evidence_rows)


TARGET_AUTHORITY_TOKENS = {
    "prefer_enemy_hero",
    "prefer_enemy_minion",
    "prefer_friendly_minion",
    "targeting_rule",
}


def _has_target_authority(rows: list[Mapping[str, Any]]) -> bool:
    for row in rows:
        if str(row.get("target_scope", "") or "").strip():
            return True
        qualifiers = row.get("semantic_qualifiers")
        if (
            isinstance(qualifiers, Mapping)
            and str(qualifiers.get("target_scope", "") or "").strip()
        ):
            return True
        tokens = _semantic_surface_tokens(row)
        if tokens & TARGET_AUTHORITY_TOKENS:
            return True
    return False


def _mentions_battlecry(row: Mapping[str, Any]) -> bool:
    tokens = _semantic_surface_tokens(row)
    return "battlecry" in tokens or str(row.get("behavior_block", "")).lower() == (
        "beforebattlecrytargetbonus"
    )


def _has_explicit_behavior_row_authority(row: Mapping[str, Any]) -> bool:
    semantic_score = row.get("semantic_score")
    if (
        isinstance(semantic_score, Mapping)
        and str(semantic_score.get("reason", "")).strip() == "semantic_default"
    ):
        return False
    return bool(_runtime_row_claim_ids(row) | _row_claim_ids(row))


def _semantic_surface_roles_by_card(
    card_behavior: Mapping[str, Any],
    gameplan_contract: Mapping[str, Any],
    semantic_enrichment: Mapping[str, Any],
) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {}
    for row in _meaningful_cardid_rows(card_behavior):
        card_id = _row_card_id(row)
        if card_id:
            roles.setdefault(card_id, set()).update(_semantic_surface_tokens(row))
    for row in _card_metadata_rows(gameplan_contract.get("cards")):
        card_id = _row_card_id(row)
        if card_id:
            roles.setdefault(card_id, set()).update(_semantic_surface_role_tokens(row))
    for row in _report_rows(gameplan_contract, ("card_role_map",)):
        card_id = _row_card_id(row)
        if card_id:
            roles.setdefault(card_id, set()).update(_semantic_surface_role_tokens(row))
    for row in _card_metadata_rows(semantic_enrichment.get("cards")):
        card_id = _row_card_id(row)
        if card_id:
            roles.setdefault(card_id, set()).update(_semantic_surface_role_tokens(row))
    return roles


def _card_specific_source_metadata_cards(
    gameplan_contract: Mapping[str, Any],
    semantic_enrichment: Mapping[str, Any],
) -> set[str]:
    card_ids: set[str] = set()
    for row in _card_metadata_rows(gameplan_contract.get("cards")):
        if _has_card_specific_source_metadata(row):
            card_id = _row_card_id(row)
            if card_id:
                card_ids.add(card_id)
    for row in _report_rows(gameplan_contract, ("card_role_map",)):
        if _has_card_specific_source_metadata(row):
            card_id = _row_card_id(row)
            if card_id:
                card_ids.add(card_id)
    for row in _card_metadata_rows(semantic_enrichment.get("cards")):
        if _has_card_specific_source_metadata(row):
            card_id = _row_card_id(row)
            if card_id:
                card_ids.add(card_id)
    return card_ids


def _card_metadata_rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        rows = []
        for card_id, row in value.items():
            if not isinstance(row, Mapping):
                continue
            normalized = dict(row)
            normalized.setdefault("card_id", str(card_id))
            rows.append(normalized)
        return rows
    if isinstance(value, list):
        return [row for row in value if isinstance(row, Mapping)]
    return []


def _has_card_specific_source_metadata(row: Mapping[str, Any]) -> bool:
    for key in ("roles", "semantic_families", "source_claim_ids"):
        if _string_list(row.get(key)):
            return True
    classification = row.get("classification")
    if isinstance(classification, Mapping):
        return bool(classification)
    return bool(str(classification or "").strip())


def _semantic_surface_role_tokens(row: Mapping[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in ("roles", "semantic_families", "mechanic_families"):
        tokens.update(_normalized_tokens(row.get(key)))
    return tokens


def _semantic_surface_tokens(row: Mapping[str, Any]) -> set[str]:
    tokens = _semantic_surface_role_tokens(row)
    for key in (
        "behavior_block",
        "claim_kind",
        "claim_type",
        "intent",
        "mechanic",
        "runtime_block",
        "stance",
    ):
        tokens.update(_normalized_tokens(row.get(key)))
    return tokens


def _normalized_tokens(value: Any) -> set[str]:
    raw_values = _string_list(value)
    tokens: set[str] = set()
    for raw_value in raw_values:
        token = (
            str(raw_value)
            .strip()
            .lower()
            .replace("'", "")
            .replace("’", "")
            .replace(" ", "_")
            .replace("-", "_")
        )
        if token:
            tokens.add(token)
    return tokens


def _compact_runtime_row(row: Mapping[str, str]) -> dict[str, str]:
    return {
        "card_id": str(row.get("card_id", "")),
        "behavior_block": str(row.get("behavior_block", "")),
        "value": str(row.get("value", "")),
    }


def _dedupe_sorted_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, str]] = []
    for row in rows:
        key = tuple(sorted((str(k), str(v)) for k, v in row.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return sorted(
        deduped,
        key=lambda row: (
            str(row.get("card_id", "")),
            str(row.get("behavior_block", "")),
            str(row.get("mechanic", "")),
            str(row.get("value", "")),
            str(row.get("reason", "")),
        ),
    )


def _semantic_warning_only_summary(
    semantic_enrichment: Mapping[str, Any],
) -> dict[str, Any]:
    cards = semantic_enrichment.get("cards", {})
    if isinstance(cards, Mapping):
        rows = list(cards.values())
    elif isinstance(cards, list):
        rows = cards
    else:
        rows = []

    card_count = 0
    mechanics: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        row_mechanics = _string_list(row.get("warning_only_mechanics"))
        row_mechanics.extend(_string_list(row.get("warning_only")))
        normalized = sorted(
            {mechanic.strip() for mechanic in row_mechanics if mechanic.strip()}
        )
        if not normalized:
            continue
        card_count += 1
        mechanics.update(normalized)

    return {
        "card_count": card_count,
        "mechanics": sorted(mechanics),
    }


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _taxonomy_reason_counts(card_behavior_check: Mapping[str, Any]) -> dict[str, int]:
    rows = _list_of_mappings(card_behavior_check.get("semantic_score_rows"))
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("reason", "")).strip()
        if not reason:
            continue
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _runtime_json_check(
    package: Path,
    deck_identity: Mapping[str, Any],
    card_behavior: Mapping[str, Any],
    explainability: Mapping[str, Any],
) -> dict[str, Any]:
    deck_dirs = _custom_config_deck_dirs(package)
    expected_card_ids = _expected_cardid_runtime_files(
        deck_identity,
        card_behavior,
        explainability,
    )
    metadata_leaks: list[dict[str, Any]] = []
    stray_cardid_files: list[str] = []
    for deck_dir in deck_dirs:
        for path in sorted(deck_dir.glob("*.json")):
            try:
                classification = classify_runtime_surface(path.name)
            except KeyError:
                if (
                    path.name
                    not in _HISTORICAL_SYNTHETIC_CARDID_DIAGNOSTIC_FILES
                ):
                    continue
                classification = "diagnostic_only"
            if classification == "forbidden":
                continue
            if classification == "conditional_card_surface":
                file_card_id = _file_card_id(path.name)
                if file_card_id and file_card_id not in expected_card_ids:
                    stray_cardid_files.append(_relative(path, package))
            payload = _read_json(path)
            if not isinstance(payload, Mapping):
                continue
            for block, block_payload in payload.items():
                if block in {"GameCardId", "ConfigComment"}:
                    continue
                if isinstance(block_payload, Mapping):
                    values = block_payload.get("values", [])
                elif isinstance(block_payload, list):
                    values = block_payload
                else:
                    continue
                if not isinstance(values, list):
                    continue
                for index, value_row in enumerate(values):
                    if not isinstance(value_row, Mapping):
                        continue
                    extra_keys = sorted(
                        set(value_row)
                        - _diagnostic_runtime_value_row_keys(path.name)
                    )
                    if extra_keys:
                        metadata_leaks.append(
                            {
                                "file": _relative(path, package),
                                "block": str(block),
                                "row_index": index,
                                "extra_keys": extra_keys,
                            }
                        )
    return {
        "deck_dir_present": bool(deck_dirs),
        "metadata_leaks": metadata_leaks,
        "stray_cardid_files": sorted(stray_cardid_files),
    }


def _legacy_surface_check(package: Path) -> dict[str, Any]:
    present = []
    custom_config = package / "CustomConfig"
    if not custom_config.is_dir():
        return {"present": present}
    for path in sorted(custom_config.rglob("*.json")):
        if path.name in FORBIDDEN_RUNTIME_SURFACES:
            present.append(_relative(path, package))
    return {"present": present}


def _darkbishop_boundary_check(package: Path) -> dict[str, Any]:
    mulligan_keep_present = False
    effect_runtime_present = False
    linked_owner_evidence = _validated_linked_runtime_owner_evidence(
        package,
        DARKBISHOP_CARD_ID,
    )
    runtime_owner_card_id = (
        linked_owner_evidence.runtime_owner_card_id
        if linked_owner_evidence is not None
        else DARKBISHOP_CARD_ID
    )
    explicit_mulligan_keep_evidence_present = (
        _has_explicit_mulligan_keep_evidence(package, DARKBISHOP_CARD_ID)
    )

    for deck_dir in _custom_config_deck_dirs(package):
        mulligan = _read_json(deck_dir / "Mulligan.json")
        mulligan_keep_present = mulligan_keep_present or _mulligan_keep_mentions_card(
            mulligan,
            DARKBISHOP_CARD_ID,
        )

        if linked_owner_evidence is None:
            runtime_path = deck_dir / f"{DARKBISHOP_CARD_ID}.json"
        elif linked_owner_evidence.runtime_emitted:
            runtime_path = deck_dir / f"{runtime_owner_card_id}.json"
        else:
            continue
        darkbishop_runtime = _read_json(runtime_path)
        if isinstance(darkbishop_runtime, Mapping):
            effect_runtime_present = (
                effect_runtime_present or _has_runtime_effect_rows(darkbishop_runtime)
            )

    return {
        "seen": mulligan_keep_present or effect_runtime_present,
        "mulligan_keep_present": mulligan_keep_present,
        "effect_runtime_present": effect_runtime_present,
        "runtime_owner_card_id": runtime_owner_card_id,
        "explicit_mulligan_keep_evidence_present": (
            explicit_mulligan_keep_evidence_present
        ),
    }


def _validated_linked_runtime_owner_evidence(
    package: Path,
    source_card_id: str,
) -> _LinkedRuntimeOwnerEvidence | None:
    receipt = _read_json(package / "package_derivation_receipt.json")
    ledger = _read_json(package / "reports" / "runtime_surface_ledger.json")
    if not isinstance(receipt, Mapping) or not isinstance(ledger, Mapping):
        return None

    receipt_verified, _reasons = verify_package_derivation_receipt(
        package,
        receipt,
    )
    if not receipt_verified:
        return None

    try:
        rederived_ledger = rederive_runtime_surface_ledger_from_package(package)
    except (OSError, TypeError, ValueError):
        return None
    if dict(ledger) != rederived_ledger:
        return None

    relations = receipt.get("linked_runtime_owners")
    linked_entities = ledger.get("linked_runtime_entities")
    if not isinstance(relations, list) or not isinstance(linked_entities, Mapping):
        return None

    source_relations = [
        relation
        for relation in relations
        if isinstance(relation, Mapping)
        and relation.get("source_card_id") == source_card_id
    ]
    if len(source_relations) != 1:
        return None

    relation = source_relations[0]
    runtime_card_id = str(relation.get("runtime_card_id", ""))
    link_kind = str(relation.get("link_kind", ""))
    source_entities = [
        (str(runtime_id), entity)
        for runtime_id, entity in linked_entities.items()
        if isinstance(entity, Mapping)
        and entity.get("source_card_id") == source_card_id
    ]
    if len(source_entities) != 1:
        return None

    ledger_runtime_card_id, linked_entity = source_entities[0]
    runtime_emitted = linked_entity.get("runtime_emitted")
    receipt_relation = (
        source_card_id,
        runtime_card_id,
        link_kind,
        f"{runtime_card_id}.json",
    )
    ledger_relation = (
        linked_entity.get("source_card_id"),
        linked_entity.get("runtime_card_id"),
        linked_entity.get("link_kind"),
        linked_entity.get("runtime_surface"),
    )
    if (
        not runtime_card_id
        or runtime_card_id == source_card_id
        or not link_kind
        or ledger_runtime_card_id != runtime_card_id
        or ledger_relation != receipt_relation
        or not isinstance(runtime_emitted, bool)
    ):
        return None
    return _LinkedRuntimeOwnerEvidence(
        runtime_owner_card_id=runtime_card_id,
        runtime_emitted=runtime_emitted,
    )


def _custom_config_deck_dirs(package: Path) -> list[Path]:
    custom_config = package / "CustomConfig"
    if not custom_config.is_dir():
        return []
    return sorted(path for path in custom_config.iterdir() if path.is_dir())


def _mulligan_keep_mentions_card(value: Any, card_id: str) -> bool:
    if not isinstance(value, Mapping):
        return False

    for key in ("Keep", "keep"):
        if _json_mentions(value.get(key), card_id):
            return True

    mulligan_block = value.get("Mulligan")
    if not isinstance(mulligan_block, Mapping):
        return False
    rows = mulligan_block.get("values", [])
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        action = str(row.get("value", "") or row.get("action", "")).strip().lower()
        if action not in {"hold", "keep"}:
            continue
        selector = (
            row.get("mulligan")
            or row.get("selector")
            or row.get("card_id")
            or row.get("cards")
        )
        if _json_mentions(selector, card_id):
            return True
    return False


def _has_runtime_effect_rows(payload: Mapping[str, Any]) -> bool:
    for block, block_payload in payload.items():
        if block in {"GameCardId", "ConfigComment"}:
            continue
        if not isinstance(block_payload, Mapping):
            continue
        values = block_payload.get("values", [])
        if isinstance(values, list) and values:
            return True
    return False


def _has_explicit_mulligan_keep_evidence(package: Path, card_id: str) -> bool:
    explicit_claim_ids = _explicit_mulligan_keep_claim_ids(package, card_id)
    if not explicit_claim_ids:
        return False
    return _mulligan_plan_accepts_claim(
        package,
        card_id,
        explicit_claim_ids,
    ) or _source_contract_accepts_claim(package, card_id, explicit_claim_ids)


def _explicit_mulligan_keep_claim_ids(package: Path, card_id: str) -> set[str]:
    claims: set[str] = set()
    bundle = _read_json(package / "reports" / "guide_claim_bundle.json")
    source_refs = _eligible_public_guide_source_refs(bundle)
    for row in _report_rows(bundle, ("claims", "claim_rows")):
        if not _is_explicit_mulligan_keep_claim(row, card_id):
            continue
        if not _is_source_backed_opening_hand_claim(row, source_refs):
            continue
        claim_id = _claim_id(row)
        if claim_id:
            claims.add(claim_id)
    return claims


def _is_explicit_mulligan_keep_claim(row: Mapping[str, Any], card_id: str) -> bool:
    if str(row.get("claim_kind", "") or row.get("claim_type", "")) != "mulligan_keep":
        return False
    return _json_mentions(row.get("cards"), card_id) or _json_mentions(row, card_id)


def _eligible_public_guide_source_refs(bundle: Any) -> set[str]:
    refs: set[str] = set()
    for row in _report_rows(bundle, ("source_evidence_index",)):
        if _string_list(row.get("missing_source_keys")):
            continue
        if str(row.get("source_family", "")).strip() not in PUBLIC_GUIDE_SOURCE_FAMILIES:
            continue
        if not all(
            str(row.get(key, "")).strip()
            for key in ("source_url", "source_title", "retrieved_at")
        ):
            continue
        source_ref = str(row.get("source_ref", "")).strip()
        if source_ref:
            refs.add(source_ref)
    return refs


def _is_source_backed_opening_hand_claim(
    row: Mapping[str, Any],
    eligible_source_refs: set[str],
) -> bool:
    if not claim_can_lower_to_runtime(dict(row)):
        return False
    if not has_explicit_opening_hand_mulligan_intent(row):
        return False

    source_lane = str(row.get("source_lane", "")).strip()
    source_type = str(row.get("source_type", "")).strip()
    if source_lane and source_lane not in PUBLIC_GUIDE_SOURCE_LANES:
        return False
    if not source_lane and source_type not in PUBLIC_GUIDE_SOURCE_TYPES:
        return False

    claim_source_refs = set(_string_list(row.get("source_refs")))
    source_ref = str(row.get("source_ref", "")).strip()
    if source_ref:
        claim_source_refs.add(source_ref)
    return bool(claim_source_refs & eligible_source_refs)


def _mulligan_plan_accepts_claim(
    package: Path,
    card_id: str,
    claim_ids: set[str],
) -> bool:
    plan = _read_json(package / "reports" / "mulligan_plan_report.json")
    if not isinstance(plan, Mapping):
        return False
    for rule in _report_rows(plan, ("rules",)):
        action = str(rule.get("action", "") or rule.get("value", "")).strip().lower()
        if action not in {"hold", "keep"}:
            continue
        if not _json_mentions(rule, card_id):
            continue
        if _row_claim_ids(rule) & claim_ids:
            return True
    return False


def _source_contract_accepts_claim(
    package: Path,
    card_id: str,
    claim_ids: set[str],
) -> bool:
    reports = package / "reports"
    for report_name, row_keys in (
        ("source_contract_audit.json", ("claim_rows", "claim_lifecycle_rows")),
        ("source_to_runtime_explainability.json", ("claim_rows",)),
    ):
        payload = _read_json(reports / report_name)
        for row in _report_rows(payload, row_keys):
            if not _row_claim_ids(row) & claim_ids:
                continue
            if not _is_explicit_mulligan_keep_claim(row, card_id):
                continue
            if _source_contract_row_is_accepted_for_mulligan(row):
                return True
    return False


def _source_contract_row_is_accepted_for_mulligan(row: Mapping[str, Any]) -> bool:
    decisions = {
        str(row.get(key, "")).strip()
        for key in (
            "builder_or_router_decision",
            "runtime_lowering_status",
            "claim_lane",
            "source_lane",
            "readiness_lane",
        )
    }
    if decisions & {"emitted", "runtime_lowered", "runtime_emitted"}:
        return True
    return _json_mentions(row.get("emitted_runtime_files"), "Mulligan.json") or (
        _json_mentions(row.get("runtime_surfaces"), "Mulligan.json")
    )


def _report_rows(payload: Any, row_keys: tuple[str, ...]) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    rows: list[Mapping[str, Any]] = []
    for key in row_keys:
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, Mapping))
        elif isinstance(value, Mapping):
            rows.extend(item for item in value.values() if isinstance(item, Mapping))
    return rows


def _row_claim_ids(row: Mapping[str, Any]) -> set[str]:
    ids = set()
    claim_id = _claim_id(row)
    if claim_id:
        ids.add(claim_id)
    ids.update(item.strip() for item in _string_list(row.get("source_claim_ids")))
    ids.update(item.strip() for item in _string_list(row.get("claim_ids")))
    return {item for item in ids if item}


def _json_mentions(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return value == needle or needle in value
    if isinstance(value, Mapping):
        return any(_json_mentions(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_json_mentions(item, needle) for item in value)
    return False


def _config_intent_self_audit_check(
    *,
    package: Path,
    operator: Mapping[str, Any],
    deck_identity: Mapping[str, Any],
    card_behavior: Mapping[str, Any],
    explainability: Mapping[str, Any],
    surface_intent: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_files = _runtime_files_from_custom_config(package)
    explained_files = _explained_runtime_files_from_reports(
        operator=operator,
        card_behavior=card_behavior,
        explainability=explainability,
        surface_intent=surface_intent,
    )
    normal_apply_authority_drift = _normal_apply_authority_drift(operator)
    deck_card_ids = _deck_identity_card_ids(deck_identity)
    default_only_runtime_surfaces = [
        str(surface)
        for surface in operator.get("default_only_runtime_surfaces", [])
        if str(surface)
    ]
    unsupported_runtime_files: list[str] = []
    for item in runtime_files:
        try:
            classification = classify_runtime_surface(Path(item).name)
        except KeyError:
            unsupported_runtime_files.append(item)
            continue
        if classification == "forbidden":
            unsupported_runtime_files.append(item)
    unsupported_runtime_file_set = set(unsupported_runtime_files)

    runtime_files_without_intent: list[str] = []
    for runtime_file in runtime_files:
        if runtime_file in unsupported_runtime_file_set:
            continue
        basename = Path(runtime_file).name
        card_id = _file_card_id(basename)
        if basename in {"GlobalValues.json", "Mulligan.json"}:
            if basename in explained_files:
                continue
        elif basename == "Combo.json":
            if basename in explained_files:
                continue
        elif card_id and (basename in explained_files or card_id in deck_card_ids):
            continue
        runtime_files_without_intent.append(runtime_file)

    attention: list[dict[str, Any]] = []
    if normal_apply_authority_drift:
        attention.append(
            {
                "check": "normal_apply_authority_drift",
                "count": 1,
            }
        )
    if runtime_files_without_intent:
        attention.append(
            {
                "check": "runtime_file_without_intent",
                "count": len(runtime_files_without_intent),
            }
        )
    if unsupported_runtime_files:
        attention.append(
            {
                "check": "unsupported_runtime_file",
                "count": len(unsupported_runtime_files),
            }
        )
    if default_only_runtime_surfaces:
        attention.append(
            {
                "check": "default_only_runtime_surface",
                "count": len(default_only_runtime_surfaces),
            }
        )
    if bool(operator.get("source_status_apply_blocking", False)):
        attention.append(
            {
                "check": "source_status_apply_blocking",
                "count": 1,
            }
        )

    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "status": "clean" if not attention else "attention",
        "normal_apply_authority": _normal_apply_authority(operator),
        "normal_apply_authority_drift": normal_apply_authority_drift,
        "runtime_surface_boundary": list(NORMAL_RUNTIME_SURFACE_BOUNDARY),
        "runtime_files_total": len(runtime_files),
        "runtime_files_without_intent": runtime_files_without_intent,
        "unsupported_runtime_files": unsupported_runtime_files,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "source_status_apply_blocking": bool(
            operator.get("source_status_apply_blocking", False)
        ),
        "attention": attention,
        "first_attention": attention[0]["check"] if attention else None,
    }


def _normal_apply_authority(operator: Mapping[str, Any]) -> str:
    return NORMAL_APPLY_AUTHORITY


def _normal_apply_authority_drift(operator: Mapping[str, Any]) -> dict[str, str] | None:
    contract = operator.get("runtime_apply_contract", {})
    if isinstance(contract, Mapping):
        authority = str(contract.get("apply_authority", "")).strip()
        if authority and authority != NORMAL_APPLY_AUTHORITY:
            return {
                "expected": NORMAL_APPLY_AUTHORITY,
                "reported": authority,
            }
    return None


def _runtime_files_from_custom_config(package: Path) -> list[str]:
    files: list[str] = []
    custom_config = package / "CustomConfig"
    if not custom_config.is_dir():
        return files
    for path in sorted(custom_config.rglob("*.json")):
        files.append(_relative(path, package))
    return files


def _explained_runtime_files_from_reports(
    *,
    operator: Mapping[str, Any],
    card_behavior: Mapping[str, Any],
    explainability: Mapping[str, Any],
    surface_intent: Mapping[str, Any],
) -> set[str]:
    explained: set[str] = set()

    for row in _report_rows(explainability, ("claim_rows", "card_rows")):
        if _has_emitted_runtime_intent(row):
            explained.update(
                Path(item).name
                for item in _string_list(row.get("emitted_runtime_files"))
            )
            explained.update(
                Path(item).name for item in _string_list(row.get("runtime_surfaces"))
            )
            closure = row.get("closure")
            if isinstance(closure, Mapping):
                explained.update(
                    Path(item).name
                    for item in _string_list(closure.get("runtime_surfaces"))
                )
        evidence_chain = row.get("evidence_chain", [])
        if isinstance(evidence_chain, list):
            for item in evidence_chain:
                if not isinstance(item, Mapping):
                    continue
                if not _has_emitted_runtime_intent(item):
                    continue
                explained.update(
                    Path(value).name
                    for value in _string_list(item.get("runtime_files"))
                )

    for row in _meaningful_cardid_rows(card_behavior):
        card_id = _runtime_owner_card_id(row)
        if card_id:
            explained.add(f"{card_id}.json")

    surface_rows = operator.get("surface_status_ledger", [])
    if isinstance(surface_rows, list):
        for row in surface_rows:
            if not isinstance(row, Mapping):
                continue
            status = str(row.get("status", "")).strip()
            if status not in INTENTIONAL_OPERATOR_LEDGER_STATUSES:
                continue
            surface = _standard_surface_name(row.get("surface"))
            if surface == "per-card <CARDID>.json":
                explained.add(surface)
            elif surface:
                explained.add(surface)

    explained.update(_surface_intent_runtime_files(surface_intent))

    return explained


def _surface_intent_runtime_files(surface_intent: Mapping[str, Any]) -> set[str]:
    explained: set[str] = set()
    for row in _report_rows(surface_intent, ("rows",)):
        if not _is_canonical_surface_intent_row(surface_intent, row):
            continue
        surface = str(row.get("surface") or "").strip()
        intent = str(row.get("intent", "")).strip()
        if not intent or intent == "legacy_policy_surface":
            continue
        explained.add(surface)
    return explained


def _is_canonical_surface_intent_row(
    surface_intent: Mapping[str, Any],
    row: Mapping[str, Any],
) -> bool:
    surface = str(row.get("surface") or "").strip()
    required_surfaces = set(_string_list(surface_intent.get("required_surfaces")))
    optional_surfaces = set(_string_list(surface_intent.get("optional_surfaces")))

    if (
        not surface
        or surface != Path(surface).name
        or surface not in required_surfaces | optional_surfaces
        or surface in FORBIDDEN_RUNTIME_SURFACES
    ):
        return False

    rule_id = str(row.get("rule_id") or "").strip()
    card_id = _row_card_id(row)
    if surface == "GlobalValues.json":
        return (
            surface in required_surfaces
            and not card_id
            and rule_id == "globalvalues_full_key_profile"
        )
    if surface == "Combo.json":
        return surface in optional_surfaces and rule_id == "combo_sequences" and not card_id
    if surface == "Mulligan.json":
        is_bot_delegation = (
            bool(card_id)
            and rule_id == f"{card_id}_mulligan_bot_delegation"
            and str(row.get("intent") or "")
            == "delegate_to_hearthranger_bot"
            and str(row.get("intent_source") or "")
            == "versioned_internal_policy"
            and str(row.get("evidence_lane") or "") == "E"
            and str(row.get("policy_id") or "")
            == "BOT_NATIVE_PRE_RUN"
            and bool(str(row.get("reason_code") or "").strip())
        )
        return (
            surface in required_surfaces
            and bool(card_id)
            and (
                rule_id == f"{card_id}_mulligan_hold"
                or is_bot_delegation
            )
        )

    return (
        surface in required_surfaces
        and bool(card_id)
        and surface == f"{card_id}.json"
        and str(row.get("surface_family") or "") == "CARDID.json"
        and rule_id == f"{card_id}_card_behavior"
    )


def _surface_intent_row_summary(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        "card_id": _row_card_id(row),
        "rule_id": str(row.get("rule_id") or ""),
        "surface": str(row.get("surface") or ""),
    }


def _has_emitted_runtime_intent(row: Mapping[str, Any]) -> bool:
    if _has_non_emitted_runtime_marker(row):
        return False
    if (
        str(row.get("builder_or_router_decision", "")).strip()
        in RUNTIME_INTENT_DECISIONS
    ):
        return True
    if (
        str(row.get("runtime_lowering_status", "")).strip()
        in RUNTIME_INTENT_LOWERING_STATUSES
    ):
        return True
    return (
        str(row.get("resolution_reason", "")).strip()
        in RUNTIME_INTENT_RESOLUTION_REASONS
    )


def _has_non_emitted_runtime_marker(row: Mapping[str, Any]) -> bool:
    if str(row.get("first_missing_link", "")).strip():
        return True
    if str(row.get("suppressed_reason", "")).strip():
        return True
    for key in (
        "builder_or_router_decision",
        "claim_lane",
        "lane",
        "readiness_lane",
        "resolution_reason",
        "runtime_lowering_status",
        "source_lane",
        "surface_gate_decision",
    ):
        if str(row.get(key, "")).strip() in NON_EMITTED_RUNTIME_INTENT_MARKERS:
            return True
    return False


def _standard_surface_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return RUNTIME_SURFACE_ALIASES.get(text, text)


def _problems(checks: dict[str, Any]) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []

    operator = checks["operator_summary"]
    if operator["source_status_apply_blocking"]:
        problems.append(
            {
                "check": "source_status_apply_blocking_must_remain_false",
                "value": True,
            }
        )
    if operator["default_only_runtime_surfaces"]:
        problems.append(
            {
                "check": "operator_default_only_runtime_surfaces",
                "value": operator["default_only_runtime_surfaces"],
            }
        )

    closure = checks["closure_freshness"]
    if not closure["present"]:
        problems.append(
            {
                "check": "source_to_runtime_closure_summary_missing",
                "value": "operator_summary.json",
            }
        )
    elif not closure["closure_schema_current"]:
        problems.append(
            {
                "check": "source_to_runtime_closure_not_current",
                "value": False,
            }
        )
    if closure["cards_missing_closure"]:
        problems.append(
            {
                "check": "source_to_runtime_closure_rows_missing",
                "value": closure["cards_missing_closure"],
            }
        )

    explainability = checks["source_to_runtime_explainability"]
    if explainability["has_default_only_runtime_surfaces"]:
        problems.append(
            {
                "check": "explainability_default_only_runtime_surfaces",
                "value": True,
            }
        )
    if explainability["default_only_runtime_surface_errors"]:
        problems.append(
            {
                "check": "explainability_default_only_runtime_surface_errors",
                "value": explainability["default_only_runtime_surface_errors"],
            }
        )

    trace = checks["trace_completeness"]
    if trace["runtime_rows_missing_trace"]:
        problems.append(
            {
                "check": "card_behavior_runtime_row_missing_trace",
                "value": trace["runtime_rows_missing_trace"],
            }
        )

    runtime_row_inventory = checks["runtime_row_trace_inventory"]
    if runtime_row_inventory["unreported_runtime_rows"]:
        problems.append(
            {
                "check": "unreported_cardid_runtime_rows",
                "value": runtime_row_inventory["unreported_runtime_rows"],
            }
        )
    if runtime_row_inventory["reported_rows_missing_runtime"]:
        problems.append(
            {
                "check": "reported_cardid_rows_missing_runtime",
                "value": runtime_row_inventory["reported_rows_missing_runtime"],
            }
        )

    card_behavior = checks["card_behavior"]
    if card_behavior["semantic_score_missing_rows"]:
        problems.append(
            {
                "check": "card_behavior_semantic_score_missing",
                "value": card_behavior["semantic_score_missing_rows"],
            }
        )
    if card_behavior["semantic_default_rows"]:
        problems.append(
            {
                "check": "card_behavior_semantic_default_visible",
                "value": card_behavior["semantic_default_rows"],
            }
        )
    if card_behavior["out_of_range_value_rows"]:
        problems.append(
            {
                "check": "card_behavior_value_out_of_range",
                "value": card_behavior["out_of_range_value_rows"],
            }
        )

    runtime_json = checks["runtime_json"]
    if runtime_json["metadata_leaks"]:
        problems.append(
            {
                "check": "runtime_json_metadata_leaks",
                "value": runtime_json["metadata_leaks"],
            }
        )
    if runtime_json["stray_cardid_files"]:
        problems.append(
            {
                "check": "stray_cardid_runtime_files",
                "value": runtime_json["stray_cardid_files"],
            }
        )

    mechanic = checks["mechanic_runtime_discipline"]
    if mechanic["report_only_runtime_rows"]:
        problems.append(
            {
                "check": "report_only_mechanic_emitted_runtime",
                "value": mechanic["report_only_runtime_rows"],
            }
        )

    legacy = checks["legacy_surfaces"]
    if legacy["present"]:
        problems.append(
            {
                "check": "forbidden_legacy_runtime_surfaces",
                "value": legacy["present"],
            }
        )

    config_intent = checks["config_intent_self_audit"]
    if config_intent["normal_apply_authority_drift"]:
        problems.append(
            {
                "check": "config_intent_normal_apply_authority_drift",
                "value": config_intent["normal_apply_authority_drift"],
            }
        )
    if config_intent["runtime_files_without_intent"]:
        problems.append(
            {
                "check": "config_intent_runtime_file_without_intent",
                "value": config_intent["runtime_files_without_intent"],
            }
        )
    if config_intent["unsupported_runtime_files"]:
        problems.append(
            {
                "check": "config_intent_unsupported_runtime_files",
                "value": config_intent["unsupported_runtime_files"],
            }
        )

    visionai = checks["visionai_semantic_surface"]
    if visionai["status"] == "failed":
        problems.append(
            {
                "check": "visionai_semantic_surface_failed",
                "value": {
                    key: len(visionai[key])
                    for key in (
                        "non_targeted_battlecry_target_rows",
                        "effect_only_body_rows",
                        "unsupported_report_only_runtime_rows",
                        "semantic_default_runtime_rows",
                    )
                },
            }
        )

    darkbishop = checks["darkbishop_boundary"]
    if (
        darkbishop["mulligan_keep_present"]
        and not darkbishop["explicit_mulligan_keep_evidence_present"]
    ):
        problems.append(
            {
                "check": "darkbishop_mulligan_keep_without_explicit_evidence",
                "value": {"card_id": DARKBISHOP_CARD_ID},
            }
        )

    return problems


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


__all__ = ("build_config_quality_report",)
