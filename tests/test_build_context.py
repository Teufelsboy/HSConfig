from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from importlib import resources as importlib_resources
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from typing import Any

import pytest

from hsconfig import audited_deck_catalog, package_builder
from hsconfig.audited_deck_catalog import load_audited_deck_build_identity
from hsconfig.build_inputs import CanonicalBuildInputs, canonicalize_build_inputs
from hsconfig.build_context import resolve_build_context
from hsconfig.build_input_catalog import (
    load_audited_build_inputs,
    load_audited_build_resource_store,
)
from hsconfig.globalvalues_baseline import FALLBACK_GLOBALVALUES_BASELINE
from hsconfig.package_domain import (
    ClaimDisposition,
    ClaimDispositionRow,
    DispositionLedger,
    disposition_ledger_content_sha256,
)
from hsconfig.pre_run_metrics import (
    _load_pre_run_authority_handoff,
    build_pre_run_authority_handoff,
    evidence_authority_from_projection,
)
from hsconfig.source_acquisition_closure import (
    AcquisitionClosure,
    AcquisitionFailure,
    acquisition_closure_content_sha256,
    acquisition_closure_payload,
    policy_provenance_payload,
)


RESOURCE_ROOT = Path("src/hsconfig/resources")


class _MemoryStore:
    def __init__(self, values: dict[str, bytes]):
        self.values = dict(values)

    def read_by_sha256(self, content_sha256: str) -> bytes:
        return self.values[content_sha256]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _raw_digest(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _self_hash(document: dict[str, Any]) -> None:
    payload = dict(document)
    payload.pop("content_sha256", None)
    document["content_sha256"] = _raw_digest(_canonical(payload))


def _loaded() -> tuple[Any, Any]:
    audited = load_audited_build_inputs(
        RESOURCE_ROOT / "audited_build_inputs.json"
    )
    store = load_audited_build_resource_store(
        RESOURCE_ROOT / "audited_build_resources.json",
        audited_inputs=audited,
    )
    return audited, store


def _memory_store(inputs: CanonicalBuildInputs, store: Any) -> _MemoryStore:
    digests = {
        inputs.deck_cards_resource_sha256,
        inputs.card_snapshot_resource_sha256,
        inputs.policy_profile_resource_sha256,
        inputs.evidence_contract_resource_sha256,
        inputs.globalvalues_baseline_resource_sha256,
        *inputs.source_bundle_resource_sha256s,
    }
    return _MemoryStore(
        {
            digest: store.read_by_sha256(digest)
            for digest in digests
        }
    )


def _replace_resource(
    inputs: CanonicalBuildInputs,
    store: Any,
    *,
    field: str,
    document: object,
    domain_sha256: str | None = None,
) -> tuple[CanonicalBuildInputs, _MemoryStore]:
    raw = _canonical(document)
    digest = _raw_digest(raw)
    payload = json.loads(inputs.canonical_payload)
    if field == "source_bundle_resource_sha256s":
        payload[field] = [digest]
        if domain_sha256 is not None:
            payload["source_bundle_sha256s"] = [domain_sha256]
    else:
        payload[field] = digest
    changed = canonicalize_build_inputs(payload)
    memory = _memory_store(inputs, store)
    memory.values[digest] = raw
    return changed, memory


def _task7_disposition_ledger(
    deck: dict[str, Any],
    evidence: dict[str, Any],
) -> DispositionLedger:
    authorities_by_claim_id = {
        row["claim_id"]: row for row in evidence["authorities"]
    }
    claims = tuple(
        ClaimDispositionRow(
            deck_fingerprint=deck["deck_fingerprint"],
            claim_id=claim["claim_id"],
            claim_kind=authorities_by_claim_id[claim["claim_id"]][
                "claim_kind"
            ],
            evidence_id=f"inventory:{claim['claim_id']}",
            disposition=ClaimDisposition.CONTRACT_ONLY,
            runtime_paths=(),
            reason_code="claim_kind_has_no_runtime_surface",
        )
        for claim in deck["claims"]
    )
    return DispositionLedger(
        deck_fingerprint=deck["deck_fingerprint"],
        cards=(),
        claims=claims,
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=deck["deck_fingerprint"],
            cards=(),
            claims=claims,
        ),
    )


def _task7_authorities(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        row["claim_id"]: evidence_authority_from_projection(row)
        for row in evidence["authorities"]
    }


def test_all_evidence_resources_have_exact_task7_field_set() -> None:
    audited, store = _loaded()

    for inputs in audited.builds:
        evidence = json.loads(
            store.read_by_sha256(inputs.evidence_contract_resource_sha256)
        )

        assert set(evidence) == {
            "schema_version",
            "deck_fingerprint",
            "authorities",
            "content_sha256",
        }, inputs.deck_name


def test_all_evidence_resources_are_byte_identical_task7_producer_output() -> (
    None
):
    audited, store = _loaded()

    for inputs in audited.builds:
        deck = json.loads(
            store.read_by_sha256(inputs.deck_cards_resource_sha256)
        )
        evidence_raw = store.read_by_sha256(
            inputs.evidence_contract_resource_sha256
        )
        evidence = json.loads(evidence_raw)
        disposition_ledger = _task7_disposition_ledger(deck, evidence)
        produced = build_pre_run_authority_handoff(
            disposition_ledger=disposition_ledger,
            classified_authorities=_task7_authorities(evidence),
        )

        assert evidence_raw == _canonical(produced), inputs.deck_name


def test_task7_loader_accepts_all_evidence_resources() -> None:
    audited, store = _loaded()

    for inputs in audited.builds:
        deck = json.loads(
            store.read_by_sha256(inputs.deck_cards_resource_sha256)
        )
        evidence = json.loads(
            store.read_by_sha256(inputs.evidence_contract_resource_sha256)
        )
        disposition_ledger = _task7_disposition_ledger(deck, evidence)

        loaded = _load_pre_run_authority_handoff(
            evidence,
            disposition_ledger=disposition_ledger,
        )

        assert tuple(loaded) == tuple(
            row["claim_id"] for row in deck["claims"]
        ), inputs.deck_name


def test_resolver_returns_every_exact_hash_verified_context() -> None:
    audited, store = _loaded()
    inventory = json.loads(
        Path(
            "tests/fixtures/near100/current_semantic_inventory.json"
        ).read_text(encoding="utf-8")
    )
    inventory_by_name = {
        row["deck_name"]: row
        for row in inventory["decks"]
    }

    for inputs in audited.builds:
        context = resolve_build_context(inputs, resources=store)

        assert context.inputs is inputs
        assert (
            _raw_digest(context.deck_cards_canonical_json)
            == inputs.deck_cards_resource_sha256
        )
        assert (
            _raw_digest(context.card_snapshot_canonical_json)
            == inputs.card_snapshot_resource_sha256
        )
        assert (
            _raw_digest(context.policy_profile_canonical_json)
            == inputs.policy_profile_resource_sha256
        )
        assert (
            _raw_digest(context.evidence_contract_canonical_json)
            == inputs.evidence_contract_resource_sha256
        )
        assert tuple(
            _raw_digest(value)
            for value in context.source_bundle_canonical_json
        ) == inputs.source_bundle_resource_sha256s
        assert (
            _raw_digest(context.globalvalues_baseline_canonical_json)
            == inputs.globalvalues_baseline_resource_sha256
        )
        deck = json.loads(context.deck_cards_canonical_json)
        snapshot = json.loads(context.card_snapshot_canonical_json)
        policy = json.loads(context.policy_profile_canonical_json)
        evidence = json.loads(context.evidence_contract_canonical_json)
        bundles = [
            json.loads(value)
            for value in context.source_bundle_canonical_json
        ]
        baseline = json.loads(context.globalvalues_baseline_canonical_json)
        identity = load_audited_deck_build_identity(inputs.deck_name)
        inventory_row = inventory_by_name[inputs.deck_name]
        assert identity.deck_code_sha256 == inputs.deck_code_sha256
        assert identity.deck_fingerprint == inputs.deck_fingerprint
        assert deck["deck_name"] == inputs.deck_name
        assert deck["deck_fingerprint"] == inputs.deck_fingerprint
        assert deck["deck_code_sha256"] == inputs.deck_code_sha256
        assert deck["main_cards"] == inventory_row["main_cards"]
        assert deck["sideboard_modules"] == inventory_row["sideboard_modules"]
        assert deck["claims"] == inventory_row["claims"]
        assert sum(row["count"] for row in deck["main_cards"]) == 30
        assert snapshot["metadata"]["source_identifier"] == inputs.card_snapshot_id
        assert (
            snapshot["metadata"]["snapshot_sha256"]
            == inputs.card_snapshot_sha256
        )
        snapshot_domain = {
            "cards": snapshot["cards"],
            "metadata": {
                key: value
                for key, value in snapshot["metadata"].items()
                if key != "snapshot_sha256"
            },
            "schema_version": snapshot["schema_version"],
        }
        assert (
            "sha256:"
            + sha256(
                json.dumps(
                    snapshot_domain,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            == inputs.card_snapshot_sha256
        )
        assert policy["policy_id"] == inputs.policy_profile_id
        assert _raw_digest(_canonical(policy["rules"])) == (
            inputs.policy_profile_sha256
        )
        evidence_payload = dict(evidence)
        evidence_hash = evidence_payload.pop("content_sha256")
        assert _raw_digest(_canonical(evidence_payload)) == evidence_hash
        assert evidence["deck_fingerprint"] == inputs.deck_fingerprint
        assert inputs.evidence_policy_ids == (
            "BOT_NATIVE_PRE_RUN",
            "pre_run_authority_handoff",
        )
        assert [row["claim_id"] for row in evidence["authorities"]] == [
            row["claim_id"] for row in deck["claims"]
        ]
        assert all(row["lane"] == "D" for row in evidence["authorities"])
        assert len(baseline) == 38
        assert baseline == FALLBACK_GLOBALVALUES_BASELINE
        assert set(baseline) == set(deck["globalvalues_decisions"])
        assert len(bundles) == 2
        bundle = next(
            document
            for document in bundles
            if "content_sha256" in document
        )
        input_binding = next(
            document
            for document in bundles
            if set(document)
            == {"policy_provenance", "acquisition_closure"}
        )
        assert set(bundle) == {
            "schema_version",
            "authority",
            "apply_blocking",
            "deck",
            "policy",
            "acquisition_closure",
            "sources",
            "claims",
            "content_sha256",
        }
        bundle_payload = dict(bundle)
        bundle_hash = bundle_payload.pop("content_sha256")
        assert _raw_digest(_canonical(bundle_payload)) == bundle_hash
        assert {
            bundle_hash,
            _raw_digest(_canonical(input_binding)),
        } == set(inputs.source_bundle_sha256s)
        assert bundle["deck"]["name"] == inputs.deck_name
        assert bundle["deck"]["fingerprint"] == inputs.deck_fingerprint
        assert set(bundle["acquisition_closure"]) == {
            "deck_fingerprint",
            "attempt_id",
            "attempted_at",
            "attempted_urls",
            "successful_evidence_ids",
            "failed_attempts",
            "negative_search_documented",
            "checked_dossier",
            "policy_id",
            "status",
            "content_sha256",
        }
        assert set(input_binding) == {
            "policy_provenance",
            "acquisition_closure",
        }
        assert input_binding == {
            "policy_provenance": policy_provenance_payload(policy),
            "acquisition_closure": bundle["acquisition_closure"],
        }
        closure_document = bundle["acquisition_closure"]
        closure = AcquisitionClosure(
            deck_fingerprint=closure_document["deck_fingerprint"],
            attempt_id=closure_document["attempt_id"],
            attempted_at=closure_document["attempted_at"],
            attempted_urls=tuple(closure_document["attempted_urls"]),
            successful_evidence_ids=tuple(
                closure_document["successful_evidence_ids"]
            ),
            failed_attempts=tuple(
                AcquisitionFailure(**row)
                for row in closure_document["failed_attempts"]
            ),
            negative_search_documented=closure_document[
                "negative_search_documented"
            ],
            checked_dossier=closure_document["checked_dossier"],
            policy_id=closure_document["policy_id"],
            status=closure_document["status"],
            content_sha256=closure_document["content_sha256"],
        )
        assert acquisition_closure_payload(closure) == closure_document
        assert acquisition_closure_content_sha256(
            closure,
            policy_profile=policy,
        ) == closure.content_sha256
        if inputs.deck_name == "CuteWarrior":
            assert closure.status == "open"
            assert bundle["sources"] == []
            assert bundle["claims"] == []
        else:
            assert closure.status == "closed_with_evidence"
            assert bundle["sources"]
            assert bundle["claims"]


def test_resolver_rejects_deck_multiplicity_and_fingerprint_replay() -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]
    deck = json.loads(store.read_by_sha256(inputs.deck_cards_resource_sha256))
    multiplicity = deepcopy(deck)
    multiplicity["main_cards"][0]["count"] -= 1
    changed, memory = _replace_resource(
        inputs,
        store,
        field="deck_cards_resource_sha256",
        document=multiplicity,
    )
    with pytest.raises(ValueError, match="deck_cards_multiplicity_invalid"):
        resolve_build_context(changed, resources=memory)

    replay = deepcopy(deck)
    replay["deck_fingerprint"] = audited.builds[1].deck_fingerprint
    changed, memory = _replace_resource(
        inputs,
        store,
        field="deck_cards_resource_sha256",
        document=replay,
    )
    with pytest.raises(ValueError, match="deck_cards_identity_mismatch"):
        resolve_build_context(changed, resources=memory)


def test_resolver_rejects_freshly_self_hashed_unapproved_inputs() -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]
    payload = json.loads(inputs.canonical_payload)
    payload["deck_code_sha256"] = "0" * 64
    forged = canonicalize_build_inputs(payload)

    with pytest.raises(ValueError, match="deck_cards_deck_code_mismatch"):
        resolve_build_context(forged, resources=store)


def test_resolver_rejects_unapproved_evidence_policy_tuple_before_resolution() -> (
    None
):
    audited, _store = _loaded()
    payload = json.loads(audited.builds[0].canonical_payload)
    payload["evidence_policy_ids"] = ["BOT_NATIVE_PRE_RUN", "forged.policy"]
    forged = canonicalize_build_inputs(payload)

    with pytest.raises(
        ValueError,
        match="resolved_build_evidence_policy_ids_not_approved",
    ):
        resolve_build_context(forged, resources=_MemoryStore({}))


def test_resolver_rejects_coordinated_self_hashed_input_substitution() -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]
    forged_deck_code = "0" * 64

    deck = json.loads(store.read_by_sha256(inputs.deck_cards_resource_sha256))
    deck["deck_code_sha256"] = forged_deck_code
    deck_raw = _canonical(deck)
    deck_digest = _raw_digest(deck_raw)
    payload = json.loads(inputs.canonical_payload)
    payload["deck_code_sha256"] = forged_deck_code
    payload["deck_cards_resource_sha256"] = deck_digest
    forged = canonicalize_build_inputs(payload)
    memory = _memory_store(inputs, store)
    memory.values[deck_digest] = deck_raw

    with pytest.raises(ValueError, match="resolved_build_inputs_not_approved"):
        resolve_build_context(forged, resources=memory)


def test_resolver_recomputes_deck_fingerprint_from_main_roster() -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]
    deck = json.loads(store.read_by_sha256(inputs.deck_cards_resource_sha256))
    deck["main_cards"][0]["card_id"] = "FAKE_CARD_001"
    deck["main_cards"][0]["composite_card_key"] = (
        f"{inputs.deck_fingerprint}:main_deck:FAKE_CARD_001"
    )
    changed, memory = _replace_resource(
        inputs,
        store,
        field="deck_cards_resource_sha256",
        document=deck,
    )

    with pytest.raises(ValueError, match="deck_cards_fingerprint_mismatch"):
        resolve_build_context(changed, resources=memory)


def test_resolver_rejects_sideboard_card_missing_from_pinned_snapshot() -> None:
    audited, store = _loaded()
    inputs = next(
        row for row in audited.builds if row.deck_name == "MechPala"
    )
    deck = json.loads(store.read_by_sha256(inputs.deck_cards_resource_sha256))
    deck["sideboard_modules"][0]["card_id"] = "FAKE_CARD_001"
    owner = deck["sideboard_modules"][0]["owner_card_id"]
    deck["sideboard_modules"][0]["composite_card_key"] = (
        f"{inputs.deck_fingerprint}:sideboard_module:{owner}:FAKE_CARD_001"
    )
    changed, memory = _replace_resource(
        inputs,
        store,
        field="deck_cards_resource_sha256",
        document=deck,
    )

    with pytest.raises(ValueError, match="deck_cards_snapshot_card_missing"):
        resolve_build_context(changed, resources=memory)


def test_resolver_rejects_content_incomplete_schema_v1() -> None:
    audited, store = _loaded()
    schema_v1 = replace(audited.builds[0], schema_version=1)

    with pytest.raises(ValueError, match="resolved_build_inputs_schema_invalid"):
        resolve_build_context(schema_v1, resources=store)


def test_resolver_rejects_dataclass_fields_drifted_from_input_hash() -> None:
    audited, store = _loaded()
    drifted = replace(
        audited.builds[0],
        deck_cards_resource_sha256=(
            audited.builds[1].deck_cards_resource_sha256
        ),
    )

    with pytest.raises(ValueError, match="resolved_build_inputs_hash_stale"):
        resolve_build_context(drifted, resources=store)


def test_resolver_rejects_card_snapshot_and_policy_drift() -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]
    snapshot = json.loads(
        store.read_by_sha256(inputs.card_snapshot_resource_sha256)
    )
    snapshot["cards"][0][2] = "Drifted Name"
    changed, memory = _replace_resource(
        inputs,
        store,
        field="card_snapshot_resource_sha256",
        document=snapshot,
    )
    with pytest.raises(ValueError, match="card_snapshot_sha256_mismatch"):
        resolve_build_context(changed, resources=memory)

    policy = json.loads(
        store.read_by_sha256(inputs.policy_profile_resource_sha256)
    )
    policy["policy_id"] = "SUBSTITUTED_POLICY"
    changed, memory = _replace_resource(
        inputs,
        store,
        field="policy_profile_resource_sha256",
        document=policy,
    )
    with pytest.raises(ValueError, match="policy_profile_identity_invalid"):
        resolve_build_context(changed, resources=memory)


def test_resolver_rejects_raw_guide_instead_of_typed_authority() -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]
    evidence = json.loads(
        store.read_by_sha256(inputs.evidence_contract_resource_sha256)
    )
    evidence["authorities"][0] = {
        "claim_id": evidence["authorities"][0]["claim_id"],
        "guide": {"url": "https://example.test/raw-guide"},
    }
    _self_hash(evidence)
    changed, memory = _replace_resource(
        inputs,
        store,
        field="evidence_contract_resource_sha256",
        document=evidence,
    )
    with pytest.raises(ValueError, match="evidence_contract_raw_guide_forbidden"):
        resolve_build_context(changed, resources=memory)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "duplicate", "extra", "cross_deck"],
)
def test_resolver_rejects_invalid_authority_sets(mutation: str) -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]
    evidence = json.loads(
        store.read_by_sha256(inputs.evidence_contract_resource_sha256)
    )
    if mutation == "missing":
        evidence["authorities"].pop()
    elif mutation == "duplicate":
        evidence["authorities"].append(deepcopy(evidence["authorities"][0]))
    elif mutation == "extra":
        extra = deepcopy(evidence["authorities"][0])
        extra["claim_id"] = "claim_000000000000"
        extra["composite_claim_identity"] = (
            f"{inputs.deck_fingerprint}:claim_000000000000"
        )
        extra["authority_id"] = (
            "D:BOT_NATIVE_PRE_RUN:1:explicit_policy_claim:"
            "claim_000000000000"
        )
        extra["source_identity"] = "audited-inventory:claim_000000000000"
        evidence["authorities"].append(extra)
    else:
        evidence["authorities"][0]["deck_fingerprint"] = (
            audited.builds[1].deck_fingerprint
        )
    _self_hash(evidence)
    changed, memory = _replace_resource(
        inputs,
        store,
        field="evidence_contract_resource_sha256",
        document=evidence,
    )

    with pytest.raises(ValueError, match="evidence_contract_"):
        resolve_build_context(changed, resources=memory)


def _changed_source_context(
    mutation: str,
) -> tuple[CanonicalBuildInputs, _MemoryStore]:
    audited, store = _loaded()
    inputs = audited.builds[0]
    documents = [
        json.loads(store.read_by_sha256(digest))
        for digest in inputs.source_bundle_resource_sha256s
    ]
    bundle = next(
        document for document in documents if "content_sha256" in document
    )
    binding = next(
        document
        for document in documents
        if set(document) == {"policy_provenance", "acquisition_closure"}
    )
    old_bundle_resource = _raw_digest(_canonical(bundle))
    old_bundle_domain = bundle["content_sha256"]
    old_binding_resource = _raw_digest(_canonical(binding))
    if mutation == "replay":
        bundle["deck"]["name"] = audited.builds[1].deck_name
    elif mutation == "acquisition_removal":
        bundle.pop("acquisition_closure")
    elif mutation == "policy":
        bundle["policy"]["policy_id"] = "SUBSTITUTED_POLICY"
    elif mutation == "negative_with_evidence":
        bundle["acquisition_closure"]["status"] = "closed_negative_search"
        bundle["acquisition_closure"]["negative_search_documented"] = True
    elif mutation == "claim_evidence":
        bundle["claims"][0]["evidence_id"] = "evidence:" + ("0" * 64)
    else:
        binding["acquisition_closure"]["attempted_urls"].append(
            "https://example.test/unbound"
        )
    if mutation != "input_binding":
        _self_hash(bundle)
    changed_document = binding if mutation == "input_binding" else bundle
    old_resource = (
        old_binding_resource
        if mutation == "input_binding"
        else old_bundle_resource
    )
    old_domain = (
        old_resource
        if mutation == "input_binding"
        else old_bundle_domain
    )
    raw = _canonical(changed_document)
    new_resource = _raw_digest(raw)
    new_domain = (
        new_resource
        if mutation == "input_binding"
        else changed_document["content_sha256"]
    )
    resources = [
        digest
        for digest in inputs.source_bundle_resource_sha256s
        if digest != old_resource
    ]
    resources.append(new_resource)
    domains = [
        digest
        for digest in inputs.source_bundle_sha256s
        if digest != old_domain
    ]
    domains.append(new_domain)
    payload = json.loads(inputs.canonical_payload)
    payload["source_bundle_resource_sha256s"] = resources
    payload["source_bundle_sha256s"] = domains
    changed = canonicalize_build_inputs(payload)
    memory = _memory_store(inputs, store)
    memory.values[new_resource] = raw
    return changed, memory


@pytest.mark.parametrize(
    "mutation",
    [
        "replay",
        "acquisition_removal",
        "policy",
        "negative_with_evidence",
        "claim_evidence",
        "input_binding",
    ],
)
def test_resolver_rejects_invalid_source_bundle_bindings(
    mutation: str,
) -> None:
    inputs, store = _changed_source_context(mutation)

    with pytest.raises(ValueError, match="source_bundle_"):
        resolve_build_context(inputs, resources=store)


@pytest.mark.parametrize("mutation", ["missing", "extra", "invalid", "substitute"])
def test_resolver_rejects_globalvalues_baseline_mutations(
    mutation: str,
) -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]
    baseline = json.loads(
        store.read_by_sha256(inputs.globalvalues_baseline_resource_sha256)
    )
    if mutation == "missing":
        baseline.pop(next(iter(baseline)))
    elif mutation == "extra":
        baseline["UnexpectedKey"] = {"values": [{"condition": "*", "value": "0"}]}
    elif mutation == "invalid":
        baseline["GlobalCharge"] = {"values": []}
    else:
        baseline["GlobalCharge"]["values"][0]["value"] = "999"
    changed, memory = _replace_resource(
        inputs,
        store,
        field="globalvalues_baseline_resource_sha256",
        document=baseline,
    )

    with pytest.raises(ValueError, match="globalvalues_baseline_"):
        resolve_build_context(changed, resources=memory)


def test_resolver_rejects_mutable_or_digest_mismatched_store_returns() -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]
    memory = _memory_store(inputs, store)
    memory.values[inputs.deck_cards_resource_sha256] = bytearray(  # type: ignore[assignment]
        memory.values[inputs.deck_cards_resource_sha256]
    )
    with pytest.raises(ValueError, match="deck_cards_resource_mutable"):
        resolve_build_context(inputs, resources=memory)

    memory = _memory_store(inputs, store)
    memory.values[inputs.deck_cards_resource_sha256] = b"{}"
    with pytest.raises(ValueError, match="deck_cards_resource_sha256_mismatch"):
        resolve_build_context(inputs, resources=memory)


def test_resolved_context_is_detached_from_later_store_mutation() -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]
    memory = _memory_store(inputs, store)
    context = resolve_build_context(inputs, resources=memory)
    expected = context.deck_cards_canonical_json

    memory.values[inputs.deck_cards_resource_sha256] = b"{}"

    assert context.deck_cards_canonical_json == expected
    assert type(context.deck_cards_canonical_json) is bytes


def test_resolver_touches_no_ambient_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audited, store = _loaded()
    inputs = audited.builds[0]

    def forbidden(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("ambient authority touched")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(time, "time", forbidden)
    monkeypatch.setattr(importlib_resources, "files", forbidden)
    monkeypatch.setattr(
        audited_deck_catalog,
        "load_audited_deck_catalog",
        forbidden,
    )
    monkeypatch.setattr(package_builder, "prepare_package_payload", forbidden)
    monkeypatch.setattr(package_builder, "build_package_payload", forbidden)

    context = resolve_build_context(inputs, resources=store)

    assert context.inputs is inputs
