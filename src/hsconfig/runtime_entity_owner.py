from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


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
    if not runtime_card_id:
        return None
    return RuntimeEntityOwner(
        source_card_id=source_card_id,
        runtime_card_id=str(runtime_card_id),
        link_kind="hero_power_transform",
    )


__all__ = ("RuntimeEntityOwner", "resolve_runtime_entity_owner")
