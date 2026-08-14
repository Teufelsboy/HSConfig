from __future__ import annotations

import json

import pytest

from hsconfig.cli import main
from hsconfig.source_contract_matrix import source_contract_vocabulary_rows
from hsconfig.source_document_model import (
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    can_lower_to_mulligan,
)
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)
from tests.test_universal_wild_no_block_matrix import (
    DECKS,
    FIXTURE_CARD_ID,
    prepare_fixture_deck_with_source_claim,
)


NORMAL_RUNTIME_SURFACES = {"mulligan", "globalvalues", "combo", "cardid"}


def test_contract_vocabulary_covers_every_claim_kind_without_apply_authority():
    rows = source_contract_vocabulary_rows()
    rows_by_kind = {row["claim_kind"]: row for row in rows}

    assert set(rows_by_kind) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert all(row["operator_gate_impact"] == "diagnostic_only" for row in rows)
    assert all(
        set(row["allowed_surfaces"]).issubset(NORMAL_RUNTIME_SURFACES)
        for row in rows
    )
    assert all("Presume.json" not in row["runtime_files"] for row in rows)
    assert all("Concede.json" not in row["runtime_files"] for row in rows)
    assert all("CardBehavior.json" not in row["runtime_files"] for row in rows)

    assert rows_by_kind["mulligan_keep"]["runtime_files"] == ("Mulligan.json",)
    assert rows_by_kind["hero_power_transform"]["runtime_files"] == ("CARDID.json",)
    assert rows_by_kind["globalvalue_numeric_tuning"]["runtime_files"] == ()
    assert rows_by_kind["globalvalue_numeric_tuning"]["default_suppression_reason"] == (
        "requires_runtime_evidence"
    )


def test_report_only_card_is_visible_but_not_treated_as_default_only_success():
    audit = {
        "schema_version": 1,
        "deck_name": "ReportOnlyFixture",
        "claim_rows": {
            "report_claim": {
                "claim_id": "report_claim",
                "claim_kind": "tech_slot",
                "lane": "report_only",
                "policy_lane": "report_only",
                "cards": ["CARD_REPORT"],
            }
        },
        "claim_lifecycle_rows": [
            {
                "claim_id": "report_claim",
                "claim_kind": "tech_slot",
                "policy_lane": "report_only",
                "surface_gate_decision": "rejected",
                "surface_gate_reason": "report_only",
                "builder_or_router_decision": "not_seen_by_builder",
                "runtime_surface": None,
                "emitted_files": [],
                "suppressed_reason": "claim_kind_policy",
                "first_missing_link": "claim_kind_policy",
                "operator_impact": "diagnostic_only",
            }
        ],
        "card_rows": {
            "CARD_REPORT": {
                "name": "Report Card",
                "readiness_lane": "report_only_supported",
                "first_missing_link": "claim_kind_policy",
                "runtime_surfaces": [],
                "claim_lanes": {"report_only": 1},
            }
        },
    }

    report = build_source_to_runtime_explainability_report(audit)
    attention = report["operator_attention"][0]

    assert report["apply_blocking"] is False
    assert attention["status"] == "source_action_needed"
    assert attention["first_missing_link"] == "claim_kind_policy"
    assert attention["next_source_action"] == "map_claim_kind_or_keep_report_only"


def test_start_of_game_hero_power_transform_preserves_effect_without_mulligan_keep(
    tmp_path,
):
    result = prepare_fixture_deck_with_source_claim(
        tmp_path,
        deck_name="StartOfGameEffectCanary",
        claim={
            "claim_id": "effect_only",
            "claim_kind": "hero_power_transform",
            "cards": ["CARD_001"],
            "evidence_text_short": (
                "Keep the deck all shadow so the hero power transforms."
            ),
            "source_confidence": "guide_backed",
            "semantic_qualifiers": {
                "timing": ["start_of_game"],
                "state_requirements": ["hero_power_transform"],
            },
        },
    )

    deck_dir = next((result["package"] / "CustomConfig").iterdir())
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    card_behavior = json.loads(
        (deck_dir / f"{FIXTURE_CARD_ID}.json").read_text(encoding="utf-8")
    )
    behavior_report = json.loads(
        (
            result["package"] / "reports" / "card_behavior_plan_report.json"
        ).read_text(encoding="utf-8")
    )

    assert result["exit_code"] == 0
    assert result["operator_summary"]["runtime_apply_allowed"] is False
    assert result["operator_summary"]["runtime_apply_mode"] == "blocked"
    assert result["operator_summary"]["source_apply_eligibility_reasons"] == [
        "diagnostic_source_not_apply_eligible"
    ]
    assert not any(
        row.get("mulligan") == FIXTURE_CARD_ID
        for row in mulligan["Mulligan"]["values"]
    )
    assert "BeforeUseHeroPowerBonus" not in card_behavior
    assert any(
        row["reason"] == "linked_runtime_entity_unresolved"
        and row["cards"] == [FIXTURE_CARD_ID]
        for row in behavior_report["suppressed"]
    )


@pytest.mark.parametrize(
    ("role", "qualifier"),
    [
        ("hero_power_transform", "hero_power_transform"),
        ("deckbuilding_modifier", "deckbuilding_effect"),
        ("highlander_modifier", "deckbuilding_effect"),
        ("even_odd_modifier", "deckbuilding_effect"),
        ("quest_reward", "deckbuilding_effect"),
        ("transform_effect", "deckbuilding_effect"),
    ],
)
def test_non_hand_start_effect_roles_do_not_become_mulligan_keeps(
    role,
    qualifier,
):
    claim = {
        "claim_kind": "mulligan_keep",
        "cards": ["CARD_EFFECT"],
        "source_confidence": "guide_backed",
        "semantic_qualifiers": {
            "timing": ["start_of_game"],
            "state_requirements": [qualifier],
        },
        "evidence_text_short": "This effect is important for the deck.",
    }

    decision = can_lower_to_mulligan(
        claim,
        card_roles={
            "CARD_EFFECT": {
                "roles": ["start_of_game", role],
                "semantic_families": ["start_of_game", role],
            }
        },
    )

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_any_deck_matrix_has_load_safe_apply_and_no_legacy_runtime_surfaces(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )

    for deck_name, deck_code in DECKS:
        out = tmp_path / deck_name
        assert main(
            [
                "prepare",
                "--deck-name",
                deck_name,
                "--deck-code",
                deck_code,
                "--runtime-root",
                str(tmp_path / "runtime"),
                "--out",
                str(out),
                "--json",
            ]
        ) == 0

        reports = out / "reports"
        operator = json.loads(
            (reports / "operator_summary.json").read_text(encoding="utf-8")
        )
        explainability = json.loads(
            (reports / "source_to_runtime_explainability.json").read_text(
                encoding="utf-8"
            )
        )
        deck_dir = next((out / "CustomConfig").iterdir())

        assert operator["technical_status"] == "VALID_PACKAGE"
        assert operator["runtime_apply_allowed"] is True
        assert operator["runtime_apply_contract"]["apply_authority"] == (
            "reports/operator_summary.json"
        )
        assert explainability["apply_blocking"] is False
        assert explainability["operator_gate_impact"] == "diagnostic_only"
        assert explainability["operator_attention"]
        assert not (deck_dir / "Presume.json").exists()
        assert not (deck_dir / "Concede.json").exists()
        assert not (deck_dir / "CardBehavior.json").exists()
