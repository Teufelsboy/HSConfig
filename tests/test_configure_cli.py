from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hsconfig.cli import main
from hsconfig.commands.configure import (
    _build_acceptance_summary,
    _build_config_proof_summary,
    _compact_config_quality_summary,
    configure_payload,
)
from hsconfig.cli_parser import build_parser
from tests.helpers.verified_deck_input import deck_code_for_cards


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
CONFIGURE_FIXTURE_CARDS = [
    {
        "card_id": "SW_448",
        "dbf_id": 64443,
        "count": 1,
        "name": "Darkbishop Benedictus",
        "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
    }
]
CONFIGURE_FIXTURE_DECK_CODE = deck_code_for_cards(CONFIGURE_FIXTURE_CARDS)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cards_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "cards": [
                    CONFIGURE_FIXTURE_CARDS[0]
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
    assert summary["runtime_package_match_status"] == "not_checked"
    assert summary["runtime_package_match"] is None


def test_configure_exposes_package_stage_digests_without_changing_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _stub_empty_card_fetches(monkeypatch)
    args = build_parser().parse_args(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(tmp_path / "configure"),
            "--current-date",
            "2026-07-28",
            "--json",
        ]
    )
    observed_stages: list[tuple[str, str]] = []

    def diagnostic_observer(name: str, digest: str) -> None:
        observed_stages.append((name, digest))
        raise SystemExit("diagnostic observer failure")

    payload, status = configure_payload(
        args,
        stage_observer=diagnostic_observer,
    )

    assert status == 0
    assert payload == _read_json(tmp_path / "configure" / "configure_summary.json")
    assert [name for name, _digest in observed_stages] == [
        "verified_deck",
        "normalized_source",
        "claim_surfaces",
        "lowered_runtime",
        "validated_authority",
        "artifact_writing",
    ]


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
            CONFIGURE_FIXTURE_DECK_CODE,
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
        return {
            "status": "applied",
            "receipt": {"runtime_package_match": {"status": "matched"}},
        }, 0

    monkeypatch.setattr("hsconfig.commands.configure.apply_payload", fake_apply_payload)

    code = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            CONFIGURE_FIXTURE_DECK_CODE,
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
    assert summary["runtime_package_match_status"] == "matched"
    assert summary["runtime_package_match"]["status"] == "matched"
    assert captured == {
        "package": str(out / "04_package"),
        "runtime_root": str(runtime_root),
        "allow_source_informed": False,
        "fake": False,
        "from_fake_receipt": None,
        "json": True,
    }


@pytest.mark.parametrize(
    "receipt",
    [{}, {"runtime_package_match": "matched"}],
)
def test_configure_apply_fails_closed_for_invalid_runtime_match_receipt(
    tmp_path: Path,
    monkeypatch,
    receipt: dict[str, object],
):
    _stub_empty_card_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json)
    out = tmp_path / "configure"

    monkeypatch.setattr(
        "hsconfig.commands.configure.apply_payload",
        lambda args: ({"status": "applied", "receipt": receipt}, 0),
    )

    code = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            CONFIGURE_FIXTURE_DECK_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--apply",
            "--json",
        ]
    )

    summary = _read_json(out / "configure_summary.json")

    assert code == 1
    assert summary["status"] == "failed"
    assert summary["stage"] == "apply"
    assert summary["errors"] == [
        "Successful apply receipt lacks runtime_package_match.status=matched."
    ]


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


def _operator_summary(**overrides) -> dict:
    summary = {
        "technical_status": "VALID_PACKAGE",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_contract": {
            "apply_authority": "reports/operator_summary.json",
        },
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
        "source_status_apply_blocking": False,
        "first_missing_source_action": None,
        "default_only_runtime_surfaces": [],
    }
    summary.update(overrides)
    return summary


def test_acceptance_summary_separates_load_safety_from_semantic_attention():
    operator = _operator_summary(
        technical_status="VALID_PACKAGE",
        runtime_apply_allowed=True,
        runtime_apply_mode="load_safe_apply",
        source_backed_status="SOURCE_BACKED_STRONG",
    )
    quality = {
        "status": "attention",
        "checks": {
            "runtime_row_trace_inventory": {
                "status": "attention",
                "unreported_runtime_rows": [{"card_id": "EX1_001"}],
            },
            "visionai_semantic_surface": {
                "status": "attention",
                "attention": ["semantic_surface_not_expressible"],
            },
        },
    }

    summary = _build_acceptance_summary(
        operator_summary=operator,
        validation_status="passed",
        config_quality_summary=quality,
        apply_requested=False,
        apply_status=None,
    )

    assert summary["load_safe_to_install"] is True
    assert summary["use_config_now"] is True
    assert summary["semantic_handoff_status"] == "attention"
    assert "unreported_runtime_rows" in summary["semantic_handoff_reasons"]


def test_source_strong_does_not_imply_semantic_closed():
    summary = _build_acceptance_summary(
        operator_summary=_operator_summary(
            technical_status="VALID_PACKAGE",
            runtime_apply_allowed=True,
            runtime_apply_mode="load_safe_apply",
            source_backed_status="SOURCE_BACKED_STRONG",
        ),
        validation_status="passed",
        config_quality_summary={
            "status": "attention",
            "checks": {
                "visionai_semantic_surface": {
                    "status": "attention",
                    "attention": ["missing_target_scope"],
                }
            },
        },
        apply_requested=False,
        apply_status=None,
    )

    assert summary["source_strength"] == "SOURCE_BACKED_STRONG"
    assert summary["semantic_handoff_status"] == "attention"


def test_acceptance_preserves_operator_semantic_attention_when_quality_is_incomplete():
    summary = _build_acceptance_summary(
        operator_summary=_operator_summary(
            semantic_handoff_status="attention",
            semantic_handoff_reasons=["semantic_surface_not_expressible"],
        ),
        validation_status="passed",
        config_quality_summary={
            "status": "clean",
            "problems": [],
        },
        apply_requested=False,
        apply_status=None,
    )

    assert summary["load_safe_to_install"] is True
    assert summary["semantic_handoff_status"] == "attention"
    assert summary["semantic_handoff_reasons"] == [
        "semantic_surface_not_expressible"
    ]


def test_build_acceptance_summary_marks_load_safe_package_usable() -> None:
    operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_contract": {
            "apply_authority": "reports/operator_summary.json",
        },
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
        "source_status_apply_blocking": False,
        "first_missing_source_action": "prove_current_or_evergreen_and_package_source_closure",
        "default_only_runtime_surfaces": [],
    }
    config_quality_summary = {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
    }

    assert _build_acceptance_summary(
        operator_summary=operator_summary,
        validate_status=0,
        apply_requested=False,
        apply_status=None,
        config_quality_summary=config_quality_summary,
    ) == {
        "schema_version": 1,
        "load_safe_to_install": True,
        "use_config_now": True,
        "use_config_now_scope": "load_safety_only",
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
        "normal_apply_authority": "reports/operator_summary.json",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "technical_status": "VALID_PACKAGE",
        "validation_status": "passed",
        "apply_requested": False,
        "apply_status": None,
        "source_strength": "SOURCE_BACKED_PARTIAL",
        "source_gaps_apply_blocking": False,
        "default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "config_quality_status": "clean",
        "config_quality_problem_checks": [],
        "first_missing_source_action": "prove_current_or_evergreen_and_package_source_closure",
        "next_report_to_open": "reports/operator_summary.json",
        "interpretation": (
            "Package is usable now according to reports/operator_summary.json; "
            "source and config-quality details remain diagnostic."
        ),
    }


def test_build_acceptance_summary_surfaces_diagnostics_without_blocking() -> None:
    operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_contract": {
            "apply_authority": "reports/operator_summary.json",
        },
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "source_status_apply_blocking": False,
        "first_missing_source_action": "add_source_claim_for_mulligan_keep",
        "default_only_runtime_surfaces": ["Mulligan.json"],
    }
    config_quality_summary = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 2,
        "problem_checks": [
            "operator_default_only_runtime_surfaces",
            "source_to_runtime_closure_rows_missing",
        ],
        "semantic_intent_status": "attention",
        "semantic_intent_first_attention": "card_behavior_runtime_row_missing_trace",
        "next_action": "run_contract_doctor_for_details",
    }

    summary = _build_acceptance_summary(
        operator_summary=operator_summary,
        validate_status=0,
        apply_requested=True,
        apply_status=0,
        config_quality_summary=config_quality_summary,
    )

    assert summary["use_config_now"] is True
    assert summary["normal_apply_authority"] == "reports/operator_summary.json"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["source_strength"] == "SOURCE_BACKED_STRONG"
    assert summary["source_gaps_apply_blocking"] is False
    assert summary["default_only_clean"] is False
    assert summary["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert summary["config_quality_problem_checks"] == [
        "operator_default_only_runtime_surfaces",
        "source_to_runtime_closure_rows_missing",
    ]
    assert summary["semantic_intent_status"] == "attention"
    assert summary["semantic_intent_first_attention"] == (
        "card_behavior_runtime_row_missing_trace"
    )
    assert summary["next_report_to_open"] == "reports/contract_doctor.json"
    assert summary["interpretation"] == (
        "Package is usable now according to reports/operator_summary.json; "
        "source and config-quality details remain diagnostic."
    )


def test_build_config_proof_summary_reports_clean_diagnostic_proof() -> None:
    operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "runtime_load_safe": True,
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_contract": {
            "apply_authority": "reports/operator_summary.json",
        },
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "source_status_apply_blocking": False,
        "first_missing_source_action": "none",
        "default_only_runtime_surfaces": [],
        "mechanic_visibility_summary": {
            "non_blocking": True,
            "first_warning_boundary": None,
        },
    }
    config_quality_summary = {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
        "forbidden_normal_surfaces_absent": True,
        "forbidden_normal_surfaces_status": "clean",
        "legacy_surfaces_present": [],
        "darkbishop_boundary_status": "effect_without_mulligan_keep",
        "runtime_json_status": "clean",
        "source_to_runtime_status": "clean",
        "currentness_status": "clean",
        "closure_schema_current": True,
        "cards_missing_closure": 0,
        "cards_total": 18,
        "cards_with_closure": 18,
        "mechanic_runtime_discipline_status": "clean",
        "semantic_intent_status": "clean",
        "config_intent_self_audit_status": "clean",
        "config_intent_first_attention": None,
        "config_intent_runtime_files_total": 3,
        "config_intent_runtime_files_without_intent": 0,
    }

    assert _build_config_proof_summary(
        operator_summary=operator_summary,
        validate_status=0,
        apply_requested=False,
        apply_status=None,
        config_quality_summary=config_quality_summary,
    ) == {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "normal_apply_authority": "reports/operator_summary.json",
        "technical_load_safe": True,
        "technical_status": "VALID_PACKAGE",
        "validation_status": "passed",
        "apply_requested": False,
        "apply_status": None,
        "source_strength": "SOURCE_BACKED_STRONG",
        "source_status_apply_blocking": False,
        "first_missing_source_action": "none",
        "no_default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "forbidden_normal_surfaces_absent": True,
        "forbidden_normal_surfaces_status": "clean",
        "forbidden_normal_surfaces_present": [],
        "runtime_surface_boundary": [
            "GlobalValues.json",
            "Mulligan.json",
            "per-card <CARDID>.json",
            "Combo.json",
        ],
        "runtime_surface_boundary_details": {
            "unconditional_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
                "per-card <CARDID>.json",
            ],
            "conditional_surfaces": {
                "Combo.json": "complete_source_backed_combo",
            },
        },
        "darkbishop_boundary_status": "effect_without_mulligan_keep",
        "mechanic_visibility_non_blocking": True,
        "first_warning_boundary": None,
        "runtime_json_status": "clean",
        "source_to_runtime_status": "clean",
        "currentness_status": "clean",
        "closure_schema_current": True,
        "cards_missing_closure": 0,
        "cards_total": 18,
        "cards_with_closure": 18,
        "semantic_intent_status": "clean",
        "surface_intent_status": "",
        "surface_intent_present": False,
        "surface_intent_surface_count": 0,
        "surface_intent_fallback_intent_rows": 0,
        "surface_intent_legacy_policy_surface_rows": [],
        "surface_intent_first_attention": None,
        "config_intent_self_audit_status": "clean",
        "config_intent_first_attention": None,
        "config_intent_runtime_files_without_intent": 0,
        "config_quality_status": "clean",
        "config_quality_problem_checks": [],
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_build_config_proof_summary_surfaces_attention_without_blocking() -> None:
    operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "runtime_load_safe": True,
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_contract": {
            "apply_authority": "reports/operator_summary.json",
        },
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
        "source_status_apply_blocking": False,
        "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
        "default_only_runtime_surfaces": ["Mulligan.json"],
        "mechanic_visibility_summary": {
            "non_blocking": True,
            "first_warning_boundary": {
                "mechanic": "location_activation",
                "boundary": "warning_only",
            },
        },
    }
    config_quality_summary = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 2,
        "problem_checks": [
            "operator_default_only_runtime_surfaces",
            "source_to_runtime_closure_rows_missing",
        ],
        "forbidden_normal_surfaces_absent": False,
        "forbidden_normal_surfaces_status": "attention",
        "legacy_surfaces_present": ["CustomConfig/deck/Presume.json"],
        "darkbishop_boundary_status": "mulligan_keep_present",
        "runtime_json_status": "attention",
        "source_to_runtime_status": "attention",
        "currentness_status": "attention",
        "closure_schema_current": False,
        "cards_missing_closure": 2,
        "cards_total": 18,
        "cards_with_closure": 16,
        "mechanic_runtime_discipline_status": "attention",
        "semantic_intent_status": "attention",
        "config_intent_self_audit_status": "attention",
        "config_intent_first_attention": "runtime_file_without_intent",
        "config_intent_runtime_files_total": 4,
        "config_intent_runtime_files_without_intent": 1,
    }

    summary = _build_config_proof_summary(
        operator_summary=operator_summary,
        validate_status=0,
        apply_requested=True,
        apply_status=0,
        config_quality_summary=config_quality_summary,
    )

    assert summary["apply_blocking"] is False
    assert summary["source_status_apply_blocking"] is False
    assert summary["no_default_only_clean"] is False
    assert summary["forbidden_normal_surfaces_absent"] is False
    assert summary["forbidden_normal_surfaces_present"] == [
        "CustomConfig/deck/Presume.json"
    ]
    assert summary["source_to_runtime_status"] == "attention"
    assert summary["currentness_status"] == "attention"
    assert summary["config_intent_self_audit_status"] == "attention"
    assert summary["config_intent_first_attention"] == "runtime_file_without_intent"
    assert summary["config_intent_runtime_files_without_intent"] == 1
    assert summary["first_warning_boundary"] == {
        "mechanic": "location_activation",
        "boundary": "warning_only",
    }
    assert summary["next_report_to_open"] == "reports/contract_doctor.json"


def test_acceptance_summary_helper_is_reexported_by_thin_configure_facade() -> None:
    import hsconfig.commands.configure as configure_command
    import hsconfig.configure_workflow as configure_workflow

    repo_root = Path(__file__).resolve().parents[1]
    apply_source = (
        repo_root / "src" / "hsconfig" / "commands" / "apply.py"
    ).read_text(encoding="utf-8")
    apply_gate_source = (
        repo_root / "src" / "hsconfig" / "apply_gate.py"
    ).read_text(encoding="utf-8")
    acceptance_matrix_source = (
        repo_root / "src" / "hsconfig" / "acceptance_matrix.py"
    ).read_text(encoding="utf-8")

    assert (
        configure_command._build_acceptance_summary
        is configure_workflow._build_acceptance_summary
    )
    assert "_build_acceptance_summary" not in apply_source
    assert "_build_acceptance_summary" not in apply_gate_source
    assert "_build_acceptance_summary" not in acceptance_matrix_source


def test_config_proof_summary_helper_is_reexported_by_thin_configure_facade() -> None:
    import hsconfig.commands.configure as configure_command
    import hsconfig.configure_workflow as configure_workflow

    repo_root = Path(__file__).resolve().parents[1]
    production_apply_surfaces = [
        repo_root / "src" / "hsconfig" / "commands" / "apply.py",
        repo_root / "src" / "hsconfig" / "apply_gate.py",
        repo_root / "src" / "hsconfig" / "runtime_apply.py",
        repo_root / "src" / "hsconfig" / "runtime_apply_receipts.py",
        repo_root / "src" / "hsconfig" / "commands" / "acceptance_matrix.py",
        repo_root / "src" / "hsconfig" / "acceptance_matrix.py",
    ]

    assert (
        configure_command._build_config_proof_summary
        is configure_workflow._build_config_proof_summary
    )
    for path in production_apply_surfaces:
        source = path.read_text(encoding="utf-8")
        assert "_build_config_proof_summary" not in source
        assert "config_proof_summary" not in source


def test_build_acceptance_summary_marks_non_load_safe_package_unusable() -> None:
    operator_summary = {
        "technical_status": "INVALID_PACKAGE",
        "runtime_apply_allowed": False,
        "runtime_apply_mode": "blocked",
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
        "source_status_apply_blocking": False,
        "default_only_runtime_surfaces": [],
    }
    config_quality_summary = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 1,
        "problem_checks": ["operator_summary_missing_or_invalid"],
    }

    summary = _build_acceptance_summary(
        operator_summary=operator_summary,
        validate_status=1,
        apply_requested=False,
        apply_status=None,
        config_quality_summary=config_quality_summary,
    )

    assert summary["use_config_now"] is False
    assert summary["normal_apply_authority"] == "reports/operator_summary.json"
    assert summary["runtime_apply_allowed"] is False
    assert summary["runtime_apply_mode"] == "blocked"
    assert summary["validation_status"] == "failed"
    assert summary["next_report_to_open"] == "reports/operator_summary.json"
    assert summary["interpretation"] == (
        "Package is not usable now; inspect reports/operator_summary.json first."
    )


def test_compact_config_quality_summary_reports_clean_status() -> None:
    report = {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [],
    }

    assert _compact_config_quality_summary(report) == {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
    }


def test_compact_config_quality_summary_reports_attention_checks() -> None:
    report = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [
            {"check": "card_behavior_semantic_default_visible", "value": ["CS2_235"]},
            {"check": "source_to_runtime_closure_rows_missing", "value": 1},
            {"check": "card_behavior_semantic_default_visible", "value": ["CS2_235"]},
        ],
    }

    assert _compact_config_quality_summary(report) == {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 3,
        "problem_checks": [
            "card_behavior_semantic_default_visible",
            "source_to_runtime_closure_rows_missing",
        ],
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
        "next_action": "run_contract_doctor_for_details",
    }


def test_compact_config_quality_summary_includes_semantic_intent_when_present() -> None:
    report = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [],
        "checks": {
            "semantic_intent_coverage": {
                "status": "attention",
                "first_attention": "card_behavior_runtime_row_missing_trace",
            }
        },
    }

    assert _compact_config_quality_summary(report) == {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
        "semantic_intent_status": "attention",
        "semantic_intent_first_attention": "card_behavior_runtime_row_missing_trace",
    }


def test_compact_config_quality_summary_includes_config_intent_self_audit() -> None:
    report = {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [],
        "checks": {
            "config_intent_self_audit": {
                "status": "attention",
                "first_attention": "runtime_file_without_intent",
                "runtime_files_total": 4,
                "runtime_files_without_intent": [
                    "CustomConfig/shadowpriest/UNTRACED_001.json"
                ],
                "unsupported_runtime_files": [],
                "default_only_runtime_surfaces": [],
            }
        },
    }

    assert _compact_config_quality_summary(report) == {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
        "config_intent_self_audit_status": "attention",
        "config_intent_first_attention": "runtime_file_without_intent",
        "config_intent_runtime_files_total": 4,
        "config_intent_runtime_files_without_intent": 1,
        "config_intent_unsupported_runtime_files": [],
        "config_intent_default_only_runtime_surfaces": [],
    }


def test_compact_config_quality_summary_includes_clean_visionai_semantic_surface() -> None:
    report = {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [],
        "checks": {
            "visionai_semantic_surface": {
                "status": "clean",
                "non_targeted_battlecry_target_rows": [],
                "effect_only_body_rows": [],
                "unsupported_report_only_runtime_rows": [],
                "semantic_default_runtime_rows": [],
            }
        },
    }

    assert _compact_config_quality_summary(report) == {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
        "visionai_semantic_surface_status": "clean",
        "visionai_non_targeted_battlecry_target_rows": 0,
        "visionai_effect_only_body_rows": 0,
        "visionai_unsupported_report_only_runtime_rows": 0,
        "visionai_semantic_default_runtime_rows": 0,
    }


def test_compact_config_quality_summary_includes_proof_fields() -> None:
    report = {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problems": [],
        "checks": {
            "legacy_surfaces": {"present": []},
            "darkbishop_boundary": {
                "seen": True,
                "mulligan_keep_present": False,
                "effect_runtime_present": True,
            },
            "runtime_json": {
                "deck_dir_present": True,
                "metadata_leaks": [],
                "stray_cardid_files": [],
            },
            "source_to_runtime_explainability": {
                "present": True,
                "authority": "diagnostic_only",
                "apply_blocking": False,
            },
            "trace_completeness": {
                "runtime_rows_missing_trace": [],
            },
            "closure_freshness": {
                "present": True,
                "closure_schema_current": True,
                "cards_missing_closure": 0,
                "cards_total": 18,
                "cards_with_closure": 18,
            },
            "mechanic_runtime_discipline": {
                "status": "clean",
                "report_only_runtime_rows": [],
            },
            "semantic_intent_coverage": {
                "status": "clean",
                "first_attention": None,
            },
        },
    }

    assert _compact_config_quality_summary(report) == {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
        "legacy_surfaces_present": [],
        "forbidden_normal_surfaces_absent": True,
        "forbidden_normal_surfaces_status": "clean",
        "darkbishop_boundary_status": "effect_without_mulligan_keep",
        "runtime_json_status": "clean",
        "source_to_runtime_status": "clean",
        "currentness_status": "clean",
        "closure_schema_current": True,
        "cards_missing_closure": 0,
        "cards_total": 18,
        "cards_with_closure": 18,
        "mechanic_runtime_discipline_status": "clean",
        "semantic_intent_status": "clean",
    }


def test_compact_config_quality_summary_marks_missing_trace_as_attention() -> None:
    report = {
        "status": "attention",
        "problems": [],
        "checks": {
            "source_to_runtime_explainability": {"present": True},
            "trace_completeness": {
                "runtime_rows_missing_trace": [{"card_id": "CS2_235"}],
            },
            "closure_freshness": {
                "present": True,
                "closure_schema_current": True,
                "cards_missing_closure": 0,
                "cards_total": 1,
                "cards_with_closure": 1,
            },
        },
    }

    summary = _compact_config_quality_summary(report)

    assert summary["source_to_runtime_status"] == "attention"
    assert summary["currentness_status"] == "clean"


@pytest.mark.parametrize(
    ("closure", "expected_status"),
    [
        (
            {
                "present": True,
                "closure_schema_current": False,
                "cards_missing_closure": 1,
                "cards_total": 18,
                "cards_with_closure": 17,
            },
            "attention",
        ),
        (None, "missing"),
    ],
)
def test_compact_config_quality_summary_projects_closure_currentness(
    closure: dict[str, Any] | None,
    expected_status: str,
) -> None:
    checks: dict[str, Any] = {
        "source_to_runtime_explainability": {"present": True},
        "trace_completeness": {"runtime_rows_missing_trace": []},
    }
    if closure is not None:
        checks["closure_freshness"] = closure
    report = {"status": "attention", "problems": [], "checks": checks}

    summary = _compact_config_quality_summary(report)

    assert summary["currentness_status"] == expected_status
    if closure is None:
        assert summary["closure_schema_current"] is False
        assert summary["cards_missing_closure"] == 0
    else:
        assert summary["closure_schema_current"] is closure["closure_schema_current"]
        assert summary["cards_missing_closure"] == closure["cards_missing_closure"]


def test_configure_writes_diagnostic_config_quality_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_empty_card_fetches(monkeypatch)

    def clean_report(_package_dir: Path) -> dict[str, Any]:
        return {
            "status": "clean",
            "problems": [],
            "checks": {
                "config_intent_self_audit": {
                    "status": "clean",
                    "first_attention": None,
                    "runtime_files_total": 3,
                    "runtime_files_without_intent": [],
                    "unsupported_runtime_files": [],
                    "default_only_runtime_surfaces": [],
                }
            },
        }

    monkeypatch.setattr(
        "hsconfig.commands.configure.build_config_quality_report",
        clean_report,
    )
    out = tmp_path / "out"

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

    summary = _read_json(out / "configure_summary.json")
    operator_summary = _read_json(
        out / "04_package" / "reports" / "operator_summary.json"
    )

    assert summary["config_quality_summary"] == {
        "status": "clean",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 0,
        "problem_checks": [],
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
        "config_intent_self_audit_status": "clean",
        "config_intent_runtime_files_total": 3,
        "config_intent_runtime_files_without_intent": 0,
        "config_intent_unsupported_runtime_files": [],
        "config_intent_default_only_runtime_surfaces": [],
    }
    assert summary["acceptance_summary"] == {
        "schema_version": 1,
        "load_safe_to_install": True,
        "use_config_now": True,
        "use_config_now_scope": "load_safety_only",
        "semantic_handoff_status": "attention",
        "semantic_handoff_reasons": [
            "reciprocal_burn_report_only",
            "semantic_surface_not_expressible",
            "variable_cost_condition_not_encoded",
        ],
        "normal_apply_authority": "reports/operator_summary.json",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "technical_status": "VALID_PACKAGE",
        "validation_status": "passed",
        "apply_requested": False,
        "apply_status": None,
        "source_strength": operator_summary["source_backed_status"],
        "source_gaps_apply_blocking": False,
        "default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "config_quality_status": "clean",
        "config_quality_problem_checks": [],
        "first_missing_source_action": operator_summary["first_missing_source_action"],
        "next_report_to_open": "reports/operator_summary.json",
        "interpretation": (
            "Package is usable now according to reports/operator_summary.json; "
            "source and config-quality details remain diagnostic."
        ),
    }
    assert operator_summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert summary["acceptance_summary"]["normal_apply_authority"] == (
        operator_summary["runtime_apply_contract"]["apply_authority"]
    )
    proof = summary["config_proof_summary"]
    assert proof["authority"] == "diagnostic_only"
    assert proof["apply_blocking"] is False
    assert proof["runtime_write_performed"] is False
    assert proof["normal_apply_authority"] == "reports/operator_summary.json"
    assert proof["technical_load_safe"] is True
    assert proof["no_default_only_clean"] is True
    assert proof["forbidden_normal_surfaces_status"] == "unknown"
    assert proof["forbidden_normal_surfaces_absent"] is None
    assert proof["config_intent_self_audit_status"] == "clean"
    assert proof["config_intent_runtime_files_without_intent"] == 0
    assert proof["runtime_surface_boundary"] == [
        "GlobalValues.json",
        "Mulligan.json",
        "per-card <CARDID>.json",
        "Combo.json",
    ]
    handoff = summary["handoff_contract"]
    assert handoff["authority"] == "diagnostic_only"
    assert handoff["apply_blocking"] is False
    assert handoff["runtime_write_performed"] is False
    assert handoff["normal_apply_authority"] == "reports/operator_summary.json"
    assert handoff["single_apply_authority_confirmed"] is True
    assert handoff["use_config_now"] is True
    assert handoff["semantic_handoff_status"] == "attention"
    assert handoff["semantic_handoff_reasons"] == [
        "reciprocal_burn_report_only",
        "semantic_surface_not_expressible",
        "variable_cost_condition_not_encoded",
    ]
    assert handoff["source_status_apply_blocking"] is False
    assert handoff["source_gaps_apply_blocking"] is False
    assert handoff["default_only_clean"] is True
    assert handoff["default_only_runtime_surfaces"] == []
    assert handoff["config_intent_self_audit_status"] == "clean"
    assert handoff["config_intent_runtime_files_without_intent"] == 0
    assert handoff["runtime_surface_boundary"] == [
        "GlobalValues.json",
        "Mulligan.json",
        "per-card <CARDID>.json",
        "Combo.json",
    ]
    assert handoff["next_report_to_open"] == "reports/operator_summary.json"
    assert "config_quality_summary" not in operator_summary
    assert "acceptance_summary" not in operator_summary
    assert "config_proof_summary" not in operator_summary
    assert "handoff_contract" not in operator_summary


def test_configure_quality_summary_failure_stays_diagnostic_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_empty_card_fetches(monkeypatch)
    apply_calls = []

    def raise_report(_package_dir: Path) -> dict[str, Any]:
        raise RuntimeError("quality unavailable")

    def fake_apply_payload(args):
        apply_calls.append(args)
        return {
            "status": "applied",
            "receipt": {"runtime_package_match": {"status": "matched"}},
        }, 0

    monkeypatch.setattr(
        "hsconfig.commands.configure.build_config_quality_report",
        raise_report,
    )
    monkeypatch.setattr("hsconfig.commands.configure.apply_payload", fake_apply_payload)
    out = tmp_path / "out"

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
            "--apply",
            "--json",
        ]
    ) == 0

    summary = _read_json(out / "configure_summary.json")

    assert summary["config_quality_summary"] == {
        "status": "attention",
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": 1,
        "problem_checks": ["config_quality_summary_failed"],
        "semantic_handoff_status": "insufficient_evidence",
        "semantic_handoff_reasons": ["semantic_runtime_evidence_missing"],
        "next_action": "run_contract_doctor_for_details",
        "error": "RuntimeError: quality unavailable",
    }
    assert summary["acceptance_summary"]["use_config_now"] is True
    assert summary["acceptance_summary"]["source_gaps_apply_blocking"] is False
    assert summary["acceptance_summary"]["config_quality_status"] == "attention"
    assert summary["acceptance_summary"]["config_quality_problem_checks"] == [
        "config_quality_summary_failed"
    ]
    assert summary["acceptance_summary"]["next_report_to_open"] == (
        "reports/contract_doctor.json"
    )
    assert summary["acceptance_summary"]["interpretation"] == (
        "Package is usable now according to reports/operator_summary.json; "
        "source and config-quality details remain diagnostic."
    )
    assert summary["config_proof_summary"]["forbidden_normal_surfaces_status"] == (
        "unknown"
    )
    assert summary["config_proof_summary"]["forbidden_normal_surfaces_absent"] is None
    assert len(apply_calls) == 1
    assert apply_calls[0].package == str(out / "04_package")
