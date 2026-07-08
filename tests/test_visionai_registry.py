from hsconfig.visionai_registry import (
    CARD_BEHAVIOR_BLOCK_REGISTRY,
    is_supported_card_behavior_block,
    runtime_block_support,
    supported_surface,
)


def test_registry_keeps_core_card_behavior_blocks_supported():
    for block in [
        "BeforePlayCardBonus",
        "BeforeBattlecryTargetBonus",
        "BeforeUseHeroPowerBonus",
        "BeforePhysicalAttackBonus",
        "OnDiscoverCardBonus",
        "OnChooseOneCardBonus",
    ]:
        row = runtime_block_support(block)
        assert row["support"] == "supported"
        assert is_supported_card_behavior_block(block)


def test_registry_marks_unknown_blocks_as_unsupported():
    row = runtime_block_support("BeforeInventedCardBonus")

    assert row["support"] == "unsupported"
    assert row["normal_path_runtime"] is False
    assert not is_supported_card_behavior_block("BeforeInventedCardBonus")


def test_registry_keeps_presume_and_concede_non_normal_even_if_surface_known():
    assert supported_surface("Presume.json")
    assert supported_surface("Concede.json")
    assert runtime_block_support("Presume.json")["normal_path_runtime"] is False
    assert runtime_block_support("Concede.json")["normal_path_runtime"] is False
