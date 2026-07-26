from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from hsconfig.source_document_builder import build_source_document_bundle


MULLIGAN_AUTHORITY_FINGERPRINT = "sha256:test-mulligan-authority"


def build_canonical_mulligan_bundle(
    claims: Iterable[Mapping[str, Any]],
    *,
    deck_fingerprint: str = MULLIGAN_AUTHORITY_FINGERPRINT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_claims = [dict(claim) for claim in claims]
    card_ids = sorted(
        {
            str(card_id)
            for claim in raw_claims
            for card_id in claim.get("cards", [])
            if str(card_id)
        }
    )
    deck_identity = {
        "deck_name": "CanonicalMulliganFixture",
        "deck_fingerprint": deck_fingerprint,
        "cards": [
            {
                "card_id": card_id,
                "name": f"Fixture {card_id}",
                "count": 1,
            }
            for card_id in card_ids
        ],
    }
    normalized_claims = []
    for index, claim in enumerate(raw_claims, start=1):
        claim_kind = str(claim.get("claim_kind", "mulligan_keep"))
        normalized_claims.append(
            {
                "claim_id": f"canonical-mulligan-{index}",
                "claim_kind": claim_kind,
                "scope": "card",
                "stance": (
                    "discard" if claim_kind == "mulligan_discard" else "keep"
                ),
                "evidence_text_short": (
                    "Discard this card from the opening hand."
                    if claim_kind == "mulligan_discard"
                    else "Keep this card in the opening hand."
                ),
                "source_confidence": "high",
                "promotion_eligible": True,
                **claim,
            }
        )
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.test/canonical-mulligan-guide",
                "source_title": "Canonical Mulligan Guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "acquisition_provenance": {
                    "mode": "live_http",
                    "content_sha256": "sha256:" + ("a" * 64),
                    "authority": "live_verified",
                },
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": (
                            deck_fingerprint
                        ),
                        "candidate_deck_code_hashes": [
                            "sha256:test-mulligan-source"
                        ],
                    }
                },
                "claims": normalized_claims,
            }
        ],
        current_date="2026-07-26",
    )
    return bundle, deck_identity


def canonical_mulligan_gate_context(
    bundle: Mapping[str, Any],
    deck_identity: Mapping[str, Any],
    *,
    card_roles: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    context = {
        "deck_identity": dict(deck_identity),
        "verified_source_receipts": [
            dict(receipt)
            for receipt in bundle.get("canonical_source_receipts", [])
        ],
    }
    if card_roles is not None:
        context["card_roles"] = dict(card_roles)
    return context
