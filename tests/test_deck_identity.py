import importlib
import json

import pytest

from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.deck_identity import build_deck_identity, stable_deck_fingerprint
from hsconfig.input_loading import load_cards


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _deck_input_verification_module():
    try:
        return importlib.import_module("hsconfig.deck_input_verification")
    except ModuleNotFoundError:
        pytest.fail("hsconfig.deck_input_verification is required")


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
        format="FT_WILD",
    )

    assert identity["deck_name"] == "Example"
    assert identity["deck_slug"] == "example"
    assert identity["hero_dbf_id"] == 7
    assert identity["format"] == "FT_WILD"
    assert identity["cards"][0] == {"card_id": "B", "dbf_id": 2, "count": 1}
    assert identity["cards"][1] == {"card_id": "A", "dbf_id": 1, "count": 2}
    assert identity["card_count_total"] == 3
    assert identity["unresolved_card_count"] == 0
    assert len(identity["deck_code_hash"]) == 64
    assert len(identity["deck_fingerprint"]) == 64


def test_build_deck_identity_preserves_sideboard_owner_identity():
    deck_identity = build_deck_identity(
        deck_name="Mech Paladin",
        deck_code="test-code",
        cards=[{"card_id": "CORE_EX1_383", "dbf_id": 671, "count": 30}],
        sideboards=[
            {
                "sideboard_index": 1,
                "owner_dbf_id": 102983,
                "owner_card_id": "TOY_516",
                "cards": [{"card_id": "TOY_517", "dbf_id": 104947, "count": 1}],
            }
        ],
    )

    assert deck_identity["sideboards"][0]["owner_dbf_id"] == 102983
    assert deck_identity["sideboards"][0]["owner_card_id"]


@pytest.mark.parametrize("deck_zone", ["main", "sideboard"])
def test_build_deck_identity_preserves_and_sanitizes_identity_only_provenance(
    deck_zone,
):
    identity_only_card = {
        "card_id": "IDENTITY_ONLY",
        "dbf_id": 424242,
        "count": 1,
        "name": "Secret Identity",
        "cost": 3,
        "type": "SPELL",
        "card_class": "MAGE",
        "text": "Secret: When your opponent plays a card, draw a card.",
        "mechanics": ["secret"],
        "metadata_status": "source_record",
        "deckstring_identity_only": True,
    }
    cards = [identity_only_card] if deck_zone == "main" else [
        {"card_id": "SIDEBOARD_OWNER", "dbf_id": 434343, "count": 1}
    ]
    sideboards = [] if deck_zone == "main" else [
        {
            "sideboard_index": 1,
            "owner_dbf_id": 434343,
            "owner_card_id": "SIDEBOARD_OWNER",
            "cards": [identity_only_card],
        }
    ]

    identity = build_deck_identity(
        deck_name="Identity Boundary",
        deck_code="test-code",
        cards=cards,
        sideboards=sideboards,
    )

    normalized = (
        identity["cards"][0]
        if deck_zone == "main"
        else identity["sideboards"][0]["cards"][0]
    )
    assert normalized == {
        "card_id": "IDENTITY_ONLY",
        "dbf_id": 424242,
        "count": 1,
        "deckstring_identity_only": True,
    }


def test_build_deck_identity_rejects_missing_card_id():
    with pytest.raises(ValueError, match="card_id"):
        build_deck_identity(
            deck_name="Example",
            deck_code="test-code",
            cards=[{"dbf_id": 1, "count": 1}],
        )


@pytest.mark.parametrize(
    ("source", "deck_code", "cards_factory", "expected_status", "eligible"),
    [
        (
            "deckstring",
            SHADOWPRIEST_CODE,
            lambda decoded: decoded,
            "decoded_from_deck_code",
            True,
        ),
        (
            "cards_json",
            SHADOWPRIEST_CODE,
            lambda decoded: list(reversed(decoded)),
            "cards_json_matches_deck_code",
            True,
        ),
        (
            "cards_json",
            SHADOWPRIEST_CODE,
            lambda decoded: [{**decoded[0], "count": decoded[0]["count"] + 1}, *decoded[1:]],
            "cards_json_unverified",
            False,
        ),
        (
            "placeholder",
            None,
            lambda _decoded: [{"card_id": "HSC_PLACEHOLDER", "count": 1}],
            "placeholder_unverified",
            False,
        ),
        (
            "cards_json",
            "malformed-deck-code",
            lambda decoded: decoded,
            "cards_json_unverified",
            False,
        ),
        (
            "cards_json",
            "AA==",
            lambda decoded: decoded,
            "cards_json_unverified",
            False,
        ),
    ],
)
def test_deck_input_verification_matrix(
    source,
    deck_code,
    cards_factory,
    expected_status,
    eligible,
):
    verification = _deck_input_verification_module()
    decoded_cards = decode_deck_code(SHADOWPRIEST_CODE)["cards"]

    verdict = verification.verify_deck_input(
        deck_code=deck_code,
        cards=cards_factory(decoded_cards),
        source=source,
    )

    assert verdict["status"] == expected_status
    assert verdict["runtime_apply_eligible"] is eligible
    assert verdict["normalized_roster_sha256"].startswith("sha256:")
    assert len(verdict["normalized_roster_sha256"]) == 71


def test_deck_input_verification_normalizes_multiset_without_names_or_order():
    verification = _deck_input_verification_module()
    decoded_cards = decode_deck_code(SHADOWPRIEST_CODE)["cards"]
    card_with_two_copies = next(card for card in decoded_cards if card["count"] == 2)
    supplied_cards = [
        {
            **card,
            "name": f"Renamed {index}",
        }
        for index, card in enumerate(reversed(decoded_cards))
        if card["card_id"] != card_with_two_copies["card_id"]
    ]
    supplied_cards.extend(
        [
            {
                "card_id": card_with_two_copies["card_id"],
                "count": 1,
                "name": "First duplicate",
            },
            {
                "card_id": card_with_two_copies["card_id"],
                "count": 1,
                "name": "Second duplicate",
            },
        ]
    )

    verdict = verification.verify_deck_input(
        deck_code=SHADOWPRIEST_CODE,
        cards=supplied_cards,
        source="cards_json",
    )

    assert verdict["status"] == "cards_json_matches_deck_code"
    assert verdict["runtime_apply_eligible"] is True


@pytest.mark.parametrize(
    ("cards", "error_code"),
    [
        ([{"card_id": "EX1_001", "count": 0}], "deck_input_count_non_positive"),
        ([{"card_id": "EX1_001", "count": -1}], "deck_input_count_non_positive"),
        ([{"count": 1}], "deck_input_card_id_missing"),
    ],
)
def test_deck_input_verification_rejects_invalid_roster_before_hashing(
    cards,
    error_code,
):
    verification = _deck_input_verification_module()

    with pytest.raises(ValueError, match=error_code):
        verification.verify_deck_input(
            deck_code=SHADOWPRIEST_CODE,
            cards=cards,
            source="cards_json",
        )


@pytest.mark.parametrize("count", [True, 1.5])
def test_load_cards_rejects_non_integer_count_types(tmp_path, count):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps({"cards": [{"card_id": "EX1_001", "count": count}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="deck_input_count_invalid"):
        load_cards(
            str(cards_json),
            deck_name="Example",
            deck_code=SHADOWPRIEST_CODE,
        )
