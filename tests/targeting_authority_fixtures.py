from __future__ import annotations

from typing import Any

from hsconfig.source_document_builder import build_source_document_bundle
from tests.helpers.live_acquisition import acquire_live_test_provenance


TARGETING_DECK_FINGERPRINT = "targeting-authority-deck-fingerprint"


def build_canonical_targeting_bundle() -> tuple[dict[str, Any], dict[str, Any]]:
    deck_identity = {
        "deck_name": "TargetingAuthority",
        "deck_fingerprint": TARGETING_DECK_FINGERPRINT,
        "cards": [
            {"card_id": "CARD_TARGET", "name": "Target Card", "count": 1},
            {"card_id": "CARD_OTHER", "name": "Other Card", "count": 1},
        ],
    }
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/targeting-authority-guide",
                "source_title": "Targeting authority exact-deck guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "acquisition_provenance": acquire_live_test_provenance(
                    b"<html><body>Targeting authority guide.</body></html>"
                ),
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": TARGETING_DECK_FINGERPRINT,
                        "candidate_deck_code_hashes": [
                            "sha256:targeting-authority-source"
                        ],
                    }
                },
                "claims": [
                    {
                        "claim_id": "targeting-authorized",
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_TARGET"],
                        "scope": "card",
                        "stance": "prefer_enemy_minion",
                        "target_scope": "enemy_minion",
                        "runtime_block": "BeforeBattlecryTargetBonus",
                        "condition": "my_target(count(),minion=true) > 0",
                        "runtime_value": "12",
                        "evidence_text_short": (
                            "Target the enemy minion with Target Card."
                        ),
                        "source_confidence": "high",
                        "promotion_eligible": True,
                    },
                    {
                        "claim_id": "targeting-other-claim",
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_OTHER"],
                        "scope": "card",
                        "stance": "prefer_enemy_hero",
                        "target_scope": "enemy_hero",
                        "runtime_block": "BeforeBattlecryTargetBonus",
                        "condition": "my_target(count(),hero=true) > 0",
                        "runtime_value": "12",
                        "evidence_text_short": (
                            "Target the enemy hero with Other Card."
                        ),
                        "source_confidence": "high",
                        "promotion_eligible": True,
                    },
                ],
            }
        ],
        current_date="2026-07-26",
    )
    return bundle, deck_identity


def targeting_gate_context(
    bundle: dict[str, Any],
    deck_identity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "deck_identity": deck_identity,
        "verified_source_receipts": bundle["canonical_source_receipts"],
    }
