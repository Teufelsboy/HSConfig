from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from typing import Any

import pytest

from hsconfig.evidence_contract import (
    classify_evidence_authority,
    load_policy_profile,
)
from hsconfig.package_domain import EvidenceLane, PolicyProfile
from hsconfig.source_acquisition_provenance import (
    build_acquisition_provenance,
)
from hsconfig.source_contract_audit import build_source_contract_audit
from hsconfig.source_document_model import source_claim_signature
from hsconfig.source_evidence_policy import classify_source_evidence


_DECK_FINGERPRINT = "sha256:fixture-deck-fingerprint"
_SNAPSHOT_SHA256 = "sha256:" + ("a" * 64)


def _deck_identity() -> dict[str, str]:
    return {
        "deck_name": "Fixture Deck",
        "deck_fingerprint": _DECK_FINGERPRINT,
    }


def _exact_claim() -> dict[str, Any]:
    provenance = build_acquisition_provenance(
        mode="live_http",
        content="complete exact guide text",
    )
    return {
        "claim_id": "claim-exact-keep",
        "claim_kind": "mulligan_keep",
        "source_family": "public_guide",
        "source_type": "public_guide",
        "source_url": "https://example.test/exact-guide",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "deck_match_scope": "exact_deck_matched",
        "as_of_date": "2026-07-29",
        "acquisition_provenance": provenance,
        "deck_match": {
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": _DECK_FINGERPRINT,
                "candidate_deck_code_hashes": [
                    "sha256:fixture-source-deck-code"
                ],
            }
        },
    }


def _matching_receipts(
    claim: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    return (
        {
            "receipt_kind": "canonical_exact_deck_source_document",
            "source_ref": "exact-guide",
            "source_url": claim["source_url"],
            "matched_deck_fingerprint": _DECK_FINGERPRINT,
            "claim_id": claim["claim_id"],
            "claim_signature": source_claim_signature(claim),
            "acquisition_provenance": copy.deepcopy(
                claim["acquisition_provenance"]
            ),
        },
    )


def _policy_mapping(profile: PolicyProfile) -> dict[str, Any]:
    return {
        "policy_id": profile.policy_id,
        "version": profile.version,
        "effective_date": profile.effective_date,
        "content_sha256": profile.content_sha256,
        "rules": json.loads(profile.rules_canonical_json),
    }


def test_evidence_authority_classifier_is_importable() -> None:
    assert callable(classify_evidence_authority)


def test_exact_live_guide_requires_matching_fingerprint_and_receipt() -> None:
    claim = _exact_claim()

    authority = classify_evidence_authority(
        claim=claim,
        deck_identity=_deck_identity(),
        verified_source_receipts=_matching_receipts(claim),
        policy_profile=_policy_mapping(load_policy_profile()),
    )

    assert authority.lane is EvidenceLane.EXACT_LIVE_GUIDE
    assert authority.authority_id == "B:claim-exact-keep"
    assert authority.source_identity == claim["source_url"]
    assert authority.content_sha256 == claim["acquisition_provenance"][
        "content_sha256"
    ]
    assert authority.exact_deck_fingerprint == _DECK_FINGERPRINT
    assert authority.runtime_authorized is True
    assert authority.reason == "exact_live_guide_authority"


@pytest.mark.parametrize(
    "mutation",
    [
        "not_live_http",
        "not_live_verified",
        "not_full_text",
        "incomplete_exact_evidence",
        "mismatching_fingerprint",
        "missing_receipt",
    ],
)
def test_exact_guide_missing_required_authority_never_downgrades_to_lane_c(
    mutation: str,
) -> None:
    claim = _exact_claim()
    receipts = _matching_receipts(claim)
    if mutation == "not_live_http":
        claim["acquisition_provenance"]["mode"] = "captured_record"
        receipts = _matching_receipts(claim)
    elif mutation == "not_live_verified":
        claim["acquisition_provenance"]["authority"] = "captured_unverified"
        receipts = _matching_receipts(claim)
    elif mutation == "not_full_text":
        claim["source_visibility"] = "snippet_only"
        receipts = _matching_receipts(claim)
    elif mutation == "incomplete_exact_evidence":
        del claim["deck_match"]["exact_deck_evidence"][
            "decoded_candidate_count"
        ]
        receipts = _matching_receipts(claim)
    elif mutation == "mismatching_fingerprint":
        claim["deck_match"]["exact_deck_evidence"][
            "matched_deck_fingerprint"
        ] = "sha256:other-deck"
        receipts = _matching_receipts(claim)
    elif mutation == "missing_receipt":
        receipts = ()

    with pytest.raises(ValueError, match="^evidence_lane_unclassified$"):
        classify_evidence_authority(
            claim=claim,
            deck_identity=_deck_identity(),
            verified_source_receipts=receipts,
            policy_profile=_policy_mapping(load_policy_profile()),
        )


def test_missing_metadata_does_not_become_bot_delegation() -> None:
    with pytest.raises(ValueError, match="^evidence_lane_unclassified$"):
        classify_evidence_authority(
            claim={},
            deck_identity=_deck_identity(),
            verified_source_receipts=(),
            policy_profile=_policy_mapping(load_policy_profile()),
        )


def test_bot_delegation_lane_is_not_classified_from_source_metadata() -> None:
    with pytest.raises(ValueError, match="^evidence_lane_unclassified$"):
        classify_evidence_authority(
            claim={
                "claim_id": "claim-bot",
                "claim_kind": "mulligan_keep",
                "evidence_lane": "E",
                "source_type": "bot_delegation",
                "source_identity": "hearthranger_bot",
                "as_of_date": "2026-07-29",
            },
            deck_identity=_deck_identity(),
            verified_source_receipts=(),
            policy_profile=_policy_mapping(load_policy_profile()),
        )


def test_pinned_official_card_data_classifies_as_lane_a() -> None:
    authority = classify_evidence_authority(
        claim={
            "claim_id": "claim-official-card",
            "claim_kind": "hero_power_transform",
            "source_type": "official_card_data",
            "source_identity": "hearthstonejson:fixture",
            "as_of_date": "2026-07-29",
            "content_sha256": "sha256:" + ("b" * 64),
            "card_snapshot_sha256": _SNAPSHOT_SHA256,
        },
        deck_identity=_deck_identity(),
        verified_source_receipts=(),
        policy_profile=_policy_mapping(load_policy_profile()),
    )

    assert authority.lane is EvidenceLane.OFFICIAL_CARD_DATA
    assert authority.exact_deck_fingerprint is None
    assert authority.runtime_authorized is True
    assert authority.reason == "official_card_data_authority"


def test_official_card_data_without_pinned_snapshot_is_unclassified() -> None:
    with pytest.raises(ValueError, match="^evidence_lane_unclassified$"):
        classify_evidence_authority(
            claim={
                "claim_id": "claim-official-card",
                "claim_kind": "hero_power_transform",
                "source_type": "official_card_data",
                "source_identity": "hearthstonejson:fixture",
                "as_of_date": "2026-07-29",
                "content_sha256": "sha256:" + ("b" * 64),
            },
            deck_identity=_deck_identity(),
            verified_source_receipts=(),
            policy_profile=_policy_mapping(load_policy_profile()),
        )


def test_full_text_archetype_guide_classifies_as_context_only_lane_c() -> None:
    provenance = build_acquisition_provenance(
        mode="live_http",
        content="archetype guide text",
    )
    authority = classify_evidence_authority(
        claim={
            "claim_id": "claim-archetype-context",
            "claim_kind": "gameplan_posture",
            "source_family": "archetype_guide",
            "source_url": "https://example.test/archetype-guide",
            "source_visibility": "full_text",
            "deck_match_scope": "archetype_matched",
            "as_of_date": "2026-07-29",
            "acquisition_provenance": provenance,
        },
        deck_identity=_deck_identity(),
        verified_source_receipts=(),
        policy_profile=_policy_mapping(load_policy_profile()),
    )

    assert authority.lane is EvidenceLane.ARCHETYPE_OR_MECHANIC_GUIDE
    assert authority.exact_deck_fingerprint is None
    assert authority.runtime_authorized is False
    assert authority.reason == "context_only_guide_authority"


def test_versioned_internal_policy_requires_exact_packaged_binding() -> None:
    profile = load_policy_profile()
    authority = classify_evidence_authority(
        claim={
            "claim_id": "claim-policy",
            "claim_kind": "mechanic_usage",
            "source_type": "versioned_internal_policy",
            "source_identity": "BOT_NATIVE_PRE_RUN",
            "as_of_date": "2026-07-29",
            "policy_id": profile.policy_id,
            "policy_version": profile.version,
            "policy_content_sha256": profile.content_sha256,
            "policy_rule_id": "explicit_policy_claim",
            "cards": ["FIXTURE_CARD"],
            "action": "use_explicit_policy_claim",
            "reason_code": "explicit_reviewed_policy",
        },
        deck_identity=_deck_identity(),
        verified_source_receipts=(),
        policy_profile=_policy_mapping(profile),
    )

    assert authority.lane is EvidenceLane.VERSIONED_INTERNAL_POLICY
    assert authority.content_sha256 == profile.content_sha256
    assert authority.runtime_authorized is True
    assert authority.reason == "versioned_internal_policy_authority"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policy_id", "OTHER_POLICY"),
        ("policy_version", 2),
        ("policy_content_sha256", "sha256:" + ("0" * 64)),
        ("policy_rule_id", "unknown-rule"),
    ],
)
def test_internal_policy_mismatch_is_unclassified(
    field: str,
    value: Any,
) -> None:
    profile = load_policy_profile()
    claim = {
        "claim_id": "claim-policy",
        "claim_kind": "mechanic_usage",
        "source_type": "versioned_internal_policy",
        "source_identity": "BOT_NATIVE_PRE_RUN",
        "as_of_date": "2026-07-29",
        "policy_id": profile.policy_id,
        "policy_version": profile.version,
        "policy_content_sha256": profile.content_sha256,
        "policy_rule_id": "explicit_policy_claim",
        "cards": ["FIXTURE_CARD"],
        "action": "use_explicit_policy_claim",
        "reason_code": "explicit_reviewed_policy",
    }
    claim[field] = value

    with pytest.raises(ValueError, match="^evidence_lane_unclassified$"):
        classify_evidence_authority(
            claim=claim,
            deck_identity=_deck_identity(),
            verified_source_receipts=(),
            policy_profile=_policy_mapping(profile),
        )


def test_internal_policy_requires_explicit_card_action_and_reason() -> None:
    profile = load_policy_profile()
    with pytest.raises(ValueError, match="^evidence_lane_unclassified$"):
        classify_evidence_authority(
            claim={
                "claim_id": "claim-policy",
                "claim_kind": "mechanic_usage",
                "source_type": "versioned_internal_policy",
                "source_identity": "BOT_NATIVE_PRE_RUN",
                "as_of_date": "2026-07-29",
                "policy_id": profile.policy_id,
                "policy_version": profile.version,
                "policy_content_sha256": profile.content_sha256,
                "policy_rule_id": "explicit_policy_claim",
            },
            deck_identity=_deck_identity(),
            verified_source_receipts=(),
            policy_profile=_policy_mapping(profile),
        )


def test_malformed_policy_profile_is_an_unclassified_lane() -> None:
    claim = _exact_claim()
    profile = _policy_mapping(load_policy_profile())
    profile["unknown"] = True

    with pytest.raises(ValueError, match="^evidence_lane_unclassified$"):
        classify_evidence_authority(
            claim=claim,
            deck_identity=_deck_identity(),
            verified_source_receipts=_matching_receipts(claim),
            policy_profile=profile,
        )


def test_packaged_policy_is_canonical_explicit_and_immutable() -> None:
    profile = load_policy_profile()
    rules = json.loads(profile.rules_canonical_json)

    assert profile.policy_id == "BOT_NATIVE_PRE_RUN"
    assert profile.version == 1
    assert profile.effective_date == "2026-07-28"
    assert profile.content_sha256 == (
        "sha256:" + sha256(profile.rules_canonical_json).hexdigest()
    )
    assert rules
    assert all(
        isinstance(rule.get("rule_id"), str)
        and rule.get("required_claim_fields")
        for rule in rules
    )
    forbidden = ("curve", "lowest_cost", "role_rank", "generic_keep")
    policy_text = profile.rules_canonical_json.decode("utf-8").lower()
    assert not any(token in policy_text for token in forbidden)
    with pytest.raises(FrozenInstanceError):
        profile.policy_id = "MUTATED"  # type: ignore[misc]


def test_source_policy_exposes_candidates_without_self_certifying_authority() -> None:
    official = classify_source_evidence(
        {
            "source_type": "official_card_data",
            "source_visibility": "full_text",
            "claim_kind": "hero_power_transform",
            "publication_year": 2026,
        },
        deck_name="Fixture Deck",
        current_date="2026-07-29",
        deck_identity=_deck_identity(),
    )
    exact_candidate = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_visibility": "full_text",
            "normalized_text": "complete guide text",
            "publication_year": 2026,
            "deck_match_scope": "exact_deck_matched",
            "deck_match": {
                "exact_deck_evidence": {
                    "matched": True,
                    "matched_deck_fingerprint": _DECK_FINGERPRINT,
                }
            },
        },
        deck_name="Fixture Deck",
        current_date="2026-07-29",
        deck_identity=_deck_identity(),
    )

    assert official["evidence_lane_candidate"] == "A"
    assert exact_candidate["evidence_lane_candidate"] == "B"
    assert "evidence_authority" not in exact_candidate


def test_source_contract_audit_projects_typed_authority_or_explicit_gap() -> None:
    claim = _exact_claim()
    report = build_source_contract_audit(
        deck_name="Fixture Deck",
        deck_identity=_deck_identity(),
        guide_claim_bundle={
            "claims": [claim, {}],
            "canonical_source_receipts": list(_matching_receipts(claim)),
        },
        include_evidence_authority=True,
    )

    exact_row = report["claim_rows"]["claim-exact-keep"]
    missing_row = report["claim_rows"]["claim_0002"]
    assert exact_row["evidence_authority"]["lane"] == "B"
    assert exact_row["evidence_lane_error"] is None
    assert missing_row["evidence_authority"] is None
    assert missing_row["evidence_lane_error"] == "evidence_lane_unclassified"
