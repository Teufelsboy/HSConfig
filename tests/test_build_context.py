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
        assert [row["claim_id"] for row in evidence["authorities"]] == [
            row["claim_id"] for row in deck["claims"]
        ]
        assert all(row["lane"] == "D" for row in evidence["authorities"])
        assert len(baseline) == 38
        assert baseline == FALLBACK_GLOBALVALUES_BASELINE
        assert set(baseline) == set(deck["globalvalues_decisions"])
        for bundle, domain_sha256 in zip(
            bundles,
            inputs.source_bundle_sha256s,
            strict=True,
        ):
            bundle_payload = dict(bundle)
            bundle_hash = bundle_payload.pop("content_sha256")
            assert _raw_digest(_canonical(bundle_payload)) == bundle_hash
            assert bundle_hash == domain_sha256
            assert bundle["deck"]["name"] == inputs.deck_name
            assert (
                bundle["deck"]["fingerprint"]
                == inputs.deck_fingerprint
            )
            if inputs.deck_name == "CuteWarrior":
                assert bundle["acquisition_closure"]["status"] == "open"
                assert bundle["sources"] == []
                assert bundle["claim_bindings"] == []
            else:
                assert (
                    bundle["acquisition_closure"]["status"]
                    == "closed_with_evidence"
                )
                assert bundle["sources"]
            closure_payload = dict(bundle["acquisition_closure"])
            closure_hash = closure_payload.pop("content_sha256")
            assert _raw_digest(_canonical(closure_payload)) == closure_hash
            binding_payload = dict(bundle["input_binding"])
            binding_hash = binding_payload.pop("content_sha256")
            assert _raw_digest(_canonical(binding_payload)) == binding_hash


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
    source = json.loads(
        store.read_by_sha256(inputs.source_bundle_resource_sha256s[0])
    )
    if mutation == "replay":
        source["deck"]["name"] = audited.builds[1].deck_name
    elif mutation == "acquisition_removal":
        source.pop("acquisition_closure")
    elif mutation == "policy":
        source["policy"]["policy_id"] = "SUBSTITUTED_POLICY"
    elif mutation == "negative_with_evidence":
        source["acquisition_closure"]["status"] = "closed_negative_search"
        source["acquisition_closure"]["negative_search_documented"] = True
        _self_hash(source["acquisition_closure"])
        source["input_binding"]["acquisition_closure_sha256"] = (
            source["acquisition_closure"]["content_sha256"]
        )
        _self_hash(source["input_binding"])
    elif mutation == "claim_evidence":
        source["claim_bindings"][0]["evidence_id"] = "evidence:" + ("0" * 64)
    else:
        source["input_binding"]["source_document_sha256s"][0] = (
            "sha256:" + ("0" * 64)
        )
        _self_hash(source["input_binding"])
    _self_hash(source)
    return _replace_resource(
        inputs,
        store,
        field="source_bundle_resource_sha256s",
        document=source,
        domain_sha256=source["content_sha256"],
    )


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
