from __future__ import annotations

from typing import Any

from hsconfig.condition_format import lower_runtime_condition
from hsconfig.mechanic_support import (
    ROLE_ALIASES,
    mechanic_allowed_runtime_blocks,
    mechanic_default_runtime_block,
    mechanic_lowering_policy,
    normalize_role_token,
)
from hsconfig.semantic_intent_score import score_card_behavior_claim
from hsconfig.source_claim_lifecycle import lifecycle_claim_id
from hsconfig.source_document_model import can_lower_to_cardid, normalized_claim_kind
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


def route_card_behavior_surfaces(
    claims: list[dict[str, Any]],
    identity_links: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    option_resolution: list[dict[str, Any]] = []
    strong_cards: set[str] = set()
    resolved_discover_choice_cards = _resolved_choice_cards(claims, identity_links)

    for claim in claims:
        claim_kind = normalized_claim_kind(claim)
        cards = _claim_cards(claim)
        gate = can_lower_to_cardid(claim)
        if not gate.allowed:
            if _belongs_to_dedicated_non_cardid_surface(claim_kind):
                continue
            suppressed.append(_suppressed_row(claim, claim_kind, cards, gate.reason))
            continue
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
            if not _is_target_backed_claim(claim):
                suppressed.append(
                    _suppressed_row(claim, claim_kind, cards, "missing_target_scope")
                )
                continue
            if explicit_block not in TARGET_RUNTIME_BLOCKS:
                suppressed.append(
                    _suppressed_row(claim, claim_kind, cards, "target_scope_not_encoded")
                )
                continue
            intent = _claim_intent(claim, fallback=claim_kind)
            rows.extend(
                _rows_for_cards(
                    claim,
                    cards,
                    condition=condition,
                    behavior_block=explicit_block,
                    intent=intent,
                    roles=[intent],
                )
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
                rows.extend(
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
                    )
                )
                continue

        if claim_kind in INTENT_BLOCKS:
            intent = _claim_intent(claim, fallback=claim_kind)
            rows.extend(
                _rows_for_cards(
                    claim,
                    cards,
                    condition=condition,
                    behavior_block=explicit_block or INTENT_BLOCKS[claim_kind],
                    intent=intent,
                    roles=[claim_kind],
                )
            )
            continue

        if claim_kind == "card_role":
            for card_id in cards:
                if card_id in strong_cards:
                    continue
                intent = _claim_intent(claim, fallback="deck_card")
                row = _base_row(claim, card_id, condition=condition)
                if explicit_block is not None:
                    rows.append(
                        _attach_behavior_fields(
                            row,
                            behavior_block=explicit_block,
                            intent=intent,
                            roles=[intent],
                            claim=claim,
                        )
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
                rows.extend(
                    _rows_for_cards(
                        claim,
                        cards,
                        condition=condition,
                        behavior_block=explicit_block,
                        intent=intent,
                        roles=[claim_kind],
                    )
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

    return {
        "rows": rows,
        "suppressed": suppressed,
        "option_resolution": option_resolution,
    }


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


def _base_row(claim: dict[str, Any], card_id: str, *, condition: str) -> dict[str, Any]:
    return {
        "surface": "CardID.json",
        "surface_family": "CARDID.json",
        "card_id": card_id,
        "claim_id": lifecycle_claim_id(claim),
        "condition": condition,
        "confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
        "source_claim_ids": _source_claim_ids(claim),
        "source_refs": [str(item) for item in claim.get("source_refs", [])],
        "claim_confidence": str(claim.get("claim_confidence", claim.get("confidence", "source_backed"))),
    }


def _suppressed_row(
    claim: dict[str, Any],
    claim_kind: str,
    cards: list[str],
    reason: str,
) -> dict[str, Any]:
    return {
        "claim_id": lifecycle_claim_id(claim),
        "claim_kind": claim_kind,
        "cards": cards,
        "reason": reason,
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
    if isinstance(claim.get("source_claim_ids"), list):
        return [str(item) for item in claim["source_claim_ids"]]
    if claim.get("claim_id"):
        return [str(claim["claim_id"])]
    return []


def _claim_intent(claim: dict[str, Any], *, fallback: str) -> str:
    return str(claim.get("stance") or claim.get("intent") or fallback)


def _is_target_backed_claim(claim: dict[str, Any]) -> bool:
    return _target_scope(claim) is not None


def _target_scope(claim: dict[str, Any]) -> str | None:
    if claim.get("target_scope"):
        return str(claim["target_scope"])
    qualifiers = claim.get("semantic_qualifiers")
    if isinstance(qualifiers, dict) and qualifiers.get("target_scope"):
        return str(qualifiers["target_scope"])
    return None


def _documented_target_scope_condition(claim: dict[str, Any]) -> str | None:
    target_scope = _target_scope(claim)
    if target_scope is None:
        return None
    expected = TARGET_SCOPE_RUNTIME_CONDITIONS.get(target_scope.lower())
    if expected is None:
        return None
    raw_condition = claim.get("conditions", claim.get("condition", "*"))
    if isinstance(raw_condition, dict):
        raw_condition = raw_condition.get("runtime_condition")
    if not isinstance(raw_condition, str):
        return None
    normalized = " ".join(raw_condition.strip().split())
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
        behavior_block=str(row["behavior_block"]),
        intent=str(row.get("intent", "")),
        roles=[str(role) for role in row.get("roles", [])],
        value_default=value_default,
    )
    row["value"] = semantic_score.value
    row["semantic_score"] = {
        "band": semantic_score.band,
        "reason": semantic_score.reason,
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
