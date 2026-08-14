from hsconfig.source_bundle import build_source_bundle


def test_source_bundle_exposes_source_claim_runtime_chain():
    bundle = build_source_bundle(
        deck_name="ShadowPriest",
        deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        source_records=[
            {
                "source_id": "src-shadowpriest-guide",
                "source_type": "community_guide",
                "source_url": "https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "deck_or_archetype_matched",
            }
        ],
        claims=[
            {
                "claim_id": "claim-sw448-transform",
                "source_id": "src-shadowpriest-guide",
                "claim_kind": "hero_power_transform",
                "card_ids": ["SW_448"],
                "opening_hand_relevant": False,
                "runtime_lowering": "cardid_or_contract_only",
                "promotion_eligible": True,
            }
        ],
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strong_ready": True,
            "first_missing_source_action": "none",
            "source_missing_source_actions": [],
            "source_status_reasons": [],
            "source_status_diagnostic_only": True,
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": [],
            "pre_run_contract_status": "complete",
            "strategy_authority_status": "strong",
        },
        explainability_report={
            "card_rows": [
                {
                    "card_id": "SW_448",
                    "strongest_claim_kind": "hero_power_transform",
                    "runtime_backed": True,
                    "first_missing_link": None,
                    "next_source_action": "none",
                }
            ]
        },
    )

    assert bundle["schema_version"] == 1
    assert bundle["deck"]["name"] == "ShadowPriest"
    assert bundle["source_record_count"] == 1
    assert bundle["claim_count"] == 1
    assert bundle["default_only_runtime_surfaces"] == []
    assert bundle["promotion"]["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert bundle["promotion"]["source_strong_ready"] is True
    assert bundle["promotion"]["first_missing_source_action"] == "none"
    assert bundle["promotion"]["source_missing_source_actions"] == []
    assert bundle["promotion"]["source_status_reasons"] == []
    assert bundle["promotion"]["source_status_diagnostic_only"] is True
    assert bundle["promotion"]["source_status_apply_blocking"] is False
    assert bundle["card_coverage"][0]["card_id"] == "SW_448"
    assert bundle["pre_run_contract"] == {
        "hsconfig_scope": "PRE_RUN_CONTRACT",
        "gameplay_strategy_owner": "hearthranger_bot",
        "gameplay_quality": "OUT_OF_SCOPE_ASSUMED_EXTERNAL",
        "bot_gameplay_assumption": "trusted_external",
        "pre_run_contract_status": "complete",
        "strategy_authority_status": "strong",
        "diagnostic_only": True,
        "apply_blocking": False,
    }


def test_source_bundle_uses_operator_summary_as_source_status_authority():
    bundle = build_source_bundle(
        deck_name="ThinDeck",
        deck_code="AAEBA-test",
        source_records=[],
        claims=[],
        operator_summary={
            "source_backed_status": "SOURCE_BACKED_PARTIAL",
            "first_missing_source_action": "add_operator_declared_source_action",
            "source_missing_source_actions": ["add_operator_declared_source_action"],
            "source_status_reasons": ["operator_summary_declared_gap"],
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": [],
        },
        explainability_report={
            "card_rows": [
                {
                    "first_missing_source_action": "stale_explainability_gap",
                    "next_source_action": "map_claim_kind_or_keep_report_only",
                }
            ]
        },
    )

    assert (
        bundle["promotion"]["first_missing_source_action"]
        == "add_operator_declared_source_action"
    )
    assert bundle["promotion"]["source_missing_source_actions"] == [
        "add_operator_declared_source_action"
    ]
    assert bundle["promotion"]["source_status_reasons"] == [
        "operator_summary_declared_gap"
    ]
    assert bundle["promotion"]["source_status_apply_blocking"] is False


def test_source_bundle_uses_canonical_operator_promotion_fields() -> None:
    bundle = build_source_bundle(
        deck_name="PartialDeck",
        deck_code="AAEBA-partial",
        source_records=[],
        claims=[],
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_status": "SOURCE_BACKED_PARTIAL",
            "source_strong_ready": False,
            "first_missing_source_action": "add_profile_runtime_surface",
            "source_missing_source_actions": ["add_profile_runtime_surface"],
            "source_status_reasons": ["source_claim_gap"],
            "source_status_diagnostic_only": True,
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": [],
        },
        explainability_report={
            "card_rows": [
                {
                    "first_missing_source_action": "none",
                    "next_source_action": "none",
                }
            ]
        },
    )

    assert bundle["promotion"]["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert bundle["promotion"]["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert (
        bundle["promotion"]["first_missing_source_action"]
        == "add_profile_runtime_surface"
    )
    assert bundle["promotion"]["source_strong_ready"] is False
    assert bundle["promotion"]["source_missing_source_actions"] == [
        "add_profile_runtime_surface"
    ]
    assert bundle["promotion"]["source_status_reasons"] == ["source_claim_gap"]
    assert bundle["promotion"]["source_status_diagnostic_only"] is True
    assert bundle["promotion"]["source_status_apply_blocking"] is False
