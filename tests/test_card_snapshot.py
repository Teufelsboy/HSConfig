from __future__ import annotations

from hashlib import sha256
import io

import pytest
from hearthstone.deckstrings import FormatType, write_deckstring

from hsconfig.card_snapshot import build_card_snapshot
from hsconfig.deckstring_decode import (
    _decode_parsed_deck,
    decode_deck_code_from_snapshot,
)
from hsconfig.hearthstonejson import fetch_card_snapshot
from hsconfig.package_request import FrozenJsonDocument


CAPTURED_AT = "2026-09-09T00:00:00Z"


def _rows() -> list[dict]:
    return [
        {"id": "TEST_HERO", "dbfId": 1001, "type": "HERO", "name": "Hero"},
        {
            "id": "TEST_OWNER_A",
            "dbfId": 1002,
            "type": "MINION",
            "name": "Owner A",
            "cost": 1,
            "attack": 1,
            "health": 2,
            "collectible": True,
        },
        {
            "id": "TEST_MEMBER",
            "dbfId": 1003,
            "type": "MINION",
            "name": "Member",
            "text": "",
            "cost": 2,
            "attack": 2,
            "health": 3,
        },
        {
            "id": "TEST_OWNER_B",
            "dbfId": 1004,
            "type": "MINION",
            "name": "Owner B",
            "cost": 3,
            "attack": 3,
            "health": 4,
        },
    ]


def test_snapshot_decoder_does_not_consult_installed_cardxml(monkeypatch):
    def unexpected_local_database():
        raise AssertionError("local cardxml consulted")

    monkeypatch.setattr(
        "hsconfig.deckstring_decode.cardxml.load_dbf",
        unexpected_local_database,
    )
    rows = [
        {"id": "TEST_HERO", "dbfId": 1001, "type": "HERO", "name": "Hero"},
        {
            "id": "TEST_CARD",
            "dbfId": 1002,
            "type": "MINION",
            "name": "Card",
            "cost": 1,
            "attack": 1,
            "health": 2,
            "collectible": True,
        },
    ]
    snapshot = build_card_snapshot(rows, captured_at=CAPTURED_AT)
    code = write_deckstring([(1002, 2)], [1001], FormatType.FT_WILD)

    decoded = decode_deck_code_from_snapshot(code, snapshot)

    assert decoded["hero"]["card_id"] == "TEST_HERO"
    assert [(row["card_id"], row["count"]) for row in decoded["cards"]] == [
        ("TEST_CARD", 2)
    ]


def test_snapshot_preserves_raw_presence_and_hashes_the_full_projection():
    rows = _rows() + [
        {
            "id": "TEST_METADATA_ONLY",
            "type": "SPELL",
            "name": "Metadata only",
            "collectible": True,
        }
    ]

    snapshot = build_card_snapshot(
        rows,
        captured_at=CAPTURED_AT,
        upstream_version="fixture-v1",
    )
    value = snapshot.to_value()

    assert set(value) == {
        "full_cards",
        "collectible_cards",
        "dbf_to_card_id",
        "captured_at",
        "upstream_version",
        "dataset_sha256",
    }
    assert value["captured_at"] == CAPTURED_AT
    assert value["upstream_version"] == "fixture-v1"
    assert value["dbf_to_card_id"] == {
        "1001": "TEST_HERO",
        "1002": "TEST_OWNER_A",
        "1003": "TEST_MEMBER",
        "1004": "TEST_OWNER_B",
    }
    by_id = {row["id"]: row for row in value["full_cards"]}
    assert by_id["TEST_HERO"]["dbf_id"] == 1001
    assert by_id["TEST_METADATA_ONLY"]["dbf_id"] is None
    assert "text" not in by_id["TEST_HERO"]["source_fields"]
    assert "text" in by_id["TEST_MEMBER"]["source_fields"]
    assert [row["id"] for row in value["collectible_cards"]] == [
        "TEST_METADATA_ONLY",
        "TEST_OWNER_A",
    ]
    full_projection = FrozenJsonDocument.from_value(value["full_cards"])
    assert value["dataset_sha256"] == (
        f"sha256:{sha256(full_projection.canonical_json).hexdigest()}"
    )


def test_snapshot_deduplicates_only_exact_rows():
    row = {
        "id": "TEST_CARD",
        "dbfId": 1002,
        "type": "MINION",
        "name": "Card",
    }

    value = build_card_snapshot(
        [row, dict(row)],
        captured_at=CAPTURED_AT,
    ).to_value()

    assert [card["id"] for card in value["full_cards"]] == ["TEST_CARD"]


@pytest.mark.parametrize(
    "row",
    [
        {"id": True, "dbfId": 1001},
        {"id": 7, "dbfId": 1001},
        {"id": "", "dbfId": 1001},
        {"id": "TEST_CARD", "dbfId": True},
        {"id": "TEST_CARD", "dbfId": "1001"},
        {"id": "TEST_CARD", "dbfId": 0},
        {"id": "TEST_CARD", "dbfId": -1},
        {"id": "TEST_CARD", "dbfId": 1001, "dbf_id": 1002},
    ],
)
def test_snapshot_rejects_invalid_supplied_identity_types(row):
    with pytest.raises(ValueError, match="^card_snapshot_identity_invalid$"):
        build_card_snapshot([row], captured_at=CAPTURED_AT)


@pytest.mark.parametrize(
    "rows",
    [
        [
            {"id": "TEST_FIRST", "dbfId": 1001},
            {"id": "TEST_SECOND", "dbfId": 1001},
        ],
        [
            {"id": "TEST_CARD", "dbfId": 1001, "name": "First"},
            {"id": "TEST_CARD", "dbfId": 1002, "name": "Second"},
        ],
        [
            {"id": "TEST_CARD", "dbfId": 1001, "name": "First"},
            {"id": "TEST_CARD", "dbfId": 1001, "name": "Second"},
        ],
    ],
)
def test_snapshot_rejects_identity_conflicts(rows):
    with pytest.raises(ValueError, match="^card_snapshot_identity_conflict$"):
        build_card_snapshot(rows, captured_at=CAPTURED_AT)


@pytest.mark.parametrize(
    ("missing_dbf_id", "sideboards"),
    [
        (1001, []),
        (1002, [(1003, 2, 1002)]),
        (1003, [(1003, 2, 1002)]),
    ],
    ids=["hero", "sideboard_owner", "sideboard_member"],
)
def test_snapshot_decoder_fails_closed_for_every_required_identity(
    missing_dbf_id,
    sideboards,
):
    rows = [row for row in _rows() if row.get("dbfId") != missing_dbf_id]
    code = write_deckstring(
        [(1004, 1)],
        [1001],
        FormatType.FT_WILD,
        sideboards,
    )

    with pytest.raises(ValueError, match="^card_snapshot_identity_missing$"):
        decode_deck_code_from_snapshot(
            code,
            build_card_snapshot(rows, captured_at=CAPTURED_AT),
        )


def test_snapshot_decoder_preserves_shared_memberships_and_multiplicities():
    code = write_deckstring(
        [(1002, 1), (1004, 1)],
        [1001],
        FormatType.FT_WILD,
        [(1003, 2, 1002), (1003, 3, 1004)],
    )

    decoded = decode_deck_code_from_snapshot(
        code,
        build_card_snapshot(_rows(), captured_at=CAPTURED_AT),
    )

    assert [sideboard["sideboard_index"] for sideboard in decoded["sideboards"]] == [
        1,
        2,
    ]
    assert [
        (
            sideboard["owner_card_id"],
            sideboard["cards"][0]["card_id"],
            sideboard["cards"][0]["count"],
        )
        for sideboard in decoded["sideboards"]
    ] == [
        ("TEST_OWNER_A", "TEST_MEMBER", 2),
        ("TEST_OWNER_B", "TEST_MEMBER", 3),
    ]
    assert decoded["sideboard_count"] == 5
    assert decoded["deckstring_decode_receipt"]["sideboard_unique_card_count"] == 2


def test_snapshot_decoder_revalidates_digest_and_mapping():
    snapshot = build_card_snapshot(_rows(), captured_at=CAPTURED_AT)
    value = snapshot.to_value()
    value["dbf_to_card_id"]["1002"] = "TEST_OWNER_B"
    tampered = FrozenJsonDocument.from_value(value)
    code = write_deckstring([(1002, 1)], [1001], FormatType.FT_WILD)

    with pytest.raises(ValueError, match="^card_snapshot_invalid$"):
        decode_deck_code_from_snapshot(code, tampered)


def test_snapshot_decoder_revalidates_normalized_row_types():
    snapshot = build_card_snapshot(_rows(), captured_at=CAPTURED_AT)
    value = snapshot.to_value()
    value["full_cards"][0]["cost"] = True
    value["dataset_sha256"] = "sha256:" + sha256(
        FrozenJsonDocument.from_value(value["full_cards"]).canonical_json
    ).hexdigest()
    tampered = FrozenJsonDocument.from_value(value)
    code = write_deckstring([(1002, 1)], [1001], FormatType.FT_WILD)

    with pytest.raises(ValueError, match="^card_snapshot_invalid$"):
        decode_deck_code_from_snapshot(code, tampered)


@pytest.mark.parametrize(
    "parsed",
    [
        {"cards": [(1002, True)], "heroes": [1001], "format": 1, "sideboards": []},
        {"cards": [(1002, 1)], "heroes": [True], "format": 1, "sideboards": []},
        {
            "cards": [(1002, 1)],
            "heroes": [1001],
            "format": 1,
            "sideboards": [(1003, True, 1002)],
        },
    ],
)
def test_parsed_deck_rejects_boolean_identities_and_counts(parsed):
    with pytest.raises(ValueError, match="^deckstring_identity_invalid$"):
        _decode_parsed_deck(
            parsed,
            resolve=lambda dbf_id, count: {
                "card_id": f"TEST_{dbf_id}",
                "dbf_id": dbf_id,
                "count": count,
                "metadata_status": "source_record",
            },
            code_length=10,
        )


def test_fetch_card_snapshot_reads_full_feed_once_and_does_not_guess_version(
    monkeypatch,
):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return io.BytesIO(
            b'[{"id":"TEST_CARD","dbfId":1001,"collectible":true,"text":""}]'
        )

    monkeypatch.setattr("hsconfig.hearthstonejson.urlopen", fake_urlopen)

    value = fetch_card_snapshot(timeout=4.5).to_value()

    assert calls == [("https://api.hearthstonejson.com/v1/latest/enUS/cards.json", 4.5)]
    assert value["upstream_version"] is None
    assert value["full_cards"][0]["source_fields"] == [
        "collectible",
        "dbfId",
        "id",
        "text",
    ]
    assert value["collectible_cards"] == value["full_cards"]
