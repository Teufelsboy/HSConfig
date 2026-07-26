import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from tests.helpers.fixture_prepare import load_archetype_matrix


SOURCE_CLAIM_FIELDS = {
    "card_id",
    "claim_id",
    "claim_kind",
    "evidence_text_short",
    "mechanic",
    "semantic_qualifiers",
    "source_confidence",
}

ALLOWED_EXPECTED_RUNTIME_SURFACE_STATUSES = {
    "source_backed",
    "policy_backed",
    "static_semantics_backed",
    "not_expected",
    "suppressed_with_reason",
    "explicit_gap",
    "default_only",
}


def test_profile_strong_rows_do_not_have_default_only_surfaces():
    for deck in load_archetype_matrix():
        if deck.get("expected_semantic_status") == "SOURCE_BACKED_STRONG":
            assert deck.get("default_only_runtime_surfaces") == []
            assert deck.get("closure_profile_first_missing_link") == "none"


SEMANTIC_ARCHETYPE_FIXTURES = [
    {
        "deck_name": "SyntheticSecretHunter",
        "cards": [
            {"card_id": "SECRET_001", "name": "Secret Opener", "cost": 1, "type": "SPELL", "text": "Secret: fixture.", "mechanics": ["SECRET"]},
            {"card_id": "TEMPO_001", "name": "Tempo One", "cost": 1, "type": "MINION", "text": "Battlecry: deal damage.", "mechanics": ["BATTLECRY"]},
        ],
        "claims": [
            {"claim_id": "claim_63d125d89e8e", "claim_kind": "mulligan_keep", "card_id": "TEMPO_001", "evidence_text_short": "Keep early pressure.", "source_confidence": "guide_backed"},
            {
                "claim_id": "claim_db9a1c18eb5a",
                "claim_kind": "mechanic_usage",
                "card_id": "SECRET_001",
                "mechanic": "secret",
                "evidence_text_short": "Secrets are part of the gameplan.",
                "source_confidence": "guide_backed",
            },
        ],
        "runtime_expectations": {
            "SECRET_001": {
                "claim_db9a1c18eb5a": {
                    "runtime_block": "BeforePlayCardBonus",
                    "condition": "*",
                    "value": "6",
                    "comment": "SyntheticSecretHunter: SECRET_001_use_secret_according_to_card_text",
                }
            }
        },
    },
    {
        "deck_name": "SyntheticLocationDruid",
        "cards": [
            {"card_id": "LOCATION_001", "name": "Location Fixture", "cost": 2, "type": "LOCATION", "text": "Summon two minions."},
            {"card_id": "BOARD_001", "name": "Board One", "cost": 1, "type": "MINION", "text": "Summon a Treant."},
        ],
        "claims": [
            {"claim_id": "claim_fbd07c663bf4", "claim_kind": "mulligan_keep", "card_id": "BOARD_001", "evidence_text_short": "Keep board opener.", "source_confidence": "guide_backed"},
            {
                "claim_id": "claim_325924175cfb",
                "claim_kind": "mechanic_usage",
                "card_id": "LOCATION_001",
                "mechanic": "location",
                "evidence_text_short": "Location supports board plan.",
                "source_confidence": "guide_backed",
            },
        ],
        "runtime_expectations": {
            "LOCATION_001": {
                "claim_325924175cfb": {
                    "runtime_block": "BeforePlayCardBonus",
                    "condition": "*",
                    "value": "8",
                    "comment": "SyntheticLocationDruid: LOCATION_001_use_location_according_to_card_text",
                    "semantic_reason": "location_tempo",
                }
            }
        },
    },
    {
        "deck_name": "SyntheticDiscoverMage",
        "cards": [
            {"card_id": "DISCOVER_001", "name": "Discover One", "cost": 2, "type": "SPELL", "text": "Discover a spell."},
            {"card_id": "BURN_001", "name": "Burn One", "cost": 1, "type": "SPELL", "text": "Deal damage."},
        ],
        "claims": [
            {"claim_id": "claim_aafc09aad784", "claim_kind": "mulligan_keep", "card_id": "BURN_001", "evidence_text_short": "Keep cheap burn.", "source_confidence": "guide_backed"},
            {"claim_id": "claim_2ba9a2be2581", "claim_kind": "discover_choice", "card_id": "DISCOVER_001", "evidence_text_short": "Prefer damage from Discover.", "source_confidence": "guide_backed"},
        ],
    },
    {
        "deck_name": "SyntheticHighlanderPriest",
        "cards": [
            {"card_id": "HIGHLANDER_001", "name": "Highlander Effect", "cost": 5, "type": "MINION", "text": "Start of Game: if your deck has no duplicates, improve your hero power."},
            {"card_id": "LOW_CURVE_001", "name": "Low Curve One", "cost": 1, "type": "MINION", "text": "Battlecry: deal damage."},
        ],
        "claims": [
            {"claim_id": "claim_f4040dfcd9af", "claim_kind": "hero_power_transform", "card_id": "HIGHLANDER_001", "semantic_qualifiers": {"timing": "start_of_game", "zone_scope": "deck"}, "evidence_text_short": "The deckbuilding effect matters.", "source_confidence": "guide_backed"},
            {"claim_id": "claim_377b7a739f09", "claim_kind": "mulligan_keep", "card_id": "LOW_CURVE_001", "evidence_text_short": "Keep the low curve opener.", "source_confidence": "guide_backed"},
        ],
    },
]


def _runtime_card_files(deck_dir: Path) -> dict[str, dict]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in deck_dir.glob("*.json")
        if path.name not in {"Combo.json", "GlobalValues.json", "Mulligan.json"}
    }


def _source_claims(fixture: dict) -> list[dict]:
    return [
        {
            field: claim[field]
            for field in SOURCE_CLAIM_FIELDS
            if field in claim
        }
        for claim in fixture["claims"]
    ]


def _runtime_config_surface_files(deck_dir: Path) -> set[str]:
    return {path.name for path in deck_dir.glob("*.json")}


def _claim_lifecycle_rows_for_card(
    fixture: dict, card_id: str, claim_id: str, source_gap: dict, source_audit: dict
) -> list[dict]:
    source_claim_ids = set(source_gap["card_rows"][card_id].get("source_claim_ids", []))
    fixture_claim = next(
        claim
        for claim in fixture["claims"]
        if claim["card_id"] == card_id and claim["claim_id"] == claim_id
    )
    assert fixture_claim["claim_id"] in source_claim_ids
    return [
        row
        for row in source_audit["claim_lifecycle_rows"]
        if row["claim_id"] == fixture_claim["claim_id"]
    ]


def _assert_semantic_claim_routing(fixture: dict, deck_dir: Path, reports: Path) -> None:
    source_gap = json.loads(
        (reports / "source_claim_gap_report.json").read_text(encoding="utf-8")
    )
    source_audit = json.loads(
        (reports / "source_contract_audit.json").read_text(encoding="utf-8")
    )
    gameplan_contract = json.loads(
        (reports / "gameplan_contract.json").read_text(encoding="utf-8")
    )
    runtime_cards = _runtime_card_files(deck_dir)
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    hold_ids = {
        row["mulligan"]
        for row in mulligan["Mulligan"]["values"]
        if row.get("value") == "hold"
    }

    fixture_card_ids = {card["card_id"] for card in fixture["cards"]}
    assert set(source_gap["card_rows"]) == fixture_card_ids
    assert set(runtime_cards) == fixture_card_ids
    assert set(gameplan_contract["cards"]) == fixture_card_ids
    for card_id, card_file in runtime_cards.items():
        assert card_file["GameCardId"] == card_id
        assert card_id in gameplan_contract["cards"]

    effect_only_ids = {
        claim["card_id"]
        for claim in fixture["claims"]
        if claim["claim_kind"] == "hero_power_transform"
        and claim.get("semantic_qualifiers", {}).get("timing") == "start_of_game"
    }
    assert not hold_ids & effect_only_ids

    for claim in fixture["claims"]:
        card_id = claim["card_id"]
        claim_id = claim["claim_id"]
        card_row = source_gap["card_rows"][card_id]
        lifecycle_rows = _claim_lifecycle_rows_for_card(
            fixture, card_id, claim_id, source_gap, source_audit
        )
        assert card_row["source_claim_ids"]
        assert lifecycle_rows, f"no lifecycle provenance for {claim_id}"
        assert all(row["claim_id"] == claim_id for row in lifecycle_rows)
        assert all(row["claim_kind"] == claim["claim_kind"] for row in lifecycle_rows)
        assert claim_id in gameplan_contract["cards"][card_id]["source_claim_ids"]
        assert any(
            source_claim["claim_id"] == claim_id
            for source_claim in gameplan_contract["source_claims"]
        )

        if claim["claim_kind"] == "mulligan_keep":
            matching_rules = [
                rule
                for rule in gameplan_contract["mulligan_plan"]["rules"]
                if rule.get("card") == card_id
                and rule.get("action") == "hold"
                and (
                    rule.get("claim_id") == claim_id
                    or claim_id in rule.get("source_claim_ids", [])
                )
            ]
            lifecycle_emitted = any(
                row["builder_or_router_decision"] == "emitted"
                and "Mulligan.json" in row["emitted_files"]
                and row["final_runtime_effect"] == "emitted_runtime_row"
                for row in lifecycle_rows
            )
            if lifecycle_emitted:
                assert matching_rules, f"no generated Mulligan rule for {claim_id}"
            else:
                assert matching_rules == []
                assert all(
                    row["final_runtime_effect"] != "emitted_runtime_row"
                    for row in lifecycle_rows
                )
        elif claim["claim_kind"] == "mechanic_usage":
            assert any(
                f"{card_id}.json" in row["emitted_files"]
                and row["builder_or_router_decision"] == "emitted"
                and row["final_runtime_effect"] == "emitted_runtime_row"
                for row in lifecycle_rows
            )
            behavior_rows = gameplan_contract["card_behavior_plan"]["card_rows"][card_id]
            assert any(
                row.get("claim_id") == claim_id
                and claim_id in row.get("source_claim_ids", [])
                for row in behavior_rows
            )
            expected_runtime = fixture["runtime_expectations"][card_id][claim_id]
            if expected_runtime.get("semantic_reason"):
                matching_behavior_rows = [
                    row for row in behavior_rows if row.get("claim_id") == claim_id
                ]
                assert matching_behavior_rows
                assert {
                    row["semantic_score"]["reason"]
                    for row in matching_behavior_rows
                    if row.get("semantic_score")
                } == {expected_runtime["semantic_reason"]}
            runtime_block = expected_runtime["runtime_block"]
            assert runtime_block in runtime_cards[card_id]
            runtime_values = runtime_cards[card_id][runtime_block]["values"]
            expected_row = {
                "condition": expected_runtime["condition"],
                "value": expected_runtime["value"],
                "comment": expected_runtime["comment"],
            }
            matching_runtime_rows = [
                row
                for row in runtime_values
                if row.get("condition") == expected_row["condition"]
                and row.get("value") == expected_row["value"]
                and (
                    "comment" not in expected_row
                    or row.get("comment") == expected_row["comment"]
                )
            ]
            assert matching_runtime_rows, (
                f"{claim['mechanic']} claim lacks its expected runtime payload: "
                f"{expected_row!r}; got {runtime_values!r}"
            )
        elif claim["claim_kind"] == "discover_choice":
            runtime_config_surfaces = _runtime_config_surface_files(deck_dir)
            assert all(
                not set(row["emitted_files"]) & runtime_config_surfaces
                for row in lifecycle_rows
            )
            assert all(
                row["final_runtime_effect"] != "emitted_runtime_row"
                for row in lifecycle_rows
            )
            discover_is_unsupported = any(
                item["claim_id"] == claim_id
                for item in gameplan_contract["unsupported_or_review_only_claims"]
            )
            discover_has_audit_route = any(
                row["claim_id"] == claim_id
                and row["final_runtime_effect"] != "emitted_runtime_row"
                for row in lifecycle_rows
            )
            assert discover_is_unsupported or discover_has_audit_route
            assert set(runtime_cards[card_id]) <= {"GameCardId", "ConfigComment"}
            assert "OnChooseOneCardBonus" not in runtime_cards[card_id]
        elif claim["claim_kind"] == "hero_power_transform":
            assert any(
                f"{card_id}.json" in row["emitted_files"]
                and row["final_runtime_effect"] == "emitted_runtime_row"
                for row in lifecycle_rows
            )
            assert any(
                row.get("claim_id") == claim_id
                and claim_id in row.get("source_claim_ids", [])
                for row in gameplan_contract["card_behavior_plan"]["card_rows"][card_id]
            )
            assert "BeforeUseHeroPowerBonus" in runtime_cards[card_id]
            assert card_id not in hold_ids


def _write_fixture(tmp_path: Path, fixture: dict) -> tuple[Path, Path]:
    cards_path = tmp_path / f"{fixture['deck_name']}_cards.json"
    cards_path.write_text(json.dumps({"cards": fixture["cards"]}), encoding="utf-8")
    sources_path = tmp_path / f"{fixture['deck_name']}_sources.json"
    sources_path.write_text(
        json.dumps(
            [
                {
                    "source_url": f"https://example.invalid/{fixture['deck_name']}",
                    "source_title": f"{fixture['deck_name']} Guide Fixture",
                    "source_family": "guide_fixture",
                    "retrieved_at": "2026-07-14T00:00:00Z",
                    "claims": _source_claims(fixture),
                }
            ]
        ),
        encoding="utf-8",
    )
    return cards_path, sources_path


def _prepare_semantic_fixture(tmp_path: Path, fixture: dict) -> dict:
    cards_path, sources_path = _write_fixture(tmp_path, fixture)
    out = tmp_path / fixture["deck_name"]
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            fixture["deck_name"],
            "--deck-code",
            "synthetic-fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_path),
            "--guide-sources-json",
            str(sources_path),
            "--json",
        ]
    )
    reports = out / "reports"
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    return {"exit_code": exit_code, "out": out, "reports": reports, "operator": operator}


def _expected_surface_status(surface: str, ledger_row: dict, usefulness: dict) -> str:
    status = ledger_row["status"]
    if status in ALLOWED_EXPECTED_RUNTIME_SURFACE_STATUSES:
        return status
    surface_row = usefulness.get("surfaces", {}).get(surface, {})
    if surface_row.get("status") == "not_expected":
        return "not_expected"
    if status == "warning_only":
        return "explicit_gap"
    return status


def build_no_default_only_matrix(tmp_path: Path) -> list[dict]:
    rows = []
    for fixture in SEMANTIC_ARCHETYPE_FIXTURES:
        prepared = _prepare_semantic_fixture(tmp_path, fixture)
        operator = prepared["operator"]
        usefulness = operator["config_usefulness"]
        for ledger_row in operator["surface_status_ledger"]:
            rows.append(
                {
                    "deck_name": fixture["deck_name"],
                    "surface": ledger_row["surface"],
                    "technical_status": operator["technical_status"],
                    "expected_runtime_surface_status": _expected_surface_status(
                        ledger_row["surface"],
                        ledger_row,
                        usefulness,
                    ),
                    "silent_default_only": (
                        ledger_row["default_only"] is True
                        and ledger_row["apply_blocking"] is False
                        and not ledger_row.get("first_missing_link")
                    ),
                }
            )
    return rows


def test_representative_matrix_has_no_silent_default_only_surfaces(tmp_path):
    rows = build_no_default_only_matrix(tmp_path)
    assert rows
    for row in rows:
        assert row["technical_status"] == "VALID_PACKAGE", row
        assert (
            row["expected_runtime_surface_status"]
            in ALLOWED_EXPECTED_RUNTIME_SURFACE_STATUSES
        ), row
        assert row.get("silent_default_only") is False, row


@pytest.mark.parametrize("fixture", SEMANTIC_ARCHETYPE_FIXTURES, ids=lambda item: item["deck_name"])
def test_semantic_archetype_fixture_remains_load_safe_and_not_default_only(tmp_path, fixture):
    prepared = _prepare_semantic_fixture(tmp_path, fixture)
    out = prepared["out"]
    reports = prepared["reports"]
    operator = prepared["operator"]
    assert prepared["exit_code"] == 0

    deck_dirs = [path for path in (out / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    deck_dir = deck_dirs[0]
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    source_gap = json.loads((reports / "source_claim_gap_report.json").read_text(encoding="utf-8"))
    source_audit = json.loads((reports / "source_contract_audit.json").read_text(encoding="utf-8"))
    global_values = json.loads((deck_dir / "GlobalValues.json").read_text(encoding="utf-8"))
    global_values_profile = json.loads(
        (reports / "global_values_key_profile_report.json").read_text(encoding="utf-8")
    )

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_allowed"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert all(
        row["status"] != "default_only" or row["surface"] == "mulligan"
        for row in operator["surface_status_ledger"]
    )
    assert all(
        row["apply_blocking"] is False
        for row in operator["surface_status_ledger"]
    )
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert not (deck_dir / "Combo.json").exists()
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
    mulligan_surface = next(
        row for row in operator["surface_status_ledger"] if row["surface"] == "mulligan"
    )
    if mulligan_surface["status"] == "default_only":
        assert mulligan["Mulligan"]["values"] == []
    else:
        assert mulligan["Mulligan"]["values"]
    assert global_values_profile["key_count"] == len(global_values)
    assert set(global_values_profile["keys"]) == set(global_values)
    assert global_values_profile["key_count"] == len(global_values_profile["keys"])
    for key, profile in global_values_profile["keys"].items():
        assert {
            "category",
            "authority_category",
            "board_value_component",
            "decision",
            "status",
            "reason",
        } <= set(profile)
        if profile["category"] != "metadata":
            assert "baseline_value" in profile
    assert "card_rows" in source_gap
    assert "claim_lifecycle_rows" in source_audit
    _assert_semantic_claim_routing(fixture, deck_dir, reports)
