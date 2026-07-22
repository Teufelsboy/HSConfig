from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hsconfig.default_only_runtime_surfaces import (
    default_only_runtime_surface_errors,
    has_default_only_runtime_surfaces,
)
from hsconfig.mechanic_support import mechanic_lowering_policy


FORBIDDEN_LEGACY_RUNTIME_SURFACES = {
    "CardBehavior.json",
    "Concede.json",
    "Presume.json",
}

RUNTIME_VALUE_ROW_KEYS = {"comment", "condition", "value"}
SPECIAL_RUNTIME_FILES = {
    "Combo.json",
    "GlobalValues.json",
    "Mulligan.json",
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
DARKBISHOP_CARD_ID = "SW_448"


def build_config_quality_report(package: str | Path) -> dict[str, Any]:
    package = Path(package)
    operator = _read_json(package / "reports" / "operator_summary.json")
    if not isinstance(operator, Mapping):
        return {
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

    checks = {
        "operator_summary": _operator_summary_check(operator),
        "card_behavior": _card_behavior_check(card_behavior),
        "source_to_runtime_explainability": _explainability_check(explainability),
        "trace_completeness": _trace_completeness_check(card_behavior, explainability),
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
    }
    checks["semantic_intent_coverage"] = _semantic_intent_coverage_check(
        card_behavior_check=checks["card_behavior"],
        trace_check=checks["trace_completeness"],
        mechanic_check=checks["mechanic_runtime_discipline"],
        semantic_enrichment=semantic_enrichment,
    )
    problems = _problems(checks)
    return {
        "schema_version": 1,
        "status": "clean" if not problems else "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "package": str(package),
        "checks": checks,
        "problems": problems,
    }


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
    if surface == "CARDID.json":
        return True
    if not surface.endswith(".json"):
        return False
    return Path(surface).name not in SPECIAL_RUNTIME_FILES


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
        "runtime_card_ids": sorted({_row_card_id(row) for row in runtime_rows}),
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


def _compact_behavior_row(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        "card_id": _row_card_id(row),
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
    card_id = _row_card_id(row)
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


def _file_card_id(value: Any) -> str:
    name = Path(str(value or "")).name
    if not name.endswith(".json") or name in SPECIAL_RUNTIME_FILES:
        return ""
    return name[:-5]


def _expected_cardid_runtime_files(
    deck_identity: Mapping[str, Any],
    card_behavior: Mapping[str, Any],
    explainability: Mapping[str, Any],
) -> set[str]:
    expected = _deck_identity_card_ids(deck_identity)
    expected.update(_row_card_id(row) for row in _meaningful_cardid_rows(card_behavior))
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
        mechanic = str(row.get("mechanic", "") or "").strip()
        if not mechanic:
            continue
        policy = mechanic_lowering_policy(mechanic)
        if policy.get("suppression_reason") == "unregistered_mechanic_runtime_surface":
            unregistered.add(mechanic)
        if policy.get("policy") != "report_only":
            continue
        report_only_rows.append(
            {
                "card_id": _row_card_id(row),
                "mechanic": mechanic,
                "behavior_block": str(row.get("behavior_block", "")),
                "value": str(row.get("value", "")),
            }
        )

    return {
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
            if path.name in SPECIAL_RUNTIME_FILES:
                continue
            if path.name in FORBIDDEN_LEGACY_RUNTIME_SURFACES:
                continue
            file_card_id = _file_card_id(path.name)
            if file_card_id and file_card_id not in expected_card_ids:
                stray_cardid_files.append(_relative(path, package))
            payload = _read_json(path)
            if not isinstance(payload, Mapping):
                continue
            for block, block_payload in payload.items():
                if block in {"GameCardId", "ConfigComment"}:
                    continue
                if not isinstance(block_payload, Mapping):
                    continue
                values = block_payload.get("values", [])
                if not isinstance(values, list):
                    continue
                for index, value_row in enumerate(values):
                    if not isinstance(value_row, Mapping):
                        continue
                    extra_keys = sorted(set(value_row) - RUNTIME_VALUE_ROW_KEYS)
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
        if path.name in FORBIDDEN_LEGACY_RUNTIME_SURFACES:
            present.append(_relative(path, package))
    return {"present": present}


def _darkbishop_boundary_check(package: Path) -> dict[str, Any]:
    mulligan_keep_present = False
    effect_runtime_present = False
    explicit_mulligan_keep_evidence_present = (
        _has_explicit_mulligan_keep_evidence(package, DARKBISHOP_CARD_ID)
    )

    for deck_dir in _custom_config_deck_dirs(package):
        mulligan = _read_json(deck_dir / "Mulligan.json")
        mulligan_keep_present = mulligan_keep_present or _mulligan_keep_mentions_card(
            mulligan,
            DARKBISHOP_CARD_ID,
        )

        darkbishop_runtime = _read_json(deck_dir / f"{DARKBISHOP_CARD_ID}.json")
        if isinstance(darkbishop_runtime, Mapping):
            effect_runtime_present = (
                effect_runtime_present or _has_runtime_effect_rows(darkbishop_runtime)
            )

    return {
        "seen": mulligan_keep_present or effect_runtime_present,
        "mulligan_keep_present": mulligan_keep_present,
        "effect_runtime_present": effect_runtime_present,
        "explicit_mulligan_keep_evidence_present": (
            explicit_mulligan_keep_evidence_present
        ),
    }


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
    reports = package / "reports"
    for report_name, row_keys in (
        ("guide_claim_bundle.json", ("claims", "claim_rows")),
        ("source_contract_audit.json", ("claim_rows", "claim_lifecycle_rows")),
        ("source_to_runtime_explainability.json", ("claim_rows",)),
    ):
        payload = _read_json(reports / report_name)
        for row in _report_rows(payload, row_keys):
            if _is_explicit_mulligan_keep_claim(row, card_id):
                claim_id = _claim_id(row)
                claims.add(claim_id or "__explicit_unidentified_claim__")
    return claims


def _is_explicit_mulligan_keep_claim(row: Mapping[str, Any], card_id: str) -> bool:
    if str(row.get("claim_kind", "") or row.get("claim_type", "")) != "mulligan_keep":
        return False
    return _json_mentions(row.get("cards"), card_id) or _json_mentions(row, card_id)


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
