from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pytest

from hsconfig.audited_deck_catalog import load_audited_deck_build_identity
from hsconfig.build_inputs import CanonicalBuildInputs, canonicalize_build_inputs
from hsconfig.card_data_context import load_pinned_card_data_context


AUDITED_CARD_DB_PATH = Path("tests/fixtures/audited_deck_card_db.json")
GENERATOR_COMMIT = "6ff2328ce95e59043013d73c4df18be19dbc8548"
SHADOWPRIEST_DECK_CODE_SHA256 = (
    "fd7afada1f4a7f60bb269dc56188ddf83603e4bb0147a163d3e337be388917f2"
)
SHADOWPRIEST_DECK_FINGERPRINT = (
    "831b989cf8d076bff87848b4d0d6f382c9d306fddea7619017f0c361bfc92327"
)
AUDITED_CARD_SNAPSHOT_ID = "HearthstoneJSON:247416:CardDefs.xml"
AUDITED_CARD_SNAPSHOT_SHA256 = (
    "sha256:8ce0192a62b9c94147c8ccab1770699f9c07cbe65f94614b18d9572630a8a8d0"
)


def _digest(character: str) -> str:
    return "sha256:" + (character * 64)


def _valid_payload() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "generator_version": "0.1.0",
        "generator_commit": GENERATOR_COMMIT,
        "deck_name": "ShadowPriest",
        "deck_code_sha256": SHADOWPRIEST_DECK_CODE_SHA256,
        "deck_fingerprint": SHADOWPRIEST_DECK_FINGERPRINT,
        "card_snapshot_id": AUDITED_CARD_SNAPSHOT_ID,
        "card_snapshot_sha256": _digest("a"),
        "policy_profile_id": "policy.v1",
        "policy_profile_sha256": _digest("b"),
        "as_of_date": " 2026-07-28 ",
        "source_bundle_sha256s": [_digest("e"), _digest("d")],
        "evidence_policy_ids": ["evidence.z", "evidence.a"],
        "deck_cards_resource_sha256": _digest("0"),
        "card_snapshot_resource_sha256": _digest("1"),
        "policy_profile_resource_sha256": _digest("2"),
        "evidence_contract_resource_sha256": _digest("3"),
        "source_bundle_resource_sha256s": [_digest("5"), _digest("4")],
        "globalvalues_baseline_resource_sha256": _digest("6"),
    }


def test_canonicalize_build_inputs_normalizes_and_hashes_exact_json_bytes() -> None:
    inputs = canonicalize_build_inputs(_valid_payload())

    assert isinstance(inputs, CanonicalBuildInputs)
    assert inputs.schema_version == 2
    assert inputs.generator_version == "0.1.0"
    assert inputs.generator_commit == GENERATOR_COMMIT
    assert inputs.deck_name == "ShadowPriest"
    assert inputs.as_of_date == "2026-07-28"
    assert inputs.source_bundle_sha256s == (_digest("d"), _digest("e"))
    assert inputs.evidence_policy_ids == ("evidence.a", "evidence.z")
    expected_payload = {
        **_valid_payload(),
        "as_of_date": "2026-07-28",
        "source_bundle_sha256s": [_digest("d"), _digest("e")],
        "evidence_policy_ids": ["evidence.a", "evidence.z"],
        "source_bundle_resource_sha256s": [_digest("4"), _digest("5")],
    }
    assert inputs.canonical_payload == json.dumps(
        expected_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert inputs.input_sha256 == (
        "0ed7fdd07ba620507c69cea4ec531d78fe793107665974b31a66ea4db9ff7b0c"
    )
    assert inputs.input_sha256 == sha256(inputs.canonical_payload).hexdigest()
    assert not hasattr(inputs, "__dict__")
    with pytest.raises(FrozenInstanceError):
        inputs.deck_name = "Changed"  # type: ignore[misc]


def test_canonical_payload_uses_utf8_instead_of_ascii_escapes() -> None:
    payload = _valid_payload()
    payload["deck_name"] = "ShadowPrïest"

    inputs = canonicalize_build_inputs(payload)

    assert "ShadowPrïest".encode() in inputs.canonical_payload
    assert b"\\u00ef" not in inputs.canonical_payload


def test_audited_build_identity_matches_decoded_catalog() -> None:
    identity = load_audited_deck_build_identity("ShadowPriest")

    assert identity.deck_name == "ShadowPriest"
    assert identity.deck_code_sha256 == SHADOWPRIEST_DECK_CODE_SHA256
    assert identity.deck_fingerprint == SHADOWPRIEST_DECK_FINGERPRINT
    assert not hasattr(identity, "__dict__")

    payload = _valid_payload()
    payload["deck_name"] = identity.deck_name
    payload["deck_code_sha256"] = identity.deck_code_sha256
    payload["deck_fingerprint"] = identity.deck_fingerprint

    inputs = canonicalize_build_inputs(payload)

    assert inputs.deck_code_sha256 == identity.deck_code_sha256
    assert inputs.deck_fingerprint == identity.deck_fingerprint


def test_pinned_card_data_context_serializes_identity_and_digest_not_path() -> None:
    context = load_pinned_card_data_context(AUDITED_CARD_DB_PATH.resolve())
    payload = _valid_payload()
    payload["card_snapshot_id"] = context.card_snapshot_id
    payload["card_snapshot_sha256"] = context.card_snapshot_sha256

    inputs = canonicalize_build_inputs(payload)

    assert context.card_snapshot_id == AUDITED_CARD_SNAPSHOT_ID
    assert context.card_snapshot_sha256 == AUDITED_CARD_SNAPSHOT_SHA256
    assert inputs.card_snapshot_id == AUDITED_CARD_SNAPSHOT_ID
    assert inputs.card_snapshot_sha256 == AUDITED_CARD_SNAPSHOT_SHA256
    assert str(AUDITED_CARD_DB_PATH.resolve()).encode() not in inputs.canonical_payload
    assert "path" not in json.loads(inputs.canonical_payload)
    assert not hasattr(context, "__dict__")


def test_pinned_card_data_context_rejects_unpinned_or_drifted_content(
    tmp_path: Path,
) -> None:
    payload = json.loads(AUDITED_CARD_DB_PATH.read_text(encoding="utf-8"))
    payload["metadata"].pop("snapshot_sha256")
    unpinned = tmp_path / "unpinned.json"
    unpinned.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="card_snapshot_unpinned"):
        load_pinned_card_data_context(unpinned)

    payload["metadata"]["snapshot_sha256"] = AUDITED_CARD_SNAPSHOT_SHA256
    payload["cards"][0][2] = "Drifted Name"
    drifted = tmp_path / "drifted.json"
    drifted.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="card_snapshot_sha256_mismatch"):
        load_pinned_card_data_context(drifted)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("card_snapshot_id", "HearthstoneJSON:synthetic:CardDefs.xml"),
        ("card_snapshot_sha256", _digest("c")),
        ("policy_profile_id", "policy.synthetic.v2"),
        ("policy_profile_sha256", _digest("c")),
        ("source_bundle_sha256s", [_digest("c"), _digest("d")]),
        ("evidence_policy_ids", ["evidence.a", "evidence.synthetic"]),
        ("deck_cards_resource_sha256", _digest("c")),
        ("card_snapshot_resource_sha256", _digest("c")),
        ("policy_profile_resource_sha256", _digest("c")),
        ("evidence_contract_resource_sha256", _digest("c")),
        (
            "source_bundle_resource_sha256s",
            [_digest("c"), _digest("4")],
        ),
        ("globalvalues_baseline_resource_sha256", _digest("c")),
    ],
)
def test_every_synthetic_hash_reference_is_bound_by_input_sha256(
    field: str,
    replacement: Any,
) -> None:
    baseline = canonicalize_build_inputs(_valid_payload())
    changed_payload = _valid_payload()
    changed_payload[field] = replacement

    changed = canonicalize_build_inputs(changed_payload)

    assert changed.canonical_payload != baseline.canonical_payload
    assert changed.input_sha256 != baseline.input_sha256
    assert changed.input_sha256 == sha256(changed.canonical_payload).hexdigest()


@pytest.mark.parametrize("forbidden_key", ["deck_code", "raw_deck_code"])
def test_canonicalize_rejects_raw_deckcodes(forbidden_key: str) -> None:
    payload = _valid_payload()
    payload[forbidden_key] = (
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
        "KgG17oG1cEGAAA="
    )

    with pytest.raises(ValueError, match="build_inputs_raw_deck_code_forbidden"):
        canonicalize_build_inputs(payload)


def test_canonicalize_rejects_unknown_keys() -> None:
    payload = _valid_payload()
    payload["surprise"] = "not part of schema version 2"

    with pytest.raises(ValueError, match="build_inputs_unknown_keys"):
        canonicalize_build_inputs(payload)


@pytest.mark.parametrize(
    ("field", "absolute_path"),
    [
        ("generator_commit", r"\\server\share\repo"),
    ],
)
def test_canonicalize_rejects_absolute_paths(
    field: str,
    absolute_path: str,
) -> None:
    payload = _valid_payload()
    payload[field] = absolute_path

    with pytest.raises(ValueError, match="build_inputs_absolute_path_forbidden"):
        canonicalize_build_inputs(payload)


@pytest.mark.parametrize(
    "field",
    ["card_snapshot_id", "policy_profile_id", "evidence_policy_ids"],
)
@pytest.mark.parametrize(
    "path_shaped_identifier",
    [
        r"\private\cards.json",
        r"C:private\cards.json",
        r"..\private\policy.json",
        "../private/policy.json",
        "fixtures/cards.json",
        r"fixtures\cards.json",
        "file:///C:/private/cards.json",
        "cards.json",
        "local-policy.json",
    ],
)
def test_canonicalize_rejects_path_shaped_stable_identifiers(
    field: str,
    path_shaped_identifier: str,
) -> None:
    payload = _valid_payload()
    payload[field] = (
        [path_shaped_identifier]
        if field == "evidence_policy_ids"
        else path_shaped_identifier
    )

    with pytest.raises(ValueError, match="build_inputs_identifier_invalid"):
        canonicalize_build_inputs(payload)


@pytest.mark.parametrize(
    "invalid_identifier",
    [
        "policy id",
        "policy@v1",
        "policy.überprüft",
        ":policy",
        "policy::v1",
        ".",
        "..",
    ],
)
def test_canonicalize_rejects_identifiers_outside_stable_ascii_grammar(
    invalid_identifier: str,
) -> None:
    payload = _valid_payload()
    payload["policy_profile_id"] = invalid_identifier

    with pytest.raises(ValueError, match="build_inputs_identifier_invalid"):
        canonicalize_build_inputs(payload)


def test_canonicalize_accepts_namespaced_stable_ascii_identifiers() -> None:
    payload = _valid_payload()
    payload["card_snapshot_id"] = "HearthstoneJSON:247416:CardDefs.xml"
    payload["policy_profile_id"] = "policy-profile_v1.2"
    payload["evidence_policy_ids"] = ["evidence:policy-v1_2.3"]

    inputs = canonicalize_build_inputs(payload)

    assert inputs.card_snapshot_id == "HearthstoneJSON:247416:CardDefs.xml"
    assert inputs.policy_profile_id == "policy-profile_v1.2"
    assert inputs.evidence_policy_ids == ("evidence:policy-v1_2.3",)


@pytest.mark.parametrize(
    "missing_field",
    [
        "as_of_date",
        "card_snapshot_id",
        "card_snapshot_sha256",
        "deck_cards_resource_sha256",
        "card_snapshot_resource_sha256",
        "policy_profile_resource_sha256",
        "evidence_contract_resource_sha256",
        "source_bundle_resource_sha256s",
        "globalvalues_baseline_resource_sha256",
    ],
)
def test_canonicalize_requires_explicit_date_and_pinned_card_data(
    missing_field: str,
) -> None:
    payload = _valid_payload()
    payload.pop(missing_field)

    with pytest.raises(ValueError, match="build_inputs_missing_keys"):
        canonicalize_build_inputs(payload)


@pytest.mark.parametrize(
    ("field", "duplicate_values"),
    [
        ("source_bundle_sha256s", [_digest("d"), _digest("d")]),
        ("evidence_policy_ids", ["evidence.a", " evidence.a "]),
        (
            "source_bundle_resource_sha256s",
            [_digest("4"), _digest("4")],
        ),
    ],
)
def test_canonicalize_rejects_duplicate_reference_ids(
    field: str,
    duplicate_values: list[str],
) -> None:
    payload = _valid_payload()
    payload[field] = duplicate_values

    with pytest.raises(ValueError, match="build_inputs_duplicate_ids"):
        canonicalize_build_inputs(payload)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("schema_version", 1),
        ("schema_version", True),
        ("generator_version", None),
        ("generator_commit", 123),
        ("deck_name", ["ShadowPriest"]),
        ("deck_code_sha256", "sha256:" + ("a" * 64)),
        ("deck_fingerprint", "not-a-digest"),
        ("card_snapshot_sha256", "a" * 64),
        ("policy_profile_sha256", "sha256:not-a-digest"),
        ("as_of_date", "2026-02-30"),
        ("as_of_date", 20260728),
        ("source_bundle_sha256s", _digest("d")),
        ("source_bundle_sha256s", [_digest("d"), 7]),
        ("evidence_policy_ids", "evidence.a"),
        ("evidence_policy_ids", ["evidence.a", 7]),
        ("deck_cards_resource_sha256", "f" * 64),
        ("card_snapshot_resource_sha256", "sha256:NOT_LOWERCASE"),
        ("policy_profile_resource_sha256", None),
        ("evidence_contract_resource_sha256", "sha256:short"),
        ("source_bundle_resource_sha256s", _digest("j")),
        ("source_bundle_resource_sha256s", [_digest("4"), 7]),
        ("globalvalues_baseline_resource_sha256", "6" * 64),
    ],
)
def test_canonicalize_rejects_invalid_schema_digests_and_types(
    field: str,
    invalid_value: Any,
) -> None:
    payload = _valid_payload()
    payload[field] = invalid_value

    with pytest.raises(ValueError, match="build_inputs_"):
        canonicalize_build_inputs(payload)


def test_canonicalize_does_not_mutate_the_caller_mapping() -> None:
    payload = _valid_payload()
    original = deepcopy(payload)

    canonicalize_build_inputs(payload)

    assert payload == original
