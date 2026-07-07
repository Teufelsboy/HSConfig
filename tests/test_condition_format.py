from hsconfig.condition_format import classify_runtime_condition, lower_runtime_condition


def test_allows_documented_simple_runtime_conditions():
    allowed = [
        "*",
        "coin",
        "nocoin",
        "my_hand(count()) == 4",
        "my_hand(count(),cardid=SW_448) > 0",
        "opp_hero(count(),warrior=true) > 0",
        "my_target(count(),hero=true) > 0",
        "my_minion(count(),cardid=EX1_002) > 0",
        "my_discover(count(),cardid=SW_448) > 0",
        "coin AND my_hand(count(),cardid=SW_448) > 0",
        "coin OR nocoin",
    ]

    for condition in allowed:
        lowered = classify_runtime_condition(condition)
        assert lowered.status == "runtime_safe", condition
        assert lower_runtime_condition(condition) == (condition, None)


def test_rejects_unknown_strings_and_top_level_pipe():
    assert classify_runtime_condition("play this if hand is good").status == "unsupported"
    assert classify_runtime_condition("coin | nocoin").status == "unsupported"


def test_allows_documented_opponent_hero_class_list_condition():
    condition = "opp_hero(count(), hero_class=warrior | rogue | paladin ) > 0"

    lowered = classify_runtime_condition(condition)

    assert lowered.status == "runtime_safe"
    assert lower_runtime_condition(condition) == (condition, None)


def test_structured_opponent_classes_lower_to_documented_runtime_condition():
    assert lower_runtime_condition({"opponent_classes": ["warrior", "rogue", "paladin"]}) == (
        "opp_hero(count(), hero_class=warrior | rogue | paladin ) > 0",
        None,
    )


def test_structured_coin_and_opponent_classes_remain_runtime_safe():
    condition = {"coin": True, "opponent_classes": ["warrior", "rogue"]}
    expected = "coin AND opp_hero(count(), hero_class=warrior | rogue ) > 0"

    lowered = classify_runtime_condition(condition)

    assert lowered.status == "runtime_safe"
    assert lowered.value == expected
    assert lower_runtime_condition(condition) == (expected, None)


def test_structured_opponent_classes_unknown_single_value_fails_closed():
    condition = {"opponent_classes": ["banana"]}

    lowered = classify_runtime_condition(condition)

    assert lowered.status == "unsupported"
    assert lowered.reason == "unsupported_condition"
    assert lower_runtime_condition(condition) == ("*", "unsupported_condition")


def test_structured_opponent_classes_mixed_invalid_list_fails_closed_with_coin():
    condition = {"coin": True, "opponent_classes": ["warrior", "bad class"]}

    lowered = classify_runtime_condition(condition)

    assert lowered.status == "unsupported"
    assert lowered.reason == "unsupported_condition"
    assert lower_runtime_condition(condition) == ("*", "unsupported_condition")


def test_structured_opponent_classes_mixed_supported_and_unknown_fail_closed():
    condition = {"opponent_classes": ["warrior", "banana"]}

    lowered = classify_runtime_condition(condition)

    assert lowered.status == "unsupported"
    assert lowered.reason == "unsupported_condition"
    assert lower_runtime_condition(condition) == ("*", "unsupported_condition")


def test_structured_opponent_classes_scalar_fails_closed_with_coin():
    condition = {"coin": True, "opponent_classes": 123}

    lowered = classify_runtime_condition(condition)

    assert lowered.status == "unsupported"
    assert lowered.reason == "unsupported_condition"
    assert lower_runtime_condition(condition) == ("*", "unsupported_condition")


def test_structured_opponent_classes_scalar_string_fails_closed():
    condition = {"opponent_classes": "warrior"}

    lowered = classify_runtime_condition(condition)

    assert lowered.status == "unsupported"
    assert lowered.reason == "unsupported_condition"
    assert lower_runtime_condition(condition) == ("*", "unsupported_condition")


def test_structured_opponent_class_unknown_value_fails_closed():
    condition = {"opponent_class": "banana"}

    lowered = classify_runtime_condition(condition)

    assert lowered.status == "unsupported"
    assert lowered.reason == "unsupported_condition"
    assert lower_runtime_condition(condition) == ("*", "unsupported_condition")


def test_structured_conditions_lower_to_runtime_safe_atoms():
    assert lower_runtime_condition({"coin": True}) == ("coin", None)
    assert lower_runtime_condition({"nocoin": True}) == ("nocoin", None)
    assert lower_runtime_condition({"opponent_class": "warrior"}) == (
        "opp_hero(count(),warrior=true) > 0",
        None,
    )
    assert lower_runtime_condition({"hand_contains": "SW_448"}) == (
        "my_hand(count(),cardid=SW_448) > 0",
        None,
    )


def test_report_only_and_unsupported_dicts_do_not_emit_runtime_conditions():
    assert lower_runtime_condition({"phase": "early", "posture": "burn"}) == ("*", None)
    assert lower_runtime_condition({"unknown": "value"}) == ("*", "unsupported_condition")
    assert lower_runtime_condition({"coin": True, "unknown": "value"}) == (
        "*",
        "unsupported_condition",
    )
    assert lower_runtime_condition({"coin": True, "hand_contains_any": ["A", "B"]}) == (
        "*",
        "unsupported_condition",
    )


def test_direct_string_opponent_hero_conditions_with_unknown_classes_are_unsupported():
    unsupported = [
        "opp_hero(count(), hero_class=banana ) > 0",
        "opp_hero(count(),banana=true) > 0",
    ]

    for condition in unsupported:
        lowered = classify_runtime_condition(condition)

        assert lowered.status == "unsupported", condition
        assert lowered.reason == "unsupported_condition", condition
        assert lower_runtime_condition(condition) == ("*", "unsupported_condition")
