"""Pure helper closure owned by the canonical package compiler."""

from __future__ import annotations

from collections.abc import Mapping
import json
from types import CodeType, FunctionType
from typing import Any

from hsconfig.card_metadata import analysis_cards_from_deck_identity
from hsconfig.disposition_ledger import build_disposition_ledger, build_dual_closure
from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix
from hsconfig.linked_entity_supplement import curated_links_for
from hsconfig.package_domain import GlobalValuesDecisionLedger
from hsconfig.pre_run_metrics import (
    VerifiedEmissionInput,
    pre_emission_expectations_from_audit,
    verified_emission_input_from_physical_rows,
)
from hsconfig.source_claim_conflicts import build_claim_conflict_report
from hsconfig.source_claim_lifecycle import select_claims_for_surface
from hsconfig.source_document_model import (
    has_verified_source_receipt,
    normalized_claim_kind,
)

_STRATEGIC_STRONG_CLOSURE_CLAIM_KINDS = frozenset(
    {
        "combo_sequence",
        "mulligan_keep",
        "mulligan_discard",
        "targeting_rule",
        "gameplan_posture",
        "globalvalue_numeric_tuning",
    }
)


def seal_function_definition_closure(
    function: FunctionType,
    memo: dict[int, FunctionType] | None = None,
) -> FunctionType:
    """Bind reachable HSConfig functions to their definition-time globals."""

    if memo is None:
        memo = {}
    existing = memo.get(id(function))
    if existing is not None:
        return existing
    stable_globals = dict(function.__globals__)
    sealed = FunctionType(
        function.__code__,
        stable_globals,
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )
    memo[id(function)] = sealed
    sealed.__kwdefaults__ = function.__kwdefaults__
    sealed.__annotations__ = dict(function.__annotations__)
    sealed.__dict__.update(function.__dict__)
    sealed.__module__ = function.__module__
    sealed.__qualname__ = function.__qualname__
    for name in _code_global_names(function.__code__):
        dependency = stable_globals.get(name)
        if (
            isinstance(dependency, FunctionType)
            and dependency.__module__.startswith("hsconfig.")
        ):
            stable_globals[name] = seal_function_definition_closure(
                dependency,
                memo,
            )
    return sealed


def _code_global_names(code: CodeType) -> frozenset[str]:
    names = set(code.co_names)
    for value in code.co_consts:
        if isinstance(value, CodeType):
            names.update(_code_global_names(value))
    return frozenset(names)


def _with_strategic_receipt_verification(
    claims: Any,
    *,
    deck_identity: dict[str, Any],
    verified_source_receipts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    target_fingerprint = str(deck_identity.get("deck_fingerprint", "")).strip().lower()
    result: list[dict[str, Any]] = []
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            continue
        normalized = dict(claim)
        if normalized_claim_kind(normalized) in _STRATEGIC_STRONG_CLOSURE_CLAIM_KINDS:
            normalized["strategic_receipt_verified"] = has_verified_source_receipt(
                normalized,
                target_fingerprint=target_fingerprint,
                verified_source_receipts=verified_source_receipts,
            )
        result.append(normalized)
    return result


def _build_package_disposition_ledger(
    *,
    deck_identity: dict[str, Any],
    source_contract_audit_report: dict[str, Any],
    runtime_surface_ledger: dict[str, Any],
    globalvalues_ledger: GlobalValuesDecisionLedger,
    strategy_source_status: str,
):
    deck_fingerprint = str(deck_identity.get("deck_fingerprint", ""))
    claim_rows = source_contract_audit_report.get("claim_rows", {})
    lifecycle_rows = source_contract_audit_report.get(
        "claim_lifecycle_rows", []
    )
    claims_by_card: dict[str, set[str]] = {}
    if isinstance(claim_rows, dict):
        for claim_id, claim in claim_rows.items():
            if not isinstance(claim, dict):
                continue
            for card_id in claim.get("cards", []):
                claims_by_card.setdefault(str(card_id), set()).add(
                    str(claim_id)
                )

    ledger_cards = runtime_surface_ledger.get("cards", {})
    linked_entities = runtime_surface_ledger.get(
        "linked_runtime_entities", {}
    )
    evidence_cards: list[dict[str, Any]] = []
    physical_emission_index: dict[str, list[str]] = {}
    physical_emissions: list[dict[str, Any]] = []
    composite_by_card: dict[str, str] = {}
    lifecycle_by_id = {
        str(row.get("claim_id", "")): row
        for row in lifecycle_rows
        if isinstance(row, dict) and row.get("claim_id")
    }
    for card in analysis_cards_from_deck_identity(deck_identity):
        card_id = str(card.get("card_id", ""))
        if not card_id:
            continue
        zone = (
            "sideboard_module"
            if str(card.get("deck_zone", "main")) == "sideboard"
            else "main_deck"
        )
        composite_key = f"{deck_fingerprint}:{zone}:{card_id}"
        composite_by_card[card_id] = composite_key
        emission_observations: list[tuple[str, str]] = []
        raw_ledger_card = (
            ledger_cards.get(card_id, {})
            if isinstance(ledger_cards, dict)
            else {}
        )
        if isinstance(raw_ledger_card, dict):
            emission_observations.extend(
                (card_id, str(path))
                for path in raw_ledger_card.get("runtime_surfaces", [])
                if str(path) == f"{card_id}.json"
            )
        if isinstance(linked_entities, dict):
            for runtime_card_id, raw_link in linked_entities.items():
                if (
                    isinstance(raw_link, dict)
                    and str(raw_link.get("source_card_id", "")) == card_id
                    and raw_link.get("runtime_emitted") is True
                ):
                    linked_owner = str(runtime_card_id)
                    emission_observations.append(
                        (
                            linked_owner,
                            str(
                            raw_link.get("runtime_surface")
                            or f"{runtime_card_id}.json"
                            ),
                        )
                    )
        emission_observations = sorted(
            set(emission_observations),
            key=lambda row: (row[1], row[0]),
        )
        runtime_paths = sorted(
            {path for _owner, path in emission_observations}
        )
        physical_owner = (
            card_id
            if any(
                owner == card_id
                for owner, _path in emission_observations
            )
            else (
                emission_observations[0][0]
                if emission_observations
                else card_id
            )
        )
        if runtime_paths:
            physical_emission_index[composite_key] = runtime_paths
            physical_emissions.extend(
                {
                    "composite_card_key": composite_key,
                    "physical_owner": owner,
                    "relative_path": path,
                    "meaningful": True,
                    "schema_supported": True,
                }
                for owner, path in emission_observations
            )
        claim_ids = sorted(claims_by_card.get(card_id, set()))
        authority_lane = _card_evidence_authority_lane(
            claim_ids=claim_ids,
            claim_rows=claim_rows,
            lifecycle_by_id=lifecycle_by_id,
        )
        evidence_ids = _card_evidence_authority_ids(
            claim_ids=claim_ids,
            claim_rows=claim_rows,
        )
        evidence_cards.append(
            {
                "composite_card_key": composite_key,
                "zone": zone,
                "official_semantics_canonical_json": {
                    "GameCardId": physical_owner,
                },
                "authority_lane": authority_lane,
                "evidence_ids": evidence_ids
                or claim_ids
                or [f"official:{card_id}"],
                "claim_ids": claim_ids,
                "physical_owner": physical_owner,
            }
        )

    normalized_lifecycle_rows: list[dict[str, Any]] = []
    for claim_id, raw_claim in sorted(
        claim_rows.items() if isinstance(claim_rows, dict) else ()
    ):
        claim = raw_claim if isinstance(raw_claim, dict) else {}
        lifecycle = lifecycle_by_id.get(str(claim_id), {})
        emitted_files = sorted(
            {
                str(path)
                for path in lifecycle.get("emitted_files", [])
                if str(path)
            }
        )
        related_cards = sorted(
            str(card_id)
            for card_id in claim.get("cards", [])
            if str(card_id) in composite_by_card
        )
        owner_card_id = next(
            (
                card_id
                for card_id in related_cards
                if f"{card_id}.json" in emitted_files
            ),
            related_cards[0] if related_cards else None,
        )
        normalized_lifecycle_rows.append(
            {
                "deck_fingerprint": deck_fingerprint,
                "claim_id": str(claim_id),
                "claim_kind": str(claim.get("claim_kind", "")),
                "evidence_id": _claim_evidence_authority_id(
                    claim,
                    fallback=str(claim_id),
                ),
                "composite_card_key": (
                    composite_by_card.get(owner_card_id, "__contract__")
                ),
                "builder_state": _final_disposition_builder_state(
                    lifecycle
                ),
                "runtime_paths": emitted_files,
                "policy_id": (
                    lifecycle.get("policy_id")
                    or claim.get("policy_id")
                    or _claim_evidence_policy_id(claim)
                ),
            }
        )

    dispositions = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": deck_fingerprint,
            "cards": evidence_cards,
            "claim_ids": sorted(
                str(claim_id)
                for claim_id in (
                    claim_rows if isinstance(claim_rows, dict) else {}
                )
            ),
        },
        claim_lifecycle_rows=normalized_lifecycle_rows,
        physical_emission_index=physical_emission_index,
        runtime_surface_ledger={
            "physical_emissions": physical_emissions,
        },
    )
    dual_closure = build_dual_closure(
        dispositions=dispositions,
        globalvalues_ledger=globalvalues_ledger,
        strategy_source_status=strategy_source_status,
    )
    rejected_physical_rows = [
        *runtime_surface_ledger.get("physical_errors", ()),
        *runtime_surface_ledger.get("unexpected_runtime_emissions", ()),
        *runtime_surface_ledger.get(
            "linked_runtime_owner_collisions",
            (),
        ),
    ]
    verified_emissions: VerifiedEmissionInput = (
        verified_emission_input_from_physical_rows(
            disposition_ledger=dispositions,
            physical_rows=physical_emissions,
            rejected_rows=rejected_physical_rows,
            semantic_expectations=(
                pre_emission_expectations_from_audit(
                    disposition_ledger=dispositions,
                    source_contract_audit=source_contract_audit_report,
                )
            ),
        )
    )
    return dispositions, dual_closure, verified_emissions


def _card_evidence_authority_lane(
    *,
    claim_ids: list[str],
    claim_rows: Mapping[str, Any],
    lifecycle_by_id: Mapping[str, Any],
) -> str:
    if claim_ids and all(
        _is_exact_bot_delegation(
            lifecycle_by_id.get(claim_id),
            claim_rows.get(claim_id),
        )
        for claim_id in claim_ids
    ):
        return "E"
    lanes = {
        str(authority.get("lane", ""))
        for claim_id in claim_ids
        for authority in (
            _claim_evidence_authority(claim_rows.get(claim_id)),
        )
        if authority is not None
    }
    for lane in ("B", "D", "C", "A"):
        if lane in lanes:
            return lane
    return "A"


def _card_evidence_authority_ids(
    *,
    claim_ids: list[str],
    claim_rows: Mapping[str, Any],
) -> list[str]:
    return sorted(
        {
            str(authority["authority_id"])
            for claim_id in claim_ids
            for authority in (
                _claim_evidence_authority(claim_rows.get(claim_id)),
            )
            if authority is not None
            and isinstance(authority.get("authority_id"), str)
            and authority["authority_id"]
        }
    )


def _claim_evidence_authority(
    claim: Any,
) -> Mapping[str, Any] | None:
    if not isinstance(claim, Mapping):
        return None
    authority = claim.get("evidence_authority")
    return authority if isinstance(authority, Mapping) else None


def _claim_evidence_authority_id(
    claim: Any,
    *,
    fallback: str,
) -> str:
    authority = _claim_evidence_authority(claim)
    if authority is None:
        return fallback
    authority_id = authority.get("authority_id")
    return (
        authority_id
        if isinstance(authority_id, str) and authority_id
        else fallback
    )


def _claim_evidence_policy_id(claim: Any) -> str | None:
    authority = _claim_evidence_authority(claim)
    if authority is None:
        return None
    policy_id = authority.get("policy_id")
    return (
        policy_id
        if isinstance(policy_id, str) and policy_id
        else None
    )


def _is_exact_bot_delegation(lifecycle: Any, claim: Any) -> bool:
    if not isinstance(lifecycle, Mapping):
        return False
    policy_id = (
        lifecycle.get("policy_id")
        or (
            claim.get("policy_id")
            if isinstance(claim, Mapping)
            else None
        )
        or _claim_evidence_policy_id(claim)
    )
    return (
        str(lifecycle.get("builder_or_router_decision", ""))
        == "bot_delegated"
        and policy_id == "BOT_NATIVE_PRE_RUN"
    )


def _final_disposition_builder_state(
    lifecycle: dict[str, Any],
) -> str:
    emitted_files = lifecycle.get("emitted_files", [])
    if isinstance(emitted_files, list) and any(
        isinstance(path, str) and path for path in emitted_files
    ):
        return "runtime_emitted"
    reason = str(lifecycle.get("suppressed_reason") or "")
    policy_lane = str(lifecycle.get("policy_lane") or "")
    if (
        policy_lane in {
            "report_only",
            "suppressed_or_conditional",
            "unsupported_or_unmapped",
        }
        or reason in {
            "claim_kind_policy",
            "claim_kind_not_globalvalues_surface",
            "requires_supported_cardid_surface",
            "source_eligibility",
            "unsupported_or_unmapped",
        }
    ):
        return "suppressed_unsupported_surface"
    if str(lifecycle.get("builder_or_router_decision") or "") == "suppressed":
        return "suppressed_insufficient_authority"
    return str(
        lifecycle.get("builder_or_router_decision")
        or "unclassified_builder_state"
    )


def _runtime_evidence_globalvalue_claims(
    lifecycle_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for row in lifecycle_rows:
        if row.get("quarantine_status") == "quarantined":
            continue
        if row.get("claim_kind") != "globalvalue_numeric_tuning":
            continue
        claim = dict(row.get("claim") or {})
        claim["claim_kind"] = "globalvalue_numeric_tuning"
        claim["_claim_lifecycle"] = {
            "claim_id": row.get("claim_id"),
            "surface": "globalvalues",
            "policy_lane": row.get("policy_lane"),
            "surface_gate_reason": "requires_runtime_evidence",
        }
        claims.append(claim)
    return claims


def _normalize_claim_conflict_report(bundle: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(bundle)
    claims = normalized.get("claims", [])
    if not isinstance(claims, list):
        claims = []
    normalized["claim_conflict_report"] = build_claim_conflict_report(
        [claim for claim in claims if isinstance(claim, dict)]
    )
    return normalized


def _build_plan_input_diagnostics(
    *,
    canonical_guide_claim_bundle: dict[str, Any],
    imported_guide_claim_bundle: dict[str, Any],
    imported_mulligan_plan: dict[str, Any] | None,
    imported_card_behavior_plan: dict[str, Any] | None,
    imported_combo_plan: dict[str, Any] | None,
    imported_global_values_authority_matrix: dict[str, Any],
) -> dict[str, Any]:
    imported_mulligan_payload = imported_mulligan_plan or {}
    imported_card_behavior_payload = imported_card_behavior_plan or {}
    imported_combo_payload = imported_combo_plan or {}
    canonical_claim_ids = {
        str(claim.get("claim_id", ""))
        for claim in canonical_guide_claim_bundle.get("claims", [])
        if isinstance(claim, dict) and claim.get("claim_id")
    }
    imported_claims = [
        claim
        for claim in imported_guide_claim_bundle.get("claims", [])
        if isinstance(claim, dict)
    ]
    ignored_claims = []
    for claim in imported_claims:
        claim_id = str(claim.get("claim_id", ""))
        ignored_claims.append(
            {
                "claim_id": claim_id,
                "claim_kind": normalized_claim_kind(claim),
                "reason": (
                    "plan_claim_reference_only_canonical_truth_retained"
                    if claim_id and claim_id in canonical_claim_ids
                    else "plan_claim_not_canonical_source_truth"
                ),
                "runtime_gate_impact": "none",
            }
        )

    imported_rows: list[dict[str, Any]] = []
    for report_name, section, rows in (
        (
            "mulligan_plan_report.json",
            "rules",
            imported_mulligan_payload.get("rules", []),
        ),
        (
            "card_behavior_plan_report.json",
            "rows",
            imported_card_behavior_payload.get("rows", []),
        ),
        (
            "combo_plan_report.json",
            "combos",
            imported_combo_payload.get("combos", []),
        ),
        (
            "global_values_authority_matrix.json",
            "allowed_step1_overlays",
            imported_global_values_authority_matrix.get(
                "allowed_step1_overlays",
                [],
            ),
        ),
        (
            "global_values_authority_matrix.json",
            "blocked_until_runtime_evidence",
            imported_global_values_authority_matrix.get(
                "blocked_until_runtime_evidence",
                [],
            ),
        ),
    ):
        if not isinstance(rows, list):
            continue
        imported_rows.extend(
            {
                "report": report_name,
                "section": section,
                "row": dict(row),
            }
            for row in rows
            if isinstance(row, dict)
        )

    imported_receipts = imported_guide_claim_bundle.get(
        "canonical_source_receipts",
        imported_guide_claim_bundle.get("globalvalues_source_receipts", []),
    )
    imported_plan_reports = {
        filename: dict(payload)
        for filename, payload in (
            ("mulligan_plan_report.json", imported_mulligan_plan),
            (
                "card_behavior_plan_report.json",
                imported_card_behavior_plan,
            ),
            ("combo_plan_report.json", imported_combo_plan),
        )
        if payload is not None
    }
    return {
        "authority": "diagnostic_only",
        "runtime_gate_impact": "none",
        "guide_claim_bundle_status": "ignored_as_runtime_authority",
        "source_receipts_status": "ignored_as_runtime_authority",
        "canonical_claim_ids": sorted(canonical_claim_ids),
        "imported_claim_count": len(imported_claims),
        "imported_claims": [dict(claim) for claim in imported_claims],
        "imported_source_receipt_count": (
            len(imported_receipts) if isinstance(imported_receipts, list) else 0
        ),
        "imported_source_receipts": (
            [
                dict(receipt) if isinstance(receipt, dict) else receipt
                for receipt in imported_receipts
            ]
            if isinstance(imported_receipts, list)
            else []
        ),
        "ignored_claims": ignored_claims,
        "imported_row_count": len(imported_rows),
        "imported_rows": imported_rows,
        "imported_plan_reports": imported_plan_reports,
    }


def _policy_mulligan_deck_cards(
    gameplan_cards: Any,
    card_metadata: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    metadata_by_card = _metadata_rows_by_card(card_metadata)
    if isinstance(gameplan_cards, dict):
        rows = gameplan_cards.items()
    elif isinstance(gameplan_cards, list):
        rows = (
            (str(row.get("card_id", row.get("id", ""))), row)
            for row in gameplan_cards
            if isinstance(row, dict)
        )
    else:
        rows = []
    merged: dict[str, dict[str, Any]] = {}
    for card_id, row in rows:
        card_id = str(card_id)
        if not card_id:
            continue
        base = metadata_by_card.get(card_id, {})
        if isinstance(row, dict):
            merged[card_id] = {**base, **row}
        else:
            merged[card_id] = {**base, "card_id": card_id}
    return merged


def _explicit_bot_delegation_claims(
    *,
    card_ids: Mapping[str, Any],
    existing_claims: list[dict[str, Any]],
    policy_id: str,
) -> list[dict[str, Any]]:
    already_disposed = {
        card_id
        for claim in existing_claims
        for card_id in _claim_card_ids(claim)
    }
    delegated_cards = sorted(
        {
            str(card_id).strip()
            for card_id in card_ids
            if str(card_id).strip()
            and str(card_id).strip() not in already_disposed
        }
    )
    if not delegated_cards:
        return []
    return [
        {
            "claim_id": "bot-native-pre-run-explicit-delegation",
            "claim_kind": "mulligan_bot_delegation",
            "policy_id": policy_id,
            "policy_rule_id": "intentional_bot_delegation",
            "cards": delegated_cards,
            "reason_code": "unsupported_exact_mulligan_authority",
        }
    ]


def _claim_card_ids(claim: dict[str, Any]) -> set[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    if not isinstance(cards, list):
        return set()
    return {str(card) for card in cards if str(card)}


def _is_internal_mulligan_policy_claim(
    claim: Mapping[str, Any],
) -> bool:
    return (
        normalized_claim_kind(claim) == "mulligan_bot_delegation"
        or str(claim.get("source_type", "")).strip().lower()
        == "versioned_internal_policy"
        or str(claim.get("source_family", "")).strip().lower()
        == "versioned_internal_policy"
        or str(claim.get("policy_rule_id", "")).strip()
        in {"explicit_policy_claim", "intentional_bot_delegation"}
    )


def _metadata_rows_by_card(
    card_metadata: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    rows = card_metadata.get("cards", []) if isinstance(card_metadata, dict) else card_metadata
    if not isinstance(rows, list):
        return {}
    return {
        str(row["card_id"]): dict(row)
        for row in rows
        if isinstance(row, dict) and row.get("card_id")
    }


def _filter_plan_reports_by_lifecycle(
    *,
    initial_lifecycle_rows: list[dict[str, Any]],
    mulligan_plan: dict[str, Any],
    card_behavior_plan: dict[str, Any],
    combo_plan: dict[str, Any],
    global_values_authority_matrix: dict[str, Any],
    canonical_global_values_authority_matrix: dict[str, Any],
    card_roles: dict[str, Any],
    deck_identity: dict[str, Any],
    verified_source_receipts: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    globalvalues_selection = select_claims_for_surface(
        initial_lifecycle_rows,
        "globalvalues",
        context={
            "deck_identity": deck_identity,
            "verified_source_receipts": verified_source_receipts,
        },
    )
    globalvalues_decision_claims = [
        *globalvalues_selection["accepted_claims"],
        *globalvalues_selection["rejected_claims"],
    ]
    del card_roles
    globalvalues_diagnostics = build_globalvalues_authority_matrix(
        aggression_profile="baseline",
        claims=globalvalues_decision_claims,
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
    )
    return (
        mulligan_plan,
        card_behavior_plan,
        combo_plan,
        _filter_globalvalues_authority_matrix(
            global_values_authority_matrix,
            canonical_matrix=canonical_global_values_authority_matrix,
            diagnostic_matrix=globalvalues_diagnostics,
        ),
    )


def _filter_globalvalues_authority_matrix(
    matrix: dict[str, Any],
    *,
    canonical_matrix: dict[str, Any],
    diagnostic_matrix: dict[str, Any],
) -> dict[str, Any]:
    result = dict(canonical_matrix)
    allowed_rows = [
        dict(row)
        for row in canonical_matrix.get("allowed_step1_overlays", [])
        if isinstance(row, dict)
    ]
    diagnostic_blocked = [
        row
        for row in diagnostic_matrix.get("blocked_until_runtime_evidence", [])
        if isinstance(row, dict)
    ]
    blocked_rows = [
        dict(row)
        for row in canonical_matrix.get("blocked_until_runtime_evidence", [])
        if isinstance(row, dict)
    ]
    for row in diagnostic_blocked:
        if row not in blocked_rows:
            blocked_rows.append(dict(row))
    canonical_signatures = {
        _globalvalues_plan_row_signature(row)
        for row in allowed_rows
    }
    for row in matrix.get("allowed_step1_overlays", []):
        if not isinstance(row, dict):
            continue
        if row.get("key") == "baseline":
            if any(
                row == canonical_row
                for canonical_row in allowed_rows
                if canonical_row.get("key") == "baseline"
            ):
                continue
        elif _globalvalues_plan_row_signature(row) in canonical_signatures:
            continue
        blocked_rows.append(
            {
                "key": str(row.get("key", "")),
                "operation": str(row.get("operation", "")),
                "overlay": str(row.get("overlay", "")),
                "value": (
                    None
                    if row.get("value") is None
                    else str(row.get("value"))
                ),
                "authority": "source_contract_suppressed",
                "claim_id": str(row.get("claim_id", "")),
                "claim_refs": sorted(_row_claim_ids(row)),
                "reason": "globalvalues_plan_row_not_canonical",
                "blocked_reason": "globalvalues_plan_row_not_canonical",
            }
        )
    result["allowed_step1_overlays"] = allowed_rows
    result["blocked_until_runtime_evidence"] = blocked_rows
    return result


def _globalvalues_plan_row_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("key", "")),
        str(row.get("operation", "")),
        str(row.get("overlay", "")),
        None if row.get("value") is None else str(row.get("value")),
        str(row.get("reason", "")),
        str(row.get("authority", "")),
        tuple(sorted(_row_claim_ids(row))),
    )


def _row_claim_ids(row: dict[str, Any]) -> set[str]:
    claim_ids: set[str] = set()
    for key in ("claim_id", "source_claim_id"):
        value = row.get(key)
        if value:
            claim_ids.add(str(value))
    for key in ("claim_ids", "source_claim_ids", "claim_refs", "merged_claim_ids"):
        value = row.get(key, [])
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            claim_ids.update(str(item) for item in value if str(item))
    return claim_ids


def _filter_runtime_rows_by_claim_ids(
    rows: Any,
    allowed_claim_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and bool(_row_claim_ids(row) & allowed_claim_ids)
    ]


def _card_behavior_identity_links(gameplan_contract: dict[str, Any]) -> dict[str, Any]:
    cards = gameplan_contract.get("cards", {})
    if not isinstance(cards, dict):
        return {}
    identity_links: dict[str, Any] = {}
    for card_id, row in cards.items():
        if not isinstance(row, dict):
            continue
        source_card_id = str(card_id)
        links = list(row.get("linked_entities", []))
        owner_links: dict[str, Any] = {"links": links}
        for curated_link in curated_links_for(source_card_id):
            link_kind = str(curated_link.get("link_kind", "")).strip()
            runtime_card_id = str(curated_link.get("card_id", "")).strip()
            if link_kind and runtime_card_id:
                owner_links[link_kind] = runtime_card_id
        identity_links[source_card_id] = owner_links
    return identity_links


def disposition_diagnostics_document(
    *,
    dispositions,
    dual_closure,
) -> dict[str, Any]:
    """Project the temporary diagnostic payload from canonical typed truth."""

    return {
        "authority": "diagnostic_only",
        "operator_gate_impact": "diagnostic_only",
        "apply_blocking": False,
        "normal_apply_authority": "reports/operator_summary.json",
        "ledger": {
            "deck_fingerprint": dispositions.deck_fingerprint,
            "content_sha256": dispositions.content_sha256,
            "cards": [
                {
                    "deck_fingerprint": row.deck_fingerprint,
                    "composite_card_key": row.composite_card_key,
                    "zone": row.zone,
                    "official_semantics": json.loads(
                        row.official_semantics_canonical_json
                    ),
                    "authority_lane": row.authority_lane.value,
                    "evidence_ids": list(row.evidence_ids),
                    "claim_ids": list(row.claim_ids),
                    "physical_owner": row.physical_owner,
                    "disposition": row.disposition.value,
                    "runtime_paths": list(row.runtime_paths),
                    "reason_code": row.reason_code,
                }
                for row in dispositions.cards
            ],
            "claims": [
                {
                    "deck_fingerprint": row.deck_fingerprint,
                    "claim_id": row.claim_id,
                    "claim_kind": row.claim_kind,
                    "evidence_id": row.evidence_id,
                    "disposition": row.disposition.value,
                    "runtime_paths": list(row.runtime_paths),
                    "reason_code": row.reason_code,
                }
                for row in dispositions.claims
            ],
        },
        "dual_closure": {
            "pre_run_contract_status": (
                dual_closure.pre_run_contract_status
            ),
            "strategy_authority_status": (
                dual_closure.strategy_authority_status
            ),
            "exact_guide_authority": dual_closure.exact_guide_authority,
            "unresolved_reasons": list(dual_closure.unresolved_reasons),
        },
    }
