from __future__ import annotations

import inspect
import json
from typing import Any

import pytest

from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.evidence_contract import load_policy_profile
from hsconfig.mulligan_plan import build_mulligan_plan
from hsconfig.source_document_model import globalvalues_claim_signature
from tests.helpers.live_acquisition import acquire_live_test_provenance


_DECK_FINGERPRINT = "sha256:mulligan-bot-delegation-fixture"


def _plan_inputs_for(card_id: str) -> dict[str, Any]:
    return {
        "deck_name": "Delegation Fixture",
        "claims": [],
        "card_roles": {
            card_id: {
                "roles": ["start_of_game"],
                "semantic_families": ["start_of_game"],
            }
        },
        "deck_cards": {card_id: {"name": card_id, "cost": 1}},
        "policy_profile": load_policy_profile(),
        "internal_policy_claims": [
            {
                "claim_id": f"delegate-{card_id}",
                "claim_kind": "mulligan_bot_delegation",
                "policy_id": "BOT_NATIVE_PRE_RUN",
                "policy_rule_id": "intentional_bot_delegation",
                "cards": [card_id],
                "reason_code": "unsupported_exact_mulligan_authority",
            }
        ],
    }


@pytest.mark.parametrize(
    "card_id",
    ["JAM_013", "VAC_939", "EDR_804", "DMF_519", "CS2_146", "BOT_020", "SW_448"],
)
def test_contextual_or_start_of_game_cards_delegate_without_exact_keep(
    card_id: str,
) -> None:
    plan = build_mulligan_plan(**_plan_inputs_for(card_id))

    assert all(row.card_id != card_id for row in plan.rules)
    assert card_id in {row.card_id for row in plan.bot_delegated}


def test_only_exact_lane_b_claim_emits_a_source_keep() -> None:
    policy_profile = load_policy_profile()
    acquisition_provenance = acquire_live_test_provenance()
    claim = {
        "claim_id": "exact-b-keep",
        "claim_kind": "mulligan_keep",
        "cards": ["EXACT_B"],
        "context": "mulligan",
        "source_family": "guide",
        "source_url": "https://example.test/exact-b",
        "as_of_date": "2026-07-29",
        "deck_match_scope": "exact_deck_matched",
        "promotion_eligible": True,
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "acquisition_provenance": acquisition_provenance,
        "deck_match": {
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": _DECK_FINGERPRINT,
                "candidate_deck_code_hashes": ["sha256:exact-b-source"],
            }
        },
    }
    source_receipt = {
        "receipt_kind": "canonical_exact_deck_source_document",
        "matched_deck_fingerprint": _DECK_FINGERPRINT,
        "claim_id": claim["claim_id"],
        "claim_signature": globalvalues_claim_signature(claim),
        "acquisition_provenance": acquisition_provenance,
    }

    plan = build_mulligan_plan(
        deck_name="Exact B",
        claims=[claim],
        card_roles={},
        deck_cards={"EXACT_B": {"name": "Exact B", "cost": 7}},
        policy_profile=policy_profile,
        deck_identity={"deck_fingerprint": _DECK_FINGERPRINT},
        verified_source_receipts=[source_receipt],
    )

    assert [(row.card_id, row.action) for row in plan.rules] == [
        ("EXACT_B", "hold")
    ]
    assert plan.bot_delegated == ()
    assert all(row.selector_kind != "wildcard" for row in plan.rules)


def test_only_exact_lane_d_claim_emits_a_policy_keep() -> None:
    policy_profile = load_policy_profile()
    policy_claim = {
        "claim_id": "exact-d-keep",
        "claim_kind": "mulligan_keep",
        "cards": ["EXACT_D"],
        "action": "hold",
        "reason_code": "reviewed_deterministic_keep",
        "policy_id": policy_profile.policy_id,
        "policy_version": policy_profile.version,
        "policy_content_sha256": policy_profile.content_sha256,
        "policy_rule_id": "explicit_policy_claim",
        "source_family": "versioned_internal_policy",
        "source_identity": "BOT_NATIVE_PRE_RUN-v1",
        "as_of_date": "2026-07-29",
    }

    plan = build_mulligan_plan(
        deck_name="Exact D",
        claims=[],
        card_roles={},
        deck_cards={"EXACT_D": {"name": "Exact D", "cost": 9}},
        policy_profile=policy_profile,
        internal_policy_claims=[policy_claim],
    )

    assert [(row.card_id, row.action) for row in plan.rules] == [
        ("EXACT_D", "hold")
    ]
    assert plan.bot_delegated == ()
    assert all(row.selector_kind != "wildcard" for row in plan.rules)


def test_missing_authority_is_suppressed_and_never_implicitly_delegated() -> None:
    plan = build_mulligan_plan(
        deck_name="Unknown",
        claims=[
            {
                "claim_id": "unknown-keep",
                "claim_kind": "mulligan_keep",
                "cards": ["UNKNOWN"],
                "context": "mulligan",
            }
        ],
        card_roles={},
        deck_cards=None,
        policy_profile=load_policy_profile(),
    )

    assert plan.rules == ()
    assert plan.bot_delegated == ()
    assert [(row.card_id, row.reason_code) for row in plan.suppressed] == [
        ("UNKNOWN", "mulligan_requires_public_guide_source")
    ]


def test_missing_delegation_metadata_does_not_create_lane_e() -> None:
    policy_profile = load_policy_profile()
    plan = build_mulligan_plan(
        deck_name="Unknown Delegation",
        claims=[],
        card_roles={},
        deck_cards=None,
        policy_profile=policy_profile,
        internal_policy_claims=[
            {
                "claim_id": "missing-reason",
                "claim_kind": "mulligan_bot_delegation",
                "policy_id": policy_profile.policy_id,
                "policy_rule_id": "intentional_bot_delegation",
                "cards": ["UNKNOWN_E"],
            }
        ],
    )

    assert plan.rules == ()
    assert plan.bot_delegated == ()
    assert [(row.card_id, row.reason_code) for row in plan.suppressed] == [
        ("UNKNOWN_E", "evidence_lane_unclassified")
    ]


def test_card_roles_deck_name_and_curve_never_create_a_keep_or_delegation() -> None:
    plan = build_mulligan_plan(
        deck_name="Aggro Pirate Curve Deck",
        claims=[],
        card_roles={
            "ONE_DROP": {
                "roles": ["one_drop", "early_pressure", "pirate_pressure"]
            }
        },
        deck_cards={"ONE_DROP": {"name": "One Drop", "cost": 1}},
        policy_profile=load_policy_profile(),
    )

    assert plan.rules == ()
    assert plan.bot_delegated == ()


def test_fully_delegated_plan_compiles_empty_values_without_wildcard() -> None:
    plan = build_mulligan_plan(**_plan_inputs_for("JAM_013"))

    compiled = compile_mulligan(plan)

    assert compiled["Mulligan"]["values"] == []
    assert "*" not in json.dumps(compiled, sort_keys=True)


def test_removed_heuristic_inputs_are_not_in_the_public_signature() -> None:
    parameters = inspect.signature(build_mulligan_plan).parameters

    assert "allow_policy_backed" not in parameters
    assert "policy_excluded_card_ids" not in parameters
    assert "external_policy_vetoes" not in parameters
