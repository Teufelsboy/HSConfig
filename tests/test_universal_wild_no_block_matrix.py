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
        assert operator["technical_status"] == "VALID_PACKAGE"
        assert operator["runtime_load_safe"] is True
        assert operator["runtime_apply_mode"] == "load_safe_apply"
        assert operator["mechanic_visibility_summary"]["non_blocking"] is True
