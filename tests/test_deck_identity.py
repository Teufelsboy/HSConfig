import pytest

from hsconfig.deck_identity import build_deck_identity, stable_deck_fingerprint


def test_stable_deck_fingerprint_is_order_independent():
    left = stable_deck_fingerprint([("A", 2), ("B", 1)])
    right = stable_deck_fingerprint([("B", 1), ("A", 2)])

    assert left == right
    assert len(left) == 64


def test_stable_deck_fingerprint_changes_when_counts_change():
    left = stable_deck_fingerprint([("A", 2), ("B", 1)])
    right = stable_deck_fingerprint([("A", 1), ("B", 1)])

    assert left != right


def test_build_deck_identity_from_explicit_cards():
    identity = build_deck_identity(
        deck_name="Example",
        deck_code="test-code",
        cards=[
            {"card_id": "B", "dbf_id": "2", "count": "1"},
            {"card_id": "A", "dbf_id": 1, "count": 2},
        ],
        hero_dbf_id=7,
    )

    assert identity["deck_name"] == "Example"
    assert identity["deck_slug"] == "example"
    assert identity["hero_dbf_id"] == 7
    assert identity["cards"][0] == {"card_id": "B", "dbf_id": 2, "count": 1}
    assert identity["cards"][1] == {"card_id": "A", "dbf_id": 1, "count": 2}
    assert identity["card_count_total"] == 3
    assert identity["unresolved_card_count"] == 0
    assert len(identity["deck_code_hash"]) == 64
    assert len(identity["deck_fingerprint"]) == 64


def test_build_deck_identity_rejects_missing_card_id():
    with pytest.raises(ValueError, match="card_id"):
        build_deck_identity(
            deck_name="Example",
            deck_code="test-code",
            cards=[{"dbf_id": 1, "count": 1}],
        )
