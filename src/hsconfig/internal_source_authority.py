from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


_HANDOFF_TOKEN = object()
_SEARCH_RECORDS_STAGE = "verified_search_records"
_SOURCE_DOCUMENTS_STAGE = "verified_source_documents"
_CALLER_AUTHORITY_ATTRIBUTES = (
    "trusted_source_documents",
    "trusted_source_search_records",
)


@dataclass(frozen=True, slots=True)
class InternalSourceAuthorityHandoff:
    """Opaque in-process transport for source authority established by acquisition."""

    stage: str
    search_records: tuple[dict[str, Any], ...]
    source_documents: tuple[dict[str, Any], ...]
    _token: object


def reject_caller_supplied_source_authority(args: Any) -> None:
    for attribute in _CALLER_AUTHORITY_ATTRIBUTES:
        if getattr(args, attribute, None) is not None:
            raise ValueError(f"caller_supplied_{attribute}_not_allowed")


def _issue_acquired_search_records_handoff(
    records: list[dict[str, Any]],
) -> InternalSourceAuthorityHandoff:
    return InternalSourceAuthorityHandoff(
        stage=_SEARCH_RECORDS_STAGE,
        search_records=tuple(deepcopy(records)),
        source_documents=(),
        _token=_HANDOFF_TOKEN,
    )


def advance_to_source_documents_handoff(
    handoff: InternalSourceAuthorityHandoff,
    documents: list[dict[str, Any]],
) -> InternalSourceAuthorityHandoff:
    _require_handoff(handoff, stage=_SEARCH_RECORDS_STAGE)
    return InternalSourceAuthorityHandoff(
        stage=_SOURCE_DOCUMENTS_STAGE,
        search_records=handoff.search_records,
        source_documents=tuple(deepcopy(documents)),
        _token=_HANDOFF_TOKEN,
    )


def trusted_search_records_from_handoff(
    handoff: InternalSourceAuthorityHandoff,
) -> list[dict[str, Any]]:
    _require_handoff(handoff, stage=_SEARCH_RECORDS_STAGE)
    return deepcopy(list(handoff.search_records))


def trusted_source_documents_from_handoff(
    handoff: InternalSourceAuthorityHandoff | None,
) -> list[dict[str, Any]] | None:
    if handoff is None:
        return None
    _require_handoff(handoff, stage=_SOURCE_DOCUMENTS_STAGE)
    return deepcopy(list(handoff.source_documents))


def _require_handoff(
    handoff: InternalSourceAuthorityHandoff,
    *,
    stage: str,
) -> None:
    if (
        not isinstance(handoff, InternalSourceAuthorityHandoff)
        or handoff._token is not _HANDOFF_TOKEN
        or handoff.stage != stage
    ):
        raise ValueError("invalid_internal_source_authority_handoff")
