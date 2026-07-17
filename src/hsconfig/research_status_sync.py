from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from hsconfig.io import read_json


NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"
DIAGNOSTIC_AUTHORITY = "diagnostic_only"
STRONG_STATUS = "SOURCE_BACKED_STRONG"
PARTIAL_STATUS = "SOURCE_BACKED_PARTIAL"
SEED_STRENGTHS = {
    "candidate_url_only",
    "decklist_only",
    "snippet_only",
    "stats_only",
    "unfetched_acquisition_seed",
}
RELATIONS = (
    "current_with_canonical",
    "stale_or_seed_only",
    "conflicts_with_canonical",
    "missing",
)


def build_research_status_sync_report(
    package_dir: str | Path,
    research_result_paths: Sequence[str | Path],
) -> dict[str, Any]:
    package_path = Path(package_dir)
    canonical_status = _canonical_status(package_path)
    rows = [
        _research_snapshot_row(canonical_status, Path(result_path))
        for result_path in sorted(research_result_paths, key=lambda path: str(path))
    ]
    if not rows:
        rows.append(_missing_research_snapshot_row(canonical_status))

    return {
        "schema_version": 1,
        "normal_apply_authority": NORMAL_APPLY_AUTHORITY,
        "research_snapshot_authority": DIAGNOSTIC_AUTHORITY,
        "canonical_downgrade_allowed": False,
        "canonical_promotion_allowed": False,
        "source_status_apply_blocking": False,
        "summary": _summary(canonical_status, rows),
        "research_snapshots": rows,
    }


def _canonical_status(package_path: Path) -> str:
    payload = _read_json(package_path / NORMAL_APPLY_AUTHORITY)
    if not isinstance(payload, Mapping):
        return "UNKNOWN"
    return str(
        payload.get("source_backed_status")
        or payload.get("source_status")
        or payload.get("static_contract_status")
        or "UNKNOWN"
    )


def _research_snapshot_row(
    canonical_status: str,
    result_path: Path,
) -> dict[str, Any]:
    payload = _read_json(result_path)
    research_status = _research_status(payload)
    snapshot_kind = _research_snapshot_kind(payload, research_status)
    return {
        "path": str(result_path),
        "deck_name": _deck_name(result_path, payload),
        "canonical_status": canonical_status,
        "research_status": research_status,
        "snapshot_kind": snapshot_kind,
        "relation_to_canonical": _snapshot_relation(
            canonical_status=canonical_status,
            research_status=research_status,
            snapshot_kind=snapshot_kind,
        ),
        "recommended_refresh_action": _recommended_refresh_action(
            canonical_status=canonical_status,
            research_status=research_status,
            snapshot_kind=snapshot_kind,
        ),
        "canonical_downgrade_allowed": False,
        "canonical_promotion_allowed": False,
        "source_status_apply_blocking": False,
    }


def _missing_research_snapshot_row(canonical_status: str) -> dict[str, Any]:
    return {
        "path": None,
        "deck_name": None,
        "canonical_status": canonical_status,
        "research_status": None,
        "snapshot_kind": "missing",
        "relation_to_canonical": "missing",
        "recommended_refresh_action": "run_research_deep_snapshot_refresh",
        "canonical_downgrade_allowed": False,
        "canonical_promotion_allowed": False,
        "source_status_apply_blocking": False,
    }


def _research_status(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    status = (
        payload.get("source_backed_status")
        or payload.get("source_status")
        or payload.get("static_contract_status")
    )
    return str(status) if status else None


def _research_snapshot_kind(payload: Any, research_status: str | None) -> str:
    if not isinstance(payload, Mapping):
        return "missing"
    if _contains_seed_only_strength(payload):
        return "seed_only"
    if research_status == STRONG_STATUS:
        return "strong_snapshot"
    if research_status == PARTIAL_STATUS:
        return "partial_snapshot"
    return "snapshot"


def _snapshot_relation(
    *,
    canonical_status: str,
    research_status: str | None,
    snapshot_kind: str,
) -> str:
    if snapshot_kind == "missing" or research_status is None:
        return "missing"
    if snapshot_kind == "seed_only":
        return "stale_or_seed_only"
    if research_status == canonical_status:
        return "current_with_canonical"
    return "conflicts_with_canonical"


def _recommended_refresh_action(
    *,
    canonical_status: str,
    research_status: str | None,
    snapshot_kind: str,
) -> str:
    relation = _snapshot_relation(
        canonical_status=canonical_status,
        research_status=research_status,
        snapshot_kind=snapshot_kind,
    )
    if relation == "current_with_canonical":
        return "none"
    if relation == "stale_or_seed_only":
        return "refresh_research_snapshot"
    if relation == "conflicts_with_canonical":
        return "refresh_package_or_research_snapshot"
    return "run_research_deep_snapshot_refresh"


def _summary(canonical_status: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {relation: 0 for relation in RELATIONS}
    for row in rows:
        relation = str(row.get("relation_to_canonical") or "")
        if relation in counts:
            counts[relation] += 1
    return {
        "authoritative_status": canonical_status,
        "normal_apply_authority": NORMAL_APPLY_AUTHORITY,
        "research_snapshot_authority": DIAGNOSTIC_AUTHORITY,
        "canonical_downgrade_allowed": False,
        "canonical_promotion_allowed": False,
        "source_status_apply_blocking": False,
        "counts": counts,
    }


def _deck_name(result_path: Path, payload: Any) -> str:
    if isinstance(payload, Mapping):
        deck_name = payload.get("deck_name") or payload.get("name")
        if deck_name:
            return str(deck_name)
    return result_path.stem


def _contains_seed_only_strength(payload: Mapping[str, Any]) -> bool:
    strength = str(payload.get("source_strength") or payload.get("source_kind") or "")
    if strength in SEED_STRENGTHS:
        return True
    acquisition = payload.get("source_acquisition")
    if isinstance(acquisition, Mapping):
        acquisition_strength = str(
            acquisition.get("source_strength") or acquisition.get("source_kind") or ""
        )
        if acquisition_strength in SEED_STRENGTHS:
            return True
    items = payload.get("items")
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            item_strength = str(
                item.get("source_strength")
                or item.get("source_kind")
                or item.get("kind")
                or ""
            )
            if item_strength in SEED_STRENGTHS:
                return True
    return False


def _read_json(path: Path) -> Any:
    try:
        return read_json(path)
    except (FileNotFoundError, ValueError):
        return None
