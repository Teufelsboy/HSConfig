from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from hsconfig.card_intent_taxonomy import (
    CONDITION_REQUIRED_SEMANTIC_INTENTS,
    classify_attack_owner_relation,
    classify_runtime_boundary,
)
from hsconfig.condition_format import lower_runtime_condition
from hsconfig.mechanic_support import (
    ROLE_ALIASES,
    mechanic_allowed_runtime_blocks,
    mechanic_default_runtime_block,
    mechanic_lowering_policy,
    normalize_role_token,
)
from hsconfig.runtime_entity_owner import resolve_runtime_entity_owner
from hsconfig.runtime_row_identity import canonicalize_runtime_rows
from hsconfig.semantic_intent_score import score_card_behavior_claim
from hsconfig.semantic_runtime_gate import semantic_runtime_decision
from hsconfig.source_claim_lifecycle import lifecycle_claim_id
from hsconfig.source_document_model import can_lower_to_cardid, normalized_claim_kind
from hsconfig.source_semantic_qualifiers import normalize_semantic_qualifiers
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS


DEFAULT_ROW_VALUE = "6"

TARGETING_STANCES = {
    "prefer_enemy_hero",
    "prefer_enemy_minion",
    "prefer_friendly_minion",
}
TARGET_RUNTIME_BLOCKS = {
    "BeforeBattlecryTargetBonus",
    "OnDiscoverCardBonus",
    "OnChooseOneCardBonus",
    "OnAdaptCardBonus",
}
TARGET_SCOPE_RUNTIME_CONDITIONS = {
    "enemy_hero": "my_target(count(),hero=true) > 0",
    "enemy_minion": "my_target(count(),minion=true) > 0",
    "friendly_hero": "my_target(count(),hero=true) > 0",
    "friendly_minion": "my_target(count(),minion=true) > 0",
}
TARGETABLE_SCOPES = frozenset(TARGET_SCOPE_RUNTIME_CONDITIONS)
NON_TARGET_SCOPES = frozenset({"no_target"})
INTENT_BLOCKS = {
    "in_hand_value": "InHandBonus",
    "on_board_value": "OnBoardBonus",
    "play_timing": "BeforePlayCardBonus",
    "targeting_rule": "BeforePlayCardBonus",
    "hero_power_use": "BeforeUseHeroPowerBonus",
    "hero_power_transform": "BeforeUseHeroPowerBonus",
    "attack_posture": "BeforePhysicalAttackBonus",
    "discover_choice": "OnDiscoverCardBonus",
    "choose_one_choice": "OnChooseOneCardBonus",
}
OPTION_CLAIM_KINDS = {"discover_choice", "choose_one_choice"}
MECHANIC_USAGE_REQUIRES_EXPLICIT_RUNTIME_BLOCK = {
    "destroy",
    "generic_spell_target",
    "hero_power",
    "silence",
    "transform",
}
OPTION_CARD_KEYS = (
    "option_card_id",
    "option_card",
    "choice_card_id",
    "choice_card",
)
SEMANTIC_SAFETY_SUPPRESSION_REASONS = frozenset(
    {
        *CONDITION_REQUIRED_SEMANTIC_INTENTS,
        "attack_owner_not_proven",
        "battlecry_owner_does_not_attack",
        "buff_target_owner_mismatch",
        "discard_trigger_not_manual_play",
        "spell_cannot_own_on_board",
        "spell_cannot_use_battlecry_target",
        "trigger_owner_does_not_attack",
    }
)


def route_card_behavior_surfaces(
    claims: list[dict[str, Any]],
    identity_links: dict[str, Any] | None = None,
    *,
    deck_identity: Mapping[str, Any] | None = None,
    card_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    verified_source_receipts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    option_resolution: list[dict[str, Any]] = []
    strong_cards: set[str] = set()
    metadata_by_card = _metadata_by_card(card_metadata)
    resolved_discover_choice_cards = _resolved_choice_cards(claims, identity_links)

    for claim in claims:
        claim_kind = normalized_claim_kind(claim)
        cards = _claim_cards(claim)
        condition, condition_error = _condition(claim)
        if condition_error is not None:
            target_condition = _documented_target_scope_condition(claim)
            if target_condition is not None:
                condition = target_condition
                condition_error = None
        if condition_error is not None:
            suppressed.append(_suppressed_row(claim, claim_kind, cards, condition_error))
            continue

        explicit_block, explicit_error = _explicit_runtime_block(claim)
        if explicit_error is not None:
            suppressed.append(
                {
                    **_suppressed_row(
                        claim,
                        claim_kind,
                        cards,
                        str(explicit_error["reason"]),
                    ),
                    "runtime_block": explicit_error["runtime_block"],
                }
            )
            continue

        cards = _preflight_semantic_cards(
            claim=claim,
            claim_kind=claim_kind,
            cards=cards,
            condition=condition,
            runtime_block=explicit_block,
            metadata_by_card=metadata_by_card,
            suppressed=suppressed,
        )
        if not cards:
            continue

        gate = can_lower_to_cardid(
            claim,
            deck_identity=deck_identity,
            verified_source_receipts=verified_source_receipts,
        )
        if not gate.allowed and claim_kind != "targeting_rule":
            if _belongs_to_dedicated_non_cardid_surface(claim_kind):
                continue
            suppressed.append(_suppressed_row(claim, claim_kind, cards, gate.reason))
            continue

        option_rows = _option_resolution_rows(
            claim=claim,
            claim_kind=claim_kind,
            cards=cards,
            identity_links=identity_links,
        )
        option_resolution.extend(option_rows)
        if option_rows:
            resolved_cards = [row["card_id"] for row in option_rows if row["status"] == "resolved"]
            unresolved_cards = [
                row["card_id"] for row in option_rows if row["status"] == "unresolved"
            ]
            if unresolved_cards:
                suppressed.append(
                    _suppressed_row(
                        claim,
                        claim_kind,
                        unresolved_cards,
                        "unresolved_option_identity",
                    )
                )
            if not resolved_cards:
                continue
            cards = resolved_cards
            condition = _choice_surface_condition(
                claim_kind,
                condition,
                _claim_option_card_id(claim),
            )

        if claim_kind == "targeting_rule":
            _, target_scope_error = _target_scope(claim)
            if target_scope_error is not None:
                suppressed.append(
                    _suppressed_row(claim, claim_kind, cards, target_scope_error)
                )
                continue
            if explicit_block not in TARGET_RUNTIME_BLOCKS:
                suppressed.append(
                    _suppressed_row(claim, claim_kind, cards, "target_scope_not_encoded")
                )
                continue
            if not gate.allowed:
                suppressed.append(
                    _suppressed_row(claim, claim_kind, cards, gate.reason)
                )
                continue
            intent = _claim_intent(claim, fallback=claim_kind)
            _append_semantically_allowed_rows(
                rows,
                suppressed,
                _rows_for_cards(
                    claim,
                    cards,
                    condition=condition,
                    behavior_block=explicit_block,
                    intent=intent,
                    roles=[intent],
                ),
                claim=claim,
                claim_kind=claim_kind,
                metadata_by_card=metadata_by_card,
            )
            if intent in TARGETING_STANCES:
                strong_cards.update(cards)
            continue

        if claim_kind == "mechanic_usage":
            mechanic = _claim_mechanic(claim)
            policy = mechanic_lowering_policy(mechanic)
            policy_name = str(policy["policy"])
            if policy_name == "report_only":
                reason = (
                    "requires_supported_cardid_surface"
                    if mechanic == "generated_entity_random_pool"
                    else str(policy["suppression_reason"])
                )
                suppressed.append(
                    {
                        **_suppressed_row(
                            claim,
                            claim_kind,
                            cards,
                            reason,
                        ),
                        "mechanic": mechanic,
                        "lowering_policy": policy_name,
                    }
                )
                continue
            if mechanic in MECHANIC_USAGE_REQUIRES_EXPLICIT_RUNTIME_BLOCK and explicit_block is None:
                suppressed.append(
                    {
                        **_suppressed_row(
                            claim,
                            claim_kind,
                            cards,
                            f"{mechanic}_requires_explicit_runtime_block",
                        ),
                        "mechanic": mechanic,
                        "lowering_policy": policy_name,
                    }
                )
                continue
            if _mechanic_usage_requires_option_identity(mechanic, policy):
                suppressed.append(
                    {
                        **_suppressed_row(
                            claim,
                            claim_kind,
                            cards,
                            "identity_gated_mechanic_requires_option_identity",
                        ),
                        "mechanic": mechanic,
                        "lowering_policy": policy_name,
                    }
                )
                continue
            if explicit_block is not None and not _mechanic_runtime_block_allowed(
                mechanic,
                explicit_block,
            ):
                suppressed.append(
                    {
                        **_suppressed_row(
                            claim,
                            claim_kind,
                            cards,
                            "unsupported_mechanic_runtime_block",
                        ),
                        "mechanic": mechanic,
                        "runtime_block": explicit_block,
                    }
                )
                continue
            behavior_block = explicit_block or mechanic_default_runtime_block(mechanic)
            if behavior_block is not None:
                covered_cards = (
                    [card_id for card_id in cards if card_id in resolved_discover_choice_cards]
                    if mechanic == "discover" and explicit_block is None
                    else []
                )
                uncovered_cards = [card_id for card_id in cards if card_id not in covered_cards]
                if covered_cards:
                    suppressed.append(
                        _suppressed_row(
                            claim,
                            claim_kind,
                            covered_cards,
                            "covered_by_resolved_choice_surface",
                        )
                    )
                if not uncovered_cards:
                    continue
                _append_semantically_allowed_rows(
                    rows,
                    suppressed,
                    _rows_for_cards(
                        claim,
                        uncovered_cards,
                        condition=_mechanic_condition(claim, condition, policy),
                        behavior_block=behavior_block,
                        intent=_claim_intent(
                            claim,
                            fallback=str(
                                policy.get("default_intent")
                                or f"use_{mechanic}_according_to_card_text"
                            ),
                        ),
                        roles=[mechanic],
                        value_default=str(policy.get("default_value", DEFAULT_ROW_VALUE)),
                    ),
                    claim=claim,
                    claim_kind=claim_kind,
                    metadata_by_card=metadata_by_card,
                )
                continue

        if claim_kind in INTENT_BLOCKS:
            intent = _claim_intent(claim, fallback=claim_kind)
            _append_semantically_allowed_rows(
                rows,
                suppressed,
                _rows_for_cards(
                    claim,
                    cards,
                    condition=condition,
                    behavior_block=explicit_block or INTENT_BLOCKS[claim_kind],
                    intent=intent,
                    roles=[claim_kind],
                ),
                claim=claim,
                claim_kind=claim_kind,
                metadata_by_card=metadata_by_card,
            )
            continue

        if claim_kind == "card_role":
            for card_id in cards:
                if card_id in strong_cards:
                    continue
                intent = _claim_intent(claim, fallback="deck_card")
                row = _base_row(claim, card_id, condition=condition)
                if explicit_block is not None:
                    _append_semantically_allowed_rows(
                        rows,
                        suppressed,
                        [
                            _attach_behavior_fields(
                                row,
                                behavior_block=explicit_block,
                                intent=intent,
                                roles=[intent],
                                claim=claim,
                            )
                        ],
                        claim=claim,
                        claim_kind=claim_kind,
                        metadata_by_card=metadata_by_card,
                    )
                else:
                    row["intent"] = "in_hand_priority"
                    row["roles"] = [intent]
                    row["rule_id_suffix"] = "in_hand_priority"
                    row["value"] = _runtime_value(claim, default="7")
                    row["meaningful_runtime_surface"] = False
                    rows.append(row)
            continue

        if claim_kind == "known_bad_pattern":
            if explicit_block is not None:
                intent = _claim_intent(claim, fallback=claim_kind)
                _append_semantically_allowed_rows(
                    rows,
                    suppressed,
                    _rows_for_cards(
                        claim,
                        cards,
                        condition=condition,
                        behavior_block=explicit_block,
                        intent=intent,
                        roles=[claim_kind],
                    ),
                    claim=claim,
                    claim_kind=claim_kind,
                    metadata_by_card=metadata_by_card,
                )
            else:
                suppressed.append(
                    _suppressed_row(
                        claim,
                        claim_kind,
                        cards,
                        "no_documented_card_behavior_surface",
                    )
                )
            continue

        if claim_kind == "combo_sequence":
            continue

        suppressed.append(
            _suppressed_row(claim, claim_kind, cards, "no_documented_card_behavior_surface")
        )

    owned_rows = _assign_runtime_entity_owners(
        rows,
        suppressed=suppressed,
        claims=claims,
        identity_links=identity_links,
    )
    runtime_rows = [row for row in owned_rows if row.get("behavior_block")]
    report_only_rows = [row for row in owned_rows if not row.get("behavior_block")]
    canonical = canonicalize_runtime_rows(runtime_rows)
    output_rows = sorted(
        [*canonical["rows"], *report_only_rows],
        key=_runtime_and_report_row_sort_key,
    )
    return {
        "rows": output_rows,
        "suppressed": suppressed,
        "option_resolution": option_resolution,
        "merged_duplicate_runtime_row_count": canonical["merged_duplicate_count"],
        "runtime_row_conflicts": canonical["conflicts"],
    }


def diagnose_card_behavior_surfaces(
    claims: list[dict[str, Any]],
    *,
    card_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Describe lifecycle-rejected CardID claims without producing rows."""
    suppressed: list[dict[str, Any]] = []
    metadata_by_card = _metadata_by_card(card_metadata)
    for claim in claims:
        claim_kind = normalized_claim_kind(claim)
        cards = _claim_cards(claim)
        lifecycle = claim.get("_claim_lifecycle")
        lifecycle_reason = (
            str(lifecycle.get("surface_gate_reason") or "")
            if isinstance(lifecycle, Mapping)
            else ""
        )
        if not lifecycle_reason:
            lifecycle_reason = "claim_not_runtime_lowerable"

        condition, condition_error = _condition(claim)
        if condition_error is not None:
            documented_condition = _documented_target_scope_condition(claim)
            condition = documented_condition or "*"
        runtime_block, _ = _explicit_runtime_block(claim)
        remaining_cards = list(cards)
        if runtime_block is not None:
            remaining_cards = _preflight_semantic_cards(
                claim=claim,
                claim_kind=claim_kind,
                cards=cards,
                condition=condition,
                runtime_block=runtime_block,
                metadata_by_card=metadata_by_card,
                suppressed=suppressed,
            )
        if remaining_cards:
            suppressed.append(
                _suppressed_row(
                    claim,
                    claim_kind,
                    remaining_cards,
                    lifecycle_reason,
                )
            )
    return suppressed


def _assign_runtime_entity_owners(
    rows: list[dict[str, Any]],
    *,
    suppressed: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    identity_links: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    claim_kinds = {
        lifecycle_claim_id(claim): normalized_claim_kind(claim)
        for claim in claims
    }
    owner_links = identity_links or {}
    owned_rows: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("behavior_block"):
            owned_rows.append(row)
            continue

        source_card_id = str(row["card_id"])
        semantic_reason = _runtime_owner_semantic_reason(row)
        owner = resolve_runtime_entity_owner(
            source_card_id=source_card_id,
            semantic_reason=semantic_reason,
            identity_links=owner_links,
        )
        if owner is None:
            suppressed.append(
                {
                    "claim_id": str(row.get("claim_id", "")),
                    "claim_kind": claim_kinds.get(
                        str(row.get("claim_id", "")),
                        "",
                    ),
                    "cards": [source_card_id],
                    "reason": "linked_runtime_entity_unresolved",
                }
            )
            continue

        owned_rows.append(
            {
                **row,
                "source_card_id": owner.source_card_id,
                "runtime_card_id": owner.runtime_card_id,
                "link_kind": owner.link_kind,
            }
        )
    return owned_rows


def _runtime_owner_semantic_reason(row: dict[str, Any]) -> str:
    semantic_score = row.get("semantic_score", {})
    semantic_reason = (
        str(semantic_score.get("semantic_reason", ""))
        if isinstance(semantic_score, dict)
        else ""
    )
    if (
        row.get("behavior_block") == "BeforeUseHeroPowerBonus"
        and semantic_reason == "hero_power_transform"
    ):
        return "hero_power_before_use"
    return semantic_reason


def _runtime_and_report_row_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("card_id", "")).strip(),
        str(row.get("behavior_block", "")).strip(),
        str(row.get("condition", "*")).strip() or "*",
        str(row.get("value", "")).strip(),
        str(row.get("claim_id", "")).strip(),
    )


def _rows_for_cards(
    claim: dict[str, Any],
    cards: list[str],
    *,
    condition: str,
    behavior_block: str,
    intent: str,
    roles: list[str],
    value_default: str = DEFAULT_ROW_VALUE,
) -> list[dict[str, Any]]:
    return [
        _attach_behavior_fields(
            _base_row(claim, card_id, condition=condition),
            behavior_block=behavior_block,
            intent=intent,
            roles=roles,
            claim=claim,
            value_default=value_default,
        )
        for card_id in cards
    ]


def _append_semantically_allowed_rows(
    rows: list[dict[str, Any]],
    suppressed: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    claim: dict[str, Any],
    claim_kind: str,
    metadata_by_card: Mapping[str, Mapping[str, Any]],
) -> None:
    for row in candidates:
        semantic_score = row.get("semantic_score", {})
        semantic_reason = str(
            semantic_score.get(
                "semantic_reason",
                semantic_score.get("reason", ""),
            )
        )
        card_id = str(row["card_id"])
        metadata = metadata_by_card.get(card_id, {})
        semantic_text = _semantic_text(claim, metadata)
        boundary_intent = _boundary_intent(claim_kind, semantic_text)
        decision = semantic_runtime_decision(
            semantic_intent=boundary_intent or semantic_reason,
            source_lane=_claim_source_lane(claim),
            condition=str(row["condition"]),
            runtime_block=str(row["behavior_block"]),
            claim_kind=claim_kind,
            card_type=str(metadata.get("type", "")),
            target_scope=str(normalize_semantic_qualifiers(claim).get("target_scope") or ""),
            option_identity=str(_claim_option_card_id(claim) or ""),
            attack_owner_relation=classify_attack_owner_relation(
                semantic_text,
                card_type=str(metadata.get("type", "")),
            ),
        )
        if not decision.allowed:
            suppression_reason = (
                "reciprocal_burn_report_only"
                if semantic_reason == "reciprocal_hero_burn"
                else decision.reason
            )
            suppressed.append(
                _suppressed_row(
                    claim,
                    claim_kind,
                    [str(row["card_id"])],
                    suppression_reason,
                )
            )
            continue
        rows.append(row)


def _base_row(claim: dict[str, Any], card_id: str, *, condition: str) -> dict[str, Any]:
    return {
        "surface": "CardID.json",
        "surface_family": "CARDID.json",
        "card_id": card_id,
        "claim_id": lifecycle_claim_id(claim),
        "condition": condition,
        "confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
        "source_claim_ids": _source_claim_ids(claim),
        "source_refs": _source_refs(claim),
        "claim_confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
    }


def _claim_source_lane(claim: dict[str, Any]) -> str:
    source_lane = str(claim.get("source_lane", "")).strip()
    if source_lane:
        return source_lane
    source_refs = claim.get("source_refs", [])
    if source_refs == ["hearthstonejson_static_semantics"]:
        return "official_static_semantics"
    claim_readiness = str(claim.get("claim_readiness", "")).strip()
    if claim_readiness == "source_backed_static_semantics":
        return "source_backed_static_semantics"
    if claim_readiness == "guide_backed":
        return "deck_matched_public_guide"
    return ""


def _suppressed_row(
    claim: dict[str, Any],
    claim_kind: str,
    cards: list[str],
    reason: str,
) -> dict[str, Any]:
    row = {
        "claim_id": lifecycle_claim_id(claim),
        "claim_kind": claim_kind,
        "cards": cards,
        "reason": reason,
    }
    for key in ("source_claim_ids", "source_refs", "acquisition_provenance"):
        if key in claim:
            value = claim[key]
            if isinstance(value, Mapping):
                row[key] = dict(value)
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                row[key] = list(value)
            else:
                row[key] = [value]
    return row


def _preflight_semantic_cards(
    *,
    claim: dict[str, Any],
    claim_kind: str,
    cards: list[str],
    condition: str,
    runtime_block: str | None,
    metadata_by_card: Mapping[str, Mapping[str, Any]],
    suppressed: list[dict[str, Any]],
) -> list[str]:
    if runtime_block is None or claim_kind in OPTION_CLAIM_KINDS:
        return cards
    remaining: list[str] = []
    qualifiers = normalize_semantic_qualifiers(claim)
    for card_id in cards:
        metadata = metadata_by_card.get(card_id, {})
        semantic_text = _semantic_text(claim, metadata)
        decision = semantic_runtime_decision(
            semantic_intent=_boundary_intent(claim_kind, semantic_text)
            or "semantic_default",
            source_lane=_claim_source_lane(claim),
            condition=condition,
            runtime_block=runtime_block,
            claim_kind=claim_kind,
            card_type=str(metadata.get("type", "")),
            target_scope=str(qualifiers.get("target_scope") or ""),
            option_identity=str(_claim_option_card_id(claim) or ""),
            attack_owner_relation=classify_attack_owner_relation(
                semantic_text,
                card_type=str(metadata.get("type", "")),
            ),
        )
        if not decision.allowed and decision.reason in SEMANTIC_SAFETY_SUPPRESSION_REASONS:
            suppressed.append(
                _suppressed_row(claim, claim_kind, [card_id], decision.reason)
            )
            continue
        remaining.append(card_id)
    return remaining


def _semantic_text(
    claim: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> str:
    return " ".join(
        str(value)
        for value in (
            metadata.get("text"),
            claim.get("evidence_text_short"),
            claim.get("stance"),
            claim.get("intent"),
        )
        if value
    )


def _boundary_intent(claim_kind: str, semantic_text: str) -> str:
    if claim_kind == "discover_choice":
        return "discover_condition_not_encoded"
    if claim_kind == "choose_one_choice":
        return "choose_one_condition_not_encoded"
    return classify_runtime_boundary(semantic_text)


def _metadata_by_card(
    card_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    if isinstance(card_metadata, Mapping):
        if isinstance(card_metadata.get("cards"), Sequence):
            rows = card_metadata["cards"]
        else:
            rows = [
                {**dict(row), "card_id": str(card_id)}
                for card_id, row in card_metadata.items()
                if isinstance(row, Mapping)
            ]
    else:
        rows = card_metadata or []
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return {}
    return {
        str(row["card_id"]): row
        for row in rows
        if isinstance(row, Mapping) and row.get("card_id")
    }


def _claim_cards(claim: dict[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    return [str(card) for card in cards if str(card)]


def _belongs_to_dedicated_non_cardid_surface(claim_kind: str) -> bool:
    return claim_kind in {
        "combo_sequence",
        "gameplan_posture",
        "globalvalue_numeric_tuning",
    }


def _source_claim_ids(claim: dict[str, Any]) -> list[str]:
    source_claim_ids = claim.get("source_claim_ids")
    if isinstance(source_claim_ids, Sequence) and not isinstance(
        source_claim_ids,
        (str, bytes),
    ):
        return [str(item) for item in source_claim_ids]
    if source_claim_ids:
        return [str(source_claim_ids)]
    if claim.get("claim_id"):
        return [str(claim["claim_id"])]
    return []


def _source_refs(claim: Mapping[str, Any]) -> list[str]:
    source_refs = claim.get("source_refs")
    if isinstance(source_refs, Sequence) and not isinstance(
        source_refs,
        (str, bytes),
    ):
        return [str(item) for item in source_refs]
    if source_refs:
        return [str(source_refs)]
    return []


def _claim_intent(claim: dict[str, Any], *, fallback: str) -> str:
    return str(claim.get("stance") or claim.get("intent") or fallback)


def _target_scope(claim: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return a documented target scope or a precise fail-closed reason."""
    target_scope = normalize_semantic_qualifiers(claim).get("target_scope")
    if target_scope is None:
        return None, "missing_target_scope"
    if not isinstance(target_scope, str) or not target_scope:
        return None, "invalid_target_scope"
    if target_scope in NON_TARGET_SCOPES:
        return None, "no_target_scope"
    if target_scope not in TARGETABLE_SCOPES:
        return None, "invalid_target_scope"
    return target_scope, None


def _documented_target_scope_condition(claim: dict[str, Any]) -> str | None:
    target_scope, target_scope_error = _target_scope(claim)
    if target_scope_error is not None or target_scope is None:
        return None
    expected = TARGET_SCOPE_RUNTIME_CONDITIONS.get(target_scope)
    if expected is None:
        return None
    raw_condition = claim.get("conditions", claim.get("condition", "*"))
    if isinstance(raw_condition, dict):
        normalized, condition_error = lower_runtime_condition(raw_condition)
        if condition_error is not None:
            return None
    elif isinstance(raw_condition, str):
        normalized = " ".join(raw_condition.strip().split())
    else:
        return None
    return expected if normalized == expected else None


def _condition(claim: dict[str, Any]) -> tuple[str, str | None]:
    return lower_runtime_condition(claim.get("conditions", claim.get("condition", "*")))


def _explicit_runtime_block(claim: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    block = claim.get("runtime_block")
    if block is None:
        return None, None
    normalized = str(block)
    if normalized not in CARD_BEHAVIOR_BLOCKS:
        return None, {
            "runtime_block": normalized,
            "reason": "unsupported_card_behavior_block",
        }
    return normalized, None


def _runtime_value(claim: dict[str, Any], default: str = DEFAULT_ROW_VALUE) -> str:
    return str(claim.get("runtime_value", claim.get("value", default)))


def _claim_mechanic(claim: dict[str, Any]) -> str:
    token = normalize_role_token(claim.get("mechanic", claim.get("stance", "")))
    return ROLE_ALIASES.get(token, token)


def _mechanic_runtime_block_allowed(mechanic: str, runtime_block: str) -> bool:
    return runtime_block in mechanic_allowed_runtime_blocks(mechanic)


def _mechanic_usage_requires_option_identity(
    mechanic: str,
    policy: dict[str, Any],
) -> bool:
    return (
        mechanic == "choose_one"
        and policy.get("policy") == "identity_gated"
        and policy.get("default_block") is None
    )


def _mechanic_condition(
    claim: dict[str, Any],
    condition: str,
    policy: dict[str, Any],
) -> str:
    if condition != "*" or claim.get("condition") is not None or claim.get("conditions") is not None:
        return condition
    return str(policy.get("default_condition") or condition)


def _attach_behavior_fields(
    row: dict[str, Any],
    *,
    behavior_block: str,
    intent: str,
    roles: list[str],
    claim: dict[str, Any],
    value_default: str = DEFAULT_ROW_VALUE,
) -> dict[str, Any]:
    row["behavior_block"] = behavior_block
    row["intent"] = intent
    row["roles"] = roles
    row["rule_id_suffix"] = str(claim.get("rule_id_suffix", intent))
    semantic_score = score_card_behavior_claim(
        claim,
        card_identity=str(row["card_id"]),
        behavior_block=str(row["behavior_block"]),
        intent=str(row.get("intent", "")),
        roles=[str(role) for role in row.get("roles", [])],
        value_default=value_default,
    )
    row["value"] = semantic_score.value
    row["semantic_score"] = {
        "band": semantic_score.band,
        "reason": semantic_score.reason,
        "semantic_reason": semantic_score.semantic_reason,
        "profile": semantic_score.profile,
        "matched_signals": list(semantic_score.matched_signals),
    }
    row["meaningful_runtime_surface"] = True
    return row


def _option_resolution_rows(
    *,
    claim: dict[str, Any],
    claim_kind: str,
    cards: list[str],
    identity_links: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if claim_kind not in OPTION_CLAIM_KINDS:
        return []

    option_card_id = _claim_option_card_id(claim)
    rows: list[dict[str, Any]] = []
    identity_links = identity_links or {}
    for card_id in cards:
        linked_ids = _linked_card_ids(identity_links.get(card_id, []))
        status = "resolved" if option_card_id and option_card_id in linked_ids else "unresolved"
        rows.append(
            {
                "claim_id": lifecycle_claim_id(claim),
                "card_id": card_id,
                "option_card_id": option_card_id or "",
                "status": status,
            }
        )
    return rows


def _resolved_choice_cards(
    claims: list[dict[str, Any]],
    identity_links: dict[str, Any] | None,
) -> set[str]:
    resolved_cards: set[str] = set()
    for claim in claims:
        claim_kind = normalized_claim_kind(claim)
        if claim_kind != "discover_choice":
            continue
        if not can_lower_to_cardid(claim).allowed:
            continue
        cards = _claim_cards(claim)
        if not cards:
            continue
        _, condition_error = _condition(claim)
        if condition_error is not None:
            continue
        _, explicit_error = _explicit_runtime_block(claim)
        if explicit_error is not None:
            continue
        option_rows = _option_resolution_rows(
            claim=claim,
            claim_kind=claim_kind,
            cards=cards,
            identity_links=identity_links,
        )
        if not option_rows:
            continue
        resolved_cards.update(
            row["card_id"] for row in option_rows if row["status"] == "resolved"
        )
    return resolved_cards


def _claim_option_card_id(claim: dict[str, Any]) -> str | None:
    for key in OPTION_CARD_KEYS:
        if claim.get(key):
            return str(claim[key])
    return None


def _choice_surface_condition(
    claim_kind: str,
    condition: str,
    option_card_id: str | None,
) -> str:
    if condition != "*":
        return condition
    if claim_kind == "discover_choice" and option_card_id:
        return f"my_discover(count(),cardid={option_card_id}) > 0"
    return condition


def _linked_card_ids(value: Any) -> set[str]:
    if isinstance(value, dict):
        if isinstance(value.get("links"), list):
            value = value["links"]
        else:
            return {str(value["card_id"])} if value.get("card_id") else set()
    if not isinstance(value, list):
        return set()
    linked_ids = set()
    for row in value:
        if isinstance(row, dict) and row.get("card_id"):
            linked_ids.add(str(row["card_id"]))
        elif isinstance(row, str):
            linked_ids.add(row)
    return linked_ids
