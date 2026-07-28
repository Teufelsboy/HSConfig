from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import hsconfig.source_acquisition as source_acquisition
from hsconfig.audited_deck_catalog import load_audited_role_manifest
from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.card_metadata import (
    analysis_cards_from_deck_identity,
    hydrate_card_metadata,
)
from hsconfig.cli import main
from hsconfig.deck_identity import build_deck_identity
from hsconfig.deckstring_decode import _parse_deckstring, decode_deck_code
from hsconfig.input_loading import source_records_from_cards
from hsconfig.io import write_json
from hsconfig.strict_package_validation import validate_complete_package
from tests.helpers.fixture_prepare import prepare_fixture_deck, read_json


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
SUPPLEMENTAL_PATH = Path("docs/operator/supplemental-proof-decks.json")
AUDITED_CATALOG_PATH = Path("docs/operator/audited-deck-catalog.json")
AUDITED_CARD_DB_PATH = Path("tests/fixtures/audited_deck_card_db.json")
DIAGNOSTIC_APPLY_REASON = "diagnostic_source_not_apply_eligible"
CARD_METADATA_KEYS = {"ConfigComment", "GameCardId"}
FORBIDDEN_LEGACY_RUNTIME_SURFACES = frozenset(
    {"CardBehavior.json", "Concede.json", "Presume.json"}
)
AUDITED_CARD_DB_SNAPSHOT_SHA256 = (
    "sha256:8ce0192a62b9c94147c8ccab1770699f9c07cbe65f94614b18d9572630a8a8d0"
)
AUDITED_CARD_DB_METADATA = {
    "captured_at": "2026-07-27T16:45:03Z",
    "snapshot_sha256": AUDITED_CARD_DB_SNAPSHOT_SHA256,
    "source_build": 247416,
    "source_identifier": "HearthstoneJSON:247416:CardDefs.xml",
    "source_url": "https://api.hearthstonejson.com/v1/247416/CardDefs.xml",
    "upstream_raw_sha256": (
        "sha256:a3b0e3dcd112626aa47ba16ede1b26506eed175b1fda288c1b6952065c06aac4"
    ),
}
# Test-only identity mapping for visibility deck decoding. These rows are not part of
# the audited 192-row semantic snapshot and must never be used as semantic evidence.
VISIBILITY_IDENTITY_DECODE_ONLY_CARD_IDS = {
    1783: "FP1_004",
    2551: "AT_012",
    39767: "KAR_092",
    40299: "CFM_066",
    40323: "CFM_020",
    40373: "CFM_603",
    40583: "CFM_760",
    41173: "UNG_032",
    43408: "ICC_830",
    53756: "ULD_003",
    53822: "ULD_240",
    59029: "SCH_311",
    61585: "DMF_107",
    61944: "YOP_006",
    62879: "BAR_315",
    69566: "CORE_EX1_193",
    69607: "CORE_EX1_287",
    69702: "CORE_UNG_020",
    70020: "AV_324",
    70027: "AV_331",
    71781: "TSC_908",
    72007: "TSC_032",
    76314: "CORE_LOE_011",
    77305: "REV_249",
    78371: "REV_513",
    79486: "REV_841",
    84351: "MAW_101",
    86235: "CORE_LOOT_101",
    86626: "RLK_222",
    90749: "ETC_080",
    94822: "JAM_036",
    95336: "JAM_001",
    98403: "TTN_742",
    98413: "JAM_027",
    101955: "WW_384",
    101958: "WW_387",
    102221: "CORE_SW_072",
    102225: "CORE_CFM_790",
    102592: "WON_058",
    102718: "CORE_SW_448",
}
EXPECTED_AUDITED_DECK_CATALOG = [
    {
        "deck_name": "ShadowPriest",
        "deck_code": (
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
            "KgG17oG1cEGAAA="
        ),
        "hs_id": "2737726722",
        "hdt_deck_id": "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602",
        "matrix_role": "representative",
    },
    {
        "deck_name": "CtAPaladin",
        "deck_code": (
            "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQF"
            "hY4GmY4G9ZUGmvwHAAA="
        ),
        "hs_id": "2737744316",
        "hdt_deck_id": "f9b54950-ca24-48cf-805e-bf620eab47a0",
        "matrix_role": "representative",
    },
    {
        "deck_name": "PirateRogue",
        "deck_code": (
            "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQ"
            "b8qAatxQYAAA=="
        ),
        "hs_id": "2740734095",
        "hdt_deck_id": "c1e87d43-5802-460b-b955-31ae458eb41a",
        "matrix_role": "representative",
    },
    {
        "deck_name": "BigShaman",
        "deck_code": (
            "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmA"
            "bGpgakpwb44gas/QYAAA=="
        ),
        "hs_id": "2737735409",
        "hdt_deck_id": "6b26f907-6f1e-44c8-a4e4-d14e9d51f819",
        "matrix_role": "representative",
    },
    {
        "deck_name": "Discolock",
        "deck_code": (
            "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8"
            "ayB9a+B9m+B8+/BwAA"
        ),
        "hs_id": "2740357533",
        "hdt_deck_id": "55241397-ac74-4d46-a662-089e5858839c",
        "matrix_role": "representative",
    },
    {
        "deck_name": "TreantDruid",
        "deck_code": (
            "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+g"
            "XZ/wXJ0Aat4gYAAA=="
        ),
        "hs_id": "2740360895",
        "hdt_deck_id": "a120a28b-1840-4032-a3c9-2da4c51338ed",
        "matrix_role": "representative",
    },
    {
        "deck_name": "ImbueMage",
        "deck_code": (
            "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94"
            "EHs4cHwIcH7o0HAAA="
        ),
        "hs_id": "2740361888",
        "hdt_deck_id": "49c05560-8b30-4d06-b3a2-a8b0ff36d005",
        "matrix_role": "representative",
    },
    {
        "deck_name": "MechPala",
        "deck_code": (
            "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Q"
            "bi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="
        ),
        "hs_id": "2740734214",
        "hdt_deck_id": "8f011f55-8ae2-436c-b53a-315f280e8833",
        "matrix_role": "representative",
    },
    {
        "deck_name": "Kingslayer",
        "deck_code": (
            "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/K"
            "UG/KgGs8EG6sQGrcUGAAA="
        ),
        "hs_id": "2740733989",
        "hdt_deck_id": "1292ff02-8ebe-47a5-90b1-9a1899acd6aa",
        "matrix_role": "representative",
    },
    {
        "deck_name": "Boarlock",
        "deck_code": (
            "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBY"
            "SeBpWzBpTKBoSZB4adBwAA"
        ),
        "hs_id": "2740361505",
        "hdt_deck_id": "7727c718-c93c-47ca-a766-5612c3806f0f",
        "matrix_role": "representative",
    },
    {
        "deck_name": "PirateDH",
        "deck_code": (
            "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqg"
            "X8qAbYwAb2wAatxQax6wYAAA=="
        ),
        "hs_id": "2737737281",
        "hdt_deck_id": "2bc184ed-b59a-4420-900d-b0ed3d153979",
        "matrix_role": "representative",
    },
    {
        "deck_name": "CuteWarrior",
        "deck_code": (
            "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFov"
            "oF/KgGltMGtI8HAAA="
        ),
        "hs_id": "2750150375",
        "hdt_deck_id": "a753f091-b770-4a06-8da8-59f1d5269f6b",
        "matrix_role": "supplemental",
    },
]


def test_network_fence_denies_direct_source_acquisition_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = _install_read_only_isolation(monkeypatch)

    with pytest.raises(AssertionError):
        source_acquisition.getaddrinfo("alias.example", None)
    with pytest.raises(AssertionError):
        source_acquisition.create_connection(("93.184.216.34", 443), 1.0)
    with pytest.raises(AssertionError):
        source_acquisition._default_resolver("resolver.example")

    assert attempts == {
        "external_network": [
            "alias.example",
            "('93.184.216.34', 443)",
            "resolver.example",
        ],
        "runtime_write": [],
    }


def _required_snapshot_dbf_ids() -> set[int]:
    matrix, supplemental = _catalog_payloads()
    decks = _validate_audited_deck_catalog(matrix, supplemental)
    required: set[int] = set()
    for deck in decks:
        parsed = _parse_deckstring(str(deck["deck_code"]))
        required.update(int(dbf_id) for dbf_id, _count in parsed["cards"])
        required.update(int(dbf_id) for dbf_id in parsed["heroes"])
        for sideboard in parsed.get("sideboards", []):
            if isinstance(sideboard, tuple) and len(sideboard) == 3:
                card_dbf_id, _count, owner_dbf_id = sideboard
                required.update((int(card_dbf_id), int(owner_dbf_id)))
    return required


def _visibility_identity_decode_only_dbf_ids() -> set[int]:
    payload = read_json(SUPPLEMENTAL_PATH)
    decks = [
        row
        for row in payload["decks"]
        if row["deck_name"] in {"SecretMage", "HighlanderPriest"}
    ]
    required: set[int] = set()
    for deck in decks:
        parsed = _parse_deckstring(str(deck["deck_code"]))
        required.update(int(dbf_id) for dbf_id, _count in parsed["cards"])
        required.update(int(dbf_id) for dbf_id in parsed["heroes"])
        for sideboard in parsed.get("sideboards", []):
            if isinstance(sideboard, tuple) and len(sideboard) == 3:
                card_dbf_id, _count, owner_dbf_id = sideboard
                required.update((int(card_dbf_id), int(owner_dbf_id)))
    return required


def test_audited_dbf_snapshot_metadata_and_exact_set_are_pinned() -> None:
    payload = read_json(AUDITED_CARD_DB_PATH)
    required = _required_snapshot_dbf_ids()

    cards = _validate_audited_card_db_payload(
        payload,
        required_dbf_ids=required,
    )

    assert payload["schema_version"] == 2
    assert payload["metadata"] == {
        "captured_at": "2026-07-27T16:45:03Z",
        "snapshot_sha256": AUDITED_CARD_DB_SNAPSHOT_SHA256,
        "source_build": 247416,
        "source_identifier": "HearthstoneJSON:247416:CardDefs.xml",
        "source_url": ("https://api.hearthstonejson.com/v1/247416/CardDefs.xml"),
        "upstream_raw_sha256": (
            "sha256:a3b0e3dcd112626aa47ba16ede1b26506eed175b1fda288c1b6952065c06aac4"
        ),
    }
    assert len(required) == 192
    assert {int(row[0]) for row in cards} == required
    assert len({str(row[1]) for row in cards}) == 192


def test_visibility_identity_decode_overlay_is_exact_and_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = read_json(AUDITED_CARD_DB_PATH)
    audited_dbf_ids = {int(row[0]) for row in payload["cards"]}
    visibility_dbf_ids = _visibility_identity_decode_only_dbf_ids()

    assert len(audited_dbf_ids) == 192
    assert len(visibility_dbf_ids) == 49
    assert len(visibility_dbf_ids - audited_dbf_ids) == 40
    assert set(VISIBILITY_IDENTITY_DECODE_ONLY_CARD_IDS) == (
        visibility_dbf_ids - audited_dbf_ids
    )
    assert len(set(VISIBILITY_IDENTITY_DECODE_ONLY_CARD_IDS.values())) == 40

    decoder_db = _audited_card_db()
    assert set(decoder_db) == audited_dbf_ids | visibility_dbf_ids
    monkeypatch.setattr(
        "hsconfig.deckstring_decode.cardxml.load_dbf",
        lambda: (decoder_db, None),
    )

    supplemental = read_json(SUPPLEMENTAL_PATH)
    visibility_decks = [
        row
        for row in supplemental["decks"]
        if row["deck_name"] in {"SecretMage", "HighlanderPriest"}
    ]
    for deck in visibility_decks:
        decoded = decode_deck_code(str(deck["deck_code"]))
        assert decoded["card_count_total"] == 30
        assert decoded["unresolved_card_count"] == 0
        assert decoded["sideboard_count"] == (
            3 if deck["deck_name"] == "HighlanderPriest" else 0
        )
        identity_only_cards = [
            card
            for card in decoded["cards"]
            if card["dbf_id"] in VISIBILITY_IDENTITY_DECODE_ONLY_CARD_IDS
        ]
        generic_identity_only_card = {
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
        assert identity_only_cards
        assert all(card["deckstring_identity_only"] is True for card in identity_only_cards)
        assert source_records_from_cards(
            [
                *identity_only_cards,
                generic_identity_only_card,
                {
                    "card_id": "ORDINARY_SOURCE_CONTROL",
                    "name": "Ordinary Source Control",
                    "type": "MINION",
                    "text": "Battlecry: Draw a card.",
                },
            ]
        ) == {
            "ORDINARY_SOURCE_CONTROL": {
                "name": "Ordinary Source Control",
                "type": "MINION",
                "text": "Battlecry: Draw a card.",
            }
        }
        deck_identity = build_deck_identity(
            deck_name=deck["deck_name"],
            deck_code=deck["deck_code"],
            cards=[
                *identity_only_cards,
                generic_identity_only_card,
                {
                    "card_id": "ORDINARY_SOURCE_CONTROL",
                    "dbf_id": 123456,
                    "count": 1,
                    "name": "Ordinary Source Control",
                    "type": "MINION",
                    "text": "Battlecry: Draw a card.",
                },
            ],
        )
        analysis_cards = analysis_cards_from_deck_identity(deck_identity)
        source_records = source_records_from_cards(analysis_cards)
        assert source_records == {
            "ORDINARY_SOURCE_CONTROL": {
                "name": "Ordinary Source Control",
            }
        }
        hydrated = hydrate_card_metadata(
            cards=analysis_cards,
            source_records=source_records,
        )
        hydrated_identity_only = next(
            card
            for card in hydrated["cards"]
            if card["card_id"] == "IDENTITY_ONLY"
        )
        assert hydrated_identity_only["metadata_status"] == "missing_source_record"
        assert hydrated_identity_only["source_record_key"] is None
        assert {"secret", "secret_timing"}.isdisjoint(
            hydrated_identity_only["mechanic_families"]
        )


def test_audited_dbf_snapshot_rejects_malformed_schema_or_metadata() -> None:
    required = _required_snapshot_dbf_ids()
    payload = read_json(AUDITED_CARD_DB_PATH)

    malformed_schema = deepcopy(payload)
    malformed_schema["schema_version"] = 1
    with pytest.raises(ValueError, match="snapshot_schema_invalid"):
        _validate_audited_card_db_payload(
            malformed_schema,
            required_dbf_ids=required,
        )

    missing_metadata = deepcopy(payload)
    del missing_metadata["metadata"]["source_build"]
    with pytest.raises(ValueError, match="snapshot_metadata_invalid"):
        _validate_audited_card_db_payload(
            missing_metadata,
            required_dbf_ids=required,
        )

    mutable_source = deepcopy(payload)
    mutable_source["metadata"]["source_url"] = (
        "https://api.hearthstonejson.com/v1/latest/CardDefs.xml"
    )
    with pytest.raises(ValueError, match="snapshot_metadata_invalid"):
        _validate_audited_card_db_payload(
            mutable_source,
            required_dbf_ids=required,
        )


def test_audited_dbf_snapshot_rejects_duplicate_dbf_or_card_id() -> None:
    required = _required_snapshot_dbf_ids()
    payload = read_json(AUDITED_CARD_DB_PATH)

    duplicate_dbf = deepcopy(payload)
    duplicate_dbf_row = deepcopy(duplicate_dbf["cards"][0])
    duplicate_dbf_row[1] = "UNIQUE_CARD_ID"
    duplicate_dbf["cards"].append(duplicate_dbf_row)
    with pytest.raises(ValueError, match="snapshot_duplicate_dbf_id"):
        _validate_audited_card_db_payload(
            duplicate_dbf,
            required_dbf_ids=required,
        )

    duplicate_card_id = deepcopy(payload)
    duplicate_card_id_row = deepcopy(duplicate_card_id["cards"][0])
    duplicate_card_id_row[0] = 999_998
    duplicate_card_id["cards"].append(duplicate_card_id_row)
    with pytest.raises(ValueError, match="snapshot_duplicate_card_id"):
        _validate_audited_card_db_payload(
            duplicate_card_id,
            required_dbf_ids=required,
        )


def test_audited_dbf_snapshot_rejects_missing_or_extra_dbf_id() -> None:
    required = _required_snapshot_dbf_ids()
    payload = read_json(AUDITED_CARD_DB_PATH)

    missing = deepcopy(payload)
    missing["cards"].pop()
    with pytest.raises(ValueError, match="snapshot_dbf_set_mismatch"):
        _validate_audited_card_db_payload(
            missing,
            required_dbf_ids=required,
        )

    extra = deepcopy(payload)
    extra_row = deepcopy(extra["cards"][0])
    extra_row[0] = 999_999
    extra_row[1] = "EXTRA_CARD_ID"
    extra["cards"].append(extra_row)
    with pytest.raises(ValueError, match="snapshot_dbf_set_mismatch"):
        _validate_audited_card_db_payload(
            extra,
            required_dbf_ids=required,
        )


def test_audited_dbf_snapshot_rejects_malformed_row_or_hash_drift() -> None:
    required = _required_snapshot_dbf_ids()
    payload = read_json(AUDITED_CARD_DB_PATH)

    malformed_row = deepcopy(payload)
    malformed_row["cards"][0] = malformed_row["cards"][0][:-1]
    with pytest.raises(ValueError, match="snapshot_card_row_invalid"):
        _validate_audited_card_db_payload(
            malformed_row,
            required_dbf_ids=required,
        )

    corrupt_content = deepcopy(payload)
    corrupt_content["cards"][0][2] = "Corrupt Name"
    with pytest.raises(ValueError, match="snapshot_sha256_mismatch"):
        _validate_audited_card_db_payload(
            corrupt_content,
            required_dbf_ids=required,
        )

    corrupt_expected_hash = deepcopy(payload)
    corrupt_expected_hash["metadata"]["snapshot_sha256"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValueError, match="snapshot_sha256_mismatch"):
        _validate_audited_card_db_payload(
            corrupt_expected_hash,
            required_dbf_ids=required,
        )


def _snapshot_sha256(payload: Mapping[str, Any]) -> str:
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("snapshot_metadata_invalid")
    digest_payload = {
        "cards": payload.get("cards"),
        "metadata": {
            str(key): value
            for key, value in metadata.items()
            if key != "snapshot_sha256"
        },
        "schema_version": payload.get("schema_version"),
    }
    canonical = json.dumps(
        digest_payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def _validate_audited_card_db_payload(
    payload: Mapping[str, Any],
    *,
    required_dbf_ids: set[int],
) -> list[list[Any]]:
    if payload.get("schema_version") != 2:
        raise ValueError("snapshot_schema_invalid")
    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("snapshot_metadata_invalid")
    metadata_without_hash = {
        str(key): value for key, value in metadata.items() if key != "snapshot_sha256"
    }
    expected_without_hash = {
        key: value
        for key, value in AUDITED_CARD_DB_METADATA.items()
        if key != "snapshot_sha256"
    }
    if (
        set(metadata) != set(AUDITED_CARD_DB_METADATA)
        or metadata_without_hash != expected_without_hash
    ):
        raise ValueError("snapshot_metadata_invalid")
    cards = payload.get("cards")
    if not isinstance(cards, list):
        raise ValueError("snapshot_cards_invalid")

    dbf_ids: set[int] = set()
    card_ids: set[str] = set()
    validated_cards: list[list[Any]] = []
    for row in cards:
        if (
            not isinstance(row, list)
            or len(row) != 8
            or not isinstance(row[0], int)
            or isinstance(row[0], bool)
            or not isinstance(row[1], str)
            or not row[1]
            or not isinstance(row[2], str)
            or not isinstance(row[3], (int, type(None)))
            or isinstance(row[3], bool)
            or not isinstance(row[4], str)
            or not row[4]
            or not isinstance(row[5], str)
            or not row[5]
            or not isinstance(row[6], str)
            or not isinstance(row[7], list)
            or any(not isinstance(mechanic, str) for mechanic in row[7])
        ):
            raise ValueError("snapshot_card_row_invalid")
        dbf_id = int(row[0])
        card_id = str(row[1])
        if dbf_id in dbf_ids:
            raise ValueError("snapshot_duplicate_dbf_id")
        if card_id in card_ids:
            raise ValueError("snapshot_duplicate_card_id")
        dbf_ids.add(dbf_id)
        card_ids.add(card_id)
        validated_cards.append(row)

    if dbf_ids != required_dbf_ids:
        raise ValueError("snapshot_dbf_set_mismatch")
    if (
        metadata.get("snapshot_sha256") != AUDITED_CARD_DB_SNAPSHOT_SHA256
        or _snapshot_sha256(payload) != AUDITED_CARD_DB_SNAPSHOT_SHA256
    ):
        raise ValueError("snapshot_sha256_mismatch")
    return validated_cards


def _audited_card_db() -> dict[int, SimpleNamespace]:
    payload = read_json(AUDITED_CARD_DB_PATH)
    rows = _validate_audited_card_db_payload(
        payload,
        required_dbf_ids=_required_snapshot_dbf_ids(),
    )
    cards: dict[int, SimpleNamespace] = {}
    for row in rows:
        (
            dbf_id,
            card_id,
            name,
            cost,
            card_type,
            card_class,
            text,
            mechanics,
        ) = row
        card = SimpleNamespace(
            card_class=card_class,
            card_id=card_id,
            cost=cost,
            english_description=text,
            english_name=name,
            name=name,
            type=card_type,
        )
        for mechanic in mechanics:
            setattr(card, str(mechanic), True)
        cards[int(dbf_id)] = card
    cards.update(_visibility_identity_decode_only_card_db())
    return cards


def _visibility_identity_decode_only_card_db() -> dict[int, SimpleNamespace]:
    return {
        dbf_id: SimpleNamespace(
            card_class="VISIBILITY_IDENTITY_ONLY",
            card_id=card_id,
            cost=None,
            english_description="",
            english_name=card_id,
            name=card_id,
            type="VISIBILITY_IDENTITY_ONLY",
            deckstring_identity_only=True,
        )
        for dbf_id, card_id in VISIBILITY_IDENTITY_DECODE_ONLY_CARD_IDS.items()
    }


def _install_read_only_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, list[str]]:
    attempts: dict[str, list[str]] = {
        "external_network": [],
        "runtime_write": [],
    }

    def deny_external_network(*args: Any, **kwargs: Any) -> None:
        del kwargs
        attempts["external_network"].append(str(args[0]) if args else "unknown")
        raise AssertionError("external network access is forbidden in acceptance tests")

    def no_cardfeed(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        del args, kwargs
        return []

    def deny_runtime_write(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        attempts["runtime_write"].append("apply_package")
        raise AssertionError("runtime writes are forbidden in acceptance tests")

    monkeypatch.setattr("hsconfig.hearthstonejson.urlopen", deny_external_network)
    monkeypatch.setattr("socket.create_connection", deny_external_network)
    monkeypatch.setattr("socket.getaddrinfo", deny_external_network)
    monkeypatch.setattr(
        "hsconfig.source_acquisition.create_connection",
        deny_external_network,
    )
    monkeypatch.setattr(
        "hsconfig.source_acquisition.getaddrinfo",
        deny_external_network,
    )
    audited_card_db = _audited_card_db()
    monkeypatch.setattr(
        "hsconfig.deckstring_decode.cardxml.load_dbf",
        lambda: (audited_card_db, None),
    )
    monkeypatch.setattr("hsconfig.hearthstonejson.fetch_latest_cards", no_cardfeed)
    monkeypatch.setattr(
        "hsconfig.hearthstonejson.fetch_latest_collectible_cards",
        no_cardfeed,
    )
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", no_cardfeed)
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        no_cardfeed,
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        no_cardfeed,
    )
    monkeypatch.setattr("hsconfig.runtime_apply.apply_package", deny_runtime_write)
    monkeypatch.setattr(
        "hsconfig.commands.apply.apply_package",
        deny_runtime_write,
    )
    return attempts


@pytest.fixture
def read_only_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[dict[str, list[str]]]:
    attempts = _install_read_only_isolation(monkeypatch)

    yield attempts

    assert attempts == {
        "external_network": [],
        "runtime_write": [],
    }


def _catalog_payloads() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        deepcopy(load_audited_role_manifest(MATRIX_PATH)),
        deepcopy(load_audited_role_manifest(SUPPLEMENTAL_PATH)),
    )


def test_audited_deck_catalog_is_the_unique_exact_identity_source() -> None:
    payload = read_json(AUDITED_CATALOG_PATH)
    rows = payload["decks"]

    assert payload["schema_version"] == 1
    assert rows == EXPECTED_AUDITED_DECK_CATALOG
    assert len(rows) == 12
    for field in ("deck_name", "deck_code", "hs_id", "hdt_deck_id"):
        values = [str(row[field]) for row in rows]
        assert all(values)
        assert len(set(values)) == 12
    assert [row["matrix_role"] for row in rows].count("representative") == 11
    assert [row["matrix_role"] for row in rows].count("supplemental") == 1

    for row in rows:
        decoded = decode_deck_code(str(row["deck_code"]))
        assert decoded["card_count"] == 30
        assert decoded["card_count_total"] == 30
        assert decoded["unresolved_card_count"] == 0
        if row["deck_name"] == "MechPala":
            assert decoded["sideboard_count"] == 3
            assert len(decoded["sideboards"]) == 1
            sideboard = decoded["sideboards"][0]
            assert sideboard["owner_card_id"] == "TOY_330"
            assert {card["card_id"] for card in sideboard["cards"]} == {
                "TOY_330t95",
                "TOY_330t98",
                "TOY_330t11",
            }
        else:
            assert decoded["sideboard_count"] == 0
            assert decoded["sideboards"] == []


def test_audited_catalog_requires_exact_manifest_membership() -> None:
    matrix, supplemental = _catalog_payloads()

    audited = _validate_audited_deck_catalog(matrix, supplemental)

    assert len(matrix) == 11
    assert sum(row["deck_name"] == "CuteWarrior" for row in supplemental) == 1
    assert len(audited) == 12
    assert len({row["deck_name"] for row in audited}) == 12
    assert len({row["deck_code"] for row in audited}) == 12


def test_audited_catalog_rejects_missing_matrix_deck_or_cute_warrior() -> None:
    matrix, supplemental = _catalog_payloads()

    with pytest.raises(ValueError):
        _validate_audited_deck_catalog(matrix[:-1], supplemental)
    with pytest.raises(ValueError):
        _validate_audited_deck_catalog(
            matrix,
            [row for row in supplemental if row["deck_name"] != "CuteWarrior"],
        )


def test_audited_catalog_rejects_duplicate_cute_name_or_deck_code() -> None:
    matrix, supplemental = _catalog_payloads()
    cute = next(row for row in supplemental if row["deck_name"] == "CuteWarrior")

    with pytest.raises(ValueError):
        _validate_audited_deck_catalog(matrix, [*supplemental, deepcopy(cute)])

    duplicate_name = deepcopy(matrix)
    duplicate_name[-1]["deck_name"] = duplicate_name[0]["deck_name"]
    with pytest.raises(ValueError):
        _validate_audited_deck_catalog(duplicate_name, supplemental)

    duplicate_code = deepcopy(matrix)
    duplicate_code[-1]["deck_code"] = duplicate_code[0]["deck_code"]
    with pytest.raises(ValueError):
        _validate_audited_deck_catalog(duplicate_code, supplemental)


def _synthetic_cardid_contract(
    *,
    behavior_block: str = "OnBoardBonus",
    source_type: str = "MINION",
    linked_runtime_owner: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    source_card_id = "SOURCE_001"
    runtime_card_id = "RUNTIME_001" if linked_runtime_owner else source_card_id
    linked_entities = (
        [
            {
                "card_id": runtime_card_id,
                "link_kind": "starting_hero_power",
                "type": "HERO_POWER",
            }
        ]
        if linked_runtime_owner
        else []
    )
    semantic = {
        "cards": [
            {
                "card_id": source_card_id,
                "linked_entities": linked_entities,
                "type": source_type,
            }
        ]
    }
    behavior = {
        "rows": [
            {
                "behavior_block": behavior_block,
                "card_id": source_card_id,
                "condition": "friendly",
                "link_kind": (
                    "starting_hero_power" if linked_runtime_owner else "self"
                ),
                "meaningful_runtime_surface": True,
                "runtime_card_id": runtime_card_id,
                "source_card_id": source_card_id,
                "source_claim_ids": ["claim:1"],
                "source_refs": ["source:1"],
                "value": 5,
            }
        ]
    }
    payloads = {
        runtime_card_id: {
            "ConfigComment": "synthetic acceptance payload",
            "GameCardId": runtime_card_id,
            behavior_block: {
                "values": [{"condition": "friendly", "value": 5}],
            },
        }
    }
    return semantic, behavior, payloads


@pytest.mark.parametrize(
    "behavior_block",
    ["OnBoardBonus", "BeforeBattlecryTargetBonus"],
)
def test_spell_cannot_own_board_or_battlecry_target_runtime_surface(
    behavior_block: str,
) -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract(
        behavior_block=behavior_block,
        source_type="SPELL",
    )

    with pytest.raises(AssertionError):
        _assert_cardid_report_contract(semantic, behavior, payloads)


def test_linked_runtime_owner_uses_source_and_runtime_semantic_types() -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract(
        linked_runtime_owner=True,
    )

    _assert_cardid_report_contract(semantic, behavior, payloads)


def test_unlinked_runtime_owner_fails_even_when_both_card_types_are_known() -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract()
    semantic["cards"].append(
        {
            "card_id": "UNRELATED_001",
            "linked_entities": [],
            "type": "HERO_POWER",
        }
    )
    behavior["rows"][0]["runtime_card_id"] = "UNRELATED_001"
    payloads["UNRELATED_001"] = payloads.pop("SOURCE_001")
    payloads["UNRELATED_001"]["GameCardId"] = "UNRELATED_001"

    with pytest.raises(AssertionError):
        _assert_cardid_report_contract(semantic, behavior, payloads)


def test_cardid_parity_rejects_phantom_report_row() -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract()
    phantom = deepcopy(behavior["rows"][0])
    phantom["value"] = 6
    behavior["rows"].append(phantom)

    with pytest.raises(AssertionError):
        _assert_cardid_report_contract(semantic, behavior, payloads)


@pytest.mark.parametrize("duplicate_side", ["physical", "report"])
def test_cardid_parity_preserves_duplicate_rows(duplicate_side: str) -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract()
    if duplicate_side == "physical":
        payloads["SOURCE_001"]["OnBoardBonus"]["values"].append(
            {"condition": "friendly", "value": 5}
        )
    else:
        behavior["rows"].append(deepcopy(behavior["rows"][0]))

    with pytest.raises(AssertionError):
        _assert_cardid_report_contract(semantic, behavior, payloads)


@pytest.mark.parametrize(
    ("field", "drifted_value"),
    [("condition", True), ("value", "5")],
)
def test_cardid_parity_rejects_condition_or_value_type_drift(
    field: str,
    drifted_value: Any,
) -> None:
    semantic, behavior, payloads = _synthetic_cardid_contract()
    behavior["rows"][0][field] = drifted_value

    with pytest.raises(AssertionError):
        _assert_cardid_report_contract(semantic, behavior, payloads)


def _validate_audited_deck_catalog(
    matrix: list[dict[str, Any]],
    supplemental: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(matrix) != 11:
        raise ValueError("audited matrix must contain exactly 11 decks")
    cute_warriors = [
        row for row in supplemental if row.get("deck_name") == "CuteWarrior"
    ]
    if len(cute_warriors) != 1:
        raise ValueError("supplemental catalog must contain CuteWarrior exactly once")
    audited = [*matrix, cute_warriors[0]]
    if len(audited) != 12:
        raise ValueError("audited catalog must contain exactly 12 decks")
    deck_names = [str(row.get("deck_name", "")) for row in audited]
    deck_codes = [str(row.get("deck_code", "")) for row in audited]
    if "" in deck_names or len(set(deck_names)) != len(deck_names):
        raise ValueError("audited deck names must be non-empty and unique")
    if "" in deck_codes or len(set(deck_codes)) != len(deck_codes):
        raise ValueError("audited deck codes must be non-empty and unique")
    return audited


def audited_decks() -> list[dict[str, Any]]:
    matrix = load_audited_role_manifest(MATRIX_PATH)
    supplemental = load_audited_role_manifest(SUPPLEMENTAL_PATH)
    return _validate_audited_deck_catalog(matrix, supplemental)


def _captured_source_documents(deck: Mapping[str, Any]) -> dict[str, Any]:
    fixture_bytes = f"{deck['deck_name']}:diagnostic-fixture".encode()
    return {
        "source_documents": [
            {
                "source_url": "https://example.invalid/diagnostic-fixture",
                "source_title": f"{deck['deck_name']} diagnostic fixture",
                "source_family": "guide",
                "retrieved_at": "2026-07-27T00:00:00Z",
                "acquisition_provenance": {
                    "mode": "captured_record",
                    "authority": "captured_unverified",
                    "content_sha256": f"sha256:{sha256(fixture_bytes).hexdigest()}",
                },
                "source_visibility": "full_text",
                "source_lane": "archetype_matched_public_guide",
                "deck_name": str(deck["deck_name"]),
                "archetype": "diagnostic_fixture",
                "deck_match_scope": "archetype_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 0,
                        "decoded_candidate_count": 0,
                        "matched": False,
                        "matched_deck_fingerprint": "",
                        "candidate_deck_code_hashes": [],
                    }
                },
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "scope": "deck",
                        "cards": [],
                        "stance": "diagnostic_fixture",
                        "evidence_text_short": (
                            "Diagnostic captured source used for read-only acceptance."
                        ),
                        "source_confidence": "medium",
                        "promotion_eligible": False,
                    }
                ],
            }
        ]
    }


def _prepare_audited_deck(
    tmp_path: Path,
    deck: dict[str, Any],
) -> dict[str, Any]:
    runtime_root = tmp_path / "runtime"
    if deck["deck_name"] != "CuteWarrior":
        return {
            **prepare_fixture_deck(tmp_path, deck),
            "runtime_root": runtime_root,
        }

    source_path = tmp_path / "cutewarrior-diagnostic-source.json"
    write_json(source_path, _captured_source_documents(deck))
    out = tmp_path / "CuteWarrior"
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            str(deck["deck_name"]),
            "--deck-code",
            str(deck["deck_code"]),
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--source-documents-json",
            str(source_path),
            "--json",
        ]
    )
    return {
        "exit_code": exit_code,
        "out": out,
        "operator": read_json(out / "reports" / "operator_summary.json"),
        "runtime_root": runtime_root,
    }


def _deck_dir(package: Mapping[str, Any]) -> Path:
    directories = [
        path
        for path in (Path(package["out"]) / "CustomConfig").iterdir()
        if path.is_dir()
    ]
    assert len(directories) == 1
    return directories[0]


def _card_payloads(package: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        path.stem: read_json(path)
        for path in _deck_dir(package).glob("*.json")
        if path.name not in {"GlobalValues.json", "Mulligan.json", "Combo.json"}
    }


def _physical_card_rows(
    payloads: Mapping[str, Mapping[str, Any]],
) -> list[tuple[str, str, tuple[Any, ...], tuple[Any, ...]]]:
    rows: list[tuple[str, str, tuple[Any, ...], tuple[Any, ...]]] = []
    for card_id, payload in payloads.items():
        for block, block_payload in payload.items():
            if block in CARD_METADATA_KEYS or not isinstance(block_payload, Mapping):
                continue
            values = block_payload.get("values", [])
            assert isinstance(values, list)
            for row in values:
                assert isinstance(row, Mapping)
                rows.append(
                    (
                        card_id,
                        block,
                        _canonical_json_value(row.get("condition")),
                        _canonical_json_value(row.get("value")),
                    )
                )
    return rows


def _canonical_json_value(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, list):
        return (
            "list",
            tuple(_canonical_json_value(item) for item in value),
        )
    if isinstance(value, Mapping):
        return (
            "object",
            tuple(
                sorted(
                    (
                        str(key),
                        _canonical_json_value(item),
                    )
                    for key, item in value.items()
                )
            ),
        )
    raise AssertionError(f"unsupported runtime JSON value type: {type(value).__name__}")


def _semantic_card_types_and_links(
    semantic: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, set[str]]]:
    card_types: dict[str, str] = {}
    linked_runtime_ids: dict[str, set[str]] = {}

    def add_card_type(card_id: str, card_type: str) -> None:
        assert card_id
        normalized_type = card_type.strip().upper()
        assert normalized_type
        previous = card_types.get(card_id)
        assert previous in {None, normalized_type}
        card_types[card_id] = normalized_type

    for card in semantic.get("cards", []):
        assert isinstance(card, Mapping)
        source_card_id = str(card.get("card_id", ""))
        add_card_type(source_card_id, str(card.get("type", "")))
        for linked in card.get("linked_entities", []):
            assert isinstance(linked, Mapping)
            runtime_card_id = str(linked.get("card_id", ""))
            add_card_type(runtime_card_id, str(linked.get("type", "")))
            linked_runtime_ids.setdefault(source_card_id, set()).add(runtime_card_id)

    for effect in semantic.get("deckwide_effects", []):
        assert isinstance(effect, Mapping)
        source_card_id = str(effect.get("source_card_id", ""))
        runtime_card_id = str(effect.get("target_card_id", ""))
        add_card_type(runtime_card_id, str(effect.get("target_type", "")))
        linked_runtime_ids.setdefault(source_card_id, set()).add(runtime_card_id)

    return card_types, linked_runtime_ids


def _assert_cardid_report_contract(
    semantic: Mapping[str, Any],
    behavior: Mapping[str, Any],
    payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    card_types, linked_runtime_ids = _semantic_card_types_and_links(semantic)
    report_rows = [
        row
        for row in behavior.get("rows", [])
        if isinstance(row, Mapping) and row.get("meaningful_runtime_surface") is True
    ]

    report_counter = Counter(
        (
            str(row.get("runtime_card_id", row.get("card_id", ""))),
            str(row.get("behavior_block", "")),
            _canonical_json_value(row.get("condition")),
            _canonical_json_value(row.get("value")),
        )
        for row in report_rows
    )
    physical_counter = Counter(_physical_card_rows(payloads))
    assert physical_counter == report_counter

    for row in report_rows:
        source_card_id = str(row.get("source_card_id", row.get("card_id", "")))
        runtime_card_id = str(row.get("runtime_card_id", row.get("card_id", "")))
        assert str(row.get("card_id", "")) == source_card_id
        assert source_card_id in card_types
        assert runtime_card_id in card_types
        if runtime_card_id != source_card_id:
            assert runtime_card_id in linked_runtime_ids.get(source_card_id, set())
        if row.get("behavior_block") in {
            "OnBoardBonus",
            "BeforeBattlecryTargetBonus",
        }:
            assert card_types[source_card_id] != "SPELL"
            assert card_types[runtime_card_id] != "SPELL"
        assert row.get("source_claim_ids")
        assert row.get("source_refs")


def _mulligan_hold_cards(package: Mapping[str, Any]) -> set[str]:
    mulligan = read_json(_deck_dir(package) / "Mulligan.json")
    return {
        str(row["mulligan"])
        for row in mulligan["Mulligan"]["values"]
        if row.get("value") == "hold"
    }


def _assert_global_semantic_invariants(package: Mapping[str, Any]) -> None:
    out = Path(package["out"])
    reports = out / "reports"
    semantic = read_json(reports / "semantic_enrichment_report.json")
    behavior = read_json(reports / "card_behavior_plan_report.json")
    mulligan_plan = read_json(reports / "mulligan_plan_report.json")
    payloads = _card_payloads(package)
    _assert_cardid_report_contract(semantic, behavior, payloads)

    card_condition_suppressions = {
        str(row["claim_id"])
        for row in behavior["suppressed"]
        if "condition" in str(row.get("reason", ""))
        and (
            str(row.get("reason", "")).endswith("_not_encoded")
            or "unsupported" in str(row.get("reason", ""))
        )
    }
    emitted_card_claims = {
        str(claim_id)
        for row in behavior["rows"]
        for claim_id in row.get("source_claim_ids", [])
    }
    assert card_condition_suppressions.isdisjoint(emitted_card_claims)

    mulligan_condition_suppressions = {
        str(row["claim_id"])
        for row in mulligan_plan["suppressed_rules"]
        if row.get("reason") == "unsupported_mulligan_condition"
    }
    emitted_mulligan_claims = {
        str(claim_id)
        for row in mulligan_plan["rules"]
        for claim_id in row.get("source_claim_ids", [])
    }
    assert mulligan_condition_suppressions.isdisjoint(emitted_mulligan_claims)


def _assert_warning_only_mechanic_visible(
    package: Mapping[str, Any],
    *,
    mechanic: str,
    expected_card_ids: set[str],
) -> None:
    reports = Path(package["out"]) / "reports"
    semantic = read_json(reports / "semantic_enrichment_report.json")
    warning_only_card_ids = {
        str(card["card_id"])
        for card in semantic["cards"]
        if mechanic in card.get("warning_only_mechanics", [])
    }
    assert expected_card_ids <= warning_only_card_ids

    if not warning_only_card_ids:
        return
    summary = read_json(reports / "operator_summary.json")
    visible_warning_mechanics = {
        str(row["mechanic"])
        for row in summary["mechanic_visibility_summary"]["warning_boundaries"]
    }
    assert mechanic in visible_warning_mechanics


def _assert_suppressed_card_semantics_absent(
    package: Mapping[str, Any],
    *,
    expected_by_reason: Mapping[str, set[str]],
) -> None:
    reports = Path(package["out"]) / "reports"
    behavior = read_json(reports / "card_behavior_plan_report.json")
    emitted_claim_ids = {
        str(claim_id)
        for row in behavior["rows"]
        for claim_id in row.get("source_claim_ids", [])
    }

    for reason, expected_card_ids in expected_by_reason.items():
        matching_rows = [
            row for row in behavior["suppressed"] if row.get("reason") == reason
        ]
        visible_card_ids = {
            str(card_id) for row in matching_rows for card_id in row.get("cards", [])
        }
        suppressed_claim_ids = {
            str(row["claim_id"])
            for row in matching_rows
            if expected_card_ids.intersection(
                str(card_id) for card_id in row.get("cards", [])
            )
        }
        assert expected_card_ids <= visible_card_ids
        assert suppressed_claim_ids
        assert suppressed_claim_ids.isdisjoint(emitted_claim_ids)


def _assert_forbidden_semantic_conditions_absent(
    package: Mapping[str, Any],
    *,
    mechanics: set[str],
) -> None:
    behavior = read_json(
        Path(package["out"]) / "reports" / "card_behavior_plan_report.json"
    )
    assert all(
        not (
            isinstance(row.get("condition"), Mapping)
            and row["condition"].get("unsupported_semantic") in mechanics
        )
        for row in behavior["rows"]
    )


def _assert_no_inferred_combo(package: Mapping[str, Any]) -> None:
    reports = Path(package["out"]) / "reports"
    combo_plan = read_json(reports / "combo_plan_report.json")
    assert combo_plan["combos"] == []
    assert not (_deck_dir(package) / "Combo.json").exists()


def _assert_ctapaladin_semantic_boundary(package: Mapping[str, Any]) -> None:
    _assert_warning_only_mechanic_visible(
        package,
        mechanic="secret_timing",
        expected_card_ids={"EX1_136", "GIL_903", "DMF_236", "BAR_875"},
    )
    _assert_suppressed_card_semantics_absent(
        package,
        expected_by_reason={
            "semantic_surface_not_proven": {"DMF_236", "EX1_136"},
            "semantic_surface_not_expressible": {"GIL_903"},
            "trigger_owner_does_not_attack": {"BAR_875"},
        },
    )
    _assert_forbidden_semantic_conditions_absent(
        package,
        mechanics={"secret_timing"},
    )


def _assert_piraterogue_semantic_boundary(package: Mapping[str, Any]) -> None:
    _assert_no_inferred_combo(package)
    _assert_warning_only_mechanic_visible(
        package,
        mechanic="dredge",
        expected_card_ids={"TSC_086"},
    )
    _assert_suppressed_card_semantics_absent(
        package,
        expected_by_reason={
            "dredge_condition_not_encoded": {"TSC_086"},
            "combo_target_condition_not_encoded": {"CS2_073"},
            "combo_count_condition_not_encoded": {"DMF_519"},
            "hand_position_condition_not_encoded": {"TTN_922"},
        },
    )
    _assert_forbidden_semantic_conditions_absent(
        package,
        mechanics={"combo_sequence", "dredge", "hand_position"},
    )


def _assert_bigshaman_semantic_boundary(package: Mapping[str, Any]) -> None:
    _assert_no_inferred_combo(package)
    _assert_warning_only_mechanic_visible(
        package,
        mechanic="location_activation",
        expected_card_ids={"TOY_507"},
    )
    _assert_warning_only_mechanic_visible(
        package,
        mechanic="board_position",
        expected_card_ids=set(),
    )
    _assert_suppressed_card_semantics_absent(
        package,
        expected_by_reason={
            "semantic_surface_not_proven": {"TOY_507"},
        },
    )
    _assert_forbidden_semantic_conditions_absent(
        package,
        mechanics={"board_position", "combo_sequence", "location_activation"},
    )


def _assert_treantdruid_semantic_boundary(package: Mapping[str, Any]) -> None:
    _assert_suppressed_card_semantics_absent(
        package,
        expected_by_reason={
            "variable_cost_condition_not_encoded": {
                "DRG_314",
                "DMF_060",
                "TTN_954",
            },
            "spell_cannot_own_on_board": {"TTN_954"},
        },
    )
    _assert_forbidden_semantic_conditions_absent(
        package,
        mechanics={"board_count_threshold", "variable_cost"},
    )


def _assert_piratedh_semantic_boundary(package: Mapping[str, Any]) -> None:
    _assert_warning_only_mechanic_visible(
        package,
        mechanic="outcast",
        expected_card_ids={"BT_490", "SCH_356", "CORE_YOP_001"},
    )
    _assert_warning_only_mechanic_visible(
        package,
        mechanic="location_activation",
        expected_card_ids={"VAC_929"},
    )
    _assert_suppressed_card_semantics_absent(
        package,
        expected_by_reason={
            "outcast_condition_not_encoded": {
                "BT_490",
                "CORE_YOP_001",
                "SCH_356",
            },
            "trigger_owner_does_not_attack": {"VAC_929"},
        },
    )
    _assert_forbidden_semantic_conditions_absent(
        package,
        mechanics={"hand_position", "location_activation", "outcast"},
    )
    assert FORBIDDEN_LEGACY_RUNTIME_SURFACES.isdisjoint(
        path.name for path in _deck_dir(package).iterdir()
    )


def _assert_cutewarrior_semantic_boundary(package: Mapping[str, Any]) -> None:
    matrix_names = {str(row["deck_name"]) for row in read_json(MATRIX_PATH)["decks"]}
    supplemental_names = {
        str(row["deck_name"]) for row in read_json(SUPPLEMENTAL_PATH)["decks"]
    }
    assert "CuteWarrior" not in matrix_names
    assert "CuteWarrior" in supplemental_names

    summary = read_json(Path(package["out"]) / "reports" / "operator_summary.json")
    assert summary["fixture_classification"] == "load_safe_fixture"
    assert summary["runtime_load_safe"] is True
    assert summary["source_apply_eligible"] is False
    assert summary["runtime_apply_allowed"] is False
    assert summary["configuration_assurance"]["source_authority"] == "archetype_only"

    _assert_suppressed_card_semantics_absent(
        package,
        expected_by_reason={
            "unresolved_option_identity": {"EDR_570"},
            "choose_one_condition_not_encoded": {"EDR_570"},
        },
    )
    _assert_warning_only_mechanic_visible(
        package,
        mechanic="board_position",
        expected_card_ids=set(),
    )
    _assert_forbidden_semantic_conditions_absent(
        package,
        mechanics={"board_position", "choose_one"},
    )


DECK_SEMANTIC_BOUNDARY_ASSERTIONS = {
    "CtAPaladin": _assert_ctapaladin_semantic_boundary,
    "PirateRogue": _assert_piraterogue_semantic_boundary,
    "BigShaman": _assert_bigshaman_semantic_boundary,
    "TreantDruid": _assert_treantdruid_semantic_boundary,
    "PirateDH": _assert_piratedh_semantic_boundary,
    "CuteWarrior": _assert_cutewarrior_semantic_boundary,
}


def _assert_deck_specific_invariants(
    deck_name: str,
    package: Mapping[str, Any],
) -> None:
    out = Path(package["out"])
    reports = out / "reports"
    payloads = _card_payloads(package)
    holds = _mulligan_hold_cards(package)

    semantic_boundary_assertion = DECK_SEMANTIC_BOUNDARY_ASSERTIONS.get(deck_name)
    if semantic_boundary_assertion is not None:
        semantic_boundary_assertion(package)
        return

    if deck_name == "ShadowPriest":
        assert "BeforeUseHeroPowerBonus" not in payloads["SW_448"]
        assert len(payloads["EX1_625t"]["BeforeUseHeroPowerBonus"]["values"]) == 1
        behavior = read_json(reports / "card_behavior_plan_report.json")
        reciprocal = [
            row
            for row in behavior["suppressed"]
            if row.get("reason") == "reciprocal_burn_report_only"
        ]
        assert reciprocal
        assert "GVG_009" in {card for row in reciprocal for card in row["cards"]}
        reciprocal_claims = {
            str(claim_id) for row in reciprocal for claim_id in row["source_claim_ids"]
        }
        emitted_claims = {
            str(claim_id)
            for row in behavior["rows"]
            for claim_id in row.get("source_claim_ids", [])
        }
        assert reciprocal_claims.isdisjoint(emitted_claims)
        for card_id in ("TOY_518", "WON_065"):
            assert len(payloads[card_id]["OnBoardBonus"]["values"]) == 1
        return

    if deck_name == "MechPala":
        module_ids = {"TOY_330t95", "TOY_330t98", "TOY_330t11"}
        metadata = read_json(reports / "semantic_enrichment_report.json")
        readiness = read_json(reports / "per_card_config_readiness_report.json")
        metadata_by_card = {row["card_id"]: row for row in metadata["cards"]}
        assert module_ids <= set(metadata_by_card)
        assert module_ids <= set(readiness["cards"])
        for card_id in module_ids:
            assert metadata_by_card[card_id]["deck_zone"] == "sideboard"
            assert metadata_by_card[card_id]["sideboard_owner_card_id"] == "TOY_330"
            assert readiness["cards"][card_id]["deck_zone"] == "sideboard"
            assert readiness["cards"][card_id]["runtime_surfaces"] == []
        assert "TOY_330" not in holds
        return

    if deck_name == "Kingslayer":
        assert "DEEP_014" not in holds
        for card_id in ("VAC_938", "VAC_701"):
            assert "BeforePhysicalAttackBonus" not in payloads[card_id]
        return

    if deck_name == "Boarlock":
        assert "WW_092" not in holds
        assert not (_deck_dir(package) / "Combo.json").exists()
        globalvalues = read_json(_deck_dir(package) / "GlobalValues.json")
        assert "MyHeroPowerValue" not in globalvalues
        return

    if deck_name == "Discolock":
        assert all("InHandPlayPriority" not in payload for payload in payloads.values())
        profile = read_json(reports / "globalvalues_profile.json")
        assert profile["authority_parity"] == {
            "authorized_overlay_keys": [],
            "emitted_overlay_keys": [],
            "status": "matched",
        }
        return

    if deck_name == "ImbueMage":
        readiness = read_json(reports / "per_card_config_readiness_report.json")
        readiness_mulligan_cards = {
            card_id
            for card_id, row in readiness["cards"].items()
            if "Mulligan.json" in row["runtime_surfaces"]
        }
        mulligan = read_json(_deck_dir(package) / "Mulligan.json")
        physical_mulligan_cards = {
            str(row["mulligan"])
            for row in mulligan["Mulligan"]["values"]
            if row.get("mulligan") != "*"
        }
        assert physical_mulligan_cards == readiness_mulligan_cards
        assert "FIR_911" in physical_mulligan_cards


def _insert_forbidden_semantic_row(
    package: Mapping[str, Any],
    *,
    card_id: str,
    mechanic: str,
    suppression_reason: str,
) -> None:
    reports = Path(package["out"]) / "reports"
    behavior_path = reports / "card_behavior_plan_report.json"
    behavior = read_json(behavior_path)
    suppressed = next(
        row
        for row in behavior["suppressed"]
        if row.get("reason") == suppression_reason and card_id in row.get("cards", [])
    )
    row = {
        "behavior_block": "BeforePlayCardBonus",
        "card_id": card_id,
        "condition": {"unsupported_semantic": mechanic},
        "link_kind": "self",
        "meaningful_runtime_surface": True,
        "runtime_card_id": card_id,
        "source_card_id": card_id,
        "source_claim_ids": [str(suppressed["claim_id"])],
        "source_refs": list(suppressed["source_refs"]),
        "value": 999,
    }
    behavior["rows"].append(row)
    write_json(behavior_path, behavior)

    card_path = _deck_dir(package) / f"{card_id}.json"
    payload = read_json(card_path)
    block = payload.setdefault("BeforePlayCardBonus", {"values": []})
    block["values"].append(
        {
            "condition": {"unsupported_semantic": mechanic},
            "value": 999,
        }
    )
    write_json(card_path, payload)


def _insert_unrelated_control_surface(
    package: Mapping[str, Any],
    *,
    card_id: str,
) -> None:
    reports = Path(package["out"]) / "reports"
    behavior_path = reports / "card_behavior_plan_report.json"
    behavior = read_json(behavior_path)
    behavior["rows"].append(
        {
            "behavior_block": "BeforePlayCardBonus",
            "card_id": card_id,
            "condition": {"supported_semantic": "unrelated_control_surface"},
            "link_kind": "self",
            "meaningful_runtime_surface": True,
            "runtime_card_id": card_id,
            "source_card_id": card_id,
            "source_claim_ids": ["control:unrelated_control_surface"],
            "source_refs": ["control:unrelated_control_surface"],
            "value": 17,
        }
    )
    write_json(behavior_path, behavior)

    card_path = _deck_dir(package) / f"{card_id}.json"
    payload = read_json(card_path)
    block = payload.setdefault("BeforePlayCardBonus", {"values": []})
    block["values"].append(
        {
            "condition": {"supported_semantic": "unrelated_control_surface"},
            "value": 17,
        }
    )
    write_json(card_path, payload)


def _insert_custom_semantic_row(
    package: Mapping[str, Any],
    *,
    card_id: str,
    condition: Mapping[str, Any],
    source_claim_ids: list[str],
    source_refs: list[str],
) -> None:
    reports = Path(package["out"]) / "reports"
    behavior_path = reports / "card_behavior_plan_report.json"
    behavior = read_json(behavior_path)
    behavior["rows"].append(
        {
            "behavior_block": "BeforePlayCardBonus",
            "card_id": card_id,
            "condition": dict(condition),
            "link_kind": "self",
            "meaningful_runtime_surface": True,
            "runtime_card_id": card_id,
            "source_card_id": card_id,
            "source_claim_ids": source_claim_ids,
            "source_refs": source_refs,
            "value": 23,
        }
    )
    write_json(behavior_path, behavior)

    card_path = _deck_dir(package) / f"{card_id}.json"
    payload = read_json(card_path)
    block = payload.setdefault("BeforePlayCardBonus", {"values": []})
    block["values"].append(
        {
            "condition": dict(condition),
            "value": 23,
        }
    )
    write_json(card_path, payload)


@pytest.mark.parametrize(
    ("deck_name", "card_id", "mechanic", "suppression_reason"),
    [
        (
            "CtAPaladin",
            "EX1_136",
            "secret_timing",
            "semantic_surface_not_proven",
        ),
        (
            "PirateRogue",
            "TSC_086",
            "dredge",
            "dredge_condition_not_encoded",
        ),
        (
            "BigShaman",
            "TOY_507",
            "location_activation",
            "semantic_surface_not_proven",
        ),
        (
            "TreantDruid",
            "DRG_314",
            "variable_cost",
            "variable_cost_condition_not_encoded",
        ),
        (
            "PirateDH",
            "BT_490",
            "outcast",
            "outcast_condition_not_encoded",
        ),
        (
            "CuteWarrior",
            "EDR_570",
            "choose_one",
            "choose_one_condition_not_encoded",
        ),
    ],
)
def test_named_deck_boundary_rejects_invented_semantic_row(
    deck_name: str,
    card_id: str,
    mechanic: str,
    suppression_reason: str,
    tmp_path: Path,
    read_only_isolation: dict[str, list[str]],
) -> None:
    del read_only_isolation
    deck = next(row for row in audited_decks() if row["deck_name"] == deck_name)
    package = _prepare_audited_deck(tmp_path, deck)
    assert package["exit_code"] == 0

    _insert_forbidden_semantic_row(
        package,
        card_id=card_id,
        mechanic=mechanic,
        suppression_reason=suppression_reason,
    )
    reports = Path(package["out"]) / "reports"
    _assert_cardid_report_contract(
        read_json(reports / "semantic_enrichment_report.json"),
        read_json(reports / "card_behavior_plan_report.json"),
        _card_payloads(package),
    )

    with pytest.raises(AssertionError):
        DECK_SEMANTIC_BOUNDARY_ASSERTIONS[deck_name](package)


@pytest.mark.parametrize(
    ("deck_name", "card_id"),
    [
        ("CtAPaladin", "EX1_136"),
        ("TreantDruid", "DRG_314"),
    ],
)
def test_named_deck_boundary_allows_unrelated_control_surface(
    deck_name: str,
    card_id: str,
    tmp_path: Path,
    read_only_isolation: dict[str, list[str]],
) -> None:
    del read_only_isolation
    deck = next(row for row in audited_decks() if row["deck_name"] == deck_name)
    package = _prepare_audited_deck(tmp_path, deck)
    assert package["exit_code"] == 0

    _insert_unrelated_control_surface(package, card_id=card_id)
    reports = Path(package["out"]) / "reports"
    _assert_cardid_report_contract(
        read_json(reports / "semantic_enrichment_report.json"),
        read_json(reports / "card_behavior_plan_report.json"),
        _card_payloads(package),
    )

    DECK_SEMANTIC_BOUNDARY_ASSERTIONS[deck_name](package)


@pytest.mark.parametrize(
    "surface_name",
    sorted(FORBIDDEN_LEGACY_RUNTIME_SURFACES),
)
def test_piratedh_boundary_rejects_each_forbidden_legacy_surface(
    surface_name: str,
    tmp_path: Path,
    read_only_isolation: dict[str, list[str]],
) -> None:
    del read_only_isolation
    deck = next(row for row in audited_decks() if row["deck_name"] == "PirateDH")
    package = _prepare_audited_deck(tmp_path, deck)
    assert package["exit_code"] == 0
    write_json(_deck_dir(package) / surface_name, {})

    with pytest.raises(AssertionError):
        _assert_piratedh_semantic_boundary(package)


def test_ctapaladin_boundary_rejects_bar875_secret_trigger_claim(
    tmp_path: Path,
    read_only_isolation: dict[str, list[str]],
) -> None:
    del read_only_isolation
    deck = next(row for row in audited_decks() if row["deck_name"] == "CtAPaladin")
    package = _prepare_audited_deck(tmp_path, deck)
    assert package["exit_code"] == 0
    reports = Path(package["out"]) / "reports"
    behavior = read_json(reports / "card_behavior_plan_report.json")
    suppressed = next(
        row
        for row in behavior["suppressed"]
        if row.get("reason") == "trigger_owner_does_not_attack"
        and "BAR_875" in row.get("cards", [])
    )
    _insert_custom_semantic_row(
        package,
        card_id="BAR_875",
        condition={"supported_semantic": "unrelated_control_surface"},
        source_claim_ids=[str(suppressed["claim_id"])],
        source_refs=list(suppressed["source_refs"]),
    )
    _assert_cardid_report_contract(
        read_json(reports / "semantic_enrichment_report.json"),
        read_json(reports / "card_behavior_plan_report.json"),
        _card_payloads(package),
    )

    with pytest.raises(AssertionError):
        _assert_ctapaladin_semantic_boundary(package)


def test_ctapaladin_boundary_rejects_extended_unsupported_condition(
    tmp_path: Path,
    read_only_isolation: dict[str, list[str]],
) -> None:
    del read_only_isolation
    deck = next(row for row in audited_decks() if row["deck_name"] == "CtAPaladin")
    package = _prepare_audited_deck(tmp_path, deck)
    assert package["exit_code"] == 0
    reports = Path(package["out"]) / "reports"
    _insert_custom_semantic_row(
        package,
        card_id="EX1_136",
        condition={
            "unsupported_semantic": "secret_timing",
            "context": "opponent_trigger",
        },
        source_claim_ids=["control:extended_unsupported_condition"],
        source_refs=["control:extended_unsupported_condition"],
    )
    _assert_cardid_report_contract(
        read_json(reports / "semantic_enrichment_report.json"),
        read_json(reports / "card_behavior_plan_report.json"),
        _card_payloads(package),
    )

    with pytest.raises(AssertionError):
        _assert_ctapaladin_semantic_boundary(package)


@pytest.mark.parametrize(
    "deck",
    audited_decks(),
    ids=lambda row: row["deck_name"],
)
def test_audited_deck_contract_is_current(
    deck: dict[str, Any],
    tmp_path: Path,
    read_only_isolation: dict[str, list[str]],
) -> None:
    del read_only_isolation
    decoded = decode_deck_code(str(deck["deck_code"]))
    assert decoded["card_count"] == 30
    assert decoded["unresolved_card_count"] == 0
    assert deck["fixture_expected_load_safe"] is True
    assert deck["fixture_runtime_apply_authority"] == "diagnostic_only"

    runtime_root = tmp_path / "runtime"
    assert not runtime_root.exists()
    package = _prepare_audited_deck(tmp_path, deck)

    assert package["exit_code"] == 0
    assert package["runtime_root"] == runtime_root
    assert not runtime_root.exists()
    summary = package["operator"]
    assert (Path(package["out"]) / "package_derivation_receipt.json").is_file()
    assert summary["package_derivation"]["verified"] is True
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_load_safe"] is True
    assert summary["fixture_classification"] == "load_safe_fixture"
    assert summary["runtime_apply_mode"] == "blocked"
    assert summary["runtime_apply_allowed"] is False
    assert summary["runtime_apply_reason"] == DIAGNOSTIC_APPLY_REASON
    assert summary["runtime_apply_contract"] == {
        "apply_authority": "reports/operator_summary.json",
        "authority_scope": "current_package_operator_gate",
    }
    assert summary["no_block_failure_mode_summary"]["hard_block"] is False
    assert summary["no_block_failure_mode_summary"]["runtime_apply_reason"] == (
        DIAGNOSTIC_APPLY_REASON
    )
    assert not (
        Path(package["out"]) / "reports" / "runtime_apply_receipt.json"
    ).exists()

    _assert_global_semantic_invariants(package)
    _assert_deck_specific_invariants(str(deck["deck_name"]), package)


def test_exact_live_verified_fixture_requires_strict_validation_for_eligibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    read_only_isolation: dict[str, list[str]],
) -> None:
    del read_only_isolation
    deck = next(row for row in audited_decks() if row["deck_name"] == "ShadowPriest")
    html = f"""
    <html>
      <head><title>ShadowPriest exact deck guide</title></head>
      <body><main>
        <time datetime="2026-07-27"></time>
        <h1>ShadowPriest guide</h1>
        <p>Deck code: {deck["deck_code"]}</p>
        <h2>Mulligan</h2>
        <p>Keep Voidtouched Attendant in the opening hand.</p>
        <p>Darkbishop Benedictus establishes Shadowform.</p>
      </main></body>
    </html>
    """.encode()
    monkeypatch.setattr(
        "hsconfig.source_acquisition._default_resolver",
        lambda _hostname: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "hsconfig.source_acquisition._fetch_with_validated_address",
        lambda _url, _timeout, _address: (200, "text/html", html),
    )
    out = tmp_path / "live-verified"
    runtime_root = tmp_path / "runtime"
    assert not runtime_root.exists()

    exit_code = main(
        [
            "configure",
            "--deck-name",
            str(deck["deck_name"]),
            "--deck-code",
            str(deck["deck_code"]),
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--online-source",
            "--auto-source",
            "--source-url",
            "https://example.test/exact-guide",
            "--current-date",
            "2026-07-27",
            "--json",
        ]
    )
    package = out / "04_package"
    summary = read_json(package / "reports" / "operator_summary.json")
    bundle = read_json(package / "reports" / "guide_claim_bundle.json")
    validation = validate_complete_package(package)
    gate = evaluate_apply_gate(package)

    assert exit_code == 0
    assert bundle["canonical_source_receipts"]
    assert all(
        receipt["acquisition_provenance"]["mode"] == "live_http"
        and receipt["acquisition_provenance"]["authority"] == "live_verified"
        for receipt in bundle["canonical_source_receipts"]
    )
    assert validation["status"] == "passed"
    assert validation["errors"] == []
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["source_apply_eligible"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert not runtime_root.exists()
    assert not (package / "reports" / "runtime_apply_receipt.json").exists()

    (package / "reports" / "globalvalues_profile.json").unlink()
    invalid_validation = validate_complete_package(package)
    invalid_gate = evaluate_apply_gate(package)

    assert invalid_validation["status"] == "failed"
    assert invalid_gate["status"] == "blocked"
    assert invalid_gate["allowed"] is False
    assert invalid_gate["reasons"][0]["reason"] == "strict_package_validation_failed"
