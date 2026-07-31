import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.config_quality_contract import build_config_quality_report
from hsconfig.current_output import resolve_current_package
from hsconfig.source_closure_intake import build_source_closure_intake_receipt
from tests.helpers.fixture_prepare import load_archetype_matrix
from tests.helpers.verified_deck_input import (
    VERIFIED_SYNTHETIC_CARDS,
    deck_code_for_cards,
    remap_card_ids,
)


DECKS = [
    ("ShadowPriest", "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="),
    ("CtAPaladin", "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA="),
    ("PirateRogue", "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA=="),
    ("BigShaman", "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA=="),
    ("Discolock", "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA"),
    ("TreantDruid", "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA=="),
    ("ImbueMage", "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA="),
    ("MechPala", "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="),
    ("Kingslayer", "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA="),
    ("Boarlock", "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA"),
    ("PirateDH", "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA=="),
    ("CuteWarrior", "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA="),
]
FIXTURE_CARD_ID = VERIFIED_SYNTHETIC_CARDS[0]["card_id"]
FUTURE_FIXTURE_CARD_ID = VERIFIED_SYNTHETIC_CARDS[1]["card_id"]
FIXTURE_CARD_ALIASES = {
    "CARD_001": FIXTURE_CARD_ID,
    "CARD_777": FUTURE_FIXTURE_CARD_ID,
}


def expected_analysis_card_universe(
    deck_identity: dict,
) -> set[str]:
    main_deck_card_ids = {
        str(card["card_id"])
        for card in deck_identity["main_deck"]
    }
    sideboard_card_ids = {
        str(card["card_id"])
        for sideboard in deck_identity.get("sideboards", [])
        for card in sideboard.get("cards", [])
    }
    return main_deck_card_ids | sideboard_card_ids


def expected_linked_runtime_entities(
    derivation_receipt: dict,
) -> set[str]:
    return {
        str(row["runtime_card_id"])
        for row in derivation_receipt.get("linked_runtime_owners", [])
    }


def test_every_matrix_deck_declares_closure_profile():
    for deck in load_archetype_matrix():
        assert deck["closure_profile"]
        assert "closure_profile_first_missing_link" in deck
        assert deck["fixture_expected_load_safe"] is True
        assert deck["fixture_runtime_apply_authority"] == "diagnostic_only"
        assert "runtime_apply_allowed" not in deck


def test_representative_wild_matrix_uses_specific_closure_profiles():
    expected_profiles = {
        "ShadowPriest": "aggro_burn_hero_power",
        "CtAPaladin": "board_flood_recruit",
        "PirateRogue": "weapon_pressure",
        "BigShaman": "cheat_recruit_big",
        "Discolock": "discard_pressure",
        "TreantDruid": "board_flood_recruit",
        "ImbueMage": "hero_power_imbue",
        "MechPala": "board_flood_recruit",
        "Kingslayer": "weapon_pressure",
        "Boarlock": "combo_setup",
        "PirateDH": "weapon_pressure",
    }

    rows = {deck["deck_name"]: deck for deck in load_archetype_matrix()}
    for deck_name, expected_profile in expected_profiles.items():
        assert rows[deck_name]["closure_profile"] == expected_profile


def test_no_block_deck_matrix_matches_source_candidate_proof_manifest():
    proof = json.loads(
        Path("docs/operator/source-candidate-proof-decks.json").read_text(
            encoding="utf-8"
        )
    )

    assert {deck_name for deck_name, _ in DECKS} == {
        row["deck_name"] for row in proof["decks"]
    }


@pytest.mark.parametrize(
    ("deck_name", "deck_code", "first_missing_source_action"),
    [
        ("ShadowPriest", DECKS[0][1], "none"),
        ("CtAPaladin", DECKS[1][1], "add_current_cta_paladin_mulligan_keep_source"),
        ("PirateRogue", DECKS[2][1], "add_current_pirate_rogue_mulligan_or_role_source"),
        ("BigShaman", DECKS[3][1], "add_current_big_shaman_full_text_mulligan_or_gameplan_source"),
        ("Discolock", DECKS[4][1], "add_current_discolock_full_text_mulligan_or_gameplan_source"),
        ("TreantDruid", DECKS[5][1], "add_current_treant_druid_mulligan_keep_source"),
        ("ImbueMage", DECKS[6][1], "none"),
        ("MechPala", DECKS[7][1], "add_card_specific_source_claim"),
        ("Kingslayer", DECKS[8][1], "add_kingslayer_quick_pick_mulligan_source"),
        ("Boarlock", DECKS[9][1], "add_boarlock_fracking_mulligan_source"),
        ("PirateDH", DECKS[10][1], "add_pirate_dh_card_role_or_mulligan_source"),
        ("CuteWarrior", DECKS[11][1], "add_current_full_text_mulligan_or_gameplan_source"),
    ],
)
def test_source_closure_intake_receipt_never_blocks_user_wild_matrix(
    deck_name: str, deck_code: str, first_missing_source_action: str
):
    receipt = build_source_closure_intake_receipt(deck_name, deck_code)

    assert receipt["authority"] == "diagnostic_only"
    assert receipt["source_status_apply_blocking"] is False
    assert receipt["deck_name"] == deck_name
    assert receipt["candidate_count"] >= 1
    assert receipt["source_rows"]
    assert receipt["first_missing_source_action"] == first_missing_source_action
    assert all(row["authority"] == "candidate_seed_only" for row in receipt["source_rows"])
    assert all(row["apply_blocking"] is False for row in receipt["source_rows"])
    assert all(row["can_promote_runtime_claim"] is False for row in receipt["source_rows"])
    assert all(row["can_write_runtime_config"] is False for row in receipt["source_rows"])
    if first_missing_source_action == "none":
        assert receipt["promotion_eligible_seed_count"] >= 1


def _stub_empty_card_fetches(monkeypatch) -> None:
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )


def prepare_fixture_deck_with_source_claim(tmp_path: Path, *, deck_name: str, claim: dict):
    fixture_cards = [
        {
            **VERIFIED_SYNTHETIC_CARDS[0],
            "count": 30,
            "text": "Future mechanic: fixture card text.",
            "mechanics": ["FUTURE_MECHANIC"],
        }
    ]
    cards = tmp_path / "cards.json"
    cards.write_text(
        json.dumps({"cards": fixture_cards}),
        encoding="utf-8",
    )
    sources = tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            [
                {
                    "source_url": "https://example.invalid/qualifier",
                    "source_title": "Qualifier Fixture",
                    "source_family": "guide_fixture",
                    "retrieved_at": "2026-07-13T00:00:00Z",
                    "claims": [remap_card_ids(claim, FIXTURE_CARD_ALIASES)],
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code_for_cards(fixture_cards),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards),
            "--guide-sources-json",
            str(sources),
        ]
    )
    reports = out / "reports"
    return {
        "exit_code": exit_code,
        "package": out,
        "operator_summary": json.loads(
            (reports / "operator_summary.json").read_text(encoding="utf-8")
        ),
        "guide_claim_bundle": json.loads(
            (reports / "guide_claim_bundle.json").read_text(encoding="utf-8")
        ),
    }


def prepare_fixture_deck_with_source_claims(
    tmp_path: Path, *, deck_name: str, claims: list[dict]
):
    fixture_cards = [
        {
            **VERIFIED_SYNTHETIC_CARDS[0],
            "count": 1,
            "text": "Fixture card text.",
        },
        {
            **VERIFIED_SYNTHETIC_CARDS[1],
            "count": 1,
            "name": "Future Fixture Card",
            "text": "Future mechanic fixture card text.",
            "mechanics": ["FUTURE_KEYWORD"],
        },
    ]
    cards = tmp_path / f"{deck_name}_cards.json"
    cards.write_text(
        json.dumps({"cards": fixture_cards}),
        encoding="utf-8",
    )
    sources = tmp_path / f"{deck_name}_sources.json"
    sources.write_text(
        json.dumps(
            [
                {
                    "source_url": f"https://example.invalid/{deck_name}",
                    "source_title": f"{deck_name} Fixture",
                    "source_family": "guide_fixture",
                    "retrieved_at": "2026-07-13T00:00:00Z",
                    "claims": remap_card_ids(claims, FIXTURE_CARD_ALIASES),
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / f"{deck_name}_package"
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code_for_cards(fixture_cards),
            "--runtime-root",
            str(tmp_path / f"{deck_name}_runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards),
            "--guide-sources-json",
            str(sources),
        ]
    )
    reports = out / "reports"
    deck_dir = next((out / "CustomConfig").iterdir())
    return {
        "exit_code": exit_code,
        "package": out,
        "deck_dir": deck_dir,
        "operator_summary": json.loads(
            (reports / "operator_summary.json").read_text(encoding="utf-8")
        ),
        "source_contract_audit": json.loads(
            (reports / "source_contract_audit.json").read_text(encoding="utf-8")
        ),
        "guide_claim_bundle": json.loads(
            (reports / "guide_claim_bundle.json").read_text(encoding="utf-8")
        ),
        "global_values_authority_matrix": json.loads(
            (reports / "global_values_authority_matrix.json").read_text(
                encoding="utf-8"
            )
        ),
        "unsupported_claims_report": json.loads(
            (reports / "unsupported_claims_report.json").read_text(encoding="utf-8")
        ),
        "mulligan": json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8")),
    }


def assert_diagnostic_source_package_is_load_safe_but_apply_blocked(
    operator_summary: dict,
):
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_allowed"] is False
    assert operator_summary["runtime_apply_mode"] == "blocked"
    assert operator_summary["source_apply_eligible"] is False
    assert operator_summary["source_apply_eligibility_reasons"] == [
        "diagnostic_source_not_apply_eligible"
    ]
    assert (
        operator_summary["deck_input_verification"]["status"]
        == "cards_json_matches_deck_code"
    )
    assert operator_summary["deck_input_verification"]["runtime_apply_eligible"] is True
    assert operator_summary["source_contract_audit_summary"]["non_blocking"] is True
    assert operator_summary["no_block_failure_mode_summary"]["hard_block"] is False
    assert operator_summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert operator_summary["source_backed_strong_closure"]["diagnostic_only"] is True
    assert (
        operator_summary["source_backed_strong_closure"][
            "closure_profile_apply_blocking"
        ]
        is False
    )
    assert operator_summary["source_status_diagnostic_only"] is True
    assert operator_summary["source_status_apply_blocking"] is False
    assert operator_summary["source_backed_status"] in {
        "SOURCE_BACKED_STRONG",
        "SOURCE_BACKED_PARTIAL",
    }
    assert isinstance(operator_summary["source_missing_source_actions"], list)
    assert operator_summary["source_backed_strong_closure"]["status"] in {
        "not_reported",
        "ready",
        "needs_source_closure",
    }
    assert isinstance(operator_summary["first_missing_source_action"], str)


def assert_no_runtime_surface_is_hidden_default(deck_dir: Path, operator: dict) -> None:
    required_files = {
        "Mulligan.json",
        "GlobalValues.json",
    }
    emitted_files = {path.name for path in deck_dir.glob("*.json")}
    assert required_files <= emitted_files

    for file_name in emitted_files:
        path = deck_dir / file_name
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            file_name not in {"Combo.json", "GlobalValues.json", "Mulligan.json"}
            and set(payload) <= {"GameCardId", "ConfigComment"}
        ):
            continue
        runtime_rows = [
            row
            for block in payload.values()
            if isinstance(block, dict)
            for row in block.get("values", [])
        ]
        if file_name == "Mulligan.json" and not runtime_rows:
            assert (
                operator["mulligan_bot_delegation_summary"]["count"]
                > 0
            )
            continue
        assert runtime_rows, f"{file_name} has no visible runtime rows"

    assert operator["default_only_runtime_surfaces"] == []
    assert operator["default_only_runtime_surface_details"] == []
    assert operator["no_default_only_runtime_status"] == "clean"
    assert operator["first_missing_source_action"]
    assert operator["source_status_diagnostic_only"] is True
    assert operator["source_status_apply_blocking"] is False
    assert operator["source_backed_status"] in {
        "SOURCE_BACKED_STRONG",
        "SOURCE_BACKED_PARTIAL",
    }
    assert isinstance(operator["source_strong_ready"], bool)
    assert isinstance(operator["source_missing_source_actions"], list)
    assert isinstance(operator["source_status_reasons"], list)
    ledger_rows = operator.get("surface_status_ledger", [])
    assert ledger_rows
    assert all(row["status"] != "default_only" for row in ledger_rows)
    ledger = {row["surface"]: row for row in ledger_rows}
    assert {"mulligan", "globalvalues", "cardid_behavior"} <= set(ledger)
    assert ledger["mulligan"]["status"] in {
        "source_backed",
        "policy_backed",
        "source_and_policy_backed",
        "static_semantics_backed",
        "warning_only",
    }
    mulligan_policy = operator["mulligan_policy_status"]
    assert mulligan_policy["default_only"] is False
    assert mulligan_policy["status"] in {
        "bot_delegated",
        "policy_backed",
        "rich",
        "source_backed",
        "source_and_policy_backed",
    }
    assert isinstance(mulligan_policy.get("policy_lanes", []), list)
    assert isinstance(mulligan_policy.get("policy_reasons", []), list)


def assert_accepted_cardid_behavior_rows_have_bounded_values(behavior_plan: dict) -> None:
    for row in behavior_plan["rows"]:
        if row.get("surface_family") == "CARDID.json" and row.get("behavior_block"):
            assert str(row["value"]).isdigit()
            assert 4 <= int(row["value"]) <= 12


def assert_runtime_surface_shape(deck_dir: Path, deck_card_ids: set[str]) -> None:
    special_files = {"Combo.json", "GlobalValues.json", "Mulligan.json"}
    card_files = {
        path.stem
        for path in deck_dir.glob("*.json")
        if path.name not in special_files
    }
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert card_files == deck_card_ids
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()


def assert_darkbishop_effect_semantics_without_mulligan_keep(deck_dir: Path) -> None:
    darkbishop_path = deck_dir / "SW_448.json"
    hero_power_owner_path = deck_dir / "EX1_625t.json"
    assert darkbishop_path.is_file()
    assert hero_power_owner_path.is_file()
    darkbishop = json.loads(darkbishop_path.read_text(encoding="utf-8"))
    hero_power_owner = json.loads(hero_power_owner_path.read_text(encoding="utf-8"))
    assert darkbishop["GameCardId"] == "SW_448"
    assert "BeforeUseHeroPowerBonus" not in darkbishop
    assert hero_power_owner["GameCardId"] == "EX1_625t"
    hero_power_bonus = hero_power_owner["BeforeUseHeroPowerBonus"]["values"]
    assert hero_power_bonus
    assert any(
        row.get("value") and _has_shadow_hero_power_transform_semantics(row)
        for row in hero_power_bonus
    )
    mulligan = json.loads(
        (deck_dir / "Mulligan.json").read_text(encoding="utf-8")
    )
    assert not any(
        row.get("mulligan") == "SW_448" or row.get("card_id") == "SW_448"
        for row in mulligan["Mulligan"]["values"]
    )


def _has_shadow_hero_power_transform_semantics(row: dict) -> bool:
    text = " ".join(
        str(row.get(key, ""))
        for key in ("comment", "condition", "target", "value", "name")
    ).lower()
    return any(
        token in text
        for token in ("enable_shadow", "shadowform", "mind spike", "shadow hero")
    ) or any(
        token in text
        for token in ("enable_transformed_hero_power", "transformed_hero_power")
    )


def test_darkbishop_transform_semantic_guard_rejects_generic_hero_power_rows():
    assert _has_shadow_hero_power_transform_semantics(
        {"comment": "ShadowPriest: SW_448_enable_shadow_hero_power", "value": "6"}
    )
    assert _has_shadow_hero_power_transform_semantics(
        {"comment": "ShadowPriest: SW_448_enable_transformed_hero_power", "value": "6"}
    )
    assert not _has_shadow_hero_power_transform_semantics(
        {"comment": "generic hero_power priority", "value": "1"}
    )
    assert not _has_shadow_hero_power_transform_semantics(
        {"comment": "generic transform hero_power priority", "value": "1"}
    )


@pytest.mark.parametrize(("deck_name", "deck_code"), DECKS)
def test_valid_wild_deck_produces_load_safe_warning_apply_package(
    tmp_path: Path,
    capsys,
    monkeypatch,
    deck_name: str,
    deck_code: str,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    out = tmp_path / deck_name
    runtime_root = tmp_path / "runtime"

    code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    source_contract_audit = json.loads(
        (out / "reports" / "source_contract_audit.json").read_text(encoding="utf-8")
    )
    source_to_runtime = json.loads(
        (
            out / "reports" / "source_to_runtime_explainability.json"
        ).read_text(encoding="utf-8")
    )
    behavior_plan = json.loads(
        (out / "reports" / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )
    derivation_receipt = json.loads(
        (out / "package_derivation_receipt.json").read_text(encoding="utf-8")
    )
    quality = build_config_quality_report(out)
    if deck_name == "Kingslayer":
        assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
        assert operator["first_missing_source_action"] != "none"
        assert operator["runtime_apply_allowed"] is True
        assert operator["source_backed_strong_closure"]["diagnostic_only"] is True
        assert operator["source_backed_strong_closure"]["closure_profile_apply_blocking"] is False
        assert source_to_runtime["authority"] == "diagnostic_only"
        assert source_to_runtime["apply_blocking"] is False
        assert any(
            row["first_missing_source_action"] != "none"
            for row in source_to_runtime["operator_attention"]
        )
    semantic_report = json.loads(
        (out / "reports" / "semantic_enrichment_report.json").read_text(encoding="utf-8")
    )
    deck_identity = json.loads((out / "reports" / "deck_identity.json").read_text(encoding="utf-8"))

    deck_dirs = [path for path in (out / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    deck_dir = deck_dirs[0]
    deck_card_ids = {
        str(card["card_id"]) for card in deck_identity["main_deck"]
    }
    analysis_card_ids = expected_analysis_card_universe(deck_identity)
    linked_runtime_card_ids = expected_linked_runtime_entities(
        derivation_receipt
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert_no_runtime_surface_is_hidden_default(deck_dir, operator)
    no_block = operator["no_block_failure_mode_summary"]
    assert no_block["hard_block"] is False
    assert no_block["runtime_apply_allowed"] is True
    assert no_block["runtime_apply_mode"] == "load_safe_apply"
    assert no_block["overall"] in {
        "load_safe_apply_allowed",
        "load_safe_apply_allowed_with_warnings",
    }
    assert no_block["categories"]["technical_hard_block"] == []
    assert no_block["operator_message"].startswith("Package is load-safe.")
    assert operator["source_contract_audit_summary"]["non_blocking"] is True
    assert source_contract_audit["schema_version"] == 1
    source_contract_card_ids = set(source_contract_audit["card_rows"])
    assert source_contract_audit["summary"]["cards_total"] == len(source_contract_card_ids)
    assert source_contract_card_ids == analysis_card_ids
    assert source_to_runtime["authority"] == "diagnostic_only"
    assert source_to_runtime["apply_blocking"] is False
    source_to_runtime_card_ids = {
        str(row["card_id"]) for row in source_to_runtime["card_rows"]
    }
    assert source_to_runtime["summary"]["cards_total"] == len(source_to_runtime_card_ids)
    assert source_to_runtime_card_ids == analysis_card_ids
    assert {
        str(row["runtime_card_id"])
        for row in source_to_runtime["runtime_entity_transitions"]
    } == linked_runtime_card_ids
    assert quality["authority"] == "diagnostic_only"
    assert quality["apply_blocking"] is False
    assert quality["runtime_write_performed"] is False
    assert quality["checks"]["legacy_surfaces"]["present"] == []
    assert quality["checks"]["runtime_json"]["stray_cardid_files"] == []
    assert quality["checks"]["runtime_json"]["metadata_leaks"] == []
    assert quality["checks"]["mechanic_runtime_discipline"][
        "report_only_runtime_rows"
    ] == []
    assert quality["checks"]["card_behavior"]["out_of_range_value_rows"] == []
    assert_accepted_cardid_behavior_rows_have_bounded_values(behavior_plan)
    assert source_to_runtime["operator_attention"]
    assert all("closure" in row for row in source_to_runtime["card_rows"])
    assert all(
        row["closure"]["lane"]
        in {
            "source_backed_runtime_lowered",
            "explicit_gap",
            "runtime_backed",
            "source_action_needed",
            "diagnostic_only",
            "baseline_only_visible",
            "report_only",
        }
        for row in source_to_runtime["card_rows"]
    )
    assert operator["mechanic_visibility_summary"]["non_blocking"] is True
    assert operator["semantic_enrichment_summary"]["non_blocking"] is True
    assert operator["next_action"] in {"READY_TO_APPLY_OR_HANDOFF", "READY_TO_APPLY_WITH_WARNINGS"}
    assert semantic_report["non_blocking"] is True
    assert "summary" in semantic_report
    assert "cards" in semantic_report
    assert_runtime_surface_shape(deck_dir, deck_card_ids | linked_runtime_card_ids)
    if deck_name == "ShadowPriest":
        assert_darkbishop_effect_semantics_without_mulligan_keep(deck_dir)


def test_configure_path_preserves_no_block_contract_for_matrix(tmp_path, monkeypatch):
    _stub_empty_card_fetches(monkeypatch)

    for deck_name, deck_code in DECKS:
        out = tmp_path / deck_name
        assert main(
            [
                "configure",
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

        package = resolve_current_package(out)
        operator = json.loads(
            (package / "reports" / "operator_summary.json").read_text(
                encoding="utf-8"
            )
        )
        source_contract_audit = json.loads(
            (package / "reports" / "source_contract_audit.json").read_text(
                encoding="utf-8"
            )
        )
        source_to_runtime = json.loads(
            (
                package / "reports" / "source_to_runtime_explainability.json"
            ).read_text(encoding="utf-8")
        )
        behavior_plan = json.loads(
            (
                package / "reports" / "card_behavior_plan_report.json"
            ).read_text(encoding="utf-8")
        )
        quality = build_config_quality_report(package)
        deck_dirs = [
            path for path in (package / "CustomConfig").iterdir() if path.is_dir()
        ]
        assert len(deck_dirs) == 1
        deck_dir = deck_dirs[0]
        assert operator["technical_status"] == "VALID_PACKAGE"
        assert operator["runtime_load_safe"] is True
        assert operator["runtime_apply_mode"] == "load_safe_apply"
        assert_no_runtime_surface_is_hidden_default(deck_dir, operator)
        assert operator["source_contract_audit_summary"]["non_blocking"] is True
        source_quality = operator["source_claim_quality_summary"]
        assert source_quality["non_blocking"] is True
        assert isinstance(source_quality["source_quality_lane_counts"], dict)
        assert operator["next_action"] in {
            "READY_TO_APPLY_OR_HANDOFF",
            "READY_TO_APPLY_WITH_WARNINGS",
        }
        assert operator["runtime_apply_contract"]["apply_authority"] == "reports/operator_summary.json"
        assert source_contract_audit["schema_version"] == 1
        assert source_to_runtime["authority"] == "diagnostic_only"
        assert source_to_runtime["apply_blocking"] is False
        assert quality["authority"] == "diagnostic_only"
        assert quality["apply_blocking"] is False
        assert quality["runtime_write_performed"] is False
        assert quality["checks"]["legacy_surfaces"]["present"] == []
        assert quality["checks"]["runtime_json"]["stray_cardid_files"] == []
        assert quality["checks"]["runtime_json"]["metadata_leaks"] == []
        assert quality["checks"]["mechanic_runtime_discipline"][
            "report_only_runtime_rows"
        ] == []
        assert quality["checks"]["card_behavior"]["out_of_range_value_rows"] == []
        assert_accepted_cardid_behavior_rows_have_bounded_values(behavior_plan)
        assert operator["mechanic_visibility_summary"]["non_blocking"] is True


def test_unknown_semantic_qualifier_stays_warning_not_apply_block(tmp_path):
    result = prepare_fixture_deck_with_source_claim(
        tmp_path,
        deck_name="QualifierUnknown",
        claim={
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_001"],
            "evidence_text_short": "Use the new future mechanic when possible.",
            "source_confidence": "high",
            "semantic_qualifiers": {"state_requirements": ["future_mechanic"]},
        },
    )

    assert result["exit_code"] == 0
    operator_summary = result["operator_summary"]
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["runtime_apply_allowed"] is False
    assert operator_summary["runtime_apply_mode"] == "blocked"
    assert operator_summary["no_block_failure_mode_summary"]["hard_block"] is False
    mechanic_visibility = operator_summary["mechanic_visibility_summary"]
    assert mechanic_visibility["non_blocking"] is True
    assert "future_mechanic" in mechanic_visibility["mechanics_by_bucket"]["warning_only"]
    assert any(
        boundary["mechanic"] == "future_mechanic"
        for boundary in mechanic_visibility["warning_boundaries"]
    )
    assert operator_summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    claim = result["guide_claim_bundle"]["claims"][0]
    assert claim["semantic_qualifiers"]["state_requirements"] == ["future_mechanic"]


def test_singleton_hero_power_state_requirement_preserves_effect_without_mulligan_keep(tmp_path):
    result = prepare_fixture_deck_with_source_claim(
        tmp_path,
        deck_name="SingletonHeroPower",
        claim={
            "claim_kind": "hero_power_transform",
            "cards": ["CARD_001"],
            "evidence_text_short": "Start of Game transforms the hero power when all spells are Shadow.",
            "source_confidence": "high",
            "semantic_qualifiers": {"state_requirements": "all_shadow_spells"},
        },
    )

    package = result["package"]
    deck_dir = next((package / "CustomConfig").iterdir())
    card_behavior = json.loads(
        (deck_dir / f"{FIXTURE_CARD_ID}.json").read_text(encoding="utf-8")
    )
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    claim = result["guide_claim_bundle"]["claims"][0]
    operator_summary = result["operator_summary"]
    behavior_report = json.loads(
        (package / "reports" / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["exit_code"] == 0
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["runtime_apply_allowed"] is False
    assert operator_summary["runtime_apply_mode"] == "blocked"
    assert claim["semantic_qualifiers"]["state_requirements"] == ["all_shadow_spells"]
    assert "BeforeUseHeroPowerBonus" not in card_behavior
    assert any(
        row["reason"] == "linked_runtime_entity_unresolved"
        and row["cards"] == [FIXTURE_CARD_ID]
        for row in behavior_report["suppressed"]
    )
    assert not any(
        row.get("mulligan") == FIXTURE_CARD_ID
        for row in mulligan["Mulligan"]["values"]
    )


def test_quarantined_claims_do_not_block_valid_load_safe_package(tmp_path):
    result = prepare_fixture_deck_with_source_claims(
        tmp_path,
        deck_name="NoBlockConflictDeck",
        claims=[
            {
                "claim_id": "keep_card",
                "claim_kind": "mulligan_keep",
                "card_id": "CARD_001",
                "evidence_text_short": "Keep the fixture card in the mulligan.",
                "source_confidence": "guide_backed",
            },
            {
                "claim_id": "discard_card",
                "claim_kind": "mulligan_discard",
                "card_id": "CARD_001",
                "evidence_text_short": "Discard the fixture card in the mulligan.",
                "source_confidence": "guide_backed",
            },
        ],
    )

    operator_summary = result["operator_summary"]
    source_contract_audit = result["source_contract_audit"]
    lifecycle_rows = source_contract_audit["claim_lifecycle_rows"]
    quarantined_rows = [
        row for row in lifecycle_rows if row.get("quarantine_status") == "quarantined"
    ]

    assert result["exit_code"] == 0
    assert_diagnostic_source_package_is_load_safe_but_apply_blocked(
        operator_summary
    )
    assert result["guide_claim_bundle"]["claim_conflict_report"]["conflict_count"] == 1
    assert {row["claim_kind"] for row in quarantined_rows} == {
        "mulligan_keep",
        "mulligan_discard",
    }
    assert all(
        row["builder_or_router_decision"] == "suppressed"
        and row["final_runtime_effect"] == "suppressed_quarantined_claim"
        and row["first_missing_link"] == "source_claim_conflict"
        and row["operator_impact"] == "diagnostic_only"
        for row in quarantined_rows
    )
    assert source_contract_audit["summary"]["claim_lifecycle_decision_counts"][
        "suppressed"
    ] >= len(quarantined_rows)
    assert not any(
        row.get("mulligan") == FIXTURE_CARD_ID
        for row in result["mulligan"]["Mulligan"]["values"]
    )


def test_quarantined_lowerable_card_role_never_reaches_physical_cardid(
    tmp_path,
):
    result = prepare_fixture_deck_with_source_claims(
        tmp_path,
        deck_name="NoCardIdConflictBypass",
        claims=[
            {
                "claim_id": "use_enemy_minion",
                "claim_kind": "card_role",
                "card_id": "CARD_001",
                "stance": "use_enemy_minion",
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
                "evidence_text_short": "Use this card against an enemy minion.",
                "source_confidence": "guide_backed",
            },
            {
                "claim_id": "do_not_target_enemy_minion",
                "claim_kind": "known_bad_pattern",
                "card_id": "CARD_001",
                "stance": "do_not_target_enemy_minion",
                "evidence_text_short": "Do not target an enemy minion with this card.",
                "source_confidence": "guide_backed",
            },
        ],
    )
    behavior_plan = json.loads(
        (
            result["package"]
            / "reports"
            / "card_behavior_plan_report.json"
        ).read_text(encoding="utf-8")
    )
    card_payload = json.loads(
        (result["deck_dir"] / f"{FIXTURE_CARD_ID}.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["exit_code"] == 0
    assert not any(
        row.get("claim_id") == "use_enemy_minion"
        for row in behavior_plan["rows"]
    )
    assert "BeforePlayCardBonus" not in card_payload
    suppression = next(
        row
        for row in behavior_plan["suppressed"]
        if row.get("claim_id") == "use_enemy_minion"
    )
    assert suppression["reason"] == "source_claim_conflict"
    assert suppression["source_claim_ids"]
    assert suppression["source_refs"]
    assert suppression["acquisition_provenance"]


def test_unsupported_future_report_only_and_runtime_evidence_claims_do_not_block(tmp_path):
    result = prepare_fixture_deck_with_source_claims(
        tmp_path,
        deck_name="NoBlockDiagnosticDeck",
        claims=[
            {
                "claim_id": "future_mechanic",
                "claim_kind": "mechanic_usage",
                "card_id": "CARD_777",
                "mechanic": "future_keyword",
                "evidence_text_short": "Future keyword support remains diagnostic.",
                "source_confidence": "unknown_future_mechanic",
            },
            {
                "claim_id": "report_only_role",
                "claim_kind": "card_role",
                "card_id": "CARD_001",
                "stance": "thin report-only role",
                "evidence_text_short": "Thin source role should not become runtime authority.",
                "source_confidence": "low",
            },
            {
                "claim_id": "numeric_runtime_evidence",
                "claim_kind": "globalvalue_numeric_tuning",
                "scope": "deck",
                "key": "LowHpBoardValuePenalty",
                "evidence_text_short": "Tune this numeric key only after runtime evidence.",
                "source_confidence": "guide_backed",
            },
            {
                "claim_id": "unsupported_future_claim",
                "claim_kind": "future_claim_kind",
                "card_id": "CARD_001",
                "evidence_text_short": "Unsupported future claim stays report-visible.",
                "source_confidence": "guide_backed",
            },
        ],
    )

    operator_summary = result["operator_summary"]
    source_contract_audit = result["source_contract_audit"]
    lifecycle_rows = source_contract_audit["claim_lifecycle_rows"]
    report_only_rows = [
        row for row in lifecycle_rows if row.get("runtime_eligibility") == "report_only"
    ]
    runtime_evidence_rows = [
        row
        for row in lifecycle_rows
        if row.get("policy_lane") == "runtime_evidence_required"
    ]
    unsupported_rows = [
        row
        for row in result["unsupported_claims_report"]
        if row.get("claim_kind") == "future_claim_kind"
    ]

    assert result["exit_code"] == 0
    assert_diagnostic_source_package_is_load_safe_but_apply_blocked(
        operator_summary
    )
    behavior_plan = json.loads(
        (
            result["package"]
            / "reports"
            / "card_behavior_plan_report.json"
        ).read_text(encoding="utf-8")
    )
    report_only_suppression = next(
        row
        for row in behavior_plan["suppressed"]
        if row.get("claim_id") == "report_only_role"
    )
    assert report_only_suppression["reason"] == "claim_not_runtime_lowerable"
    assert report_only_suppression["source_claim_ids"] == ["report_only_role"]
    assert report_only_suppression["source_refs"]
    assert report_only_suppression["acquisition_provenance"]
    assert source_contract_audit["summary"]["runtime_evidence_required_claims"] >= 1
    assert report_only_rows
    assert all(row["builder_or_router_decision"] != "emitted" for row in report_only_rows)
    assert runtime_evidence_rows
    assert any(
        row["builder_or_router_decision"] == "suppressed"
        and row["first_missing_link"] == "runtime_evidence"
        and row["operator_impact"] == "diagnostic_only"
        for row in runtime_evidence_rows
    )
    assert unsupported_rows
    assert all(row["reason"] == "unsupported_claim_kind" for row in unsupported_rows)
    assert any(
        row.get("key") == "LowHpBoardValuePenalty"
        for row in result["global_values_authority_matrix"][
            "blocked_until_runtime_evidence"
        ]
    )
    assert "future_keyword" in operator_summary["mechanic_drift_summary"][
        "unknown_mechanics"
    ]
    assert "future_keyword" in operator_summary["mechanic_visibility_summary"][
        "mechanics_by_bucket"
    ]["warning_only"]


def test_warning_bearing_future_mechanic_package_still_load_safe(tmp_path):
    result = prepare_fixture_deck_with_source_claims(
        tmp_path,
        deck_name="FutureMechanicNoBlock",
        claims=[
            {
                "claim_id": "future_keyword_visible",
                "claim_kind": "future_claim_kind",
                "claim_readiness": "contract_gap",
                "cards": ["CARD_777"],
                "mechanic": "future_keyword",
                "evidence_text_short": "Future keyword should be visible but not blocking.",
            },
            {
                "claim_id": "runtime_only_globalvalue_visible",
                "claim_kind": "globalvalue_numeric_tuning",
                "claim_readiness": "guide_backed",
                "source_confidence": "guide_backed",
                "scope": "deck",
                "key": "FirstTurnValueWeight",
                "runtime_value": 1.3,
                "evidence_text_short": "Runtime value request requires post-game evidence.",
            },
        ],
    )
    assert result["exit_code"] == 0
    operator_summary = result["operator_summary"]

    assert_diagnostic_source_package_is_load_safe_but_apply_blocked(
        operator_summary
    )
    assert operator_summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert operator_summary["no_block_failure_mode_summary"]["hard_block"] is False
    assert any(
        warning.get("key") == "FirstTurnValueWeight"
        and warning.get("reason") == "globalvalue_runtime_evidence_required"
        for warning in operator_summary["warnings"]
    )
    assert any(
        row["key"] == "FirstTurnValueWeight"
        and row["reason"] == "requires_runtime_evidence"
        for row in result["global_values_authority_matrix"][
            "blocked_until_runtime_evidence"
        ]
    )
    global_values = json.loads(
        (result["deck_dir"] / "GlobalValues.json").read_text(encoding="utf-8")
    )
    assert global_values["FirstTurnValueWeight"]["values"] == [
        {"condition": "*", "value": "0"}
    ]
