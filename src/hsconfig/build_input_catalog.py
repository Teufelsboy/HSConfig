from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from hashlib import sha256
from importlib import resources
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any

from hsconfig.build_inputs import CanonicalBuildInputs, canonicalize_build_inputs


_SCHEMA_VERSION = 3
_STORE_SCHEMA_VERSION = 1
_AUDITED_ORDER = (
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
_CATALOG_FIELDS = frozenset(
    {
        "schema_version",
        "builds",
        "resource_sha256s",
        "content_sha256",
    }
)
_STORE_FIELDS = frozenset({"schema_version", "resources"})
_STORE_ENTRY_FIELDS = frozenset({"kind", "value"})
_STORE_KINDS = frozenset(
    {
        "card_snapshot",
        "deck_cards",
        "evidence_contract",
        "globalvalues_baseline",
        "general_preconfig",
        "acquisition_closure",
        "policy_profile",
        "source_bundle",
    }
)
_CONTENT_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RAW_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_INPUT_SHA256_FIELD = "input_sha256"
_PACKAGED_INPUTS = "resources/audited_build_inputs.json"
_PACKAGED_STORE = "resources/audited_build_resources.json"

# Updated only by the reviewed deterministic materialization step. This pin is
# deliberately independent of the self-hash embedded in the catalog.
APPROVED_AUDITED_BUILD_INPUTS_SHA256 = (
    "sha256:8235c5b64a622fcb84ab79c8594d29386aae1440d42537005b6212bf0675152c"
)


@dataclass(frozen=True, slots=True)
class AuditedBuildInputSet:
    schema_version: int
    builds: tuple[CanonicalBuildInputs, ...]
    content_sha256: str

    @property
    def resource_sha256s(self) -> tuple[str, ...]:
        return _resource_union(self.builds)


@dataclass(frozen=True, slots=True)
class FrozenBuildResourceStore:
    _values: Mapping[str, bytes]
    content_sha256s: tuple[str, ...]

    @classmethod
    def from_values(
        cls,
        values: Mapping[str, bytes],
    ) -> FrozenBuildResourceStore:
        copied = {
            str(key): bytes(value)
            for key, value in values.items()
        }
        return cls(
            _values=MappingProxyType(copied),
            content_sha256s=tuple(sorted(copied)),
        )

    def read_by_sha256(self, content_sha256: str) -> bytes:
        if (
            not isinstance(content_sha256, str)
            or _CONTENT_SHA256_RE.fullmatch(content_sha256) is None
        ):
            raise ValueError("build_resource_sha256_invalid")
        try:
            value = self._values[content_sha256]
        except KeyError as error:
            raise ValueError("build_resource_missing") from error
        return bytes(value)


def load_audited_build_inputs(path: Path) -> AuditedBuildInputSet:
    return _load_audited_build_inputs_bytes(Path(path).read_bytes())


def load_packaged_audited_build_inputs() -> AuditedBuildInputSet:
    raw = resources.files("hsconfig").joinpath(_PACKAGED_INPUTS).read_bytes()
    return _load_audited_build_inputs_bytes(raw)


def load_audited_build_resource_store(
    path: Path,
    *,
    audited_inputs: AuditedBuildInputSet,
) -> FrozenBuildResourceStore:
    return _load_audited_build_resource_store_bytes(
        Path(path).read_bytes(),
        expected_sha256s=audited_inputs.resource_sha256s,
    )


def load_packaged_audited_build_resource_store(
    *,
    audited_inputs: AuditedBuildInputSet,
) -> FrozenBuildResourceStore:
    raw = resources.files("hsconfig").joinpath(_PACKAGED_STORE).read_bytes()
    return _load_audited_build_resource_store_bytes(
        raw,
        expected_sha256s=audited_inputs.resource_sha256s,
    )


def _load_audited_build_inputs_bytes(raw: bytes) -> AuditedBuildInputSet:
    document = _canonical_document(raw, error="audited_build_catalog")
    if not isinstance(document, Mapping) or set(document) != _CATALOG_FIELDS:
        raise ValueError("audited_build_catalog_fields_invalid")
    if (
        type(document.get("schema_version")) is not int
        or document["schema_version"] != _SCHEMA_VERSION
    ):
        raise ValueError("audited_build_catalog_schema_invalid")
    rows = document.get("builds")
    if not isinstance(rows, list) or len(rows) != len(_AUDITED_ORDER):
        raise ValueError("audited_build_catalog_count_invalid")

    builds: list[CanonicalBuildInputs] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("audited_build_catalog_row_invalid")
        row_copy = dict(row)
        serialized_input_sha256 = row_copy.pop(_INPUT_SHA256_FIELD, None)
        if (
            not isinstance(serialized_input_sha256, str)
            or _RAW_SHA256_RE.fullmatch(serialized_input_sha256) is None
        ):
            raise ValueError("audited_build_catalog_input_sha256_invalid")
        build = canonicalize_build_inputs(row_copy)
        if build.input_sha256 != serialized_input_sha256:
            raise ValueError("audited_build_catalog_input_sha256_stale")
        builds.append(build)

    frozen_builds = tuple(builds)
    if tuple(row.deck_name for row in frozen_builds) != _AUDITED_ORDER:
        raise ValueError("audited_build_catalog_order_invalid")
    _require_unique(
        (row.deck_name for row in frozen_builds),
        error="audited_build_catalog_duplicate_name",
    )
    _require_unique(
        (row.deck_fingerprint for row in frozen_builds),
        error="audited_build_catalog_duplicate_fingerprint",
    )
    _require_unique(
        (row.input_sha256 for row in frozen_builds),
        error="audited_build_catalog_duplicate_input",
    )

    declared_resources = _content_sha256_sequence(
        document.get("resource_sha256s"),
        error="audited_build_catalog_resource_union_invalid",
    )
    if declared_resources != _resource_union(frozen_builds):
        raise ValueError("audited_build_catalog_resource_union_invalid")

    declared_content_sha256 = document.get("content_sha256")
    digest_payload = dict(document)
    digest_payload.pop("content_sha256")
    computed_content_sha256 = _raw_content_sha256(
        _canonical_json(digest_payload)
    )
    if declared_content_sha256 != computed_content_sha256:
        raise ValueError("audited_build_catalog_content_sha256_stale")
    if computed_content_sha256 != APPROVED_AUDITED_BUILD_INPUTS_SHA256:
        raise ValueError("audited_build_catalog_not_approved")
    return AuditedBuildInputSet(
        schema_version=_SCHEMA_VERSION,
        builds=frozen_builds,
        content_sha256=computed_content_sha256,
    )


def _load_audited_build_resource_store_bytes(
    raw: bytes,
    *,
    expected_sha256s: Collection[str],
) -> FrozenBuildResourceStore:
    document = _canonical_document(raw, error="audited_build_store")
    if not isinstance(document, Mapping) or set(document) != _STORE_FIELDS:
        raise ValueError("audited_build_store_fields_invalid")
    if (
        type(document.get("schema_version")) is not int
        or document["schema_version"] != _STORE_SCHEMA_VERSION
    ):
        raise ValueError("audited_build_store_schema_invalid")
    entries = document.get("resources")
    if not isinstance(entries, Mapping):
        raise ValueError("audited_build_store_resources_invalid")

    values: dict[str, bytes] = {}
    for content_sha256, entry in entries.items():
        if (
            not isinstance(content_sha256, str)
            or _CONTENT_SHA256_RE.fullmatch(content_sha256) is None
        ):
            raise ValueError("audited_build_store_digest_alias")
        if not isinstance(entry, Mapping) or set(entry) != _STORE_ENTRY_FIELDS:
            raise ValueError("audited_build_store_entry_fields_invalid")
        if entry.get("kind") not in _STORE_KINDS:
            raise ValueError("audited_build_store_kind_invalid")
        value = _canonical_json(entry.get("value"))
        if _raw_content_sha256(value) != content_sha256:
            raise ValueError("audited_build_store_digest_mismatch")
        values[content_sha256] = value

    expected = tuple(sorted(expected_sha256s))
    if tuple(sorted(values)) != expected:
        raise ValueError("audited_build_store_resource_union_invalid")
    return FrozenBuildResourceStore.from_values(values)


def _resource_union(
    builds: tuple[CanonicalBuildInputs, ...],
) -> tuple[str, ...]:
    digests: set[str] = set()
    for row in builds:
        digests.update(
            {
                row.deck_cards_resource_sha256,
                row.card_snapshot_resource_sha256,
                row.policy_profile_resource_sha256,
                row.evidence_contract_resource_sha256,
                row.globalvalues_baseline_resource_sha256,
                row.general_preconfig_resource_sha256,
                row.acquisition_closure_resource_sha256,
            }
        )
        digests.update(row.source_bundle_resource_sha256s)
    return tuple(sorted(digests))


def _canonical_document(raw: bytes, *, error: str) -> Any:
    if not isinstance(raw, bytes):
        raise ValueError(f"{error}_bytes_invalid")
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
        raise ValueError("audited_build_json_invalid") from error


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("audited_build_json_duplicate_key")
        result[key] = value
    return result


def _raw_content_sha256(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _content_sha256_sequence(value: Any, *, error: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(error)
    normalized = tuple(value)
    if (
        any(
            not isinstance(item, str)
            or _CONTENT_SHA256_RE.fullmatch(item) is None
            for item in normalized
        )
        or len(set(normalized)) != len(normalized)
        or normalized != tuple(sorted(normalized))
    ):
        raise ValueError(error)
    return normalized


def _require_unique(values: Collection[str] | Any, *, error: str) -> None:
    frozen = tuple(values)
    if len(set(frozen)) != len(frozen):
        raise ValueError(error)


__all__ = (
    "APPROVED_AUDITED_BUILD_INPUTS_SHA256",
    "AuditedBuildInputSet",
    "FrozenBuildResourceStore",
    "load_audited_build_inputs",
    "load_audited_build_resource_store",
    "load_packaged_audited_build_inputs",
    "load_packaged_audited_build_resource_store",
)
