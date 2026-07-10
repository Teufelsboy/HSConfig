from hsconfig.mechanic_drift import build_mechanic_drift_report


def test_mechanic_drift_detects_text_only_tradeable_without_blocking():
    report = build_mechanic_drift_report(
        [
            {
                "id": "SW_001",
                "name": "Text Trade Card",
                "type": "SPELL",
                "mechanics": [],
                "referencedTags": [],
                "text": "Tradeable. Deal 2 damage.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["text_only_mechanics"] == ["tradeable"]
    assert report["unknown_mechanics"] == []
    assert report["support_by_mechanic"]["tradeable"]["support_level"] == "warning_only"


def test_mechanic_drift_detects_modern_text_only_mechanics_without_blocking():
    report = build_mechanic_drift_report(
        [
            {
                "id": "KINDRED_001",
                "type": "MINION",
                "mechanics": [],
                "referencedTags": [],
                "text": "Kindred: Deal 2 damage.",
            },
            {
                "id": "TOURIST_001",
                "type": "MINION",
                "mechanics": [],
                "referencedTags": [],
                "text": "Tourist. Your deck can include Paladin cards.",
            },
            {
                "id": "STARSHIP_001",
                "type": "STARSHIP",
                "mechanics": [],
                "referencedTags": [],
                "text": "Launch your Starship.",
            },
            {
                "id": "SPELLBURST_001",
                "type": "MINION",
                "mechanics": [],
                "referencedTags": [],
                "text": "Spellburst: Summon a 1/1.",
            },
            {
                "id": "MINI_001",
                "type": "MINION",
                "mechanics": [],
                "referencedTags": [],
                "text": "Miniaturize.",
            },
            {
                "id": "QUICK_001",
                "type": "SPELL",
                "mechanics": [],
                "referencedTags": [],
                "text": "Quickdraw: Costs (1) less.",
            },
            {
                "id": "HONOR_001",
                "type": "MINION",
                "mechanics": [],
                "referencedTags": [],
                "text": "Honorable Kill: Draw a card.",
            },
            {
                "id": "ELUSIVE_001",
                "type": "MINION",
                "mechanics": [],
                "referencedTags": [],
                "text": "Elusive.",
            },
            {
                "id": "POISON_001",
                "type": "MINION",
                "mechanics": [],
                "referencedTags": [],
                "text": "Poisonous.",
            },
            {
                "id": "IMBUE_001",
                "type": "SPELL",
                "mechanics": [],
                "referencedTags": [],
                "text": "Imbue your Hero Power.",
            },
            {
                "id": "REWIND_001",
                "type": "SPELL",
                "mechanics": [],
                "referencedTags": [],
                "text": "Rewind: Repeat your last spell.",
            },
            {
                "id": "HERALD_001",
                "type": "MINION",
                "mechanics": [],
                "referencedTags": [],
                "text": "Herald: Draw a minion.",
            },
            {
                "id": "SHATTER_001",
                "type": "SPELL",
                "mechanics": [],
                "referencedTags": [],
                "text": "Shatter a Frozen minion.",
            },
        ]
    )

    assert report["non_blocking"] is True
    assert report["unknown_card_types"] == []
    assert report["unknown_mechanics"] == []
    assert report["text_only_mechanics"] == [
        "elusive",
        "herald",
        "honorable_kill",
        "imbue",
        "kindred",
        "miniaturize",
        "poisonous",
        "quickdraw",
        "rewind",
        "shatter",
        "spellburst",
        "starship",
        "tourist",
    ]
    for mechanic in ["rewind", "herald", "shatter"]:
        assert report["support_by_mechanic"][mechanic]["support_level"] == "warning_only"
    for mechanic in ["kindred", "tourist", "rewind", "herald", "shatter"]:
        assert mechanic in report["text_only_mechanics"]
        assert report["support_by_mechanic"][mechanic]["normal_path_surfaces"] == [
            "report-only"
        ]
        assert report["support_by_mechanic"][mechanic]["support_level"] == "warning_only"
    assert report["support_by_mechanic"]["starship"]["support_level"] == "warning_only"
    assert report["support_by_mechanic"]["spellburst"]["support_level"] == "partial"


def test_mechanic_drift_keeps_unknown_mechanics_warning_only():
    report = build_mechanic_drift_report(
        [
            {
                "id": "FUTURE_001",
                "name": "Future Card",
                "type": "MINION",
                "mechanics": ["FUTURE_KEYWORD"],
                "referencedTags": [],
                "text": "Future Keyword: Do something.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["unknown_mechanics"] == ["future_keyword"]
    assert report["support_by_mechanic"]["future_keyword"]["support_level"] == "warning_only"
    assert report["support_by_mechanic"]["future_keyword"]["registered"] is False


def test_mechanic_drift_reports_unknown_card_types_without_blocking():
    report = build_mechanic_drift_report(
        [
            {
                "id": "FUTURE_TYPE_001",
                "name": "Future Type Card",
                "type": "LETTUCE_ABILITY",
                "mechanics": [],
                "referencedTags": [],
                "text": "A future card type.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["card_types"] == ["lettuce_ability"]
    assert report["unknown_card_types"] == ["lettuce_ability"]
    assert report["summary"]["unknown_card_type_count"] == 1


def test_mechanic_drift_treats_registered_future_mechanics_as_known():
    report = build_mechanic_drift_report(
        [
            {
                "id": "FUTURE_QUEST",
                "name": "Future Questline",
                "type": "SPELL",
                "mechanics": ["QUESTLINE", "MANATHIRST"],
                "text": "Questline. Manathirst (8): Improve this.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["unknown_mechanics"] == []
    assert report["support_by_mechanic"]["questline"]["support_level"] == "partial"
    assert report["support_by_mechanic"]["manathirst"]["support_level"] == "partial"


def test_mechanic_drift_detects_text_only_invoke_as_known_partial():
    report = build_mechanic_drift_report(
        [
            {
                "id": "ULD_719",
                "name": "Invoke Card",
                "type": "SPELL",
                "mechanics": [],
                "referencedTags": [],
                "text": "Invoke Galakrond.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["text_only_mechanics"] == ["invoke"]
    assert report["unknown_mechanics"] == []
    assert report["support_by_mechanic"]["invoke"]["support_level"] == "partial"


def test_mechanic_drift_normalizes_explicit_cthun_punctuation_to_package():
    report = build_mechanic_drift_report(
        [
            {
                "id": "OG_280",
                "name": "C'Thun",
                "type": "MINION",
                "mechanics": ["C'THUN"],
                "referencedTags": [],
                "text": "Your C'Thun has +2/+2.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["unknown_mechanics"] == []
    assert report["mechanics"] == ["cthun_package"]
    assert report["support_by_mechanic"]["cthun_package"]["support_level"] == "partial"
