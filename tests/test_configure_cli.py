from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cards_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "BAR_735",
                        "dbf_id": 1,
                        "count": 1,
                        "name": "Darkbishop Benedictus",
                        "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _write_source_evidence_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "evidence_rows": [
                    {
                        "source_url": "https://example.invalid/shadow-priest",
                        "source_title": "Shadow Priest Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T12:00:00Z",
                        "claim_kind": "hero_power_transform",
                        "card_mentions": ["Darkbishop Benedictus"],
                        "stance": "enable_transformed_hero_power",
                        "evidence_text_short": "Shadow Priest wants the transformed hero power.",
                        "source_confidence": "high",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_configure_builds_valid_load_safe_package_without_source_evidence(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )

    out = tmp_path / "configure"
    runtime_root = tmp_path / "runtime"

    assert main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--json",
        ]
    ) == 0

    package = out / "04_package"
    operator = _read_json(package / "reports" / "operator_summary.json")
    summary = _read_json(out / "configure_summary.json")

    assert summary["status"] == "OK"
    assert summary["package_path"] == str(package)
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert (package / "CustomConfig").exists()
    assert list(package.glob("CustomConfig/*/GlobalValues.json"))
    assert list(package.glob("CustomConfig/*/Mulligan.json"))


def test_configure_source_evidence_is_not_reingested_after_drafting(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    cards_json = tmp_path / "cards.json"
    source_evidence_json = tmp_path / "source_evidence.json"
    _write_cards_json(cards_json)
    _write_source_evidence_json(source_evidence_json)
    out = tmp_path / "configure"

    code = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--source-evidence-json",
            str(source_evidence_json),
            "--json",
        ]
    )

    guide_sources = _read_json(out / "03_research" / "guide_sources.json")
    guide_builder_receipt = _read_json(out / "03_research" / "guide_builder_receipt.json")

    assert code == 0
    assert guide_sources["summary"]["source_count"] == 1
    assert len(guide_sources["sources"]) == 1
    assert guide_builder_receipt["source_count"] == 1


def test_configure_malformed_deck_code_writes_failure_summary_without_package(
    tmp_path: Path,
    capsys,
):
    out = tmp_path / "configure"
    runtime_root = tmp_path / "runtime"

    code = main(
        [
            "configure",
            "--deck-name",
            "MalformedDeck",
            "--deck-code",
            "not-a-deck-code",
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    summary = _read_json(out / "configure_summary.json")

    assert code == 1
    assert payload["status"] == "failed"
    assert payload["stage"] == "source-manifest"
    assert payload["errors"]
    assert summary == payload
    assert not (out / "04_package" / "CustomConfig").exists()
    assert not (runtime_root / "CustomConfig").exists()


def test_configure_apply_uses_existing_apply_command_gate(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json)
    out = tmp_path / "configure"
    runtime_root = tmp_path / "runtime"
    captured = {}

    def fake_run_apply_command(args):
        captured["package"] = args.package
        captured["runtime_root"] = args.runtime_root
        captured["allow_source_informed"] = args.allow_source_informed
        captured["fake"] = args.fake
        captured["from_fake_receipt"] = args.from_fake_receipt
        captured["json"] = args.json
        return 0

    monkeypatch.setattr("hsconfig.commands.configure.run_apply_command", fake_run_apply_command)

    code = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--apply",
            "--json",
        ]
    )

    summary = _read_json(out / "configure_summary.json")

    assert code == 0
    assert summary["apply_performed"] is True
    assert summary["apply_status"] == 0
    assert captured == {
        "package": str(out / "04_package"),
        "runtime_root": str(runtime_root),
        "allow_source_informed": False,
        "fake": False,
        "from_fake_receipt": None,
        "json": True,
    }
