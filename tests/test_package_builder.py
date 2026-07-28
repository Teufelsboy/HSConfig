import json
from datetime import date
from pathlib import Path

from hsconfig.cli import main
from hsconfig.cli_parser import build_parser
from hsconfig.package_builder import build_package_payload
from tests.helpers.verified_deck_input import deck_code_for_cards


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
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )

    baseline_payload, baseline_status = build_package_payload(
        args,
        current_date=date(2026, 7, 28),
    )
    baseline_tree = _semantic_tree(package)
    observed_stages: list[tuple[str, str]] = []
    observed_payload, observed_status = build_package_payload(
        args,
        current_date=date(2026, 7, 28),
        stage_observer=lambda name, digest: observed_stages.append((name, digest)),
    )

    assert baseline_status == observed_status == 0
    assert observed_payload == baseline_payload
    assert _semantic_tree(package) == baseline_tree
    assert observed_stages == [
        (
            "verified_deck",
            "sha256:db4d8624abb96a9539e322cf70f2eb62694aa06cebc8f0a57266e4a959b6a651",
        ),
        (
            "normalized_source",
            "sha256:830fc856a4057967bf598bb0ba0c09c70dbf0148af1e1795c1ef0f738bfde933",
        ),
        (
            "claim_surfaces",
            "sha256:08fdd14c9e752f5ed6569cc5eaf2824e9750256a62c9c463770e6e87891aad59",
        ),
        (
            "lowered_runtime",
            "sha256:01ca388e8ea1c766bcfd64e20a713449ad4358bf090cc1550c6111d6f54844f7",
        ),
        (
            "validated_authority",
            "sha256:8d7ea863dc8a9d6bd7ed4a9b4eb54e0147fab9e96f58e6b7f5d8a6984e6cd797",
        ),
        (
            "artifact_writing",
            "sha256:4a2d7cdb8bc5db26bda3b81a4637a2ed4f3a3f9bc4f37ef94724c2286e39eddd",
        ),
    ]


def _semantic_tree(root: Path) -> dict[str, object]:
    tree: dict[str, object] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if path.suffix == ".json":
            tree[relative] = json.loads(path.read_text(encoding="utf-8"))
        else:
            tree[relative] = path.read_text(encoding="utf-8")
    return tree
