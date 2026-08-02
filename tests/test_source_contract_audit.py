from __future__ import annotations

from hsconfig import source_contract_audit
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_claim_lifecycle import build_initial_lifecycle_rows
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_contract_audit import (
    build_source_contract_audit,
    render_source_contract_audit_markdown,
)
from tests.helpers.live_acquisition import acquire_live_test_provenance
from tests.mulligan_authority_fixtures import build_canonical_mulligan_bundle


REQUIRED_LIFECYCLE_FIELDS = {
    "claim_id",
    "claim_kind",
    "policy_lane",
    "surface_gate_decision",
    "surface_gate_reason",
    "builder_or_router_decision",
    "runtime_surface",
    "emitted_files",
    "suppressed_reason",
    "first_missing_link",
    "operator_impact",
}


def test_claim_card_and_reference_helpers_normalize_legacy_shapes() -> None:
    assert source_contract_audit._claim_cards({"cards": "A"}) == ["A"]
    assert source_contract_audit._claim_cards({"cards": ["B", "", "A", "A"]}) == [
        "A",
        "B",
    ]
    assert source_contract_audit._claim_cards({"cards": {}, "card_id": "C"}) == [
        "C"
    ]
    assert source_contract_audit._claim_cards({"card": "D"}) == ["D"]
    assert source_contract_audit._claim_cards({}) == []

    assert source_contract_audit._claim_reference_keys(
        "fallback",
        {"claim_id": "explicit", "source_refs": "source:one"},
    ) == {"fallback", "explicit", "source:one"}
    assert source_contract_audit._claim_reference_keys(
        "fallback",
        {"source_refs": ["source:two", "", "source:three"]},
    ) == {"fallback", "source:two", "source:three"}


def test_claim_row_id_helpers_collect_all_supported_reference_families() -> None:
    row = {
        "claim_id": "one",
        "source_claim_id": "two",
        "claim_ids": "three",
        "source_claim_ids": ["four", ""],
        "merged_claim_ids": ["five", "six"],
        "claim_refs": "seven",
    }
    assert source_contract_audit._row_claim_ids(row) == {
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
    }
    assert source_contract_audit._ids_from_rows(["invalid", row]) == (
        source_contract_audit._row_claim_ids(row)
    )
    assert source_contract_audit._rows("invalid") == []
    assert source_contract_audit._rows(["invalid", row]) == [row]


def test_combo_card_parser_supports_structured_and_legacy_sequences() -> None:
    assert source_contract_audit._combo_cards({"cards": "A"}) == ["A"]
    assert source_contract_audit._combo_cards({"cards": ["A", "", "B"]}) == [
        "A",
        "B",
    ]
    assert source_contract_audit._combo_cards({"combo": " A >> B >> "}) == [
        "A",
        "B",
    ]
    assert source_contract_audit._combo_cards({}) == []


def test_suppression_reason_maps_to_the_first_actionable_missing_link() -> None:
    cases = {
        None: None,
        "missing_target_scope": "needs_target_scope",
        "no_target_scope": "needs_target_scope",
        "invalid_target_scope": "needs_invalid_target_scope",
        "target_scope_not_encoded": "needs_target_surface",
        "requires_runtime_evidence": "runtime_evidence",
        "source_evidence_required": "source_evidence",
        "surface_gate_rejected": "surface_gate",
        "builder_or_router_missing": "builder_or_router",
        "other": "runtime_surface",
    }
    assert {
        reason: source_contract_audit._first_missing_link_for_suppression(reason)
        for reason in cases
    } == cases


def test_legacy_lowering_fallback_respects_surface_and_authority_boundaries() -> None:
    emitted = {"mulligan": {"direct"}, "cardid": set(), "combo": set()}
    plans = {
        "mulligan_plan": {"rules": [{"card": "A"}]},
        "card_behavior_plan": {
            "rows": [
                {"card_id": "A", "meaningful_runtime_surface": False},
                {"card_id": "B", "meaningful_runtime_surface": True},
            ]
        },
        "combo_plan": {"combos": [{"combo": "A >> C"}]},
    }

    def lowered(
        surface: str,
        claim: dict[str, object],
        *,
        claim_id: str = "claim",
        allow_legacy: bool = True,
    ) -> bool:
        return source_contract_audit._claim_lowered_to_surface(
            claim_id=claim_id,
            claim=claim,
            surface=surface,
            emitted_claim_ids=emitted,
            allow_legacy_card_fallback=allow_legacy,
            **plans,
        )

    assert lowered("mulligan", {}, claim_id="direct")
    assert not lowered("globalvalues", {"cards": ["A"]})
    assert not lowered("mulligan", {"cards": ["A"]}, allow_legacy=False)
    assert not lowered("mulligan", {})
    assert lowered("mulligan", {"cards": ["A"]})
    assert not lowered("cardid", {"cards": ["A"]})
    assert lowered("cardid", {"cards": ["B"]})
    assert lowered("combo", {"cards": ["C"]})
    assert not lowered("unknown", {"cards": ["A"]})


def test_lifecycle_surface_prefers_emission_then_gate_specificity() -> None:
    def surface(
        emission: dict[str, object],
        emitted: list[str],
        surfaces: object,
    ) -> str:
        return source_contract_audit._lifecycle_surface(
            emission=emission,
            emitted_surfaces=emitted,
            claim_row={"surfaces": surfaces},
        )

    assert surface({"surface": "combo"}, ["cardid"], {}) == "combo"
    assert surface({}, ["cardid"], {}) == "cardid"
    assert surface(
        {},
        [],
        {"mulligan": {"reason": "requires_runtime_evidence"}},
    ) == "mulligan"
    assert surface({}, [], {"combo": {"allowed": True}}) == "combo"
    assert surface({}, [], {"cardid": {"allowed": False}}) == "cardid"
    assert surface({}, [], []) == ""


def test_emission_merge_prefers_emitted_rows_and_specific_suppression() -> None:
    index: dict[str, dict[str, object]] = {}
    source_contract_audit._merge_emission_rows(
        index,
        [
            {"claim_id": ""},
            {
                "claim_id": "claim",
                "decision": "suppressed",
                "surface": None,
                "emitted_files": ["A.json"],
                "suppressed_reason": "builder_or_router_missing",
            },
            {
                "claim_id": "claim",
                "decision": "suppressed",
                "surface": "combo",
                "emitted_files": ["B.json"],
                "suppressed_reason": "requires_runtime_evidence",
            },
        ],
    )
    assert index["claim"] == {
        "decision": "suppressed",
        "surface": "combo",
        "runtime_surface": None,
        "emitted_files": ["A.json", "B.json"],
        "suppressed_reason": "requires_runtime_evidence",
    }

    source_contract_audit._merge_emission_rows(
        index,
        [
            {
                "claim_id": "claim",
                "decision": "emitted",
                "surface": "cardid",
                "runtime_surface": "CARD.json",
                "emitted_files": ["CARD.json"],
            }
        ],
    )
    assert index["claim"]["decision"] == "emitted"
    assert index["claim"]["suppressed_reason"] is None
    assert index["claim"]["surface"] == "cardid"
    assert index["claim"]["runtime_surface"] == "CARD.json"


def test_deck_card_projection_ignores_invalid_and_unnamed_rows() -> None:
    assert source_contract_audit._deck_cards({"cards": "invalid"}) == {}
    valid = {"card_id": "A", "name": "Alpha"}
    assert source_contract_audit._deck_cards(
        {"cards": ["invalid", {"card_id": ""}, valid]}
    ) == {"A": valid}


def test_runtime_identity_preserves_only_meaningful_surface_selectors() -> None:
    assert source_contract_audit._claim_runtime_identity(
        {},
        claim_kind="mulligan_keep",
        cards=["A"],
    ) == {"selector": "A", "action": "hold", "condition": "*"}
    assert source_contract_audit._claim_runtime_identity(
        {"mulligan": "A or B", "intent": "discard", "condition": "versus aggro"},
        claim_kind="mulligan_discard",
        cards=["A", "B"],
    ) == {
        "selector": "A or B",
        "action": "discard",
        "condition": "versus aggro",
    }
    assert source_contract_audit._claim_runtime_identity(
        {"timing_kind": "before", "globalvalues_key": "Legacy"},
        claim_kind="combo_sequence",
        cards=["A", "B"],
        globalvalues_keys=["Canonical", ""],
    ) == {
        "timing_kind": "before",
        "operator": ">>",
        "globalvalues_key": "Legacy",
        "globalvalues_keys": ["Canonical"],
        "key": "Canonical",
    }


def test_audit_helpers_default_malformed_optional_containers_without_authority() -> None:
    assert source_contract_audit._guide_claims({"claims": "invalid"}) == []
    assert source_contract_audit._card_roles_from_readiness(
        {"cards": "invalid"}
    ) == {}
    assert source_contract_audit._card_roles_from_readiness(
        {"cards": {"A": {"roles": ["anchor"]}, "B": "invalid"}}
    ) == {"A": {"roles": ["anchor"]}}
    assert source_contract_audit._normalized_suppression_reason(
        {"reason": "requires_runtime_evidence"}
    ) == "runtime_evidence_required"
    assert source_contract_audit._normalized_suppression_reason({}) == "suppressed"
    assert source_contract_audit._int("7") == 7
    assert source_contract_audit._int("invalid") == 0


def test_audit_markdown_ignores_malformed_rows_and_escapes_table_values() -> None:
    markdown = render_source_contract_audit_markdown(
        {
            "deck_name": "Deck|Name",
            "summary": "invalid",
            "card_rows": {
                "invalid": "not-a-row",
                "CARD": {
                    "name": "Card|Name",
                    "readiness_lane": "ready",
                    "claim_lanes": {},
                    "first_missing_link": "none",
                },
            },
            "claim_lifecycle_rows": [
                "invalid",
                {
                    "claim_id": "claim|one",
                    "claim_kind": "card_role",
                    "policy_lane": "runtime_lowerable",
                    "surface_gate_decision": "allowed",
                    "builder_or_router_decision": "emitted",
                    "runtime_surface": "CARD.json",
                    "first_missing_link": "none",
                },
            ],
        }
    )

    assert "# Source Contract Audit - Deck|Name" in markdown
    assert "| CARD Card\\|Name | ready | none |  |  |" in markdown
    assert "| claim\\|one | card_role | runtime_lowerable |" in markdown


def _verified_posture_claim(claim_id: str = "posture_claim") -> dict:
    return _verified_posture_bundle(claim_id)["claims"][0]


def _verified_posture_bundle(claim_id: str = "posture_claim") -> dict:
    deck_identity = {
        "deck_name": "FixtureDeck",
        "deck_fingerprint": "fixture-deck-fingerprint",
        "cards": [{"card_id": "CARD_KEEP", "name": "Keep Card", "count": 2}],
    }
    return build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/fixture-guide",
                "source_title": "Fixture Guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "acquisition_provenance": acquire_live_test_provenance(),
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": "fixture-deck-fingerprint",
                        "candidate_deck_code_hashes": ["sha256:fixture-source"],
                    }
                },
                "claims": [
                    {
                        "claim_id": claim_id,
                        "claim_kind": "gameplan_posture",
                        "cards": ["CARD_KEEP"],
                        "scope": "deck",
                        "stance": "aggressive",
                        "evidence_text_short": "Use a more aggressive posture.",
                        "source_confidence": "high",
                        "promotion_eligible": True,
                    }
                ],
            }
        ],
        current_date="2026-07-26",
    )


def _verified_mulligan_bundle(*claims: dict) -> tuple[dict, dict]:
    return build_canonical_mulligan_bundle(
        [{"timing": "mulligan", **claim} for claim in claims],
        deck_fingerprint="fixture-deck-fingerprint",
    )


def test_source_contract_audit_explains_surface_gate_lanes():
    mulligan_bundle, mulligan_identity = _verified_mulligan_bundle(
        {
            "claim_id": "keep_claim",
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_KEEP"],
            "evidence_text_short": "Keep CARD_KEEP.",
        }
    )
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            **mulligan_identity,
            "cards": [
                {"card_id": "CARD_KEEP", "name": "Keep Card", "count": 2},
                {"card_id": "CARD_NUM", "name": "Numeric Card", "count": 1},
            ],
        },
        guide_claim_bundle={
            "claims": [
                mulligan_bundle["claims"][0],
                {
                    "claim_id": "numeric_claim",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_NUM"],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Tune LowHpBoardValuePenalty later.",
                },
            ],
            "canonical_source_receipts": mulligan_bundle[
                "canonical_source_receipts"
            ],
        },
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_KEEP",
                    "action": "hold",
                    "source_claim_ids": ["keep_claim"],
                }
            ],
            "suppressed_rules": [],
        },
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [
                {"key": "LowHpBoardValuePenalty", "claim_id": "numeric_claim"}
            ],
        },
        config_readiness_report={
            "cards": {
                "CARD_KEEP": {
                    "name": "Keep Card",
                    "roles": ["mulligan_anchor"],
                    "runtime_surfaces": ["Mulligan.json"],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "needs_runtime_surface",
                },
                "CARD_NUM": {
                    "name": "Numeric Card",
                    "roles": [],
                    "runtime_surfaces": [],
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "none",
                },
            }
        },
    )

    assert report["schema_version"] == 1
    assert report["authority"] == "diagnostic_only"
    assert report["operator_gate_impact"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert report["normal_apply_authority"] == "reports/operator_summary.json"
    assert report["summary"]["claims_total"] == 2
    assert report["summary"]["runtime_lowered_claims"] == 1
    assert report["summary"]["runtime_evidence_required_claims"] == 1
    assert report["claim_rows"]["keep_claim"]["lane"] == "runtime_lowered"
    assert report["claim_rows"]["keep_claim"]["surfaces"]["mulligan"]["allowed"] is True
    assert report["claim_rows"]["numeric_claim"]["lane"] == "runtime_evidence_required"
    assert report["claim_rows"]["numeric_claim"]["surfaces"]["globalvalues"]["reason"] == (
        "requires_runtime_evidence"
    )
    assert report["card_rows"]["CARD_KEEP"]["first_missing_link"] == "needs_runtime_surface"
    assert report["card_rows"]["CARD_KEEP"]["claim_lanes"]["runtime_lowered"] == 1


def test_claim_lifecycle_rows_explain_static_policy_and_runtime_outcome():
    mulligan_bundle, mulligan_identity = _verified_mulligan_bundle(
        {
            "claim_id": "keep_claim",
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_KEEP"],
            "evidence_text_short": "Keep CARD_KEEP.",
        }
    )
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            **mulligan_identity,
            "cards": [
                {"card_id": "CARD_KEEP", "name": "Keep Card", "count": 2},
                {"card_id": "CARD_NUM", "name": "Numeric Card", "count": 1},
            ],
        },
        guide_claim_bundle={
            "claims": [
                mulligan_bundle["claims"][0],
                {
                    "claim_id": "numeric_claim",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_NUM"],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Tune LowHpBoardValuePenalty after games.",
                },
            ],
            "canonical_source_receipts": mulligan_bundle[
                "canonical_source_receipts"
            ],
        },
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_KEEP",
                    "action": "hold",
                    "source_claim_ids": ["keep_claim"],
                }
            ],
            "suppressed_rules": [],
        },
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [
                {
                    "key": "LowHpBoardValuePenalty",
                    "claim_id": "numeric_claim",
                    "reason": "runtime_evidence_required",
                }
            ],
        },
        config_readiness_report={
            "cards": {
                "CARD_KEEP": {
                    "name": "Keep Card",
                    "roles": ["mulligan_anchor"],
                    "runtime_surfaces": ["Mulligan.json"],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "none",
                },
                "CARD_NUM": {
                    "name": "Numeric Card",
                    "roles": [],
                    "runtime_surfaces": [],
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "runtime_evidence",
                },
            }
        },
    )
    policy_by_claim_kind = source_contract_policy_by_claim_kind()

    lifecycle_rows = report["claim_lifecycle_rows"]
    assert lifecycle_rows
    assert all(REQUIRED_LIFECYCLE_FIELDS <= set(row) for row in lifecycle_rows)
    assert all(row["operator_impact"] == "diagnostic_only" for row in lifecycle_rows)

    rows_by_claim_id = {row["claim_id"]: row for row in lifecycle_rows}
    assert rows_by_claim_id["keep_claim"] == {
        "claim_id": "keep_claim",
        "claim_kind": "mulligan_keep",
        "policy_lane": policy_by_claim_kind["mulligan_keep"]["lane"],
        "surface_gate_decision": "allowed",
        "surface_gate_reason": "allowed",
        "builder_or_router_decision": "emitted",
        "runtime_surface": "Mulligan.json",
        "emitted_files": ["Mulligan.json"],
        "suppressed_reason": None,
        "first_missing_link": None,
        "operator_impact": "diagnostic_only",
    }
    assert rows_by_claim_id["numeric_claim"] == {
        "claim_id": "numeric_claim",
        "claim_kind": "globalvalue_numeric_tuning",
        "policy_lane": policy_by_claim_kind["globalvalue_numeric_tuning"]["lane"],
        "surface_gate_decision": "rejected",
        "surface_gate_reason": "requires_runtime_evidence",
        "builder_or_router_decision": "suppressed",
        "runtime_surface": None,
        "emitted_files": [],
        "suppressed_reason": "runtime_evidence_required",
        "first_missing_link": "runtime_evidence",
        "operator_impact": "diagnostic_only",
    }


def test_claim_lifecycle_uses_canonical_quarantine_rows():
    claims = [
        {
            "claim_id": "keep_card",
            "claim_kind": "mulligan_keep",
            "source_confidence": "guide_backed",
            "cards": ["CARD_001"],
            "source_title": "Fixture Guide",
            "evidence_text_short": "Keep CARD_001.",
        },
        {
            "claim_id": "discard_card",
            "claim_kind": "mulligan_discard",
            "source_confidence": "guide_backed",
            "cards": ["CARD_001"],
            "source_title": "Fixture Guide",
            "evidence_text_short": "Discard CARD_001.",
        },
    ]
    lifecycle_rows = build_initial_lifecycle_rows(
        claims,
        conflict_report={
            "conflicts": [
                {
                    "claim_ids": ["keep_card", "discard_card"],
                    "reason": "contradictory_mulligan_keep_discard",
                }
            ]
        },
    )

    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "cards": [{"card_id": "CARD_001", "name": "Conflict Card", "count": 1}],
        },
        guide_claim_bundle={"claims": claims},
        mulligan_plan={"rules": [], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={
            "cards": {
                "CARD_001": {
                    "name": "Conflict Card",
                    "roles": ["mulligan_anchor"],
                    "runtime_surfaces": [],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "source_claim_conflict",
                }
            }
        },
        initial_lifecycle_rows=lifecycle_rows,
    )

    rows_by_claim_id = {row["claim_id"]: row for row in report["claim_lifecycle_rows"]}
    row = rows_by_claim_id["discard_card"]

    assert REQUIRED_LIFECYCLE_FIELDS <= set(row)
    assert row["quarantine_status"] == "quarantined"
    assert row["quarantine_reason"] == "contradictory_mulligan_keep_discard"
    assert row["runtime_eligibility"] == "quarantined"
    assert row["builder_or_router_decision"] == "suppressed"
    assert row["suppressed_reason"] == "contradictory_mulligan_keep_discard"
    assert row["first_missing_link"] == "source_claim_conflict"
    assert row["final_runtime_effect"] == "suppressed_quarantined_claim"
    assert report["summary"]["claim_lifecycle_decision_counts"] == {"suppressed": 2}


def test_initial_source_ineligible_runtime_claim_is_not_seen_by_builder_with_source_reason():
    claims = [
        {
            "claim_id": "report_only_posture",
            "claim_kind": "gameplan_posture",
            "source_confidence": "report_only",
            "source_title": "Fixture Guide",
            "evidence_text_short": "Maintain an aggressive posture.",
        }
    ]
    initial_lifecycle_rows = build_initial_lifecycle_rows(claims)

    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={"deck_name": "FixtureDeck", "cards": []},
        guide_claim_bundle={"claims": claims},
        mulligan_plan={"rules": [], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={"cards": {}},
        initial_lifecycle_rows=initial_lifecycle_rows,
    )

    row = report["claim_lifecycle_rows"][0]

    assert initial_lifecycle_rows[0]["runtime_eligibility"] == "report_only"
    assert row["builder_or_router_decision"] == "not_seen_by_builder"
    assert row["suppressed_reason"] == "source_eligibility"
    assert row["first_missing_link"] == "source_eligibility"
    assert row["final_runtime_effect"] == "not_emitted_by_builder_or_router"


def test_initial_runtime_evidence_required_claim_stays_suppressed_diagnostic():
    claims = [
        {
            "claim_id": "numeric_runtime_evidence",
            "claim_kind": "globalvalue_numeric_tuning",
            "source_confidence": "guide_backed",
            "source_title": "Fixture Guide",
            "evidence_text_short": "Tune LowHpBoardValuePenalty after runtime evidence.",
        }
    ]
    initial_lifecycle_rows = build_initial_lifecycle_rows(claims)

    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={"deck_name": "FixtureDeck", "cards": []},
        guide_claim_bundle={"claims": claims},
        mulligan_plan={"rules": [], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={"cards": {}},
        initial_lifecycle_rows=initial_lifecycle_rows,
    )

    row = report["claim_lifecycle_rows"][0]

    assert initial_lifecycle_rows[0]["runtime_eligibility"] == "runtime_candidate"
    assert row["policy_lane"] == "runtime_evidence_required"
    assert row["builder_or_router_decision"] == "suppressed"
    assert row["suppressed_reason"] == "runtime_evidence_required"
    assert row["first_missing_link"] == "runtime_evidence"
    assert row["operator_impact"] == "diagnostic_only"
    assert row["final_runtime_effect"] == "suppressed_runtime_claim"


def test_initial_policy_report_only_claim_keeps_claim_kind_policy_reason():
    claims = [
        {
            "claim_id": "archetype_context",
            "claim_kind": "archetype",
            "source_confidence": "guide_backed",
            "source_title": "Fixture Guide",
            "evidence_text_short": "The deck is an archetype.",
        }
    ]

    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        guide_claim_bundle={"claims": claims},
        initial_lifecycle_rows=build_initial_lifecycle_rows(claims),
    )

    row = report["claim_lifecycle_rows"][0]

    assert row["runtime_eligibility"] == "runtime_candidate"
    assert row["suppressed_reason"] == "claim_kind_policy"
    assert row["first_missing_link"] == "claim_kind_policy"


def test_source_contract_audit_matches_real_source_claim_ids_and_claim_refs():
    mulligan_bundle, _ = _verified_mulligan_bundle(
        {
            "claim_id": "keep_claim",
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_KEEP"],
            "evidence_text_short": "Keep CARD_KEEP.",
        }
    )
    posture_bundle = _verified_posture_bundle()
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "deck_fingerprint": "fixture-deck-fingerprint",
            "cards": [{"card_id": "CARD_KEEP", "name": "Keep Card", "count": 2}],
        },
        guide_claim_bundle={
            "claims": [
                mulligan_bundle["claims"][0],
                posture_bundle["claims"][0],
            ],
            "canonical_source_receipts": [
                *mulligan_bundle["canonical_source_receipts"],
                *posture_bundle["canonical_source_receipts"],
            ],
        },
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_KEEP",
                    "action": "hold",
                    "source_claim_ids": ["keep_claim"],
                }
            ],
            "suppressed_rules": [],
        },
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [
                {
                    "key": "MyHeroPowerValue",
                    "operation": "increase",
                    "claim_refs": ["posture_claim"],
                }
            ],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={
            "cards": {
                "CARD_KEEP": {
                    "name": "Keep Card",
                    "roles": ["mulligan_anchor"],
                    "runtime_surfaces": ["Mulligan.json"],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "none",
                }
            }
        },
    )

    assert report["claim_rows"]["keep_claim"]["lowered_surfaces"] == ["mulligan"]
    assert report["claim_rows"]["posture_claim"]["lowered_surfaces"] == [
        "globalvalues"
    ]
    assert report["summary"]["runtime_lowered_claims"] == 2


def test_source_contract_audit_counts_merged_mulligan_claim_ids_as_emitted():
    mulligan_bundle, mulligan_identity = _verified_mulligan_bundle(
        {
            "claim_id": "keep_claim_a",
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_KEEP"],
            "evidence_text_short": "Keep CARD_KEEP.",
        },
        {
            "claim_id": "keep_claim_b",
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_KEEP"],
            "evidence_text_short": "CARD_KEEP is also a keep.",
        },
    )
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity=mulligan_identity,
        guide_claim_bundle={
            "claims": mulligan_bundle["claims"],
            "canonical_source_receipts": mulligan_bundle[
                "canonical_source_receipts"
            ],
        },
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_KEEP",
                    "action": "hold",
                    "claim_id": "keep_claim_a",
                    "source_claim_ids": ["raw_keep_a", "raw_keep_b"],
                    "merged_claim_ids": ["keep_claim_a", "keep_claim_b"],
                }
            ],
            "suppressed_rules": [],
        },
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
    )

    rows_by_claim_id = {row["claim_id"]: row for row in report["claim_lifecycle_rows"]}

    assert report["claim_rows"]["keep_claim_a"]["lowered_surfaces"] == ["mulligan"]
    assert report["claim_rows"]["keep_claim_b"]["lowered_surfaces"] == ["mulligan"]
    assert rows_by_claim_id["keep_claim_a"]["builder_or_router_decision"] == "emitted"
    assert rows_by_claim_id["keep_claim_b"]["builder_or_router_decision"] == "emitted"
    assert rows_by_claim_id["keep_claim_b"]["runtime_surface"] == "Mulligan.json"
    assert report["summary"]["runtime_lowered_claims"] == 2


def test_source_contract_audit_preserves_start_of_game_effect_without_mulligan_keep():
    report = build_source_contract_audit(
        deck_name="ShadowPriest",
        deck_identity={
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "SW_448", "name": "Darkbishop Benedictus", "count": 1}],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "darkbishop_effect",
                    "claim_kind": "hero_power_transform",
                    "claim_readiness": "source_backed_static_semantics",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["SW_448"],
                    "source_title": "Hearthstone card data",
                    "evidence_text_short": "Start of Game hero power transform.",
                },
                {
                    "claim_id": "bad_keep",
                    "claim_kind": "mulligan_keep",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["SW_448"],
                    "source_title": "Bad fixture",
                    "evidence_text_short": "Keep because the effect matters.",
                },
            ]
        },
        mulligan_plan={
            "rules": [],
            "suppressed_rules": [
                {
                    "claim_id": "bad_keep",
                    "card": "SW_448",
                    "reason": "start_of_game_effect_does_not_require_opening_hand",
                }
            ],
        },
        card_behavior_plan={
            "rows": [
                {
                    "claim_id": "darkbishop_effect",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "surface_family": "CARDID.json",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforeUseHeroPowerBonus": {"values": []}},
                }
            ],
            "suppressed": [],
        },
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={
            "cards": {
                "SW_448": {
                    "name": "Darkbishop Benedictus",
                    "roles": ["start_of_game", "hero_power_transform"],
                    "runtime_surfaces": ["EX1_625t.json"],
                    "readiness_lane": "linked_runtime_source",
                    "first_missing_link": "none",
                }
            }
        },
    )

    assert report["claim_rows"]["darkbishop_effect"]["lane"] == "runtime_lowered"
    assert report["claim_rows"]["darkbishop_effect"]["surfaces"]["cardid"]["allowed"] is True
    assert report["claim_rows"]["bad_keep"]["lane"] == "suppressed_with_reason"
    assert report["claim_rows"]["bad_keep"]["first_reason"] == (
        "start_of_game_effect_does_not_require_opening_hand"
    )
    assert report["card_rows"]["SW_448"]["claim_lanes"]["runtime_lowered"] == 1
    assert report["card_rows"]["SW_448"]["claim_lanes"]["suppressed_with_reason"] == 1
    effect_lifecycle = next(
        row
        for row in report["claim_lifecycle_rows"]
        if row["claim_id"] == "darkbishop_effect"
    )
    assert effect_lifecycle["runtime_surface"] == "EX1_625t.json"
    assert effect_lifecycle["emitted_files"] == ["EX1_625t.json"]


def test_source_contract_audit_markdown_is_compact_and_operator_readable():
    report = {
        "deck_name": "FixtureDeck",
        "summary": {
            "claims_total": 2,
            "runtime_lowered_claims": 1,
            "suppressed_claims": 1,
            "runtime_evidence_required_claims": 0,
            "report_only_claims": 0,
            "cards_total": 1,
            "cards_with_missing_links": 1,
        },
        "card_rows": {
            "CARD_001": {
                "name": "Fixture Card",
                "readiness_lane": "report_only_supported",
                "first_missing_link": "needs_runtime_surface",
                "runtime_surfaces": [],
                "claim_lanes": {"suppressed_with_reason": 1},
            }
        },
    }

    markdown = render_source_contract_audit_markdown(report)

    assert "# Source Contract Audit - FixtureDeck" in markdown
    assert "Runtime-lowered claims: 1" in markdown
    assert "| CARD_001 Fixture Card | report_only_supported | needs_runtime_surface |" in markdown


def test_source_contract_audit_adds_policy_lane_for_each_claim():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "cards": [{"card_id": "CARD_001", "name": "Fixture", "count": 1}],
        },
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "posture",
                    "claim_kind": "gameplan_posture",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_001"],
                    "source_title": "Fixture",
                    "evidence_text_short": "Push aggressive posture.",
                },
                {
                    "claim_id": "numeric",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_001"],
                    "source_title": "Fixture",
                    "evidence_text_short": "Tune a numeric key after games.",
                },
            ]
        },
        global_values_authority_matrix={
            "allowed_step1_overlays": [
                {"key": "MyHeroPowerValue", "claim_refs": ["posture"]}
            ],
            "blocked_until_runtime_evidence": [
                {"key": "LowHpBoardValuePenalty", "claim_id": "numeric"}
            ],
        },
    )

    assert report["claim_rows"]["posture"]["policy_lane"] == "runtime_lowerable"
    assert report["claim_rows"]["numeric"]["policy_lane"] == "runtime_evidence_required"
    assert report["summary"]["claim_kind_policy_counts"]["runtime_lowerable"] == 1
    assert report["summary"]["claim_kind_policy_counts"]["runtime_evidence_required"] == 1


def test_source_contract_audit_marks_unknown_claim_kind_as_unsupported_or_unmapped():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "unknown",
                    "claim_kind": "future_claim_kind",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_title": "Fixture",
                    "evidence_text_short": "Future claim.",
                }
            ]
        },
    )

    assert report["claim_rows"]["unknown"]["policy_lane"] == "unsupported_or_unmapped"
    assert report["claim_rows"]["unknown"]["lane"] == "unsupported_or_unmapped"


def test_source_contract_audit_policy_matrix_failure_is_nonblocking(monkeypatch):
    def fail_policy_matrix():
        raise RuntimeError("stale source contract policy")

    monkeypatch.setattr(
        "hsconfig.source_contract_audit.source_contract_policy_by_claim_kind",
        fail_policy_matrix,
    )

    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "posture",
                    "claim_kind": "gameplan_posture",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "source_title": "Fixture",
                    "evidence_text_short": "Aggressive posture.",
                }
            ]
        },
    )

    assert report["claim_rows"]["posture"]["policy_lane"] == "unsupported_or_unmapped"
    assert report["summary"]["claim_kind_policy_counts"] == {
        "unsupported_or_unmapped": 1
    }


def test_claim_lifecycle_marks_allowed_claim_without_builder_emission_as_not_seen_by_builder():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "deck_fingerprint": "fixture-deck-fingerprint",
            "cards": [],
        },
            guide_claim_bundle={
                "claims": [_verified_posture_claim()],
                "globalvalues_source_receipts": _verified_posture_bundle()[
                    "globalvalues_source_receipts"
                ],
            },
        mulligan_plan={"rules": [], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={"cards": {}},
    )

    row = report["claim_lifecycle_rows"][0]

    assert row["claim_id"] == "posture_claim"
    assert row["claim_kind"] == "gameplan_posture"
    assert row["surface_gate_decision"] == "allowed"
    assert row["surface_gate_reason"] == "allowed"
    assert row["builder_or_router_decision"] == "not_seen_by_builder"
    assert row["suppressed_reason"] == "builder_or_router_missing"
    assert row["first_missing_link"] == "builder_or_router"
    assert row["operator_impact"] == "diagnostic_only"


def test_source_contract_audit_summarizes_claim_lifecycle_decisions():
    report = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={
            "deck_name": "FixtureDeck",
            "deck_fingerprint": "fixture-deck-fingerprint",
            "cards": [{"card_id": "CARD_KEEP", "name": "Keep Card", "count": 2}],
        },
            guide_claim_bundle={
                "claims": [
                {
                    "claim_id": "keep_claim",
                    "claim_kind": "mulligan_keep",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": ["CARD_KEEP"],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Keep CARD_KEEP.",
                },
                _verified_posture_claim(),
                {
                    "claim_id": "numeric_claim",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "runtime_candidate",
                    "cards": [],
                    "source_title": "Fixture Guide",
                    "evidence_text_short": "Tune a numeric GlobalValues key only after games.",
                    },
                ],
                "globalvalues_source_receipts": _verified_posture_bundle()[
                    "globalvalues_source_receipts"
                ],
            },
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_KEEP",
                    "action": "hold",
                    "source_claim_ids": ["keep_claim"],
                }
            ],
            "suppressed_rules": [],
        },
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [
                {
                    "key": "LowHpBoardValuePenalty",
                    "claim_id": "numeric_claim",
                    "reason": "runtime_evidence_required",
                }
            ],
        },
        config_readiness_report={
            "cards": {
                "CARD_KEEP": {
                    "name": "Keep Card",
                    "roles": ["mulligan_anchor"],
                    "runtime_surfaces": ["Mulligan.json"],
                    "readiness_lane": "mulligan_only",
                    "first_missing_link": "none",
                }
            }
        },
    )

    assert report["summary"]["claim_lifecycle_decision_counts"] == {
        "emitted": 1,
        "not_seen_by_builder": 1,
        "suppressed": 1,
    }
