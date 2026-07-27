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
        "CtAPaladin",
        "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=",
        Path("tests/fixtures/source_documents_ctapaladin_strong.json"),
    ),
    (
        "PirateRogue",
        "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==",
        Path("tests/fixtures/source_documents_piraterogue_strong.json"),
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
        "TreantDruid",
        "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==",
        Path("tests/fixtures/source_documents_treantdruid_strong.json"),
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
    (
        "MechPala",
        "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
        Path("tests/fixtures/source_documents_mechpala_strong.json"),
    ),
    (
        "Boarlock",
        "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA",
        Path("tests/fixtures/source_documents_boarlock_strong.json"),
    ),
    (
        "PirateDH",
        "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==",
        Path("tests/fixtures/source_documents_piratedh_strong.json"),
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
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
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
    assert operator["semantic_status"] in {
        "SOURCE_BACKED_STRONG",
        "VALID_BUT_NOT_GUIDE_STRONG",
        "STATIC_SEMANTICS_USABLE",
    }
    assert operator["next_action"] == "ACQUIRE_LIVE_VERIFIED_SOURCE_BEFORE_APPLY"
    assert operator["runtime_apply_mode"] == "blocked"
    assert operator["runtime_apply_allowed"] is False
    assert operator["runtime_apply_reason"] == (
        "diagnostic_source_not_apply_eligible"
    )
    assert (
        coverage["summary"]["guide_backed"]
        + coverage["summary"]["static_semantics_backfilled"]
        > 0
    )
    assert readiness["summary"]["runtime_emitted"] + readiness["summary"]["mulligan_only"] > 0
    assert card_behavior["rows"] or mulligan["rules"]
    assert "allowed_step1_overlays" in globalvalues
    assert "blocked_until_runtime_evidence" in globalvalues


def test_shadowpriest_fixture_stays_load_safe_with_semantic_gaps_visible(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "ShadowPriest"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )

    assert code == 0
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    readiness = json.loads(
        (out / "reports" / "per_card_config_readiness_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert readiness["summary"]["generic_low_confidence"] == 0
    assert readiness["summary"]["cards_needing_guide_claims"] == 0
    assert readiness["summary"]["cards_needing_runtime_surface"] == 0
    assert readiness["summary"]["cards_needing_mechanic_lowering"] == 0


def test_bigshaman_static_recruit_stays_report_only_but_explicit_guide_row_remains(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "BigShaman"

    code = main(
        [
            "prepare",
            "--deck-name",
            "BigShaman",
            "--deck-code",
            "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_bigshaman_strong.json",
            "--json",
        ]
    )

    assert code == 0
    gvg_029 = json.loads(
        (out / "CustomConfig" / "bigshaman" / "GVG_029.json").read_text(encoding="utf-8")
    )
    ww_440 = json.loads(
        (out / "CustomConfig" / "bigshaman" / "WW_440.json").read_text(encoding="utf-8")
    )

    assert set(gvg_029) == {"GameCardId", "ConfigComment"}
    assert "BeforePlayCardBonus" in ww_440
    assert "OnBoardBonus" not in ww_440
