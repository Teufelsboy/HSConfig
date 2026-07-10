from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.config_readiness import build_config_readiness_report
from hsconfig.guide_claim_builder import build_guide_claim_bundle


def test_mechanic_lowering_parity_micro_fixture_connects_claims_to_runtime_reports():
    card_metadata = {
        "DEATH_001": {
            "card_id": "DEATH_001",
            "name": "Deathrattle Test",
            "type": "MINION",
            "text": "Deathrattle: Summon a 1/1 minion.",
            "mechanics": ["DEATHRATTLE"],
        },
        "RUSH_001": {
            "card_id": "RUSH_001",
            "name": "Rush Test",
            "type": "MINION",
            "text": "Rush",
            "mechanics": ["RUSH"],
        },
        "SPELLBURST_001": {
            "card_id": "SPELLBURST_001",
            "name": "Spellburst Test",
            "type": "MINION",
            "text": "Spellburst: Draw a card.",
            "mechanics": ["SPELLBURST"],
        },
        "DREDGE_001": {
            "card_id": "DREDGE_001",
            "name": "Dredge Test",
            "type": "SPELL",
            "text": "Dredge.",
            "mechanics": ["DREDGE"],
        },
        "TRADE_001": {
            "card_id": "TRADE_001",
            "name": "Tradeable Test",
            "type": "SPELL",
            "text": "Tradeable",
            "mechanics": ["TRADEABLE"],
        },
        "DISCOVER_001": {
            "card_id": "DISCOVER_001",
            "name": "Discover Test",
            "type": "MINION",
            "text": "Battlecry: Discover a spell.",
            "mechanics": ["BATTLECRY", "DISCOVER"],
        },
        "CHOOSE_001": {
            "card_id": "CHOOSE_001",
            "name": "Choice Test",
            "type": "SPELL",
            "text": "Pick one of two effects.",
        },
    }
    source_documents = [
        {
            "source_url": "https://example.invalid/mechanic-parity-guide",
            "source_title": "Mechanic Parity Fixture Guide",
            "source_family": "guide",
            "retrieved_at": "2026-07-10T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "mechanic_usage",
                    "cards": ["DREDGE_001"],
                    "mechanic": "dredge",
                    "stance": "use_dredge_when_value_is_high",
                    "evidence_text_short": "The guide says Dredge improves draw quality.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "mechanic_usage",
                    "cards": ["TRADE_001"],
                    "mechanic": "tradeable",
                    "stance": "trade_when_not_needed",
                    "evidence_text_short": "The guide says Tradeable cards can be cycled.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "mechanic_usage",
                    "cards": ["DISCOVER_001"],
                    "mechanic": "discover",
                    "stance": "use_discover_for_value",
                    "evidence_text_short": "The guide values the Discover effect.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "choose_one_choice",
                    "cards": ["CHOOSE_001"],
                    "choice_card_id": "CHOICE_OPTION_A",
                    "stance": "prefer_option_a",
                    "evidence_text_short": "The guide prefers option A, but no linked entity is resolved.",
                    "source_confidence": "high",
                },
            ],
        }
    ]
    deck_identity = {
        "deck_name": "MechanicParity",
        "deck_slug": "mechanicparity",
        "cards": [
            {"card_id": card_id, "name": card["name"], "count": 1}
            for card_id, card in card_metadata.items()
        ],
    }

    bundle = build_guide_claim_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_documents=source_documents,
    )
    behavior_plan = route_card_behavior_surfaces(bundle["claims"])
    contract = _contract_from_claims(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        claims=bundle["claims"],
    )
    cardid_files = compile_cardid_behaviors(contract, rows=behavior_plan["rows"])
    readiness = build_config_readiness_report(
        deck_identity=deck_identity,
        claim_coverage=bundle["claim_coverage_report"],
        gameplan_contract=contract,
        mulligan_plan={"rules": []},
        card_behavior_plan=behavior_plan,
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files=list(cardid_files),
    )

    assert _behavior_blocks(behavior_plan, "DEATH_001") == {"BeforePlayCardBonus"}
    assert _behavior_blocks(behavior_plan, "RUSH_001") == {"BeforePhysicalAttackBonus"}
    assert _behavior_blocks(behavior_plan, "SPELLBURST_001") == {"BeforePlayCardBonus"}
    assert "OnDiscoverCardBonus" in _behavior_blocks(behavior_plan, "DISCOVER_001")
    assert {
        (row["claim_kind"], tuple(row["cards"]), row["reason"])
        for row in behavior_plan["suppressed"]
    } >= {
        ("mechanic_usage", ("DREDGE_001",), "dredge_has_no_documented_runtime_block"),
        ("mechanic_usage", ("TRADE_001",), "tradeable_has_no_documented_runtime_block"),
        ("choose_one_choice", ("CHOOSE_001",), "unresolved_option_identity"),
    }

    assert len(cardid_files) == len(card_metadata)
    for card_id in card_metadata:
        card_file = cardid_files[f"{card_id}.json"]
        assert card_file["GameCardId"] == card_id
        assert "InHandPlayPriority" in card_file
    assert "BeforePlayCardBonus" not in cardid_files["TRADE_001.json"]
    assert "OnDiscoverCardBonus" not in cardid_files["DREDGE_001.json"]

    assert readiness["cards"]["DEATH_001"]["readiness_lane"] == "runtime_emitted"
    assert readiness["cards"]["RUSH_001"]["readiness_lane"] == "runtime_emitted"
    assert readiness["cards"]["SPELLBURST_001"]["readiness_lane"] == "runtime_emitted"
    assert readiness["summary"]["cards_needing_mechanic_lowering"] == 0
    assert "needs_mechanic_lowering" not in {
        row["first_missing_link"] for row in readiness["cards"].values()
    }
    assert readiness["summary"]["mechanic_visibility"]["mechanics_by_bucket"][
        "warning_only"
    ] == ["dredge", "tradeable"]


def _contract_from_claims(
    *,
    deck_identity: dict,
    card_metadata: dict[str, dict],
    claims: list[dict],
) -> dict:
    roles_by_card = {card_id: [] for card_id in card_metadata}
    source_claim_ids_by_card = {card_id: [] for card_id in card_metadata}
    coverage_by_card = {card_id: "source_backed_static_semantics" for card_id in card_metadata}
    for claim in claims:
        for card_id in claim.get("cards", []):
            if card_id not in roles_by_card:
                continue
            source_claim_ids_by_card[card_id].append(claim["claim_id"])
            confidence = str(claim.get("confidence", "source_backed_static_semantics"))
            if confidence == "guide_backed":
                coverage_by_card[card_id] = "guide_backed"
            if claim.get("claim_kind") == "mechanic_usage" and claim.get("mechanic"):
                roles_by_card[card_id].append(str(claim["mechanic"]))

    return {
        "deck_name": deck_identity["deck_name"],
        "deck_slug": deck_identity["deck_slug"],
        "cards": {
            card_id: {
                "card_id": card_id,
                "name": card["name"],
                "count": 1,
                "coverage_status": coverage_by_card[card_id],
                "confidence": coverage_by_card[card_id],
                "roles": sorted(set(roles_by_card[card_id])),
                "source_claim_ids": sorted(set(source_claim_ids_by_card[card_id])),
            }
            for card_id, card in card_metadata.items()
        },
    }


def _behavior_blocks(plan: dict, card_id: str) -> set[str]:
    return {
        row["behavior_block"]
        for row in plan["rows"]
        if row.get("card_id") == card_id and row.get("behavior_block")
    }
