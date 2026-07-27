import argparse
import json
import re
import tomllib
from pathlib import Path

import pytest

from hsconfig.commands.common import emit_result, run_payload_command
from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.cli import main
from hsconfig.deck_identity import stable_deck_fingerprint
from hsconfig.cli_parser import build_parser
from hsconfig.input_loading import guide_documents_from_legacy_claims
from hsconfig.package_builder import _filter_globalvalues_authority_matrix
from hsconfig.source_document_model import globalvalues_claim_signature
from tests.helpers.verified_deck_input import (
    VERIFIED_CARD_DBF_IDS,
    deck_code_for_cards,
    verified_roster_for_card_ids,
)


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_cli_parser_subcommands_match_main_dispatch_commands():
    parser = build_parser()
    subparser_action = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    registered_commands = set(subparser_action.choices)
    dispatch_source = Path("src/hsconfig/cli.py").read_text(encoding="utf-8")
    dispatched_commands = set(re.findall(r'args\.command == "([^"]+)"', dispatch_source))

    assert registered_commands == dispatched_commands


def _write_cards_json(path: Path, card_ids: list[str]) -> list[dict]:
    if all(card_id in VERIFIED_CARD_DBF_IDS for card_id in card_ids):
        roster = verified_roster_for_card_ids(card_ids)
    else:
        roster = [
            {
                "card_id": card_id,
                "dbf_id": index,
                "count": 1,
                "name": f"Fixture {card_id}",
            }
            for index, card_id in enumerate(card_ids, start=1)
        ]
    path.write_text(
        json.dumps({"cards": roster}),
        encoding="utf-8",
    )
    return roster


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


def _canonical_globalvalues_baseline_row() -> dict:
    return {
        "key": "baseline",
        "overlay": "none",
        "operation": "none",
        "value": None,
        "authority": "baseline_default",
        "key_authority": {
            "key": "baseline",
            "category": "copy_baseline",
            "board_value_component": "baseline",
        },
        "claim_refs": [],
        "reason": "no_source_backed_posture_overlay",
    }


def _write_minimal_source_documents(
    path: Path,
    card_id: str = "EX1_001",
    *,
    claim_id: str | None = None,
) -> None:
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
                                **({"claim_id": claim_id} if claim_id else {}),
                                "claim_kind": "targeting_rule",
                                "cards": [card_id],
                                "stance": "prefer_enemy_hero",
                                "target_scope": "enemy_hero",
                                "runtime_block": "BeforeBattlecryTargetBonus",
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


def _write_conflicting_target_source_documents(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/conflict-guide",
                        "source_title": "Canonical conflict guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-26T00:00:00Z",
                        "claims": [
                            {
                                "claim_id": "valid_runtime_target",
                                "claim_kind": "targeting_rule",
                                "cards": ["EX1_001"],
                                "stance": "prefer_enemy_hero",
                                "target_scope": "enemy_hero",
                                "runtime_block": "BeforeBattlecryTargetBonus",
                                "runtime_value": "12",
                                "source_confidence": "high",
                                "evidence_text_short": (
                                    "Use the valid card as a runtime target."
                                ),
                            },
                            {
                                "claim_id": "conflict_target",
                                "claim_kind": "targeting_rule",
                                "cards": ["EX1_002"],
                                "stance": "prefer_enemy_hero",
                                "target_scope": "enemy_hero",
                                "runtime_block": "BeforeBattlecryTargetBonus",
                                "runtime_value": "12",
                                "source_confidence": "high",
                                "evidence_text_short": (
                                    "A canonical conflicting target row."
                                ),
                            },
                            {
                                "claim_id": "conflict_target_opposed",
                                "claim_kind": "targeting_rule",
                                "cards": ["EX1_002"],
                                "stance": "prefer_friendly_minion",
                                "target_scope": "friendly_minion",
                                "runtime_block": "BeforeBattlecryTargetBonus",
                                "runtime_value": "-12",
                                "source_confidence": "high",
                                "evidence_text_short": (
                                    "The opposing canonical target row."
                                ),
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_noncanonical_globalvalues_plan_row_preserves_attempted_operation_and_value():
    result = _filter_globalvalues_authority_matrix(
        {
            "allowed_step1_overlays": [
                {
                    "key": "GlobalHeroHealth",
                    "operation": "set",
                    "overlay": "set:999",
                    "value": "999",
                    "authority": "step1_source_backed_posture",
                    "claim_id": "forged-plan-posture",
                    "claim_refs": ["forged-plan-posture"],
                    "reason": "forged_imported_value",
                }
            ]
        },
        canonical_matrix={
            "allowed_step1_overlays": [
                {
                    "key": "baseline",
                    "operation": "none",
                    "overlay": "none",
                    "value": None,
                    "authority": "baseline_default",
                    "claim_refs": [],
                    "reason": "no_source_backed_posture_overlay",
                }
            ],
            "blocked_until_runtime_evidence": [],
        },
        diagnostic_matrix={"blocked_until_runtime_evidence": []},
    )

    suppression = result["blocked_until_runtime_evidence"][0]
    assert suppression["key"] == "GlobalHeroHealth"
    assert suppression["operation"] == "set"
    assert suppression["overlay"] == "set:999"
    assert suppression["value"] == "999"
    assert suppression["claim_id"] == "forged-plan-posture"
    assert suppression["claim_refs"] == ["forged-plan-posture"]


def test_malicious_baseline_plan_row_is_visibly_suppressed_without_runtime_authority():
    canonical_baseline = _canonical_globalvalues_baseline_row()

    result = _filter_globalvalues_authority_matrix(
        {
            "allowed_step1_overlays": [
                {
                    "key": "baseline",
                    "operation": "set",
                    "overlay": "set:999",
                    "value": "999",
                    "authority": "step1_source_backed_posture",
                    "claim_id": "evil",
                    "claim_refs": ["evil"],
                    "reason": "forged_baseline_value",
                }
            ]
        },
        canonical_matrix={
            "allowed_step1_overlays": [canonical_baseline],
            "blocked_until_runtime_evidence": [],
        },
        diagnostic_matrix={"blocked_until_runtime_evidence": []},
    )

    assert result["allowed_step1_overlays"] == [canonical_baseline]
    assert result["blocked_until_runtime_evidence"] == [
        {
            "key": "baseline",
            "operation": "set",
            "overlay": "set:999",
            "value": "999",
            "authority": "source_contract_suppressed",
            "claim_id": "evil",
            "claim_refs": ["evil"],
            "reason": "globalvalues_plan_row_not_canonical",
            "blocked_reason": "globalvalues_plan_row_not_canonical",
        }
    ]


def _write_exact_posture_source_document(
    path: Path,
    *,
    fingerprint: str,
    card_id: str = "EX1_001",
    source_family: str = "guide",
    source_type: str = "public_guide",
    provenance: str | None = None,
    claim_id: str | None = None,
) -> None:
    source_identity = {"source_type": source_type}
    if provenance is not None:
        source_identity["provenance"] = provenance
    path.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/exact-guide",
                        "source_title": "Exact deck public guide",
                        "source_family": source_family,
                        **source_identity,
                        "retrieved_at": "2026-07-26T00:00:00Z",
                        "source_visibility": "full_text",
                        "source_lane": "deck_matched_public_guide",
                        "deck_match_scope": "exact_deck_matched",
                        "deck_match": {
                            "exact_deck_evidence": {
                                "candidate_count": 1,
                                "decoded_candidate_count": 1,
                                "matched": True,
                                "matched_deck_fingerprint": fingerprint,
                                "candidate_deck_code_hashes": ["sha256:source-code"],
                            }
                        },
                        "claims": [
                            {
                                **({"claim_id": claim_id} if claim_id else {}),
                                "claim_kind": "gameplan_posture",
                                "cards": [card_id],
                                "scope": "deck",
                                "stance": "aggressive",
                                "evidence_text_short": "Play an aggressive exact-deck plan.",
                                "source_confidence": "high",
                                "promotion_eligible": True,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _write_canonical_runtime_plan_source_document(
    path: Path,
    *,
    fingerprint: str,
) -> None:
    path.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/canonical-plan-guide",
                        "source_title": "Canonical Plan Guide",
                        "source_family": "guide",
                        "source_type": "public_guide",
                        "retrieved_at": "2026-07-26T00:00:00Z",
                        "source_visibility": "full_text",
                        "source_lane": "deck_matched_public_guide",
                        "deck_match_scope": "exact_deck_matched",
                        "deck_match": {
                            "exact_deck_evidence": {
                                "candidate_count": 1,
                                "decoded_candidate_count": 1,
                                "matched": True,
                                "matched_deck_fingerprint": fingerprint,
                                "candidate_deck_code_hashes": [
                                    "sha256:canonical-plan-source-code"
                                ],
                            }
                        },
                        "claims": [
                            {
                                "claim_id": "canonical-mulligan",
                                "claim_kind": "mulligan_keep",
                                "cards": ["EX1_001"],
                                "scope": "card",
                                "stance": "keep",
                                "condition": "*",
                                "promotion_eligible": True,
                                "evidence_text_short": (
                                    "Keep Fixture EX1_001 in the opening hand."
                                ),
                                "source_confidence": "high",
                            },
                            {
                                "claim_id": "canonical-card",
                                "claim_kind": "card_role",
                                "cards": ["EX1_002"],
                                "scope": "card",
                                "stance": "prioritize_in_hand",
                                "runtime_block": "InHandBonus",
                                "runtime_value": "13",
                                "evidence_text_short": (
                                    "Prioritize EX1_002 while it is in hand."
                                ),
                                "source_confidence": "high",
                            },
                            {
                                "claim_id": "canonical-suppressed-card",
                                "claim_kind": "known_bad_pattern",
                                "cards": ["EX1_003"],
                                "scope": "card",
                                "stance": "avoid_without_runtime_surface",
                                "evidence_text_short": (
                                    "Avoid the documented pattern for EX1_003."
                                ),
                                "source_confidence": "high",
                            },
                            {
                                "claim_id": "canonical-combo",
                                "claim_kind": "combo_sequence",
                                "cards": ["EX1_001", "EX1_002"],
                                "sequence": ["EX1_001", "EX1_002"],
                                "scope": "card",
                                "stance": "ordered_combo_sequence",
                                "operator": ">>",
                                "values": ["7", "9"],
                                "timing_kind": "same_turn",
                                "condition": "*",
                                "evidence_text_short": (
                                    "Play EX1_001 before EX1_002 in the same turn."
                                ),
                                "source_confidence": "high",
                                "promotion_eligible": True,
                            },
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
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    derivation = json.loads(
        (out / "package_derivation_receipt.json").read_text(encoding="utf-8")
    )
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
    assert manifest["deck_input_verification"] == operator["deck_input_verification"]
    assert operator["deck_input_verification"]["status"] == "decoded_from_deck_code"
    assert operator["deck_input_verification"]["runtime_apply_eligible"] is True
    assert "deck_input_verification" in derivation["inputs"]
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


def test_configure_keeps_unverified_cards_diagnostic_but_blocks_apply_before_write_prep(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    diagnostic_out = tmp_path / "diagnostic"

    diagnostic_code = main(
        [
            "configure",
            "--deck-name",
            "Diagnostic Cards",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(diagnostic_out),
            "--cards-json",
            str(cards_json),
            "--json",
        ]
    )
    diagnostic_payload = json.loads(capsys.readouterr().out)
    package = diagnostic_out / "04_package"
    manifest = json.loads(
        (package / "reports" / "input_manifest.json").read_text(encoding="utf-8")
    )
    operator = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )

    assert diagnostic_code == 0
    assert diagnostic_payload["status"] == "OK"
    assert manifest["deck_input_verification"] == operator["deck_input_verification"]
    assert operator["deck_input_verification"]["status"] == "cards_json_unverified"
    assert operator["deck_input_verification"]["runtime_apply_eligible"] is False
    assert operator["runtime_apply_allowed"] is False

    def fail_if_write_prep_is_reached(*_args, **_kwargs):
        raise AssertionError("runtime write preparation must not be reached")

    monkeypatch.setattr(
        "hsconfig.runtime_apply._single_config_dir",
        fail_if_write_prep_is_reached,
    )
    monkeypatch.setattr(
        "hsconfig.runtime_apply._snapshot_existing_runtime_target",
        fail_if_write_prep_is_reached,
    )
    apply_out = tmp_path / "apply"
    apply_code = main(
        [
            "configure",
            "--deck-name",
            "Diagnostic Cards",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(apply_out),
            "--cards-json",
            str(cards_json),
            "--apply",
            "--json",
        ]
    )
    apply_payload = json.loads(capsys.readouterr().out)

    assert apply_code == 1
    assert apply_payload["status"] == "failed"
    assert apply_payload["stage"] == "apply"
    assert "deck_input_not_verified" in json.dumps(apply_payload)
    assert not (tmp_path / "runtime").exists()


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
    for text in (
        "Card behavior surface damage row without targeting guidance.",
        "Card behavior surface damage row without target guidance.",
    ):
        documents = guide_documents_from_legacy_claims(
            [
                {
                    "source": "guide",
                    "url": "https://example.invalid/deck-guide",
                    "claim": text,
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


def test_legacy_claims_still_match_minion_targeting_scope():
    documents = guide_documents_from_legacy_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/deck-guide",
                "claim": "Target an enemy minion with this removal effect.",
                "cards": ["EX1_001"],
            }
        ]
    )

    claim = documents[0]["claims"][0]

    assert claim["claim_kind"] == "targeting_rule"
    assert claim["stance"] == "deck_card"


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


def test_build_accepts_claims_json_without_minting_mulligan_authority(
    tmp_path: Path, capsys
):
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
    deck_fingerprint = stable_deck_fingerprint(
        [("EX1_001", 2), ("EX1_002", 1)]
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
                    "promotion_eligible": True,
                    "source_visibility": "full_text",
                    "source_lane": "deck_matched_public_guide",
                    "deck_match_scope": "exact_deck_matched",
                    "deck_match": {
                        "exact_deck_evidence": {
                            "matched": True,
                            "matched_deck_fingerprint": deck_fingerprint,
                        }
                    },
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
    source_contract_audit = json.loads(
        (reports / "source_contract_audit.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert archetype_research["confidence"] == "guide_backed"
    assert card_role_map["EX1_001"]["confidence"] == "guide_backed"
    assert mulligan_anchor_map["EX1_001"]["intent"] == "neutral"
    assert globalvalue_intent["pressure_bias"] == "high"
    assert mulligan["Mulligan"]["values"][0]["mulligan"] == "EX1_001"
    assert not (deck_dir / "Combo.json").exists()
    assert combo_plan["combos"] == []
    assert combo_suppressions == combo_plan["suppressed"]
    assert combo_suppressions == []
    combo_claim = next(
        row
        for row in source_contract_audit["claim_rows"].values()
        if row["claim_kind"] == "combo_sequence"
    )
    assert combo_claim["surfaces"]["combo"]["reason"] == (
        "combo_requires_exact_deck_match"
    )
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
    roster = [
        {
            "card_id": "EX1_001",
            "dbf_id": 1655,
            "count": 2,
            "name": "Pressure One",
        }
    ]
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps({"cards": roster}),
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
            deck_code_for_cards(roster),
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


def test_build_ignores_plan_claim_bundle_when_computing_source_depth(
    tmp_path: Path,
    capsys,
):
    roster = [
        {
            "card_id": "EX1_001",
            "dbf_id": 1655,
            "count": 2,
            "name": "Pressure One",
        }
    ]
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps({"cards": roster}),
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
            deck_code_for_cards(roster),
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
    plan_diagnostics = json.loads(
        (reports / "plan_input_diagnostics.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert receipt["source_depth_status"] == "source_backed"
    assert depth["summary"]["report_only_claims"] == 0
    assert depth["source_depth_status"] == "static_semantics_only"
    assert operator_summary["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert plan_diagnostics["ignored_claims"] == [
        {
            "claim_id": "claim_report_only_runtime",
            "claim_kind": "targeting_rule",
            "reason": "plan_claim_not_canonical_source_truth",
            "runtime_gate_impact": "none",
        }
    ]
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_mode"] == "blocked"
    assert operator_summary["runtime_apply_allowed"] is False


def test_build_plan_reports_dir_filters_stale_report_only_runtime_rows(
    tmp_path: Path, capsys
):
    cards_json = tmp_path / "cards.json"
    card_ids = ["EX1_001", "EX1_002", "EX1_004", "EX1_005", "EX1_006", "EX1_007"]
    roster = _write_cards_json(cards_json, card_ids)
    source_documents = tmp_path / "source_documents.json"
    _write_minimal_source_documents(
        source_documents,
        claim_id="valid_runtime_target",
    )
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
                    "cards": ["EX1_004"],
                    "claim_readiness": "explicit_low_confidence",
                    "trust_ceiling": "report_only",
                    "source_confidence": "low",
                    "evidence_text_short": "A stale low-confidence mulligan row.",
                },
                {
                    "claim_id": "rejected_combo",
                    "claim_kind": "combo_sequence",
                    "cards": ["EX1_005", "EX1_006"],
                    "sequence": ["EX1_005", "EX1_006"],
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
                "card": "EX1_004",
                "selector_kind": "card",
                "selector": "EX1_004",
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
                "card_id": "EX1_007",
                "surface_family": "CARDID.json",
                "surface": "CardID.json",
                "behavior_block": "BeforePlayCardBonus",
                "meaningful_runtime_surface": True,
            },
        ],
        combo_rows=[
            {
                "rule_id": "rejected_combo",
                "cards": ["EX1_005", "EX1_006"],
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
            deck_code_for_cards(roster),
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
        (deck_dir / "EX1_007.json").read_text(encoding="utf-8")
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
    ignored_plan_claims = {
        row["claim_id"]: row
        for row in source_contract_audit["plan_input_diagnostics"][
            "ignored_claims"
        ]
    }

    assert code == 0
    assert payload["status"] == "passed"
    assert "BeforeBattlecryTargetBonus" not in valid_card
    assert "BeforePlayCardBonus" not in report_only_card
    assert "BeforePlayCardBonus" not in unreferenced_card
    assert not any(
        row.get("mulligan") == "EX1_004" for row in mulligan["Mulligan"]["values"]
    )
    assert not (deck_dir / "Combo.json").exists()
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_allowed"] is False
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert (
        lifecycle_by_id["valid_runtime_target"]["builder_or_router_decision"]
        != "emitted"
    )
    for claim_id in (
        "report_only_target",
        "low_confidence_keep",
        "rejected_combo",
    ):
        assert claim_id not in lifecycle_by_id
        assert ignored_plan_claims[claim_id]["reason"] == (
            "plan_claim_not_canonical_source_truth"
        )


def test_build_plan_reports_dir_suppresses_noncanonical_globalvalues_overlay(
    tmp_path: Path, capsys
):
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    source_documents = tmp_path / "source_documents.json"
    _write_minimal_source_documents(source_documents)
    plan_reports = tmp_path / "plan_reports"
    _write_plan_override_reports(
        plan_reports,
        guide_claim_bundle=_claim_bundle_for_override(
            card_ids=["EX1_001"],
            claims=[
                {
                    "claim_id": "unverified-posture",
                    "claim_kind": "gameplan_posture",
                    "scope": "deck",
                    "stance": "aggressive",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_confidence": "high",
                    "source_type": "public_guide",
                    "source_family": "guide",
                    "deck_match_scope": "exact_deck_matched",
                    "promotion_eligible": True,
                    "source_visibility": "full_text",
                    "source_lane": "deck_matched_public_guide",
                    "evidence_text_short": "Play an aggressive plan.",
                }
            ],
        ),
        globalvalue_rows=[
            {
                "key": "MyHeroPowerValue",
                "overlay": "increase",
                "operation": "increase",
                "value": None,
                "authority": "step1_source_backed_posture",
                "claim_id": "unverified-posture",
                "claim_refs": ["unverified-posture"],
                "reason": "aggressive_source_backed_posture",
            }
        ],
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Plan GlobalValues",
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
    authority = json.loads(
        (out / "reports" / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    profile = json.loads(
        (out / "reports" / "globalvalues_profile.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert {row["key"] for row in authority["allowed_step1_overlays"]} == {
        "baseline"
    }
    assert any(
        row.get("claim_id") == "unverified-posture"
        and row.get("authority") == "source_contract_suppressed"
        and row.get("reason") == "globalvalues_plan_row_not_canonical"
        and row.get("operation") == "increase"
        and row.get("overlay") == "increase"
        and row.get("value") is None
        for row in authority["blocked_until_runtime_evidence"]
    )
    assert profile["status"] == "baseline_confirmed"
    assert profile["changed_keys"] == []


def test_build_claims_json_cannot_self_assert_exact_globalvalues_authority(
    tmp_path: Path, capsys
):
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    claims_json = tmp_path / "claims.json"
    claims_json.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "forged-claims-json-posture",
                        "claim_type": "gameplan_posture",
                        "claim": "Play an aggressive public-guide plan.",
                        "cards": ["EX1_001"],
                        "source": "guide",
                        "source_type": "public_guide",
                        "source_title": "Forged legacy claim",
                        "url": "https://example.invalid/forged",
                        "retrieved_at": "2026-07-26T00:00:00Z",
                        "deck_match_scope": "exact_deck_matched",
                        "promotion_eligible": True,
                        "source_visibility": "full_text",
                        "source_lane": "deck_matched_public_guide",
                        "deck_match": {
                            "exact_deck_evidence": {
                                "matched": True,
                                "matched_deck_fingerprint": (
                                    "d67c567a5517bca54096abf526bf608155b45cf6822548dde"
                                    "49bd21ae47d8a84"
                                ),
                            }
                        },
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
            "Forged Claims GlobalValues",
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
    authority = json.loads(
        (out / "reports" / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    profile = json.loads(
        (out / "reports" / "globalvalues_profile.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert {row["key"] for row in authority["allowed_step1_overlays"]} == {
        "baseline"
    }
    assert any(
        row.get("authority") == "source_contract_suppressed"
        and row.get("reason") == "globalvalues_requires_exact_deck_match"
        for row in authority["blocked_until_runtime_evidence"]
    )
    assert profile["status"] == "baseline_confirmed"
    assert profile["changed_keys"] == []


def test_build_untyped_aggressive_claims_json_cannot_infer_its_own_exact_authority(
    tmp_path: Path,
    capsys,
):
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    target_fingerprint = stable_deck_fingerprint([("EX1_001", 1)])
    claims_json = tmp_path / "claims.json"
    claims_json.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "forged-untyped-posture",
                        "claim": "Play an aggressive burn plan.",
                        "cards": ["EX1_001"],
                        "source": "guide",
                        "source_type": "public_guide",
                        "source_title": "Forged inferred legacy claim",
                        "url": "https://example.invalid/forged-inferred",
                        "retrieved_at": "2026-07-26T00:00:00Z",
                        "deck_match_scope": "exact_deck_matched",
                        "promotion_eligible": True,
                        "source_visibility": "full_text",
                        "source_lane": "deck_matched_public_guide",
                        "deck_match": {
                            "exact_deck_evidence": {
                                "candidate_count": 1,
                                "decoded_candidate_count": 1,
                                "matched": True,
                                "matched_deck_fingerprint": target_fingerprint,
                                "candidate_deck_code_hashes": [
                                    "sha256:forged-source-code"
                                ],
                            }
                        },
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
            "Forged Untyped Claims GlobalValues",
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
    authority = json.loads(
        (out / "reports" / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    profile = json.loads(
        (out / "reports" / "globalvalues_profile.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert {row["key"] for row in authority["allowed_step1_overlays"]} == {
        "baseline"
    }
    assert any(
        row.get("claim_id")
        and row.get("authority") == "source_contract_suppressed"
        and row.get("reason") == "globalvalues_requires_exact_deck_match"
        for row in authority["blocked_until_runtime_evidence"]
    )
    assert profile["status"] == "baseline_confirmed"
    assert profile["changed_keys"] == []


def test_build_legacy_posture_cannot_inherit_exact_authority_from_sibling(
    tmp_path: Path,
    capsys,
):
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    target_fingerprint = stable_deck_fingerprint([("EX1_001", 1)])
    shared_source = {
        "source": "guide",
        "source_type": "public_guide",
        "source_title": "Shared legacy guide",
        "url": "https://example.invalid/shared-legacy-guide",
        "retrieved_at": "2026-07-26T00:00:00Z",
    }
    claims_json = tmp_path / "claims.json"
    claims_json.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        **shared_source,
                        "claim_type": "targeting_rule",
                        "claim": "Target the enemy hero.",
                        "cards": ["EX1_001"],
                        "deck_match_scope": "exact_deck_matched",
                        "promotion_eligible": True,
                        "source_visibility": "full_text",
                        "source_lane": "deck_matched_public_guide",
                        "deck_match": {
                            "exact_deck_evidence": {
                                "candidate_count": 1,
                                "decoded_candidate_count": 1,
                                "matched": True,
                                "matched_deck_fingerprint": target_fingerprint,
                                "candidate_deck_code_hashes": [
                                    "sha256:shared-source-code"
                                ],
                            }
                        },
                    },
                    {
                        **shared_source,
                        "claim": "Use aggressive burn pressure.",
                        "cards": ["EX1_001"],
                    },
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
            "Legacy Sibling Isolation",
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
    claim_bundle = json.loads(
        (out / "reports" / "guide_claim_bundle.json").read_text(
            encoding="utf-8"
        )
    )
    authority = json.loads(
        (out / "reports" / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    profile = json.loads(
        (out / "reports" / "globalvalues_profile.json").read_text(
            encoding="utf-8"
        )
    )
    claims_by_kind = {
        claim["claim_kind"]: claim for claim in claim_bundle["claims"]
    }
    posture_claim = claims_by_kind["gameplan_posture"]
    targeting_claim = claims_by_kind["targeting_rule"]
    receipt_claim_ids = {
        receipt["claim_id"]
        for receipt in claim_bundle["globalvalues_source_receipts"]
    }

    assert code == 0
    assert payload["status"] == "passed"
    assert targeting_claim["claim_id"] not in receipt_claim_ids
    assert posture_claim["claim_id"] not in receipt_claim_ids
    assert authority["allowed_step1_overlays"] == [
        _canonical_globalvalues_baseline_row()
    ]
    assert any(
        row.get("claim_id") == posture_claim["claim_id"]
        and row.get("authority") == "source_contract_suppressed"
        and row.get("reason") == "globalvalues_requires_exact_deck_match"
        for row in authority["blocked_until_runtime_evidence"]
    )
    assert profile["status"] == "baseline_confirmed"
    assert profile["changed_keys"] == []


def test_build_contradictory_source_identity_vetoes_globalvalues_public_guide(
    tmp_path: Path, capsys
):
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    source_documents = tmp_path / "source_documents.json"
    _write_exact_posture_source_document(
        source_documents,
        fingerprint=(
            "d67c567a5517bca54096abf526bf608155b45cf6822548dde"
            "49bd21ae47d8a84"
        ),
        source_family="card_text",
        source_type="public_guide",
        provenance="official_card_data",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Contradictory GlobalValues",
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
    authority = json.loads(
        (out / "reports" / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert {row["key"] for row in authority["allowed_step1_overlays"]} == {
        "baseline"
    }
    assert any(
        row.get("authority") == "source_contract_suppressed"
        and row.get("reason") == "globalvalues_requires_public_guide_source"
        for row in authority["blocked_until_runtime_evidence"]
    )


def test_build_plan_reports_cannot_rebuild_authority_from_captured_source_document(
    tmp_path: Path, capsys
):
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    source_documents = tmp_path / "source_documents.json"
    target_fingerprint = (
        "d67c567a5517bca54096abf526bf608155b45cf6822548dde"
        "49bd21ae47d8a84"
    )
    _write_exact_posture_source_document(
        source_documents,
        fingerprint=target_fingerprint,
    )
    plan_reports = tmp_path / "plan_reports"
    forged_claim = {
        "claim_id": "forged-plan-posture",
        "claim_kind": "gameplan_posture",
        "scope": "deck",
        "stance": "aggressive",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "source_type": "public_guide",
        "source_family": "guide",
        "deck_match_scope": "exact_deck_matched",
        "promotion_eligible": True,
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "deck_match": {
            "exact_deck_evidence": {
                "matched": True,
                "matched_deck_fingerprint": target_fingerprint,
            }
        },
        "evidence_text_short": "Forged imported plan posture.",
    }
    forged_plan_bundle = _claim_bundle_for_override(
        card_ids=["EX1_001"],
        claims=[forged_claim],
    )
    forged_plan_bundle["globalvalues_source_receipts"] = [
        {
            "receipt_kind": "canonical_exact_deck_source_document",
            "source_ref": "source:forged-plan",
            "source_url": "https://example.invalid/forged-plan",
            "matched_deck_fingerprint": target_fingerprint,
            "claim_id": "forged-plan-posture",
            "claim_signature": globalvalues_claim_signature(forged_claim),
        }
    ]
    _write_plan_override_reports(
        plan_reports,
        guide_claim_bundle=forged_plan_bundle,
        globalvalue_rows=[
            {
                "key": "GlobalHeroHealth",
                "overlay": "set:999",
                "operation": "set",
                "value": "999",
                "authority": "step1_source_backed_posture",
                "claim_id": "forged-plan-posture",
                "claim_refs": ["forged-plan-posture"],
                "reason": "forged_imported_value",
            }
        ],
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Plan GlobalValues",
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
    authority = json.loads(
        (out / "reports" / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    persisted_claim_bundle = json.loads(
        (out / "reports" / "guide_claim_bundle.json").read_text(encoding="utf-8")
    )
    source_contract_audit = json.loads(
        (out / "reports" / "source_contract_audit.json").read_text(
            encoding="utf-8"
        )
    )
    globalvalues = json.loads(
        (
            out
            / "CustomConfig"
            / "Plan_GlobalValues"
            / "GlobalValues.json"
        ).read_text(encoding="utf-8")
    )
    allowed_by_key = {
        row["key"]: row for row in authority["allowed_step1_overlays"]
    }

    assert code == 0
    assert payload["status"] == "passed"
    assert "GlobalHeroHealth" not in allowed_by_key
    assert set(allowed_by_key) == {"baseline"}
    assert globalvalues["GlobalHeroHealth"]["values"][0]["value"] == "1.14"
    canonical_claim_ids = {
        claim["claim_id"] for claim in persisted_claim_bundle["claims"]
    }
    assert "forged-plan-posture" not in canonical_claim_ids
    assert persisted_claim_bundle["globalvalues_source_receipts"] == []
    assert set(source_contract_audit["claim_rows"]) == canonical_claim_ids
    assert {
        row["claim_id"] for row in source_contract_audit["claim_lifecycle_rows"]
    } == canonical_claim_ids
    ignored_claims = source_contract_audit["plan_input_diagnostics"][
        "ignored_claims"
    ]
    imported_plan_claims = source_contract_audit["plan_input_diagnostics"][
        "imported_claims"
    ]
    imported_plan_receipts = source_contract_audit["plan_input_diagnostics"][
        "imported_source_receipts"
    ]
    assert any(
        row.get("claim_id") == "forged-plan-posture"
        and row.get("reason") == "plan_claim_not_canonical_source_truth"
        for row in ignored_claims
    )
    assert [claim["claim_id"] for claim in imported_plan_claims] == [
        "forged-plan-posture"
    ]
    assert imported_plan_receipts == forged_plan_bundle[
        "globalvalues_source_receipts"
    ]
    suppressed_attempt = next(
        row
        for row in authority["blocked_until_runtime_evidence"]
        if row.get("reason") == "globalvalues_plan_row_not_canonical"
        and row.get("key") == "GlobalHeroHealth"
    )
    assert suppressed_attempt["operation"] == "set"
    assert suppressed_attempt["overlay"] == "set:999"
    assert suppressed_attempt["value"] == "999"
    assert suppressed_attempt["claim_id"] == "forged-plan-posture"
    assert suppressed_attempt["claim_refs"] == ["forged-plan-posture"]


def test_build_plan_reports_dir_rejects_captured_exact_globalvalues_overlay(
    tmp_path: Path, capsys
):
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    source_documents = tmp_path / "source_documents.json"
    _write_exact_posture_source_document(
        source_documents,
        fingerprint=(
            "d67c567a5517bca54096abf526bf608155b45cf6822548dde"
            "49bd21ae47d8a84"
        ),
        claim_id="verified-posture",
    )
    plan_reports = tmp_path / "plan_reports"
    _write_plan_override_reports(
        plan_reports,
        guide_claim_bundle=_claim_bundle_for_override(
            card_ids=["EX1_001"],
            claims=[
                {
                    "claim_id": "verified-posture",
                    "claim_kind": "gameplan_posture",
                    "scope": "deck",
                    "stance": "aggressive",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_confidence": "high",
                    "source_type": "public_guide",
                    "source_family": "guide",
                    "deck_match_scope": "exact_deck_matched",
                    "promotion_eligible": True,
                    "source_visibility": "full_text",
                    "source_lane": "deck_matched_public_guide",
                    "deck_match": {
                        "exact_deck_evidence": {
                            "matched": True,
                            "matched_deck_fingerprint": (
                                "d67c567a5517bca54096abf526bf608155b45cf6822548dde"
                                "49bd21ae47d8a84"
                            ),
                        }
                    },
                    "evidence_text_short": "Play an aggressive plan.",
                }
            ],
        ),
        globalvalue_rows=[
            {
                "key": "MyHeroPowerValue",
                "overlay": "increase",
                "operation": "increase",
                "value": None,
                "authority": "step1_source_backed_posture",
                "claim_id": "verified-posture",
                "claim_refs": [
                    "verified-posture",
                    "source:1",
                    "https://example.invalid/exact-guide",
                ],
                "reason": "aggressive_source_backed_posture",
            }
        ],
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Plan GlobalValues",
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
    authority = json.loads(
        (out / "reports" / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    profile = json.loads(
        (out / "reports" / "globalvalues_profile.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert "MyHeroPowerValue" not in {
        row["key"] for row in authority["allowed_step1_overlays"]
    }
    assert any(
        row.get("reason") == "globalvalues_plan_row_not_canonical"
        for row in authority["blocked_until_runtime_evidence"]
    )
    assert "MyHeroPowerValue" not in profile["changed_keys"]


def test_build_empty_plan_reports_dir_does_not_serialize_fallbacks_as_imports(
    tmp_path: Path,
    capsys,
):
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    plan_reports = tmp_path / "plan_reports"
    plan_reports.mkdir()
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Empty Plan Reports",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--plan-reports-dir",
            str(plan_reports),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    diagnostics = json.loads(
        (out / "reports" / "plan_input_diagnostics.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert diagnostics["imported_claim_count"] == 0
    assert diagnostics["imported_claims"] == []
    assert diagnostics["imported_source_receipt_count"] == 0
    assert diagnostics["imported_source_receipts"] == []
    assert diagnostics["imported_row_count"] == 0
    assert diagnostics["imported_rows"] == []
    assert diagnostics["ignored_claims"] == []


def test_build_partial_plan_reports_counts_only_rows_from_present_files(
    tmp_path: Path,
    capsys,
):
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    plan_reports = tmp_path / "plan_reports"
    plan_reports.mkdir()
    canonical_baseline = _canonical_globalvalues_baseline_row()
    (plan_reports / "global_values_authority_matrix.json").write_text(
        json.dumps(
            {
                "allowed_step1_overlays": [canonical_baseline],
                "blocked_until_runtime_evidence": [],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Partial Plan Reports",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--plan-reports-dir",
            str(plan_reports),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    diagnostics = json.loads(
        (out / "reports" / "plan_input_diagnostics.json").read_text(
            encoding="utf-8"
        )
    )
    authority = json.loads(
        (out / "reports" / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert diagnostics["imported_claim_count"] == 0
    assert diagnostics["imported_source_receipt_count"] == 0
    assert diagnostics["imported_row_count"] == 1
    assert diagnostics["imported_rows"] == [
        {
            "report": "global_values_authority_matrix.json",
            "section": "allowed_step1_overlays",
            "row": canonical_baseline,
        }
    ]
    assert not any(
        row.get("reason") == "globalvalues_plan_row_not_canonical"
        for row in authority["blocked_until_runtime_evidence"]
    )


def test_build_plan_reports_dir_filters_conflict_quarantined_runtime_rows(
    tmp_path: Path, capsys
):
    cards_json = tmp_path / "cards.json"
    card_ids = ["EX1_001", "EX1_002"]
    roster = _write_cards_json(cards_json, card_ids)
    source_documents = tmp_path / "source_documents.json"
    _write_conflicting_target_source_documents(source_documents)
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
            deck_code_for_cards(roster),
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
    assert "BeforeBattlecryTargetBonus" not in valid_card
    assert "BeforePlayCardBonus" not in quarantined_card
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_allowed"] is False
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


def test_build_claims_json_timed_combo_cannot_mint_combo_authority(
    tmp_path: Path,
    capsys,
):
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
    combo_plan = json.loads((reports / "combo_plan_report.json").read_text(encoding="utf-8"))
    combo_suppressions = json.loads(
        (reports / "combo_suppression_report.json").read_text(encoding="utf-8")
    )
    source_contract_audit = json.loads(
        (reports / "source_contract_audit.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert not (deck_dir / "Combo.json").exists()
    assert combo_plan["combos"] == []
    assert combo_suppressions == []
    combo_claim = next(
        row
        for row in source_contract_audit["claim_rows"].values()
        if row["claim_kind"] == "combo_sequence"
    )
    assert combo_claim["surfaces"]["combo"]["reason"] == (
        "combo_requires_exact_deck_match"
    )


def test_build_consumes_plan_rows_without_replacing_canonical_claim_truth(
    tmp_path: Path,
    capsys,
):
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
    plan_input_diagnostics = json.loads(
        (out / "reports" / "plan_input_diagnostics.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert [
        (row["mulligan"], row["value"])
        for row in mulligan["Mulligan"]["values"]
    ] == [
        ("EX1_001", "hold"),
        ("*", "discard"),
    ]
    canonical_claim_ids = {
        claim["claim_id"] for claim in guide_claim_bundle["claims"]
    }
    assert "override_runtime_claim" not in canonical_claim_ids
    assert {
        row["claim_id"] for row in source_contract_audit["claim_lifecycle_rows"]
    } == canonical_claim_ids
    assert plan_input_diagnostics["ignored_claims"] == [
        {
            "claim_id": "override_runtime_claim",
            "claim_kind": "targeting_rule",
            "reason": "plan_claim_not_canonical_source_truth",
            "runtime_gate_impact": "none",
        }
    ]


def test_build_imported_runtime_plans_are_full_payload_diagnostics_only(
    tmp_path: Path,
    capsys,
):
    card_ids = ["EX1_001", "EX1_002", "EX1_003", "EX1_004"]
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, card_ids)
    target_fingerprint = stable_deck_fingerprint(
        (card_id, 1) for card_id in card_ids
    )
    source_documents = tmp_path / "source_documents.json"
    _write_canonical_runtime_plan_source_document(
        source_documents,
        fingerprint=target_fingerprint,
    )
    imported_mulligan_rows = [
        {
            "card": "EX1_004",
            "selector_kind": "card",
            "selector": "EX1_004",
            "action": "hold",
            "condition": "coin",
            "reason": "imported same-id mutation",
            "claim_id": "canonical-mulligan",
            "source_claim_ids": ["canonical-mulligan"],
        },
        {
            "card": "EX1_004",
            "selector_kind": "card",
            "selector": "EX1_004",
            "action": "hold",
            "condition": "*",
            "reason": "imported no-id policy mutation",
            "source_type": "policy_backed_autonomous_mulligan",
        },
    ]
    imported_card_rows = [
        {
            "card_id": "EX1_004",
            "surface_family": "CARDID.json",
            "surface": "CARDID.json",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "coin",
            "value": "999",
            "meaningful_runtime_surface": True,
            "claim_id": "canonical-card",
            "source_claim_ids": ["canonical-card"],
        },
        {
            "card_id": "EX1_003",
            "surface_family": "CARDID.json",
            "surface": "CARDID.json",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": "777",
            "meaningful_runtime_surface": True,
            "claim_id": "canonical-suppressed-card",
            "source_claim_ids": ["canonical-suppressed-card"],
        },
    ]
    imported_combo_rows = [
        {
            "rule_id": "imported-same-id-combo",
            "cards": ["EX1_002", "EX1_001"],
            "operator": ">>",
            "values": ["99", "88"],
            "combo": "EX1_002>>EX1_001",
            "value": 99,
            "condition": "coin",
            "claim_id": "canonical-combo",
            "source_claim_ids": ["canonical-combo"],
        }
    ]
    plan_reports = tmp_path / "plan_reports"
    _write_plan_override_reports(
        plan_reports,
        guide_claim_bundle=_claim_bundle_for_override(
            card_ids=card_ids,
            claims=[],
        ),
        mulligan_rules=imported_mulligan_rows,
        card_behavior_rows=imported_card_rows,
        combo_rows=imported_combo_rows,
    )
    imported_payloads = {
        "mulligan_plan_report.json": json.loads(
            (plan_reports / "mulligan_plan_report.json").read_text(
                encoding="utf-8"
            )
        ),
        "card_behavior_plan_report.json": json.loads(
            (plan_reports / "card_behavior_plan_report.json").read_text(
                encoding="utf-8"
            )
        ),
        "combo_plan_report.json": json.loads(
            (plan_reports / "combo_plan_report.json").read_text(
                encoding="utf-8"
            )
        ),
    }
    imported_payloads["mulligan_plan_report.json"]["quality"] = {
        "status": "IMPORTED_STALE_QUALITY"
    }
    imported_payloads["mulligan_plan_report.json"]["summary"] = {
        "status": "IMPORTED_STALE_SUMMARY"
    }
    imported_payloads["card_behavior_plan_report.json"]["card_rows"] = {
        "EX1_004": [{"status": "IMPORTED_STALE_CARD_ROWS"}]
    }
    imported_payloads["card_behavior_plan_report.json"]["summary"] = {
        "status": "IMPORTED_STALE_SUMMARY"
    }
    imported_payloads["combo_plan_report.json"]["summary"] = {
        "status": "IMPORTED_STALE_SUMMARY"
    }
    for filename, payload in imported_payloads.items():
        (plan_reports / filename).write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Canonical Plan Truth",
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
    deck_dir = out / "CustomConfig" / "canonical_plan_truth"
    reports_dir = out / "reports"
    mulligan_config = json.loads(
        (deck_dir / "Mulligan.json").read_text(encoding="utf-8")
    )
    card_config = json.loads(
        (deck_dir / "EX1_002.json").read_text(encoding="utf-8")
    )
    suppressed_card_config = json.loads(
        (deck_dir / "EX1_003.json").read_text(encoding="utf-8")
    )
    mulligan_report = json.loads(
        (reports_dir / "mulligan_plan_report.json").read_text(encoding="utf-8")
    )
    card_report = json.loads(
        (reports_dir / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )
    combo_report = json.loads(
        (reports_dir / "combo_plan_report.json").read_text(encoding="utf-8")
    )
    diagnostics = json.loads(
        (reports_dir / "plan_input_diagnostics.json").read_text(
            encoding="utf-8"
        )
    )

    canonical_mulligan_rules = [
        row
        for row in mulligan_report["rules"]
        if row.get("claim_id") == "canonical-mulligan"
    ]
    canonical_card_rows = [
        row
        for row in card_report["rows"]
        if row.get("claim_id") == "canonical-card"
    ]
    canonical_combo_rows = [
        row
        for row in combo_report["combos"]
        if row.get("claim_id") == "canonical-combo"
    ]

    assert code == 0
    assert payload["status"] == "passed"
    assert canonical_mulligan_rules == []
    assert {
        (row.get("mulligan"), row.get("condition"), row.get("value"))
        for row in mulligan_config["Mulligan"]["values"]
    } == {
        ("EX1_004", "*", "hold"),
        ("*", "*", "discard"),
    }
    assert len(canonical_card_rows) == 1
    assert canonical_card_rows[0]["card_id"] == "EX1_002"
    assert canonical_card_rows[0]["behavior_block"] == "InHandBonus"
    assert card_config["InHandBonus"]["values"][0]["value"] == "13"
    assert "BeforePlayCardBonus" not in suppressed_card_config
    assert canonical_combo_rows == []
    assert not (deck_dir / "Combo.json").exists()
    assert mulligan_report["quality"]["status"] != "IMPORTED_STALE_QUALITY"
    assert "summary" not in mulligan_report
    assert "EX1_004" not in card_report["card_rows"]
    assert "summary" not in card_report
    assert "summary" not in combo_report
    assert diagnostics["imported_plan_reports"] == imported_payloads
    assert diagnostics["runtime_gate_impact"] == "none"


def test_build_legacy_claims_json_cannot_mint_source_backed_mulligan_authority(
    tmp_path: Path,
    capsys,
):
    cards_json = tmp_path / "cards.json"
    _write_cards_json(cards_json, ["EX1_001"])
    target_fingerprint = stable_deck_fingerprint([("EX1_001", 1)])
    claims_json = tmp_path / "claims.json"
    claims_json.write_text(
        json.dumps(
            [
                {
                    "claim_id": "legacy-self-declared-mulligan",
                    "source": "guide",
                    "source_type": "public_guide",
                    "source_title": "Legacy self-declared guide",
                    "url": "https://example.invalid/legacy-self-declared",
                    "retrieved_at": "2026-07-26T00:00:00Z",
                    "claim": "Mulligan: always keep Fixture EX1_001.",
                    "cards": ["EX1_001"],
                    "claim_type": "mulligan_keep",
                    "source_confidence": "high",
                    "deck_match_scope": "exact_deck_matched",
                    "promotion_eligible": True,
                    "source_visibility": "full_text",
                    "source_lane": "deck_matched_public_guide",
                    "deck_match": {
                        "exact_deck_evidence": {
                            "candidate_count": 1,
                            "decoded_candidate_count": 1,
                            "matched": True,
                            "matched_deck_fingerprint": target_fingerprint,
                            "candidate_deck_code_hashes": [
                                "sha256:legacy-self-declared"
                            ],
                        }
                    },
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
            "Legacy Mulligan Receipt",
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
    reports_dir = out / "reports"
    claim_bundle = json.loads(
        (reports_dir / "guide_claim_bundle.json").read_text(encoding="utf-8")
    )
    mulligan_report = json.loads(
        (reports_dir / "mulligan_plan_report.json").read_text(encoding="utf-8")
    )
    canonical_claim_id = claim_bundle["claims"][0]["claim_id"]

    assert code == 0
    assert payload["status"] == "passed"
    assert claim_bundle["globalvalues_source_receipts"] == []
    assert not any(
        row.get("claim_id") == canonical_claim_id
        for row in mulligan_report["rules"]
    )
    assert any(
        row.get("claim_id") == canonical_claim_id
        and row.get("reason") == "strategic_provenance_not_live_verified"
        for row in mulligan_report["suppressed_rules"]
    )


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
