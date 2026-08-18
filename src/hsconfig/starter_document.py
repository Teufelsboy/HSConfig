"""Bounded immutable authority documents for optimized starter input."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Any

from hsconfig.package_io import plain_file_status, read_file_no_follow
from hsconfig.package_request import FrozenJsonDocument


_CONTENT_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class StarterDocument:
    """A canonical starter object that retains no caller-owned path authority."""

    document: FrozenJsonDocument
    content_sha256: str

    @property
    def canonical_json(self) -> bytes:
        return self.document.canonical_json

    def to_value(self) -> dict[str, Any]:
        value = self.document.to_value()
        if not isinstance(value, dict):
            raise TypeError("starter_document_root_invalid")
        return value


def seal_starter_document(
    value: Mapping[str, Any],
    *,
    expected_fields: frozenset[str],
    schema_version: int,
) -> StarterDocument:
    """Canonicalize a trusted draft and bind its self digest exactly once."""

    if not isinstance(value, Mapping):
        raise ValueError("starter_document_root_invalid")
    unsigned_fields = expected_fields - {"content_sha256"}
    if set(value) != unsigned_fields:
        raise ValueError("starter_document_fields_invalid")
    normalized = FrozenJsonDocument.from_value(dict(value)).to_value()
    _validate_unsigned_shape(
        normalized,
        expected_fields=expected_fields,
        schema_version=schema_version,
    )
    digest = _digest_for_unsigned_value(normalized)
    sealed_value = {**normalized, "content_sha256": digest}
    document = FrozenJsonDocument.from_value(sealed_value)
    return StarterDocument(document=document, content_sha256=digest)


def load_starter_document(
    path: Path,
    *,
    maximum_bytes: int,
    expected_fields: frozenset[str],
    schema_version: int,
) -> StarterDocument:
    """Load one bounded no-follow source file without retaining its path."""

    raw = _read_bounded_no_follow(Path(path), maximum_bytes=maximum_bytes)
    _reject_unsafe_source_bytes(raw)
    document = FrozenJsonDocument.from_json_bytes(raw)
    if document.canonical_json != raw:
        raise ValueError("starter_document_not_canonical")
    value = document.to_value()
    _validate_sealed_shape(
        value,
        expected_fields=expected_fields,
        schema_version=schema_version,
    )
    content_sha256 = value["content_sha256"]
    if not isinstance(content_sha256, str) or (
        _CONTENT_SHA256_RE.fullmatch(content_sha256) is None
    ):
        raise ValueError("starter_document_content_sha256_invalid")
    unsigned_value = dict(value)
    del unsigned_value["content_sha256"]
    if content_sha256 != _digest_for_unsigned_value(unsigned_value):
        raise ValueError("starter_document_content_sha256_invalid")
    return StarterDocument(document=document, content_sha256=content_sha256)


def _read_bounded_no_follow(path: Path, *, maximum_bytes: int) -> bytes:
    if type(maximum_bytes) is not int or maximum_bytes < 0:
        raise ValueError("starter_document_maximum_bytes_invalid")
    status = plain_file_status(path)
    return read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=maximum_bytes,
    )


def _reject_unsafe_source_bytes(raw: bytes) -> None:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("starter_document_bom_forbidden")
    if b"\x00" in raw:
        raise ValueError("starter_document_nul_forbidden")
    if b"\r" in raw:
        raise ValueError("starter_document_bare_cr_forbidden")


def _validate_unsigned_shape(
    value: object,
    *,
    expected_fields: frozenset[str],
    schema_version: int,
) -> None:
    if not isinstance(value, dict) or set(value) != (
        expected_fields - {"content_sha256"}
    ):
        raise ValueError("starter_document_fields_invalid")
    if type(value.get("schema_version")) is not int or value[
        "schema_version"
    ] != schema_version:
        raise ValueError("starter_document_schema_version_invalid")


def _validate_sealed_shape(
    value: object,
    *,
    expected_fields: frozenset[str],
    schema_version: int,
) -> None:
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise ValueError("starter_document_fields_invalid")
    if type(value.get("schema_version")) is not int or value[
        "schema_version"
    ] != schema_version:
        raise ValueError("starter_document_schema_version_invalid")


def _digest_for_unsigned_value(value: Mapping[str, Any]) -> str:
    canonical = FrozenJsonDocument.from_value(value).canonical_json
    return "sha256:" + sha256(canonical).hexdigest()


__all__ = (
    "StarterDocument",
    "load_starter_document",
    "seal_starter_document",
)
