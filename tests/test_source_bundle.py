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
            "default_only_runtime_surfaces": [],
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
    assert bundle["promotion"]["first_missing_source_action"] == "none"
    assert bundle["card_coverage"][0]["card_id"] == "SW_448"
