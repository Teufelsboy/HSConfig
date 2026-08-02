from __future__ import annotations

from hsconfig.runtime_entity_owner import runtime_entity_owner_relation_is_authorized


def test_non_owner_runtime_row_is_rejected() -> None:
    """Break caught: arbitrary source rows can own a foreign runtime entity."""
    assert runtime_entity_owner_relation_is_authorized(
        source_card_id="SOURCE_A",
        semantic_reason="hero_power_before_use",
        link_kind="hero_power_transform",
        runtime_card_id="RUNTIME_SHARED",
    ) is False
