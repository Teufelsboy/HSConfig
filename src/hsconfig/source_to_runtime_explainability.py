from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from hsconfig.runtime_entity_owner import partition_runtime_entity_owner_rows
from hsconfig.source_claim_gap_report import NEXT_ACTION_BY_MISSING_LINK


LANE_RANK = {
    "runtime_lowered": 0,
    "runtime_lowerable": 0,
    "runtime_evidence_required": 1,
    "suppressed_with_reason": 2,
    "suppressed_or_conditional": 2,
    "unsupported_or_unmapped": 3,
    "report_only": 4,
}
CLAIM_KIND_RANK = {
    "hero_power_transform": 0,
    "mechanic_usage": 90,
}
MULLIGAN_AUTHORITY_ACTION_BY_REASON = {
    "mulligan_requires_public_guide_source": "add_public_guide_source",
    "mulligan_requires_exact_deck_match": "add_exact_deck_matched_source",
    "mulligan_requires_target_deck_fingerprint": (
        "decode_current_target_deck_fingerprint"
    ),
    "mulligan_requires_verified_exact_deck_evidence": (
        "add_exact_deck_matched_source"
    ),
    "mulligan_exact_deck_fingerprint_mismatch": (
        "replace_source_with_current_target_deck_match"
    ),
    "mulligan_requires_complete_exact_deck_evidence": (
        "add_complete_exact_deck_decode_evidence"
    ),
    "mulligan_requires_verified_source_receipt": (
        "rebuild_source_documents_for_verified_receipt"
    ),
    "mulligan_requires_promotion_eligible_source": "add_promotion_eligible_source",
    "mulligan_requires_full_text_source": "add_full_text_public_guide_source",
    "mulligan_requires_deck_matched_public_guide_lane": (
        "add_deck_matched_public_guide_source"
    ),
}

REPORT_PATH = "reports/source_to_runtime_explainability.json"


def build_source_to_runtime_explainability_report(
    source_contract_audit_report: Mapping[str, Any] | None = None,
    *,
    audit: Mapping[str, Any] | None = None,
    runtime_files: Sequence[str] | set[str] | None = None,
    card_behavior_plan: Mapping[str, Any] | None = None,
    runtime_surface_ledger: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project source-contract audit rows into operator-facing diagnostics.

    The report explains why claims did or did not become runtime files. It is
    intentionally diagnostic-only and never contributes apply authority.
    """
    audit_report = _normalized_audit(
        audit if audit is not None else source_contract_audit_report,
        runtime_files=runtime_files,
    )
    accepted_behavior_rows, owner_collisions = (
        partition_runtime_entity_owner_rows(
            row
            for row in (card_behavior_plan or {}).get("rows", [])
            if isinstance(row, Mapping)
        )
    )
    runtime_entity_transitions = _runtime_entity_transitions(
        {"rows": accepted_behavior_rows}
    )
    ownership_by_claim_id = {
        row["claim_id"]: row
        for row in runtime_entity_transitions
        if row.get("claim_id")
    }
    claim_rows = _claim_rows(
        audit_report,
        ownership_by_claim_id=ownership_by_claim_id,
    )
    card_rows = _apply_runtime_surface_ledger(
        _card_rows(audit_report, claim_rows),
        runtime_surface_ledger,
    )
    summary = {
        "cards_total": len(card_rows),
        "claims_total": len(claim_rows),
        "runtime_lowered_claims": sum(
            1
            for row in claim_rows
            if row.get("builder_or_router_decision") == "emitted"
        ),
        "claims_with_first_missing_link": sum(
            1 for row in claim_rows if row.get("first_missing_link") is not None
        ),
        "cards_with_first_missing_link": sum(
            1
            for row in card_rows
            if _normalized_missing_link(row.get("first_missing_link")) is not None
        ),
        "apply_blocking": False,
        "next_report_to_open": REPORT_PATH,
    }
    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "operator_gate_impact": "diagnostic_only",
        "apply_blocking": False,
        "summary": summary,
        "claim_rows": claim_rows,
        "card_rows": card_rows,
        "runtime_entity_transitions": [
            {
                key: row[key]
                for key in (
                    "source_card_id",
                    "source_role",
                    "runtime_card_id",
                    "runtime_owner_role",
                    "link_kind",
                    "runtime_file",
                )
            }
            for row in runtime_entity_transitions
        ],
        "runtime_entity_owner_collisions": owner_collisions,
        "surface_ledger_sha256": (
            str(runtime_surface_ledger.get("surface_ledger_sha256", ""))
            if isinstance(runtime_surface_ledger, Mapping)
            else ""
        ),
        "operator_attention": _operator_attention_rows(card_rows),
    }


def _apply_runtime_surface_ledger(
    rows: list[dict[str, Any]],
    ledger: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    cards = ledger.get("cards", {}) if isinstance(ledger, Mapping) else {}
    if not isinstance(cards, Mapping):
        return rows
    projected: list[dict[str, Any]] = []
    for row in rows:
        physical = cards.get(str(row.get("card_id", "")))
        if not isinstance(physical, Mapping):
            projected.append(row)
            continue
        projected.append(
            {
                **row,
                "runtime_surfaces": [
                    str(surface) for surface in physical.get("runtime_surfaces", [])
                ],
            }
        )
    return projected


def _claim_rows(
    audit: Mapping[str, Any],
    *,
    ownership_by_claim_id: Mapping[str, Mapping[str, str]] | None = None,
) -> list[dict[str, Any]]:
    lifecycle_rows = audit.get("claim_lifecycle_rows", [])
    if not isinstance(lifecycle_rows, list):
        return []

    rows: list[dict[str, Any]] = []
    ownership_by_claim_id = ownership_by_claim_id or {}
    for raw_row in lifecycle_rows:
        if not isinstance(raw_row, Mapping):
            continue
        emitted_files = _string_list(raw_row.get("emitted_files"))
        expected_files = _expected_runtime_files(raw_row)
        ownership = ownership_by_claim_id.get(
            str(raw_row.get("claim_id", ""))
        )
        if ownership is not None:
            source_file = f"{ownership['source_card_id']}.json"
            runtime_file = str(ownership["runtime_file"])
            emitted_files = [
                runtime_file if path == source_file else path
                for path in emitted_files
            ]
            expected_files = [runtime_file]
        not_emitted_files = [
            path for path in expected_files if path not in set(emitted_files)
        ]
        first_missing_link = _normalized_missing_link(
            raw_row.get("first_missing_link")
        )
        why_not_emitted = _normalized_empty(raw_row.get("suppressed_reason"))
        row = {
            "claim_id": str(raw_row.get("claim_id", "")),
            "claim_kind": str(raw_row.get("claim_kind", "")),
            "policy_lane": str(raw_row.get("policy_lane", "")),
            "surface_gate_decision": str(
                raw_row.get("surface_gate_decision", "")
            ),
            "surface_gate_reason": str(raw_row.get("surface_gate_reason", "")),
            "builder_or_router_decision": str(
                raw_row.get("builder_or_router_decision", "")
            ),
            "emitted_runtime_files": emitted_files,
            "not_emitted_runtime_files": not_emitted_files,
            "first_missing_link": first_missing_link,
            "why_not_emitted": why_not_emitted,
            "apply_blocked": False,
            "next_source_action": _next_source_action(
                first_missing_link=first_missing_link,
                why_not_emitted=why_not_emitted,
                claim_kind=str(raw_row.get("claim_kind", "")),
            ),
        }
        if ownership is not None:
            row.update(
                {
                    "source_card_id": ownership["source_card_id"],
                    "runtime_card_id": ownership["runtime_card_id"],
                    "link_kind": ownership["link_kind"],
                }
            )
        rows.append(row)
    return rows


def _card_rows(
    audit: Mapping[str, Any], claim_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    audit_claim_rows = audit.get("claim_rows", {})
    audit_card_rows = audit.get("card_rows", {})
    if not isinstance(audit_claim_rows, Mapping) or not isinstance(
        audit_card_rows, Mapping
    ):
        return []

    claim_by_id = {str(row.get("claim_id", "")): row for row in claim_rows}
    claim_ids_by_card: dict[str, list[str]] = defaultdict(list)
    for claim_id, raw_claim in audit_claim_rows.items():
        if not isinstance(raw_claim, Mapping):
            continue
        for card_id in _string_list(raw_claim.get("cards")):
            claim_ids_by_card[card_id].append(str(claim_id))

    rows: list[dict[str, Any]] = []
    for card_id, raw_card in sorted(audit_card_rows.items()):
        if not isinstance(raw_card, Mapping):
            continue
        strongest_claim_id = _strongest_claim_id(
            claim_ids_by_card.get(str(card_id), []),
            audit_claim_rows,
        )
        strongest_claim = (
            claim_by_id.get(strongest_claim_id) if strongest_claim_id else None
        )
        related_claims = [
            claim_by_id[claim_id]
            for claim_id in claim_ids_by_card.get(str(card_id), [])
            if claim_id in claim_by_id
        ]
        related_claims = _related_claims_with_source_metadata(
            related_claims,
            audit_claim_rows,
        )
        strongest_claim = (
            _matching_claim(related_claims, strongest_claim_id) or strongest_claim
        )
        best_source_lane = _best_source_lane(raw_card, strongest_claim_id, audit_claim_rows)
        missing_claim = _first_missing_related_claim(related_claims)
        emitted_files = _aggregate_claim_files(
            related_claims, key="emitted_runtime_files"
        )
        not_emitted_files = _aggregate_claim_files(
            related_claims, key="not_emitted_runtime_files"
        )
        expected_files = _aggregate_expected_card_files(str(card_id), related_claims)
        missing_runtime_files = [
            path
            for path in sorted(set(expected_files) | set(not_emitted_files))
            if path not in set(emitted_files)
        ]
        diagnostic_first_missing_link = _card_first_missing_link(
            raw_card,
            strongest_claim,
            missing_claim,
        )
        first_missing_link = _card_level_first_missing_link(
            emitted_surfaces=emitted_files,
            missing_runtime_surfaces=missing_runtime_files,
            card_missing_links=(
                [diagnostic_first_missing_link]
                if diagnostic_first_missing_link is not None
                else []
            ),
        )
        runtime_eligible = raw_card.get("runtime_eligible", True) is True
        if not runtime_eligible:
            first_missing_link = "none"
        why_not_emitted = _card_why_not_emitted(strongest_claim, missing_claim)
        runtime_backed = bool(emitted_files) or any(
            _bool_value(claim.get("runtime_backed")) for claim in related_claims
        )
        claim_kind = (
            str(missing_claim.get("claim_kind"))
            if missing_claim
            else str(strongest_claim.get("claim_kind"))
            if strongest_claim
            else ""
        )
        next_source_action = _next_source_action(
            first_missing_link=diagnostic_first_missing_link,
            why_not_emitted=why_not_emitted,
            claim_kind=claim_kind,
        )
        closure_lane = _closure_lane(related_claims, runtime_backed)
        card_row = {
            "card_id": str(card_id),
            "name": str(raw_card.get("name", "")),
            "best_source_lane": best_source_lane,
            "source_lane": _source_lane_for_card(
                related_claims,
                best_source_lane,
            ),
            "strongest_claim_id": strongest_claim_id,
            "strongest_claim_kind": (
                strongest_claim.get("claim_kind") if strongest_claim else None
            ),
            "first_missing_link": first_missing_link,
            "emitted_runtime_files": emitted_files,
            "not_emitted_runtime_files": missing_runtime_files,
            "why_not_emitted": why_not_emitted,
            "apply_blocked": False,
            "next_source_action": next_source_action,
            "first_missing_source_action": _first_missing_source_action(
                related_claims=related_claims,
                first_missing_link=diagnostic_first_missing_link,
                why_not_emitted=why_not_emitted,
                claim_kind=claim_kind,
                next_source_action=next_source_action,
            ),
            "runtime_lowering_status": _runtime_lowering_status(
                related_claims,
                runtime_backed,
            ),
            "closure_lane": closure_lane,
            "strong_ready": closure_lane == "source_backed_runtime_lowered",
            "default_only_blocker": (
                diagnostic_first_missing_link == "default_only_runtime_surface"
            ),
        }
        if "deck_zone" in raw_card:
            card_row.update(
                {
                    "deck_zone": str(raw_card.get("deck_zone", "main")),
                    "sideboard_owner_card_id": raw_card.get(
                        "sideboard_owner_card_id"
                    ),
                    "sideboard_owner_card_ids": list(
                        raw_card.get("sideboard_owner_card_ids", [])
                    ),
                    "sideboard_memberships": list(
                        raw_card.get("sideboard_memberships", [])
                    ),
                    "runtime_eligible": runtime_eligible,
                    "runtime_surfaces": list(raw_card.get("runtime_surfaces", [])),
                    "readiness_lane": str(raw_card.get("readiness_lane", "")),
                }
            )
        if not runtime_eligible:
            card_row.update(
                {
                    "next_source_action": "none",
                    "first_missing_source_action": "none",
                    "runtime_lowering_status": "report_only_supported",
                    "closure_lane": "report_only",
                    "strong_ready": False,
                    "default_only_blocker": False,
                }
            )
        closure_input = {
            **card_row,
            "first_missing_link": diagnostic_first_missing_link,
        }
        card_row["closure"] = _closure_row(
            row=closure_input,
            related_claims=_related_claims_with_source_lanes(
                related_claims,
                audit_claim_rows,
            ),
        )
        card_row["evidence_chain"] = _evidence_chain(str(card_id), related_claims)
        rows.append(card_row)
    return rows


def _operator_attention_rows(card_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in card_rows:
        first_missing_link = row.get("first_missing_link")
        emitted_runtime_files = row.get("emitted_runtime_files", [])
        status = _operator_attention_status(row)
        closure = row.get("closure", {})
        closure_lane = (
            str(closure.get("lane", status))
            if isinstance(closure, dict)
            else status
        )
        default_only_risk = (
            bool(closure.get("default_only_risk"))
            if isinstance(closure, dict)
            else False
        )
        rows.append(
            {
                "card_id": row["card_id"],
                "name": row.get("name"),
                "status": status,
                "closure_lane": closure_lane,
                "default_only_risk": default_only_risk,
                "first_missing_link": first_missing_link,
                "next_source_action": row.get("next_source_action"),
                "source_lane": row.get("source_lane"),
                "first_missing_source_action": row.get(
                    "first_missing_source_action"
                ),
                "runtime_lowering_status": row.get("runtime_lowering_status"),
                "strongest_claim_id": row.get("strongest_claim_id"),
                "strongest_claim_kind": row.get("strongest_claim_kind"),
                "emitted_runtime_files": emitted_runtime_files,
                "not_emitted_runtime_files": row.get(
                    "not_emitted_runtime_files", []
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["first_missing_link"] is None,
            str(row["card_id"]),
        ),
    )


def _operator_attention_status(row: dict[str, object]) -> str:
    first_missing_link = row.get("first_missing_link")
    emitted_runtime_files = row.get("emitted_runtime_files", [])
    best_source_lane = str(row.get("best_source_lane", ""))
    why_not_emitted = row.get("why_not_emitted")

    if row.get("runtime_eligible") is False:
        return "report_only"
    if first_missing_link is not None:
        return "source_action_needed"
    if emitted_runtime_files:
        return "runtime_backed"
    if not row.get("strongest_claim_id") and why_not_emitted is None:
        return "baseline_only_visible"
    if best_source_lane == "report_only" or why_not_emitted in {
        "claim_kind_policy",
        "report_only",
    }:
        return "diagnostic_only"
    return "baseline_only_visible"


def _closure_row(
    *,
    row: Mapping[str, Any],
    related_claims: list[dict[str, Any]],
) -> dict[str, Any]:
    first_missing_link = row.get("first_missing_link")
    emitted_runtime_files = _string_list(row.get("emitted_runtime_files"))
    not_emitted_runtime_files = _string_list(row.get("not_emitted_runtime_files"))
    expected_runtime_files = sorted(
        set(emitted_runtime_files) | set(not_emitted_runtime_files)
    )
    lane = _operator_attention_status(dict(row))
    default_only_risk = (
        not emitted_runtime_files
        and not not_emitted_runtime_files
        and lane == "baseline_only_visible"
    )
    return {
        "lane": lane,
        "claim_kinds": sorted(
            {
                str(claim.get("claim_kind"))
                for claim in related_claims
                if claim.get("claim_kind")
            }
        ),
        "source_lanes": sorted(
            {
                str(claim.get("source_lane") or claim.get("policy_lane"))
                for claim in related_claims
                if claim.get("source_lane") or claim.get("policy_lane")
            }
        ),
        "runtime_surfaces": emitted_runtime_files,
        "expected_runtime_surfaces": expected_runtime_files,
        "missing_runtime_surfaces": not_emitted_runtime_files,
        "default_only_risk": default_only_risk,
        "suppressed_reasons": sorted(
            {
                str(claim.get("why_not_emitted"))
                for claim in related_claims
                if claim.get("why_not_emitted")
            }
        ),
        "first_missing_link": first_missing_link,
        "next_source_action": row.get("next_source_action"),
    }


def _evidence_chain(
    card_id: str,
    related_claims: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for claim in related_claims:
        emitted_files = _string_list(claim.get("emitted_runtime_files"))
        not_emitted_files = _string_list(claim.get("not_emitted_runtime_files"))
        runtime_files = sorted(
            set(emitted_files)
            | set(not_emitted_files)
            | set(_card_expected_runtime_files(card_id, claim))
        )
        first_missing_link = _normalized_missing_link(claim.get("first_missing_link"))
        why_not_emitted = _normalized_empty(claim.get("why_not_emitted"))
        claim_kind = str(claim.get("claim_kind", ""))
        row = {
            "claim_id": str(claim.get("claim_id", "")),
            "claim_kind": claim_kind,
            "source_lane": str(
                claim.get("source_lane") or claim.get("policy_lane") or ""
            ),
            "source_type": str(claim.get("source_type") or ""),
            "runtime_surface": _first_runtime_surface(runtime_files),
            "runtime_files": runtime_files,
            "resolution_reason": _evidence_chain_resolution(claim),
            "first_missing_link": first_missing_link,
            "first_missing_source_action": _first_missing_source_action(
                related_claims=[claim],
                first_missing_link=first_missing_link,
                why_not_emitted=why_not_emitted,
                claim_kind=claim_kind,
                next_source_action=_next_source_action(
                    first_missing_link=first_missing_link,
                    why_not_emitted=why_not_emitted,
                    claim_kind=claim_kind,
                ),
            ),
        }
        if claim.get("source_card_id") and claim.get("runtime_card_id"):
            row.update(
                {
                    "source_card_id": str(claim["source_card_id"]),
                    "runtime_card_id": str(claim["runtime_card_id"]),
                    "link_kind": str(claim.get("link_kind", "")),
                }
            )
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (
            LANE_RANK.get(str(row.get("source_lane", "report_only")), 99),
            str(row.get("claim_id", "")),
        ),
    )


def _first_runtime_surface(runtime_files: Sequence[str]) -> str:
    surfaces = _runtime_surfaces_from_files(runtime_files)
    return surfaces[0] if surfaces else ""


def _evidence_chain_resolution(claim: Mapping[str, Any]) -> str:
    if str(claim.get("builder_or_router_decision", "")) == "emitted":
        return "emitted"
    why_not_emitted = _normalized_empty(claim.get("why_not_emitted"))
    if why_not_emitted is not None:
        return why_not_emitted
    first_missing_link = _normalized_missing_link(claim.get("first_missing_link"))
    if first_missing_link is not None:
        return first_missing_link
    surface_gate_reason = _normalized_empty(claim.get("surface_gate_reason"))
    if surface_gate_reason is not None:
        return surface_gate_reason
    return str(claim.get("policy_lane") or "report_only")


def _normalized_audit(
    audit: Mapping[str, Any] | None,
    *,
    runtime_files: Sequence[str] | set[str] | None,
) -> Mapping[str, Any]:
    if not isinstance(audit, Mapping):
        return {}
    if isinstance(audit.get("claim_rows"), list):
        return _audit_from_compact_claim_rows(audit, runtime_files=runtime_files)
    return audit


def _audit_from_compact_claim_rows(
    audit: Mapping[str, Any],
    *,
    runtime_files: Sequence[str] | set[str] | None,
) -> dict[str, Any]:
    runtime_file_set = {str(path) for path in runtime_files or []}
    raw_rows = audit.get("claim_rows", [])
    if not isinstance(raw_rows, list):
        raw_rows = []

    claim_rows: dict[str, dict[str, Any]] = {}
    claim_lifecycle_rows: list[dict[str, Any]] = []
    card_rows: dict[str, dict[str, Any]] = {}
    for index, raw_row in enumerate(raw_rows, start=1):
        if not isinstance(raw_row, Mapping):
            continue
        card_id = str(raw_row.get("card_id") or raw_row.get("card") or "").strip()
        if not card_id:
            continue
        claim_id = str(raw_row.get("claim_id") or f"claim_{index}")
        claim_kind = str(raw_row.get("claim_kind") or "")
        expected_files = _card_expected_runtime_files(
            card_id,
            {"claim_kind": claim_kind},
        )
        runtime_backed = _bool_value(raw_row.get("runtime_backed")) or any(
            path in runtime_file_set for path in expected_files
        )
        emitted_files = expected_files if runtime_backed else []
        source_lane = _compact_source_lane(raw_row)
        lane = source_lane or ("runtime_lowered" if runtime_backed else "report_only")
        policy_lane = str(raw_row.get("policy_lane") or source_lane or lane)
        first_missing_link = _normalized_missing_link(raw_row.get("first_missing_link"))
        suppressed_reason = _normalized_empty(
            raw_row.get("suppressed_reason") or raw_row.get("why_not_emitted")
        )

        claim_rows[claim_id] = {
            "claim_id": claim_id,
            "claim_kind": claim_kind,
            "cards": [card_id],
            "lane": lane,
            "policy_lane": policy_lane,
            "source_type": str(raw_row.get("source_type") or ""),
            "source_lane": source_lane,
            "runtime_backed": runtime_backed,
            "lowered_surfaces": _runtime_surfaces_from_files(emitted_files),
        }
        claim_lifecycle_rows.append(
            {
                "claim_id": claim_id,
                "claim_kind": claim_kind,
                "policy_lane": policy_lane,
                "surface_gate_decision": "allowed" if runtime_backed else "rejected",
                "surface_gate_reason": str(
                    raw_row.get("surface_gate_reason")
                    or ("allowed" if runtime_backed else "needs_runtime_surface")
                ),
                "builder_or_router_decision": (
                    "emitted" if runtime_backed else "suppressed"
                ),
                "runtime_surface": emitted_files[0]
                if emitted_files
                else expected_files[0]
                if expected_files
                else None,
                "emitted_files": emitted_files,
                "suppressed_reason": None if runtime_backed else suppressed_reason,
                "first_missing_link": first_missing_link,
                "operator_impact": "diagnostic_only",
            }
        )

        card_row = card_rows.setdefault(
            card_id,
            {
                "card_id": card_id,
                "name": str(raw_row.get("name") or card_id),
                "readiness_lane": str(raw_row.get("readiness_lane") or ""),
                "first_missing_link": str(raw_row.get("first_missing_link") or "none"),
                "runtime_surfaces": [],
                "claim_lanes": {},
            },
        )
        card_row["runtime_surfaces"] = sorted(
            set(_string_list(card_row.get("runtime_surfaces"))) | set(emitted_files)
        )
        claim_lanes = card_row.get("claim_lanes", {})
        if not isinstance(claim_lanes, dict):
            claim_lanes = {}
        claim_lanes[lane] = int(claim_lanes.get(lane, 0)) + 1
        card_row["claim_lanes"] = claim_lanes

    return {
        "schema_version": audit.get("schema_version", 1),
        "deck_name": str(audit.get("deck_name", "")),
        "summary": audit.get("summary", {}),
        "claim_rows": claim_rows,
        "claim_lifecycle_rows": claim_lifecycle_rows,
        "card_rows": card_rows,
    }


def _runtime_surfaces_from_files(files: Sequence[str]) -> list[str]:
    surfaces: list[str] = []
    for path in files:
        if path == "Mulligan.json":
            surfaces.append("mulligan")
        elif path == "Combo.json":
            surfaces.append("combo")
        elif path == "GlobalValues.json":
            surfaces.append("globalvalues")
        elif path.endswith(".json"):
            surfaces.append("cardid")
    return sorted(set(surfaces))


def _compact_source_lane(row: Mapping[str, Any]) -> str:
    source_lane = str(row.get("source_lane") or "").strip()
    if source_lane:
        return source_lane
    if str(row.get("source_type")) == "policy_backed_autonomous_mulligan":
        return "policy_fallback"
    return ""


def _related_claims_with_source_lanes(
    related_claims: list[dict[str, Any]],
    audit_claim_rows: Mapping[str, Any],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for claim in related_claims:
        row = dict(claim)
        raw_claim = audit_claim_rows.get(str(row.get("claim_id", "")))
        if isinstance(raw_claim, Mapping):
            row["source_lane"] = str(
                raw_claim.get("source_lane") or raw_claim.get("lane", "")
            )
        enriched.append(row)
    return enriched


def _related_claims_with_source_metadata(
    related_claims: list[dict[str, Any]],
    audit_claim_rows: Mapping[str, Any],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for claim in related_claims:
        row = dict(claim)
        raw_claim = audit_claim_rows.get(str(row.get("claim_id", "")))
        if isinstance(raw_claim, Mapping):
            source_type = _normalized_empty(raw_claim.get("source_type"))
            if source_type is not None:
                row["source_type"] = source_type
            source_lane = _normalized_empty(
                raw_claim.get("source_lane") or raw_claim.get("lane")
            )
            if source_lane is not None:
                row["source_lane"] = source_lane
            if "runtime_backed" in raw_claim:
                row["runtime_backed"] = _bool_value(raw_claim.get("runtime_backed"))
        enriched.append(row)
    return enriched


def _matching_claim(
    related_claims: Sequence[Mapping[str, Any]],
    claim_id: str | None,
) -> Mapping[str, Any] | None:
    if claim_id is None:
        return None
    for claim in related_claims:
        if str(claim.get("claim_id", "")) == str(claim_id):
            return claim
    return None


def _strongest_claim_id(
    claim_ids: list[str], audit_claim_rows: Mapping[str, Any]
) -> str | None:
    ranked: list[tuple[int, int, str]] = []
    for claim_id in claim_ids:
        raw_claim = audit_claim_rows.get(claim_id)
        if not isinstance(raw_claim, Mapping):
            continue
        lane = str(raw_claim.get("lane", "report_only"))
        claim_kind = str(raw_claim.get("claim_kind", ""))
        ranked.append(
            (
                LANE_RANK.get(lane, 99),
                CLAIM_KIND_RANK.get(claim_kind, 50),
                claim_id,
            )
        )
    if not ranked:
        return None
    return sorted(ranked)[0][2]


def _best_source_lane(
    raw_card: Mapping[str, Any],
    strongest_claim_id: str | None,
    audit_claim_rows: Mapping[str, Any],
) -> str:
    claim_lanes = raw_card.get("claim_lanes", {})
    if isinstance(claim_lanes, Mapping) and claim_lanes:
        return sorted(
            (str(lane) for lane in claim_lanes),
            key=lambda lane: (LANE_RANK.get(lane, 99), lane),
        )[0]
    if strongest_claim_id:
        raw_claim = audit_claim_rows.get(strongest_claim_id)
        if isinstance(raw_claim, Mapping):
            return str(raw_claim.get("lane", "report_only"))
    return "report_only"


def _source_lane_for_card(
    related_claims: Sequence[Mapping[str, Any]],
    best_source_lane: str,
) -> str:
    source_lanes = [
        str(claim.get("source_lane"))
        for claim in related_claims
        if _normalized_empty(claim.get("source_lane")) is not None
    ]
    if source_lanes:
        return sorted(
            source_lanes,
            key=lambda lane: (LANE_RANK.get(lane, 99), lane),
        )[0]
    return best_source_lane


def _card_first_missing_link(
    raw_card: Mapping[str, Any],
    strongest_claim: Mapping[str, Any] | None,
    missing_claim: Mapping[str, Any] | None,
) -> str | None:
    card_missing = _normalized_missing_link(raw_card.get("first_missing_link"))
    if card_missing is not None:
        return card_missing
    if strongest_claim:
        strongest_missing = _normalized_missing_link(
            strongest_claim.get("first_missing_link")
        )
        if strongest_missing is not None:
            return strongest_missing
    if missing_claim:
        return _normalized_missing_link(missing_claim.get("first_missing_link"))
    return None


def _card_level_first_missing_link(
    *,
    emitted_surfaces: list[str],
    missing_runtime_surfaces: list[str],
    card_missing_links: list[str],
) -> str | None:
    if emitted_surfaces and not missing_runtime_surfaces:
        return None
    return card_missing_links[0] if card_missing_links else None


def _first_missing_related_claim(
    related_claims: list[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    missing_claims = [
        claim
        for claim in related_claims
        if _normalized_missing_link(claim.get("first_missing_link")) is not None
        or _normalized_empty(claim.get("why_not_emitted")) is not None
    ]
    if not missing_claims:
        return None
    return sorted(
        missing_claims,
        key=lambda claim: (
            LANE_RANK.get(str(claim.get("policy_lane", "report_only")), 99),
            str(claim.get("claim_id", "")),
        ),
    )[0]


def _card_why_not_emitted(
    strongest_claim: Mapping[str, Any] | None,
    missing_claim: Mapping[str, Any] | None,
) -> str | None:
    if strongest_claim:
        why = _normalized_empty(strongest_claim.get("why_not_emitted"))
        if why is not None:
            return why
    if missing_claim:
        return _normalized_empty(missing_claim.get("why_not_emitted"))
    return None


def _expected_runtime_files(row: Mapping[str, Any]) -> list[str]:
    runtime_surface = _normalized_empty(row.get("runtime_surface"))
    return [runtime_surface] if runtime_surface else []


def _card_expected_runtime_files(
    card_id: str, strongest_claim: Mapping[str, Any] | None
) -> list[str]:
    if strongest_claim is None:
        return []
    runtime_card_id = _normalized_empty(
        strongest_claim.get("runtime_card_id")
    )
    source_card_id = _normalized_empty(
        strongest_claim.get("source_card_id")
    )
    if (
        runtime_card_id is not None
        and source_card_id is not None
        and runtime_card_id != source_card_id
    ):
        return [f"{runtime_card_id}.json"]
    claim_kind = str(strongest_claim.get("claim_kind", ""))
    if claim_kind in {
        "targeting_rule",
        "hero_power_transform",
        "mechanic_usage",
        "known_bad_pattern",
        "discover_choice",
        "choose_one_choice",
        "card_role",
    }:
        return [f"{card_id}.json"]
    if claim_kind in {"mulligan_keep", "mulligan_discard"}:
        return ["Mulligan.json"]
    if claim_kind == "combo_sequence" and _combo_claim_is_runtime_lowerable(
        strongest_claim
    ):
        return ["Combo.json"]
    if claim_kind in {"gameplan_posture", "globalvalue_numeric_tuning"}:
        return ["GlobalValues.json"]
    return []


def _runtime_entity_transitions(
    card_behavior_plan: Mapping[str, Any],
) -> list[dict[str, str]]:
    transitions: dict[
        tuple[str, str, str, str],
        dict[str, str],
    ] = {}
    raw_rows = card_behavior_plan.get("rows", [])
    if not isinstance(raw_rows, list):
        return []
    for row in raw_rows:
        if not isinstance(row, Mapping):
            continue
        source_card_id = str(
            row.get("source_card_id") or row.get("card_id") or ""
        ).strip()
        runtime_card_id = str(
            row.get("runtime_card_id") or row.get("card_id") or ""
        ).strip()
        link_kind = str(row.get("link_kind") or "self").strip()
        claim_id = str(row.get("claim_id") or "").strip()
        if (
            row.get("meaningful_runtime_surface") is not True
            or not source_card_id
            or not runtime_card_id
            or source_card_id == runtime_card_id
            or link_kind == "self"
        ):
            continue
        key = (claim_id, source_card_id, runtime_card_id, link_kind)
        transitions[key] = {
            "claim_id": claim_id,
            "source_card_id": source_card_id,
            "source_role": f"{link_kind}_source",
            "runtime_card_id": runtime_card_id,
            "runtime_owner_role": (
                "hero_power"
                if link_kind == "hero_power_transform"
                else "linked_runtime_entity"
            ),
            "link_kind": link_kind,
            "runtime_file": f"{runtime_card_id}.json",
        }
    return [transitions[key] for key in sorted(transitions)]


def _combo_claim_is_runtime_lowerable(combo: Mapping[str, Any]) -> bool:
    if combo.get("suppressed_reason") or combo.get("why_not_emitted"):
        return False
    if combo.get("runtime_lowering_status") in {"emitted", "runtime_lowered"}:
        return True
    if combo.get("runtime_surface") == "Combo.json":
        return True
    timing = str(combo.get("timing") or combo.get("sequence_timing") or "").strip()
    cards = combo.get("cards") or combo.get("card_ids") or []
    return timing in {"same_turn", "ordered", "exact_order"} and len(cards) >= 2


def _aggregate_expected_card_files(
    card_id: str, related_claims: list[Mapping[str, Any]]
) -> list[str]:
    files: set[str] = set()
    for claim in related_claims:
        files.update(_card_expected_runtime_files(card_id, claim))
    return sorted(files)


def _aggregate_claim_files(
    related_claims: list[Mapping[str, Any]], *, key: str
) -> list[str]:
    files: set[str] = set()
    for claim in related_claims:
        files.update(_string_list(claim.get(key)))
    return sorted(files)


def _next_source_action(
    *, first_missing_link: str | None, why_not_emitted: Any, claim_kind: str
) -> str:
    reason = _normalized_empty(why_not_emitted)
    if first_missing_link is None and reason is None:
        return "none"
    authority_action = MULLIGAN_AUTHORITY_ACTION_BY_REASON.get(reason or "")
    if authority_action is not None:
        return authority_action
    if first_missing_link in NEXT_ACTION_BY_MISSING_LINK:
        return NEXT_ACTION_BY_MISSING_LINK[first_missing_link]
    if first_missing_link == "opening_hand_mulligan_intent":
        return "add_explicit_opening_hand_mulligan_source"
    if first_missing_link == "runtime_evidence" or reason == "runtime_evidence_required":
        return "collect_runtime_evidence"
    if first_missing_link == "claim_kind_policy" or reason in {
        "unsupported_or_unmapped",
        "report_only",
    }:
        return "map_claim_kind_or_keep_report_only"
    if first_missing_link in {"builder_or_router", "needs_runtime_surface"} or reason in {
        "requires_supported_cardid_surface",
        "requires_complete_combo_sequence",
        "requires_exact_option_identity",
        "claim_kind_not_globalvalues_surface",
    }:
        return "add_supported_runtime_surface_or_keep_report_only"
    if first_missing_link == "mulligan_source" or claim_kind.startswith("mulligan_"):
        return "add_explicit_mulligan_claim"
    return "improve_source_claim_or_keep_report_only"


def _first_missing_source_action(
    *,
    related_claims: Sequence[Mapping[str, Any]],
    first_missing_link: str | None,
    why_not_emitted: Any,
    claim_kind: str,
    next_source_action: str,
) -> str:
    if _has_policy_backed_mulligan(related_claims):
        return "add_explicit_mulligan_source"
    return _next_source_action(
        first_missing_link=first_missing_link,
        why_not_emitted=why_not_emitted,
        claim_kind=claim_kind,
    ) or next_source_action


def _runtime_lowering_status(
    related_claims: Sequence[Mapping[str, Any]], runtime_backed: bool
) -> str:
    if _has_policy_backed_mulligan(related_claims):
        return (
            "policy_backed_runtime"
            if runtime_backed
            else "policy_backed_contract_only"
        )
    if runtime_backed:
        return "source_backed_runtime"
    if related_claims:
        return "source_backed_contract_only"
    return "missing_source_claim"


def _closure_lane(
    related_claims: Sequence[Mapping[str, Any]], runtime_backed: bool
) -> str:
    if runtime_backed and any(
        _is_source_backed_strong_claim(claim) for claim in related_claims
    ):
        return "source_backed_runtime_lowered"
    if _has_policy_backed_mulligan(related_claims) or any(
        str(claim.get("policy_lane")) == "policy_fallback"
        or str(claim.get("source_lane")) == "policy_fallback"
        for claim in related_claims
    ):
        return "policy_backed"
    if runtime_backed:
        return "runtime_backed_non_strong"
    return "explicit_gap"


def _is_source_backed_strong_claim(claim: Mapping[str, Any]) -> bool:
    if claim.get("promotion_eligible") is True:
        return True
    if str(claim.get("source_type")) == "policy_backed_autonomous_mulligan":
        return False
    lane = str(claim.get("source_lane") or claim.get("policy_lane") or "")
    return lane in {"runtime_lowered", "runtime_lowerable", "deck_matched_public_guide"}


def _has_policy_backed_mulligan(related_claims: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        str(row.get("claim_kind")) == "mulligan_keep"
        and str(row.get("source_type")) == "policy_backed_autonomous_mulligan"
        for row in related_claims
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _normalized_missing_link(value: Any) -> str | None:
    text = _normalized_empty(value)
    if text in {None, "none", "closed"}:
        return None
    return text


def _normalized_empty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
