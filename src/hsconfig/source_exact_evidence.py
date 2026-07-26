from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_DECIMAL_INTEGER = re.compile(r"^[0-9]+$")


def parse_strict_nonnegative_int(value: Any) -> int | None:
    """Parse the supported exact-evidence count forms without coercing types."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not _DECIMAL_INTEGER.fullmatch(text):
            return None
        try:
            parsed = int(text)
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed >= 0 else None


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

    candidate_count = parse_strict_nonnegative_int(
        exact_evidence.get("candidate_count")
    )
    decoded_candidate_count = parse_strict_nonnegative_int(
        exact_evidence.get("decoded_candidate_count")
    )
    hashes = _canonical_hashes(
        exact_evidence.get("candidate_deck_code_hashes")
    )
    if (
        candidate_count is None
        or decoded_candidate_count is None
        or candidate_count < 1
        or decoded_candidate_count < 1
        or not hashes
    ):
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


def _canonical_hashes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    hashes: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return []
        clean = item.strip()
        if not clean:
            return []
        hashes.append(clean)
    return sorted(set(hashes))


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
