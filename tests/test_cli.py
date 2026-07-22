import argparse
import json
import tomllib
from pathlib import Path

import pytest

from hsconfig.commands.common import emit_result, run_payload_command
from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.cli import main
from hsconfig.input_loading import guide_documents_from_legacy_claims


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _write_cards_json(path: Path, card_ids: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": card_id,
                        "dbf_id": index,
                        "count": 1,
                        "name": f"Fixture {card_id}",
                    }
                    for index, card_id in enumerate(card_ids, start=1)
                ]
            }
        ),
        encoding="utf-8",
    )


def _claim_bundle_for_override(
    *,
    claims: list[dict],
    card_ids: list[str],
    conflict_report: dict | None = None,
) -> dict:
    coverage_cards = {
        card_id: {"coverage_status": "guide_backed"} for card_id in card_ids
    }
    coverage = {
        "guide_backed_cards": len(card_ids),
        "uncovered_cards": [],
        "summary": {
            "guide_backed": len(card_ids),
            "static_semantics_backfilled": 0,
            "uncovered_low_confidence": 0,
        },
        "cards": coverage_cards,
    }
    return {
        "claims": claims,
        "unsupported_claims": [],
        "source_evidence_index": [],
        "coverage": coverage,
        "claim_coverage_report": coverage,
        "claim_conflict_report": conflict_report
        or {"conflict_count": 0, "conflicts": []},
    }


def _write_plan_override_reports(
    plan_reports: Path,
    *,
    guide_claim_bundle: dict,
    mulligan_rules: list[dict] | None = None,
    card_behavior_rows: list[dict] | None = None,
    combo_rows: list[dict] | None = None,
    globalvalue_rows: list[dict] | None = None,
) -> None:
    plan_reports.mkdir()
    (plan_reports / "guide_claim_bundle.json").write_text(
        json.dumps(guide_claim_bundle),
        encoding="utf-8",
    )
    (plan_reports / "mulligan_plan_report.json").write_text(
        json.dumps(
            {
                "deck_name": "Plan Override",
                "rules": mulligan_rules or [],
                "suppressed_rules": [],
                "quality": {"status": "thin"},
            }
        ),
        encoding="utf-8",
    )
    rows = card_behavior_rows or []
    card_rows: dict[str, list[dict]] = {}
    for row in rows:
        card_rows.setdefault(str(row["card_id"]), []).append(row)
    (plan_reports / "card_behavior_plan_report.json").write_text(
        json.dumps(
            {
                "card_rows": card_rows,
                "rows": rows,
                "suppressed": [],
                "option_resolution": [],
            }
        ),
        encoding="utf-8",
    )
    (plan_reports / "combo_plan_report.json").write_text(
        json.dumps({"combos": combo_rows or [], "suppressed": []}),
        encoding="utf-8",
    )
    (plan_reports / "global_values_authority_matrix.json").write_text(
        json.dumps(
            {
                "allowed_step1_overlays": globalvalue_rows or [],
                "blocked_until_runtime_evidence": [],
            }
        ),
        encoding="utf-8",
    )


def _write_minimal_source_documents(path: Path, card_id: str = "EX1_001") -> None:
    path.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/guide",
                        "source_title": "Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T00:00:00Z",
                        "claims": [
                            {
                                "claim_kind": "targeting_rule",
                                "cards": [card_id],
                                "stance": "prefer_enemy_hero",
                                "runtime_block": "BeforePlayCardBonus",
                                "runtime_value": "12",
                                "evidence_text_short": "Fixture runtime claim.",
                                "source_confidence": "high",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_validate_missing_package_returns_nonzero_json(tmp_path: Path, capsys):
    code = main(["validate", "--package", str(tmp_path / "missing"), "--json"])

    captured = capsys.readouterr()

    assert code == 1
    assert json.loads(captured.out)["status"] == "failed"


def test_pyproject_exposes_hsconfig_entrypoint():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["hsconfig"] == "hsconfig.cli:main"


def test_cli_main_dispatches_apply_without_changing_public_command_shape(
    tmp_path: Path, monkeypatch
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    package.mkdir()
    runtime.mkdir()

    captured = {}

    def fake_run_apply_command(args):
        captured["package"] = args.package
        captured["runtime_root"] = args.runtime_root
        captured["json"] = args.json
        return 0

    monkeypatch.setattr("hsconfig.cli.run_apply_command", fake_run_apply_command)

    assert (
        main(
            [
                "apply",
                "--package",
                str(package),
                "--runtime-root",
                str(runtime),
                "--json",
            ]
        )
        == 0
    )
    assert captured == {
        "package": str(package),
        "runtime_root": str(runtime),
        "json": True,
    }


def test_apply_rejects_fake_and_from_fake_receipt_together(
    tmp_path: Path, monkeypatch, capsys
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    receipt = tmp_path / "fake-receipt.json"
    package.mkdir()
    runtime.mkdir()
    receipt.write_text("{}", encoding="utf-8")
    dispatched = False

    def fake_run_apply_command(args):
        nonlocal dispatched
        dispatched = True
        return 0

    monkeypatch.setattr("hsconfig.cli.run_apply_command", fake_run_apply_command)

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "apply",
                "--package",
                str(package),
                "--runtime-root",
                str(runtime),
                "--fake",
                "--from-fake-receipt",
                str(receipt),
                "--json",
            ]
        )

    assert excinfo.value.code == 2
    assert dispatched is False
    captured = capsys.readouterr()
    assert "--fake" in captured.err
    assert "--from-fake-receipt" in captured.err


def test_cli_main_dispatches_validate_without_changing_public_command_shape(
    tmp_path: Path, monkeypatch
):
    package = tmp_path / "package"
    package.mkdir()

    captured = {}

    def fake_run_validate_command(args):
        captured["package"] = args.package
        captured["json"] = args.json
        return 0

    monkeypatch.setattr("hsconfig.cli.run_validate_command", fake_run_validate_command)

    assert main(["validate", "--package", str(package), "--json"]) == 0
    assert captured == {"package": str(package), "json": True}


def test_cli_main_dispatches_contract_doctor_without_apply_authority(
    tmp_path: Path, monkeypatch
):
    package = tmp_path / "package"
    package.mkdir()
    captured = {}

    def fake_run_contract_doctor_command(args):
        captured["package"] = args.package
        captured["out"] = args.out
        captured["json"] = args.json
        return 0

    monkeypatch.setattr(
        "hsconfig.cli.run_contract_doctor_command",
        fake_run_contract_doctor_command,
    )

    assert main(["contract-doctor", "--package", str(package), "--json"]) == 0
    assert captured == {"package": str(package), "out": None, "json": True}


def test_readme_documents_prepare_as_normal_path():
    root_readme = Path("README.md").read_text(encoding="utf-8")
    operator_readme = Path("docs/operator/README.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )

    assert "docs/operator/README.md" in root_readme
    assert "hsconfig prepare" in root_readme
    assert "hsconfig apply" in root_readme
    assert "hsconfig build" in operator_readme
    assert "reports/research" in workflow


def test_cli_no_longer_owns_input_loading_helpers():
    text = Path("src/hsconfig/cli.py").read_text(encoding="utf-8")

    assert "def _load_cards(" not in text
    assert "def _load_claims(" not in text
    assert "def _load_guide_sources(" not in text
    assert "def _load_source_documents(" not in text
    assert "def _load_source_evidence(" not in text
    assert "def _fixture_row_for(" not in text


def test_build_accepts_cards_json_object(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Card One"},
                    {"card_id": "EX1_002", "dbf_id": 2, "count": 1, "name": "Card Two"},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Explicit Cards",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 0
    assert payload["status"] == "passed"
    assert (out / "CustomConfig" / "explicit_cards" / "EX1_001.json").exists()
    assert (out / "CustomConfig" / "explicit_cards" / "EX1_002.json").exists()


def test_build_decodes_deck_code_by_default(tmp_path: Path, capsys):
    out = tmp_path / "package"

    code = main(
        [
            "build",
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
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    reports = out / "reports"
    deck_identity = json.loads((reports / "deck_identity.json").read_text(encoding="utf-8"))
    manifest = json.loads((reports / "input_manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((reports / "deckstring_decode_receipt.json").read_text(encoding="utf-8"))
    card_id_map = json.loads((reports / "card_id_map.json").read_text(encoding="utf-8"))
    semantic_report = json.loads(
        (reports / "semantic_enrichment_report.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert deck_identity["hero_dbf_id"] == 813
    assert deck_identity["format"] == "FT_WILD"
    assert deck_identity["card_count_total"] == 30
    assert manifest["card_source"] == "deckstring"
    assert manifest["format"] == "FT_WILD"
    assert receipt["decoder"] == "hearthstone.deckstrings"
    assert card_id_map["545"]["card_id"] == "DS1_233"
    assert any(card["card_id"] == "SW_448" for card in semantic_report["cards"])
    assert (reports / "card_semantic_audit.md").exists()
    assert (out / "CustomConfig" / "shadowpriest" / "DS1_233.json").exists()


def test_build_rejects_invalid_deck_code_without_placeholder_flag(tmp_path: Path, capsys):
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Fixture Deck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 1
    assert payload["status"] == "failed"
    assert not list(out.glob("CustomConfig/fixture_deck/HSC_*.json"))


def test_legacy_claims_synthesize_legacy_retrieved_at_when_unstamped():
    documents = guide_documents_from_legacy_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/deck-guide",
                "claim": "Always keep Pressure One.",
                "cards": ["EX1_001"],
                "claim_type": "mulligan",
            }
        ]
    )

    assert documents[0]["retrieved_at"] == "1970-01-01T00:00:00Z"


def test_legacy_claims_do_not_match_face_inside_surface_word():
    documents = guide_documents_from_legacy_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/deck-guide",
                "claim": "Card behavior surface damage row without targeting guidance.",
                "cards": ["EX1_001"],
            }
        ]
    )

    claim = documents[0]["claims"][0]

    assert claim["claim_kind"] == "card_role"
    assert claim["stance"] == "deck_card"
    routed = route_card_behavior_surfaces([claim])
    assert all(row.get("intent") != "prefer_enemy_hero" for row in routed["rows"])
    assert all(row.get("meaningful_runtime_surface") is False for row in routed["rows"])


def test_legacy_claims_still_match_real_face_targeting_phrases():
    documents = guide_documents_from_legacy_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/deck-guide",
                "claim": "Send face damage now.",
                "cards": ["EX1_001"],
            },
            {
                "source": "guide",
                "url": "https://example.invalid/deck-guide",
                "claim": "Target the enemy hero with burst.",
                "cards": ["EX1_002"],
            },
        ]
    )

    claims = [document_claim for document in documents for document_claim in document["claims"]]

    assert [claim["claim_kind"] for claim in claims] == ["targeting_rule", "targeting_rule"]
    assert [claim["stance"] for claim in claims] == [
        "prefer_enemy_hero",
        "prefer_enemy_hero",
    ]


def test_build_accepts_claims_json_for_guide_backed_config(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "EX1_001",
                        "dbf_id": 1,
                        "count": 2,
                        "name": "Pressure One",
                        "text": "Battlecry: deal damage.",
                    },
                    {"card_id": "EX1_002", "dbf_id": 2, "count": 1, "name": "Burst Two"},
                ]
            }
        ),
        encoding="utf-8",
    )
    claims_json = tmp_path / "claims.json"
    claims_json.write_text(
        json.dumps(
            [
                {
                    "source": "guide",
                    "url": "https://example.invalid/deck-guide",
                    "claim": "Always keep Pressure One and push face damage early.",
                    "cards": ["EX1_001"],
                    "claim_type": "mulligan_keep",
                },
                {
                    "source": "guide",
                    "url": "https://example.invalid/deck-guide",
                    "claim": "Use Pressure One with Burst Two for a combo burst turn.",
                    "cards": ["EX1_001", "EX1_002"],
                    "claim_type": "combo",
                    "values": ["8", "14"],
                },
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Guide Cards",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--claims-json",
            str(claims_json),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    research_dir = out / "reports" / "research"
    archetype_research = json.loads(
        (research_dir / "archetype_research.json").read_text(encoding="utf-8")
    )
    card_role_map = json.loads((research_dir / "card_role_map.json").read_text(encoding="utf-8"))
    mulligan_anchor_map = json.loads(
        (research_dir / "mulligan_anchor_map.json").read_text(encoding="utf-8")
    )
    globalvalue_intent = json.loads(
        (research_dir / "globalvalue_intent.json").read_text(encoding="utf-8")
    )
    deck_dir = out / "CustomConfig" / "guide_cards"
    reports = out / "reports"
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    operator_summary = json.loads(
        (reports / "operator_summary.json").read_text(encoding="utf-8")
    )
    combo_plan = json.loads((reports / "combo_plan_report.json").read_text(encoding="utf-8"))
    combo_suppressions = json.loads(
        (reports / "combo_suppression_report.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert archetype_research["confidence"] == "guide_backed"
    assert card_role_map["EX1_001"]["confidence"] == "guide_backed"
    assert mulligan_anchor_map["EX1_001"]["intent"] == "hold"
    assert globalvalue_intent["pressure_bias"] == "high"
    assert mulligan["Mulligan"]["values"][0]["mulligan"] == "EX1_001"
    assert not (deck_dir / "Combo.json").exists()
    assert combo_plan["combos"] == []
    assert combo_suppressions == combo_plan["suppressed"]
    assert combo_suppressions[0]["reason"] == "missing_timing"
    assert "combo" not in operator_summary["default_only_runtime_surfaces"]


def test_build_accepts_source_documents_json_and_writes_source_evidence_report(
    tmp_path: Path, capsys
):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Pressure One"},
                ]
            }
        ),
        encoding="utf-8",
    )
    source_documents = tmp_path / "source_documents.json"
    source_documents.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/deck-guide",
                        "source_title": "Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T00:00:00Z",
                        "claims": [
                            {
                                "claim_kind": "card_role",
                                "cards": ["EX1_001"],
                                "reason": "Pressure One supports the early board plan.",
                                "source_confidence": "high",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Guide Cards",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = out / "reports"
    source_report = json.loads(
        (reports / "source_evidence_verification_report.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert source_report["status"] == "passed"
    assert source_report["summary"]["claim_count"] == 1
    assert source_report["warnings"] == []


def test_build_threads_source_evidence_warnings_into_operator_summary(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Pressure One"},
                ]
            }
        ),
        encoding="utf-8",
    )
    source_documents = tmp_path / "source_documents.json"
    source_documents.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://localhost/guide",
                        "source_title": "Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T00:00:00Z",
                        "claims": [
                            {
                                "claim_kind": "targeting_rule",
                                "cards": ["EX1_001"],
                                "stance": "prefer_enemy_hero",
                                "runtime_block": "BeforePlayCardBonus",
                                "runtime_value": "12",
                                "evidence_text_short": "Pressure One should go face.",
                                "source_confidence": "high",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "PressureDeck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = out / "reports"
    depth = json.loads((reports / "guide_source_depth_report.json").read_text(encoding="utf-8"))
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    source_report = json.loads(
        (reports / "source_evidence_verification_report.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert source_report["summary"]["warnings_count"] == 1
    assert depth["source_evidence"]["warnings_count"] == 1
    assert operator_summary["guide_strength_summary"]["source_evidence_warnings"] == 1
    assert operator_summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"


def test_build_uses_computed_source_depth_status_for_operator_gating(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Pressure One"},
                ]
            }
        ),
        encoding="utf-8",
    )
    source_documents = tmp_path / "source_documents.json"
    source_documents.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/guide",
                        "source_title": "Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T00:00:00Z",
                        "claims": [
                            {
                                "claim_kind": "targeting_rule",
                                "cards": ["EX1_001"],
                                "stance": "prefer_enemy_hero",
                                "runtime_block": "BeforePlayCardBonus",
                                "runtime_value": "12",
                                "evidence_text_short": "Pressure One should go face.",
                                "source_confidence": "high",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    plan_reports = tmp_path / "plan_reports"
    plan_reports.mkdir()
    (plan_reports / "guide_claim_bundle.json").write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "claim_report_only_runtime",
                        "claim_kind": "targeting_rule",
                        "cards": ["EX1_001"],
                        "claim_readiness": "explicit_low_confidence",
                        "trust_ceiling": "report_only",
                        "source_family": "guide",
                    }
                ],
                "unsupported_claims": [],
                "source_evidence_index": [],
                "coverage": {
                    "guide_backed_cards": 1,
                    "uncovered_cards": [],
                    "summary": {
                        "guide_backed": 1,
                        "static_semantics_backfilled": 0,
                        "uncovered_low_confidence": 0,
                    },
                    "cards": {
                        "EX1_001": {
                            "coverage_status": "guide_backed",
                        }
                    },
                },
                "claim_coverage_report": {
                    "guide_backed_cards": 1,
                    "uncovered_cards": [],
                    "summary": {
                        "guide_backed": 1,
                        "static_semantics_backfilled": 0,
                        "uncovered_low_confidence": 0,
                    },
                    "cards": {
                        "EX1_001": {
                            "coverage_status": "guide_backed",
                        }
                    },
                },
                "claim_conflict_report": {"conflict_count": 0, "conflicts": []},
            }
        ),
        encoding="utf-8",
    )
    (plan_reports / "mulligan_plan_report.json").write_text(
        json.dumps({"rules": [], "suppressed_rules": []}),
        encoding="utf-8",
    )
    (plan_reports / "card_behavior_plan_report.json").write_text(
        json.dumps(
            {
                "card_rows": {
                    "EX1_001": [
                        {
                            "card_id": "EX1_001",
                            "surface_family": "CARDID.json",
                            "surface": "CardID.json",
                            "behavior_block": "BeforePlayCardBonus",
                            "meaningful_runtime_surface": True,
                            "source_claim_ids": ["claim_report_only_runtime"],
                        }
                    ]
                },
                "rows": [
                    {
                        "card_id": "EX1_001",
                        "surface_family": "CARDID.json",
                        "surface": "CardID.json",
                        "behavior_block": "BeforePlayCardBonus",
                        "meaningful_runtime_surface": True,
                        "source_claim_ids": ["claim_report_only_runtime"],
                    }
                ],
                "suppressed": [],
                "option_resolution": [],
            }
        ),
        encoding="utf-8",
    )
    (plan_reports / "combo_plan_report.json").write_text(
        json.dumps({"combos": [], "suppressed": []}),
        encoding="utf-8",
    )
    (plan_reports / "global_values_authority_matrix.json").write_text(
        json.dumps({"allowed_step1_overlays": [], "blocked_until_runtime_evidence": []}),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "PressureDeck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(source_documents),
            "--plan-reports-dir",
            str(plan_reports),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = out / "reports"
    receipt = json.loads((reports / "guide_builder_receipt.json").read_text(encoding="utf-8"))
    depth = json.loads((reports / "guide_source_depth_report.json").read_text(encoding="utf-8"))
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert receipt["source_depth_status"] == "source_backed"
    assert depth["summary"]["report_only_claims"] == 1
    assert depth["source_depth_status"] == "needs_more_research"
    assert operator_summary["semantic_status"] == "NEEDS_MORE_RESEARCH"
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_mode"] == "load_safe_apply"
    assert operator_summary["runtime_apply_allowed"] is True


def test_build_plan_reports_dir_filters_stale_report_only_runtime_rows(
    tmp_path: Path, capsys
):
    cards_json = tmp_path / "cards.json"
    card_ids = ["EX1_001", "EX1_002", "EX1_003", "EX1_004", "EX1_005", "EX1_006"]
    _write_cards_json(cards_json, card_ids)
    source_documents = tmp_path / "source_documents.json"
    _write_minimal_source_documents(source_documents)
    plan_reports = tmp_path / "plan_reports"
    _write_plan_override_reports(
        plan_reports,
        guide_claim_bundle=_claim_bundle_for_override(
            card_ids=card_ids,
            claims=[
                {
                    "claim_id": "valid_runtime_target",
                    "claim_kind": "targeting_rule",
                    "cards": ["EX1_001"],
                    "stance": "prefer_enemy_hero",
                    "runtime_block": "BeforePlayCardBonus",
                    "runtime_value": "12",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_confidence": "high",
                    "evidence_text_short": "Use the valid card as a runtime target.",
                },
                {
                    "claim_id": "report_only_target",
                    "claim_kind": "targeting_rule",
                    "cards": ["EX1_002"],
                    "stance": "prefer_enemy_hero",
                    "runtime_block": "BeforePlayCardBonus",
                    "runtime_value": "12",
                    "claim_readiness": "source_backed_static_semantics",
                    "trust_ceiling": "report_only",
                    "source_confidence": "high",
                    "evidence_text_short": "A stale report-only target row.",
                },
                {
                    "claim_id": "low_confidence_keep",
                    "claim_kind": "mulligan_keep",
                    "cards": ["EX1_003"],
                    "claim_readiness": "explicit_low_confidence",
                    "trust_ceiling": "report_only",
                    "source_confidence": "low",
                    "evidence_text_short": "A stale low-confidence mulligan row.",
                },
                {
                    "claim_id": "rejected_combo",
                    "claim_kind": "combo_sequence",
                    "cards": ["EX1_004", "EX1_005"],
                    "sequence": ["EX1_004", "EX1_005"],
                    "operator": ">>",
                    "values": ["7", "9"],
                    "claim_readiness": "contract_gap",
                    "trust_ceiling": "report_only",
                    "source_confidence": "low",
                    "evidence_text_short": "A stale rejected combo row.",
                },
            ],
        ),
        mulligan_rules=[
            {
                "card": "EX1_003",
                "selector_kind": "card",
                "selector": "EX1_003",
                "action": "hold",
                "condition": "*",
                "source_claim_ids": ["low_confidence_keep"],
            }
        ],
        card_behavior_rows=[
            {
                "card_id": "EX1_001",
                "surface_family": "CARDID.json",
                "surface": "CardID.json",
                "behavior_block": "BeforePlayCardBonus",
                "meaningful_runtime_surface": True,
                "source_claim_ids": ["valid_runtime_target"],
            },
            {
                "card_id": "EX1_002",
                "surface_family": "CARDID.json",
                "surface": "CardID.json",
                "behavior_block": "BeforePlayCardBonus",
                "meaningful_runtime_surface": True,
                "source_claim_ids": ["report_only_target"],
            },
            {
                "card_id": "EX1_006",
                "surface_family": "CARDID.json",
                "surface": "CardID.json",
                "behavior_block": "BeforePlayCardBonus",
                "meaningful_runtime_surface": True,
            },
        ],
        combo_rows=[
            {
                "rule_id": "rejected_combo",
                "cards": ["EX1_004", "EX1_005"],
                "operator": ">>",
                "values": ["7", "9"],
                "condition": "*",
                "source_claim_ids": ["rejected_combo"],
            }
        ],
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Plan Override Filter",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(source_documents),
            "--plan-reports-dir",
            str(plan_reports),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    deck_dir = out / "CustomConfig" / "plan_override_filter"
    valid_card = json.loads((deck_dir / "EX1_001.json").read_text(encoding="utf-8"))
    report_only_card = json.loads(
        (deck_dir / "EX1_002.json").read_text(encoding="utf-8")
    )
    unreferenced_card = json.loads(
        (deck_dir / "EX1_006.json").read_text(encoding="utf-8")
    )
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    operator_summary = json.loads(
        (out / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    source_contract_audit = json.loads(
        (out / "reports" / "source_contract_audit.json").read_text(encoding="utf-8")
    )
    lifecycle_by_id = {
        row["claim_id"]: row for row in source_contract_audit["claim_lifecycle_rows"]
    }

    assert code == 0
    assert payload["status"] == "passed"
    assert valid_card["BeforePlayCardBonus"]["values"]
    assert "BeforePlayCardBonus" not in report_only_card
    assert "BeforePlayCardBonus" not in unreferenced_card
    assert not any(
        row.get("mulligan") == "EX1_003" for row in mulligan["Mulligan"]["values"]
    )
    assert not (deck_dir / "Combo.json").exists()
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_allowed"] is True
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert lifecycle_by_id["report_only_target"]["runtime_eligibility"] == "report_only"
    assert lifecycle_by_id["report_only_target"]["builder_or_router_decision"] != "emitted"
    assert lifecycle_by_id["low_confidence_keep"]["builder_or_router_decision"] != "emitted"
    assert lifecycle_by_id["rejected_combo"]["builder_or_router_decision"] != "emitted"


def test_build_plan_reports_dir_filters_conflict_quarantined_runtime_rows(
    tmp_path: Path, capsys
):
    cards_json = tmp_path / "cards.json"
    card_ids = ["EX1_001", "EX1_002"]
    _write_cards_json(cards_json, card_ids)
    source_documents = tmp_path / "source_documents.json"
    _write_minimal_source_documents(source_documents)
    plan_reports = tmp_path / "plan_reports"
    _write_plan_override_reports(
        plan_reports,
        guide_claim_bundle=_claim_bundle_for_override(
            card_ids=card_ids,
            conflict_report={
                "conflict_count": 0,
                "conflicts": [],
            },
            claims=[
                {
                    "claim_id": "valid_runtime_target",
                    "claim_kind": "targeting_rule",
                    "cards": ["EX1_001"],
                    "stance": "prefer_enemy_hero",
                    "runtime_block": "BeforePlayCardBonus",
                    "runtime_value": "12",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_confidence": "high",
                    "evidence_text_short": "Use the valid card as a runtime target.",
                },
                {
                    "claim_id": "conflict_target",
                    "claim_kind": "targeting_rule",
                    "cards": ["EX1_002"],
                    "stance": "prefer_enemy_hero",
                    "runtime_block": "BeforePlayCardBonus",
                    "runtime_value": "12",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_confidence": "high",
                    "evidence_text_short": "A stale quarantined target row.",
                },
                {
                    "claim_id": "conflict_target_opposed",
                    "claim_kind": "targeting_rule",
                    "cards": ["EX1_002"],
                    "stance": "prefer_friendly_minion",
                    "runtime_block": "BeforePlayCardBonus",
                    "runtime_value": "-12",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_confidence": "high",
                    "evidence_text_short": "A contradictory stale target row.",
                },
            ],
        ),
        card_behavior_rows=[
            {
                "card_id": "EX1_001",
                "surface_family": "CARDID.json",
                "surface": "CardID.json",
                "behavior_block": "BeforePlayCardBonus",
                "meaningful_runtime_surface": True,
                "source_claim_ids": ["valid_runtime_target"],
            },
            {
                "card_id": "EX1_002",
                "surface_family": "CARDID.json",
                "surface": "CardID.json",
                "behavior_block": "BeforePlayCardBonus",
                "meaningful_runtime_surface": True,
                "source_claim_ids": ["conflict_target"],
            },
        ],
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Plan Override Conflict Filter",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(source_documents),
            "--plan-reports-dir",
            str(plan_reports),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    deck_dir = out / "CustomConfig" / "plan_override_conflict_filter"
    valid_card = json.loads((deck_dir / "EX1_001.json").read_text(encoding="utf-8"))
    quarantined_card = json.loads(
        (deck_dir / "EX1_002.json").read_text(encoding="utf-8")
    )
    operator_summary = json.loads(
        (out / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    source_contract_audit = json.loads(
        (out / "reports" / "source_contract_audit.json").read_text(encoding="utf-8")
    )
    claim_conflict_report = json.loads(
        (out / "reports" / "claim_conflict_report.json").read_text(encoding="utf-8")
    )
    lifecycle_by_id = {
        row["claim_id"]: row for row in source_contract_audit["claim_lifecycle_rows"]
    }

    assert code == 0
    assert payload["status"] == "passed"
    assert valid_card["BeforePlayCardBonus"]["values"]
    assert "BeforePlayCardBonus" not in quarantined_card
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_allowed"] is True
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert claim_conflict_report["conflict_count"] == 1
    assert set(claim_conflict_report["conflicts"][0]["claim_ids"]) == {
        "conflict_target",
        "conflict_target_opposed",
    }
    assert lifecycle_by_id["conflict_target"]["quarantine_status"] == "quarantined"
    assert lifecycle_by_id["conflict_target_opposed"]["quarantine_status"] == "quarantined"
    assert lifecycle_by_id["conflict_target"]["builder_or_router_decision"] != "emitted"
    assert (
        lifecycle_by_id["conflict_target"]["final_runtime_effect"]
        == "suppressed_quarantined_claim"
    )


def test_build_claims_json_timed_combo_emits_combo_json(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Pressure One"},
                    {"card_id": "EX1_002", "dbf_id": 2, "count": 1, "name": "Burst Two"},
                ]
            }
        ),
        encoding="utf-8",
    )
    claims_json = tmp_path / "claims.json"
    claims_json.write_text(
        json.dumps(
            [
                {
                    "source": "guide",
                    "url": "https://example.invalid/deck-guide",
                    "claim": "Use Pressure One with Burst Two for a same-turn combo burst.",
                    "cards": ["EX1_001", "EX1_002"],
                    "claim_type": "combo",
                    "timing_kind": "same_turn",
                    "operator": ">>",
                    "values": ["8", "14"],
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Guide Cards",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--claims-json",
            str(claims_json),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    deck_dir = out / "CustomConfig" / "guide_cards"
    reports = out / "reports"
    combo = json.loads((deck_dir / "Combo.json").read_text(encoding="utf-8"))
    combo_plan = json.loads((reports / "combo_plan_report.json").read_text(encoding="utf-8"))
    combo_suppressions = json.loads(
        (reports / "combo_suppression_report.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert combo_plan["combos"][0]["operator"] == ">>"
    assert combo["ComboList"]["values"][0]["combo"] == "EX1_001>>EX1_002"
    assert combo["ComboList"]["values"][0]["value"] == "8>>14"
    assert combo_suppressions == []


def test_build_consumes_plan_reports_dir_overrides(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Pressure One"},
                    {"card_id": "EX1_002", "dbf_id": 2, "count": 1, "name": "Burst Two"},
                ]
            }
        ),
        encoding="utf-8",
    )
    guide_sources = tmp_path / "sources.json"
    guide_sources.write_text(
        json.dumps(
            [
                {
                    "source_url": "https://example.invalid/guide",
                    "source_title": "Guide",
                    "source_family": "guide",
                    "claims": [
                        {
                            "claim_kind": "mulligan_keep",
                            "cards": ["EX1_001"],
                            "stance": "keep",
                            "evidence_text_short": "Keep Pressure One.",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    plan_reports = tmp_path / "plan_reports"
    plan_reports.mkdir()
    (plan_reports / "guide_claim_bundle.json").write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "override_runtime_claim",
                        "claim_kind": "targeting_rule",
                        "cards": ["EX1_002"],
                        "stance": "prefer_enemy_hero",
                        "runtime_block": "BeforePlayCardBonus",
                        "runtime_value": "12",
                        "claim_readiness": "explicit",
                        "trust_ceiling": "runtime_candidate",
                        "source_confidence": "high",
                        "source_family": "guide",
                        "source_title": "Override Guide",
                        "evidence_text_short": "Use Burst Two as the override source claim.",
                    }
                ],
                "unsupported_claims": [],
                "source_evidence_index": [],
                "coverage": {
                    "guide_backed_cards": 1,
                    "uncovered_cards": ["EX1_001"],
                    "summary": {
                        "guide_backed": 1,
                        "static_semantics_backfilled": 0,
                        "uncovered_low_confidence": 1,
                    },
                    "cards": {
                        "EX1_001": {"coverage_status": "uncovered_low_confidence"},
                        "EX1_002": {"coverage_status": "guide_backed"},
                    },
                },
                "claim_coverage_report": {
                    "guide_backed_cards": 1,
                    "uncovered_cards": ["EX1_001"],
                    "summary": {
                        "guide_backed": 1,
                        "static_semantics_backfilled": 0,
                        "uncovered_low_confidence": 1,
                    },
                    "cards": {
                        "EX1_001": {"coverage_status": "uncovered_low_confidence"},
                        "EX1_002": {"coverage_status": "guide_backed"},
                    },
                },
                "claim_conflict_report": {"conflict_count": 0, "conflicts": []},
            }
        ),
        encoding="utf-8",
    )
    (plan_reports / "mulligan_plan_report.json").write_text(
        json.dumps(
            {
                "deck_name": "Plan Override",
                "rules": [],
                "quality": {"blocked_reason": "no_source_backed_mulligan_keeps"},
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Plan Override",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--guide-sources-json",
            str(guide_sources),
            "--plan-reports-dir",
            str(plan_reports),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    mulligan = json.loads(
        (out / "CustomConfig" / "plan_override" / "Mulligan.json").read_text(encoding="utf-8")
    )
    guide_claim_bundle = json.loads(
        (out / "reports" / "guide_claim_bundle.json").read_text(encoding="utf-8")
    )
    source_contract_audit = json.loads(
        (out / "reports" / "source_contract_audit.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert mulligan["Mulligan"]["values"] == []
    assert [claim["claim_id"] for claim in guide_claim_bundle["claims"]] == [
        "override_runtime_claim"
    ]
    assert [row["claim_id"] for row in source_contract_audit["claim_lifecycle_rows"]] == [
        "override_runtime_claim"
    ]


def test_command_common_emit_result_prints_json(capsys):
    code = emit_result({"status": "OK", "deck": "ShadowPriest"}, as_json=True, code=0)

    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"deck": "ShadowPriest", "status": "OK"}


def test_command_common_run_payload_command_wraps_exceptions(capsys):
    def boom(args):
        raise ValueError("broken command")

    code = run_payload_command(argparse.Namespace(json=True), boom)

    assert code == 1
    assert json.loads(capsys.readouterr().out) == {
        "errors": ["broken command"],
        "status": "failed",
    }


def test_apply_command_module_no_longer_imports_hsconfig_cli():
    text = Path("src/hsconfig/commands/apply.py").read_text(encoding="utf-8")

    assert "from hsconfig.cli import" not in text


def test_source_workflow_command_module_no_longer_imports_hsconfig_cli():
    text = Path("src/hsconfig/commands/source_workflow.py").read_text(encoding="utf-8")

    assert "from hsconfig.cli import" not in text


def test_prepare_command_module_no_longer_imports_hsconfig_cli():
    text = Path("src/hsconfig/commands/prepare.py").read_text(encoding="utf-8")

    assert "from hsconfig.cli import" not in text


def test_package_builder_does_not_import_command_modules():
    text = Path("src/hsconfig/package_builder.py").read_text(encoding="utf-8")

    assert "from hsconfig.commands" not in text


def test_cli_no_longer_owns_package_builder():
    text = Path("src/hsconfig/cli.py").read_text(encoding="utf-8")

    assert "def _build_preconfig_context(" not in text
    assert "def _prepare(" not in text
    assert "def _build(" not in text
