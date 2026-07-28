import json
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hsconfig.audited_deck_catalog import load_audited_role_manifest
from hsconfig.deck_identity import build_deck_identity
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.combo_plan import build_combo_plan
from hsconfig.mulligan_plan import build_mulligan_plan
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


FIXTURES = {
    "ShadowPriest": Path("tests/fixtures/source_documents_shadowpriest_strong.json"),
    "CtAPaladin": Path("tests/fixtures/source_documents_ctapaladin_strong.json"),
    "PirateRogue": Path("tests/fixtures/source_documents_piraterogue_strong.json"),
    "BigShaman": Path("tests/fixtures/source_documents_bigshaman_strong.json"),
    "Discolock": Path("tests/fixtures/source_documents_discolock_strong.json"),
    "TreantDruid": Path("tests/fixtures/source_documents_treantdruid_strong.json"),
    "Kingslayer": Path("tests/fixtures/source_documents_kingslayer_strong.json"),
    "ImbueMage": Path("tests/fixtures/source_documents_imbuemage_strong.json"),
    "MechPala": Path("tests/fixtures/source_documents_mechpala_strong.json"),
    "Boarlock": Path("tests/fixtures/source_documents_boarlock_strong.json"),
    "PirateDH": Path("tests/fixtures/source_documents_piratedh_strong.json"),
}
MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
LOCAL_REF_SCHEMES = {"claim", "evidence", "guide", "source"}
URL_SCHEMES = {
    "data",
    "file",
    "fixture",
    "ftp",
    "http",
    "https",
    "javascript",
    "mailto",
    "private",
}


def _documents(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["source_documents"] if isinstance(payload, dict) else payload


def _matrix() -> dict:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    payload["decks"] = load_audited_role_manifest(MATRIX_PATH)
    return payload


def _core_matrix_rows() -> list[dict]:
    rows = [
        row
        for row in _matrix()["decks"]
        if row["fixture_stage"] == "core_source_backed_fixture"
    ]
    assert {row["deck_name"] for row in rows} <= set(FIXTURES)
    return rows


def _deck_identity_for_fixture(deck_name: str) -> dict:
    row = next(row for row in _matrix()["decks"] if row["deck_name"] == deck_name)
    decoded_deck = decode_deck_code(row["deck_code"])
    return build_deck_identity(
        deck_name=row["deck_name"],
        deck_code=row["deck_code"],
        cards=decoded_deck["cards"],
        hero_dbf_id=decoded_deck["hero_dbf_id"],
        format=decoded_deck["format"],
        sideboards=decoded_deck["sideboards"],
    )


def _source_bundle_for_fixture(deck_name: str) -> dict:
    deck_identity = _deck_identity_for_fixture(deck_name)
    return build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=_documents(FIXTURES[deck_name]),
        current_date="2026-07-07",
    )


def _claims(deck_name: str) -> list[dict]:
    return [
        claim
        for document in _documents(FIXTURES[deck_name])
        for claim in document["claims"]
    ]


@pytest.mark.parametrize(
    ("deck_name", "card_id", "runtime_block"),
    [
        ("CtAPaladin", "WW_336", "BeforePlayCardBonus"),
        ("CtAPaladin", "WW_051", "BeforePlayCardBonus"),
        ("CtAPaladin", "CATA_479", "BeforePlayCardBonus"),
        ("PirateRogue", "CS2_073", "BeforePlayCardBonus"),
        ("PirateRogue", "DMF_519", "BeforeBattlecryTargetBonus"),
        ("PirateRogue", "TTN_922", "BeforePlayCardBonus"),
        ("BigShaman", "GVG_029", "BeforePlayCardBonus"),
        ("BigShaman", "CS2_038", "BeforeBattlecryTargetBonus"),
        ("BigShaman", "WON_335", "BeforeBattlecryTargetBonus"),
        ("BigShaman", "TOY_877", "OnBoardBonus"),
        ("TreantDruid", "JAM_028", "BeforePlayCardBonus"),
        ("TreantDruid", "TTN_954", "OnBoardBonus"),
        ("PirateRogue", "NX2_006", "BeforePhysicalAttackBonus"),
        ("Kingslayer", "VAC_938", "BeforePhysicalAttackBonus"),
        ("Kingslayer", "VAC_701", "BeforePhysicalAttackBonus"),
    ],
)
def test_audited_unexpressible_claims_remain_in_source_fixtures(
    deck_name: str,
    card_id: str,
    runtime_block: str,
) -> None:
    assert any(
        card_id in claim.get("cards", [])
        and claim.get("runtime_block") == runtime_block
        for claim in _claims(deck_name)
    )


def _is_url_like_source_ref(value: object) -> bool:
    text = str(value).strip()
    if not text:
        return False
    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    if "://" in text:
        return True
    if text.lower().startswith("www."):
        return True
    if scheme in LOCAL_REF_SCHEMES:
        return False
    return scheme in URL_SCHEMES


def _assert_public_https_url(value: object, *, context: str) -> None:
    text = str(value).strip()
    parsed = urlsplit(text)
    assert parsed.scheme == "https", f"{context} must use public https://: {text}"
    assert parsed.netloc, f"{context} must include a public host: {text}"
    host = (parsed.hostname or "").lower()
    assert host, f"{context} must include a public host: {text}"
    assert host not in {"localhost"} and not host.endswith(".localhost"), (
        f"{context} must not use localhost: {text}"
    )
    assert not host.endswith(".local"), f"{context} must not use a local host: {text}"
    try:
        address = ip_address(host)
    except ValueError:
        return
    assert not (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    ), f"{context} must not use a non-public IP host: {text}"


@pytest.mark.parametrize(
    "source_url",
    [
        "fixture://shadowpriest",
        "file:///tmp/source.json",
        "private://local/source",
        "http://localhost/source",
        "ftp://example.com/source",
    ],
)
def test_public_https_validator_rejects_private_or_non_https_urls(source_url):
    with pytest.raises(AssertionError):
        _assert_public_https_url(source_url, context="fixture")


def test_core_source_fixture_files_exist():
    for path in FIXTURES.values():
        assert path.exists(), path


def test_core_source_fixtures_have_required_source_fields():
    for deck_name, path in FIXTURES.items():
        documents = _documents(path)
        assert documents, deck_name
        for document in documents:
            assert document["source_url"]
            assert document["source_title"]
            assert document["source_family"] in {
                "guide",
                "mulligan_guide",
                "matchup_guide",
                "card_text",
                "metadata",
                "static_semantics",
            }
            assert document["retrieved_at"]
            assert isinstance(document["claims"], list)
            assert document["claims"]


def test_core_source_fixtures_use_public_source_urls():
    for deck_name, path in FIXTURES.items():
        for document_index, document in enumerate(_documents(path), start=1):
            source_url = document["source_url"]
            _assert_public_https_url(
                source_url,
                context=f"{deck_name} document {document_index} source_url",
            )
            for claim_index, claim in enumerate(document["claims"], start=1):
                for source_ref in claim.get("source_refs", []):
                    if _is_url_like_source_ref(source_ref):
                        _assert_public_https_url(
                            source_ref,
                            context=(
                                f"{deck_name} document {document_index} "
                                f"claim {claim_index} source_ref"
                            ),
                        )


def test_core_source_fixtures_use_supported_atomic_claims():
    for deck_name, path in FIXTURES.items():
        claim_kinds = {
            claim["claim_kind"]
            for document in _documents(path)
            for claim in document["claims"]
        }
        assert claim_kinds <= SUPPORTED_ATOMIC_CLAIM_KINDS
        assert "gameplan_posture" in claim_kinds
        assert {"mulligan_keep", "card_role"} & claim_kinds


def test_core_source_fixtures_build_bundles_against_real_deck_identities():
    for row in _core_matrix_rows():
        bundle = _source_bundle_for_fixture(row["deck_name"])

        assert bundle["claims"], row["deck_name"]
        assert bundle["unsupported_claims"] == [], row["deck_name"]
        assert {
            claim["claim_kind"] for claim in bundle["claims"]
        } <= SUPPORTED_ATOMIC_CLAIM_KINDS


def test_all_source_fixtures_build_bundles_against_real_deck_identities():
    for deck_name in FIXTURES:
        bundle = _source_bundle_for_fixture(deck_name)

        assert bundle["claims"], deck_name
        assert bundle["unsupported_claims"] == [], deck_name
        assert {
            claim["claim_kind"] for claim in bundle["claims"]
        } <= SUPPORTED_ATOMIC_CLAIM_KINDS


def test_core_source_fixtures_do_not_mark_every_claim_low_confidence():
    for deck_name, path in FIXTURES.items():
        confidences = [
            claim["source_confidence"]
            for document in _documents(path)
            for claim in document["claims"]
        ]
        assert any(confidence in {"high", "medium"} for confidence in confidences), deck_name


def test_shadowpriest_fixture_covers_hero_power_and_face_pressure():
    claims = [
        claim
        for document in _documents(FIXTURES["ShadowPriest"])
        for claim in document["claims"]
    ]
    kinds = {claim["claim_kind"] for claim in claims}
    stances = {str(claim.get("stance", "")) for claim in claims}
    assert "hero_power_transform" in kinds
    assert "targeting_rule" in kinds
    assert "prefer_enemy_hero" in stances


def test_shadowpriest_fixture_closes_known_audit_gaps():
    bundle = _source_bundle_for_fixture("ShadowPriest")
    claims_by_card = {}
    for claim in bundle["claims"]:
        for card in claim.get("cards", []):
            claims_by_card.setdefault(card, []).append(claim)

    expected_cards = {
        "CFM_637",
        "DRG_056",
        "REV_290",
        "SCH_514",
        "TOY_381",
        "TOY_518",
        "VAC_512",
        "WON_065",
        "YOD_032",
        "NX2_019",
        "SW_446",
        "SW_448",
    }
    assert expected_cards <= set(claims_by_card)
    assert any(
        claim.get("runtime_block") == "BeforeBattlecryTargetBonus"
        and claim.get("stance") == "prefer_enemy_minion"
        for claim in claims_by_card["NX2_019"]
    )
    assert any(
        claim.get("runtime_block") == "BeforePlayCardBonus"
        and claim.get("stance") == "burn_followup_pressure"
        for claim in claims_by_card["NX2_019"]
    )
    assert any(
        claim.get("runtime_block") in {"BeforePlayCardBonus", "OnBoardBonus"}
        for claim in claims_by_card["SW_446"]
    )
    assert any(
        claim["claim_kind"] == "hero_power_transform"
        for claim in claims_by_card["SW_448"]
    )


def test_shadowpriest_fixture_does_not_mulligan_keep_darkbishop_start_of_game_effect():
    bundle = _source_bundle_for_fixture("ShadowPriest")
    darkbishop_claims = [
        claim
        for claim in bundle["claims"]
        if "SW_448" in claim.get("cards", [])
    ]

    assert any(claim["claim_kind"] == "hero_power_transform" for claim in darkbishop_claims)
    assert not any(
        claim["claim_kind"] == "mulligan_keep" for claim in darkbishop_claims
    )


def test_effect_only_start_of_game_hero_power_transform_claim_is_suppressed():
    plan = build_mulligan_plan(
        deck_name="ShadowPriest",
        claims=[
            {
                "claim_id": "claim_darkbishop_keep",
                "claim_kind": "mulligan_keep",
                "claim_type": "mulligan_keep",
                "cards": ["SW_448"],
                "claim": "Darkbishop Benedictus enables the start-of-game hero power plan.",
                "evidence_text_short": "Darkbishop Benedictus enables the start-of-game hero power plan.",
                "confidence": "guide_backed",
                "source_confidence": "high",
            }
        ],
        card_roles={
            "SW_448": {
                "roles": ["hero_power_transform", "hero_power_pressure", "start_of_game"],
                "semantic_families": [
                    "hero_power_transform",
                    "hero_power_pressure",
                    "start_of_game",
                ],
                "confidence": "guide_backed",
            }
        },
    )

    assert not any(
        rule.get("card") == "SW_448" and rule.get("action") == "hold"
        for rule in plan["rules"]
    )
    assert any(
        rule.get("card") == "SW_448"
        and rule.get("reason") == "start_of_game_effect_does_not_require_opening_hand"
        for rule in plan["suppressed_rules"]
    )


def test_bigshaman_fixture_covers_big_cheat_and_bad_target_patterns():
    claims = _claims("BigShaman")
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    kinds = {claim["claim_kind"] for claim in claims}
    assert {"card_role", "known_bad_pattern"} & kinds
    assert any(marker in text for marker in ("recruit", "big", "deathrattle", "cheat"))
    assert any(marker in text for marker in ("friendly", "own minion", "not enemy"))


def test_bigshaman_fixture_keeps_metadata_claims_static_and_explicit():
    metadata_claims = [
        claim
        for document in _documents(FIXTURES["BigShaman"])
        if document["source_family"] == "metadata"
        for claim in document["claims"]
    ]
    banned_stances = {
        "repeatable_big_pressure",
        "threat_cheat",
        "colossal_payoff",
        "board_scaling",
        "deck_recruit_deathrattle_payoff",
    }

    assert not {claim.get("stance") for claim in metadata_claims} & banned_stances
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "recruit"
        and claim.get("runtime_block") == "BeforePlayCardBonus"
        and claim.get("runtime_value") == "9"
        for claim in metadata_claims
    )
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "deathrattle"
        and claim.get("runtime_block") == "OnBoardBonus"
        and claim.get("runtime_value") == "7"
        for claim in metadata_claims
    )


def test_discolock_fixture_covers_discard_and_hand_mutation():
    claims = _claims("Discolock")
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert "discard" in text
    assert any(claim["claim_kind"] in {"mechanic_usage", "known_bad_pattern"} for claim in claims)


def test_discolock_fixture_marks_discard_runtime_and_never_autopatch_boundaries():
    claims = _claims("Discolock")
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "discard"
        and claim.get("runtime_block") == "BeforePlayCardBonus"
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] == "known_bad_pattern"
        and "discard" in str(claim.get("evidence_text_short", "")).lower()
        for claim in claims
    )


def test_kingslayer_fixture_covers_weapon_sequence_pressure():
    claims = _claims("Kingslayer")
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert any(marker in text for marker in ("weapon", "attack", "kingsbane", "kingslayer"))
    assert any(
        claim["claim_kind"] in {"targeting_rule", "mechanic_usage", "card_role"}
        for claim in claims
    )


def test_kingslayer_fixture_has_runtime_lowerable_weapon_sequence_claims():
    claims = _claims("Kingslayer")
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "weapon"
        and claim.get("runtime_block") in {"BeforePlayCardBonus", "BeforePhysicalAttackBonus"}
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] == "targeting_rule"
        and claim.get("stance") == "prefer_enemy_hero"
        and claim.get("runtime_block") == "BeforePhysicalAttackBonus"
        and claim.get("runtime_value")
        for claim in claims
    )


def test_kingslayer_fixture_closes_runtime_surfaces_for_pirate_support_cards():
    claims_by_card = {}
    for claim in _claims("Kingslayer"):
        for card in claim.get("cards", []):
            claims_by_card.setdefault(card, []).append(claim)

    expected_cards = {
        "CFM_637",
        "DRG_056",
        "EDR_846",
        "NX2_006",
        "TOY_505",
        "TOY_518",
        "VAC_938",
    }
    for card_id in expected_cards:
        assert any(
            claim.get("runtime_block") in {"BeforePlayCardBonus", "BeforePhysicalAttackBonus", "OnBoardBonus"}
            and claim.get("runtime_value")
            for claim in claims_by_card.get(card_id, [])
        ), card_id


def test_kingslayer_unsupported_quick_pick_mulligan_claim_does_not_lower():
    bundle = _source_bundle_for_fixture("Kingslayer")
    quick_pick_claims = [
        claim
        for claim in bundle["claims"]
        if claim["claim_kind"] == "mulligan_keep" and claim["cards"] == ["DEEP_014"]
    ]
    assert quick_pick_claims
    assert {claim["claim_readiness"] for claim in quick_pick_claims} == {
        "explicit_low_confidence"
    }
    assert {claim["trust_ceiling"] for claim in quick_pick_claims} == {"report_only"}

    plan = build_mulligan_plan(
        deck_name="Kingslayer",
        claims=bundle["claims"],
        card_roles={},
    )

    assert not any(
        rule.get("card") == "DEEP_014" and rule.get("action") == "hold"
        for rule in plan["rules"]
    )
    assert any(
        rule.get("card") == "DEEP_014"
        and rule.get("action") == "hold"
        and rule.get("reason") == "claim_not_runtime_lowerable"
        for rule in plan["suppressed_rules"]
    )


def test_imbuemage_fixture_covers_hero_power_and_generation():
    claims = _claims("ImbueMage")
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    kinds = {claim["claim_kind"] for claim in claims}
    assert any(marker in text for marker in ("imbue", "hero power", "spell", "generate", "discover"))
    assert {"hero_power_transform", "mechanic_usage", "discover_choice"} & kinds


def test_imbuemage_fixture_marks_hero_power_and_generation_boundaries():
    claims = _claims("ImbueMage")
    assert any(
        claim["claim_kind"] == "hero_power_transform"
        and claim.get("runtime_block") == "BeforeUseHeroPowerBonus"
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] in {"mechanic_usage", "discover_choice"}
        and claim.get("mechanic") in {"spell_generation", "discover", "imbue"}
        for claim in claims
    )


def test_imbuemage_fixture_mulligan_claims_remain_diagnostic_without_receipts():
    bundle = _source_bundle_for_fixture("ImbueMage")
    deck_identity = _deck_identity_for_fixture("ImbueMage")
    plan = build_mulligan_plan(
        deck_name="ImbueMage",
        claims=bundle["claims"],
        card_roles={},
        deck_identity=deck_identity,
        verified_source_receipts=bundle["canonical_source_receipts"],
    )
    source_claim_holds = {
        rule.get("card")
        for rule in plan["rules"]
        if rule.get("action") == "hold" and rule.get("source_type") == "source_claim"
    }

    assert bundle["canonical_source_receipts"] == []
    assert source_claim_holds == set()
    assert {
        claim["claim_kind"]
        for claim in bundle["claims"]
        if claim["claim_kind"].startswith("mulligan_")
    } == {"mulligan_keep"}


def test_ctapaladin_fixture_covers_recruit_board_flood():
    claims = _claims("CtAPaladin")
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert any(marker in text for marker in ("recruit", "call to arms", "board", "flood"))


def test_ctapaladin_source_fixture_has_runtime_lowerable_recruit_and_aura_claims():
    claims = _claims("CtAPaladin")
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "recruit"
        and claim.get("runtime_block") == "BeforePlayCardBonus"
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] in {"card_role", "targeting_rule"}
        and str(claim.get("stance", "")).lower()
        in {"board_flood", "aura_pressure", "wide_board_pressure"}
        and claim.get("runtime_block") in {"BeforePlayCardBonus", "OnBoardBonus"}
        and claim.get("runtime_value")
        for claim in claims
    )


def test_ctapaladin_fixture_closes_remaining_guide_claim_gaps():
    bundle = _source_bundle_for_fixture("CtAPaladin")
    claims_by_card = {}
    for claim in bundle["claims"]:
        for card in claim.get("cards", []):
            claims_by_card.setdefault(card, []).append(claim)

    expected_cards = {"AV_137", "CATA_479", "WW_336", "WW_391"}
    assert expected_cards <= set(claims_by_card)
    for card_id in expected_cards:
        assert any(
            claim["claim_kind"] in {"card_role", "targeting_rule", "mechanic_usage"}
            and claim.get("runtime_block") in {"BeforePlayCardBonus", "OnBoardBonus"}
            and claim.get("runtime_value")
            for claim in claims_by_card[card_id]
        ), card_id


def test_piraterogue_fixture_covers_pirate_weapon_pressure():
    claims = _claims("PirateRogue")
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert "pirate" in text
    assert any(marker in text for marker in ("weapon", "face", "tempo", "pressure"))


def test_piraterogue_fixture_closes_known_source_claim_gaps():
    bundle = _source_bundle_for_fixture("PirateRogue")
    claims_by_card = {}
    for claim in bundle["claims"]:
        for card in claim.get("cards", []):
            claims_by_card.setdefault(card, []).append(claim)

    expected_cards = {
        "CFM_637",
        "CORE_NEW1_027",
        "CS2_073",
        "DMF_519",
        "DRG_056",
        "NX2_006",
        "TOY_505",
        "TOY_518",
        "TTN_922",
        "VAC_938",
    }
    assert expected_cards <= set(claims_by_card)
    assert any(
        claim.get("runtime_block") == "OnBoardBonus"
        for claim in claims_by_card["CORE_NEW1_027"]
    )
    assert any(
        claim.get("runtime_block") == "BeforePlayCardBonus"
        for claim in claims_by_card["CS2_073"]
    )
    assert any(
        claim.get("runtime_block") == "BeforeBattlecryTargetBonus"
        for claim in claims_by_card["DMF_519"]
    )
    assert any(
        claim.get("runtime_block") == "BeforePhysicalAttackBonus"
        for claim in claims_by_card["NX2_006"]
    )


def test_treantdruid_fixture_covers_token_board_snowball():
    claims = _claims("TreantDruid")
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert any(marker in text for marker in ("treant", "token", "wide board", "board buff"))


def test_treantdruid_source_fixture_has_runtime_lowerable_token_and_board_buff_claims():
    claims = _claims("TreantDruid")
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") in {"treant", "token_board"}
        and claim.get("runtime_block") == "BeforePlayCardBonus"
        and claim.get("runtime_value")
        for claim in claims
    )
    assert any(
        claim["claim_kind"] == "card_role"
        and str(claim.get("stance", "")).lower() in {"board_buff", "board_buff_finisher"}
        and claim.get("runtime_block") in {"BeforePlayCardBonus", "OnBoardBonus"}
        and claim.get("runtime_value")
        for claim in claims
    )


def test_treantdruid_fixture_closes_remaining_guide_claim_gaps():
    bundle = _source_bundle_for_fixture("TreantDruid")
    claims_by_card = {}
    for claim in bundle["claims"]:
        for card in claim.get("cards", []):
            claims_by_card.setdefault(card, []).append(claim)

    expected_cards = {
        "CFM_614",
        "DRG_314",
        "END_009",
        "GDB_852",
        "GIL_663",
        "MIS_301",
        "REV_307",
        "SW_422",
        "TTN_950",
    }
    assert expected_cards <= set(claims_by_card)
    for card_id in expected_cards:
        assert any(
            claim["claim_kind"] in {"card_role", "targeting_rule", "mechanic_usage"}
            and claim.get("runtime_block") in {"BeforePlayCardBonus", "OnBoardBonus"}
            and claim.get("runtime_value")
            for claim in claims_by_card[card_id]
        ), card_id


def test_mechpala_fixture_covers_mech_board_scaling():
    claims = _claims("MechPala")
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert "mech" in text
    assert any(marker in text for marker in ("magnetic", "board", "scaling", "buff"))


def test_boarlock_fixture_covers_combo_resource_setup():
    claims = _claims("Boarlock")
    kinds = {claim["claim_kind"] for claim in claims}
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert any(marker in text for marker in ("combo", "resource", "setup", "boar"))
    assert {"card_role", "gameplan_posture"} <= kinds


def test_boarlock_static_combo_claim_stays_diagnostic_only_without_exact_receipt():
    bundle = _source_bundle_for_fixture("Boarlock")
    combo_claims = [
        claim for claim in bundle["claims"] if claim["claim_kind"] == "combo_sequence"
    ]

    matching_claim = next(
        (
            claim
            for claim in combo_claims
            if claim.get("sequence") == ["SW_075", "UNG_832", "DINO_402", "ULD_717"]
            and claim.get("timing_kind") == "same_turn"
            and claim.get("operator") == ">>"
            and claim.get("values") == ["1", "4", "8", "1"]
        ),
        None,
    )
    assert matching_claim is not None
    assert matching_claim["claim_readiness"] == "source_backed_static_semantics"
    assert matching_claim["source_refs"][0].startswith("source:")
    assert matching_claim["source_refs"][1:3] == [
        "https://www.hearthpwn.com/decks/1455610-elwynn-boar-sneak-attack-otk",
        "https://www.hsguru.com/deck/34322767",
    ]

    deck_cards = {
        str(card["card_id"])
        for card in decode_deck_code(
            next(row for row in _matrix()["decks"] if row["deck_name"] == "Boarlock")[
                "deck_code"
            ]
        )["cards"]
    }
    combo_plan = build_combo_plan(deck_cards=deck_cards, claims=combo_claims)

    assert not any(
        combo.get("combo") == "SW_075>>UNG_832>>DINO_402>>ULD_717"
        for combo in combo_plan["combos"]
    )
    assert {
        "claim_id": matching_claim["claim_id"],
        "cards": ["SW_075", "UNG_832", "DINO_402", "ULD_717"],
        "reason": "combo_requires_public_guide_source",
    } in combo_plan["suppressed"]


def test_piratedh_fixture_covers_pirate_hero_attack_pressure():
    claims = _claims("PirateDH")
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert "pirate" in text
    assert any(marker in text for marker in ("hero attack", "weapon", "face", "tempo"))


def test_piratedh_fixture_has_runtime_lowerable_hero_attack_claims():
    claims = _claims("PirateDH")
    assert any(
        claim["claim_kind"] == "mechanic_usage"
        and claim.get("mechanic") == "hero_attack"
        and claim.get("runtime_block") == "BeforePhysicalAttackBonus"
        and claim.get("runtime_value")
        for claim in claims
    )


def test_piratedh_fixture_closes_runtime_surfaces_for_support_cards():
    claims = _claims("PirateDH")
    claims_by_card = {}
    for claim in claims:
        for card in claim.get("cards", []):
            claims_by_card.setdefault(card, []).append(claim)

    expected_cards = {
        "AV_661",
        "BT_753",
        "CFM_637",
        "DRG_056",
        "NX2_050",
        "SCH_356",
        "TOY_518",
        "VAC_938",
    }
    for card_id in expected_cards:
        assert any(
            claim.get("runtime_block") in {"BeforePlayCardBonus", "BeforePhysicalAttackBonus", "OnBoardBonus"}
            and claim.get("runtime_value")
            for claim in claims_by_card.get(card_id, [])
        ), card_id
    assert any(
        claim["claim_kind"] == "targeting_rule"
        and claim.get("stance") == "prefer_enemy_hero"
        and claim.get("runtime_block") == "BeforePhysicalAttackBonus"
        and claim.get("runtime_value")
        for claim in claims
    )
