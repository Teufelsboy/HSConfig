from __future__ import annotations

from typing import Any

from hsconfig.evidence_contract import load_policy_profile
from hsconfig.mulligan_plan import build_mulligan_plan
from hsconfig.package_domain import MulliganPlanModel
from hsconfig.source_claim_lifecycle import build_initial_lifecycle_rows
from hsconfig.source_document_model import (
    globalvalues_claim_signature,
    normalized_claim_kind,
)
from tests.helpers.live_acquisition import acquire_live_test_provenance


_TEST_DECK_FINGERPRINT = "sha256:mulligan-plan-unit-fixture"


def _build_plan(
    *,
    deck_name: str = "Deck",
    claims: list[dict[str, Any]] | None = None,
    card_roles: dict[str, Any] | None = None,
    deck_cards: dict[str, Any] | None = None,
    source_claim_lifecycle_rows: list[dict[str, Any]] | None = None,
) -> MulliganPlanModel:
    normalized_claims: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for raw_claim in claims or []:
        claim = dict(raw_claim)
        if normalized_claim_kind(claim) in {
            "mulligan_keep",
            "mulligan_discard",
        } and claim.get("_claim_lifecycle", {}).get(
            "surface_gate_allowed"
        ) is not False:
            claim.setdefault("context", "mulligan")
            claim.setdefault("source_family", "guide")
            claim.setdefault(
                "source_url",
                f"https://example.test/{claim['claim_id']}",
            )
            claim.setdefault("as_of_date", "2026-07-29")
            claim.setdefault("deck_match_scope", "exact_deck_matched")
            claim.setdefault("promotion_eligible", True)
            claim.setdefault("source_visibility", "full_text")
            claim.setdefault(
                "source_lane",
                "deck_matched_public_guide",
            )
            claim.setdefault(
                "acquisition_provenance",
                acquire_live_test_provenance(),
            )
            claim.setdefault(
                "deck_match",
                {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": (
                            _TEST_DECK_FINGERPRINT
                        ),
                        "candidate_deck_code_hashes": [
                            "sha256:mulligan-plan-unit-source"
                        ],
                    }
                },
            )
            receipts.append(
                {
                    "receipt_kind": (
                        "canonical_exact_deck_source_document"
                    ),
                    "matched_deck_fingerprint": (
                        _TEST_DECK_FINGERPRINT
                    ),
                    "claim_id": claim["claim_id"],
                    "claim_signature": globalvalues_claim_signature(
                        claim
                    ),
                    "acquisition_provenance": claim[
                        "acquisition_provenance"
                    ],
                }
            )
        normalized_claims.append(claim)
    return build_mulligan_plan(
        deck_name=deck_name,
        claims=normalized_claims,
        card_roles=card_roles or {},
        deck_cards=deck_cards,
        policy_profile=load_policy_profile(),
        source_claim_lifecycle_rows=source_claim_lifecycle_rows,
        deck_identity={
            "deck_fingerprint": _TEST_DECK_FINGERPRINT,
        },
        verified_source_receipts=receipts,
    )


def test_public_report_preserves_canonical_field_names() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "keep-a",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
            },
            {
                "claim_id": "not-mulligan",
                "claim_kind": "hero_power_transform",
                "cards": ["CARD_B"],
            },
        ]
    )

    report = plan.to_report()

    assert set(report) == {
        "deck_name",
        "rules",
        "suppressed_rules",
        "quality",
        "bot_delegated",
        "merged_duplicate_rule_count",
    }
    assert set(report["rules"][0]) == {
        "card",
        "selector_kind",
        "selector",
        "action",
        "condition",
        "reason",
        "confidence",
        "source_claim_ids",
        "source_type",
        "claim_id",
    }
    assert set(report["suppressed_rules"][0]) == {
        "card",
        "action",
        "reason",
        "source_claim_ids",
        "claim_id",
    }


def test_non_mulligan_claim_is_visibly_suppressed() -> None:
    plan = _build_plan(
        deck_name="ShadowPriest",
        claims=[
            {
                "claim_id": "darkbishop-transform",
                "claim_kind": "hero_power_transform",
                "cards": ["SW_448"],
            }
        ],
        card_roles={
            "SW_448": {
                "roles": [
                    "start_of_game",
                    "hero_power_transform",
                ],
            }
        },
    )

    assert plan.rules == ()
    assert [
        (row.card_id, row.action, row.reason_code)
        for row in plan.suppressed
    ] == [
        (
            "SW_448",
            "none",
            "claim_kind_not_mulligan_surface",
        )
    ]


def test_exact_lane_b_keep_emits_without_wildcard_fallback() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "keep-a",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
            }
        ]
    )

    assert [(row.card_id, row.action) for row in plan.rules] == [
        ("CARD_A", "hold")
    ]
    assert all(row.selector_kind != "wildcard" for row in plan.rules)


def test_start_of_game_effect_does_not_become_an_opening_hand_keep() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "renathal-effect-keep",
                "claim_kind": "mulligan_keep",
                "cards": ["REV_018"],
            }
        ],
        card_roles={
            "REV_018": {
                "roles": [
                    "start_of_game",
                    "deckbuilding_modifier",
                ]
            }
        },
    )

    assert plan.rules == ()
    assert plan.suppressed[0].reason_code == (
        "start_of_game_effect_does_not_require_opening_hand"
    )


def test_roles_without_authority_do_not_create_runtime_rules() -> None:
    plan = _build_plan(
        deck_name="Aggro Pirate Curve",
        claims=[],
        card_roles={
            "ONE_DROP": {
                "roles": [
                    "one_drop",
                    "early_pressure",
                    "pirate_pressure",
                ]
            }
        },
        deck_cards={"ONE_DROP": {"cost": 1}},
    )

    assert plan.rules == ()
    assert plan.bot_delegated == ()


def test_same_card_may_preserve_multiple_exact_conditions() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "keep-coin",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "conditions": {"coin": True},
            },
            {
                "claim_id": "keep-no-coin",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "conditions": {"nocoin": True},
            },
        ]
    )

    assert {
        (
            row.action,
            row.condition_canonical_json.decode("utf-8"),
        )
        for row in plan.rules
    } == {("hold", '"coin"'), ("hold", '"nocoin"')}


def test_duplicate_exact_rules_merge_authority_without_duplicate_runtime() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "keep-a-1",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "source_claim_ids": ["source-a"],
            },
            {
                "claim_id": "keep-a-2",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "source_claim_ids": ["source-b"],
            },
        ]
    )

    assert len(plan.rules) == 1
    assert plan.rules[0].source_claim_ids == (
        "source-a",
        "source-b",
    )
    assert plan.merged_duplicate_rule_count == 1


def test_same_card_different_action_is_not_merged() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "keep-a",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
            },
            {
                "claim_id": "discard-a",
                "claim_kind": "mulligan_discard",
                "cards": ["CARD_A"],
            },
        ]
    )

    assert [row.action for row in plan.rules] == [
        "discard",
        "hold",
    ]
    assert plan.merged_duplicate_rule_count == 0


def test_unsupported_condition_is_suppressed_not_broadened() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "bad-condition",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "conditions": {"unsupported": True},
            }
        ]
    )

    assert plan.rules == ()
    assert plan.suppressed[0].reason_code == (
        "unsupported_mulligan_condition"
    )


def test_suppressed_report_restores_canonical_source_claim_provenance() -> None:
    source_url = "https://example.test/unsupported-condition"
    plan = _build_plan(
        claims=[
            {
                "claim_id": "bad-condition-provenance",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "conditions": {"unsupported": True},
                "source_url": source_url,
            }
        ]
    )

    suppressed = plan.to_report()["suppressed_rules"][0]

    assert suppressed["source_type"] == "source_claim"
    assert suppressed["source_url"] == source_url


def test_lifecycle_rejection_is_reported_without_runtime_rule() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "rejected-keep",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "_claim_lifecycle": {
                    "surface_gate_allowed": False,
                    "surface_gate_reason": (
                        "mulligan_requires_exact_deck_match"
                    ),
                },
            }
        ]
    )

    assert plan.rules == ()
    assert plan.suppressed[0].reason_code == (
        "mulligan_requires_exact_deck_match"
    )


def test_report_only_multicard_claim_suppresses_every_card() -> None:
    lifecycle_rows = build_initial_lifecycle_rows(
        [
            {
                "claim_id": "multicard-keep",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_B", "CARD_A"],
                "source_url": "https://example.test/report-only",
                "runtime_lowering_reason": (
                    "claim_not_runtime_lowerable"
                ),
            }
        ]
    )

    plan = _build_plan(
        claims=[],
        source_claim_lifecycle_rows=lifecycle_rows,
    )

    assert [
        (row.card_id, row.action, row.reason_code)
        for row in plan.suppressed
    ] == [
        ("CARD_A", "hold", "claim_not_runtime_lowerable"),
        ("CARD_B", "hold", "claim_not_runtime_lowerable"),
    ]


def test_plus_combo_selector_depth_is_preserved() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "keep-combo",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A", "CARD_B"],
                "selector_kind": "plus_combo",
                "selector": "CARD_A + CARD_B",
                "conditions": {"coin": True},
            }
        ]
    )

    report_rule = plan.to_report()["rules"][0]
    assert report_rule["card"] == "CARD_A"
    assert report_rule["selector_kind"] == "plus_combo"
    assert report_rule["selector"] == "CARD_A + CARD_B"
    assert report_rule["condition"] == "coin"


def test_selector_cards_outside_claim_are_suppressed() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "off-deck-selector",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "selector_kind": "plus_combo",
                "selector": "CARD_A + OFF_DECK",
            }
        ]
    )

    assert plan.rules == ()
    assert plan.suppressed[0].reason_code == (
        "selector_cards_not_in_claim"
    )


def test_unsupported_selector_is_suppressed() -> None:
    plan = _build_plan(
        claims=[
            {
                "claim_id": "bad-selector",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "selector": "CARD_A | CARD_B",
            }
        ]
    )

    assert plan.rules == ()
    assert plan.suppressed[0].reason_code == (
        "unsupported_mulligan_selector"
    )


def test_empty_plan_is_valid_and_has_no_implicit_disposition() -> None:
    plan = _build_plan()

    assert plan.rules == ()
    assert plan.suppressed == ()
    assert plan.bot_delegated == ()
