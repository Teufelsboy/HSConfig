from __future__ import annotations

import argparse
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import socket
from types import SimpleNamespace
from typing import Any

from hsconfig.build_input_catalog import (
    load_packaged_audited_build_inputs,
    load_packaged_audited_build_resource_store,
)
from hsconfig.package_builder import prepare_package_payload
from tests.helpers.audited_deck_support import (
    VISIBILITY_IDENTITY_DECODE_ONLY_CARD_IDS,
)


AUDITED_DECK_NAMES = (
    "ShadowPriest",
    "CtAPaladin",
    "PirateRogue",
    "BigShaman",
    "Discolock",
    "TreantDruid",
    "ImbueMage",
    "MechPala",
    "Kingslayer",
    "Boarlock",
    "PirateDH",
    "CuteWarrior",
)
_CATALOG_PATH = Path("docs/operator/audited-deck-catalog.json")
_CARD_DB_PATH = Path("tests/fixtures/audited_deck_card_db.json")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ALLOWED_DECK_FIELDS = frozenset(
    {"deck_fingerprint", "artifacts", "content_root_sha256"}
)
_ALLOWED_ARTIFACT_FIELDS = frozenset({"relative_path", "size", "sha256"})


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def artifact_rows_for_tree(root: Path) -> list[dict[str, Any]]:
    root = Path(root)
    rows = []
    paths = [item for item in root.rglob("*") if item.is_file()]
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        relative_path = path.relative_to(root).as_posix()
        data = path.read_bytes()
        rows.append(
            {
                "relative_path": relative_path,
                "size": len(data),
                "sha256": sha256(data).hexdigest(),
            }
        )
    return rows


def content_root_sha256(rows: list[Mapping[str, Any]]) -> str:
    ordered_rows = sorted(rows, key=lambda row: str(row["relative_path"]))
    stream = b"".join(
        (
            f"{row['relative_path']}\0{int(row['size'])}\0{row['sha256']}\n"
        ).encode("utf-8")
        for row in ordered_rows
    )
    return sha256(stream).hexdigest()


def assert_fixture_schema(fixture: Mapping[str, Any]) -> None:
    if set(fixture) != {"schema_version", "decks"}:
        raise AssertionError("package_byte_contract_fixture_fields_invalid")
    if fixture.get("schema_version") != 1:
        raise AssertionError("package_byte_contract_schema_version_invalid")
    decks = fixture.get("decks")
    if not isinstance(decks, Mapping) or tuple(decks) != AUDITED_DECK_NAMES:
        raise AssertionError("package_byte_contract_deck_catalog_invalid")
    for deck_name, deck in decks.items():
        if not isinstance(deck, Mapping) or set(deck) != _ALLOWED_DECK_FIELDS:
            raise AssertionError("package_byte_contract_deck_fields_invalid")
        _assert_sha256(deck.get("deck_fingerprint"), "deck_fingerprint")
        _assert_sha256(deck.get("content_root_sha256"), "content_root_sha256")
        artifacts = deck.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise AssertionError("package_byte_contract_artifacts_invalid")
        previous_path = ""
        for artifact in artifacts:
            if not isinstance(artifact, Mapping) or set(artifact) != _ALLOWED_ARTIFACT_FIELDS:
                raise AssertionError("package_byte_contract_artifact_fields_invalid")
            relative_path = artifact.get("relative_path")
            if (
                not isinstance(relative_path, str)
                or not relative_path
                or relative_path.startswith("/")
                or "\\" in relative_path
                or ".." in Path(relative_path).parts
                or relative_path <= previous_path
            ):
                raise AssertionError("package_byte_contract_artifact_path_invalid")
            if type(artifact.get("size")) is not int or artifact["size"] < 0:
                raise AssertionError("package_byte_contract_artifact_size_invalid")
            _assert_sha256(artifact.get("sha256"), "artifact_sha256")
            previous_path = relative_path
        if content_root_sha256(artifacts) != deck["content_root_sha256"]:
            raise AssertionError("package_byte_contract_content_root_invalid")


def assert_fixture_is_metadata_only(fixture: Mapping[str, Any]) -> None:
    encoded = json.dumps(fixture, ensure_ascii=True, sort_keys=True)
    forbidden = ("AAEBA", "Power.log", ".hsreplay", ".hdtreplay")
    if any(token in encoded for token in forbidden):
        raise AssertionError("package_byte_contract_fixture_private_data_leak")
    for deck in fixture.get("decks", {}).values():
        for artifact in deck["artifacts"]:
            if Path(artifact["relative_path"]).is_absolute():
                raise AssertionError("package_byte_contract_fixture_absolute_path")


def assert_fixture_matches_canonical_fingerprints(fixture: Mapping[str, Any]) -> None:
    canonical = canonical_fingerprints()
    decks = fixture.get("decks")
    if not isinstance(decks, Mapping):
        raise AssertionError("package_byte_contract_canonical_fingerprint_mismatch")
    for deck_name in AUDITED_DECK_NAMES:
        deck = decks.get(deck_name)
        if not isinstance(deck, Mapping) or deck.get("deck_fingerprint") != canonical[deck_name]:
            raise AssertionError("package_byte_contract_canonical_fingerprint_mismatch")


def canonical_fingerprints() -> dict[str, str]:
    return {
        build.deck_name: build.deck_fingerprint
        for build in _audited_builds()
    }


def canonical_as_of_dates() -> dict[str, date]:
    return {
        build.deck_name: date.fromisoformat(build.as_of_date)
        for build in _audited_builds()
    }


def canonicalize_source_bytes(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def prepare_audited_packages(root: Path) -> dict[str, Path]:
    root = Path(root)
    catalog = _load_audited_catalog()
    deck_cards_by_name, offline_cards, card_database = _offline_build_inputs()
    audited_dates = canonical_as_of_dates()
    output_roots: dict[str, Path] = {}
    root.mkdir(parents=True, exist_ok=True)
    runtime_root = root / "runtime-write-fence"
    if runtime_root.exists():
        raise AssertionError("package_byte_contract_runtime_root_must_not_exist")
    with _working_directory(root):
        for deck in catalog:
            deck_name = str(deck["deck_name"])
            source_documents = _materialize_source_documents(deck_name, root=root)
            out = Path("packages") / deck_name
            payload, code = _prepare_one(
                deck=deck,
                out=out,
                runtime_root=Path("runtime-write-fence"),
                source_documents=source_documents,
                deck_cards=deck_cards_by_name[deck_name],
                offline_cards=offline_cards,
                card_database=card_database,
                as_of_date=audited_dates[deck_name],
            )
            if code != 0:
                raise AssertionError(f"package_byte_contract_prepare_failed:{deck_name}:{payload}")
            output_roots[deck_name] = root / out
    if runtime_root.exists():
        raise AssertionError("package_byte_contract_runtime_write_detected")
    return output_roots


def build_fixture_from_roots(roots: Mapping[str, Path]) -> dict[str, Any]:
    if tuple(roots) != AUDITED_DECK_NAMES:
        raise AssertionError("package_byte_contract_deck_catalog_invalid")
    decks: dict[str, dict[str, Any]] = {}
    canonical = canonical_fingerprints()
    for deck_name, root in roots.items():
        artifacts = artifact_rows_for_tree(root)
        identity = json.loads(
            (root / "reports" / "deck_identity.json").read_text(encoding="utf-8")
        )
        fingerprint = identity.get("deck_fingerprint")
        _assert_sha256(fingerprint, "deck_fingerprint")
        if fingerprint != canonical[deck_name]:
            raise AssertionError("package_byte_contract_canonical_fingerprint_mismatch")
        decks[deck_name] = {
            "deck_fingerprint": fingerprint,
            "artifacts": artifacts,
            "content_root_sha256": content_root_sha256(artifacts),
        }
    fixture = {"schema_version": 1, "decks": decks}
    assert_fixture_schema(fixture)
    assert_fixture_is_metadata_only(fixture)
    assert_fixture_matches_canonical_fingerprints(fixture)
    return fixture


def assert_trees_byte_equal(left: Mapping[str, Path], right: Mapping[str, Path]) -> None:
    if tuple(left) != tuple(right):
        raise AssertionError("package_byte_contract_deck_set_mismatch")
    for deck_name in left:
        left_rows = artifact_rows_for_tree(left[deck_name])
        right_rows = artifact_rows_for_tree(right[deck_name])
        if left_rows != right_rows:
            raise AssertionError(f"package_byte_contract_two_root_mismatch:{deck_name}")
        for row in left_rows:
            relative_path = row["relative_path"]
            if (
                (left[deck_name] / relative_path).read_bytes()
                != (right[deck_name] / relative_path).read_bytes()
            ):
                raise AssertionError(
                    f"package_byte_contract_raw_byte_mismatch:{deck_name}:{relative_path}"
                )


def _prepare_one(
    *,
    deck: Mapping[str, Any],
    out: Path,
    runtime_root: Path,
    source_documents: Path,
    deck_cards: list[dict[str, Any]],
    offline_cards: list[dict[str, Any]],
    card_database: dict[int, SimpleNamespace],
    as_of_date: date,
) -> tuple[dict[str, Any], int]:
    args = argparse.Namespace(
        command="prepare",
        deck_name=str(deck["deck_name"]),
        deck_code=str(deck["deck_code"]),
        out=str(out),
        runtime_root=str(runtime_root),
        guide_sources_json=None,
        source_documents_json=str(source_documents),
        auto_research_fallback=False,
        json=True,
        cards_json=None,
        claims_json=None,
        plan_reports_dir=None,
        allow_placeholder=False,
        current_date=as_of_date.isoformat(),
        collectible_cards_json=None,
        full_cards_json=None,
        skip_semantic_fetch=False,
        source_evidence_json=None,
    )
    with _offline_network_and_card_data(offline_cards, card_database):
        return prepare_package_payload(args, current_date=as_of_date)


def _load_audited_catalog() -> list[dict[str, Any]]:
    payload = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    decks = payload.get("decks") if isinstance(payload, Mapping) else None
    if not isinstance(decks, list) or tuple(row.get("deck_name") for row in decks) != AUDITED_DECK_NAMES:
        raise AssertionError("package_byte_contract_catalog_invalid")
    return [dict(row) for row in decks]


def _audited_builds() -> tuple[Any, ...]:
    builds = load_packaged_audited_build_inputs().builds
    if tuple(build.deck_name for build in builds) != AUDITED_DECK_NAMES:
        raise AssertionError("package_byte_contract_catalog_invalid")
    return builds


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    try:
        import os

        os.chdir(path)
        yield
    finally:
        os.chdir(previous)


def _materialize_source_documents(deck_name: str, *, root: Path) -> Path:
    inputs = root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    if deck_name == "CuteWarrior":
        path = inputs / "source_documents_cutewarrior_strong.json"
        fixture_bytes = f"{deck_name}:diagnostic-fixture".encode("utf-8")
        payload = {
            "source_documents": [
                {
                    "source_url": "https://example.invalid/diagnostic-fixture",
                    "source_title": f"{deck_name} diagnostic fixture",
                    "source_family": "guide",
                    "retrieved_at": "2026-07-27T00:00:00Z",
                    "acquisition_provenance": {
                        "mode": "captured_record",
                        "authority": "captured_unverified",
                        "content_sha256": f"sha256:{sha256(fixture_bytes).hexdigest()}",
                    },
                    "source_visibility": "full_text",
                    "source_lane": "archetype_matched_public_guide",
                    "deck_name": deck_name,
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
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        path.write_bytes(canonicalize_source_bytes(raw))
        return Path("inputs") / path.name
    path = _REPOSITORY_ROOT / "tests/fixtures" / (
        f"source_documents_{deck_name.lower()}_strong.json"
    )
    if not path.is_file():
        raise AssertionError(f"package_byte_contract_source_fixture_missing:{deck_name}")
    target = inputs / path.name
    target.write_bytes(canonicalize_source_bytes(path.read_bytes()))
    return Path("inputs") / target.name


def _offline_build_inputs() -> tuple[
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
    dict[int, SimpleNamespace],
]:
    audited_inputs = load_packaged_audited_build_inputs()
    resource_store = load_packaged_audited_build_resource_store(
        audited_inputs=audited_inputs
    )
    payload = json.loads(_CARD_DB_PATH.read_text(encoding="utf-8"))
    raw_cards = payload.get("cards") if isinstance(payload, Mapping) else None
    if not isinstance(raw_cards, list):
        raise AssertionError("package_byte_contract_card_db_invalid")
    offline_cards = []
    by_card_id: dict[str, dict[str, Any]] = {}
    for row in raw_cards:
        if not isinstance(row, list) or len(row) != 8:
            raise AssertionError("package_byte_contract_card_db_row_invalid")
        dbf_id, card_id, name, cost, card_type, card_class, text, mechanics = row
        card = {
            "id": str(card_id),
            "dbfId": int(dbf_id),
            "name": str(name),
            "cost": int(cost),
            "type": str(card_type),
            "cardClass": str(card_class),
            "text": str(text),
            "mechanics": [str(item) for item in mechanics],
            "collectible": True,
        }
        offline_cards.append(card)
        by_card_id[str(card_id)] = card
    deck_cards_by_name: dict[str, list[dict[str, Any]]] = {}
    for build in audited_inputs.builds:
        resource = json.loads(
            resource_store.read_by_sha256(build.deck_cards_resource_sha256)
        )
        main_cards = resource.get("main_cards")
        if not isinstance(main_cards, list):
            raise AssertionError("package_byte_contract_deck_cards_invalid")
        deck_cards = []
        for main_card in main_cards:
            card_id = str(main_card.get("card_id", ""))
            source = by_card_id.get(card_id)
            if source is None:
                raise AssertionError("package_byte_contract_snapshot_card_missing")
            deck_cards.append(
                {
                    "card_id": card_id,
                    "dbf_id": source["dbfId"],
                    "count": int(main_card["count"]),
                    "name": source["name"],
                    "cost": source["cost"],
                    "type": source["type"],
                    "card_class": source["cardClass"],
                    "text": source["text"],
                    "mechanics": source["mechanics"],
                }
            )
        deck_cards_by_name[build.deck_name] = deck_cards
    if tuple(deck_cards_by_name) != AUDITED_DECK_NAMES:
        raise AssertionError("package_byte_contract_catalog_invalid")
    return deck_cards_by_name, offline_cards, _card_database_from_raw(raw_cards)


@contextmanager
def _offline_network_and_card_data(
    offline_cards: list[dict[str, Any]],
    card_database: dict[int, SimpleNamespace],
) -> Iterator[None]:
    from hearthstone import cardxml
    import hsconfig.hearthstonejson as hearthstonejson
    import hsconfig.package_builder as package_builder
    import hsconfig.source_acquisition as source_acquisition

    previous_fetch = package_builder.fetch_latest_cards
    previous_load_dbf = cardxml.load_dbf
    previous_connection = socket.create_connection
    previous_resolver = socket.getaddrinfo
    previous_source_connection = source_acquisition.create_connection
    previous_source_resolver = source_acquisition.getaddrinfo
    previous_urlopen = hearthstonejson.urlopen

    def offline_fetch(timeout: float = 10.0) -> list[dict[str, Any]]:
        del timeout
        return [dict(card) for card in offline_cards]

    def blocked_network(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("package_byte_contract_network_attempted")

    package_builder.fetch_latest_cards = offline_fetch
    cardxml.load_dbf = lambda: (card_database, None)
    socket.create_connection = blocked_network
    socket.getaddrinfo = blocked_network
    source_acquisition.create_connection = blocked_network
    source_acquisition.getaddrinfo = blocked_network
    hearthstonejson.urlopen = blocked_network
    try:
        yield
    finally:
        package_builder.fetch_latest_cards = previous_fetch
        cardxml.load_dbf = previous_load_dbf
        socket.create_connection = previous_connection
        socket.getaddrinfo = previous_resolver
        source_acquisition.create_connection = previous_source_connection
        source_acquisition.getaddrinfo = previous_source_resolver
        hearthstonejson.urlopen = previous_urlopen


def _card_database_from_raw(raw_cards: list[Any]) -> dict[int, SimpleNamespace]:
    cards: dict[int, SimpleNamespace] = {}
    for row in raw_cards:
        if not isinstance(row, list) or len(row) != 8:
            raise AssertionError("package_byte_contract_card_db_row_invalid")
        dbf_id, card_id, name, cost, card_type, card_class, text, mechanics = row
        card = SimpleNamespace(
            card_class=str(card_class),
            card_id=str(card_id),
            cost=int(cost),
            english_description=str(text),
            english_name=str(name),
            name=str(name),
            type=str(card_type),
        )
        for mechanic in mechanics:
            setattr(card, str(mechanic), True)
        cards[int(dbf_id)] = card
    cards.update(
        {
            int(dbf_id): SimpleNamespace(
                card_class="VISIBILITY_IDENTITY_ONLY",
                card_id=str(card_id),
                cost=None,
                english_description="",
                english_name=str(card_id),
                name=str(card_id),
                type="VISIBILITY_IDENTITY_ONLY",
                deckstring_identity_only=True,
            )
            for dbf_id, card_id in VISIBILITY_IDENTITY_DECODE_ONLY_CARD_IDS.items()
        }
    )
    return cards


def _assert_sha256(value: Any, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AssertionError(f"package_byte_contract_{name}_invalid")
