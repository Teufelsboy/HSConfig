"""Immutable, fail-closed source-acquisition completion records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
import json
import re
from typing import Any, Literal

from hsconfig.package_domain import PolicyProfile
from hsconfig.source_acquisition_provenance import (
    acquisition_provenance_is_canonical,
)


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_EVIDENCE_ID_RE = re.compile(r"evidence:[0-9a-f]{64}\Z")
_RAW_DECK_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9+/])AAE[A-Za-z0-9+/]{21,}={0,2}(?![A-Za-z0-9+/=])"
)
_HTTPS_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\(?:[?.]\\|[^\\/\s]+[\\/]))"
)
_POSIX_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w])/(?![ /\t\r\n])")
_SUCCESS_OUTCOMES = frozenset({"acquired", "success", "succeeded"})


@dataclass(frozen=True, slots=True)
class AcquisitionFailure:
    source_identity: str
    reason_code: str
    attempted_at: str


@dataclass(frozen=True, slots=True)
class AcquisitionClosure:
    deck_fingerprint: str
    attempt_id: str
    attempted_at: str
    attempted_urls: tuple[str, ...]
    successful_evidence_ids: tuple[str, ...]
    failed_attempts: tuple[AcquisitionFailure, ...]
    negative_search_documented: bool
    checked_dossier: bool
    policy_id: str | None
    status: Literal["closed_with_evidence", "closed_negative_search", "open"]
    content_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempted_urls", tuple(self.attempted_urls))
        object.__setattr__(
            self,
            "successful_evidence_ids",
            tuple(self.successful_evidence_ids),
        )
        object.__setattr__(self, "failed_attempts", tuple(self.failed_attempts))


def build_acquisition_closure(
    *,
    deck_identity: Mapping[str, Any],
    research_manifest: Mapping[str, Any],
    acquisition_report: Mapping[str, Any],
    source_records: Sequence[Mapping[str, Any]],
    policy_profile: PolicyProfile,
) -> AcquisitionClosure:
    """Derive one immutable closure without accepting caller-declared closure flags."""

    policy_id, policy_sha256, policy_version, policy_effective_date = _policy_binding(
        policy_profile
    )
    deck_fingerprint = _text(deck_identity.get("deck_fingerprint"))
    attempt_id = _text(acquisition_report.get("attempt_id"))
    attempted_at = _normalized_date(acquisition_report.get("attempted_at"))
    attempted_urls = _stable_strings(acquisition_report.get("attempted_urls"))
    attempts = _attempt_rows(acquisition_report.get("attempts"))
    reported_successful_evidence_ids = _successful_evidence_ids(attempts)
    failed_attempts = _failed_attempts(attempts, attempted_at=attempted_at)

    manifest_date = _normalized_date(research_manifest.get("research_date"))
    attempted_queries = _stable_strings(research_manifest.get("attempted_queries"))
    attempt_id_matches = (
        bool(attempt_id)
        and attempt_id == _text(research_manifest.get("attempt_id"))
    )
    deck_matches = (
        bool(deck_fingerprint)
        and deck_fingerprint
        == _text(research_manifest.get("deck_fingerprint"))
        == _text(acquisition_report.get("deck_fingerprint"))
    )
    deck_name = _text(deck_identity.get("deck_name"))
    deck_name_matches = (
        bool(deck_name)
        and deck_name == _text(research_manifest.get("deck_name"))
        == _text(acquisition_report.get("deck_name"))
    )
    date_matches = bool(attempted_at) and attempted_at == manifest_date
    expected_policy = policy_provenance_payload(policy_profile)
    policy_matches = (
        bool(policy_id)
        and _text(research_manifest.get("policy_id")) == policy_id
        and _text(acquisition_report.get("policy_id")) == policy_id
        and _text(research_manifest.get("policy_sha256")) == policy_sha256
        and _text(acquisition_report.get("policy_sha256")) == policy_sha256
        and _policy_provenance_matches(
            research_manifest.get("policy"),
            expected_policy,
        )
        and _policy_provenance_matches(
            acquisition_report.get("policy"),
            expected_policy,
        )
    )
    checked_dossier = (
        research_manifest.get("checked_dossier") is True
        and acquisition_report.get("checked_dossier") is True
    )
    recorded_attempts = _attempts_cover_urls(attempted_urls, attempts)
    attempt_dates_match = all(
        "attempted_at" not in row
        or _normalized_date(row.get("attempted_at")) == attempted_at
        for row in attempts
    )
    structural_closure = all(
        (
            deck_matches,
            deck_name_matches,
            date_matches,
            attempt_id_matches,
            bool(attempted_queries),
            bool(attempted_urls),
            recorded_attempts,
            attempt_dates_match,
            checked_dossier,
            policy_matches,
        )
    )

    (
        record_evidence_ids,
        record_evidence_bindings,
        records_are_bound,
    ) = _record_evidence_bindings(source_records)
    success_is_bound = (
        bool(reported_successful_evidence_ids)
        and records_are_bound
        and record_evidence_ids == reported_successful_evidence_ids
        and record_evidence_bindings == _successful_evidence_bindings(attempts)
    )
    successful_evidence_ids = (
        reported_successful_evidence_ids if success_is_bound else ()
    )
    all_attempts_failed_with_reasons = (
        bool(attempts)
        and not reported_successful_evidence_ids
        and len(failed_attempts) == len(attempts)
        and all(failure.reason_code for failure in failed_attempts)
    )
    if structural_closure and success_is_bound:
        status: Literal[
            "closed_with_evidence", "closed_negative_search", "open"
        ] = "closed_with_evidence"
    elif (
        structural_closure
        and all_attempts_failed_with_reasons
        and not source_records
    ):
        status = "closed_negative_search"
    else:
        status = "open"

    closure_payload = {
        "deck_fingerprint": deck_fingerprint,
        "attempt_id": attempt_id,
        "attempted_at": attempted_at,
        "attempted_urls": list(attempted_urls),
        "successful_evidence_ids": list(successful_evidence_ids),
        "failed_attempts": [asdict(row) for row in failed_attempts],
        "negative_search_documented": status == "closed_negative_search",
        "checked_dossier": checked_dossier,
        "policy_id": policy_id or None,
        "status": status,
        "policy_sha256": policy_sha256,
        "policy_version": policy_version,
        "policy_effective_date": policy_effective_date,
    }
    return AcquisitionClosure(
        deck_fingerprint=deck_fingerprint,
        attempt_id=attempt_id,
        attempted_at=attempted_at,
        attempted_urls=attempted_urls,
        successful_evidence_ids=successful_evidence_ids,
        failed_attempts=failed_attempts,
        negative_search_documented=status == "closed_negative_search",
        checked_dossier=checked_dossier,
        policy_id=policy_id or None,
        status=status,
        content_sha256=_content_digest(closure_payload),
    )


def freeze_source_bundle(
    *,
    deck_identity: Mapping[str, Any],
    closure: AcquisitionClosure,
    source_records: Sequence[Mapping[str, Any]],
    policy_profile: PolicyProfile | Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze only closed, fully bound claim projections into a portable bundle."""

    policy_id, policy_sha256, policy_version, effective_date = _policy_binding(
        policy_profile
    )
    deck_fingerprint = _text(deck_identity.get("deck_fingerprint"))
    if closure.status == "open":
        raise ValueError("acquisition_closure_open")
    if (
        not deck_fingerprint
        or deck_fingerprint != closure.deck_fingerprint
        or closure.policy_id != policy_id
        or closure.content_sha256
        != _closure_content_digest(
            closure,
            policy_sha256=policy_sha256,
            policy_version=policy_version,
            policy_effective_date=effective_date,
        )
    ):
        raise ValueError("source_bundle_closure_binding_mismatch")

    sources = _frozen_sources(source_records)
    claims = _frozen_claims(source_records)
    evidence_ids = tuple(
        sorted({str(source["evidence_id"]) for source in sources})
    )
    if closure.status == "closed_negative_search":
        if sources or claims or source_records or closure.successful_evidence_ids:
            raise ValueError("negative_source_bundle_contains_evidence")
    elif (
        not sources
        or evidence_ids != closure.successful_evidence_ids
    ):
        raise ValueError("source_bundle_evidence_binding_mismatch")

    payload: dict[str, Any] = {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "deck": {
            "name": _text(deck_identity.get("deck_name")),
            "fingerprint": deck_fingerprint,
        },
        "policy": {
            "policy_id": policy_id,
            "version": policy_version,
            "effective_date": effective_date,
            "content_sha256": policy_sha256,
        },
        "acquisition_closure": _closure_payload(closure),
        "sources": sources,
        "claims": claims,
    }
    if _contains_nonportable_string(payload):
        raise ValueError("source_bundle_not_portable")
    payload["content_sha256"] = _content_digest(payload)
    return payload


def acquisition_closure_payload(closure: AcquisitionClosure) -> dict[str, Any]:
    """Return the deterministic JSON projection for command/report integration."""

    return _closure_payload(closure)


def normalize_acquisition_date(value: Any) -> str:
    """Normalize a date or ISO timestamp to the canonical acquisition date."""

    return _normalized_date(value)


def acquisition_attempt_id(deck_fingerprint: str, attempted_at: Any) -> str:
    """Build the stable attempt identity shared by manifests and reports."""

    fingerprint = _text(deck_fingerprint)
    normalized_date = _normalized_date(attempted_at)
    if not fingerprint or not normalized_date:
        return ""
    digest = sha256(f"{fingerprint}\0{normalized_date}".encode("utf-8")).hexdigest()
    return f"acquisition:{digest}"


def source_evidence_id(source_identity: str, content_sha256: str) -> str:
    """Build the canonical typed identity for one acquired source payload."""

    identity = _text(source_identity)
    digest = _text(content_sha256)
    if not identity or _SHA256_RE.fullmatch(digest) is None:
        raise ValueError("source_evidence_binding_invalid")
    bound = sha256(f"{identity}\0{digest}".encode("utf-8")).hexdigest()
    return f"evidence:{bound}"


def policy_provenance_payload(
    policy_profile: PolicyProfile | Mapping[str, Any],
) -> dict[str, Any]:
    """Project the complete policy identity shared by source workflow artifacts."""

    policy_id, content_sha256, version, effective_date = _policy_binding(
        policy_profile
    )
    return {
        "policy_id": policy_id,
        "version": version,
        "effective_date": effective_date,
        "content_sha256": content_sha256,
    }


def _closure_payload(closure: AcquisitionClosure) -> dict[str, Any]:
    return {
        "deck_fingerprint": closure.deck_fingerprint,
        "attempt_id": closure.attempt_id,
        "attempted_at": closure.attempted_at,
        "attempted_urls": list(closure.attempted_urls),
        "successful_evidence_ids": list(closure.successful_evidence_ids),
        "failed_attempts": [asdict(row) for row in closure.failed_attempts],
        "negative_search_documented": closure.negative_search_documented,
        "checked_dossier": closure.checked_dossier,
        "policy_id": closure.policy_id,
        "status": closure.status,
        "content_sha256": closure.content_sha256,
    }


def _closure_content_digest(
    closure: AcquisitionClosure,
    *,
    policy_sha256: str,
    policy_version: int,
    policy_effective_date: str,
) -> str:
    payload = _closure_payload(closure)
    payload.pop("content_sha256")
    payload.update(
        {
            "policy_sha256": policy_sha256,
            "policy_version": policy_version,
            "policy_effective_date": policy_effective_date,
        }
    )
    return _content_digest(payload)


def _frozen_claims(
    source_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for record in source_records:
        record_evidence_id, record_is_bound = _record_evidence_binding(record)
        if not record_is_bound:
            raise ValueError("source_evidence_binding_incomplete")
        nested = record.get("claims")
        rows = (
            [row for row in nested if isinstance(row, Mapping)]
            if isinstance(nested, Sequence)
            and not isinstance(nested, (str, bytes, bytearray))
            else (
                [record]
                if _record_has_claim_signal(record)
                else []
            )
        )
        for row in rows:
            evidence_id = _first_text(row, record, keys=("evidence_id",))
            source_id = _first_text(
                row,
                record,
                keys=("source_id", "source_identity", "source_url"),
            )
            policy_id = _first_text(row, record, keys=("policy_id",))
            as_of_date = _normalized_date(
                _first_value(
                    row,
                    record,
                    keys=("as_of_date", "retrieved_at", "published_at"),
                )
            )
            claim_kind = _first_text(
                row,
                record,
                keys=("claim_kind", "claim_type"),
            )
            text = _first_text(
                row,
                record,
                keys=(
                    "claim_text",
                    "evidence_text_short",
                    "claim",
                    "text",
                    "normalized_text",
                ),
            )
            content_sha256 = _first_text(
                row,
                record,
                keys=("content_sha256",),
            )
            if not content_sha256:
                provenance = row.get("acquisition_provenance")
                if not isinstance(provenance, Mapping):
                    provenance = record.get("acquisition_provenance")
                if isinstance(provenance, Mapping):
                    content_sha256 = _text(provenance.get("content_sha256"))
            if not all(
                (
                    evidence_id,
                    evidence_id == record_evidence_id,
                    source_id or policy_id,
                    as_of_date,
                    claim_kind,
                    text,
                    _SHA256_RE.fullmatch(content_sha256),
                )
            ):
                raise ValueError("source_claim_binding_incomplete")
            claims.append(
                {
                    "evidence_id": evidence_id,
                    "source_id": source_id or None,
                    "policy_id": policy_id or None,
                    "as_of_date": as_of_date,
                    "claim_kind": claim_kind,
                    "text": text,
                    "content_sha256": content_sha256,
                }
            )
    return _canonicalized_rows(claims)


def _frozen_sources(
    source_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for record in source_records:
        evidence_id, record_is_bound = _record_evidence_binding(record)
        source_id = _first_text(
            record,
            record,
            keys=("source_id", "source_identity", "source_url"),
        )
        policy_id = _text(record.get("policy_id"))
        as_of_date = _normalized_date(
            _first_value(
                record,
                record,
                keys=("as_of_date", "retrieved_at", "published_at"),
            )
        )
        content_sha256 = _text(record.get("content_sha256"))
        if not content_sha256:
            provenance = record.get("acquisition_provenance")
            if isinstance(provenance, Mapping):
                content_sha256 = _text(provenance.get("content_sha256"))
        if not all(
            (
                evidence_id,
                record_is_bound,
                source_id or policy_id,
                as_of_date,
                _SHA256_RE.fullmatch(content_sha256),
            )
        ):
            raise ValueError("source_evidence_binding_incomplete")
        sources.append(
            {
                "evidence_id": evidence_id,
                "source_id": source_id or None,
                "policy_id": policy_id or None,
                "as_of_date": as_of_date,
                "content_sha256": content_sha256,
            }
        )
    return _canonicalized_rows(sources)


def _record_has_claim_signal(record: Mapping[str, Any]) -> bool:
    return any(
        _text(record.get(key))
        for key in (
            "claim_kind",
            "claim_type",
            "claim_text",
            "evidence_text_short",
            "claim",
            "text",
        )
    )


def _attempt_rows(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        return ()
    return tuple(row for row in value if isinstance(row, Mapping))


def _attempts_cover_urls(
    attempted_urls: tuple[str, ...],
    attempts: tuple[Mapping[str, Any], ...],
) -> bool:
    identities = tuple(
        sorted(_text(row.get("source_identity")) for row in attempts)
    )
    return (
        bool(attempts)
        and all(
            _text(row.get("source_identity"))
            and _text(row.get("outcome"))
            for row in attempts
        )
        and identities == attempted_urls
    )


def _successful_evidence_ids(
    attempts: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    ids: list[str] = []
    for attempt in attempts:
        if _text(attempt.get("outcome")).lower() not in _SUCCESS_OUTCOMES:
            continue
        evidence_id = _text(attempt.get("evidence_id"))
        if _EVIDENCE_ID_RE.fullmatch(evidence_id):
            ids.append(evidence_id)
    return tuple(sorted(set(ids)))


def _successful_evidence_bindings(
    attempts: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, str], ...]:
    bindings: list[tuple[str, str]] = []
    for attempt in attempts:
        if _text(attempt.get("outcome")).lower() not in _SUCCESS_OUTCOMES:
            continue
        evidence_id = _text(attempt.get("evidence_id"))
        source_identity = _text(attempt.get("source_identity"))
        if (
            _EVIDENCE_ID_RE.fullmatch(evidence_id) is None
            or not source_identity
        ):
            return ()
        bindings.append((evidence_id, source_identity))
    return tuple(sorted(set(bindings)))


def _failed_attempts(
    attempts: Sequence[Mapping[str, Any]],
    *,
    attempted_at: str,
) -> tuple[AcquisitionFailure, ...]:
    failures = [
        AcquisitionFailure(
            source_identity=_text(row.get("source_identity")),
            reason_code=_text(row.get("reason_code")),
            attempted_at=(
                _normalized_date(row.get("attempted_at")) or attempted_at
            ),
        )
        for row in attempts
        if _text(row.get("outcome")).lower() not in _SUCCESS_OUTCOMES
    ]
    return tuple(
        sorted(
            failures,
            key=lambda row: (
                row.source_identity,
                row.reason_code,
                row.attempted_at,
            ),
        )
    )


def _record_evidence_bindings(
    source_records: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...], bool]:
    if not source_records:
        return (), (), True
    evidence_ids: list[str] = []
    bindings: list[tuple[str, str]] = []
    for record in source_records:
        evidence_id, is_bound = _record_evidence_binding(record)
        source_identity = _text(record.get("source_identity"))
        if not is_bound:
            return (), (), False
        evidence_ids.append(evidence_id)
        bindings.append((evidence_id, source_identity))
    return (
        tuple(sorted(set(evidence_ids))),
        tuple(sorted(set(bindings))),
        True,
    )


def _record_evidence_binding(
    record: Mapping[str, Any],
) -> tuple[str, bool]:
    evidence_id = _text(record.get("evidence_id"))
    source_identity = _text(record.get("source_identity"))
    content_sha256 = _text(record.get("content_sha256"))
    provenance = record.get("acquisition_provenance")
    if (
        _EVIDENCE_ID_RE.fullmatch(evidence_id) is None
        or not source_identity
        or _SHA256_RE.fullmatch(content_sha256) is None
        or not acquisition_provenance_is_canonical(provenance)
        or _text(provenance.get("content_sha256")) != content_sha256
    ):
        return "", False
    return (
        evidence_id,
        evidence_id == source_evidence_id(source_identity, content_sha256),
    )


def _stable_strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        return ()
    return tuple(sorted({_text(item) for item in value if _text(item)}))


def _normalized_date(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    text = _text(value)
    if len(text) < 10:
        return ""
    candidate = text[:10]
    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        return ""
    return parsed.isoformat() if parsed.isoformat() == candidate else ""


def _policy_binding(
    policy_profile: PolicyProfile | Mapping[str, Any],
) -> tuple[str, str, int, str]:
    if isinstance(policy_profile, PolicyProfile):
        policy_id = policy_profile.policy_id
        content_sha256 = policy_profile.content_sha256
        version = policy_profile.version
        effective_date = policy_profile.effective_date
    elif isinstance(policy_profile, Mapping):
        policy_id = _text(policy_profile.get("policy_id"))
        content_sha256 = _text(policy_profile.get("content_sha256"))
        version = policy_profile.get("version")
        effective_date = _text(policy_profile.get("effective_date"))
    else:
        raise TypeError("policy_profile_required")
    if (
        not policy_id
        or _SHA256_RE.fullmatch(content_sha256) is None
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
        or _normalized_date(effective_date) != effective_date
    ):
        raise ValueError("policy_profile_binding_invalid")
    return policy_id, content_sha256, version, effective_date


def _policy_provenance_matches(
    value: Any,
    expected: Mapping[str, Any],
) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == set(expected)
        and type(value.get("version")) is int
        and all(value.get(key) == expected[key] for key in expected)
    )


def _canonicalized_rows(
    rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    keyed = {_canonical_json(row): row for row in rows}
    return [keyed[key] for key in sorted(keyed)]


def _contains_nonportable_string(value: Any) -> bool:
    if isinstance(value, str):
        if _RAW_DECK_CODE_RE.search(value):
            return True
        without_urls = _HTTPS_URL_RE.sub("", value)
        return (
            _WINDOWS_ABSOLUTE_PATH_RE.search(without_urls) is not None
            or _POSIX_ABSOLUTE_PATH_RE.search(without_urls) is not None
        )
    if isinstance(value, Mapping):
        return any(
            _contains_nonportable_string(key)
            or _contains_nonportable_string(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(
        value,
        (bytes, bytearray),
    ):
        return any(_contains_nonportable_string(item) for item in value)
    return False


def _first_value(
    row: Mapping[str, Any],
    record: Mapping[str, Any],
    *,
    keys: Sequence[str],
) -> Any:
    for container in (row, record):
        for key in keys:
            value = container.get(key)
            if value is not None:
                return value
    return None


def _first_text(
    row: Mapping[str, Any],
    record: Mapping[str, Any],
    *,
    keys: Sequence[str],
) -> str:
    return _text(_first_value(row, record, keys=keys))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_digest(payload: Mapping[str, Any]) -> str:
    return f"sha256:{sha256(_canonical_json(payload)).hexdigest()}"
