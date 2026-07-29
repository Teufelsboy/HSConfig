from hsconfig.disposition_ledger import (
    build_disposition_ledger,
    build_dual_closure,
)
from hsconfig.config_readiness import (
    project_config_readiness_from_dispositions,
)
from hsconfig.globalvalues_baseline import FALLBACK_GLOBALVALUES_BASELINE
from hsconfig.package_domain import ClaimDisposition
from hsconfig.source_contract_audit import (
    project_source_contract_audit_from_dispositions,
)
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)


def _complete_globalvalues():
    return [
        {"key": key, "status": "complete"}
        for key in sorted(FALLBACK_GLOBALVALUES_BASELINE)
    ]


def _explicit_ledger(*, reason_code="suppressed_unsupported_surface"):
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
        globalvalues_decisions=[
            {"key": "DiscoverSimulationValue", "status": "complete"},
        ],
        strategy_source_status="partial",
    )

    assert ledger.cards[0].disposition is not ClaimDisposition.BOT_DELEGATED
    assert status.pre_run_contract_status == "incomplete"
    assert status.strategy_authority_status == "partial"
    assert "unclassified_card_disposition" in status.unresolved_reasons


def test_complete_pre_run_contract_is_independent_of_partial_source_strength():
    status = build_dual_closure(
        dispositions=_explicit_ledger(),
        globalvalues_decisions=_complete_globalvalues(),
        strategy_source_status="partial",
    )

    assert status.pre_run_contract_status == "complete"
    assert status.strategy_authority_status == "partial"
    assert status.exact_guide_authority is False
    assert status.unresolved_reasons == ()


def test_strong_source_does_not_rescue_missing_globalvalues_decision():
    incomplete = _complete_globalvalues()[:-1]
    status = build_dual_closure(
        dispositions=_explicit_ledger(),
        globalvalues_decisions=incomplete,
        strategy_source_status="strong",
    )

    assert status.pre_run_contract_status == "incomplete"
    assert status.strategy_authority_status == "strong"
    assert status.exact_guide_authority is True
    assert "incomplete_globalvalues_decision" in status.unresolved_reasons


def test_duplicate_globalvalues_decision_blocks_exact_completeness():
    duplicated = [*_complete_globalvalues(), _complete_globalvalues()[0]]
    status = build_dual_closure(
        dispositions=_explicit_ledger(),
        globalvalues_decisions=duplicated,
        strategy_source_status="partial",
    )

    assert status.pre_run_contract_status == "incomplete"
    assert "incomplete_globalvalues_decision" in status.unresolved_reasons


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
        globalvalues_decisions=_complete_globalvalues(),
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
        globalvalues_decisions=_complete_globalvalues(),
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
