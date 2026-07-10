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
                "type": "STARSHIP",
                "mechanics": [],
                "referencedTags": [],
                "text": "A future card type.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["card_types"] == ["starship"]
    assert report["unknown_card_types"] == ["starship"]
    assert report["summary"]["unknown_card_type_count"] == 1
