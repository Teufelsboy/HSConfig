from __future__ import annotations

import json
import hmac
from secrets import token_bytes, token_hex
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal
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
_DOCUMENT_SPLIT = "document_split"
_CONSUMED_DOCUMENT = "consumed_document"
_SOURCE_AUTOPILOT_CONSUMER = "source_autopilot"
_SPLIT_CONSUMER = "split"
_DOCUMENT_CONSUMERS = ("research", "prepare")
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
    consumer: str = ""


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
    consumer: str
    mac: str


def reject_caller_supplied_source_authority(args: Any) -> None:
    for attribute in _CALLER_AUTHORITY_ATTRIBUTES:
        if getattr(args, attribute, None) is not None:
            raise ValueError(f"caller_supplied_{attribute}_not_allowed")


def _issue_acquired_search_records_handoff(
    records: list[dict[str, Any]],
) -> InternalSourceAuthorityHandoff:
    copied_records = tuple(
        _safe_deepcopy(
            records,
            failure_reason="source_authority_payload_copy_failed",
        )
    )
    record_fingerprint = _payload_fingerprint(copied_records)
    lineage_fingerprint = _lineage_fingerprint(record_fingerprint, "")
    token = _prepare_authority_token(
        state=_ACTIVE_SEARCH,
        record_fingerprint=record_fingerprint,
        document_fingerprint="",
        lineage_fingerprint=lineage_fingerprint,
        consumer=_SOURCE_AUTOPILOT_CONSUMER,
    )
    handoff = InternalSourceAuthorityHandoff(
        stage=_SEARCH_RECORDS_STAGE,
        record_fingerprint=record_fingerprint,
        document_fingerprint="",
        lineage_fingerprint=lineage_fingerprint,
        search_records=copied_records,
        source_documents=(),
        _token=token,
        consumer=_SOURCE_AUTOPILOT_CONSUMER,
    )
    _register_authority_token(token)
    return handoff


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
    if (
        handoff.consumer != _SOURCE_AUTOPILOT_CONSUMER
        or token.consumer != _SOURCE_AUTOPILOT_CONSUMER
    ):
        raise ValueError("source_authority_consumer_mismatch")
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
    copied_records = _safe_deepcopy(
        list(handoff.search_records),
        failure_reason="source_authority_payload_copy_failed",
    )
    lineage = _ConsumedSearchLineage(
        record_fingerprint=registered_fingerprint,
        search_records=handoff.search_records,
        _token=token,
    )
    consumed_mac = _authority_token_mac(token, state=_CONSUMED_SEARCH)

    _ACTIVE_ORIGINAL_TOKENS.pop(token.nonce)
    _commit_token_state(token, state=_CONSUMED_SEARCH, mac=consumed_mac)
    return copied_records, lineage


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
    copied_documents = tuple(
        _safe_deepcopy(
            documents,
            failure_reason="source_authority_payload_copy_failed",
        )
    )
    document_fingerprint = _payload_fingerprint(
        copied_documents,
        failure_reason="source_authority_handoff_lineage_mismatch",
    )
    lineage_fingerprint = _lineage_fingerprint(
        registered_fingerprint,
        document_fingerprint,
    )
    document_token = _prepare_authority_token(
        state=_ACTIVE_DOCUMENT,
        record_fingerprint=registered_fingerprint,
        document_fingerprint=document_fingerprint,
        lineage_fingerprint=lineage_fingerprint,
        consumer=_SPLIT_CONSUMER,
    )
    handoff = InternalSourceAuthorityHandoff(
        stage=_SOURCE_DOCUMENTS_STAGE,
        record_fingerprint=registered_fingerprint,
        document_fingerprint=document_fingerprint,
        lineage_fingerprint=lineage_fingerprint,
        search_records=lineage.search_records,
        source_documents=copied_documents,
        _token=document_token,
        consumer=_SPLIT_CONSUMER,
    )
    issued_mac = _authority_token_mac(token, state=_DOCUMENT_ISSUED)

    _commit_token_state(token, state=_DOCUMENT_ISSUED, mac=issued_mac)
    _register_authority_token(document_token)
    return handoff


def split_source_documents_handoff(
    handoff: InternalSourceAuthorityHandoff,
) -> tuple[InternalSourceAuthorityHandoff, InternalSourceAuthorityHandoff]:
    """Consume one document capability and issue research/prepare capabilities."""

    _require_handoff_type_and_stage(handoff, stage=_SOURCE_DOCUMENTS_STAGE)
    token = _validated_authority_token(handoff._token)
    if token.state == _DOCUMENT_SPLIT:
        raise ValueError("source_authority_handoff_replayed")
    if token.state != _ACTIVE_DOCUMENT:
        raise ValueError("invalid_internal_source_authority_handoff")
    if _ACTIVE_ORIGINAL_TOKENS.get(token.nonce) is not token:
        raise ValueError("invalid_internal_source_authority_handoff")
    if handoff.consumer != _SPLIT_CONSUMER or token.consumer != _SPLIT_CONSUMER:
        raise ValueError("source_authority_consumer_mismatch")
    (
        record_fingerprint,
        document_fingerprint,
        lineage_fingerprint,
    ) = _validated_document_handoff_fingerprints(handoff, token)

    successor_handoffs: list[InternalSourceAuthorityHandoff] = []
    prepared_tokens: list[_AuthorityToken] = []
    for consumer in _DOCUMENT_CONSUMERS:
        copied_search_records = tuple(
            _safe_deepcopy(
                list(handoff.search_records),
                failure_reason="source_authority_payload_copy_failed",
            )
        )
        copied_source_documents = tuple(
            _safe_deepcopy(
                list(handoff.source_documents),
                failure_reason="source_authority_payload_copy_failed",
            )
        )
        if (
            _payload_fingerprint(
                copied_search_records,
                failure_reason="source_authority_handoff_lineage_mismatch",
            )
            != record_fingerprint
            or _payload_fingerprint(
                copied_source_documents,
                failure_reason="source_authority_handoff_lineage_mismatch",
            )
            != document_fingerprint
            or _lineage_fingerprint(record_fingerprint, document_fingerprint)
            != lineage_fingerprint
        ):
            raise ValueError("source_authority_handoff_lineage_mismatch")
        successor_token = _prepare_authority_token(
            state=_ACTIVE_DOCUMENT,
            record_fingerprint=record_fingerprint,
            document_fingerprint=document_fingerprint,
            lineage_fingerprint=lineage_fingerprint,
            consumer=consumer,
        )
        prepared_tokens.append(successor_token)
        successor_handoffs.append(
            InternalSourceAuthorityHandoff(
                stage=_SOURCE_DOCUMENTS_STAGE,
                record_fingerprint=record_fingerprint,
                document_fingerprint=document_fingerprint,
                lineage_fingerprint=lineage_fingerprint,
                search_records=copied_search_records,
                source_documents=copied_source_documents,
                _token=successor_token,
                consumer=consumer,
            )
        )
    split_mac = _authority_token_mac(token, state=_DOCUMENT_SPLIT)

    _ACTIVE_ORIGINAL_TOKENS.pop(token.nonce)
    _commit_token_state(token, state=_DOCUMENT_SPLIT, mac=split_mac)
    for successor_token in prepared_tokens:
        _register_authority_token(successor_token)
    return successor_handoffs[0], successor_handoffs[1]


def trusted_source_documents_from_handoff(
    handoff: InternalSourceAuthorityHandoff | None,
    *,
    consumer: Literal["research", "prepare"],
) -> list[dict[str, Any]] | None:
    """Validate and consume the capability for exactly one named consumer."""

    if handoff is None:
        return None
    _require_handoff_type_and_stage(handoff, stage=_SOURCE_DOCUMENTS_STAGE)
    token = _validated_authority_token(handoff._token)
    if token.state == _CONSUMED_DOCUMENT:
        raise ValueError("source_authority_handoff_replayed")
    if token.state != _ACTIVE_DOCUMENT:
        raise ValueError("invalid_internal_source_authority_handoff")
    if _ACTIVE_ORIGINAL_TOKENS.get(token.nonce) is not token:
        raise ValueError("invalid_internal_source_authority_handoff")
    if (
        consumer not in _DOCUMENT_CONSUMERS
        or handoff.consumer != consumer
        or token.consumer != consumer
    ):
        raise ValueError("source_authority_consumer_mismatch")
    _validated_document_handoff_fingerprints(handoff, token)
    copied_documents = _safe_deepcopy(
        list(handoff.source_documents),
        failure_reason="source_authority_payload_copy_failed",
    )
    consumed_mac = _authority_token_mac(token, state=_CONSUMED_DOCUMENT)

    _ACTIVE_ORIGINAL_TOKENS.pop(token.nonce)
    _commit_token_state(token, state=_CONSUMED_DOCUMENT, mac=consumed_mac)
    return copied_documents


def _validated_document_handoff_fingerprints(
    handoff: InternalSourceAuthorityHandoff,
    token: _AuthorityToken,
) -> tuple[str, str, str]:
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
    return record_fingerprint, document_fingerprint, lineage_fingerprint


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


def _safe_deepcopy(payload: Any, *, failure_reason: str) -> Any:
    try:
        return deepcopy(payload)
    except Exception as exc:
        raise ValueError(failure_reason) from exc


def _prepare_authority_token(
    *,
    state: str,
    record_fingerprint: str,
    document_fingerprint: str,
    lineage_fingerprint: str,
    consumer: str,
) -> _AuthorityToken:
    """Construct and sign without registering or mutating predecessor state."""

    token = _AuthorityToken(
        nonce=token_hex(16),
        state=state,
        record_fingerprint=record_fingerprint,
        document_fingerprint=document_fingerprint,
        lineage_fingerprint=lineage_fingerprint,
        consumer=consumer,
        mac="",
    )
    token.mac = _authority_token_mac(token)
    return token


def _register_authority_token(token: _AuthorityToken) -> None:
    _ACTIVE_ORIGINAL_TOKENS[token.nonce] = token


def _validated_authority_token(value: Any) -> _AuthorityToken:
    if not isinstance(value, _AuthorityToken):
        raise ValueError("invalid_internal_source_authority_handoff")
    expected_mac = _authority_token_mac(value)
    if not hmac.compare_digest(value.mac, expected_mac):
        raise ValueError("invalid_internal_source_authority_handoff")
    return value


def _commit_token_state(token: _AuthorityToken, *, state: str, mac: str) -> None:
    token.state = state
    token.mac = mac


def _authority_token_mac(
    token: _AuthorityToken,
    *,
    state: str | None = None,
) -> str:
    payload = json.dumps(
        {
            "nonce": token.nonce,
            "state": token.state if state is None else state,
            "record_fingerprint": token.record_fingerprint,
            "document_fingerprint": token.document_fingerprint,
            "lineage_fingerprint": token.lineage_fingerprint,
            "consumer": token.consumer,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hmac.new(_HANDOFF_MAC_KEY, payload, sha256).hexdigest()
