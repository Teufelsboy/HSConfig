from __future__ import annotations

from hsconfig.research_result_contract import classify_research_result_contract


def _strong_payload() -> dict[str, object]:
    return {
        "deck_name": "ShadowPriest",
        "deck_code": "AAEBAa0GExample",
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "first_missing_source_action": "none",
        "source_visibility": "full_text",
        "freshness_status": "current",
        "lowerable_claim_kinds": ["mulligan_keep", "gameplan_posture"],
    }


def test_seed_only_payload_stays_diagnostic_and_non_promoting() -> None:
    result = classify_research_result_contract(
        {
            "deck_name": "ShadowPriest",
            "deck_code": "AAEBAa0GExample",
            "source_strength": "unfetched_acquisition_seed",
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
            "lowerable_claim_kinds": [],
        }
    )

    assert result == {
        "contract_valid": True,
        "snapshot_kind": "seed_only",
        "canonical_promotion_allowed": False,
        "canonical_downgrade_allowed": False,
        "source_status_apply_blocking": False,
        "errors": [],
        "warnings": [],
        "lowerable_claim_kinds": [],
    }


def test_decklist_or_stats_only_payload_stays_diagnostic_and_non_promoting() -> None:
    result = classify_research_result_contract(
        {
            "deck_name": "CtAPaladin",
            "deck_code": "AAEBAZ8FExample",
            "source_strength": "decklist_or_stats_only",
            "first_missing_source_action": "add_explicit_mulligan_source",
            "lowerable_claim_kinds": [],
        }
    )

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "seed_only"
    assert result["canonical_promotion_allowed"] is False
    assert result["canonical_downgrade_allowed"] is False
    assert result["source_status_apply_blocking"] is False


def test_seed_only_payload_with_deck_name_only_stays_diagnostic() -> None:
    result = classify_research_result_contract(
        {
            "deck_name": "ShadowPriest",
            "source_strength": "unfetched_acquisition_seed",
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
        }
    )

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "seed_only"
    assert result["canonical_promotion_allowed"] is False
    assert result["errors"] == []


def test_seed_only_payload_with_malformed_default_only_surfaces_is_invalid() -> None:
    result = classify_research_result_contract(
        {
            "deck_name": "ShadowPriest",
            "source_strength": "unfetched_acquisition_seed",
            "first_missing_source_action": (
                "fetch_and_normalize_candidate_full_text_claims"
            ),
            "default_only_runtime_surfaces": "mulligan",
        }
    )

    assert result["contract_valid"] is False
    assert result["snapshot_kind"] == "invalid"
    assert result["canonical_promotion_allowed"] is False
    assert "default_only_runtime_surfaces_must_be_list" in result["errors"]
    assert result["source_status_apply_blocking"] is False


def test_snippet_only_evidence_is_partial_and_non_promoting() -> None:
    result = classify_research_result_contract(
        {
            "deck_name": "ShadowPriest",
            "deck_code": "AAEBAa0GExample",
            "source_strength": "snippet_only",
            "lowerable_claim_kinds": [],
        }
    )

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "partial"
    assert result["canonical_promotion_allowed"] is False
    assert result["canonical_downgrade_allowed"] is False
    assert result["source_status_apply_blocking"] is False


def test_strong_payload_with_lowerable_claim_kinds_is_promotion_eligible() -> None:
    result = classify_research_result_contract(_strong_payload())

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "strong"
    assert result["canonical_promotion_allowed"] is True
    assert result["canonical_downgrade_allowed"] is False
    assert result["source_status_apply_blocking"] is False
    assert result["lowerable_claim_kinds"] == ["gameplan_posture", "mulligan_keep"]


def test_research_deep_full_text_strength_can_be_promotion_eligible() -> None:
    payload = _strong_payload()
    payload.pop("source_backed_status")
    payload["source_strength"] = "exact_full_text_guide"
    payload["source_visibility"] = "full_text"

    result = classify_research_result_contract(payload)

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "strong"
    assert result["canonical_promotion_allowed"] is True


def test_full_text_strength_without_current_or_evergreen_metadata_is_partial() -> None:
    payload = _strong_payload()
    payload.pop("source_backed_status")
    payload.pop("freshness_status")
    payload["source_strength"] = "exact_full_text_guide"
    payload["source_visibility"] = "full_text"

    result = classify_research_result_contract(payload)

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "partial"
    assert result["canonical_promotion_allowed"] is False
    assert "missing_current_or_evergreen_source_metadata" in result["warnings"]


def test_strong_source_strength_is_accepted_when_status_is_partial() -> None:
    payload = _strong_payload()
    payload["source_status"] = "SOURCE_BACKED_PARTIAL"
    payload["source_strength"] = "SOURCE_BACKED_STRONG"
    payload.pop("source_backed_status")

    result = classify_research_result_contract(payload)

    assert result["snapshot_kind"] == "strong"
    assert result["canonical_promotion_allowed"] is True


def test_strong_looking_payload_without_lowerable_claim_kinds_is_partial() -> None:
    payload = _strong_payload()
    payload["lowerable_claim_kinds"] = []

    result = classify_research_result_contract(payload)

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "partial"
    assert result["canonical_promotion_allowed"] is False
    assert "no_lowerable_claim_kinds" in result["warnings"]


def test_strong_looking_payload_with_report_only_claim_kind_is_partial() -> None:
    payload = _strong_payload()
    payload["lowerable_claim_kinds"] = ["archetype"]

    result = classify_research_result_contract(payload)

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "partial"
    assert result["canonical_promotion_allowed"] is False
    assert result["lowerable_claim_kinds"] == []
    assert "no_lowerable_claim_kinds" in result["warnings"]


def test_strong_looking_payload_with_default_only_surfaces_is_partial() -> None:
    payload = _strong_payload()
    payload["default_only_runtime_surfaces"] = ["mulligan"]

    result = classify_research_result_contract(payload)

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "partial"
    assert result["canonical_promotion_allowed"] is False
    assert "default_only_runtime_surfaces_present" in result["warnings"]


def test_strong_looking_payload_with_nested_malformed_default_only_surfaces_is_invalid() -> None:
    payload = _strong_payload()
    payload["default_only_runtime_surfaces"] = []
    payload["records"] = [{"default_only_runtime_surfaces": "mulligan"}]

    result = classify_research_result_contract(payload)

    assert result["contract_valid"] is False
    assert result["snapshot_kind"] == "invalid"
    assert result["canonical_promotion_allowed"] is False
    assert "default_only_runtime_surfaces_must_be_list" in result["errors"]
    assert result["source_status_apply_blocking"] is False


def test_strong_looking_payload_with_missing_source_action_is_partial() -> None:
    payload = _strong_payload()
    payload["first_missing_source_action"] = "add_explicit_mulligan_source"

    result = classify_research_result_contract(payload)

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "partial"
    assert result["canonical_promotion_allowed"] is False
    assert "first_missing_source_action_not_none" in result["warnings"]


def test_strong_looking_snippet_evidence_is_partial() -> None:
    payload = _strong_payload()
    payload["source_visibility"] = "snippet_only"

    result = classify_research_result_contract(payload)

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "partial"
    assert result["canonical_promotion_allowed"] is False
    assert "missing_full_text_or_canonical_evidence" in result["warnings"]


def test_missing_identity_is_invalid_and_non_blocking() -> None:
    result = classify_research_result_contract(
        {
            "source_strength": "unfetched_acquisition_seed",
            "lowerable_claim_kinds": [],
        }
    )

    assert result["contract_valid"] is False
    assert result["snapshot_kind"] == "invalid"
    assert result["canonical_promotion_allowed"] is False
    assert result["canonical_downgrade_allowed"] is False
    assert result["source_status_apply_blocking"] is False
    assert "missing_deck_identity" in result["errors"]


def test_no_payload_can_request_canonical_downgrade() -> None:
    payload = _strong_payload()
    payload["canonical_downgrade_allowed"] = True

    result = classify_research_result_contract(payload)

    assert result["canonical_downgrade_allowed"] is False


def test_research_result_contract_accepts_nested_evergreen_marker_for_strong_promotion() -> None:
    result = classify_research_result_contract(
        {
            "deck_name": "TreantDruid",
            "deck_code": "AAEBAZICFixture",
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
            "guide_sources": [
                {
                    "source_freshness_lane": "guide_evergreen_wild_archetype",
                    "current_or_evergreen_reason": "wild_guide_with_card_overlap",
                }
            ],
        }
    )

    assert result["contract_valid"] is True
    assert result["snapshot_kind"] == "strong"
    assert result["canonical_promotion_allowed"] is True
    assert result["source_status_apply_blocking"] is False


def test_research_result_contract_keeps_canonical_evidence_current_for_strong_promotion() -> None:
    result = classify_research_result_contract(
        {
            "deck_name": "TreantDruid",
            "deck_code": "AAEBAZICFixture",
            "source_strength": "exact_full_text_guide",
            "canonical_evidence": True,
            "lowerable_claim_kinds": ["mulligan_keep"],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
        }
    )

    assert result["snapshot_kind"] == "strong"
    assert result["canonical_promotion_allowed"] is True
    assert result["source_status_apply_blocking"] is False
