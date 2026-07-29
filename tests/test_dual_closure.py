import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

import hsconfig.package_builder as package_builder
from hsconfig.cli_parser import build_parser
from hsconfig.disposition_ledger import (
    build_disposition_ledger,
    build_dual_closure,
)
from hsconfig.config_readiness import (
    project_config_readiness_from_dispositions,
)
from hsconfig.globalvalues_baseline import FALLBACK_GLOBALVALUES_BASELINE
from hsconfig.package_domain import (
    CardDisposition,
    ClaimDisposition,
    GlobalValueDecision,
    GlobalValueDecisionKind,
    GlobalValuesDecisionLedger,
    globalvalues_baseline_sha256,
    globalvalues_decision_ledger_content_sha256,
)
from hsconfig.package_builder import build_package_payload
from hsconfig.source_contract_audit import (
    project_source_contract_audit_from_dispositions,
)
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)
from tests.helpers.verified_deck_input import deck_code_for_cards


def _canonical_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _globalvalues_ledger(
    decisions,
    *,
    deck_fingerprint="deck-fingerprint",
):
    frozen = tuple(decisions)
    return GlobalValuesDecisionLedger(
        deck_fingerprint=deck_fingerprint,
        baseline_sha256=globalvalues_baseline_sha256(frozen),
        decisions=frozen,
        content_sha256=globalvalues_decision_ledger_content_sha256(
            frozen
        ),
    )


def _complete_globalvalues():
    decisions = tuple(
        GlobalValueDecision(
            deck_fingerprint="deck-fingerprint",
            key=key,
            kind=GlobalValueDecisionKind.COPY_BASELINE,
            baseline_canonical_json=_canonical_bytes(value),
            emitted_canonical_json=_canonical_bytes(value),
            authority_id="globalvalues:baseline",
            claim_ids=(),
            reason="copied canonical baseline",
        )
        for key, value in FALLBACK_GLOBALVALUES_BASELINE.items()
    )
    return _globalvalues_ledger(decisions)


def _explicit_ledger(
    *,
    reason_code="suppressed_unsupported_surface",
    authority_lane="A",
):
    return build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [
                {
                    "composite_card_key": "main_deck:CARD_001",
                    "zone": "main_deck",
                    "official_semantics_canonical_json": (
                        '{"GameCardId":"CARD_001"}'
                    ),
                    "authority_lane": authority_lane,
                    "evidence_ids": ["evidence-1"],
                    "claim_ids": ["claim-1"],
                    "physical_owner": "CARD_001",
                }
            ],
        },
        claim_lifecycle_rows=[
            {
                "deck_fingerprint": "deck-fingerprint",
                "claim_id": "claim-1",
                "claim_kind": "card_play",
                "evidence_id": "evidence-1",
                "composite_card_key": "main_deck:CARD_001",
                "builder_state": reason_code,
            }
        ],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )


def test_unknown_builder_state_blocks_complete_closure():
    ledger = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [
                {
                    "composite_card_key": "main_deck:CARD_001",
                    "zone": "main_deck",
                    "official_semantics_canonical_json": (
                        '{"GameCardId":"CARD_001"}'
                    ),
                    "authority_lane": "A",
                    "evidence_ids": ["evidence-1"],
                    "claim_ids": ["claim-1"],
                    "physical_owner": "CARD_001",
                }
            ],
        },
        claim_lifecycle_rows=[
            {
                "deck_fingerprint": "deck-fingerprint",
                "claim_id": "claim-1",
                "claim_kind": "card_play",
                "evidence_id": "evidence-1",
                "composite_card_key": "main_deck:CARD_001",
                "builder_state": "future_builder_state",
            }
        ],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )

    status = build_dual_closure(
        dispositions=ledger,
        globalvalues_ledger=_complete_globalvalues(),
        strategy_source_status="partial",
    )

    assert ledger.cards[0].disposition is not ClaimDisposition.BOT_DELEGATED
    assert status.pre_run_contract_status == "incomplete"
    assert status.strategy_authority_status == "partial"
    assert "unclassified_card_disposition" in status.unresolved_reasons


def test_complete_pre_run_contract_is_independent_of_partial_source_strength():
    status = build_dual_closure(
        dispositions=_explicit_ledger(),
        globalvalues_ledger=_complete_globalvalues(),
        strategy_source_status="partial",
    )

    assert status.pre_run_contract_status == "complete"
    assert status.strategy_authority_status == "partial"
    assert status.exact_guide_authority is False
    assert status.unresolved_reasons == ()


def test_strong_source_does_not_rescue_missing_globalvalues_decision():
    complete = _complete_globalvalues()
    incomplete = _globalvalues_ledger(complete.decisions[:-1])
    status = build_dual_closure(
        dispositions=_explicit_ledger(),
        globalvalues_ledger=incomplete,
        strategy_source_status="strong",
    )

    assert status.pre_run_contract_status == "incomplete"
    assert status.strategy_authority_status == "strong"
    assert status.exact_guide_authority is False
    assert "incomplete_globalvalues_decision" in status.unresolved_reasons


def test_duplicate_globalvalues_decision_blocks_exact_completeness():
    complete = _complete_globalvalues()

    with pytest.raises(
        ValueError,
        match="globalvalues_decision_key_duplicate",
    ):
        _globalvalues_ledger(
            (*complete.decisions, complete.decisions[0])
        )


def test_extra_globalvalues_decision_blocks_exact_completeness():
    complete = _complete_globalvalues()
    decisions = (
        *complete.decisions,
        replace(
            complete.decisions[0],
            key="UnexpectedGlobalValue",
        ),
    )
    status = build_dual_closure(
        dispositions=_explicit_ledger(),
        globalvalues_ledger=_globalvalues_ledger(decisions),
        strategy_source_status="partial",
    )

    assert status.pre_run_contract_status == "incomplete"
    assert "incomplete_globalvalues_decision" in status.unresolved_reasons


def test_matching_globalvalues_keys_with_invalid_emitted_value_block_closure():
    decision = _complete_globalvalues().decisions[0]

    with pytest.raises(
        ValueError,
        match="globalvalue_copy_baseline_mismatch",
    ):
        replace(
            decision,
            emitted_canonical_json=b'"tampered-value"',
        )


@pytest.mark.parametrize(
    ("field", "invalid_value", "error"),
    [
        ("kind", "unknown", "globalvalue_kind_invalid"),
        ("authority_id", "", "globalvalue_authority_id_invalid"),
        ("reason", "", "globalvalue_reason_invalid"),
        ("claim_ids", "not-a-list", "globalvalue_claim_ids"),
    ],
)
def test_matching_globalvalues_keys_with_invalid_metadata_block_closure(
    field,
    invalid_value,
    error,
):
    decision = _complete_globalvalues().decisions[0]

    with pytest.raises(ValueError, match=error):
        replace(decision, **{field: invalid_value})


def test_strong_source_without_lane_b_is_not_exact_guide_authority():
    status = build_dual_closure(
        dispositions=_explicit_ledger(authority_lane="A"),
        globalvalues_ledger=_complete_globalvalues(),
        strategy_source_status="strong",
    )

    assert status.strategy_authority_status == "strong"
    assert status.exact_guide_authority is False


def test_strong_source_with_lane_b_is_exact_guide_authority():
    status = build_dual_closure(
        dispositions=_explicit_ledger(authority_lane="B"),
        globalvalues_ledger=_complete_globalvalues(),
        strategy_source_status="strong",
    )

    assert status.strategy_authority_status == "strong"
    assert status.exact_guide_authority is True


def test_conflicting_builder_states_block_closure_without_bot_fallback():
    ledger = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": "deck-fingerprint",
            "cards": [
                {
                    "composite_card_key": "main_deck:CARD_001",
                    "zone": "main_deck",
                    "official_semantics_canonical_json": (
                        '{"GameCardId":"CARD_001"}'
                    ),
                    "authority_lane": "A",
                    "evidence_ids": ["evidence-1"],
                    "claim_ids": ["claim-1", "claim-2"],
                    "physical_owner": "CARD_001",
                }
            ],
        },
        claim_lifecycle_rows=[
            {
                "deck_fingerprint": "deck-fingerprint",
                "claim_id": "claim-1",
                "claim_kind": "card_play",
                "evidence_id": "evidence-1",
                "composite_card_key": "main_deck:CARD_001",
                "builder_state": "suppressed_unsupported_surface",
            },
            {
                "deck_fingerprint": "deck-fingerprint",
                "claim_id": "claim-2",
                "claim_kind": "card_play",
                "evidence_id": "evidence-1",
                "composite_card_key": "main_deck:CARD_001",
                "builder_state": "suppressed_insufficient_authority",
            },
        ],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )
    status = build_dual_closure(
        dispositions=ledger,
        globalvalues_ledger=_complete_globalvalues(),
        strategy_source_status="partial",
    )

    assert all(
        row.disposition is not ClaimDisposition.BOT_DELEGATED
        for row in ledger.claims
    )
    assert status.pre_run_contract_status == "incomplete"
    assert "conflicting_card_disposition" in status.unresolved_reasons


def test_existing_reports_project_one_diagnostic_ledger_without_new_apply_gate():
    ledger = _explicit_ledger()
    status = build_dual_closure(
        dispositions=ledger,
        globalvalues_ledger=_complete_globalvalues(),
        strategy_source_status="partial",
    )
    audit = project_source_contract_audit_from_dispositions(
        {
            "schema_version": 1,
            "authority": "diagnostic_only",
            "operator_gate_impact": "diagnostic_only",
            "apply_blocking": False,
            "normal_apply_authority": "reports/operator_summary.json",
            "summary": {},
            "claim_rows": {
                "claim-1": {
                    "claim_id": "claim-1",
                    "claim_kind": "card_play",
                    "cards": ["CARD_001"],
                    "lane": "report_only",
                    "policy_lane": "unsupported_or_unmapped",
                    "first_reason": "unsupported_or_unmapped",
                    "lowered_surfaces": [],
                    "surfaces": {},
                }
            },
            "claim_lifecycle_rows": [
                {
                    "claim_id": "claim-1",
                    "claim_kind": "card_play",
                    "builder_or_router_decision": "suppressed",
                }
            ],
            "card_rows": {
                "CARD_001": {
                    "card_id": "CARD_001",
                    "runtime_surfaces": [],
                    "claim_lanes": {},
                }
            },
        },
        dispositions=ledger,
        dual_closure=status,
    )
    readiness = project_config_readiness_from_dispositions(
        {
            "summary": {},
            "cards": {"CARD_001": {"card_id": "CARD_001"}},
        },
        dispositions=ledger,
        dual_closure=status,
    )
    explainability = build_source_to_runtime_explainability_report(
        audit,
        disposition_ledger=ledger,
        dual_closure_status=status,
    )

    for report in (audit, readiness, explainability):
        projection = report["disposition_projection"]
        assert projection["content_sha256"] == ledger.content_sha256
        assert projection["operator_gate_impact"] == "diagnostic_only"
        assert projection["apply_blocking"] is False
        assert projection["pre_run_contract_status"] == "complete"
    assert audit["claim_lifecycle_rows"][0]["final_disposition"] == (
        "suppressed_unsupported_surface"
    )
    assert readiness["cards"]["CARD_001"]["final_disposition"] == (
        "suppressed_unsupported_surface"
    )
    assert explainability["operator_gate_impact"] == "diagnostic_only"
    assert explainability["apply_blocking"] is False


def test_public_package_builder_opt_in_exposes_and_projects_one_disposition_truth(
    tmp_path: Path,
    monkeypatch,
):
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
    monkeypatch.setattr(
        package_builder,
        "fetch_latest_cards",
        lambda timeout=10.0: [],
    )

    def build_args(output: Path):
        return build_parser().parse_args(
            [
                "build",
                "--deck-name",
                "ShadowPriest",
                "--deck-code",
                deck_code_for_cards(roster),
                "--runtime-root",
                str(tmp_path / "runtime"),
                "--out",
                str(output),
                "--cards-json",
                str(cards_json),
                "--json",
            ]
        )

    default_package = tmp_path / "default-package"
    default_payload, default_status = build_package_payload(
        build_args(default_package),
        current_date=date(2026, 7, 29),
    )
    default_reports = [
        json.loads(
            (default_package / "reports" / filename).read_text(
                encoding="utf-8"
            )
        )
        for filename in (
            "source_contract_audit.json",
            "per_card_config_readiness_report.json",
            "source_to_runtime_explainability.json",
        )
    ]

    assert default_status == 0
    assert default_payload["status"] == "passed"
    assert "disposition_diagnostics" not in default_payload
    assert all(
        "disposition_projection" not in report
        for report in default_reports
    )
    production_ledger = json.loads(
        (
            default_package / "reports" / "disposition_ledger.json"
        ).read_text(encoding="utf-8")
    )
    assert production_ledger["content_sha256"].startswith("sha256:")
    assert production_ledger["deck_fingerprint"]
    assert not (
        default_package / "reports" / "dual_closure_status.json"
    ).exists()

    diagnostic_package = tmp_path / "diagnostic-package"
    diagnostic_payload, diagnostic_status = build_package_payload(
        build_args(diagnostic_package),
        current_date=date(2026, 7, 29),
        include_disposition_diagnostics=True,
    )
    diagnostics = diagnostic_payload["disposition_diagnostics"]
    ledger = diagnostics["ledger"]
    dual_closure = diagnostics["dual_closure"]
    projected_reports = [
        json.loads(
            (diagnostic_package / "reports" / filename).read_text(
                encoding="utf-8"
            )
        )
        for filename in (
            "source_contract_audit.json",
            "per_card_config_readiness_report.json",
            "source_to_runtime_explainability.json",
        )
    ]

    assert diagnostic_status == 0
    assert diagnostic_payload["status"] == "passed"
    assert ledger["content_sha256"].startswith("sha256:")
    assert ledger["deck_fingerprint"]
    for report in projected_reports:
        projection = report["disposition_projection"]
        assert projection["content_sha256"] == ledger["content_sha256"]
        assert (
            projection["pre_run_contract_status"]
            == dual_closure["pre_run_contract_status"]
        )
        assert (
            projection["strategy_authority_status"]
            == dual_closure["strategy_authority_status"]
        )
        assert (
            projection["exact_guide_authority"]
            is dual_closure["exact_guide_authority"]
        )


def test_package_ledger_derives_lane_b_from_typed_evidence_authority():
    dispositions, dual_closure, verified_emissions = (
        package_builder._build_package_disposition_ledger(
            deck_identity={
                "deck_fingerprint": "deck-fingerprint",
                "cards": [{"card_id": "CARD_001", "count": 1}],
            },
            source_contract_audit_report={
                "claim_rows": {
                    "claim-1": {
                        "claim_id": "claim-1",
                        "claim_kind": "card_play",
                        "cards": ["CARD_001"],
                        "evidence_authority": {
                            "lane": "B",
                            "authority_id": "B:claim-1",
                        },
                    }
                },
                "claim_lifecycle_rows": [
                    {
                        "claim_id": "claim-1",
                        "builder_or_router_decision": "suppressed",
                        "suppressed_reason": "claim_kind_policy",
                        "emitted_files": [],
                    }
                ],
            },
            runtime_surface_ledger={
                "cards": {},
                "linked_runtime_entities": {},
            },
            globalvalues_ledger=_complete_globalvalues(),
            strategy_source_status="strong",
        )
    )

    assert dispositions.cards[0].authority_lane.value == "B"
    assert dispositions.cards[0].evidence_ids == ("B:claim-1",)
    assert dual_closure.exact_guide_authority is True
    assert dual_closure.pre_run_contract_status == "complete"
    assert verified_emissions.deck_fingerprint == "deck-fingerprint"


@pytest.mark.parametrize(
    ("policy_id", "expected_lane", "expected_disposition"),
    [
        (
            "BOT_NATIVE_PRE_RUN",
            "E",
            CardDisposition.BOT_DELEGATED,
        ),
        (
            "OTHER_POLICY",
            "A",
            CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY,
        ),
    ],
)
def test_package_ledger_requires_exact_policy_for_lane_e_bot_delegation(
    policy_id,
    expected_lane,
    expected_disposition,
):
    dispositions, dual_closure, verified_emissions = (
        package_builder._build_package_disposition_ledger(
            deck_identity={
                "deck_fingerprint": "deck-fingerprint",
                "cards": [{"card_id": "CARD_001", "count": 1}],
            },
            source_contract_audit_report={
                "claim_rows": {
                    "claim-1": {
                        "claim_id": "claim-1",
                        "claim_kind": "card_play",
                        "cards": ["CARD_001"],
                    }
                },
                "claim_lifecycle_rows": [
                    {
                        "claim_id": "claim-1",
                        "builder_or_router_decision": "bot_delegated",
                        "policy_id": policy_id,
                        "emitted_files": [],
                    }
                ],
            },
            runtime_surface_ledger={
                "cards": {},
                "linked_runtime_entities": {},
            },
            globalvalues_ledger=_complete_globalvalues(),
            strategy_source_status="strong",
        )
    )

    assert dispositions.cards[0].authority_lane.value == expected_lane
    assert dispositions.cards[0].disposition is expected_disposition
    assert dual_closure.exact_guide_authority is False
    assert verified_emissions.deck_fingerprint == "deck-fingerprint"
