from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Protocol

from hsconfig.build_inputs import CanonicalBuildInputs, canonicalize_build_inputs
from hsconfig.package_domain import PolicyProfile


_CONTENT_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RAW_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_EVIDENCE_ID_RE = re.compile(r"evidence:[0-9a-f]{64}\Z")
_CLAIM_ID_RE = re.compile(r"claim_[0-9a-f]{12}\Z")
_APPROVED_SEMANTIC_INVENTORY_SHA256 = (
    "sha256:c012df4514f5c86e6f17e1593a302b135f44c2dd03a51a1adb1b04fa3436c37a"
)
_APPROVED_CARD_SNAPSHOT_ID = "HearthstoneJSON:247416:CardDefs.xml"
_APPROVED_CARD_SNAPSHOT_SHA256 = (
    "sha256:8ce0192a62b9c94147c8ccab1770699f9c07cbe65f94614b18d9572630a8a8d0"
)
_APPROVED_POLICY_ID = "BOT_NATIVE_PRE_RUN"
_APPROVED_POLICY_SHA256 = (
    "sha256:11f503fbf0c487170efab34be74dcb4035afebcfa0f7897b605ea4deab5c1605"
)
_APPROVED_GLOBALVALUES_BASELINE_RESOURCE_SHA256 = (
    "sha256:67e6f87a792c86ffbd28b10b6289ba6d88ef17c7e8204eff3b7d968be77b5177"
)
_GLOBALVALUES_KEYS = frozenset(
    {
        "ConfigComment",
        "FirstTurnValueWeight",
        "GameCardId",
        "GlobalCharge",
        "GlobalDivineShield",
        "GlobalDurability",
        "GlobalFrozen",
        "GlobalHeroAttack",
        "GlobalHeroHealth",
        "GlobalLocationHealth",
        "GlobalLocationIntrinsicValue",
        "GlobalMinionAttack",
        "GlobalMinionHealth",
        "GlobalMinionIntrinsicValue",
        "GlobalOverload",
        "GlobalQuestProgressValue",
        "GlobalStealth",
        "GlobalTaunt",
        "GlobalWeaponAttack",
        "GlobalWindfury",
        "OppGlobalCharge",
        "OppGlobalDivineShield",
        "OppGlobalDurability",
        "OppGlobalFrozen",
        "OppGlobalHeroAttack",
        "OppGlobalHeroHealth",
        "OppGlobalLocationHealth",
        "OppGlobalLocationIntrinsicValue",
        "OppGlobalMinionAttack",
        "OppGlobalMinionHealth",
        "OppGlobalMinionIntrinsicValue",
        "OppGlobalOverload",
        "OppGlobalQuestProgressValue",
        "OppGlobalStealth",
        "OppGlobalTaunt",
        "OppGlobalWeaponAttack",
        "OppGlobalWindfury",
        "SecondTurnValueWeight",
    }
)
_DECK_RESOURCE_FIELDS = frozenset(
    {
        "schema_version",
        "inventory_content_sha256",
        "deck_name",
        "deck_fingerprint",
        "main_cards",
        "sideboard_modules",
        "claims",
        "globalvalues_decisions",
    }
)
_MAIN_CARD_FIELDS = frozenset({"card_id", "composite_card_key", "count"})
_SIDEBOARD_FIELDS = frozenset(
    {
        "card_id",
        "composite_card_key",
        "count",
        "owner_card_id",
        "owner_dbf_id",
        "sideboard_index",
    }
)
_INVENTORY_CLAIM_FIELDS = frozenset({"claim_id", "claim_key"})
_POLICY_FIELDS = frozenset(
    {"policy_id", "version", "effective_date", "content_sha256", "rules"}
)
_POLICY_RULE_FIELDS = frozenset(
    {
        "rule_id",
        "authority_lane",
        "runtime_authorized",
        "action",
        "required_claim_fields",
    }
)
_EVIDENCE_CONTRACT_FIELDS = frozenset(
    {"schema_version", "deck_fingerprint", "authorities", "content_sha256"}
)
_AUTHORITY_FIELDS = frozenset(
    {
        "deck_fingerprint",
        "composite_claim_identity",
        "claim_id",
        "lane",
        "authority_id",
        "source_identity",
        "as_of_date",
        "claim_kind",
        "content_sha256",
        "exact_deck_fingerprint",
        "runtime_authorized",
        "reason",
    }
)
_SOURCE_BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "authority",
        "apply_blocking",
        "deck",
        "policy",
        "acquisition_closure",
        "input_binding",
        "sources",
        "claim_bindings",
        "content_sha256",
    }
)
_SOURCE_DECK_FIELDS = frozenset({"name", "fingerprint"})
_SOURCE_POLICY_FIELDS = frozenset(
    {"policy_id", "version", "effective_date", "content_sha256"}
)
_ACQUISITION_FIELDS = frozenset(
    {
        "deck_fingerprint",
        "policy_id",
        "policy_sha256",
        "status",
        "successful_evidence_ids",
        "checked_dossier",
        "negative_search_documented",
        "content_sha256",
    }
)
_INPUT_BINDING_FIELDS = frozenset(
    {
        "deck_fingerprint",
        "policy_sha256",
        "acquisition_closure_sha256",
        "source_document_sha256s",
        "content_sha256",
    }
)
_SOURCE_FIELDS = frozenset(
    {
        "evidence_id",
        "source_identity",
        "as_of_date",
        "content_sha256",
        "document",
    }
)
_SOURCE_CLAIM_FIELDS = frozenset(
    {"claim_id", "evidence_id", "content_sha256", "claim"}
)


class BuildResourceStore(Protocol):
    def read_by_sha256(self, content_sha256: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ResolvedBuildContext:
    inputs: CanonicalBuildInputs
    deck_cards_canonical_json: bytes
    card_snapshot_canonical_json: bytes
    policy_profile_canonical_json: bytes
    evidence_contract_canonical_json: bytes
    source_bundle_canonical_json: tuple[bytes, ...]
    globalvalues_baseline_canonical_json: bytes


def resolve_build_context(
    inputs: CanonicalBuildInputs,
    *,
    resources: BuildResourceStore,
) -> ResolvedBuildContext:
    _validate_inputs(inputs)
    deck_bytes, deck = _resource(
        resources,
        inputs.deck_cards_resource_sha256,
        error="deck_cards",
    )
    snapshot_bytes, snapshot = _resource(
        resources,
        inputs.card_snapshot_resource_sha256,
        error="card_snapshot",
    )
    policy_bytes, policy = _resource(
        resources,
        inputs.policy_profile_resource_sha256,
        error="policy_profile",
    )
    evidence_bytes, evidence = _resource(
        resources,
        inputs.evidence_contract_resource_sha256,
        error="evidence_contract",
    )
    source_pairs = tuple(
        _resource(resources, digest, error="source_bundle")
        for digest in inputs.source_bundle_resource_sha256s
    )
    baseline_bytes, baseline = _resource(
        resources,
        inputs.globalvalues_baseline_resource_sha256,
        error="globalvalues_baseline",
    )

    claim_ids = _validate_deck_resource(deck, inputs=inputs)
    _validate_card_snapshot(snapshot, inputs=inputs)
    profile = _validate_policy(policy, inputs=inputs)
    _validate_evidence_contract(
        evidence,
        inputs=inputs,
        profile=profile,
        expected_claim_ids=claim_ids,
    )
    for (
        domain_sha256,
        (_source_bytes, source),
    ) in zip(inputs.source_bundle_sha256s, source_pairs, strict=True):
        _validate_source_bundle(
            source,
            inputs=inputs,
            profile=profile,
            expected_domain_sha256=domain_sha256,
        )
    _validate_globalvalues_baseline(
        baseline,
        resource_sha256=inputs.globalvalues_baseline_resource_sha256,
        expected_keys=deck["globalvalues_decisions"],
    )

    return ResolvedBuildContext(
        inputs=inputs,
        deck_cards_canonical_json=deck_bytes,
        card_snapshot_canonical_json=snapshot_bytes,
        policy_profile_canonical_json=policy_bytes,
        evidence_contract_canonical_json=evidence_bytes,
        source_bundle_canonical_json=tuple(
            value for value, _document in source_pairs
        ),
        globalvalues_baseline_canonical_json=baseline_bytes,
    )


def _validate_inputs(inputs: CanonicalBuildInputs) -> None:
    if not isinstance(inputs, CanonicalBuildInputs) or inputs.schema_version != 2:
        raise ValueError("resolved_build_inputs_schema_invalid")
    if sha256(inputs.canonical_payload).hexdigest() != inputs.input_sha256:
        raise ValueError("resolved_build_inputs_hash_stale")
    try:
        canonical = canonicalize_build_inputs(
            _canonical_document(
                inputs.canonical_payload,
                error="resolved_build_inputs",
            )
        )
    except (TypeError, ValueError) as error:
        raise ValueError("resolved_build_inputs_hash_stale") from error
    if canonical != inputs:
        raise ValueError("resolved_build_inputs_hash_stale")
    if len(inputs.source_bundle_sha256s) != len(
        inputs.source_bundle_resource_sha256s
    ):
        raise ValueError("resolved_build_source_bundle_roots_mismatch")


def _resource(
    resources: BuildResourceStore,
    content_sha256: str,
    *,
    error: str,
) -> tuple[bytes, Any]:
    value = resources.read_by_sha256(content_sha256)
    if type(value) is not bytes:
        raise ValueError(f"{error}_resource_mutable")
    if _raw_sha256(value) != content_sha256:
        raise ValueError(f"{error}_resource_sha256_mismatch")
    return value, _canonical_document(value, error=error)


def _validate_deck_resource(
    document: Any,
    *,
    inputs: CanonicalBuildInputs,
) -> tuple[str, ...]:
    if not isinstance(document, Mapping) or set(document) != _DECK_RESOURCE_FIELDS:
        raise ValueError("deck_cards_fields_invalid")
    if (
        document.get("schema_version") != 1
        or document.get("inventory_content_sha256")
        != _APPROVED_SEMANTIC_INVENTORY_SHA256
        or document.get("deck_name") != inputs.deck_name
        or document.get("deck_fingerprint") != inputs.deck_fingerprint
    ):
        raise ValueError("deck_cards_identity_mismatch")
    fingerprint = inputs.deck_fingerprint
    main_cards = document.get("main_cards")
    sideboards = document.get("sideboard_modules")
    claims = document.get("claims")
    decisions = document.get("globalvalues_decisions")
    if (
        not isinstance(main_cards, list)
        or not isinstance(sideboards, list)
        or not isinstance(claims, list)
        or not isinstance(decisions, list)
    ):
        raise ValueError("deck_cards_projection_invalid")

    main_ids: set[str] = set()
    total = 0
    for card in main_cards:
        if not isinstance(card, Mapping) or set(card) != _MAIN_CARD_FIELDS:
            raise ValueError("deck_cards_main_card_invalid")
        card_id = card.get("card_id")
        count = card.get("count")
        if (
            not isinstance(card_id, str)
            or not card_id
            or type(count) is not int
            or count not in {1, 2}
            or card.get("composite_card_key")
            != f"{fingerprint}:main_deck:{card_id}"
            or card_id in main_ids
        ):
            raise ValueError("deck_cards_main_card_invalid")
        main_ids.add(card_id)
        total += count
    if total != 30:
        raise ValueError("deck_cards_multiplicity_invalid")

    sideboard_keys: set[str] = set()
    for card in sideboards:
        if not isinstance(card, Mapping) or set(card) != _SIDEBOARD_FIELDS:
            raise ValueError("deck_cards_sideboard_invalid")
        card_id = card.get("card_id")
        owner = card.get("owner_card_id")
        count = card.get("count")
        key = card.get("composite_card_key")
        if (
            not isinstance(card_id, str)
            or not isinstance(owner, str)
            or owner not in main_ids
            or type(count) is not int
            or count < 1
            or type(card.get("owner_dbf_id")) is not int
            or type(card.get("sideboard_index")) is not int
            or key != f"{fingerprint}:sideboard_module:{owner}:{card_id}"
            or key in sideboard_keys
        ):
            raise ValueError("deck_cards_sideboard_invalid")
        sideboard_keys.add(key)

    claim_ids: list[str] = []
    for claim in claims:
        if not isinstance(claim, Mapping) or set(claim) != _INVENTORY_CLAIM_FIELDS:
            raise ValueError("deck_cards_claim_invalid")
        claim_id = claim.get("claim_id")
        if (
            not isinstance(claim_id, str)
            or _CLAIM_ID_RE.fullmatch(claim_id) is None
            or claim.get("claim_key") != f"{fingerprint}:{claim_id}"
        ):
            raise ValueError("deck_cards_claim_invalid")
        claim_ids.append(claim_id)
    if not claim_ids or len(set(claim_ids)) != len(claim_ids):
        raise ValueError("deck_cards_claim_invalid")
    if (
        len(decisions) != 38
        or len(set(decisions)) != 38
        or set(decisions) != _GLOBALVALUES_KEYS
    ):
        raise ValueError("deck_cards_globalvalues_decisions_invalid")
    return tuple(claim_ids)


def _validate_card_snapshot(
    document: Any,
    *,
    inputs: CanonicalBuildInputs,
) -> None:
    if (
        not isinstance(document, Mapping)
        or set(document) != {"schema_version", "metadata", "cards"}
        or type(document.get("schema_version")) is not int
        or not isinstance(document.get("cards"), list)
    ):
        raise ValueError("card_snapshot_invalid")
    metadata = document.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("card_snapshot_unpinned")
    snapshot_id = metadata.get("source_identifier")
    snapshot_sha256 = metadata.get("snapshot_sha256")
    if (
        snapshot_id != _APPROVED_CARD_SNAPSHOT_ID
        or snapshot_sha256 != _APPROVED_CARD_SNAPSHOT_SHA256
        or snapshot_id != inputs.card_snapshot_id
        or snapshot_sha256 != inputs.card_snapshot_sha256
    ):
        raise ValueError("card_snapshot_identity_mismatch")
    digest_payload = {
        "cards": document.get("cards"),
        "metadata": {
            str(key): value
            for key, value in metadata.items()
            if key != "snapshot_sha256"
        },
        "schema_version": document.get("schema_version"),
    }
    domain_bytes = json.dumps(
        digest_payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if _raw_sha256(domain_bytes) != snapshot_sha256:
        raise ValueError("card_snapshot_sha256_mismatch")


def _validate_policy(
    document: Any,
    *,
    inputs: CanonicalBuildInputs,
) -> PolicyProfile:
    if not isinstance(document, Mapping) or set(document) != _POLICY_FIELDS:
        raise ValueError("policy_profile_fields_invalid")
    rules = document.get("rules")
    if (
        document.get("policy_id") != _APPROVED_POLICY_ID
        or document.get("policy_id") != inputs.policy_profile_id
        or document.get("content_sha256") != _APPROVED_POLICY_SHA256
        or document.get("content_sha256") != inputs.policy_profile_sha256
        or document.get("version") != 1
        or not isinstance(rules, list)
        or not rules
    ):
        raise ValueError("policy_profile_identity_invalid")
    for rule in rules:
        if not isinstance(rule, Mapping) or set(rule) != _POLICY_RULE_FIELDS:
            raise ValueError("policy_profile_rule_invalid")
    try:
        return PolicyProfile(
            policy_id=document["policy_id"],
            version=document["version"],
            effective_date=document["effective_date"],
            content_sha256=document["content_sha256"],
            rules_canonical_json=_canonical_json(rules),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("policy_profile_invalid") from error


def _validate_evidence_contract(
    document: Any,
    *,
    inputs: CanonicalBuildInputs,
    profile: PolicyProfile,
    expected_claim_ids: tuple[str, ...],
) -> None:
    if (
        not isinstance(document, Mapping)
        or set(document) != _EVIDENCE_CONTRACT_FIELDS
        or document.get("schema_version") != 1
        or document.get("deck_fingerprint") != inputs.deck_fingerprint
    ):
        raise ValueError("evidence_contract_identity_invalid")
    _validate_self_hash(document, error="evidence_contract_hash_stale")
    authorities = document.get("authorities")
    if not isinstance(authorities, list):
        raise ValueError("evidence_contract_authorities_invalid")
    seen: list[str] = []
    for row in authorities:
        if not isinstance(row, Mapping) or set(row) != _AUTHORITY_FIELDS:
            raise ValueError("evidence_contract_raw_guide_forbidden")
        claim_id = row.get("claim_id")
        expected_authority_id = (
            f"D:{profile.policy_id}:{profile.version}:"
            f"explicit_policy_claim:{claim_id}"
        )
        if (
            not isinstance(claim_id, str)
            or row.get("deck_fingerprint") != inputs.deck_fingerprint
            or row.get("composite_claim_identity")
            != f"{inputs.deck_fingerprint}:{claim_id}"
            or row.get("lane") != "D"
            or row.get("authority_id") != expected_authority_id
            or row.get("source_identity") != f"audited-inventory:{claim_id}"
            or row.get("as_of_date") != profile.effective_date
            or row.get("claim_kind") != "audited_semantic_claim"
            or row.get("content_sha256") != profile.content_sha256
            or row.get("exact_deck_fingerprint") is not None
            or row.get("runtime_authorized") is not True
            or row.get("reason") != "versioned_internal_policy_authority"
        ):
            raise ValueError("evidence_contract_authority_invalid")
        seen.append(claim_id)
    if tuple(seen) != expected_claim_ids or len(set(seen)) != len(seen):
        raise ValueError("evidence_contract_authority_set_invalid")


def _validate_source_bundle(
    document: Any,
    *,
    inputs: CanonicalBuildInputs,
    profile: PolicyProfile,
    expected_domain_sha256: str,
) -> None:
    if not isinstance(document, Mapping) or set(document) != _SOURCE_BUNDLE_FIELDS:
        raise ValueError("source_bundle_fields_invalid")
    if (
        document.get("schema_version") != 1
        or document.get("authority") != "diagnostic_only"
        or document.get("apply_blocking") is not False
    ):
        raise ValueError("source_bundle_contract_invalid")
    _validate_self_hash(document, error="source_bundle_hash_stale")
    if document.get("content_sha256") != expected_domain_sha256:
        raise ValueError("source_bundle_domain_sha256_mismatch")

    deck = document.get("deck")
    policy = document.get("policy")
    closure = document.get("acquisition_closure")
    binding = document.get("input_binding")
    sources = document.get("sources")
    claims = document.get("claim_bindings")
    if (
        not isinstance(deck, Mapping)
        or set(deck) != _SOURCE_DECK_FIELDS
        or deck.get("name") != inputs.deck_name
        or deck.get("fingerprint") != inputs.deck_fingerprint
    ):
        raise ValueError("source_bundle_cross_deck")
    if (
        not isinstance(policy, Mapping)
        or set(policy) != _SOURCE_POLICY_FIELDS
        or policy
        != {
            "policy_id": profile.policy_id,
            "version": profile.version,
            "effective_date": profile.effective_date,
            "content_sha256": profile.content_sha256,
        }
    ):
        raise ValueError("source_bundle_policy_mismatch")
    if (
        not isinstance(closure, Mapping)
        or set(closure) != _ACQUISITION_FIELDS
        or not isinstance(binding, Mapping)
        or set(binding) != _INPUT_BINDING_FIELDS
        or not isinstance(sources, list)
        or not isinstance(claims, list)
    ):
        raise ValueError("source_bundle_acquisition_invalid")
    _validate_self_hash(closure, error="source_bundle_acquisition_hash_stale")
    _validate_self_hash(binding, error="source_bundle_input_binding_hash_stale")
    if (
        closure.get("deck_fingerprint") != inputs.deck_fingerprint
        or closure.get("policy_id") != profile.policy_id
        or closure.get("policy_sha256") != profile.content_sha256
        or closure.get("negative_search_documented") is not False
        or binding.get("deck_fingerprint") != inputs.deck_fingerprint
        or binding.get("policy_sha256") != profile.content_sha256
        or binding.get("acquisition_closure_sha256")
        != closure.get("content_sha256")
    ):
        raise ValueError("source_bundle_acquisition_binding_mismatch")

    source_evidence_ids: list[str] = []
    source_digests: list[str] = []
    for source in sources:
        if not isinstance(source, Mapping) or set(source) != _SOURCE_FIELDS:
            raise ValueError("source_bundle_source_invalid")
        evidence_id = source.get("evidence_id")
        source_identity = source.get("source_identity")
        document_value = source.get("document")
        content_sha256 = source.get("content_sha256")
        if (
            not isinstance(evidence_id, str)
            or _EVIDENCE_ID_RE.fullmatch(evidence_id) is None
            or not isinstance(source_identity, str)
            or not source_identity
            or not isinstance(document_value, Mapping)
            or document_value.get("source_url") != source_identity
            or _raw_sha256(_canonical_json(document_value)) != content_sha256
            or _source_evidence_id(source_identity, content_sha256)
            != evidence_id
        ):
            raise ValueError("source_bundle_source_invalid")
        source_evidence_ids.append(evidence_id)
        source_digests.append(content_sha256)
    if len(set(source_evidence_ids)) != len(source_evidence_ids):
        raise ValueError("source_bundle_source_duplicate")

    claim_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, Mapping) or set(claim) != _SOURCE_CLAIM_FIELDS:
            raise ValueError("source_bundle_claim_invalid")
        claim_value = claim.get("claim")
        evidence_id = claim.get("evidence_id")
        claim_id = claim.get("claim_id")
        if (
            not isinstance(claim_value, Mapping)
            or evidence_id not in source_evidence_ids
            or _raw_sha256(_canonical_json(claim_value))
            != claim.get("content_sha256")
            or _source_claim_id(evidence_id, claim_value) != claim_id
            or claim_id in claim_ids
        ):
            raise ValueError("source_bundle_claim_evidence_mismatch")
        claim_ids.add(claim_id)

    status = closure.get("status")
    successful = closure.get("successful_evidence_ids")
    if (
        not isinstance(successful, list)
        or successful != sorted(source_evidence_ids)
        or binding.get("source_document_sha256s") != sorted(source_digests)
    ):
        raise ValueError("source_bundle_evidence_binding_mismatch")
    if status == "closed_with_evidence":
        if (
            not sources
            or closure.get("checked_dossier") is not True
            or not successful
        ):
            raise ValueError("source_bundle_positive_closure_invalid")
    elif status == "open":
        if (
            sources
            or claims
            or successful
            or closure.get("checked_dossier") is not False
        ):
            raise ValueError("source_bundle_open_contains_evidence")
    else:
        raise ValueError("source_bundle_negative_search_forbidden")


def _validate_globalvalues_baseline(
    document: Any,
    *,
    resource_sha256: str,
    expected_keys: Any,
) -> None:
    if (
        resource_sha256 != _APPROVED_GLOBALVALUES_BASELINE_RESOURCE_SHA256
        or not isinstance(document, Mapping)
        or set(document) != _GLOBALVALUES_KEYS
        or not isinstance(expected_keys, list)
        or set(expected_keys) != _GLOBALVALUES_KEYS
    ):
        raise ValueError("globalvalues_baseline_substitution")
    if document.get("GameCardId") != "GlobalValues":
        raise ValueError("globalvalues_baseline_gamecardid_invalid")
    if not isinstance(document.get("ConfigComment"), str):
        raise ValueError("globalvalues_baseline_configcomment_invalid")
    for key in _GLOBALVALUES_KEYS - {"GameCardId", "ConfigComment"}:
        value = document.get(key)
        if (
            not isinstance(value, Mapping)
            or set(value) != {"values"}
            or not isinstance(value.get("values"), list)
            or len(value["values"]) != 1
            or not isinstance(value["values"][0], Mapping)
            or set(value["values"][0]) != {"condition", "value"}
            or value["values"][0].get("condition") != "*"
            or not isinstance(value["values"][0].get("value"), str)
        ):
            raise ValueError("globalvalues_baseline_value_invalid")


def _canonical_document(raw: bytes, *, error: str) -> Any:
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{error}_json_invalid") from exc
    if _canonical_json(document) != raw:
        raise ValueError(f"{error}_json_noncanonical")
    return document


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("resolved_build_json_invalid") from error


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("resolved_build_json_duplicate_key")
        result[key] = value
    return result


def _validate_self_hash(document: Mapping[str, Any], *, error: str) -> None:
    payload = dict(document)
    declared = payload.pop("content_sha256", None)
    if declared != _raw_sha256(_canonical_json(payload)):
        raise ValueError(error)


def _raw_sha256(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _source_evidence_id(source_identity: str, content_sha256: str) -> str:
    payload = f"{source_identity.strip()}\0{content_sha256}".encode("utf-8")
    return f"evidence:{sha256(payload).hexdigest()}"


def _source_claim_id(evidence_id: str, claim: Mapping[str, Any]) -> str:
    payload = {
        "evidence_id": evidence_id,
        "claim": claim,
    }
    digest = sha256(_canonical_json(payload)).hexdigest()
    return f"claim_{digest[:12]}"


__all__ = (
    "BuildResourceStore",
    "ResolvedBuildContext",
    "resolve_build_context",
)
