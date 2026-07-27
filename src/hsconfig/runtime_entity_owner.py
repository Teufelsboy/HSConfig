from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


LINKED_RUNTIME_ENTITY_OWNER_COLLISION = "linked_runtime_entity_owner_collision"
AUTHORIZED_HERO_POWER_OWNER = (
    "SW_448",
    "hero_power_before_use",
    "hero_power_transform",
    "EX1_625t",
)
LINKED_RUNTIME_ENTITY_RELATION_INVALID = (
    "linked_runtime_entity_relation_invalid"
)


@dataclass(frozen=True)
class RuntimeEntityOwner:
    source_card_id: str
    runtime_card_id: str
    link_kind: str


def resolve_runtime_entity_owner(
    *,
    source_card_id: str,
    semantic_reason: str,
    identity_links: Mapping[str, object],
) -> RuntimeEntityOwner | None:
    if semantic_reason != "hero_power_before_use":
        return RuntimeEntityOwner(
            source_card_id=source_card_id,
            runtime_card_id=source_card_id,
            link_kind="self",
        )

    source_links = identity_links.get(source_card_id)
    if not isinstance(source_links, Mapping):
        return None
    runtime_card_id = source_links.get("hero_power_transform")
    if not runtime_entity_owner_relation_is_authorized(
        source_card_id=source_card_id,
        semantic_reason=semantic_reason,
        link_kind="hero_power_transform",
        runtime_card_id=str(runtime_card_id or ""),
    ):
        return None
    return RuntimeEntityOwner(
        source_card_id=source_card_id,
        runtime_card_id=str(runtime_card_id),
        link_kind="hero_power_transform",
    )


def runtime_entity_owner_relation_is_authorized(
    *,
    source_card_id: str,
    semantic_reason: str,
    link_kind: str,
    runtime_card_id: str,
) -> bool:
    return (
        source_card_id,
        semantic_reason,
        link_kind,
        runtime_card_id,
    ) == AUTHORIZED_HERO_POWER_OWNER


def partition_runtime_entity_owner_rows(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]]]:
    materialized_rows = list(rows)
    source_ids_by_runtime_id: dict[str, set[str]] = {}
    for row in materialized_rows:
        owner = _meaningful_runtime_owner(row)
        if owner is None:
            continue
        source_card_id, runtime_card_id = owner
        source_ids_by_runtime_id.setdefault(runtime_card_id, set()).add(
            source_card_id
        )

    collisions = [
        {
            "status": LINKED_RUNTIME_ENTITY_OWNER_COLLISION,
            "runtime_card_id": runtime_card_id,
            "source_card_ids": sorted(source_card_ids),
        }
        for runtime_card_id, source_card_ids in sorted(
            source_ids_by_runtime_id.items()
        )
        if len(source_card_ids) > 1
    ]
    colliding_runtime_ids = {
        str(collision["runtime_card_id"]) for collision in collisions
    }
    accepted_rows = [
        row
        for row in materialized_rows
        if (
            (owner := _meaningful_runtime_owner(row)) is None
            or owner[1] not in colliding_runtime_ids
        )
    ]
    return accepted_rows, collisions


def _meaningful_runtime_owner(
    row: Mapping[str, Any],
) -> tuple[str, str] | None:
    if (
        row.get("meaningful_runtime_surface") is False
        or not row.get("behavior_block")
    ):
        return None
    source_card_id = str(
        row.get("source_card_id") or row.get("card_id") or ""
    ).strip()
    runtime_card_id = str(
        row.get("runtime_card_id") or row.get("card_id") or ""
    ).strip()
    if not source_card_id or not runtime_card_id:
        return None
    return source_card_id, runtime_card_id


__all__ = (
    "AUTHORIZED_HERO_POWER_OWNER",
    "LINKED_RUNTIME_ENTITY_OWNER_COLLISION",
    "LINKED_RUNTIME_ENTITY_RELATION_INVALID",
    "RuntimeEntityOwner",
    "partition_runtime_entity_owner_rows",
    "resolve_runtime_entity_owner",
    "runtime_entity_owner_relation_is_authorized",
)
