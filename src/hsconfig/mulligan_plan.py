"""Build the typed Mulligan plan from explicit B, D, and E authority."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

from hsconfig.condition_format import lower_runtime_condition
from hsconfig.evidence_contract import (
    classify_evidence_authority,
    load_policy_profile,
)
from hsconfig.mulligan_selector import normalize_mulligan_selector
from hsconfig.package_domain import (
    BotDelegationModel,
    EvidenceLane,
    MulliganPlanModel,
    MulliganRuleModel,
    MulliganSuppressionModel,
    PolicyProfile,
)
from hsconfig.source_claim_gap_report import (
    suppressed_mulligan_claims_from_lifecycle,
)
from hsconfig.source_claim_lifecycle import lifecycle_claim_id
from hsconfig.source_document_model import (
    can_lower_to_mulligan,
    normalized_claim_kind,
)


_DELEGATION_RULE_ID = "intentional_bot_delegation"
_EXPLICIT_POLICY_RULE_ID = "explicit_policy_claim"


def build_mulligan_plan(
    *,
    deck_name: str,
    claims: Sequence[Mapping[str, Any]],
    card_roles: Mapping[str, Any],
    deck_cards: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    policy_profile: PolicyProfile,
    expected_policy_profile: PolicyProfile | None = None,
    internal_policy_claims: Sequence[Mapping[str, Any]] = (),
    source_claim_lifecycle_rows: Sequence[Mapping[str, Any]] | None = None,
    deck_identity: Mapping[str, Any] | None = None,
    verified_source_receipts: Sequence[Mapping[str, Any]] = (),
) -> MulliganPlanModel:
    """Return the complete, fail-closed Mulligan authority decision.

    Lane B exact-guide claims and Lane D explicit deterministic policy claims
    may emit runtime rules. Lane E claims may only produce visible bot
    delegation. Card metadata, deck names, role ranks, and mana curve never
    create a rule or delegation.
    """

    expected_policy = (
        expected_policy_profile
        if expected_policy_profile is not None
        else load_policy_profile()
    )
    if policy_profile != expected_policy:
        raise ValueError("policy_profile_not_packaged")
    del deck_cards

    rules_by_identity: dict[
        tuple[str, str, bytes, str, bytes],
        MulliganRuleModel,
    ] = {}
    suppressed_by_card: dict[str, MulliganSuppressionModel] = {}
    delegated_by_card: dict[str, BotDelegationModel] = {}
    merged_duplicate_rule_count = 0

    source_claims = _merge_claim_rows(
        claims,
        suppressed_mulligan_claims_from_lifecycle(
            [dict(row) for row in source_claim_lifecycle_rows or ()]
        ),
    )
    for claim in source_claims:
        claim_kind = normalized_claim_kind(claim)
        claim_cards = _claim_cards(claim)
        lifecycle = claim.get("_claim_lifecycle")
        if (
            isinstance(lifecycle, Mapping)
            and lifecycle.get("surface_gate_allowed") is False
        ):
            _suppress_cards(
                suppressed_by_card,
                claim=claim,
                card_ids=claim_cards,
                action=_claim_action(claim_kind),
                reason_code=str(
                    lifecycle.get("surface_gate_reason")
                    or "surface_gate_rejected"
                ),
            )
            continue

        gate = can_lower_to_mulligan(
            claim,
            card_roles=card_roles,
            deck_identity=deck_identity,
            verified_source_receipts=verified_source_receipts,
        )
        if not gate.allowed:
            _suppress_cards(
                suppressed_by_card,
                claim=claim,
                card_ids=claim_cards,
                action=_claim_action(claim_kind),
                reason_code=gate.reason,
            )
            continue

        authority = _classified_authority(
            claim,
            deck_identity=deck_identity,
            verified_source_receipts=verified_source_receipts,
            policy_profile=policy_profile,
        )
        if (
            authority is None
            or authority.lane is not EvidenceLane.EXACT_LIVE_GUIDE
            or not authority.runtime_authorized
        ):
            _suppress_cards(
                suppressed_by_card,
                claim=claim,
                card_ids=claim_cards,
                action=_claim_action(claim_kind),
                reason_code="evidence_lane_unclassified",
            )
            continue

        claim_rules, claim_suppressions = _lane_b_rows(
            claim,
            claim_kind=claim_kind,
            claim_cards=claim_cards,
            authority_reason=authority.reason,
        )
        for row in claim_suppressions:
            _add_suppression(suppressed_by_card, row)
        for row in claim_rules:
            existing = rules_by_identity.get(row.identity)
            if existing is None:
                rules_by_identity[row.identity] = row
                continue
            merged_duplicate_rule_count += 1
            rules_by_identity[row.identity] = _merge_rule_authority(
                existing,
                row,
            )

    for raw_claim in internal_policy_claims:
        claim = dict(raw_claim)
        claim_kind = normalized_claim_kind(claim)
        claim_cards = _claim_cards(claim)
        if claim_kind == "mulligan_bot_delegation":
            delegations = _explicit_bot_delegations(
                (claim,),
                policy_profile=policy_profile,
            )
            if not delegations:
                _suppress_cards(
                    suppressed_by_card,
                    claim=claim,
                    card_ids=claim_cards,
                    action="none",
                    reason_code="evidence_lane_unclassified",
                )
                continue
            for row in delegations:
                delegated_by_card.setdefault(row.card_id, row)
            continue

        policy_rules, policy_suppressions = _lane_d_rows(
            claim,
            policy_profile=policy_profile,
            deck_identity=deck_identity,
            verified_source_receipts=verified_source_receipts,
        )
        for row in policy_suppressions:
            _add_suppression(suppressed_by_card, row)
        for row in policy_rules:
            existing = rules_by_identity.get(row.identity)
            if existing is None:
                rules_by_identity[row.identity] = row
                continue
            merged_duplicate_rule_count += 1
            rules_by_identity[row.identity] = _merge_rule_authority(
                existing,
                row,
            )

    rules = tuple(sorted(rules_by_identity.values(), key=lambda row: row.identity))
    exact_rule_cards = {
        row.card_id for row in rules if row.selector_kind == "card"
    }
    bot_delegated = tuple(
        delegated_by_card[card_id]
        for card_id in sorted(delegated_by_card)
        if card_id not in exact_rule_cards
    )
    suppressed = tuple(
        suppressed_by_card[card_id] for card_id in sorted(suppressed_by_card)
    )
    return MulliganPlanModel(
        deck_name=deck_name,
        rules=rules,
        suppressed=suppressed,
        bot_delegated=bot_delegated,
        merged_duplicate_rule_count=merged_duplicate_rule_count,
    )


def _lane_b_rows(
    claim: Mapping[str, Any],
    *,
    claim_kind: str,
    claim_cards: tuple[str, ...],
    authority_reason: str,
) -> tuple[
    tuple[MulliganRuleModel, ...],
    tuple[MulliganSuppressionModel, ...],
]:
    action = _claim_action(claim_kind)
    if action == "none":
        return (), _suppression_rows(
            claim=claim,
            card_ids=claim_cards,
            action=action,
            reason_code="claim_kind_not_mulligan_surface",
        )

    rules: list[MulliganRuleModel] = []
    suppressions: list[MulliganSuppressionModel] = []
    condition, unsupported_reason = lower_runtime_condition(
        claim.get("conditions", claim.get("condition", "*"))
    )
    for card_id, selector_seed, explicit_selector in _selector_rows_from_claim(
        claim,
        claim_cards,
    ):
        selector_info = normalize_mulligan_selector(
            {
                "card": card_id,
                "selector_kind": claim.get("selector_kind", ""),
                "selector": selector_seed,
            }
        )
        if (
            not selector_info["supported"]
            or selector_info["selector_kind"] == "wildcard"
        ):
            suppressions.extend(
                _suppression_rows(
                    claim=claim,
                    card_ids=(card_id,),
                    action=action,
                    reason_code=(
                        str(selector_info["reason"])
                        if not selector_info["supported"]
                        else "wildcard_mulligan_selector_forbidden"
                    ),
                )
            )
            continue
        selector_cards = tuple(
            str(card)
            for card in selector_info.get("selector_cards", ())
            if str(card)
        )
        if (
            explicit_selector
            and selector_cards
            and not set(selector_cards).issubset(set(claim_cards))
        ):
            suppressions.extend(
                _suppression_rows(
                    claim=claim,
                    card_ids=(card_id,),
                    action=action,
                    reason_code="selector_cards_not_in_claim",
                )
            )
            continue
        if explicit_selector and selector_cards:
            card_id = selector_cards[0]
        if unsupported_reason is not None:
            suppressions.extend(
                _suppression_rows(
                    claim=claim,
                    card_ids=(card_id,),
                    action=action,
                    reason_code=_mulligan_condition_reason(
                        unsupported_reason
                    ),
                )
            )
            continue
        rules.append(
            _rule_model(
                claim=claim,
                card_id=card_id,
                selector_kind=str(selector_info["selector_kind"]),
                selector=selector_info["selector"],
                action=action,
                condition=condition,
                reason=str(
                    claim.get("evidence_text_short") or authority_reason
                ),
                confidence=str(
                    claim.get(
                        "claim_confidence",
                        claim.get("confidence", "source_backed"),
                    )
                ),
            )
        )
    return tuple(rules), tuple(suppressions)


def _lane_d_rows(
    claim: Mapping[str, Any],
    *,
    policy_profile: PolicyProfile,
    deck_identity: Mapping[str, Any] | None,
    verified_source_receipts: Sequence[Mapping[str, Any]],
) -> tuple[
    tuple[MulliganRuleModel, ...],
    tuple[MulliganSuppressionModel, ...],
]:
    claim_cards = _claim_cards(claim)
    claim_kind = normalized_claim_kind(claim)
    action = _claim_action(claim_kind)
    authority = _classified_authority(
        claim,
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
        policy_profile=policy_profile,
    )
    if (
        authority is None
        or authority.lane is not EvidenceLane.VERSIONED_INTERNAL_POLICY
        or not authority.runtime_authorized
        or claim.get("policy_rule_id") != _EXPLICIT_POLICY_RULE_ID
    ):
        return (), _suppression_rows(
            claim=claim,
            card_ids=claim_cards,
            action=action,
            reason_code="evidence_lane_unclassified",
        )
    if claim_kind != "mulligan_keep" or claim.get("action") != "hold":
        return (), _suppression_rows(
            claim=claim,
            card_ids=claim_cards,
            action=action,
            reason_code="policy_mulligan_keep_authority_required",
        )
    condition, unsupported_reason = lower_runtime_condition(
        claim.get("conditions", claim.get("condition", "*"))
    )
    if unsupported_reason is not None or condition != "*":
        return (), _suppression_rows(
            claim=claim,
            card_ids=claim_cards,
            action=action,
            reason_code="policy_mulligan_requires_unconditional_context_free_claim",
        )
    if (
        claim.get("selector") not in {None, ""}
        or claim.get("selector_kind") not in {None, "", "card"}
    ):
        return (), _suppression_rows(
            claim=claim,
            card_ids=claim_cards,
            action=action,
            reason_code="policy_mulligan_requires_exact_card_selector",
        )
    return (
        tuple(
            _rule_model(
                claim=claim,
                card_id=card_id,
                selector_kind="card",
                selector=card_id,
                action="hold",
                condition="*",
                reason=str(claim.get("reason_code")),
                confidence="policy_backed",
            )
            for card_id in claim_cards
        ),
        (),
    )


def _classified_authority(
    claim: Mapping[str, Any],
    *,
    deck_identity: Mapping[str, Any] | None,
    verified_source_receipts: Sequence[Mapping[str, Any]],
    policy_profile: PolicyProfile,
):
    try:
        return classify_evidence_authority(
            claim=claim,
            deck_identity=deck_identity or {},
            verified_source_receipts=verified_source_receipts,
            policy_profile=_policy_profile_mapping(policy_profile),
            expected_policy_profile=policy_profile,
        )
    except ValueError:
        return None


def _policy_profile_mapping(
    policy_profile: PolicyProfile,
) -> dict[str, Any]:
    return {
        "policy_id": policy_profile.policy_id,
        "version": policy_profile.version,
        "effective_date": policy_profile.effective_date,
        "content_sha256": policy_profile.content_sha256,
        "rules": json.loads(policy_profile.rules_canonical_json),
    }


def _explicit_bot_delegations(
    claims: Sequence[Mapping[str, Any]],
    *,
    policy_profile: PolicyProfile,
) -> tuple[BotDelegationModel, ...]:
    delegation_rule_ids = {
        str(rule.get("rule_id"))
        for rule in json.loads(policy_profile.rules_canonical_json)
        if isinstance(rule, Mapping)
        and rule.get("authority_lane") == "E"
        and rule.get("action") == "delegate_without_runtime_row"
    }
    rows: dict[str, BotDelegationModel] = {}
    for claim in claims:
        if (
            claim.get("claim_kind") != "mulligan_bot_delegation"
            or claim.get("policy_id") != policy_profile.policy_id
            or claim.get("policy_rule_id") not in delegation_rule_ids
            or not str(claim.get("claim_id", "")).strip()
        ):
            continue
        reason_code = str(claim.get("reason_code", "")).strip()
        if not reason_code:
            continue
        for card_id in _claim_cards(claim):
            rows[card_id] = BotDelegationModel(
                card_id=card_id,
                evidence_lane="E",
                policy_id="BOT_NATIVE_PRE_RUN",
                reason_code=reason_code,
            )
    return tuple(rows[card_id] for card_id in sorted(rows))


def _rule_model(
    *,
    claim: Mapping[str, Any],
    card_id: str,
    selector_kind: str,
    selector: Any,
    action: str,
    condition: Any,
    reason: str,
    confidence: str,
) -> MulliganRuleModel:
    if action not in {"hold", "discard"}:
        raise ValueError("mulligan_rule_action_invalid")
    claim_id = lifecycle_claim_id(dict(claim)) or None
    return MulliganRuleModel(
        card_id=card_id,
        selector_kind=selector_kind,
        selector_canonical_json=_canonical_json_bytes(selector),
        action=action,
        condition_canonical_json=_canonical_json_bytes(condition),
        reason=reason,
        confidence=confidence,
        source_claim_ids=_source_claim_ids(claim),
        claim_id=claim_id,
    )


def _merge_rule_authority(
    existing: MulliganRuleModel,
    additional: MulliganRuleModel,
) -> MulliganRuleModel:
    return MulliganRuleModel(
        card_id=existing.card_id,
        selector_kind=existing.selector_kind,
        selector_canonical_json=existing.selector_canonical_json,
        action=existing.action,
        condition_canonical_json=existing.condition_canonical_json,
        reason=existing.reason,
        confidence=existing.confidence,
        source_claim_ids=tuple(
            sorted(
                set(existing.source_claim_ids).union(
                    additional.source_claim_ids
                )
            )
        ),
        claim_id=existing.claim_id or additional.claim_id,
    )


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _claim_action(claim_kind: str) -> str:
    return {
        "mulligan_keep": "hold",
        "mulligan_discard": "discard",
    }.get(claim_kind, "none")


def _claim_cards(claim: Mapping[str, Any]) -> tuple[str, ...]:
    cards = claim.get("cards", ())
    if isinstance(cards, str):
        cards = (cards,)
    if not isinstance(cards, Sequence):
        return ()
    return tuple(
        sorted(
            {
                normalized
                for card in cards
                if (normalized := str(card).strip())
            }
        )
    )


def _source_claim_ids(claim: Mapping[str, Any]) -> tuple[str, ...]:
    raw_ids = claim.get("source_claim_ids", ())
    if isinstance(raw_ids, str):
        raw_ids = (raw_ids,)
    ids = (
        {
            normalized
            for value in raw_ids
            if (normalized := str(value).strip())
        }
        if isinstance(raw_ids, Sequence)
        else set()
    )
    if not ids:
        claim_id = lifecycle_claim_id(dict(claim))
        if claim_id:
            ids.add(claim_id)
    return tuple(sorted(ids))


def _suppression_rows(
    *,
    claim: Mapping[str, Any],
    card_ids: Sequence[str],
    action: str,
    reason_code: str,
) -> tuple[MulliganSuppressionModel, ...]:
    if action not in {"hold", "discard", "none"}:
        action = "none"
    claim_id = lifecycle_claim_id(dict(claim)) or None
    source_claim_ids = _source_claim_ids(claim)
    source_url = str(claim.get("source_url", "")).strip() or None
    # Report rows classify their provenance lane as source_claim; the source
    # document retains the upstream quality type such as public_guide.
    return tuple(
        MulliganSuppressionModel(
            card_id=card_id,
            action=action,
            reason_code=reason_code,
            source_claim_ids=source_claim_ids,
            claim_id=claim_id,
            source_type="source_claim" if source_url else None,
            source_url=source_url,
        )
        for card_id in sorted(set(card_ids))
        if card_id
    )


def _suppress_cards(
    target: dict[str, MulliganSuppressionModel],
    *,
    claim: Mapping[str, Any],
    card_ids: Sequence[str],
    action: str,
    reason_code: str,
) -> None:
    for row in _suppression_rows(
        claim=claim,
        card_ids=card_ids,
        action=action,
        reason_code=reason_code,
    ):
        _add_suppression(target, row)


def _add_suppression(
    target: dict[str, MulliganSuppressionModel],
    row: MulliganSuppressionModel,
) -> None:
    existing = target.get(row.card_id)
    if existing is None or (
        existing.action == "none" and row.action in {"hold", "discard"}
    ):
        target[row.card_id] = row


def _merge_claim_rows(
    claims: Sequence[Mapping[str, Any]],
    additional_claims: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    merged = [dict(claim) for claim in claims]
    seen_claim_ids = {
        claim_id
        for claim in merged
        if (claim_id := lifecycle_claim_id(claim))
    }
    for raw_claim in additional_claims:
        claim = dict(raw_claim)
        claim_id = lifecycle_claim_id(claim)
        if claim_id and claim_id in seen_claim_ids:
            continue
        merged.append(claim)
        if claim_id:
            seen_claim_ids.add(claim_id)
    return tuple(merged)


def _selector_rows_from_claim(
    claim: Mapping[str, Any],
    claim_cards: Sequence[str],
) -> tuple[tuple[str, str, bool], ...]:
    if claim.get("selector") is not None:
        selector = str(claim.get("selector", "")).strip()
        card_id = (
            "*"
            if selector == "*"
            else (claim_cards[0] if claim_cards else selector)
        )
        return ((card_id, selector, True),)
    return tuple((card_id, card_id, False) for card_id in claim_cards)


def _mulligan_condition_reason(reason: str) -> str:
    if reason == "unsupported_condition":
        return "unsupported_mulligan_condition"
    return reason
