import hashlib
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

import hsconfig.package_builder as package_builder
from hsconfig.cli import main
from hsconfig.cli_parser import build_parser
from hsconfig.package_builder import build_package_payload
from tests.helpers.verified_deck_input import deck_code_for_cards


# Extracted from the f83248f package builder; see the Task 12 report for the
# in-memory git-show oracle method and path normalization.
PRE_REFACTOR_PACKAGE_FILE_COUNT = 56
PRE_REFACTOR_PACKAGE_TREE_DIGEST = (
    "sha256:7969ca26ff71663648ec3d188342ce62a4ec2b896753c6ee6c10b947d2166a20"
)


def test_imported_card_behavior_conflicts_remain_diagnostic_only(
    tmp_path: Path,
    capsys,
):
    roster = [
        {
            "card_id": "REV_290",
            "dbf_id": 82310,
            "count": 1,
            "name": "Cathedral of Atonement",
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
                        "source_title": "Fixture Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-26T00:00:00Z",
                        "claims": [
                            {
                                "claim_id": "claim-a",
                                "claim_kind": "card_role",
                                "cards": ["REV_290"],
                                "stance": "deploy_location",
                                "runtime_block": "BeforePlayCardBonus",
                                "evidence_text_short": "Deploy the location.",
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
    claims = [
        {
            "claim_id": claim_id,
            "claim_kind": "card_role",
            "cards": ["REV_290"],
            "stance": "deploy_location",
            "runtime_block": "BeforePlayCardBonus",
            "runtime_value": value,
            "claim_readiness": "guide_backed",
            "trust_ceiling": "runtime_candidate",
            "source_confidence": "high",
            "evidence_text_short": "Deploy the location.",
        }
        for claim_id, value in (("claim-a", "6"), ("claim-b", "8"))
    ]
    coverage = {
        "guide_backed_cards": 1,
        "uncovered_cards": [],
        "summary": {
            "guide_backed": 1,
            "static_semantics_backfilled": 0,
            "uncovered_low_confidence": 0,
        },
        "cards": {"REV_290": {"coverage_status": "guide_backed"}},
    }
    (plan_reports / "guide_claim_bundle.json").write_text(
        json.dumps(
            {
                "claims": claims,
                "unsupported_claims": [],
                "source_evidence_index": [],
                "coverage": coverage,
                "claim_coverage_report": coverage,
                "claim_conflict_report": {"conflict_count": 0, "conflicts": []},
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "card_id": "REV_290",
            "surface_family": "CARDID.json",
            "surface": "CardID.json",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": value,
            "claim_id": "claim-a",
            "source_claim_ids": ["claim-a"],
            "meaningful_runtime_surface": True,
        }
        for value in ("6", "8")
    ]
    reports = {
        "mulligan_plan_report.json": {
            "deck_name": "Compiler Conflict",
            "rules": [],
            "suppressed_rules": [],
        },
        "card_behavior_plan_report.json": {
            "card_rows": {"REV_290": rows},
            "rows": rows,
            "suppressed": [],
            "option_resolution": [],
            "merged_duplicate_runtime_row_count": 0,
            "runtime_row_conflicts": [],
        },
        "combo_plan_report.json": {"combos": [], "suppressed": []},
        "global_values_authority_matrix.json": {
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
    }
    for filename, payload in reports.items():
        (plan_reports / filename).write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    package = tmp_path / "package"
    code = main(
        [
            "build",
            "--deck-name",
            "Compiler Conflict",
            "--deck-code",
            deck_code_for_cards(roster),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(source_documents),
            "--plan-reports-dir",
            str(plan_reports),
            "--json",
        ]
    )
    capsys.readouterr()

    persisted = json.loads(
        (package / "reports" / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )
    physical = json.loads(
        (
            package
            / "CustomConfig"
            / "compiler_conflict"
            / "REV_290.json"
        ).read_text(encoding="utf-8")
    )
    operator = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    diagnostics = json.loads(
        (package / "reports" / "plan_input_diagnostics.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert persisted["runtime_row_conflicts"] == []
    assert persisted["compiler_runtime_row_conflicts"] == []
    assert persisted["compiler_merged_duplicate_runtime_row_count"] == 0
    assert diagnostics["imported_plan_reports"][
        "card_behavior_plan_report.json"
    ] == reports["card_behavior_plan_report.json"]
    assert diagnostics["runtime_gate_impact"] == "none"
    assert set(physical) == {
        "GameCardId",
        "ConfigComment",
        "BeforePlayCardBonus",
    }
    assert len(persisted["rows"]) == 1
    assert physical["BeforePlayCardBonus"]["values"][0]["value"] == (
        persisted["rows"][0]["value"]
    )
    assert operator["runtime_apply_allowed"] is False
    assert operator["runtime_apply_mode"] == "blocked"


def test_package_stage_digests_preserve_public_payload_and_artifact_tree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observed_stages: list[tuple[str, str]] = []
    package, observed_payload, observed_status = _build_stage_fixture(
        tmp_path,
        monkeypatch,
        stage_observer=lambda name, digest: observed_stages.append((name, digest)),
    )
    observed_tree = _semantic_tree(package)

    assert observed_status == 0
    assert observed_payload["status"] == "passed"
    assert len(observed_tree) == PRE_REFACTOR_PACKAGE_FILE_COUNT
    assert _semantic_tree_digest(observed_tree) == PRE_REFACTOR_PACKAGE_TREE_DIGEST
    assert observed_stages == [
        (
            "verified_deck",
            "sha256:71c304fb7ebc0305c4177d96330d9769dff5f3a362f7063a0ab950a7e10a5582",
        ),
        (
            "normalized_source",
            "sha256:dd77ffe098982b5b9d86e12a14cb22f769b3fbc431bbbc0cc01e782be2a6e5e4",
        ),
        (
            "claim_surfaces",
            "sha256:a796e382f3f3312770b1da4268fad322de504b5d4adda9f8a574827536a699ff",
        ),
        (
            "lowered_runtime",
            "sha256:738ff121e26e4f5169f5887224842b15228edf98337a613a7d935fbad95d6c7a",
        ),
        (
            "validated_authority",
            "sha256:3e450a60fe4b3bb6452732f633c577953475cf8ff352b964c8465faa3e066c88",
        ),
        (
            "artifact_writing",
            "sha256:3c5fd9982ba17f095895ddc5b598031a696c899ffe8e7eab1d6d2ffd11544c0c",
        ),
    ]


@pytest.mark.parametrize("failure_type", [RuntimeError, SystemExit])
def test_package_stage_observer_failures_are_diagnostic_only_at_every_boundary(
    tmp_path: Path,
    monkeypatch,
    failure_type: type[BaseException],
) -> None:
    observed_names: list[str] = []

    def failing_observer(name: str, digest: str) -> None:
        observed_names.append(name)
        assert digest.startswith("sha256:")
        raise failure_type("diagnostic observer failure")

    package, payload, status = _build_stage_fixture(
        tmp_path,
        monkeypatch,
        stage_observer=failing_observer,
    )
    tree = _semantic_tree(package)

    assert status == 0
    assert payload["status"] == "passed"
    assert observed_names == [
        "verified_deck",
        "normalized_source",
        "claim_surfaces",
        "lowered_runtime",
        "validated_authority",
        "artifact_writing",
    ]
    assert len(tree) == PRE_REFACTOR_PACKAGE_FILE_COUNT
    assert _semantic_tree_digest(tree) == PRE_REFACTOR_PACKAGE_TREE_DIGEST


def test_lowered_runtime_warnings_feed_public_outputs_and_break_parity_oracle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sentinel_warning = {
        "reason": "lowered_runtime_warning_sentinel",
        "card_id": "SENTINEL",
    }
    original_builder = package_builder.build_lowered_runtime_stage

    def build_perturbed_stage(**kwargs):
        return original_builder(
            **{
                **kwargs,
                "warnings": [*kwargs["warnings"], sentinel_warning],
            }
        )

    monkeypatch.setattr(
        package_builder,
        "build_lowered_runtime_stage",
        build_perturbed_stage,
    )
    package, payload, status = _build_stage_fixture(tmp_path, monkeypatch)
    tree = _semantic_tree(package)

    assert status == 0
    assert sentinel_warning in tree["reports/mulligan_plan_report.json"][
        "suppressed_rules"
    ]
    assert sentinel_warning in tree["reports/operator_summary.json"]["warnings"]
    assert sentinel_warning in payload["operator_summary"]["warnings"]
    assert any(
        blocker.get("reason") == "unsupported_conditions_present"
        for blocker in tree["reports/operator_summary.json"]["semantic_blockers"]
    )
    assert len(tree) == PRE_REFACTOR_PACKAGE_FILE_COUNT
    assert _semantic_tree_digest(tree) != PRE_REFACTOR_PACKAGE_TREE_DIGEST


def _build_stage_fixture(
    tmp_path: Path,
    monkeypatch,
    *,
    stage_observer=None,
) -> tuple[Path, dict[str, object], int]:
    roster = [
        {
            "card_id": "SW_448",
            "dbf_id": 64443,
            "count": 1,
            "name": "Darkbishop Benedictus",
            "text": (
                "Start of Game: If the spells in your deck are all Shadow, "
                "enter Shadowform."
            ),
        }
    ]
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps({"cards": roster}),
        encoding="utf-8",
    )
    package = tmp_path / "package"
    args = build_parser().parse_args(
        [
            "build",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            deck_code_for_cards(roster),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--json",
        ]
    )
    monkeypatch.setattr(
        package_builder,
        "fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    payload, status = build_package_payload(
        args,
        current_date=date(2026, 7, 28),
        stage_observer=stage_observer,
    )
    return package, payload, status


def _semantic_tree(root: Path) -> dict[str, object]:
    tree: dict[str, object] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if path.suffix == ".json":
            tree[relative] = json.loads(path.read_text(encoding="utf-8"))
        else:
            tree[relative] = path.read_text(encoding="utf-8")
    return tree


def _semantic_tree_digest(tree: dict[str, object]) -> str:
    normalized = deepcopy(tree)
    input_manifest = normalized["reports/input_manifest.json"]
    assert isinstance(input_manifest, dict)
    input_manifest["cards_json"] = "<CARDS_JSON>"
    input_manifest["runtime_root"] = "<RUNTIME_ROOT>"
    canonical = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
