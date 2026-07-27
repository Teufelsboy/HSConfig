from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_DECIMAL_INTEGER = re.compile(r"^[0-9]+$")
MAX_EXACT_SOURCE_CANDIDATES = 256
MAX_EXACT_SOURCE_COUNT_DIGITS = len(str(MAX_EXACT_SOURCE_CANDIDATES))


class ExactEvidenceError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def parse_exact_source_count(value: Any) -> int:
    """Parse one bounded exact-source count without unbounded integer conversion."""
    if isinstance(value, bool):
        raise ExactEvidenceError("exact_evidence_count_invalid")
    if isinstance(value, int):
        if value < 0:
            raise ExactEvidenceError("exact_evidence_count_invalid")
        if value > MAX_EXACT_SOURCE_CANDIDATES:
            raise ExactEvidenceError("exact_evidence_count_out_of_range")
        return value
    if not isinstance(value, str):
        raise ExactEvidenceError("exact_evidence_count_invalid")
    if value != value.strip() or not _DECIMAL_INTEGER.fullmatch(value):
        raise ExactEvidenceError("exact_evidence_count_invalid")
    if len(value) > MAX_EXACT_SOURCE_COUNT_DIGITS:
        raise ExactEvidenceError("exact_evidence_count_out_of_range")
    count = int(value)
    if count > MAX_EXACT_SOURCE_CANDIDATES:
        raise ExactEvidenceError("exact_evidence_count_out_of_range")
    return count


def parse_strict_nonnegative_int(value: Any) -> int | None:
    """Parse the supported exact-evidence count forms without coercing types."""
    try:
        return parse_exact_source_count(value)
    except ExactEvidenceError:
        return None


def validate_exact_source_cardinality(
    *,
    candidate_count: int,
    decoded_candidate_count: int,
    candidate_hashes: list[str],
) -> list[str]:
    """Return stable canonical hashes or reject inconsistent exact evidence."""
    if (
        candidate_count < 1
        or decoded_candidate_count < 1
        or decoded_candidate_count > candidate_count
        or len(candidate_hashes) != candidate_count
        or len(set(candidate_hashes)) != len(candidate_hashes)
    ):
        raise ExactEvidenceError("exact_evidence_cardinality_mismatch")
    return sorted(candidate_hashes)


def canonical_exact_deck_evidence(
    exact_evidence: Any,
    *,
    target_fingerprint: Any,
) -> dict[str, Any]:
    """Return complete canonical exact-deck evidence or an empty mapping."""
    if not isinstance(exact_evidence, Mapping):
        return {}
    if exact_evidence.get("matched") is not True:
        return {}

    target = _clean_text(target_fingerprint)
    observed = _clean_text(
        exact_evidence.get("matched_deck_fingerprint", "")
    )
    if not target or not observed or observed != target:
        return {}

    try:
        candidate_count = parse_exact_source_count(
            exact_evidence.get("candidate_count")
        )
        decoded_candidate_count = parse_exact_source_count(
            exact_evidence.get("decoded_candidate_count")
        )
    except ExactEvidenceError:
        return {}
    candidate_hashes = _candidate_hashes(
        exact_evidence.get("candidate_deck_code_hashes")
    )
    if candidate_hashes is None:
        return {}
    try:
        hashes = validate_exact_source_cardinality(
            candidate_count=candidate_count,
            decoded_candidate_count=decoded_candidate_count,
            candidate_hashes=candidate_hashes,
        )
    except ExactEvidenceError:
        return {}

    return {
        "candidate_count": candidate_count,
        "decoded_candidate_count": decoded_candidate_count,
        "matched": True,
        "matched_deck_fingerprint": target,
        "candidate_deck_code_hashes": hashes,
    }


def exact_deck_evidence_parts(
    claim_or_document: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    deck_match = claim_or_document.get("deck_match")
    if not isinstance(deck_match, Mapping):
        return None, None
    exact = deck_match.get("exact_deck_evidence")
    if not isinstance(exact, Mapping):
        return deck_match, None
    return deck_match, exact


def exact_deck_evidence_is_complete(
    exact_evidence: Any,
    *,
    target_fingerprint: Any,
) -> bool:
    return bool(
        canonical_exact_deck_evidence(
            exact_evidence,
            target_fingerprint=target_fingerprint,
        )
    )


def _candidate_hashes(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    hashes: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        clean = item.strip()
        if not clean:
            return None
        hashes.append(clean)
    return hashes


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
