import json
from pathlib import Path

import pytest

from hsconfig.cli import main


DECKS = [
    (
        "ShadowPriest",
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        Path("tests/fixtures/source_documents_shadowpriest_strong.json"),
    ),
    (
        "BigShaman",
        "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
        Path("tests/fixtures/source_documents_bigshaman_strong.json"),
    ),
    (
        "Discolock",
        "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA",
        Path("tests/fixtures/source_documents_discolock_strong.json"),
    ),
    (
        "Kingslayer",
        "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=",
        Path("tests/fixtures/source_documents_kingslayer_strong.json"),
    ),
    (
        "ImbueMage",
        "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=",
        Path("tests/fixtures/source_documents_imbuemage_strong.json"),
    ),
]


@pytest.mark.parametrize("deck_name,deck_code,source_documents", DECKS)
def test_core_archetype_fixture_prepare_path_is_source_informed(
    tmp_path: Path,
    capsys,
    monkeypatch,
    deck_name: str,
    deck_code: str,
    source_documents: Path,
):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / deck_name

    code = main(
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
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = out / "reports"
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    coverage = json.loads((reports / "claim_coverage_report.json").read_text(encoding="utf-8"))
    readiness = json.loads(
        (reports / "per_card_config_readiness_report.json").read_text(encoding="utf-8")
    )
    card_behavior = json.loads(
        (reports / "card_behavior_plan_report.json").read_text(encoding="utf-8")
    )
    mulligan = json.loads((reports / "mulligan_plan_report.json").read_text(encoding="utf-8"))
    globalvalues = json.loads(
        (reports / "global_values_authority_matrix.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] in {"SOURCE_BACKED_STRONG", "VALID_BUT_NOT_GUIDE_STRONG"}
    assert coverage["summary"]["guide_backed"] > 0
    assert (
        coverage["summary"]["guide_backed"]
        + coverage["summary"]["static_semantics_backfilled"]
        > 0
    )
    assert readiness["summary"]["runtime_emitted"] + readiness["summary"]["mulligan_only"] > 0
    assert card_behavior["rows"] or mulligan["rules"]
    assert "allowed_step1_overlays" in globalvalues
    assert "blocked_until_runtime_evidence" in globalvalues
