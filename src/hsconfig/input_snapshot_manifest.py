"""One-shot immutable compiler inputs and their sealed manifest."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import os
from pathlib import Path
import re
from typing import Any

from hsconfig.io import slugify_deck_name
from hsconfig.package_io import (
    path_identity,
    path_identity_from_status,
    plain_file_status,
    read_file_no_follow,
    require_no_alternate_data_streams,
    require_plain_directory,
    require_same_identity_resolution,
)
from hsconfig.output_operation_admission import (
    _require_windows_safe_absolute_path,
    _require_windows_safe_component,
)
from hsconfig.package_request import (
    FrozenJsonDocument,
    PackageResolutionSnapshot,
)
from hsconfig.starter_document import (
    StarterDocument,
    seal_starter_document,
)


INPUT_SNAPSHOT_SCHEMA_VERSION = 1
INPUT_SNAPSHOT_MAX_BYTES = 256 * 1024
INPUT_BLOB_MAX_BYTES = 134_217_728
INPUT_BLOB_MAX_RECORDS = 1_000_000
INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES = 1_048_576
DECK_INPUT_ENVELOPE_MAX_BYTES = (
    INPUT_BLOB_MAX_BYTES + INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES
)
CARDS_INPUT_ENVELOPE_MAX_BYTES = (
    3 * INPUT_BLOB_MAX_BYTES + INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES
)
SOURCES_INPUT_ENVELOPE_MAX_BYTES = (
    2 * INPUT_BLOB_MAX_BYTES + INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES
)
INPUT_SNAPSHOT_FIELDS = frozenset(
    {
        "schema_version",
        "compiler_inputs",
        "operator_bindings",
        "content_sha256",
    }
)
COMPILER_INPUT_FIELDS = frozenset(
    {
        "deck_code_sha256",
        "roster_fingerprint",
        "bound_date",
        "blobs",
        "runtime_grammar_version",
        "compiler_contract_id",
    }
)
OPERATOR_BINDING_FIELDS = frozenset(
    {
        "operator_profile_sha256",
        "runtime_root",
        "runtime_root_identity",
        "output_base_root",
        "output_base_root_identity",
        "deck_output_name",
        "deck_output_precondition",
    }
)


_BLOB_FIELDS = frozenset(
    {"name", "sha256", "size_bytes", "record_count"}
)
_BLOB_ORDER = (
    "deck",
    "full_cards",
    "collectible_cards",
    "source_acquisition",
    "source_documents",
    "globalvalues_baseline",
)
_DECK_INPUT_FIELDS = frozenset({"cards_payload", "deck_identity"})
_CARDS_INPUT_ENVELOPE_FIELDS = frozenset(
    {"full_cards", "collectible_cards", "globalvalues_baseline"}
)
_SOURCES_INPUT_ENVELOPE_FIELDS = frozenset(
    {"source_acquisition", "source_documents"}
)
_DECK_OUTPUT_PRECONDITION_FIELDS = frozenset({"state", "identity"})
_STANDARD_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_BARE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BOUND_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_CARD_ID = re.compile(r"[A-Za-z0-9_]+\Z")
_VERSION_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
    | {
        f"{prefix}{suffix}"
        for prefix in ("com", "lpt")
        for suffix in ("¹", "²", "³")
    }
)


@dataclass(frozen=True, slots=True)
class InputBlobBinding:
    name: str
    sha256: str
    size_bytes: int
    record_count: int


@dataclass(frozen=True, slots=True)
class ValidatedInputSnapshotManifest:
    document: StarterDocument
    compiler_inputs: FrozenJsonDocument
    operator_bindings: FrozenJsonDocument
    blobs: tuple[InputBlobBinding, ...]


@dataclass(frozen=True, slots=True)
class FrozenCompilerInputs:
    manifest: ValidatedInputSnapshotManifest
    deck: FrozenJsonDocument
    full_cards: FrozenJsonDocument
    collectible_cards: FrozenJsonDocument
    source_acquisition: FrozenJsonDocument
    source_documents: FrozenJsonDocument
    globalvalues_baseline: FrozenJsonDocument


@dataclass(frozen=True, slots=True)
class _BoundDirectory:
    path: Path
    identity: tuple[int, int, int]


def freeze_compiler_inputs(
    *,
    snapshot: PackageResolutionSnapshot,
    deck: Any,
    full_cards: Any,
    collectible_cards: Any,
    source_acquisition: Any,
    source_documents: Any,
    globalvalues_baseline: Any,
    bound_date: str,
    runtime_grammar_version: str,
    compiler_contract_id: str,
    operator_profile: Any,
    deck_output_binding: Any,
) -> FrozenCompilerInputs:
    """Freeze six supplied projections without fetching or rereading inputs."""

    if not isinstance(snapshot, PackageResolutionSnapshot):
        raise TypeError("input_snapshot_resolution_snapshot_invalid")
    preconfig = snapshot.general_preconfig.to_value()
    expected_deck = FrozenJsonDocument.from_value(
        {
            "cards_payload": preconfig["cards_payload"],
            "deck_identity": preconfig["deck_identity"],
        }
    )
    documents = {
        "deck": _freeze_supplied_blob(deck, "deck"),
        "full_cards": _freeze_supplied_blob(full_cards, "full_cards"),
        "collectible_cards": _freeze_supplied_blob(
            collectible_cards,
            "collectible_cards",
        ),
        "source_acquisition": _freeze_supplied_blob(
            source_acquisition,
            "source_acquisition",
        ),
        "source_documents": _freeze_supplied_blob(
            source_documents,
            "source_documents",
        ),
        "globalvalues_baseline": _freeze_supplied_blob(
            globalvalues_baseline,
            "globalvalues_baseline",
        ),
    }
    if documents["deck"].canonical_json != expected_deck.canonical_json:
        raise ValueError("input_snapshot_deck_projection_mismatch")
    expected_baseline = FrozenJsonDocument.from_value(
        preconfig["globalvalues_baseline"]
    )
    if (
        documents["globalvalues_baseline"].canonical_json
        != expected_baseline.canonical_json
    ):
        raise ValueError("input_snapshot_globalvalues_baseline_mismatch")

    deck_value = _require_mapping(
        documents["deck"].to_value(),
        "input_snapshot_deck_invalid",
    )
    full_value = documents["full_cards"].to_value()
    collectible_value = documents["collectible_cards"].to_value()
    _validate_deck_and_card_closure(
        deck_value,
        full_cards=full_value,
        collectible_cards=collectible_value,
    )
    _validate_blob_shapes(
        deck=deck_value,
        full_cards=full_value,
        collectible_cards=collectible_value,
        source_acquisition=documents["source_acquisition"].to_value(),
        source_documents=documents["source_documents"].to_value(),
        globalvalues_baseline=documents["globalvalues_baseline"].to_value(),
    )
    _require_strict_date(bound_date)
    _require_version_identifier(
        runtime_grammar_version,
        "runtime_grammar_version",
    )
    _require_version_identifier(
        compiler_contract_id,
        "compiler_contract_id",
    )

    deck_identity = _require_mapping(
        deck_value["deck_identity"],
        "input_snapshot_deck_identity_invalid",
    )
    deck_code_sha256 = _prefixed_bare_digest(
        deck_identity.get("deck_code_hash"),
        "deck_code_sha256",
    )
    roster_fingerprint = _prefixed_bare_digest(
        deck_identity.get("deck_fingerprint"),
        "roster_fingerprint",
    )
    bindings = tuple(
        _binding_for_document(name, documents[name])
        for name in _BLOB_ORDER
    )
    _validate_envelope_sizes(documents)
    compiler_inputs = {
        "deck_code_sha256": deck_code_sha256,
        "roster_fingerprint": roster_fingerprint,
        "bound_date": bound_date,
        "blobs": [
            {
                "name": binding.name,
                "sha256": binding.sha256,
                "size_bytes": binding.size_bytes,
                "record_count": binding.record_count,
            }
            for binding in bindings
        ],
        "runtime_grammar_version": runtime_grammar_version,
        "compiler_contract_id": compiler_contract_id,
    }
    operator_bindings = _operator_bindings_from_values(
        operator_profile=operator_profile,
        deck_output_binding=deck_output_binding,
        deck_name=deck_identity.get("deck_name"),
    )
    sealed = seal_starter_document(
        {
            "schema_version": INPUT_SNAPSHOT_SCHEMA_VERSION,
            "compiler_inputs": compiler_inputs,
            "operator_bindings": operator_bindings,
        },
        expected_fields=INPUT_SNAPSHOT_FIELDS,
        schema_version=INPUT_SNAPSHOT_SCHEMA_VERSION,
    )
    if len(sealed.canonical_json) > INPUT_SNAPSHOT_MAX_BYTES:
        raise ValueError("input_snapshot_manifest_size_invalid")
    validated = validate_input_snapshot_manifest_document(sealed.document)
    result = FrozenCompilerInputs(
        manifest=validated,
        deck=documents["deck"],
        full_cards=documents["full_cards"],
        collectible_cards=documents["collectible_cards"],
        source_acquisition=documents["source_acquisition"],
        source_documents=documents["source_documents"],
        globalvalues_baseline=documents["globalvalues_baseline"],
    )
    _require_manifest_blob_match(result)
    return result


def validate_input_snapshot_manifest_document(
    document: FrozenJsonDocument,
) -> ValidatedInputSnapshotManifest:
    """Purely validate a canonical manifest without touching a filesystem."""

    if not isinstance(document, FrozenJsonDocument):
        raise TypeError("input_snapshot_manifest_document_invalid")
    if (
        not document.canonical_json
        or len(document.canonical_json) > INPUT_SNAPSHOT_MAX_BYTES
    ):
        raise ValueError("input_snapshot_manifest_size_invalid")
    value = _require_mapping(
        document.to_value(),
        "input_snapshot_manifest_invalid",
    )
    if frozenset(value) != INPUT_SNAPSHOT_FIELDS:
        raise ValueError("input_snapshot_manifest_fields_invalid")
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != INPUT_SNAPSHOT_SCHEMA_VERSION
    ):
        raise ValueError("input_snapshot_manifest_schema_version_invalid")
    embedded_digest = _require_standard_digest(
        value["content_sha256"],
        "content_sha256",
    )
    unsigned = dict(value)
    del unsigned["content_sha256"]
    resealed = seal_starter_document(
        unsigned,
        expected_fields=INPUT_SNAPSHOT_FIELDS,
        schema_version=INPUT_SNAPSHOT_SCHEMA_VERSION,
    )
    if (
        embedded_digest != resealed.content_sha256
        or resealed.document.canonical_json != document.canonical_json
    ):
        raise ValueError("input_snapshot_manifest_content_sha256_invalid")

    compiler_value = _require_mapping(
        value["compiler_inputs"],
        "input_snapshot_compiler_inputs_invalid",
    )
    if frozenset(compiler_value) != COMPILER_INPUT_FIELDS:
        raise ValueError("input_snapshot_compiler_inputs_fields_invalid")
    _require_standard_digest(
        compiler_value["deck_code_sha256"],
        "deck_code_sha256",
    )
    _require_standard_digest(
        compiler_value["roster_fingerprint"],
        "roster_fingerprint",
    )
    _require_strict_date(compiler_value["bound_date"])
    _require_version_identifier(
        compiler_value["runtime_grammar_version"],
        "runtime_grammar_version",
    )
    _require_version_identifier(
        compiler_value["compiler_contract_id"],
        "compiler_contract_id",
    )
    blobs = _validate_blob_bindings(compiler_value["blobs"])

    operator_value = _require_mapping(
        value["operator_bindings"],
        "input_snapshot_operator_bindings_invalid",
    )
    _validate_operator_bindings(operator_value)
    return ValidatedInputSnapshotManifest(
        document=StarterDocument(
            document=document,
            content_sha256=embedded_digest,
        ),
        compiler_inputs=FrozenJsonDocument.from_value(compiler_value),
        operator_bindings=FrozenJsonDocument.from_value(operator_value),
        blobs=blobs,
    )


def load_frozen_compiler_inputs(run_root: Path) -> FrozenCompilerInputs:
    """Load and physically rebind one external run's frozen input set."""

    root_binding = _rebind_plain_directory(Path(run_root), "run_root")
    root = root_binding.path
    inputs_binding = _rebind_plain_directory(
        root / "inputs",
        "inputs_root",
        expected_parent_identity=root_binding.identity,
    )
    inputs = inputs_binding.path
    manifest_raw = _read_input_file_once(
        inputs / "input_snapshot_manifest.json",
        maximum_bytes=INPUT_SNAPSHOT_MAX_BYTES,
        expected_parent_identity=inputs_binding.identity,
    )
    manifest_document = _canonical_physical_document(
        manifest_raw,
        "input_snapshot_manifest",
    )
    manifest = validate_input_snapshot_manifest_document(manifest_document)

    deck_raw = _read_input_file_once(
        inputs / "deck.json",
        maximum_bytes=DECK_INPUT_ENVELOPE_MAX_BYTES,
        expected_parent_identity=inputs_binding.identity,
    )
    cards_raw = _read_input_file_once(
        inputs / "cards.json",
        maximum_bytes=CARDS_INPUT_ENVELOPE_MAX_BYTES,
        expected_parent_identity=inputs_binding.identity,
    )
    sources_raw = _read_input_file_once(
        inputs / "sources.json",
        maximum_bytes=SOURCES_INPUT_ENVELOPE_MAX_BYTES,
        expected_parent_identity=inputs_binding.identity,
    )
    deck = _canonical_physical_document(deck_raw, "input_deck_envelope")
    deck_value = _require_mapping(
        deck.to_value(),
        "input_deck_envelope_invalid",
    )
    if frozenset(deck_value) != _DECK_INPUT_FIELDS:
        raise ValueError("input_deck_envelope_fields_invalid")

    cards_envelope = _canonical_physical_document(
        cards_raw,
        "input_cards_envelope",
    ).to_value()
    cards_value = _require_mapping(
        cards_envelope,
        "input_cards_envelope_invalid",
    )
    if frozenset(cards_value) != _CARDS_INPUT_ENVELOPE_FIELDS:
        raise ValueError("input_cards_envelope_fields_invalid")

    sources_envelope = _canonical_physical_document(
        sources_raw,
        "input_sources_envelope",
    ).to_value()
    sources_value = _require_mapping(
        sources_envelope,
        "input_sources_envelope_invalid",
    )
    if frozenset(sources_value) != _SOURCES_INPUT_ENVELOPE_FIELDS:
        raise ValueError("input_sources_envelope_fields_invalid")

    result = FrozenCompilerInputs(
        manifest=manifest,
        deck=deck,
        full_cards=FrozenJsonDocument.from_value(
            cards_value["full_cards"]
        ),
        collectible_cards=FrozenJsonDocument.from_value(
            cards_value["collectible_cards"]
        ),
        source_acquisition=FrozenJsonDocument.from_value(
            sources_value["source_acquisition"]
        ),
        source_documents=FrozenJsonDocument.from_value(
            sources_value["source_documents"]
        ),
        globalvalues_baseline=FrozenJsonDocument.from_value(
            cards_value["globalvalues_baseline"]
        ),
    )
    _require_manifest_blob_match(result)
    _validate_loaded_compiler_binding(result)
    _rebind_operator_bindings(result)
    _require_same_directory_binding(root_binding, "run_root")
    _require_same_directory_binding(inputs_binding, "inputs_root")
    return result


def _read_input_file_once(
    path: Path,
    *,
    maximum_bytes: int,
    expected_parent_identity: tuple[int, int, int] | None = None,
) -> bytes:
    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise ValueError("input_envelope_maximum_bytes_invalid")
    input_path = Path(path)
    parent_identity = path_identity(input_path.parent)
    if (
        expected_parent_identity is not None
        and parent_identity != expected_parent_identity
    ):
        raise ValueError("input_envelope_parent_identity_changed")
    status = plain_file_status(input_path)
    if status.st_size < 1 or status.st_size > maximum_bytes:
        raise ValueError("input_envelope_size_invalid")
    require_same_identity_resolution(input_path, expected_status=status)
    require_no_alternate_data_streams(
        input_path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=parent_identity,
        directory=False,
        expected_size=status.st_size,
    )
    raw = read_file_no_follow(
        input_path,
        expected_status=status,
        maximum_size=maximum_bytes,
    )
    if path_identity(input_path.parent) != parent_identity:
        raise ValueError("input_envelope_parent_identity_changed")
    return raw


def _freeze_supplied_blob(value: Any, name: str) -> FrozenJsonDocument:
    try:
        if isinstance(value, FrozenJsonDocument):
            document = FrozenJsonDocument(value.canonical_json)
        elif isinstance(value, (bytes, bytearray, memoryview)):
            document = FrozenJsonDocument(bytes(value))
        else:
            document = FrozenJsonDocument.from_value(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"input_snapshot_{name}_invalid") from error
    if not document.canonical_json:
        raise ValueError(f"input_snapshot_{name}_empty")
    return document


def _binding_for_document(
    name: str,
    document: FrozenJsonDocument,
) -> InputBlobBinding:
    size = len(document.canonical_json)
    if size < 1 or size > INPUT_BLOB_MAX_BYTES:
        raise ValueError(f"input_snapshot_{name}_size_invalid")
    count = _record_count(name, document.to_value())
    if count < 0 or count > INPUT_BLOB_MAX_RECORDS:
        raise ValueError(f"input_snapshot_{name}_record_count_invalid")
    return InputBlobBinding(
        name=name,
        sha256=_digest(document.canonical_json),
        size_bytes=size,
        record_count=count,
    )


def _validate_blob_bindings(value: Any) -> tuple[InputBlobBinding, ...]:
    if not isinstance(value, list) or len(value) != len(_BLOB_ORDER):
        raise ValueError("input_snapshot_blobs_invalid")
    bindings: list[InputBlobBinding] = []
    for expected_name, row in zip(_BLOB_ORDER, value, strict=True):
        mapping = _require_mapping(row, "input_snapshot_blob_invalid")
        if frozenset(mapping) != _BLOB_FIELDS:
            raise ValueError("input_snapshot_blob_fields_invalid")
        if mapping["name"] != expected_name:
            raise ValueError("input_snapshot_blob_order_invalid")
        digest = _require_standard_digest(mapping["sha256"], "blob_sha256")
        size = mapping["size_bytes"]
        count = mapping["record_count"]
        if (
            type(size) is not int
            or size < 1
            or size > INPUT_BLOB_MAX_BYTES
        ):
            raise ValueError("input_snapshot_blob_size_invalid")
        if (
            type(count) is not int
            or count < 0
            or count > INPUT_BLOB_MAX_RECORDS
        ):
            raise ValueError("input_snapshot_blob_record_count_invalid")
        bindings.append(
            InputBlobBinding(
                name=expected_name,
                sha256=digest,
                size_bytes=size,
                record_count=count,
            )
        )
    return tuple(bindings)


def _validate_blob_shapes(
    *,
    deck: Any,
    full_cards: Any,
    collectible_cards: Any,
    source_acquisition: Any,
    source_documents: Any,
    globalvalues_baseline: Any,
) -> None:
    deck_mapping = _require_mapping(deck, "input_snapshot_deck_invalid")
    if frozenset(deck_mapping) != _DECK_INPUT_FIELDS:
        raise ValueError("input_snapshot_deck_fields_invalid")
    _card_rows(full_cards, "full_cards")
    _card_rows(collectible_cards, "collectible_cards")
    if not isinstance(source_acquisition, (dict, list)):
        raise ValueError("input_snapshot_source_acquisition_invalid")
    if not isinstance(source_documents, (dict, list)):
        raise ValueError("input_snapshot_source_documents_invalid")
    if not isinstance(globalvalues_baseline, dict):
        raise ValueError("input_snapshot_globalvalues_baseline_invalid")


def _validate_deck_and_card_closure(
    deck: Mapping[str, Any],
    *,
    full_cards: Any,
    collectible_cards: Any,
) -> None:
    if frozenset(deck) != _DECK_INPUT_FIELDS:
        raise ValueError("input_snapshot_deck_fields_invalid")
    cards_payload = _require_mapping(
        deck["cards_payload"],
        "input_snapshot_cards_payload_invalid",
    )
    deck_identity = _require_mapping(
        deck["deck_identity"],
        "input_snapshot_deck_identity_invalid",
    )
    deck_name = deck_identity.get("deck_name")
    if not isinstance(deck_name, str) or not deck_name.strip():
        raise ValueError("input_snapshot_deck_name_invalid")
    if deck_name != deck_name.strip():
        raise ValueError("input_snapshot_deck_name_invalid")
    deck_slug = deck_identity.get("deck_slug")
    if deck_slug != slugify_deck_name(deck_name):
        raise ValueError("input_snapshot_deck_slug_invalid")
    _prefixed_bare_digest(
        deck_identity.get("deck_code_hash"),
        "deck_code_sha256",
    )
    fingerprint = _prefixed_bare_digest(
        deck_identity.get("deck_fingerprint"),
        "roster_fingerprint",
    )
    if (
        type(deck_identity.get("unresolved_card_count")) is not int
        or deck_identity["unresolved_card_count"] != 0
    ):
        raise ValueError("input_snapshot_unresolved_deck_identity")

    main_cards = _deck_card_rows(
        deck_identity.get("cards"),
        "main_deck",
    )
    duplicate_main = _duplicate_deck_identity(main_cards)
    if duplicate_main is not None:
        raise ValueError(
            f"input_snapshot_duplicate_deck_identity:{duplicate_main}"
        )
    if deck_identity.get("main_deck") != deck_identity.get("cards"):
        raise ValueError("input_snapshot_main_deck_mismatch")
    main_total = sum(row["count"] for row in main_cards)
    if (
        type(deck_identity.get("card_count_total")) is not int
        or deck_identity["card_count_total"] != main_total
    ):
        raise ValueError("input_snapshot_main_deck_count_invalid")
    if _roster_fingerprint(main_cards) != fingerprint:
        raise ValueError("input_snapshot_roster_fingerprint_mismatch")

    sideboards = deck_identity.get("sideboards")
    if not isinstance(sideboards, list):
        raise ValueError("input_snapshot_sideboards_invalid")
    sideboard_cards: list[dict[str, Any]] = []
    owners: list[tuple[str | None, int | None]] = []
    sideboard_projection: list[
        tuple[
            int,
            str | None,
            int | None,
            tuple[tuple[str, int, int], ...],
        ]
    ] = []
    sideboard_indexes: set[int] = set()
    for sideboard in sideboards:
        row = _require_mapping(
            sideboard,
            "input_snapshot_sideboard_invalid",
        )
        index = row.get("sideboard_index")
        if type(index) is not int or index < 1 or index in sideboard_indexes:
            raise ValueError("input_snapshot_sideboard_index_invalid")
        sideboard_indexes.add(index)
        owner_card_id = row.get("owner_card_id")
        if owner_card_id is not None and (
            not isinstance(owner_card_id, str) or not owner_card_id.strip()
        ):
            raise ValueError("input_snapshot_sideboard_owner_invalid")
        owner_dbf_id = row.get("owner_dbf_id")
        if owner_dbf_id is not None and (
            type(owner_dbf_id) is not int or owner_dbf_id < 1
        ):
            raise ValueError("input_snapshot_sideboard_owner_invalid")
        if owner_card_id is None and owner_dbf_id is None:
            raise ValueError("input_snapshot_sideboard_owner_invalid")
        owner = (owner_card_id, owner_dbf_id)
        owners.append(owner)
        row_cards = _deck_card_rows(
            row.get("cards"),
            "sideboard",
        )
        sideboard_cards.extend(row_cards)
        sideboard_projection.append(
            (
                index,
                owner_card_id,
                owner_dbf_id,
                _identity_roster(row_cards),
            )
        )
    duplicate_sideboard = _duplicate_deck_identity(sideboard_cards)
    if duplicate_sideboard is not None:
        raise ValueError(
            "input_snapshot_duplicate_sideboard_identity:"
            f"{duplicate_sideboard}"
        )
    sideboard_total = sum(row["count"] for row in sideboard_cards)
    if (
        type(deck_identity.get("sideboard_count")) is not int
        or deck_identity["sideboard_count"] != sideboard_total
    ):
        raise ValueError("input_snapshot_sideboard_count_invalid")

    payload_cards = _deck_card_rows(
        cards_payload.get("cards"),
        "cards_payload",
    )
    if _identity_roster(payload_cards) != _identity_roster(main_cards):
        raise ValueError("input_snapshot_cards_payload_roster_mismatch")
    _validate_card_id_map(
        cards_payload.get("card_id_map"),
        main_cards=main_cards,
    )
    if _sideboard_identity_projection(
        cards_payload.get("sideboards"),
        "cards_payload_sideboards",
    ) != tuple(sideboard_projection):
        raise ValueError("input_snapshot_cards_payload_sideboards_mismatch")
    if cards_payload.get("hero_dbf_id") != deck_identity.get("hero_dbf_id"):
        raise ValueError("input_snapshot_hero_identity_mismatch")
    hero_dbf_id = cards_payload.get("hero_dbf_id")
    if type(hero_dbf_id) is not int or hero_dbf_id < 1:
        raise ValueError("input_snapshot_hero_identity_invalid")
    if (
        not isinstance(cards_payload.get("format"), str)
        or cards_payload.get("format") != deck_identity.get("format")
    ):
        raise ValueError("input_snapshot_deck_format_invalid")
    hero_card_id = _validate_decode_receipt(
        cards_payload.get("deckstring_decode_receipt"),
        hero_dbf_id=hero_dbf_id,
        main_total=main_total,
        unique_count=len(main_cards),
        sideboard_total=sideboard_total,
    )
    verification = _require_mapping(
        cards_payload.get("deck_input_verification"),
        "input_snapshot_deck_verification_invalid",
    )
    if (
        verification.get("normalized_roster_sha256") != fingerprint
        or verification.get("runtime_apply_eligible") is not True
        or verification.get("status")
        not in {"decoded_from_deck_code", "cards_json_matches_deck_code"}
    ):
        raise ValueError("input_snapshot_deck_verification_invalid")

    full_rows = _card_rows(full_cards, "full_cards")
    collectible_rows = _card_rows(
        collectible_cards,
        "collectible_cards",
    )
    by_id, by_dbf = _resolved_card_indices(
        full_rows=full_rows,
        collectible_rows=collectible_rows,
    )
    for row in [*main_cards, *sideboard_cards]:
        _require_resolved_card(row, by_id=by_id, by_dbf=by_dbf)
    resolved_hero = _require_resolved_identity(
        card_id=hero_card_id,
        dbf_id=hero_dbf_id,
        by_id=by_id,
        by_dbf=by_dbf,
        error_identity=hero_card_id,
    )
    if resolved_hero != (hero_card_id, hero_dbf_id):
        raise ValueError("input_snapshot_hero_identity_invalid")
    resolved_owners: set[tuple[str | None, int | None]] = set()
    for owner_card_id, owner_dbf_id in owners:
        resolved_owner = _require_resolved_identity(
            card_id=owner_card_id,
            dbf_id=owner_dbf_id,
            by_id=by_id,
            by_dbf=by_dbf,
            error_identity=owner_card_id or str(owner_dbf_id),
        )
        if resolved_owner in resolved_owners:
            raise ValueError("input_snapshot_duplicate_sideboard_owner")
        resolved_owners.add(resolved_owner)


def _validate_decode_receipt(
    value: Any,
    *,
    hero_dbf_id: int,
    main_total: int,
    unique_count: int,
    sideboard_total: int,
) -> str:
    receipt = _require_mapping(
        value,
        "input_snapshot_deck_decode_receipt_invalid",
    )
    required_zeroes = (
        "unresolved_card_count",
        "unresolved_identity_count",
    )
    if any(
        type(receipt.get(field)) is not int or receipt[field] != 0
        for field in required_zeroes
    ):
        raise ValueError("input_snapshot_unresolved_deck_identity")
    if receipt.get("unresolved_cards") != [] or receipt.get(
        "unresolved_identities"
    ) != []:
        raise ValueError("input_snapshot_unresolved_deck_identity")
    hero_card_id = receipt.get("hero_card_id")
    if (
        receipt.get("hero_dbf_id") != hero_dbf_id
        or type(hero_card_id) is not str
        or not hero_card_id
        or hero_card_id != hero_card_id.strip()
        or _CARD_ID.fullmatch(hero_card_id) is None
        or receipt.get("hero_metadata_status") != "source_record"
    ):
        raise ValueError("input_snapshot_hero_identity_invalid")
    expected_counts = {
        "card_count_total": main_total,
        "unique_card_count": unique_count,
        "sideboard_count": sideboard_total,
    }
    for field, expected in expected_counts.items():
        if type(receipt.get(field)) is not int or receipt[field] != expected:
            raise ValueError("input_snapshot_deck_decode_receipt_invalid")
    return hero_card_id


def _deck_card_rows(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"input_snapshot_{field}_invalid")
    rows: list[dict[str, Any]] = []
    for value_row in value:
        row = _require_mapping(
            value_row,
            f"input_snapshot_{field}_row_invalid",
        )
        card_id = row.get("card_id")
        dbf_id = row.get("dbf_id")
        count = row.get("count")
        if not isinstance(card_id, str) or not card_id.strip():
            raise ValueError(f"input_snapshot_{field}_card_id_invalid")
        if type(dbf_id) is not int or dbf_id < 1:
            raise ValueError(f"input_snapshot_{field}_dbf_id_invalid")
        if type(count) is not int or count < 1:
            raise ValueError(f"input_snapshot_{field}_count_invalid")
        rows.append(dict(row))
    return rows


def _validate_card_id_map(
    value: Any,
    *,
    main_cards: Sequence[Mapping[str, Any]],
) -> None:
    mapping = _require_mapping(
        value,
        "input_snapshot_card_id_map_invalid",
    )
    rows: list[dict[str, Any]] = []
    for dbf_key, value_row in mapping.items():
        row = _require_mapping(
            value_row,
            "input_snapshot_card_id_map_row_invalid",
        )
        dbf_id = row.get("dbf_id")
        if (
            type(dbf_id) is not int
            or dbf_id < 1
            or dbf_key != str(dbf_id)
        ):
            raise ValueError("input_snapshot_card_id_map_key_invalid")
        rows.extend(_deck_card_rows([row], "card_id_map"))
    if _identity_roster(rows) != _identity_roster(main_cards):
        raise ValueError("input_snapshot_card_id_map_roster_mismatch")


def _duplicate_deck_identity(rows: Sequence[Mapping[str, Any]]) -> str | None:
    ids: set[str] = set()
    dbfs: set[int] = set()
    for row in rows:
        card_id = str(row["card_id"])
        dbf_id = int(row["dbf_id"])
        if card_id in ids:
            return card_id
        if dbf_id in dbfs:
            return str(dbf_id)
        ids.add(card_id)
        dbfs.add(dbf_id)
    return None


def _card_rows(value: Any, field: str) -> list[dict[str, Any]]:
    rows_value: Any = value
    if isinstance(value, dict):
        rows_value = value.get("cards")
    if not isinstance(rows_value, list):
        raise ValueError(f"input_snapshot_{field}_invalid")
    if len(rows_value) > INPUT_BLOB_MAX_RECORDS:
        raise ValueError(f"input_snapshot_{field}_record_count_invalid")
    rows: list[dict[str, Any]] = []
    for value_row in rows_value:
        row = _require_mapping(
            value_row,
            f"input_snapshot_{field}_row_invalid",
        )
        card_id = _card_feed_id(row)
        dbf_id = _card_feed_dbf(row)
        if card_id is None and dbf_id is None:
            raise ValueError(f"input_snapshot_{field}_identity_invalid")
        rows.append(dict(row))
    return rows


def _resolved_card_indices(
    *,
    full_rows: Sequence[Mapping[str, Any]],
    collectible_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, tuple[str | None, int | None]], dict[int, tuple[str | None, int | None]]]:
    combined_by_id: dict[str, tuple[str | None, int | None]] = {}
    combined_by_dbf: dict[int, tuple[str | None, int | None]] = {}
    for field, rows in (
        ("full_cards", full_rows),
        ("collectible_cards", collectible_rows),
    ):
        local_ids: set[str] = set()
        local_dbfs: set[int] = set()
        for row in rows:
            card_id = _card_feed_id(row)
            dbf_id = _card_feed_dbf(row)
            identity = (card_id, dbf_id)
            if card_id is not None:
                if card_id in local_ids:
                    raise ValueError(
                        f"input_snapshot_duplicate_{field}_identity:{card_id}"
                    )
                local_ids.add(card_id)
                previous = combined_by_id.get(card_id)
                if previous is not None and previous != identity:
                    raise ValueError(
                        f"input_snapshot_card_identity_collision:{card_id}"
                    )
                combined_by_id[card_id] = identity
            if dbf_id is not None:
                if dbf_id in local_dbfs:
                    raise ValueError(
                        f"input_snapshot_duplicate_{field}_identity:{dbf_id}"
                    )
                local_dbfs.add(dbf_id)
                previous = combined_by_dbf.get(dbf_id)
                if previous is not None and previous != identity:
                    raise ValueError(
                        f"input_snapshot_card_identity_collision:{dbf_id}"
                    )
                combined_by_dbf[dbf_id] = identity
    for card_id, identity in combined_by_id.items():
        dbf_id = identity[1]
        if dbf_id is not None:
            dbf_identity = combined_by_dbf.get(dbf_id)
            if dbf_identity is not None and dbf_identity[0] != card_id:
                raise ValueError(
                    f"input_snapshot_card_identity_collision:{card_id}"
                )
    return combined_by_id, combined_by_dbf


def _require_resolved_card(
    row: Mapping[str, Any],
    *,
    by_id: Mapping[str, tuple[str | None, int | None]],
    by_dbf: Mapping[int, tuple[str | None, int | None]],
) -> None:
    _require_resolved_identity(
        card_id=str(row["card_id"]),
        dbf_id=int(row["dbf_id"]),
        by_id=by_id,
        by_dbf=by_dbf,
        error_identity=str(row["card_id"]),
    )


def _require_resolved_identity(
    *,
    card_id: str | None,
    dbf_id: int | None,
    by_id: Mapping[str, tuple[str | None, int | None]],
    by_dbf: Mapping[int, tuple[str | None, int | None]],
    error_identity: str,
) -> tuple[str | None, int | None]:
    id_identity = by_id.get(card_id) if card_id is not None else None
    dbf_identity = by_dbf.get(dbf_id) if dbf_id is not None else None
    if id_identity is None and dbf_identity is None:
        raise ValueError(f"input_snapshot_unknown_deck_card:{error_identity}")
    if id_identity is not None and dbf_id is not None and (
        id_identity[1] is not None and id_identity[1] != dbf_id
    ):
        raise ValueError(
            f"input_snapshot_card_identity_contradiction:{error_identity}"
        )
    if dbf_identity is not None and card_id is not None and (
        dbf_identity[0] is not None and dbf_identity[0] != card_id
    ):
        raise ValueError(
            f"input_snapshot_card_identity_contradiction:{error_identity}"
        )
    if (
        id_identity is not None
        and dbf_identity is not None
        and id_identity != dbf_identity
    ):
        raise ValueError(
            f"input_snapshot_card_identity_ambiguous:{error_identity}"
        )
    resolved = id_identity if id_identity is not None else dbf_identity
    if resolved is None:  # pragma: no cover - guarded above
        raise AssertionError("resolved card identity missing")
    return resolved


def _card_feed_id(row: Mapping[str, Any]) -> str | None:
    values: set[str] = set()
    for key in ("id", "cardId", "card_id"):
        if key not in row:
            continue
        value = row[key]
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or _CARD_ID.fullmatch(value) is None
        ):
            raise ValueError("input_snapshot_card_id_invalid")
        values.add(value)
    if len(values) > 1:
        raise ValueError("input_snapshot_card_identity_contradiction")
    return next(iter(values), None)


def _card_feed_dbf(row: Mapping[str, Any]) -> int | None:
    values: set[int] = set()
    for key in ("dbfId", "dbf_id"):
        if key not in row or row[key] in (None, ""):
            continue
        if type(row[key]) is not int or row[key] < 1:
            raise ValueError("input_snapshot_card_dbf_id_invalid")
        values.add(row[key])
    if len(values) > 1:
        raise ValueError("input_snapshot_card_identity_contradiction")
    return next(iter(values), None)


def _identity_roster(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        sorted(
            (
                str(row["card_id"]),
                int(row["dbf_id"]),
                int(row["count"]),
            )
            for row in rows
        )
    )


def _sideboard_identity_projection(
    value: Any,
    field: str,
) -> tuple[
    tuple[
        int,
        str | None,
        int | None,
        tuple[tuple[str, int, int], ...],
    ],
    ...,
]:
    if not isinstance(value, list):
        raise ValueError(f"input_snapshot_{field}_invalid")
    result = []
    indexes: set[int] = set()
    owners: set[tuple[str | None, int | None]] = set()
    for value_row in value:
        row = _require_mapping(
            value_row,
            f"input_snapshot_{field}_row_invalid",
        )
        index = row.get("sideboard_index")
        if type(index) is not int or index < 1 or index in indexes:
            raise ValueError(f"input_snapshot_{field}_index_invalid")
        indexes.add(index)
        owner_card_id = row.get("owner_card_id")
        owner_dbf_id = row.get("owner_dbf_id")
        if owner_card_id is not None and (
            not isinstance(owner_card_id, str) or not owner_card_id.strip()
        ):
            raise ValueError(f"input_snapshot_{field}_owner_invalid")
        if owner_dbf_id is not None and (
            type(owner_dbf_id) is not int or owner_dbf_id < 1
        ):
            raise ValueError(f"input_snapshot_{field}_owner_invalid")
        owner = (owner_card_id, owner_dbf_id)
        if owner == (None, None) or owner in owners:
            raise ValueError(f"input_snapshot_{field}_owner_invalid")
        owners.add(owner)
        cards = _deck_card_rows(row.get("cards"), field)
        result.append(
            (index, owner_card_id, owner_dbf_id, _identity_roster(cards))
        )
    return tuple(result)


def _roster_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    roster = sorted(
        (str(row["card_id"]), int(row["count"])) for row in rows
    )
    return _digest(FrozenJsonDocument.from_value(roster).canonical_json)


def _validate_envelope_sizes(
    documents: Mapping[str, FrozenJsonDocument],
) -> None:
    deck_size = len(documents["deck"].canonical_json)
    cards = FrozenJsonDocument.from_value(
        {
            "full_cards": documents["full_cards"].to_value(),
            "collectible_cards": documents["collectible_cards"].to_value(),
            "globalvalues_baseline": documents[
                "globalvalues_baseline"
            ].to_value(),
        }
    )
    sources = FrozenJsonDocument.from_value(
        {
            "source_acquisition": documents[
                "source_acquisition"
            ].to_value(),
            "source_documents": documents["source_documents"].to_value(),
        }
    )
    if deck_size > DECK_INPUT_ENVELOPE_MAX_BYTES:
        raise ValueError("input_deck_envelope_size_invalid")
    if len(cards.canonical_json) > CARDS_INPUT_ENVELOPE_MAX_BYTES:
        raise ValueError("input_cards_envelope_size_invalid")
    if len(sources.canonical_json) > SOURCES_INPUT_ENVELOPE_MAX_BYTES:
        raise ValueError("input_sources_envelope_size_invalid")


def _operator_bindings_from_values(
    *,
    operator_profile: Any,
    deck_output_binding: Any,
    deck_name: Any,
) -> dict[str, Any]:
    from hsconfig.operator_profile import (
        DeckOutputBinding,
        OperatorProfile,
        derive_deck_output_binding,
        revalidate_operator_profile,
    )

    if not isinstance(operator_profile, OperatorProfile):
        raise TypeError("input_snapshot_operator_profile_invalid")
    if not isinstance(deck_output_binding, DeckOutputBinding):
        raise TypeError("input_snapshot_deck_output_binding_invalid")
    if not isinstance(deck_name, str) or not deck_name:
        raise ValueError("input_snapshot_deck_name_invalid")
    revalidate_operator_profile(operator_profile)
    current_binding = derive_deck_output_binding(operator_profile, deck_name)
    if deck_output_binding != current_binding:
        raise ValueError("input_snapshot_deck_output_binding_changed")
    expected_name = slugify_deck_name(deck_name)
    if deck_output_binding.output_name != expected_name:
        raise ValueError("input_snapshot_deck_output_name_mismatch")
    if deck_output_binding.output_root != (
        operator_profile.output_base_root / expected_name
    ):
        raise ValueError("input_snapshot_deck_output_root_mismatch")
    precondition_identity = deck_output_binding.precondition_identity
    if (
        deck_output_binding.precondition_state == "absent"
        and precondition_identity is not None
    ) or (
        deck_output_binding.precondition_state == "existing"
        and precondition_identity is None
    ):
        raise ValueError("input_snapshot_deck_output_precondition_invalid")
    value = {
        "operator_profile_sha256": operator_profile.content_sha256,
        "runtime_root": str(operator_profile.runtime_root),
        "runtime_root_identity": list(
            operator_profile.runtime_root_identity
        ),
        "output_base_root": str(operator_profile.output_base_root),
        "output_base_root_identity": list(
            operator_profile.output_base_root_identity
        ),
        "deck_output_name": deck_output_binding.output_name,
        "deck_output_precondition": {
            "state": deck_output_binding.precondition_state,
            "identity": (
                list(precondition_identity)
                if precondition_identity is not None
                else None
            ),
        },
    }
    _validate_operator_bindings(value)
    return value


def _validate_operator_bindings(value: Mapping[str, Any]) -> None:
    if frozenset(value) != OPERATOR_BINDING_FIELDS:
        raise ValueError("input_snapshot_operator_bindings_fields_invalid")
    _require_standard_digest(
        value["operator_profile_sha256"],
        "operator_profile_sha256",
    )
    runtime_root = _require_lexical_absolute_path(
        value["runtime_root"],
        "runtime_root",
    )
    output_root = _require_lexical_absolute_path(
        value["output_base_root"],
        "output_base_root",
    )
    if runtime_root == output_root:
        raise ValueError("input_snapshot_operator_root_overlap")
    _identity(value["runtime_root_identity"], "runtime_root")
    _identity(value["output_base_root_identity"], "output_base_root")
    _require_safe_output_name(value["deck_output_name"])
    precondition = _require_mapping(
        value["deck_output_precondition"],
        "input_snapshot_deck_output_precondition_invalid",
    )
    if frozenset(precondition) != _DECK_OUTPUT_PRECONDITION_FIELDS:
        raise ValueError("input_snapshot_deck_output_precondition_fields_invalid")
    state = precondition["state"]
    identity = precondition["identity"]
    if state == "absent":
        if identity is not None:
            raise ValueError("input_snapshot_deck_output_precondition_invalid")
    elif state == "existing":
        _identity(identity, "deck_output_precondition")
    else:
        raise ValueError("input_snapshot_deck_output_precondition_invalid")


def _validate_loaded_compiler_binding(result: FrozenCompilerInputs) -> None:
    compiler = result.manifest.compiler_inputs.to_value()
    deck = _require_mapping(
        result.deck.to_value(),
        "input_snapshot_deck_invalid",
    )
    _validate_blob_shapes(
        deck=deck,
        full_cards=result.full_cards.to_value(),
        collectible_cards=result.collectible_cards.to_value(),
        source_acquisition=result.source_acquisition.to_value(),
        source_documents=result.source_documents.to_value(),
        globalvalues_baseline=result.globalvalues_baseline.to_value(),
    )
    _validate_deck_and_card_closure(
        deck,
        full_cards=result.full_cards.to_value(),
        collectible_cards=result.collectible_cards.to_value(),
    )
    deck_identity = _require_mapping(
        deck["deck_identity"],
        "input_snapshot_deck_identity_invalid",
    )
    if compiler["deck_code_sha256"] != _prefixed_bare_digest(
        deck_identity.get("deck_code_hash"),
        "deck_code_sha256",
    ):
        raise ValueError("input_snapshot_deck_code_binding_mismatch")
    if compiler["roster_fingerprint"] != _prefixed_bare_digest(
        deck_identity.get("deck_fingerprint"),
        "roster_fingerprint",
    ):
        raise ValueError("input_snapshot_roster_binding_mismatch")


def _require_manifest_blob_match(result: FrozenCompilerInputs) -> None:
    by_name = {binding.name: binding for binding in result.manifest.blobs}
    for name in _BLOB_ORDER:
        document = getattr(result, name)
        expected = by_name[name]
        if (
            len(document.canonical_json) != expected.size_bytes
            or _digest(document.canonical_json) != expected.sha256
            or _record_count(name, document.to_value())
            != expected.record_count
        ):
            raise ValueError(f"input_snapshot_blob_binding_mismatch:{name}")


def _rebind_operator_bindings(result: FrozenCompilerInputs) -> None:
    from hsconfig.operator_profile import (
        derive_deck_output_binding,
        load_operator_profile,
    )

    stored = result.manifest.operator_bindings.to_value()
    profile = load_operator_profile()
    expected_profile = {
        "operator_profile_sha256": profile.content_sha256,
        "runtime_root": str(profile.runtime_root),
        "runtime_root_identity": list(profile.runtime_root_identity),
        "output_base_root": str(profile.output_base_root),
        "output_base_root_identity": list(profile.output_base_root_identity),
    }
    for field, expected in expected_profile.items():
        if stored[field] != expected:
            raise ValueError(f"input_snapshot_operator_binding_changed:{field}")
    deck = result.deck.to_value()
    deck_name = deck["deck_identity"]["deck_name"]
    binding = derive_deck_output_binding(profile, deck_name)
    expected_precondition = {
        "state": binding.precondition_state,
        "identity": (
            list(binding.precondition_identity)
            if binding.precondition_identity is not None
            else None
        ),
    }
    if stored["deck_output_name"] != binding.output_name:
        raise ValueError("input_snapshot_deck_output_binding_changed")
    if stored["deck_output_precondition"] != expected_precondition:
        raise ValueError("input_snapshot_deck_output_precondition_changed")


def _rebind_plain_directory(
    path: Path,
    field: str,
    *,
    expected_parent_identity: tuple[int, int, int] | None = None,
) -> _BoundDirectory:
    candidate = _require_lexical_absolute_path(str(path), field)
    require_plain_directory(candidate)
    status = candidate.lstat()
    identity = path_identity_from_status(status)
    require_same_identity_resolution(candidate, expected_status=status)
    resolved = candidate.resolve(strict=True)
    if resolved != candidate:
        raise ValueError(f"input_snapshot_{field}_not_canonical")
    parent_identity = (
        identity
        if candidate.parent == candidate
        else path_identity(candidate.parent)
    )
    if (
        expected_parent_identity is not None
        and parent_identity != expected_parent_identity
    ):
        raise ValueError(f"input_snapshot_{field}_parent_identity_changed")
    require_no_alternate_data_streams(
        candidate,
        expected_identity=identity,
        expected_parent_identity=parent_identity,
        directory=True,
    )
    if path_identity(candidate) != identity:
        raise ValueError(f"input_snapshot_{field}_identity_changed")
    if (
        expected_parent_identity is not None
        and path_identity(candidate.parent) != expected_parent_identity
    ):
        raise ValueError(f"input_snapshot_{field}_parent_identity_changed")
    return _BoundDirectory(path=candidate, identity=identity)


def _require_same_directory_binding(
    binding: _BoundDirectory,
    field: str,
) -> None:
    require_plain_directory(binding.path)
    status = binding.path.lstat()
    if path_identity_from_status(status) != binding.identity:
        raise ValueError(f"input_snapshot_{field}_identity_changed")
    require_same_identity_resolution(binding.path, expected_status=status)


def _canonical_physical_document(
    raw: bytes,
    field: str,
) -> FrozenJsonDocument:
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw or b"\r" in raw:
        raise ValueError(f"{field}_encoding_invalid")
    try:
        return FrozenJsonDocument(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field}_not_canonical") from error


def _record_count(name: str, value: Any) -> int:
    if name == "deck":
        return 1
    if name in {"full_cards", "collectible_cards"}:
        return len(_card_rows(value, name))
    if name == "globalvalues_baseline":
        if not isinstance(value, dict):
            raise ValueError("input_snapshot_globalvalues_baseline_invalid")
        return len(value)
    if name == "source_documents":
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            for field in ("source_documents", "documents", "sources"):
                rows = value.get(field)
                if isinstance(rows, list):
                    return len(rows)
            guide_sources = value.get("guide_sources")
            if isinstance(guide_sources, dict):
                rows = guide_sources.get("sources")
                if isinstance(rows, list):
                    return len(rows)
            return 0 if not value else 1
    if name == "source_acquisition":
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            rows = value.get("records")
            if isinstance(rows, list):
                return len(rows)
            return 0 if not value else 1
    raise ValueError(f"input_snapshot_{name}_record_count_invalid")


def _require_mapping(value: Any, error: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(error)
    return value


def _require_standard_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _STANDARD_SHA256.fullmatch(value) is None:
        raise ValueError(f"input_snapshot_{field}_invalid")
    return value


def _prefixed_bare_digest(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"input_snapshot_{field}_invalid")
    bare = value.removeprefix("sha256:")
    if _BARE_SHA256.fullmatch(bare) is None:
        raise ValueError(f"input_snapshot_{field}_invalid")
    return "sha256:" + bare


def _require_strict_date(value: Any) -> str:
    if not isinstance(value, str) or _BOUND_DATE.fullmatch(value) is None:
        raise ValueError("input_snapshot_bound_date_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("input_snapshot_bound_date_invalid") from error
    if parsed.isoformat() != value:
        raise ValueError("input_snapshot_bound_date_invalid")
    return value


def _require_version_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or _VERSION_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"input_snapshot_{field}_invalid")
    return value


def _identity(value: Any, field: str) -> tuple[int, int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(item) is not int for item in value)
    ):
        raise ValueError(f"input_snapshot_{field}_identity_invalid")
    return value[0], value[1], value[2]


def _require_lexical_absolute_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"input_snapshot_{field}_invalid")
    path = Path(value)
    if (
        not path.is_absolute()
        or os.path.normpath(value) != value
        or str(path) != value
    ):
        raise ValueError(f"input_snapshot_{field}_not_canonical")
    if any(part in {".", ".."} for part in path.parts):
        raise ValueError(f"input_snapshot_{field}_not_canonical")
    return _require_windows_safe_absolute_path(
        path,
        error=f"input_snapshot_{field}_windows_namespace_invalid",
    )


def _require_safe_output_name(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("input_snapshot_deck_output_name_invalid")
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
        or len(value) > 128
        or value.endswith((".", " "))
        or value.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_NAMES
    ):
        raise ValueError("input_snapshot_deck_output_name_invalid")
    _require_windows_safe_component(
        value,
        error="input_snapshot_deck_output_name_invalid",
        reject_device_name=True,
    )
    return value


def _digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


__all__ = (
    "CARDS_INPUT_ENVELOPE_MAX_BYTES",
    "COMPILER_INPUT_FIELDS",
    "DECK_INPUT_ENVELOPE_MAX_BYTES",
    "FrozenCompilerInputs",
    "INPUT_BLOB_MAX_BYTES",
    "INPUT_BLOB_MAX_RECORDS",
    "INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES",
    "INPUT_SNAPSHOT_FIELDS",
    "INPUT_SNAPSHOT_MAX_BYTES",
    "INPUT_SNAPSHOT_SCHEMA_VERSION",
    "InputBlobBinding",
    "OPERATOR_BINDING_FIELDS",
    "SOURCES_INPUT_ENVELOPE_MAX_BYTES",
    "ValidatedInputSnapshotManifest",
    "freeze_compiler_inputs",
    "load_frozen_compiler_inputs",
    "validate_input_snapshot_manifest_document",
)
