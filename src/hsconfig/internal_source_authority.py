from __future__ import annotations

import json
import hmac
from secrets import token_bytes, token_hex
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from weakref import WeakValueDictionary


_SEARCH_RECORDS_STAGE = "verified_search_records"
_SOURCE_DOCUMENTS_STAGE = "verified_source_documents"
_CALLER_AUTHORITY_ATTRIBUTES = (
    "trusted_source_documents",
    "trusted_source_search_records",
)
_ACTIVE_SEARCH = "active_search"
_CONSUMED_SEARCH = "consumed_search"
_DOCUMENT_ISSUED = "document_issued"
_ACTIVE_DOCUMENT = "active_document"
_HANDOFF_MAC_KEY = token_bytes(32)
_ACTIVE_ORIGINAL_TOKENS: WeakValueDictionary[str, _AuthorityToken] = (
    WeakValueDictionary()
)


@dataclass(frozen=True, slots=True)
class InternalSourceAuthorityHandoff:
    """Opaque in-process transport for source authority established by acquisition."""

    stage: str
    record_fingerprint: str
    document_fingerprint: str
    lineage_fingerprint: str
    search_records: tuple[dict[str, Any], ...]
    source_documents: tuple[dict[str, Any], ...]
    _token: object


@dataclass(frozen=True, slots=True)
class _ConsumedSearchLineage:
    record_fingerprint: str
    search_records: tuple[dict[str, Any], ...]
    _token: object


@dataclass(slots=True, weakref_slot=True)
class _AuthorityToken:
    nonce: str
    state: str
    record_fingerprint: str
    document_fingerprint: str
    lineage_fingerprint: str
    mac: str


def reject_caller_supplied_source_authority(args: Any) -> None:
    for attribute in _CALLER_AUTHORITY_ATTRIBUTES:
        if getattr(args, attribute, None) is not None:
            raise ValueError(f"caller_supplied_{attribute}_not_allowed")


def _issue_acquired_search_records_handoff(
    records: list[dict[str, Any]],
) -> InternalSourceAuthorityHandoff:
    copied_records = tuple(deepcopy(records))
    record_fingerprint = _payload_fingerprint(copied_records)
    lineage_fingerprint = _lineage_fingerprint(record_fingerprint, "")
    token = _new_authority_token(
        state=_ACTIVE_SEARCH,
        record_fingerprint=record_fingerprint,
        document_fingerprint="",
        lineage_fingerprint=lineage_fingerprint,
    )
    return InternalSourceAuthorityHandoff(
        stage=_SEARCH_RECORDS_STAGE,
        record_fingerprint=record_fingerprint,
        document_fingerprint="",
        lineage_fingerprint=lineage_fingerprint,
        search_records=copied_records,
        source_documents=(),
        _token=token,
    )


def _consume_acquired_search_records_handoff(
    handoff: InternalSourceAuthorityHandoff,
) -> tuple[list[dict[str, Any]], _ConsumedSearchLineage]:
    _require_handoff_type_and_stage(handoff, stage=_SEARCH_RECORDS_STAGE)
    token = _validated_authority_token(handoff._token)
    if token.state in {_CONSUMED_SEARCH, _DOCUMENT_ISSUED}:
        raise ValueError("source_authority_handoff_replayed")
    if token.state != _ACTIVE_SEARCH:
        raise ValueError("invalid_internal_source_authority_handoff")
    if _ACTIVE_ORIGINAL_TOKENS.get(token.nonce) is not token:
        raise ValueError("invalid_internal_source_authority_handoff")
    registered_fingerprint = token.record_fingerprint
    observed_fingerprint = _payload_fingerprint(
        handoff.search_records,
        failure_reason="source_authority_handoff_lineage_mismatch",
    )
    if (
        handoff.source_documents
        or handoff.document_fingerprint
        or handoff.record_fingerprint != registered_fingerprint
        or observed_fingerprint != registered_fingerprint
        or handoff.lineage_fingerprint
        != _lineage_fingerprint(registered_fingerprint, "")
    ):
        raise ValueError("source_authority_handoff_lineage_mismatch")
    consumed_token = _ACTIVE_ORIGINAL_TOKENS.pop(token.nonce, None)
    if consumed_token is not token:
        raise ValueError("invalid_internal_source_authority_handoff")
    _set_token_state(token, _CONSUMED_SEARCH)
    lineage = _ConsumedSearchLineage(
        record_fingerprint=registered_fingerprint,
        search_records=handoff.search_records,
        _token=token,
    )
    return deepcopy(list(handoff.search_records)), lineage


def _issue_generated_source_documents_handoff(
    lineage: _ConsumedSearchLineage,
    documents: list[dict[str, Any]],
) -> InternalSourceAuthorityHandoff:
    if not isinstance(lineage, _ConsumedSearchLineage):
        raise ValueError("invalid_internal_source_authority_lineage")
    token = _validated_authority_token(lineage._token)
    if token.state == _DOCUMENT_ISSUED:
        raise ValueError("source_authority_lineage_replayed")
    if token.state != _CONSUMED_SEARCH:
        raise ValueError("invalid_internal_source_authority_lineage")
    registered_fingerprint = token.record_fingerprint
    observed_record_fingerprint = _payload_fingerprint(
        lineage.search_records,
        failure_reason="source_authority_handoff_lineage_mismatch",
    )
    if (
        lineage.record_fingerprint != registered_fingerprint
        or observed_record_fingerprint != registered_fingerprint
    ):
        raise ValueError("source_authority_handoff_lineage_mismatch")
    _set_token_state(token, _DOCUMENT_ISSUED)
    copied_documents = tuple(deepcopy(documents))
    document_fingerprint = _payload_fingerprint(
        copied_documents,
        failure_reason="source_authority_handoff_lineage_mismatch",
    )
    lineage_fingerprint = _lineage_fingerprint(
        registered_fingerprint,
        document_fingerprint,
    )
    document_token = _new_authority_token(
        state=_ACTIVE_DOCUMENT,
        record_fingerprint=registered_fingerprint,
        document_fingerprint=document_fingerprint,
        lineage_fingerprint=lineage_fingerprint,
    )
    return InternalSourceAuthorityHandoff(
        stage=_SOURCE_DOCUMENTS_STAGE,
        record_fingerprint=registered_fingerprint,
        document_fingerprint=document_fingerprint,
        lineage_fingerprint=lineage_fingerprint,
        search_records=lineage.search_records,
        source_documents=copied_documents,
        _token=document_token,
    )


def trusted_source_documents_from_handoff(
    handoff: InternalSourceAuthorityHandoff | None,
) -> list[dict[str, Any]] | None:
    if handoff is None:
        return None
    _require_handoff_type_and_stage(handoff, stage=_SOURCE_DOCUMENTS_STAGE)
    token = _validated_authority_token(handoff._token)
    if token.state != _ACTIVE_DOCUMENT:
        raise ValueError("invalid_internal_source_authority_handoff")
    if _ACTIVE_ORIGINAL_TOKENS.get(token.nonce) is not token:
        raise ValueError("invalid_internal_source_authority_handoff")
    record_fingerprint = _payload_fingerprint(
        handoff.search_records,
        failure_reason="source_authority_handoff_lineage_mismatch",
    )
    document_fingerprint = _payload_fingerprint(
        handoff.source_documents,
        failure_reason="source_authority_handoff_lineage_mismatch",
    )
    lineage_fingerprint = _lineage_fingerprint(
        record_fingerprint,
        document_fingerprint,
    )
    if (
        token.record_fingerprint != record_fingerprint
        or token.document_fingerprint != document_fingerprint
        or token.lineage_fingerprint != lineage_fingerprint
        or handoff.record_fingerprint != record_fingerprint
        or handoff.document_fingerprint != document_fingerprint
        or handoff.lineage_fingerprint != lineage_fingerprint
    ):
        raise ValueError("source_authority_handoff_lineage_mismatch")
    return deepcopy(list(handoff.source_documents))


def _require_handoff_type_and_stage(
    handoff: Any,
    *,
    stage: str,
) -> None:
    if not isinstance(handoff, InternalSourceAuthorityHandoff):
        raise ValueError("invalid_internal_source_authority_handoff")
    if handoff.stage != stage:
        raise ValueError("invalid_internal_source_authority_handoff_stage")


def _payload_fingerprint(
    payload: Any,
    *,
    failure_reason: str = "invalid_internal_source_authority_handoff",
) -> str:
    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(failure_reason) from exc
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def _lineage_fingerprint(
    record_fingerprint: str,
    document_fingerprint: str,
) -> str:
    return _payload_fingerprint(
        {
            "record_fingerprint": record_fingerprint,
            "document_fingerprint": document_fingerprint,
        }
    )


def _new_authority_token(
    *,
    state: str,
    record_fingerprint: str,
    document_fingerprint: str,
    lineage_fingerprint: str,
) -> _AuthorityToken:
    token = _AuthorityToken(
        nonce=token_hex(16),
        state=state,
        record_fingerprint=record_fingerprint,
        document_fingerprint=document_fingerprint,
        lineage_fingerprint=lineage_fingerprint,
        mac="",
    )
    token.mac = _authority_token_mac(token)
    _ACTIVE_ORIGINAL_TOKENS[token.nonce] = token
    return token


def _validated_authority_token(value: Any) -> _AuthorityToken:
    if not isinstance(value, _AuthorityToken):
        raise ValueError("invalid_internal_source_authority_handoff")
    expected_mac = _authority_token_mac(value)
    if not hmac.compare_digest(value.mac, expected_mac):
        raise ValueError("invalid_internal_source_authority_handoff")
    return value


def _set_token_state(token: _AuthorityToken, state: str) -> None:
    token.state = state
    token.mac = _authority_token_mac(token)


def _authority_token_mac(token: _AuthorityToken) -> str:
    payload = json.dumps(
        {
            "nonce": token.nonce,
            "state": token.state,
            "record_fingerprint": token.record_fingerprint,
            "document_fingerprint": token.document_fingerprint,
            "lineage_fingerprint": token.lineage_fingerprint,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hmac.new(_HANDOFF_MAC_KEY, payload, sha256).hexdigest()
