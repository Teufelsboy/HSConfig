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


def _stub_empty_card_fetches(monkeypatch) -> None:
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )


def _write_intake_cards_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "HSC_INTAKE_001",
                        "dbf_id": 91001,
                        "count": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_configure_fetches_card_data_and_writes_intake_counts(tmp_path: Path, monkeypatch):
    source_fetches = {"collectible": [], "full": []}

    def fake_collectible_cards(timeout=10.0):
        source_fetches["collectible"].append(timeout)
        return [
            {
                "id": "HSC_INTAKE_001",
                "dbf_id": 91001,
                "name": "Recognizable Deck Card",
                "type": "MINION",
                "text": "Creates a recognizable helper.",
                "child_ids": ["HSC_INTAKE_TOKEN"],
                "mechanics": [],
                "referenced_tags": [],
            }
        ]

    def fake_full_cards(timeout=10.0):
        source_fetches["full"].append(timeout)
        return [
            {
                "id": "HSC_INTAKE_TOKEN",
                "dbf_id": 91002,
                "name": "Recognizable Companion",
                "type": "MINION",
                "text": "Companion from the full feed.",
                "mechanics": [],
                "referenced_tags": [],
            }
        ]

    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_cards", fake_full_cards)
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        fake_collectible_cards,
    )

    out = tmp_path / "configure"
    cards_json = tmp_path / "cards.json"
    _write_intake_cards_json(cards_json)

    assert main(
        [
            "configure",
            "--deck-name",
            "IntakeDeck",
            "--deck-code",
            "fixture-code",
            "--cards-json",
            str(cards_json),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    ) == 0

    report = _read_json(out / "03_research" / "card_data_intake_report.json")
    assert source_fetches == {"collectible": [10.0], "full": [10.0]}
    assert report["non_blocking"] is True
    assert report["summary"]["deck_cards"] == 1
    assert report["summary"]["matched_deck_cards"] == 1
    assert report["summary"]["missing_deck_cards"] == 0
    assert report["summary"]["companion_records"] == 1
    assert report["summary"]["missing_companion_records"] == 0


def test_configure_json_outputs_single_parseable_payload(tmp_path: Path, monkeypatch, capsys):
    _stub_empty_card_fetches(monkeypatch)

    out = tmp_path / "configure"

    assert main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "OK"
    assert payload["manifest_path"] == str(out / "01_manifest" / "source_research_manifest.json")
    assert payload["research_path"] == str(out / "03_research")
    assert payload["package_path"] == str(out / "04_package")
    assert payload["apply_performed"] is False


def test_configure_uses_local_card_feed_files_without_fetching(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    def fail_fetch(timeout=10.0):
        raise AssertionError("configure should use supplied local card feeds")

    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", fail_fetch)
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_cards", fail_fetch)
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        fail_fetch,
    )

    cards_json = tmp_path / "cards.json"
    _write_intake_cards_json(cards_json)
    collectible_cards_json = tmp_path / "collectible_cards.json"
    collectible_cards_json.write_text(
        json.dumps(
            [
                {
                    "id": "HSC_INTAKE_001",
                    "dbf_id": 91001,
                    "name": "Recognizable Deck Card",
                    "type": "MINION",
                    "text": "Creates a recognizable helper.",
                    "child_ids": ["HSC_INTAKE_TOKEN"],
                }
            ]
        ),
        encoding="utf-8",
    )
    full_cards_json = tmp_path / "full_cards.json"
    full_cards_json.write_text(
        json.dumps(
            {"cards": [{"id": "HSC_INTAKE_TOKEN", "name": "Recognizable Companion"}]}
        ),
        encoding="utf-8",
    )
    out = tmp_path / "configure"

    assert main(
        [
            "configure",
            "--deck-name",
            "IntakeDeck",
            "--deck-code",
            "fixture-code",
            "--cards-json",
            str(cards_json),
            "--collectible-cards-json",
            str(collectible_cards_json),
            "--full-cards-json",
            str(full_cards_json),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    report = _read_json(out / "03_research" / "card_data_intake_report.json")
    research_identity = _read_json(out / "03_research" / "identity_graph_report.json")
    package_identity = _read_json(out / "04_package" / "reports" / "identity_graph_report.json")

    assert payload["status"] == "OK"
    assert report["summary"]["matched_deck_cards"] == 1
    assert report["summary"]["companion_records"] == 1
    assert research_identity["hearthstonejson_receipt"]["status"] == "local_files"
    assert package_identity["hearthstonejson_receipt"]["status"] == "local_files"


def test_configure_builds_valid_load_safe_package_without_source_evidence(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_card_fetches(monkeypatch)

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
    for dirname in ("01_manifest", "02_source_documents", "03_research", "04_package"):
        assert (out / dirname).is_dir()
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
    _stub_empty_card_fetches(monkeypatch)
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
    _stub_empty_card_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json)
    out = tmp_path / "configure"
    runtime_root = tmp_path / "runtime"
    captured = {}

    def fake_apply_payload(args):
        captured["package"] = args.package
        captured["runtime_root"] = args.runtime_root
        captured["allow_source_informed"] = args.allow_source_informed
        captured["fake"] = args.fake
        captured["from_fake_receipt"] = args.from_fake_receipt
        captured["json"] = args.json
        return {"status": "applied"}, 0

    monkeypatch.setattr("hsconfig.commands.configure.apply_payload", fake_apply_payload)

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


def test_configure_warning_package_can_fake_apply(tmp_path: Path, monkeypatch, capsys):
    _stub_empty_card_fetches(monkeypatch)

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
    capsys.readouterr()

    package = out / "04_package"
    operator = _read_json(package / "reports" / "operator_summary.json")
    mechanic_visibility = operator["mechanic_visibility_summary"]

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert mechanic_visibility["non_blocking"] is True
    assert mechanic_visibility["warning_only_card_count"] > 0
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"

    assert main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime_root),
            "--fake",
            "--json",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "fake_apply_ready"
    assert payload["receipt"]["runtime_write_performed"] is False
