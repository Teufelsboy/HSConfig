"""Closed independent review authority and fresh quality decision facts."""

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
    _known_evidence_references,
    _quality_globalvalues_semantic_projection,
    _validate_mulligan_rows,
    changed_globalvalue_keys,
    validate_starter_candidate,
)
from hsconfig.starter_context import (
    StarterContext,
    validate_starter_context_document,
)
from hsconfig.starter_contract import (
    QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
    QUALITY_STARTER_REVIEW_FIELDS,
    QUALITY_STARTER_SCHEMA_VERSION,
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
_REVIEW_FACTS_FIELDS = frozenset(
    {
        "schema_version", "starter_context_sha256", "candidate_sha256", "candidate_id",
        "candidate_revision", "globalvalues_changes", "card_dispositions",
        "rules_by_runtime_owner", "evidence_references", "assumptions", "findings",
        "runtime_authorized", "content_sha256",
    }
)
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
    validation_receipt: FrozenJsonDocument | None = None,
) -> ValidatedStarterReview:
    """Validate one review against freshly derived context/candidate values."""

    fresh_context = _fresh_context(context)
    fresh_candidate = _fresh_candidate(
        candidate,
        context=fresh_context,
    )
    value = _validated_review_document_value(document)
    if value["schema_version"] != fresh_context.document.to_value()["schema_version"]:
        raise ValueError("starter_review_schema_pair_invalid")

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
    if value["schema_version"] == QUALITY_STARTER_SCHEMA_VERSION:
        _validate_quality_receipt(
            validation_receipt,
            context=fresh_context,
            candidate=fresh_candidate,
            expected_digest=value["candidate_validation_receipt_sha256"],
        )

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


def build_candidate_review_facts(
    *,
    context: StarterContext,
    candidate: ValidatedStarterCandidate,
) -> FrozenJsonDocument:
    """Seal diagnostic facts only after reconstructing both authority objects."""

    context = _fresh_context(context)
    candidate = _fresh_candidate(candidate, context=context)
    context_value = context.document.to_value()
    if context_value["schema_version"] != QUALITY_STARTER_SCHEMA_VERSION:
        raise ValueError("starter_review_context_invalid")
    value = candidate.document.to_value()
    baseline = context_value["globalvalues_baseline"]["values"]
    desired = candidate.globalvalues.to_value()
    before = _quality_globalvalues_semantic_projection(baseline)
    after = _quality_globalvalues_semantic_projection(desired)
    changes = {
        key: {
            "before": before[key],
            "after": after[key],
            "justification": value["globalvalues_justifications"][key],
        }
        for key in changed_globalvalue_keys(baseline, desired)
    }
    physical_cards = {row["card_id"]: row["count"] for row in context_value["cards"]}
    rules = []
    for row in _validate_mulligan_rows(
        value["mulligan"], physical_cards=physical_cards
    ):
        for card_id in row["selector_cards"]:
            rules.append(
                {
                    "rule_id": row["rule_id"],
                    "runtime_card_id": card_id,
                    "source_card_ids": list(row["selector_cards"]),
                    "surface": "Mulligan",
                    "condition": row["condition"],
                    "action": row["action"],
                    "selector_kind": row["selector_kind"],
                    "rationale": value["rule_rationales"][row["rule_id"]],
                }
            )
    for document in candidate.card_behavior_rows:
        row = document.to_value()
        rules.append(
            {
                "rule_id": row["rule_id_suffix"],
                "runtime_card_id": row["runtime_card_id"],
                "source_card_ids": [row["source_card_id"]],
                "surface": row["behavior_block"],
                "condition": row["condition"],
                "value": row["value"],
                "link_kind": row["link_kind"],
                "rationale": value["rule_rationales"][row["rule_id_suffix"]],
            }
        )
    if value["combo"] is not None:
        row = value["combo"]
        for card_id in row["cards"]:
            rules.append(
                {
                    "rule_id": row["rule_id"],
                    "runtime_card_id": card_id,
                    "source_card_ids": row["cards"],
                    "surface": "Combo",
                    "condition": row["condition"],
                    "timing": row["timing"],
                    "values": row["values"],
                    "rationale": value["rule_rationales"][row["rule_id"]],
                }
            )
    known_refs = _known_evidence_references(context_value)
    refs = sorted(
        {
            ref
            for row in value["globalvalues_justifications"].values()
            for ref in row["evidence_refs"]
        }
    )
    research_conflicts = [
        {"observation_id": row["observation_id"], "conflict": conflict}
        for row in context_value["research_evidence"]["observations"]
        for conflict in row["conflicts"]
    ]
    facts = {
        "schema_version": 1,
        "starter_context_sha256": context.document.content_sha256,
        "candidate_sha256": candidate.document.content_sha256,
        "candidate_id": candidate.candidate_id,
        "candidate_revision": candidate.candidate_revision,
        "globalvalues_changes": changes,
        "card_dispositions": sorted(
            value["card_dispositions"], key=lambda row: row["card_id"]
        ),
        "rules_by_runtime_owner": sorted(rules, key=_canonical_json_bytes),
        "evidence_references": [
            {"reference_id": ref, "kind": known_refs[ref]} for ref in refs
        ],
        "assumptions": value["assumptions"],
        # Fresh candidate validation has already rejected runtime duplicates/conflicts.
        "findings": {
            "runtime_duplicates": [],
            "runtime_conflicts": [],
            "research_conflicts": sorted(research_conflicts, key=_canonical_json_bytes),
        },
        "runtime_authorized": False,
    }
    return FrozenJsonDocument.from_value(
        seal_starter_document(
            facts,
            expected_fields=_REVIEW_FACTS_FIELDS,
            schema_version=1,
        ).to_value()
    )


def _validate_quality_receipt(
    receipt: FrozenJsonDocument | None,
    *,
    context: StarterContext,
    candidate: ValidatedStarterCandidate,
    expected_digest: object,
) -> None:
    error = "starter_review_validation_receipt_invalid"
    if type(receipt) is not FrozenJsonDocument:
        raise ValueError(error)
    try:
        value = receipt.to_value()
        if set(value) != QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS:
            raise ValueError(error)
        unsigned = dict(value)
        digest = unsigned.pop("content_sha256")
        sealed = seal_starter_document(
            unsigned,
            expected_fields=QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
            schema_version=2,
        )
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != 2
            or value["receipt_kind"] != "candidate_validation"
            or type(value["run_id"]) is not str
            or re.fullmatch(r"[0-9a-f]{32}", value["run_id"]) is None
            or type(value["candidate_revision"]) is not int
            or value["candidate_revision"] != candidate.candidate_revision
            or value["candidate_sha256"] != candidate.document.content_sha256
            or value["starter_context_sha256"] != context.document.content_sha256
            or value["status"] != "valid"
            or value["findings"] != []
            or digest != sealed.content_sha256
            or digest != expected_digest
            or receipt.canonical_json != sealed.canonical_json
        ):
            raise ValueError(error)
        fresh_facts = build_candidate_review_facts(context=context, candidate=candidate)
        if (
            FrozenJsonDocument.from_value(value["review_facts"]).canonical_json
            != fresh_facts.canonical_json
        ):
            raise ValueError(error)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError(error) from None


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
        not in {SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION, QUALITY_STARTER_SCHEMA_VERSION}
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
    schema_version = value.get("schema_version")
    if (
        type(schema_version) is not int
        or schema_version not in {
            SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION, QUALITY_STARTER_SCHEMA_VERSION,
        }
    ):
        raise ValueError("starter_review_schema_version_invalid")
    fields = (
        QUALITY_STARTER_REVIEW_FIELDS
        if schema_version == QUALITY_STARTER_SCHEMA_VERSION
        else STARTER_REVIEW_FIELDS
    )
    if set(value) != fields:
        raise ValueError("starter_review_fields_invalid")
    unsigned = dict(value)
    content_sha256 = unsigned.pop("content_sha256")
    try:
        resealed = seal_starter_document(
            unsigned,
            expected_fields=fields,
            schema_version=schema_version,
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


__all__ = (
    "ValidatedStarterReview",
    "build_candidate_review_facts",
    "validate_starter_review",
)
