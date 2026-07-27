import pytest

from hsconfig.deckstring_decode import decode_deck_code


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)

MECHPALA_CODE = (
    "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/"
    "AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="
)

PIRATEDH_CODE = (
    "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQ"
    "ax6wYAAA=="
)


def test_decode_shadowpriest_deck_code_to_exact_cardids():
    decoded = decode_deck_code(SHADOWPRIEST_CODE)

    assert decoded["hero_dbf_id"] == 813
    assert decoded["format"] == "FT_WILD"
    assert decoded["card_count_total"] == 30
    assert decoded["sideboard_count"] == 0
    assert decoded["main_deck"] == decoded["cards"]
    assert decoded["sideboards"] == []
    assert decoded["unresolved_card_count"] == 0
    assert {card["card_id"] for card in decoded["cards"]} == {
        "CFM_637",
        "DRG_056",
        "DS1_233",
        "GVG_009",
        "NX2_019",
        "REV_290",
        "SCH_514",
        "SW_444",
        "SW_446",
        "SW_448",
        "TOY_381",
        "TOY_518",
        "VAC_419",
        "VAC_512",
        "WON_065",
        "YOD_032",
    }
    assert not any(card["card_id"].startswith("HSC_") for card in decoded["cards"])


def test_decode_receipt_contains_dbf_and_cardid_map():
    decoded = decode_deck_code(SHADOWPRIEST_CODE)

    receipt = decoded["deckstring_decode_receipt"]
    assert receipt["decoder"] == "hearthstone.deckstrings"
    assert receipt["hero_dbf_id"] == 813
    assert receipt["format"] == "FT_WILD"
    assert receipt["card_count_total"] == 30
    assert receipt["sideboard_count"] == 0

    card_id_map = decoded["card_id_map"]
    assert card_id_map["545"]["card_id"] == "DS1_233"
    assert card_id_map["64429"]["card_id"] == "SW_446"


def test_decode_mechpala_sideboards_from_hearthsim_triplets():
    decoded = decode_deck_code(MECHPALA_CODE)

    assert decoded["hero_dbf_id"] == 671
    assert decoded["format"] == "FT_WILD"
    assert decoded["card_count"] == 30
    assert decoded["card_count_total"] == 30
    assert decoded["sideboard_count"] == 3
    assert decoded["deckstring_decode_receipt"]["sideboard_unique_card_count"] == 3
    assert len(decoded["sideboards"]) == 1

    sideboard = decoded["sideboards"][0]
    assert sideboard["owner_dbf_id"] == 102983
    assert sideboard["owner_card_id"] == "TOY_330"
    assert {card["dbf_id"] for card in sideboard["cards"]} == {104947, 104950, 110446}
    assert {card["card_id"] for card in sideboard["cards"]} == {
        "TOY_330t95",
        "TOY_330t98",
        "TOY_330t11",
    }


@pytest.mark.parametrize("deck_code", [MECHPALA_CODE, PIRATEDH_CODE])
def test_decode_accepts_exact_supplied_codes_without_manual_base64_padding(deck_code):
    decoded = decode_deck_code(deck_code.rstrip("="))

    assert decoded["card_count"] == 30
