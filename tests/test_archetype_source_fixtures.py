import json
from pathlib import Path


FIXTURES = {
    "ShadowPriest": Path("tests/fixtures/source_documents_shadowpriest_strong.json"),
    "BigShaman": Path("tests/fixtures/source_documents_bigshaman_strong.json"),
    "Discolock": Path("tests/fixtures/source_documents_discolock_strong.json"),
    "Kingslayer": Path("tests/fixtures/source_documents_kingslayer_strong.json"),
    "ImbueMage": Path("tests/fixtures/source_documents_imbuemage_strong.json"),
}
SUPPORTED_CLAIM_KINDS = {
    "mulligan_keep",
    "mulligan_discard",
    "card_role",
    "targeting_rule",
    "combo_sequence",
    "gameplan_posture",
    "hero_power_transform",
    "mechanic_usage",
    "known_bad_pattern",
    "discover_choice",
    "choose_one_choice",
}


def _documents(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["source_documents"] if isinstance(payload, dict) else payload


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
            }
            assert document["retrieved_at"]
            assert isinstance(document["claims"], list)
            assert document["claims"]


def test_core_source_fixtures_use_supported_atomic_claims():
    for deck_name, path in FIXTURES.items():
        claim_kinds = {
            claim["claim_kind"]
            for document in _documents(path)
            for claim in document["claims"]
        }
        assert claim_kinds <= SUPPORTED_CLAIM_KINDS
        assert "gameplan_posture" in claim_kinds
        assert {"mulligan_keep", "card_role"} & claim_kinds


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


def test_bigshaman_fixture_covers_big_cheat_and_bad_target_patterns():
    claims = [
        claim
        for document in _documents(FIXTURES["BigShaman"])
        for claim in document["claims"]
    ]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    kinds = {claim["claim_kind"] for claim in claims}
    assert {"card_role", "known_bad_pattern"} & kinds
    assert any(marker in text for marker in ("recruit", "big", "deathrattle", "cheat"))
    assert any(marker in text for marker in ("friendly", "own minion", "not enemy"))


def test_discolock_fixture_covers_discard_and_hand_mutation():
    claims = [
        claim
        for document in _documents(FIXTURES["Discolock"])
        for claim in document["claims"]
    ]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert "discard" in text
    assert any(claim["claim_kind"] in {"mechanic_usage", "known_bad_pattern"} for claim in claims)


def test_kingslayer_fixture_covers_weapon_sequence_pressure():
    claims = [
        claim
        for document in _documents(FIXTURES["Kingslayer"])
        for claim in document["claims"]
    ]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert any(marker in text for marker in ("weapon", "attack", "kingsbane", "kingslayer"))
    assert any(
        claim["claim_kind"] in {"targeting_rule", "mechanic_usage", "card_role"}
        for claim in claims
    )


def test_imbuemage_fixture_covers_hero_power_and_generation():
    claims = [
        claim
        for document in _documents(FIXTURES["ImbueMage"])
        for claim in document["claims"]
    ]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    kinds = {claim["claim_kind"] for claim in claims}
    assert any(marker in text for marker in ("imbue", "hero power", "spell", "generate", "discover"))
    assert {"hero_power_transform", "mechanic_usage", "discover_choice"} & kinds
