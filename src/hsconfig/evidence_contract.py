"""Classify pre-run claims into the layered evidence authority contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from importlib import resources
import json
import re
from typing import Any

from hsconfig.package_domain import (
    EvidenceAuthority,
    EvidenceLane,
    PolicyProfile,
)
from hsconfig.source_acquisition_provenance import (
    LIVE_HTTP,
    LIVE_VERIFIED,
    acquisition_provenance_is_canonical,
)
from hsconfig.source_document_model import (
    has_verified_source_receipt,
    normalized_claim_kind,
)
from hsconfig.source_exact_evidence import canonical_exact_deck_evidence


_POLICY_RESOURCE = "policies/BOT_NATIVE_PRE_RUN-v1.json"
_POLICY_KEYS = frozenset(
    {"policy_id", "version", "effective_date", "content_sha256", "rules"}
)
_POLICY_RULE_KEYS = frozenset(
    {
        "rule_id",
        "authority_lane",
        "runtime_authorized",
        "action",
        "required_claim_fields",
    }
)
_CONTENT_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OFFICIAL_CARD_DATA_SOURCES = frozenset(
    {
        "official_card_data",
        "official_static_semantics",
        "blizzard_card_library",
        "hearthstonejson",
        "hearthstonejson_static_semantics",
        "static_semantics",
        "metadata",
        "card_text",
    }
)
_PUBLIC_GUIDE_SOURCES = frozenset(
    {
        "guide",
        "guide_fixture",
        "mulligan_guide",
        "matchup_guide",
        "public_guide",
        "community_guide",
        "archetype_guide",
        "mechanic_guide",
    }
)
_CONTEXT_GUIDE_SCOPES = frozenset(
    {"archetype_matched", "mechanic_matched"}
)


def load_policy_profile() -> PolicyProfile:
    raw = (
        resources.files("hsconfig")
        .joinpath(_POLICY_RESOURCE)
        .read_text(encoding="utf-8")
    )
    try:
        payload = json.loads(raw, object_pairs_hook=_unique_object)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("policy_profile_json_invalid") from error
    return _policy_profile_from_mapping(payload)


def _policy_profile_from_mapping(
    payload: Mapping[str, Any],
) -> PolicyProfile:
    if not isinstance(payload, Mapping) or set(payload) != _POLICY_KEYS:
        raise ValueError("policy_profile_fields_invalid")
    if payload.get("policy_id") != "BOT_NATIVE_PRE_RUN" or (
        not isinstance(payload.get("version"), int)
        or isinstance(payload.get("version"), bool)
        or payload.get("version") != 1
    ):
        raise ValueError("policy_profile_identity_invalid")
    rules = payload.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("policy_profile_rules_invalid")
    rule_ids: list[str] = []
    for rule in rules:
        if not isinstance(rule, Mapping) or set(rule) != _POLICY_RULE_KEYS:
            raise ValueError("policy_profile_rule_fields_invalid")
        rule_id = rule.get("rule_id")
        required = rule.get("required_claim_fields")
        if (
            not isinstance(rule_id, str)
            or not rule_id
            or not isinstance(required, list)
            or not required
            or any(not isinstance(field, str) or not field for field in required)
        ):
            raise ValueError("policy_profile_rule_invalid")
        rule_ids.append(rule_id)
    if len(set(rule_ids)) != len(rule_ids):
        raise ValueError("policy_profile_rule_duplicate")
    rules_canonical_json = json.dumps(
        rules,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return PolicyProfile(
        policy_id=payload["policy_id"],
        version=payload["version"],
        effective_date=payload["effective_date"],
        content_sha256=payload["content_sha256"],
        rules_canonical_json=rules_canonical_json,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("policy_profile_duplicate_field")
        result[key] = value
    return result


def classify_evidence_authority(
    *,
    claim: Mapping[str, Any],
    deck_identity: Mapping[str, Any],
    verified_source_receipts: Sequence[Mapping[str, Any]],
    policy_profile: Mapping[str, Any],
) -> EvidenceAuthority:
    try:
        profile = _policy_profile_from_mapping(policy_profile)
    except (TypeError, ValueError) as error:
        raise ValueError("evidence_lane_unclassified") from error

    if not isinstance(claim, Mapping) or not isinstance(
        deck_identity, Mapping
    ):
        raise ValueError("evidence_lane_unclassified")
    claim_id = _clean_text(claim.get("claim_id"))
    claim_kind = normalized_claim_kind(claim)
    source_identity = _source_identity(claim)
    as_of_date = _as_of_date(claim)
    if not all((claim_id, claim_kind, source_identity, as_of_date)):
        raise ValueError("evidence_lane_unclassified")

    source_markers = _source_markers(claim)
    if (
        _clean_text(claim.get("evidence_lane")).upper() == "E"
        or "bot_delegation" in source_markers
    ):
        raise ValueError("evidence_lane_unclassified")

    if _is_policy_intent(claim, source_markers):
        return _classify_policy_authority(
            claim=claim,
            claim_id=claim_id,
            claim_kind=claim_kind,
            source_identity=source_identity,
            as_of_date=as_of_date,
            profile=profile,
        )

    if source_markers.intersection(_OFFICIAL_CARD_DATA_SOURCES):
        content_sha256 = _content_sha256(claim)
        snapshot_sha256 = _clean_text(
            claim.get("card_snapshot_sha256")
            or claim.get("snapshot_sha256")
        )
        if not (
            _is_content_sha256(content_sha256)
            and _is_content_sha256(snapshot_sha256)
        ):
            raise ValueError("evidence_lane_unclassified")
        return EvidenceAuthority(
            lane=EvidenceLane.OFFICIAL_CARD_DATA,
            authority_id=f"A:{claim_id}",
            source_identity=source_identity,
            as_of_date=as_of_date,
            claim_kind=claim_kind,
            content_sha256=content_sha256,
            exact_deck_fingerprint=None,
            runtime_authorized=True,
            reason="official_card_data_authority",
        )

    if source_markers.intersection(_PUBLIC_GUIDE_SOURCES):
        if _has_exact_guide_intent(claim):
            return _classify_exact_live_guide(
                claim=claim,
                claim_id=claim_id,
                claim_kind=claim_kind,
                source_identity=source_identity,
                as_of_date=as_of_date,
                deck_identity=deck_identity,
                verified_source_receipts=verified_source_receipts,
            )
        if (
            _normalized_text(claim.get("source_visibility")) == "full_text"
            and (
                _normalized_text(claim.get("deck_match_scope"))
                in _CONTEXT_GUIDE_SCOPES
                or source_markers.intersection(
                    {"archetype_guide", "mechanic_guide"}
                )
            )
        ):
            content_sha256 = _content_sha256(claim)
            if not _is_content_sha256(content_sha256):
                raise ValueError("evidence_lane_unclassified")
            return EvidenceAuthority(
                lane=EvidenceLane.ARCHETYPE_OR_MECHANIC_GUIDE,
                authority_id=f"C:{claim_id}",
                source_identity=source_identity,
                as_of_date=as_of_date,
                claim_kind=claim_kind,
                content_sha256=content_sha256,
                exact_deck_fingerprint=None,
                runtime_authorized=False,
                reason="context_only_guide_authority",
            )

    raise ValueError("evidence_lane_unclassified")


def _classify_exact_live_guide(
    *,
    claim: Mapping[str, Any],
    claim_id: str,
    claim_kind: str,
    source_identity: str,
    as_of_date: str,
    deck_identity: Mapping[str, Any],
    verified_source_receipts: Sequence[Mapping[str, Any]],
) -> EvidenceAuthority:
    target_fingerprint = _clean_text(
        deck_identity.get("deck_fingerprint")
    )
    provenance = claim.get("acquisition_provenance")
    if (
        not target_fingerprint
        or _normalized_text(claim.get("source_visibility")) != "full_text"
        or not acquisition_provenance_is_canonical(
            provenance,
            mode=LIVE_HTTP,
        )
        or not isinstance(provenance, Mapping)
        or provenance.get("authority") != LIVE_VERIFIED
    ):
        raise ValueError("evidence_lane_unclassified")
    deck_match = claim.get("deck_match")
    exact_evidence = (
        deck_match.get("exact_deck_evidence")
        if isinstance(deck_match, Mapping)
        else None
    )
    canonical_exact = canonical_exact_deck_evidence(
        exact_evidence,
        target_fingerprint=target_fingerprint,
    )
    if not canonical_exact or not has_verified_source_receipt(
        claim,
        target_fingerprint=target_fingerprint,
        verified_source_receipts=verified_source_receipts,
    ):
        raise ValueError("evidence_lane_unclassified")
    content_sha256 = _content_sha256(claim)
    if not _is_content_sha256(content_sha256):
        raise ValueError("evidence_lane_unclassified")
    return EvidenceAuthority(
        lane=EvidenceLane.EXACT_LIVE_GUIDE,
        authority_id=f"B:{claim_id}",
        source_identity=source_identity,
        as_of_date=as_of_date,
        claim_kind=claim_kind,
        content_sha256=content_sha256,
        exact_deck_fingerprint=target_fingerprint,
        runtime_authorized=True,
        reason="exact_live_guide_authority",
    )


def _classify_policy_authority(
    *,
    claim: Mapping[str, Any],
    claim_id: str,
    claim_kind: str,
    source_identity: str,
    as_of_date: str,
    profile: PolicyProfile,
) -> EvidenceAuthority:
    if (
        claim.get("policy_id") != profile.policy_id
        or claim.get("policy_version") != profile.version
        or claim.get("policy_content_sha256") != profile.content_sha256
    ):
        raise ValueError("evidence_lane_unclassified")
    policy_rule_id = _clean_text(claim.get("policy_rule_id"))
    rules = json.loads(profile.rules_canonical_json)
    rule = next(
        (
            item
            for item in rules
            if isinstance(item, Mapping)
            and item.get("rule_id") == policy_rule_id
        ),
        None,
    )
    if (
        not isinstance(rule, Mapping)
        or rule.get("authority_lane") != "D"
        or not isinstance(rule.get("runtime_authorized"), bool)
    ):
        raise ValueError("evidence_lane_unclassified")
    required_fields = rule.get("required_claim_fields")
    if not isinstance(required_fields, list) or any(
        not _claim_field_present(claim, field) for field in required_fields
    ):
        raise ValueError("evidence_lane_unclassified")
    return EvidenceAuthority(
        lane=EvidenceLane.VERSIONED_INTERNAL_POLICY,
        authority_id=(
            f"D:{profile.policy_id}:{profile.version}:"
            f"{policy_rule_id}:{claim_id}"
        ),
        source_identity=source_identity,
        as_of_date=as_of_date,
        claim_kind=claim_kind,
        content_sha256=profile.content_sha256,
        exact_deck_fingerprint=None,
        runtime_authorized=rule["runtime_authorized"],
        reason="versioned_internal_policy_authority",
    )


def _source_markers(claim: Mapping[str, Any]) -> set[str]:
    return {
        marker
        for marker in (
            _normalized_text(claim.get("source_type")),
            _normalized_text(claim.get("source_family")),
            _normalized_text(claim.get("provenance")),
            _normalized_text(claim.get("source_lane")),
        )
        if marker
    }


def _source_identity(claim: Mapping[str, Any]) -> str:
    for key in ("source_identity", "source_url", "source_ref", "source_title"):
        value = _clean_text(claim.get(key))
        if value:
            return value
    return ""


def _as_of_date(claim: Mapping[str, Any]) -> str:
    for key in ("as_of_date", "retrieved_at", "published_at"):
        value = _clean_text(claim.get(key))
        if len(value) < 10:
            continue
        candidate = value[:10]
        try:
            parsed = date.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.isoformat() == candidate:
            return candidate
    return ""


def _content_sha256(claim: Mapping[str, Any]) -> str:
    direct = _clean_text(claim.get("content_sha256"))
    if direct:
        return direct
    provenance = claim.get("acquisition_provenance")
    if isinstance(provenance, Mapping):
        return _clean_text(provenance.get("content_sha256"))
    return ""


def _is_content_sha256(value: str) -> bool:
    return _CONTENT_SHA256_RE.fullmatch(value) is not None


def _is_policy_intent(
    claim: Mapping[str, Any],
    source_markers: set[str],
) -> bool:
    return (
        "versioned_internal_policy" in source_markers
        or any(
            key in claim
            for key in (
                "policy_id",
                "policy_version",
                "policy_content_sha256",
                "policy_rule_id",
            )
        )
    )


def _has_exact_guide_intent(claim: Mapping[str, Any]) -> bool:
    if _normalized_text(claim.get("deck_match_scope")) == (
        "exact_deck_matched"
    ):
        return True
    if _normalized_text(claim.get("source_lane")) == (
        "deck_matched_public_guide"
    ):
        return True
    deck_match = claim.get("deck_match")
    return isinstance(deck_match, Mapping) and (
        "exact_deck_evidence" in deck_match
    )


def _claim_field_present(claim: Mapping[str, Any], field: Any) -> bool:
    if not isinstance(field, str) or field not in claim:
        return False
    value = claim[field]
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _normalized_text(value: Any) -> str:
    return _clean_text(value).lower()
