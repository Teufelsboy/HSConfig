import json
from pathlib import Path

import pytest

from hsconfig.cli import main


SEMANTIC_ARCHETYPE_FIXTURES = [
    {
        "deck_name": "SyntheticSecretHunter",
        "cards": [
            {"card_id": "SECRET_001", "name": "Secret Opener", "cost": 1, "type": "SPELL", "text": "Secret: fixture.", "mechanics": ["SECRET"]},
            {"card_id": "TEMPO_001", "name": "Tempo One", "cost": 1, "type": "MINION", "text": "Battlecry: deal damage.", "mechanics": ["BATTLECRY"]},
        ],
        "claims": [
            {"claim_id": "tempo_keep", "claim_kind": "mulligan_keep", "card_id": "TEMPO_001", "evidence_text_short": "Keep early pressure.", "source_confidence": "guide_backed"},
            {"claim_id": "secret_visible", "claim_kind": "mechanic_usage", "card_id": "SECRET_001", "mechanic": "secret", "evidence_text_short": "Secrets are part of the gameplan.", "source_confidence": "guide_backed"},
        ],
    },
    {
        "deck_name": "SyntheticLocationDruid",
        "cards": [
            {"card_id": "LOCATION_001", "name": "Location Fixture", "cost": 2, "type": "LOCATION", "text": "Summon two minions."},
            {"card_id": "BOARD_001", "name": "Board One", "cost": 1, "type": "MINION", "text": "Summon a Treant."},
        ],
        "claims": [
            {"claim_id": "board_keep", "claim_kind": "mulligan_keep", "card_id": "BOARD_001", "evidence_text_short": "Keep board opener.", "source_confidence": "guide_backed"},
            {"claim_id": "location_visible", "claim_kind": "mechanic_usage", "card_id": "LOCATION_001", "mechanic": "location", "evidence_text_short": "Location supports board plan.", "source_confidence": "guide_backed"},
        ],
    },
    {
        "deck_name": "SyntheticDiscoverMage",
        "cards": [
            {"card_id": "DISCOVER_001", "name": "Discover One", "cost": 2, "type": "SPELL", "text": "Discover a spell."},
            {"card_id": "BURN_001", "name": "Burn One", "cost": 1, "type": "SPELL", "text": "Deal damage."},
        ],
        "claims": [
            {"claim_id": "burn_keep", "claim_kind": "mulligan_keep", "card_id": "BURN_001", "evidence_text_short": "Keep cheap burn.", "source_confidence": "guide_backed"},
            {"claim_id": "discover_report_only", "claim_kind": "discover_choice", "card_id": "DISCOVER_001", "evidence_text_short": "Prefer damage from Discover.", "source_confidence": "guide_backed"},
        ],
    },
    {
        "deck_name": "SyntheticHighlanderPriest",
        "cards": [
            {"card_id": "HIGHLANDER_001", "name": "Highlander Effect", "cost": 5, "type": "MINION", "text": "Start of Game: if your deck has no duplicates, improve your hero power."},
            {"card_id": "LOW_CURVE_001", "name": "Low Curve One", "cost": 1, "type": "MINION", "text": "Battlecry: deal damage."},
        ],
        "claims": [
            {"claim_id": "highlander_effect", "claim_kind": "hero_power_transform", "card_id": "HIGHLANDER_001", "semantic_qualifiers": {"timing": "start_of_game", "zone_scope": "deck"}, "evidence_text_short": "The deckbuilding effect matters.", "source_confidence": "guide_backed"},
            {"claim_id": "curve_keep", "claim_kind": "mulligan_keep", "card_id": "LOW_CURVE_001", "evidence_text_short": "Keep the low curve opener.", "source_confidence": "guide_backed"},
        ],
    },
]


def _runtime_card_files(deck_dir: Path) -> dict[str, dict]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in deck_dir.glob("*.json")
        if path.name not in {"GlobalValues.json", "Mulligan.json"}
    }


def _claim_lifecycle_rows_for_card(
    fixture: dict, card_id: str, source_gap: dict, source_audit: dict
) -> list[dict]:
    source_claim_ids = set(source_gap["card_rows"][card_id].get("source_claim_ids", []))
    expected_kinds = {
        claim["claim_kind"]
        for claim in fixture["claims"]
        if claim["card_id"] == card_id
    }
    return [
        row
        for row in source_audit["claim_lifecycle_rows"]
        if row["claim_id"] in source_claim_ids and row["claim_kind"] in expected_kinds
    ]


def _assert_semantic_claim_routing(fixture: dict, deck_dir: Path, reports: Path) -> None:
    source_gap = json.loads(
        (reports / "source_claim_gap_report.json").read_text(encoding="utf-8")
    )
    source_audit = json.loads(
        (reports / "source_contract_audit.json").read_text(encoding="utf-8")
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
    for card_id, card_file in runtime_cards.items():
        assert card_file["GameCardId"] == card_id

    expected_keep_ids = {
        claim["card_id"]
        for claim in fixture["claims"]
        if claim["claim_kind"] == "mulligan_keep"
    }
    effect_only_ids = {
        claim["card_id"]
        for claim in fixture["claims"]
        if claim["claim_kind"] == "hero_power_transform"
        and claim.get("semantic_qualifiers", {}).get("timing") == "start_of_game"
    }
    assert hold_ids == expected_keep_ids
    assert not hold_ids & effect_only_ids

    for claim in fixture["claims"]:
        card_id = claim["card_id"]
        card_row = source_gap["card_rows"][card_id]
        lifecycle_rows = _claim_lifecycle_rows_for_card(
            fixture, card_id, source_gap, source_audit
        )
        assert card_row["source_claim_ids"]
        assert lifecycle_rows, f"no lifecycle provenance for {claim['claim_id']}"
        matching_rows = [
            row for row in lifecycle_rows if row["claim_kind"] == claim["claim_kind"]
        ]
        assert matching_rows, f"claim kind was not preserved for {claim['claim_id']}"

        if claim["claim_kind"] == "mechanic_usage":
            assert any(
                f"{card_id}.json" in row["emitted_files"]
                and row["builder_or_router_decision"] == "emitted"
                for row in matching_rows
            )
            assert runtime_cards[card_id].keys() - {"ConfigComment", "GameCardId"}
        elif claim["claim_kind"] == "discover_choice":
            assert all(not row["emitted_files"] for row in matching_rows)
            assert all(
                row["final_runtime_effect"] != "emitted_runtime_row"
                for row in matching_rows
            )
            assert not any(
                "OnChooseOneCardBonus" in runtime_cards[card_id]
                for _ in matching_rows
            )
        elif claim["claim_kind"] == "hero_power_transform":
            assert any(
                f"{card_id}.json" in row["emitted_files"]
                for row in matching_rows
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
                    "claims": fixture["claims"],
                }
            ]
        ),
        encoding="utf-8",
    )
    return cards_path, sources_path


@pytest.mark.parametrize("fixture", SEMANTIC_ARCHETYPE_FIXTURES, ids=lambda item: item["deck_name"])
def test_semantic_archetype_fixture_remains_load_safe_and_not_default_only(tmp_path, fixture):
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
    deck_dirs = [path for path in (out / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    deck_dir = deck_dirs[0]
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    source_gap = json.loads((reports / "source_claim_gap_report.json").read_text(encoding="utf-8"))
    source_audit = json.loads((reports / "source_contract_audit.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_allowed"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["mulligan_policy_status"]["default_only"] is False
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
    assert mulligan["Mulligan"]["values"], "Mulligan output must not be default-only for representative archetypes"
    assert "card_rows" in source_gap
    assert "claim_lifecycle_rows" in source_audit
    _assert_semantic_claim_routing(fixture, deck_dir, reports)
