from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from hsconfig.build_inputs import canonicalize_build_inputs
from hsconfig.build_input_catalog import (
    load_audited_build_inputs,
    load_audited_build_resource_store,
    load_packaged_audited_build_inputs,
    load_packaged_audited_build_resource_store,
)


RESOURCE_ROOT = Path("src/hsconfig/resources")
INPUTS_PATH = RESOURCE_ROOT / "audited_build_inputs.json"
STORE_PATH = RESOURCE_ROOT / "audited_build_resources.json"
AUDITED_ORDER = (
    "ShadowPriest",
    "CtAPaladin",
    "PirateRogue",
    "BigShaman",
    "Discolock",
    "TreantDruid",
    "ImbueMage",
    "MechPala",
    "Kingslayer",
    "Boarlock",
    "PirateDH",
    "CuteWarrior",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _write(path: Path, value: object) -> None:
    path.write_bytes(_canonical(value))


def _rehash_row(row: dict) -> None:
    payload = dict(row)
    payload.pop("input_sha256", None)
    row["input_sha256"] = canonicalize_build_inputs(payload).input_sha256


def _rehash_catalog(document: dict) -> None:
    payload = dict(document)
    payload.pop("content_sha256", None)
    document["content_sha256"] = _digest(_canonical(payload))


def test_packaged_catalog_is_exact_schema_v2_audited_set() -> None:
    audited = load_audited_build_inputs(INPUTS_PATH)

    assert audited.schema_version == 2
    assert tuple(row.deck_name for row in audited.builds) == AUDITED_ORDER
    assert len({row.deck_fingerprint for row in audited.builds}) == 12
    assert len({row.input_sha256 for row in audited.builds}) == 12
    assert all(row.schema_version == 2 for row in audited.builds)
    assert all(row.deck_cards_resource_sha256 for row in audited.builds)
    assert all(row.card_snapshot_resource_sha256 for row in audited.builds)
    assert all(row.policy_profile_resource_sha256 for row in audited.builds)
    assert all(row.evidence_contract_resource_sha256 for row in audited.builds)
    assert all(row.source_bundle_resource_sha256s for row in audited.builds)
    assert all(
        row.globalvalues_baseline_resource_sha256 for row in audited.builds
    )


def test_packaged_store_is_exact_catalog_resource_union() -> None:
    audited = load_audited_build_inputs(INPUTS_PATH)
    store = load_audited_build_resource_store(
        STORE_PATH,
        audited_inputs=audited,
    )

    assert store.content_sha256s == audited.resource_sha256s


def test_importlib_packaged_loaders_resolve_the_same_frozen_resources() -> None:
    audited = load_packaged_audited_build_inputs()
    store = load_packaged_audited_build_resource_store(
        audited_inputs=audited,
    )

    assert tuple(row.deck_name for row in audited.builds) == AUDITED_ORDER
    assert store.content_sha256s == audited.resource_sha256s


@pytest.mark.parametrize("row_count", [11, 13])
def test_catalog_rejects_wrong_row_count(
    tmp_path: Path,
    row_count: int,
) -> None:
    document = _read(INPUTS_PATH)
    if row_count == 11:
        document["builds"].pop()
    else:
        document["builds"].append(deepcopy(document["builds"][-1]))
    _rehash_catalog(document)
    path = tmp_path / "catalog.json"
    _write(path, document)

    with pytest.raises(ValueError, match="audited_build_catalog_"):
        load_audited_build_inputs(path)


@pytest.mark.parametrize(
    "mutation",
    [
        "reordered",
        "duplicate_name",
        "duplicate_fingerprint",
        "duplicate_input",
    ],
)
def test_catalog_rejects_order_and_duplicate_identities(
    tmp_path: Path,
    mutation: str,
) -> None:
    document = _read(INPUTS_PATH)
    rows = document["builds"]
    if mutation == "reordered":
        rows[0], rows[1] = rows[1], rows[0]
    elif mutation == "duplicate_name":
        rows[1]["deck_name"] = rows[0]["deck_name"]
        _rehash_row(rows[1])
    elif mutation == "duplicate_fingerprint":
        rows[1]["deck_fingerprint"] = rows[0]["deck_fingerprint"]
        _rehash_row(rows[1])
    else:
        rows[1]["input_sha256"] = rows[0]["input_sha256"]
    _rehash_catalog(document)
    path = tmp_path / "catalog.json"
    _write(path, document)

    with pytest.raises(ValueError, match="audited_build_catalog_"):
        load_audited_build_inputs(path)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("schema_version", 1),
        ("deck_cards_resource_sha256", None),
        ("card_snapshot_resource_sha256", "sha256:short"),
        (
            "policy_profile_resource_sha256",
            "sha256:" + ("f" * 64),
        ),
        ("evidence_contract_resource_sha256", None),
        ("source_bundle_resource_sha256s", []),
        ("globalvalues_baseline_resource_sha256", "not-a-digest"),
    ],
)
def test_catalog_rejects_incomplete_or_substituted_raw_roots(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    document = _read(INPUTS_PATH)
    row = document["builds"][0]
    if replacement is None:
        row.pop(field)
    else:
        row[field] = replacement
    if field != "schema_version":
        try:
            _rehash_row(row)
        except ValueError:
            pass
    _rehash_catalog(document)
    path = tmp_path / "catalog.json"
    _write(path, document)

    with pytest.raises(ValueError, match="build_inputs_|audited_build_catalog_"):
        load_audited_build_inputs(path)


def test_catalog_rejects_stale_outer_hash(tmp_path: Path) -> None:
    document = _read(INPUTS_PATH)
    document["content_sha256"] = "sha256:" + ("0" * 64)
    path = tmp_path / "catalog.json"
    _write(path, document)

    with pytest.raises(
        ValueError,
        match="audited_build_catalog_content_sha256_stale",
    ):
        load_audited_build_inputs(path)


def test_catalog_rejects_coordinated_substitution_with_recomputed_hashes(
    tmp_path: Path,
) -> None:
    document = _read(INPUTS_PATH)
    row = document["builds"][0]
    row["deck_cards_resource_sha256"] = "sha256:" + ("f" * 64)
    _rehash_row(row)
    references = set(document["resource_sha256s"])
    references.remove(
        _read(INPUTS_PATH)["builds"][0]["deck_cards_resource_sha256"]
    )
    references.add(row["deck_cards_resource_sha256"])
    document["resource_sha256s"] = sorted(references)
    _rehash_catalog(document)
    path = tmp_path / "catalog.json"
    _write(path, document)

    with pytest.raises(
        ValueError,
        match="audited_build_catalog_not_approved",
    ):
        load_audited_build_inputs(path)


def test_catalog_rejects_noncanonical_json_and_duplicate_keys(
    tmp_path: Path,
) -> None:
    document = _read(INPUTS_PATH)
    pretty = tmp_path / "pretty.json"
    pretty.write_text(json.dumps(document, indent=2), encoding="utf-8")
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(
        b'{"builds":[],"builds":[],"content_sha256":"sha256:'
        + (b"0" * 64)
        + b'","resource_sha256s":[],"schema_version":2}'
    )

    with pytest.raises(ValueError, match="audited_build_catalog_json_noncanonical"):
        load_audited_build_inputs(pretty)
    with pytest.raises(ValueError, match="audited_build_catalog_json_invalid"):
        load_audited_build_inputs(duplicate)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_store_rejects_missing_or_extra_blob(
    tmp_path: Path,
    mutation: str,
) -> None:
    audited = load_audited_build_inputs(INPUTS_PATH)
    document = _read(STORE_PATH)
    if mutation == "missing":
        document["resources"].pop(next(iter(document["resources"])))
    else:
        value = {"unexpected": True}
        document["resources"][_digest(_canonical(value))] = {
            "kind": "deck_cards",
            "value": value,
        }
    path = tmp_path / "store.json"
    _write(path, document)

    with pytest.raises(
        ValueError,
        match="audited_build_store_resource_union_invalid",
    ):
        load_audited_build_resource_store(path, audited_inputs=audited)


@pytest.mark.parametrize(
    "mutation",
    ["digest_alias", "digest_mismatch", "unknown_field", "unknown_kind"],
)
def test_store_rejects_invalid_digest_or_entry_fields(
    tmp_path: Path,
    mutation: str,
) -> None:
    audited = load_audited_build_inputs(INPUTS_PATH)
    document = _read(STORE_PATH)
    digest_key = next(iter(document["resources"]))
    entry = document["resources"][digest_key]
    if mutation == "digest_alias":
        document["resources"]["sha256:" + ("0" * 64)] = deepcopy(entry)
    elif mutation == "digest_mismatch":
        entry["value"] = {"substituted": True}
    elif mutation == "unknown_field":
        entry["surprise"] = True
    else:
        entry["kind"] = "mutable_blob"
    path = tmp_path / "store.json"
    _write(path, document)

    with pytest.raises(ValueError, match="audited_build_store_"):
        load_audited_build_resource_store(path, audited_inputs=audited)


def test_store_rejects_noncanonical_json_and_duplicate_keys(
    tmp_path: Path,
) -> None:
    audited = load_audited_build_inputs(INPUTS_PATH)
    document = _read(STORE_PATH)
    pretty = tmp_path / "pretty-store.json"
    pretty.write_text(json.dumps(document, indent=2), encoding="utf-8")
    duplicate = tmp_path / "duplicate-store.json"
    duplicate.write_bytes(
        b'{"resources":{},"resources":{},"schema_version":1}'
    )

    with pytest.raises(ValueError, match="audited_build_store_json_noncanonical"):
        load_audited_build_resource_store(pretty, audited_inputs=audited)
    with pytest.raises(ValueError, match="audited_build_store_json_invalid"):
        load_audited_build_resource_store(duplicate, audited_inputs=audited)


def test_store_returns_immutable_copied_bytes() -> None:
    audited = load_audited_build_inputs(INPUTS_PATH)
    store = load_audited_build_resource_store(
        STORE_PATH,
        audited_inputs=audited,
    )
    digest_key = store.content_sha256s[0]
    first = store.read_by_sha256(digest_key)
    second = store.read_by_sha256(digest_key)

    assert type(first) is bytes
    assert first == second
    with pytest.raises(TypeError):
        store._values[digest_key] = b"mutated"  # type: ignore[index]
