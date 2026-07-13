import json
from pathlib import Path

import pytest

from hsconfig.cli import main


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


def _stub_empty_card_fetches(monkeypatch) -> None:
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )


def prepare_fixture_deck_with_source_claim(tmp_path: Path, *, deck_name: str, claim: dict):
    cards = tmp_path / "cards.json"
    cards.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "CARD_001",
                        "dbf_id": 1,
                        "count": 30,
                        "name": "Fixture Card",
                        "text": "Future mechanic: fixture card text.",
                        "mechanics": ["FUTURE_MECHANIC"],
                    }
                ]
            }
        ),
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
                    "claims": [claim],
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
            "fixture-code",
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
    semantic_report = json.loads(
        (out / "reports" / "semantic_enrichment_report.json").read_text(encoding="utf-8")
    )
    deck_identity = json.loads((out / "reports" / "deck_identity.json").read_text(encoding="utf-8"))

    deck_dirs = [path for path in (out / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    deck_dir = deck_dirs[0]
    special_files = {"Combo.json", "GlobalValues.json", "Mulligan.json"}
    card_files = {
        path.stem
        for path in deck_dir.glob("*.json")
        if path.name not in special_files
    }
    deck_card_ids = {str(card["card_id"]) for card in deck_identity["cards"]}

    assert code == 0
    assert payload["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
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
    assert source_contract_audit["summary"]["cards_total"] == len(deck_card_ids)
    assert operator["mechanic_visibility_summary"]["non_blocking"] is True
    assert operator["semantic_enrichment_summary"]["non_blocking"] is True
    assert operator["next_action"] in {"READY_TO_APPLY_OR_HANDOFF", "READY_TO_APPLY_WITH_WARNINGS"}
    assert semantic_report["non_blocking"] is True
    assert "summary" in semantic_report
    assert "cards" in semantic_report
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert card_files == deck_card_ids
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()


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

        operator = json.loads(
            (out / "04_package" / "reports" / "operator_summary.json").read_text(
                encoding="utf-8"
            )
        )
        source_contract_audit = json.loads(
            (out / "04_package" / "reports" / "source_contract_audit.json").read_text(
                encoding="utf-8"
            )
        )
        assert operator["technical_status"] == "VALID_PACKAGE"
        assert operator["runtime_load_safe"] is True
        assert operator["runtime_apply_mode"] == "load_safe_apply"
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
    assert operator_summary["runtime_apply_allowed"] is True
    assert operator_summary["runtime_apply_mode"] == "load_safe_apply"
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
    card_behavior = json.loads((deck_dir / "CARD_001.json").read_text(encoding="utf-8"))
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    claim = result["guide_claim_bundle"]["claims"][0]
    operator_summary = result["operator_summary"]

    assert result["exit_code"] == 0
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["runtime_apply_allowed"] is True
    assert claim["semantic_qualifiers"]["state_requirements"] == ["all_shadow_spells"]
    assert card_behavior["BeforeUseHeroPowerBonus"]["values"]
    assert not any(row.get("mulligan") == "CARD_001" for row in mulligan["Mulligan"]["values"])
