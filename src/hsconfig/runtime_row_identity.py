from __future__ import annotations

from collections import defaultdict
import json
from typing import Any, Iterable


RuntimeRowKey = tuple[str, str, str]
RuntimeRowSignature = tuple[str, str, str, str]


def runtime_row_key(
    card_id: Any,
    behavior_block: Any,
    row: dict[str, Any],
) -> RuntimeRowKey:
    return (
        str(card_id).strip(),
        str(behavior_block).strip(),
        str(row.get("condition", "*")).strip() or "*",
    )


def runtime_row_signature(
    card_id: Any,
    behavior_block: Any,
    row: dict[str, Any],
) -> RuntimeRowSignature:
    return (
        *runtime_row_key(card_id, behavior_block, row),
        str(row["value"]).strip(),
    )


def canonicalize_runtime_rows(
    rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    groups: dict[RuntimeRowKey, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        normalized = dict(row)
        key = runtime_row_key(
            normalized.get("card_id", ""),
            normalized.get("behavior_block", ""),
            normalized,
        )
        normalized["card_id"], normalized["behavior_block"], normalized["condition"] = key
        normalized["value"] = str(normalized["value"]).strip()
        groups[key].append(normalized)

    canonical_rows: list[dict[str, Any]] = []
    merged_duplicate_count = 0
    merged_provenance: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for key in sorted(groups):
        group = groups[key]
        values = sorted({str(row["value"]) for row in group})
        signature_groups: dict[RuntimeRowSignature, list[dict[str, Any]]] = defaultdict(list)
        for row in group:
            signature_groups[
                runtime_row_signature(row["card_id"], row["behavior_block"], row)
            ].append(row)
        merged_duplicate_count += sum(
            len(signature_rows) - 1
            for signature_rows in signature_groups.values()
        )

        if len(values) > 1:
            conflicts.append(
                {
                    "key": list(key),
                    "values": values,
                    "source_claim_ids": _merged_source_claim_ids(group),
                    "merged_claim_ids": _all_provenance_claim_ids(group),
                }
            )
            continue

        signature = next(iter(signature_groups))
        signature_rows = signature_groups[signature]
        representative = min(signature_rows, key=_representative_sort_key)
        canonical = dict(representative)
        source_claim_ids = _merged_source_claim_ids(signature_rows)
        merged_claim_ids = _merged_claim_ids(signature_rows)
        if len(signature_rows) > 1:
            merged_claim_ids = _all_provenance_claim_ids(signature_rows)
        canonical["source_claim_ids"] = source_claim_ids
        if merged_claim_ids:
            canonical["merged_claim_ids"] = merged_claim_ids
        canonical_rows.append(canonical)

        if len(signature_rows) > 1:
            merged_provenance.append(
                {
                    "signature": list(signature),
                    "source_claim_ids": source_claim_ids,
                    "merged_claim_ids": merged_claim_ids,
                }
            )

    canonical_rows.sort(
        key=lambda row: runtime_row_signature(
            row["card_id"],
            row["behavior_block"],
            row,
        )
    )
    return {
        "rows": canonical_rows,
        "merged_duplicate_count": merged_duplicate_count,
        "merged_provenance": merged_provenance,
        "conflicts": conflicts,
    }


def _merged_source_claim_ids(rows: Iterable[dict[str, Any]]) -> list[str]:
    claim_ids: set[str] = set()
    for row in rows:
        source_claim_ids = row.get("source_claim_ids", [])
        if isinstance(source_claim_ids, (list, tuple, set)):
            normalized_source_claim_ids = {
                normalized
                for item in source_claim_ids
                if (normalized := str(item).strip())
            }
            claim_ids.update(normalized_source_claim_ids)
            if normalized_source_claim_ids:
                continue
        claim_id = str(row.get("claim_id", "")).strip()
        if claim_id:
            claim_ids.add(claim_id)
    return sorted(claim_ids)


def _merged_claim_ids(rows: Iterable[dict[str, Any]]) -> list[str]:
    claim_ids: set[str] = set()
    for row in rows:
        merged_claim_ids = row.get("merged_claim_ids", [])
        if isinstance(merged_claim_ids, (list, tuple, set)):
            claim_ids.update(
                normalized
                for item in merged_claim_ids
                if (normalized := str(item).strip())
            )
    return sorted(claim_ids)


def _all_provenance_claim_ids(rows: Iterable[dict[str, Any]]) -> list[str]:
    claim_ids: set[str] = set()
    for row in rows:
        for key in ("claim_id", "source_claim_id"):
            normalized = str(row.get(key, "")).strip()
            if normalized:
                claim_ids.add(normalized)
        for key in ("source_claim_ids", "merged_claim_ids"):
            values = row.get(key, [])
            if isinstance(values, str):
                values = [values]
            if isinstance(values, (list, tuple, set)):
                claim_ids.update(
                    normalized
                    for item in values
                    if (normalized := str(item).strip())
                )
    return sorted(claim_ids)


def _representative_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("rule_id_suffix", "")).strip(),
        str(row.get("claim_id", "")).strip(),
        json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ),
    )
