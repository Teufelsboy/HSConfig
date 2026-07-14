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
    deck_dir = next((out / "CustomConfig").iterdir())
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    source_gap = json.loads((reports / "source_claim_gap_report.json").read_text(encoding="utf-8"))

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
