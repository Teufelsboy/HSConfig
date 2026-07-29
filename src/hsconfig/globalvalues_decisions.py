"""Typed, exact GlobalValues decisions for the production pre-run contract."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any

from hsconfig.compile_globalvalues import (
    apply_globalvalues_overlay_operation,
    validated_globalvalues_authority_rows,
)
from hsconfig.globalvalues_baseline import FALLBACK_GLOBALVALUES_BASELINE
from hsconfig.package_domain import (
    GlobalValueDecision,
    GlobalValueDecisionKind,
    GlobalValuesDecisionLedger,
    globalvalues_decision_ledger_content_sha256,
)


GLOBALVALUES_BASELINE_DECISION_KEYS = tuple(FALLBACK_GLOBALVALUES_BASELINE)
_DECK_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}\Z")
_BASELINE_AUTHORITY_ID = "globalvalues:baseline"
_OVERLAY_AUTHORITY_ID = "step1_source_backed_posture"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_globalvalues_baseline_sha256(
    baseline: Mapping[str, Any],
) -> str:
    return f"sha256:{sha256(_canonical_bytes(dict(baseline))).hexdigest()}"


def normalize_globalvalues_decision_baseline(
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(baseline, Mapping):
        raise ValueError("globalvalues_baseline_must_be_object")
    frozen_input = deepcopy(dict(baseline))
    normalized = deepcopy(FALLBACK_GLOBALVALUES_BASELINE)
    for key in GLOBALVALUES_BASELINE_DECISION_KEYS:
        if key in frozen_input:
            normalized[key] = deepcopy(frozen_input[key])
    return normalized


def build_globalvalues_decision_ledger(
    *,
    deck_fingerprint: str,
    baseline: Mapping[str, Any],
    baseline_sha256: str,
    authority_matrix: Mapping[str, Any],
) -> GlobalValuesDecisionLedger:
    if (
        not isinstance(deck_fingerprint, str)
        or _DECK_FINGERPRINT_RE.fullmatch(deck_fingerprint) is None
    ):
        raise ValueError("globalvalues_deck_fingerprint_invalid")
    if not isinstance(baseline, Mapping):
        raise ValueError("globalvalues_baseline_must_be_object")
    if not isinstance(authority_matrix, Mapping):
        raise ValueError("globalvalues_authority_matrix_must_be_object")

    frozen_baseline = deepcopy(dict(baseline))
    frozen_matrix = deepcopy(dict(authority_matrix))
    if (
        len(frozen_baseline) != len(GLOBALVALUES_BASELINE_DECISION_KEYS)
        or set(frozen_baseline) != set(GLOBALVALUES_BASELINE_DECISION_KEYS)
    ):
        raise ValueError("globalvalues_baseline_keys_invalid")
    if baseline_sha256 != canonical_globalvalues_baseline_sha256(
        frozen_baseline
    ):
        raise ValueError("globalvalues_baseline_sha256_invalid")

    overlays = _validated_overlay_rows(frozen_matrix)
    decisions = tuple(
        _decision_for_key(
            deck_fingerprint=deck_fingerprint,
            key=key,
            baseline_value=frozen_baseline[key],
            overlay=overlays.get(key),
        )
        for key in GLOBALVALUES_BASELINE_DECISION_KEYS
    )
    return GlobalValuesDecisionLedger(
        deck_fingerprint=deck_fingerprint,
        baseline_sha256=baseline_sha256,
        decisions=decisions,
        content_sha256=globalvalues_decision_ledger_content_sha256(
            decisions
        ),
    )


def _validated_overlay_rows(
    authority_matrix: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    raw_rows = authority_matrix.get("allowed_step1_overlays")
    if not isinstance(raw_rows, list):
        raise ValueError(
            "globalvalues_authority_allowed_step1_overlays_must_be_list"
        )
    rows: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            raise ValueError(
                f"globalvalues_authority_overlay_row_must_be_object:{index}"
            )
        key = raw_row.get("key")
        if not isinstance(key, str) or not key or key != key.strip():
            raise ValueError(
                f"globalvalues_authority_overlay_key_invalid:{index}"
            )
        if key in seen:
            raise ValueError(
                f"globalvalues_authority_duplicate_overlay_key:{key}"
            )
        seen.add(key)
        rows.append(raw_row)

    sentinel_rows = [row for row in rows if row["key"] == "baseline"]
    if sentinel_rows and len(rows) != 1:
        raise ValueError("globalvalues_authority_baseline_sentinel_mixed")
    if sentinel_rows:
        validated_globalvalues_authority_rows(authority_matrix)
        return {}

    overlays: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["key"])
        if key not in GLOBALVALUES_BASELINE_DECISION_KEYS:
            raise ValueError(
                f"globalvalues_authority_overlay_key_not_baseline:{key}"
            )
        if "operation" not in row:
            raise ValueError(
                f"globalvalues_authority_overlay_operation_missing:{key}"
            )
        if "value" not in row:
            raise ValueError(
                f"globalvalues_authority_overlay_value_missing:{key}"
            )
        claim_id = row.get("claim_id")
        if (
            not isinstance(claim_id, str)
            or not claim_id
            or claim_id != claim_id.strip()
        ):
            raise ValueError(
                "globalvalues_authority_overlay_claim_authority_missing:"
                f"{key}"
            )
        if row.get("authority") != _OVERLAY_AUTHORITY_ID:
            raise ValueError(
                f"globalvalues_authority_overlay_authority_invalid:{key}"
            )
        reason = row.get("reason")
        if (
            not isinstance(reason, str)
            or not reason
            or reason != reason.strip()
        ):
            raise ValueError(
                f"globalvalues_authority_overlay_reason_invalid:{key}"
            )
        overlays[key] = dict(row)

    validated_globalvalues_authority_rows(authority_matrix)
    return overlays


def _decision_for_key(
    *,
    deck_fingerprint: str,
    key: str,
    baseline_value: Any,
    overlay: Mapping[str, Any] | None,
) -> GlobalValueDecision:
    baseline_canonical_json = _canonical_bytes(baseline_value)
    emitted_canonical_json = baseline_canonical_json
    if overlay is not None:
        emitted_canonical_json = _canonical_bytes(
            apply_globalvalues_overlay_operation(
                baseline_value,
                operation=str(overlay["operation"]),
                value=overlay["value"],
            )
        )

    if emitted_canonical_json == baseline_canonical_json:
        kind = GlobalValueDecisionKind.COPY_BASELINE
        authority_id = _BASELINE_AUTHORITY_ID
        claim_ids: tuple[str, ...] = ()
        reason = "copied canonical baseline"
    else:
        kind = GlobalValueDecisionKind.AUTHORIZED_OVERLAY
        authority_id = str(overlay["authority"])
        claim_ids = (str(overlay["claim_id"]),)
        reason = str(overlay["reason"])
    return GlobalValueDecision(
        deck_fingerprint=deck_fingerprint,
        key=key,
        kind=kind,
        baseline_canonical_json=baseline_canonical_json,
        emitted_canonical_json=emitted_canonical_json,
        authority_id=authority_id,
        claim_ids=claim_ids,
        reason=reason,
    )


def globalvalues_decision_ledger_document(
    ledger: GlobalValuesDecisionLedger,
) -> dict[str, Any]:
    return {
        "deck_fingerprint": ledger.deck_fingerprint,
        "baseline_sha256": ledger.baseline_sha256,
        "content_sha256": ledger.content_sha256,
        "decisions": [
            {
                "key": decision.key,
                "kind": decision.kind.value,
                "baseline": json.loads(decision.baseline_canonical_json),
                "emitted": json.loads(decision.emitted_canonical_json),
                "authority_id": decision.authority_id,
                "claim_ids": list(decision.claim_ids),
                "reason": decision.reason,
            }
            for decision in ledger.decisions
        ],
    }
