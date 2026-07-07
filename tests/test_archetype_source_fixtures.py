import json
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hsconfig.deck_identity import build_deck_identity
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


FIXTURES = {
    "ShadowPriest": Path("tests/fixtures/source_documents_shadowpriest_strong.json"),
    "BigShaman": Path("tests/fixtures/source_documents_bigshaman_strong.json"),
    "Discolock": Path("tests/fixtures/source_documents_discolock_strong.json"),
    "Kingslayer": Path("tests/fixtures/source_documents_kingslayer_strong.json"),
    "ImbueMage": Path("tests/fixtures/source_documents_imbuemage_strong.json"),
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
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _core_matrix_rows() -> list[dict]:
    rows = [
        row
        for row in _matrix()["decks"]
        if row["fixture_stage"] == "core_source_backed_fixture"
    ]
    assert {row["deck_name"] for row in rows} == set(FIXTURES)
    return rows


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
        decoded_deck = decode_deck_code(row["deck_code"])
        deck_identity = build_deck_identity(
            deck_name=row["deck_name"],
            deck_code=row["deck_code"],
            cards=decoded_deck["cards"],
            hero_dbf_id=decoded_deck["hero_dbf_id"],
            format=decoded_deck["format"],
            sideboards=decoded_deck["sideboards"],
        )

        bundle = build_source_document_bundle(
            deck_identity=deck_identity,
            card_metadata={"cards": decoded_deck["cards"]},
            source_documents=_documents(FIXTURES[row["deck_name"]]),
            current_date="2026-07-07",
        )

        assert bundle["claims"], row["deck_name"]
        assert bundle["unsupported_claims"] == [], row["deck_name"]
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
