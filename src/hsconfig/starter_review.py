"""Closed independent review authority for one schema-2 starter candidate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from typing import Any
import unicodedata

from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_candidate import (
    ValidatedStarterCandidate,
    validate_starter_candidate,
)
from hsconfig.starter_context import (
    StarterContext,
    validate_starter_context_document,
)
from hsconfig.starter_contract import (
    REVIEW_CONFIDENCE,
    REVIEW_STATUSES,
    REVIEW_TARGETS,
    SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    STARTER_REVIEW_FIELDS,
    STARTER_REVIEW_ID_MAX_CHARS,
    STARTER_REVIEW_MAX_BYTES,
    STARTER_REVIEW_MAX_REQUESTS,
    STARTER_REVIEW_REQUEST_CODE_MAX_CHARS,
    STARTER_REVIEW_REQUEST_MESSAGE_MAX_CHARS,
    STARTER_REVIEW_SUMMARY_MAX_CHARS,
    validate_candidate_revision,
)
from hsconfig.starter_document import StarterDocument, seal_starter_document


_REVIEW_REQUEST_FIELDS = frozenset({"code", "target", "message"})
_CLOSED_IDENTIFIER_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_CONTENT_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_WINDOWS_DRIVE_PATH_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
_UNC_PATH_RE = re.compile(r"(?<![\\])\\\\[^\\/\s]+[\\/][^\\/\s]+")
_ROOTED_BACKSLASH_PATH_RE = re.compile(r"(?<![A-Za-z0-9\\])\\(?![\\\s])")
_POSIX_ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9/])/(?![/\s])")
_RELATIVE_TRAVERSAL_PATH_RE = re.compile(r"(?<![A-Za-z0-9.])\.\.[\\/]")
_RELATIVE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._-])(?:\.[\\/])?[A-Za-z0-9._-]+[\\/]"
    r"[A-Za-z0-9._/-]+"
)
_URI_SCHEME_RE = re.compile(
    r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]{0,31}:(?=\S)"
)
_OBFUSCATED_URI_RE = re.compile(
    r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]{0,31}\s*:\s*[\\/]{2}"
)
_SCHEMELESS_HOST_RE = re.compile(
    r"(?<![A-Za-z0-9.-])www\.(?:[A-Za-z0-9-]+\.)+"
    r"[A-Za-z]{2,63}\.?(?![A-Za-z0-9.-])",
    re.IGNORECASE,
)
_TRANSPORT_TEXT = (
    "captured_at",
    "retrieved_at",
    "source_url",
    "raw_html",
    "runtime_root",
    "output_base_root",
)


@dataclass(frozen=True, slots=True)
class ValidatedStarterReview:
    """Freshly validated immutable review values and their sealed document."""

    document: StarterDocument
    review_id: str
    review_status: str
    confidence: str
    starter_context_sha256: str
    candidate_id: str
    candidate_revision: int
    candidate_sha256: str
    revision_requests: tuple[FrozenJsonDocument, ...]
    review_summary: str


def validate_starter_review(
    document: StarterDocument,
    *,
    context: StarterContext,
    candidate: ValidatedStarterCandidate,
) -> ValidatedStarterReview:
    """Validate one review against freshly derived context/candidate values."""

    fresh_context = _fresh_context(context)
    fresh_candidate = _fresh_candidate(
        candidate,
        context=fresh_context,
    )
    value = _validated_review_document_value(document)

    review_id = _closed_identifier(
        value.get("review_id"),
        maximum=STARTER_REVIEW_ID_MAX_CHARS,
        error="starter_review_id_invalid",
    )
    review_status = value.get("review_status")
    if type(review_status) is not str or review_status not in REVIEW_STATUSES:
        raise ValueError("starter_review_status_invalid")
    confidence = value.get("confidence")
    if type(confidence) is not str or confidence not in REVIEW_CONFIDENCE:
        raise ValueError("starter_review_confidence_invalid")

    starter_context_sha256 = _standard_digest(
        value.get("starter_context_sha256"),
        error="starter_review_context_sha256_invalid",
    )
    if starter_context_sha256 != fresh_context.document.content_sha256:
        raise ValueError("starter_review_context_sha256_invalid")
    candidate_id = _closed_identifier(
        value.get("candidate_id"),
        maximum=STARTER_REVIEW_ID_MAX_CHARS,
        error="starter_review_candidate_id_invalid",
    )
    if candidate_id != "lead" or candidate_id != fresh_candidate.candidate_id:
        raise ValueError("starter_review_candidate_id_invalid")
    candidate_revision = validate_candidate_revision(
        value.get("candidate_revision")
    )
    if candidate_revision != fresh_candidate.candidate_revision:
        raise ValueError("starter_review_candidate_revision_invalid")
    candidate_sha256 = _standard_digest(
        value.get("candidate_sha256"),
        error="starter_review_candidate_sha256_invalid",
    )
    if candidate_sha256 != fresh_candidate.document.content_sha256:
        raise ValueError("starter_review_candidate_sha256_invalid")

    revision_requests = _validated_revision_requests(
        value.get("revision_requests")
    )
    if (review_status == "approved") != (not revision_requests):
        raise ValueError("starter_review_status_requests_mismatch")
    review_summary = _safe_prose(
        value.get("review_summary"),
        maximum=STARTER_REVIEW_SUMMARY_MAX_CHARS,
        error="starter_review_summary_invalid",
    )
    return ValidatedStarterReview(
        document=document,
        review_id=review_id,
        review_status=review_status,
        confidence=confidence,
        starter_context_sha256=starter_context_sha256,
        candidate_id=candidate_id,
        candidate_revision=candidate_revision,
        candidate_sha256=candidate_sha256,
        revision_requests=revision_requests,
        review_summary=review_summary,
    )


def _fresh_context(context: StarterContext) -> StarterContext:
    if type(context) is not StarterContext:
        raise TypeError("starter_review_context_invalid")
    if type(context.document) is not StarterDocument:
        raise TypeError("starter_review_context_invalid")
    try:
        fresh = validate_starter_context_document(context.document)
    except (AttributeError, TypeError, ValueError):
        raise ValueError("starter_review_context_invalid") from None
    if fresh != context:
        raise ValueError("starter_review_context_invalid")
    if (
        fresh.document.to_value().get("schema_version")
        != SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION
    ):
        raise ValueError("starter_review_context_invalid")
    return fresh


def _fresh_candidate(
    candidate: ValidatedStarterCandidate,
    *,
    context: StarterContext,
) -> ValidatedStarterCandidate:
    if type(candidate) is not ValidatedStarterCandidate:
        raise TypeError("starter_review_candidate_invalid")
    if type(candidate.document) is not StarterDocument:
        raise TypeError("starter_review_candidate_invalid")
    try:
        fresh = validate_starter_candidate(
            candidate.document,
            context=context,
        )
    except (AttributeError, TypeError, ValueError):
        raise ValueError("starter_review_candidate_invalid") from None
    if fresh != candidate:
        raise ValueError("starter_review_candidate_invalid")
    return fresh


def _validated_review_document_value(
    document: StarterDocument,
) -> dict[str, Any]:
    if not isinstance(document, StarterDocument):
        raise TypeError("starter_review_document_invalid")
    try:
        value = document.to_value()
    except (TypeError, ValueError):
        raise ValueError("starter_review_document_invalid") from None
    if set(value) != STARTER_REVIEW_FIELDS:
        raise ValueError("starter_review_fields_invalid")
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"]
        != SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION
    ):
        raise ValueError("starter_review_schema_version_invalid")
    unsigned = dict(value)
    content_sha256 = unsigned.pop("content_sha256")
    try:
        resealed = seal_starter_document(
            unsigned,
            expected_fields=STARTER_REVIEW_FIELDS,
            schema_version=SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
        )
    except (TypeError, ValueError):
        raise ValueError("starter_review_content_sha256_invalid") from None
    if (
        not isinstance(content_sha256, str)
        or content_sha256 != document.content_sha256
        or content_sha256 != resealed.content_sha256
        or document.canonical_json != resealed.canonical_json
    ):
        raise ValueError("starter_review_content_sha256_invalid")
    if len(document.canonical_json) > STARTER_REVIEW_MAX_BYTES:
        raise ValueError("starter_review_size_invalid")
    return value


def _validated_revision_requests(
    value: object,
) -> tuple[FrozenJsonDocument, ...]:
    if not isinstance(value, list) or len(value) > STARTER_REVIEW_MAX_REQUESTS:
        raise ValueError("starter_review_requests_invalid")
    rows: list[dict[str, str]] = []
    for raw_row in value:
        if not isinstance(raw_row, Mapping) or set(raw_row) != _REVIEW_REQUEST_FIELDS:
            raise ValueError("starter_review_request_fields_invalid")
        code = _closed_identifier(
            raw_row.get("code"),
            maximum=STARTER_REVIEW_REQUEST_CODE_MAX_CHARS,
            error="starter_review_request_code_invalid",
        )
        target = raw_row.get("target")
        if type(target) is not str or target not in REVIEW_TARGETS:
            raise ValueError("starter_review_request_target_invalid")
        message = _safe_prose(
            raw_row.get("message"),
            maximum=STARTER_REVIEW_REQUEST_MESSAGE_MAX_CHARS,
            error="starter_review_request_message_invalid",
        )
        rows.append({"code": code, "target": target, "message": message})
    if rows != sorted(rows, key=_canonical_json_bytes):
        raise ValueError("starter_review_revision_requests_order_invalid")
    return tuple(FrozenJsonDocument.from_value(row) for row in rows)


def _closed_identifier(value: object, *, maximum: int, error: str) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or _CLOSED_IDENTIFIER_RE.fullmatch(value) is None
    ):
        raise ValueError(error)
    return value


def _standard_digest(value: object, *, error: str) -> str:
    if type(value) is not str or _CONTENT_SHA256_RE.fullmatch(value) is None:
        raise ValueError(error)
    return value


def _safe_prose(value: object, *, maximum: int, error: str) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(
            unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
            for character in value
        )
        or "<" in value
        or ">" in value
        or _WINDOWS_DRIVE_PATH_RE.search(value) is not None
        or _UNC_PATH_RE.search(value) is not None
        or _ROOTED_BACKSLASH_PATH_RE.search(value) is not None
        or _POSIX_ABSOLUTE_PATH_RE.search(value) is not None
        or _RELATIVE_TRAVERSAL_PATH_RE.search(value) is not None
        or _RELATIVE_PATH_RE.search(value) is not None
        or _URI_SCHEME_RE.search(value) is not None
        or _OBFUSCATED_URI_RE.search(value) is not None
        or _SCHEMELESS_HOST_RE.search(value) is not None
        or any(token in value.casefold() for token in _TRANSPORT_TEXT)
    ):
        raise ValueError(error)
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = ("ValidatedStarterReview", "validate_starter_review")
