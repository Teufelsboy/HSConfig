from __future__ import annotations

import hashlib
from collections.abc import Mapping
import re
from typing import Any


LIVE_HTTP = "live_http"
CAPTURED_RECORD = "captured_record"
MANUAL_EVIDENCE = "manual_evidence"
FIXTURE_MAP = "fixture_map"
LEGACY_CLAIMS_JSON = "legacy_claims_json"

LIVE_VERIFIED = "live_verified"
CAPTURED_UNVERIFIED = "captured_unverified"
MANUAL_UNVERIFIED = "manual_unverified"
FIXTURE_ONLY = "fixture_only"
LEGACY_UNVERIFIED = "legacy_unverified"
STRATEGIC_PROVENANCE_NOT_LIVE_VERIFIED = (
    "strategic_provenance_not_live_verified"
)

_AUTHORITY_BY_MODE = {
    LIVE_HTTP: LIVE_VERIFIED,
    CAPTURED_RECORD: CAPTURED_UNVERIFIED,
    MANUAL_EVIDENCE: MANUAL_UNVERIFIED,
    FIXTURE_MAP: FIXTURE_ONLY,
    LEGACY_CLAIMS_JSON: LEGACY_UNVERIFIED,
}
_CANONICAL_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def build_acquisition_provenance(
    *,
    mode: str,
    content: bytes | str,
) -> dict[str, str]:
    try:
        authority = _AUTHORITY_BY_MODE[mode]
    except KeyError as exc:
        raise ValueError(f"unknown acquisition provenance mode: {mode}") from exc
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    return {
        "mode": mode,
        "content_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        "authority": authority,
    }


def acquisition_provenance_is_canonical(
    value: Any,
    *,
    mode: str | None = None,
) -> bool:
    if not isinstance(value, Mapping):
        return False
    observed_mode = value.get("mode")
    if observed_mode not in _AUTHORITY_BY_MODE:
        return False
    if mode is not None and observed_mode != mode:
        return False
    return (
        value.get("authority") == _AUTHORITY_BY_MODE[observed_mode]
        and isinstance(value.get("content_sha256"), str)
        and _CANONICAL_DIGEST_RE.fullmatch(value["content_sha256"]) is not None
    )


def strategic_source_provenance_is_verified(value: Any) -> bool:
    return (
        acquisition_provenance_is_canonical(value, mode=LIVE_HTTP)
        and value.get("authority") == LIVE_VERIFIED
    )
