import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from tests.helpers.fixture_prepare import load_archetype_matrix


DECKS = [
    ("ShadowPriest", "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="),
    ("CtAPaladin", "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA="),
    ("PirateRogue", "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA=="),
    ("BigShaman", "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA=="),
    ("Discolock", "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA"),
    ("TreantDruid", "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA=="),
    ("ImbueMage", "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA="),
    ("MechPala", "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="),
    ("Kingslayer", "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA="),
    ("Boarlock", "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA"),
    ("PirateDH", "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA=="),
    ("CuteWarrior", "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA="),
]


def test_every_matrix_deck_declares_closure_profile():
    for deck in load_archetype_matrix():
        assert deck["closure_profile"]
        assert "closure_profile_first_missing_link" in deck
        assert deck["runtime_apply_allowed"] is True


def _stub_empty_card_fetches(monkeypatch) -> None:
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )


def prepare_fixture_deck_with_source_claim(tmp_path: Path, *, deck_name: str, claim: dict):
    cards = tmp_path / "cards.json"
    cards.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "CARD_001",
                        "dbf_id": 1,
                        "count": 30,
                        "name": "Fixture Card",
                        "text": "Future mechanic: fixture card text.",
                        "mechanics": ["FUTURE_MECHANIC"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    sources = tmp_path / "sources.json"
    sources.write_text(
        json.dumps(
            [
                {
                    "source_url": "https://example.invalid/qualifier",
                    "source_title": "Qualifier Fixture",
                    "source_family": "guide_fixture",
                    "retrieved_at": "2026-07-13T00:00:00Z",
                    "claims": [claim],
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards),
            "--guide-sources-json",
            str(sources),
        ]
    )
    reports = out / "reports"
    return {
        "exit_code": exit_code,
        "package": out,
        "operator_summary": json.loads(
            (reports / "operator_summary.json").read_text(encoding="utf-8")
        ),
        "guide_claim_bundle": json.loads(
            (reports / "guide_claim_bundle.json").read_text(encoding="utf-8")
        ),
    }


def prepare_fixture_deck_with_source_claims(
    tmp_path: Path, *, deck_name: str, claims: list[dict]
):
    cards = tmp_path / f"{deck_name}_cards.json"
    cards.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "CARD_001",
                        "dbf_id": 1,
                        "count": 1,
                        "name": "Fixture Card",
                        "text": "Fixture card text.",
                    },
                    {
                        "card_id": "CARD_777",
                        "dbf_id": 777,
                        "count": 1,
                        "name": "Future Fixture Card",
                        "text": "Future mechanic fixture card text.",
                        "mechanics": ["FUTURE_KEYWORD"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    sources = tmp_path / f"{deck_name}_sources.json"
    sources.write_text(
        json.dumps(
            [
                {
                    "source_url": f"https://example.invalid/{deck_name}",
                    "source_title": f"{deck_name} Fixture",
                    "source_family": "guide_fixture",
                    "retrieved_at": "2026-07-13T00:00:00Z",
                    "claims": claims,
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / f"{deck_name}_package"
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / f"{deck_name}_runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards),
            "--guide-sources-json",
            str(sources),
        ]
    )
    reports = out / "reports"
    deck_dir = next((out / "CustomConfig").iterdir())
    return {
        "exit_code": exit_code,
        "package": out,
        "deck_dir": deck_dir,
        "operator_summary": json.loads(
            (reports / "operator_summary.json").read_text(encoding="utf-8")
        ),
        "source_contract_audit": json.loads(
            (reports / "source_contract_audit.json").read_text(encoding="utf-8")
        ),
        "guide_claim_bundle": json.loads(
            (reports / "guide_claim_bundle.json").read_text(encoding="utf-8")
        ),
        "global_values_authority_matrix": json.loads(
            (reports / "global_values_authority_matrix.json").read_text(
                encoding="utf-8"
            )
        ),
        "unsupported_claims_report": json.loads(
            (reports / "unsupported_claims_report.json").read_text(encoding="utf-8")
        ),
        "mulligan": json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8")),
    }


def assert_load_safe_no_block_package(operator_summary: dict):
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_allowed"] is True
    assert operator_summary["runtime_apply_mode"] == "load_safe_apply"
    assert operator_summary["source_contract_audit_summary"]["non_blocking"] is True
    assert operator_summary["no_block_failure_mode_summary"]["hard_block"] is False
    assert operator_summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert operator_summary["source_backed_strong_closure"]["diagnostic_only"] is True
    assert operator_summary["source_backed_strong_closure"]["status"] in {
        "not_reported",
        "ready",
        "needs_source_closure",
    }
    assert isinstance(operator_summary["first_missing_source_action"], str)


def assert_no_default_only_runtime_surfaces(operator: dict) -> None:
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["no_default_only_runtime_status"] == "clean"
    mulligan_policy = operator["mulligan_policy_status"]
    assert mulligan_policy["default_only"] is False
    assert mulligan_policy["status"] in {
        "policy_backed",
        "source_backed",
        "source_and_policy_backed",
    }
    assert isinstance(mulligan_policy.get("policy_lanes", []), list)
    assert isinstance(mulligan_policy.get("policy_reasons", []), list)


def assert_runtime_surface_shape(deck_dir: Path, deck_card_ids: set[str]) -> None:
    special_files = {"Combo.json", "GlobalValues.json", "Mulligan.json"}
    card_files = {
        path.stem
        for path in deck_dir.glob("*.json")
        if path.name not in special_files
    }
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert card_files == deck_card_ids
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()


@pytest.mark.parametrize(("deck_name", "deck_code"), DECKS)
def test_valid_wild_deck_produces_load_safe_warning_apply_package(
    tmp_path: Path,
    capsys,
    monkeypatch,
    deck_name: str,
    deck_code: str,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    out = tmp_path / deck_name
    runtime_root = tmp_path / "runtime"

    code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    source_contract_audit = json.loads(
        (out / "reports" / "source_contract_audit.json").read_text(encoding="utf-8")
    )
    source_to_runtime = json.loads(
        (
            out / "reports" / "source_to_runtime_explainability.json"
        ).read_text(encoding="utf-8")
    )
    semantic_report = json.loads(
        (out / "reports" / "semantic_enrichment_report.json").read_text(encoding="utf-8")
    )
    deck_identity = json.loads((out / "reports" / "deck_identity.json").read_text(encoding="utf-8"))

    deck_dirs = [path for path in (out / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    deck_dir = deck_dirs[0]
    special_files = {"Combo.json", "GlobalValues.json", "Mulligan.json"}
    card_files = {
        path.stem
        for path in deck_dir.glob("*.json")
        if path.name not in special_files
    }
    deck_card_ids = {str(card["card_id"]) for card in deck_identity["cards"]}

    assert code == 0
    assert payload["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert_no_default_only_runtime_surfaces(operator)
    no_block = operator["no_block_failure_mode_summary"]
    assert no_block["hard_block"] is False
    assert no_block["runtime_apply_allowed"] is True
    assert no_block["runtime_apply_mode"] == "load_safe_apply"
    assert no_block["overall"] in {
        "load_safe_apply_allowed",
        "load_safe_apply_allowed_with_warnings",
    }
    assert no_block["categories"]["technical_hard_block"] == []
    assert no_block["operator_message"].startswith("Package is load-safe.")
    assert operator["source_contract_audit_summary"]["non_blocking"] is True
    assert source_contract_audit["schema_version"] == 1
    assert source_contract_audit["summary"]["cards_total"] == len(deck_card_ids)
    assert source_to_runtime["authority"] == "diagnostic_only"
    assert source_to_runtime["apply_blocking"] is False
    assert source_to_runtime["summary"]["cards_total"] == len(deck_card_ids)
    assert source_to_runtime["operator_attention"]
    assert all("closure" in row for row in source_to_runtime["card_rows"])
    assert all(
        row["closure"]["lane"]
        in {
            "runtime_backed",
            "source_action_needed",
            "diagnostic_only",
            "baseline_only_visible",
        }
        for row in source_to_runtime["card_rows"]
    )
    assert operator["mechanic_visibility_summary"]["non_blocking"] is True
    assert operator["semantic_enrichment_summary"]["non_blocking"] is True
    assert operator["next_action"] in {"READY_TO_APPLY_OR_HANDOFF", "READY_TO_APPLY_WITH_WARNINGS"}
    assert semantic_report["non_blocking"] is True
    assert "summary" in semantic_report
    assert "cards" in semantic_report
    assert_runtime_surface_shape(deck_dir, deck_card_ids)


def test_configure_path_preserves_no_block_contract_for_matrix(tmp_path, monkeypatch):
    _stub_empty_card_fetches(monkeypatch)

    for deck_name, deck_code in DECKS:
        out = tmp_path / deck_name
        assert main(
            [
                "configure",
                "--deck-name",
                deck_name,
                "--deck-code",
                deck_code,
                "--runtime-root",
                str(tmp_path / "runtime"),
                "--out",
                str(out),
                "--json",
            ]
        ) == 0

        operator = json.loads(
            (out / "04_package" / "reports" / "operator_summary.json").read_text(
                encoding="utf-8"
            )
        )
        source_contract_audit = json.loads(
            (out / "04_package" / "reports" / "source_contract_audit.json").read_text(
                encoding="utf-8"
            )
        )
        assert operator["technical_status"] == "VALID_PACKAGE"
        assert operator["runtime_load_safe"] is True
        assert operator["runtime_apply_mode"] == "load_safe_apply"
        assert operator["default_only_runtime_surfaces"] == []
        assert operator["mulligan_policy_status"]["default_only"] is False
        assert operator["source_contract_audit_summary"]["non_blocking"] is True
        source_quality = operator["source_claim_quality_summary"]
        assert source_quality["non_blocking"] is True
        assert isinstance(source_quality["source_quality_lane_counts"], dict)
        assert operator["next_action"] in {
            "READY_TO_APPLY_OR_HANDOFF",
            "READY_TO_APPLY_WITH_WARNINGS",
        }
        assert operator["runtime_apply_contract"]["apply_authority"] == "reports/operator_summary.json"
        assert source_contract_audit["schema_version"] == 1
        assert operator["mechanic_visibility_summary"]["non_blocking"] is True


def test_unknown_semantic_qualifier_stays_warning_not_apply_block(tmp_path):
    result = prepare_fixture_deck_with_source_claim(
        tmp_path,
        deck_name="QualifierUnknown",
        claim={
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_001"],
            "evidence_text_short": "Use the new future mechanic when possible.",
            "source_confidence": "high",
            "semantic_qualifiers": {"state_requirements": ["future_mechanic"]},
        },
    )

    assert result["exit_code"] == 0
    operator_summary = result["operator_summary"]
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["runtime_apply_allowed"] is True
    assert operator_summary["runtime_apply_mode"] == "load_safe_apply"
    assert operator_summary["no_block_failure_mode_summary"]["hard_block"] is False
    mechanic_visibility = operator_summary["mechanic_visibility_summary"]
    assert mechanic_visibility["non_blocking"] is True
    assert "future_mechanic" in mechanic_visibility["mechanics_by_bucket"]["warning_only"]
    assert any(
        boundary["mechanic"] == "future_mechanic"
        for boundary in mechanic_visibility["warning_boundaries"]
    )
    assert operator_summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    claim = result["guide_claim_bundle"]["claims"][0]
    assert claim["semantic_qualifiers"]["state_requirements"] == ["future_mechanic"]


def test_singleton_hero_power_state_requirement_preserves_effect_without_mulligan_keep(tmp_path):
    result = prepare_fixture_deck_with_source_claim(
        tmp_path,
        deck_name="SingletonHeroPower",
        claim={
            "claim_kind": "hero_power_transform",
            "cards": ["CARD_001"],
            "evidence_text_short": "Start of Game transforms the hero power when all spells are Shadow.",
            "source_confidence": "high",
            "semantic_qualifiers": {"state_requirements": "all_shadow_spells"},
        },
    )

    package = result["package"]
    deck_dir = next((package / "CustomConfig").iterdir())
    card_behavior = json.loads((deck_dir / "CARD_001.json").read_text(encoding="utf-8"))
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    claim = result["guide_claim_bundle"]["claims"][0]
    operator_summary = result["operator_summary"]

    assert result["exit_code"] == 0
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["runtime_apply_allowed"] is True
    assert claim["semantic_qualifiers"]["state_requirements"] == ["all_shadow_spells"]
    assert card_behavior["BeforeUseHeroPowerBonus"]["values"]
    assert not any(row.get("mulligan") == "CARD_001" for row in mulligan["Mulligan"]["values"])


def test_quarantined_claims_do_not_block_valid_load_safe_package(tmp_path):
    result = prepare_fixture_deck_with_source_claims(
        tmp_path,
        deck_name="NoBlockConflictDeck",
        claims=[
            {
                "claim_id": "keep_card",
                "claim_kind": "mulligan_keep",
                "card_id": "CARD_001",
                "evidence_text_short": "Keep the fixture card in the mulligan.",
                "source_confidence": "guide_backed",
            },
            {
                "claim_id": "discard_card",
                "claim_kind": "mulligan_discard",
                "card_id": "CARD_001",
                "evidence_text_short": "Discard the fixture card in the mulligan.",
                "source_confidence": "guide_backed",
            },
        ],
    )

    operator_summary = result["operator_summary"]
    source_contract_audit = result["source_contract_audit"]
    lifecycle_rows = source_contract_audit["claim_lifecycle_rows"]
    quarantined_rows = [
        row for row in lifecycle_rows if row.get("quarantine_status") == "quarantined"
    ]

    assert result["exit_code"] == 0
    assert_load_safe_no_block_package(operator_summary)
    assert result["guide_claim_bundle"]["claim_conflict_report"]["conflict_count"] == 1
    assert {row["claim_kind"] for row in quarantined_rows} == {
        "mulligan_keep",
        "mulligan_discard",
    }
    assert all(
        row["builder_or_router_decision"] == "suppressed"
        and row["final_runtime_effect"] == "suppressed_quarantined_claim"
        and row["first_missing_link"] == "source_claim_conflict"
        and row["operator_impact"] == "diagnostic_only"
        for row in quarantined_rows
    )
    assert source_contract_audit["summary"]["claim_lifecycle_decision_counts"][
        "suppressed"
    ] >= len(quarantined_rows)
    assert not any(
        row.get("mulligan") == "CARD_001"
        for row in result["mulligan"]["Mulligan"]["values"]
    )


def test_unsupported_future_report_only_and_runtime_evidence_claims_do_not_block(tmp_path):
    result = prepare_fixture_deck_with_source_claims(
        tmp_path,
        deck_name="NoBlockDiagnosticDeck",
        claims=[
            {
                "claim_id": "future_mechanic",
                "claim_kind": "mechanic_usage",
                "card_id": "CARD_777",
                "mechanic": "future_keyword",
                "evidence_text_short": "Future keyword support remains diagnostic.",
                "source_confidence": "unknown_future_mechanic",
            },
            {
                "claim_id": "report_only_role",
                "claim_kind": "card_role",
                "card_id": "CARD_001",
                "stance": "thin report-only role",
                "evidence_text_short": "Thin source role should not become runtime authority.",
                "source_confidence": "report_only",
            },
            {
                "claim_id": "numeric_runtime_evidence",
                "claim_kind": "globalvalue_numeric_tuning",
                "scope": "deck",
                "key": "LowHpBoardValuePenalty",
                "evidence_text_short": "Tune this numeric key only after runtime evidence.",
                "source_confidence": "guide_backed",
            },
            {
                "claim_id": "unsupported_future_claim",
                "claim_kind": "future_claim_kind",
                "card_id": "CARD_001",
                "evidence_text_short": "Unsupported future claim stays report-visible.",
                "source_confidence": "guide_backed",
            },
        ],
    )

    operator_summary = result["operator_summary"]
    source_contract_audit = result["source_contract_audit"]
    lifecycle_rows = source_contract_audit["claim_lifecycle_rows"]
    report_only_rows = [
        row for row in lifecycle_rows if row.get("runtime_eligibility") == "report_only"
    ]
    runtime_evidence_rows = [
        row
        for row in lifecycle_rows
        if row.get("policy_lane") == "runtime_evidence_required"
    ]
    unsupported_rows = [
        row
        for row in result["unsupported_claims_report"]
        if row.get("claim_kind") == "future_claim_kind"
    ]

    assert result["exit_code"] == 0
    assert_load_safe_no_block_package(operator_summary)
    assert source_contract_audit["summary"]["report_only_claims"] >= 1
    assert source_contract_audit["summary"]["runtime_evidence_required_claims"] >= 1
    assert report_only_rows
    assert all(row["builder_or_router_decision"] != "emitted" for row in report_only_rows)
    assert runtime_evidence_rows
    assert any(
        row["builder_or_router_decision"] == "suppressed"
        and row["first_missing_link"] == "runtime_evidence"
        and row["operator_impact"] == "diagnostic_only"
        for row in runtime_evidence_rows
    )
    assert unsupported_rows
    assert all(row["reason"] == "unsupported_claim_kind" for row in unsupported_rows)
    assert any(
        row.get("key") == "LowHpBoardValuePenalty"
        for row in result["global_values_authority_matrix"][
            "blocked_until_runtime_evidence"
        ]
    )
    assert "future_keyword" in operator_summary["mechanic_drift_summary"][
        "unknown_mechanics"
    ]
    assert "future_keyword" in operator_summary["mechanic_visibility_summary"][
        "mechanics_by_bucket"
    ]["warning_only"]


def test_warning_bearing_future_mechanic_package_still_load_safe(tmp_path):
    result = prepare_fixture_deck_with_source_claims(
        tmp_path,
        deck_name="FutureMechanicNoBlock",
        claims=[
            {
                "claim_id": "future_keyword_visible",
                "claim_kind": "future_claim_kind",
                "claim_readiness": "contract_gap",
                "cards": ["CARD_777"],
                "mechanic": "future_keyword",
                "evidence_text_short": "Future keyword should be visible but not blocking.",
            },
            {
                "claim_id": "runtime_only_globalvalue_visible",
                "claim_kind": "globalvalue_numeric_tuning",
                "claim_readiness": "guide_backed",
                "source_confidence": "guide_backed",
                "scope": "deck",
                "key": "FirstTurnValueWeight",
                "runtime_value": 1.3,
                "evidence_text_short": "Runtime value request requires post-game evidence.",
            },
        ],
    )
    assert result["exit_code"] == 0
    operator_summary = result["operator_summary"]

    assert_load_safe_no_block_package(operator_summary)
    assert operator_summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert operator_summary["no_block_failure_mode_summary"]["hard_block"] is False
    assert any(
        warning.get("key") == "FirstTurnValueWeight"
        and warning.get("reason") == "globalvalue_runtime_evidence_required"
        for warning in operator_summary["warnings"]
    )
    assert any(
        row["key"] == "FirstTurnValueWeight"
        and row["reason"] == "requires_runtime_evidence"
        for row in result["global_values_authority_matrix"][
            "blocked_until_runtime_evidence"
        ]
    )
    global_values = json.loads(
        (result["deck_dir"] / "GlobalValues.json").read_text(encoding="utf-8")
    )
    assert global_values["FirstTurnValueWeight"]["values"] == [
        {"condition": "*", "value": "0"}
    ]
