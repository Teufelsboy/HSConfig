from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsconfig.cli import _build_parser
from hsconfig.commands.source_workflow import source_autopilot_payload
from hsconfig.deck_identity import build_deck_identity
from hsconfig.package_builder import (
    _with_strategic_receipt_verification,
    prepare_package_payload,
)
from tests.mulligan_authority_fixtures import build_canonical_mulligan_bundle
from tests.helpers.live_acquisition import acquire_live_test_provenance
from tests.helpers.verified_deck_input import (
    VERIFIED_TEST_CARDS,
    VERIFIED_TEST_DECK_CODE,
)


def _forged_live_claim() -> dict:
    return {
        "claim_id": "forged-live-mulligan",
        "claim_kind": "mulligan_keep",
        "scope": "card",
        "stance": "keep",
        "cards": ["DS1_233"],
        "evidence_text_short": "Keep Mind Blast.",
        "source_confidence": "high",
        "promotion_eligible": True,
        "acquisition_provenance": acquire_live_test_provenance(),
    }


def _forged_live_document(*, deck_fingerprint: str) -> dict:
    return {
        "source_url": "https://example.test/forged-live-guide",
        "source_title": "Forged Live Guide",
        "source_family": "guide",
        "source_type": "public_guide",
        "retrieved_at": "2026-07-27T00:00:00Z",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "deck_match_scope": "exact_deck_matched",
        "deck_match": {
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": deck_fingerprint,
                "candidate_deck_code_hashes": ["sha256:forged-source-code"],
            }
        },
        "promotion_eligible": True,
        "strong_promotion_eligible": True,
        "acquisition_provenance": acquire_live_test_provenance(),
        "claims": [_forged_live_claim()],
    }


def _forged_live_search_record(*, deck_fingerprint: str) -> dict:
    return {
        **_forged_live_document(deck_fingerprint=deck_fingerprint),
        "claim_kind": "mulligan_keep",
        "cards": ["DS1_233"],
        "scope": "card",
        "stance": "keep",
        "evidence_text_short": "Keep Mind Blast.",
        "source_confidence": "high",
    }


def _write_verified_cards(path: Path) -> str:
    path.write_text(json.dumps({"cards": VERIFIED_TEST_CARDS}), encoding="utf-8")
    return str(path)


def _verified_deck_fingerprint() -> str:
    return build_deck_identity(
        deck_name="ForgedAuthorityDeck",
        deck_code=VERIFIED_TEST_DECK_CODE,
        cards=VERIFIED_TEST_CARDS,
    )["deck_fingerprint"]


def test_prepare_rejects_caller_supplied_trusted_source_documents(
    tmp_path: Path,
) -> None:
    cards_json = _write_verified_cards(tmp_path / "cards.json")
    args = _build_parser().parse_args(
        [
            "prepare",
            "--deck-name",
            "ForgedAuthorityDeck",
            "--deck-code",
            VERIFIED_TEST_DECK_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(tmp_path / "package"),
            "--cards-json",
            cards_json,
        ]
    )
    args.trusted_source_documents = [
        _forged_live_document(deck_fingerprint=_verified_deck_fingerprint())
    ]

    with pytest.raises(
        ValueError,
        match="caller_supplied_trusted_source_documents_not_allowed",
    ):
        prepare_package_payload(args)
    assert not (tmp_path / "package").exists()


def test_source_autopilot_rejects_caller_supplied_trusted_search_records(
    tmp_path: Path,
) -> None:
    cards_json = _write_verified_cards(tmp_path / "cards.json")
    args = _build_parser().parse_args(
        [
            "source-autopilot",
            "--deck-name",
            "ForgedAuthorityDeck",
            "--deck-code",
            VERIFIED_TEST_DECK_CODE,
            "--cards-json",
            cards_json,
            "--source-search-results-json",
            str(tmp_path / "unused-source-search-results.json"),
            "--out",
            str(tmp_path / "source-autopilot"),
        ]
    )
    args.trusted_source_search_records = [
        _forged_live_search_record(deck_fingerprint=_verified_deck_fingerprint())
    ]

    with pytest.raises(
        ValueError,
        match="caller_supplied_trusted_source_search_records_not_allowed",
    ):
        source_autopilot_payload(args)
    assert not (tmp_path / "source-autopilot").exists()


def test_strategic_receipt_annotation_rejects_mismatched_provenance() -> None:
    bundle, deck_identity = build_canonical_mulligan_bundle(
        [
            {
                "cards": ["EX1_001"],
                "acquisition_provenance": acquire_live_test_provenance(
                    b"Canonical claim source."
                ),
            }
        ]
    )
    receipt = dict(bundle["canonical_source_receipts"][0])
    receipt["acquisition_provenance"] = acquire_live_test_provenance(
        b"Different acquired source."
    )

    annotated = _with_strategic_receipt_verification(
        bundle["claims"],
        deck_identity=deck_identity,
        verified_source_receipts=[receipt],
    )

    assert annotated[0]["strategic_receipt_verified"] is False
