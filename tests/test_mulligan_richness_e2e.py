import json
from pathlib import Path

from hsconfig.cli import main


CARDS = [
    {"card_id": "TEST_001", "dbf_id": 1, "count": 2, "name": "Card A", "type": "MINION"},
    {"card_id": "TEST_002", "dbf_id": 2, "count": 2, "name": "Card B", "type": "MINION"},
    {"card_id": "TEST_003", "dbf_id": 3, "count": 2, "name": "Card C", "type": "SPELL"},
]


def test_prepare_with_rich_mulligan_sources_emits_rich_applyable_package(
    tmp_path: Path, capsys, monkeypatch
):
    result = _run_prepare(
        tmp_path,
        capsys,
        monkeypatch,
        source_documents="tests/fixtures/source_documents_mulligan_rich.json",
    )

    operator = result["operator_summary"]
    mulligan_surface = operator["config_usefulness"]["surfaces"]["mulligan"]
    mulligan_values = result["mulligan_json"]["Mulligan"]["values"]

    assert result["exit_code"] == 0
    assert result["payload"]["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert mulligan_surface["status"] == "rich"
    assert mulligan_surface["source_backed_rule_count"] >= 4
    assert {row["mulligan"] for row in mulligan_values} >= {"TEST_001", "TEST_002", "TEST_003"}
    assert "*" in {row["mulligan"] for row in mulligan_values}


def test_prepare_with_thin_mulligan_sources_stays_applyable_and_diagnosed(
    tmp_path: Path, capsys, monkeypatch
):
    result = _run_prepare(
        tmp_path,
        capsys,
        monkeypatch,
        source_documents="tests/fixtures/source_documents_mulligan_thin.json",
    )

    operator = result["operator_summary"]
    mulligan_surface = operator["config_usefulness"]["surfaces"]["mulligan"]

    assert result["exit_code"] == 0
    assert result["payload"]["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert operator["config_usefulness"]["blocking"] is False
    assert operator["config_usefulness"]["first_usefulness_gap"] == "mulligan_gap"
    assert mulligan_surface["status"] == "thin"
    assert (
        mulligan_surface["first_gap_reason"]
        == "no_source_backed_or_policy_backed_mulligan_keeps"
    )
    assert (
        mulligan_surface["next_source_need"]
        == "source_backed_or_policy_backed_mulligan_keeps"
    )


def _run_prepare(
    tmp_path: Path,
    capsys,
    monkeypatch,
    *,
    source_documents: str,
) -> dict:
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(json.dumps({"cards": CARDS}), encoding="utf-8")
    package = tmp_path / "package"
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            "Mulligan Fixture",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            source_documents,
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    mulligan_path = next((package / "CustomConfig").rglob("Mulligan.json"))
    return {
        "exit_code": exit_code,
        "payload": payload,
        "operator_summary": _read_json(reports / "operator_summary.json"),
        "mulligan_json": _read_json(mulligan_path),
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
