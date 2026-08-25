from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pytest

import hsconfig.input_snapshot_manifest as input_snapshot_manifest
from hsconfig.input_snapshot_manifest import (
    CARDS_INPUT_ENVELOPE_MAX_BYTES,
    COMPILER_INPUT_FIELDS,
    DECK_INPUT_ENVELOPE_MAX_BYTES,
    INPUT_BLOB_MAX_BYTES,
    INPUT_BLOB_MAX_RECORDS,
    INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES,
    INPUT_SNAPSHOT_FIELDS,
    INPUT_SNAPSHOT_SCHEMA_VERSION,
    OPERATOR_BINDING_FIELDS,
    SOURCES_INPUT_ENVELOPE_MAX_BYTES,
    FrozenCompilerInputs,
    freeze_compiler_inputs,
    load_frozen_compiler_inputs,
    validate_input_snapshot_manifest_document,
)
from hsconfig.io import slugify_deck_name
from hsconfig.operator_profile import (
    DeckOutputBinding,
    OperatorProfile,
    derive_deck_output_binding,
    disable_operator_profile,
    enable_operator_profile,
)
from hsconfig.package_request import (
    FrozenJsonDocument,
    PackageResolutionSnapshot,
    ResolvedPackageRequest,
)
from tests.helpers.audited_package_request import (
    audited_request_with_frozen_input_projections,
)
from tests.helpers.package_byte_contract import (
    _load_audited_catalog,
)


_BLOB_ORDER = (
    "deck",
    "full_cards",
    "collectible_cards",
    "source_acquisition",
    "source_documents",
    "globalvalues_baseline",
)
_RUNTIME_GRAMMAR_VERSION = "visionai-runtime-v1"
_COMPILER_CONTRACT_ID = "hsconfig-live-start-v1"


@dataclass
class _CapturedInputs:
    request: ResolvedPackageRequest
    snapshot: PackageResolutionSnapshot
    deck: dict[str, Any]
    full_cards: list[dict[str, Any]]
    collectible_cards: list[dict[str, Any]]
    source_acquisition: dict[str, Any]
    source_documents: dict[str, Any]
    globalvalues_baseline: dict[str, Any]
    profile: OperatorProfile
    output_binding: DeckOutputBinding


@pytest.fixture
def captured_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> _CapturedInputs:
    request, projections = audited_request_with_frozen_input_projections(
        tmp_path,
        "MechPala",
    )
    preconfig = request.snapshot.general_preconfig.to_value()

    local_app_data = tmp_path / "local-app-data"
    runtime_root = tmp_path / "runtime"
    output_base_root = tmp_path / "outputs"
    local_app_data.mkdir()
    runtime_root.mkdir()
    output_base_root.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    profile = enable_operator_profile(
        runtime_root=runtime_root,
        output_base_root=output_base_root,
        expected_predecessor_sha256=None,
    )
    deck_name = str(preconfig["deck_identity"]["deck_name"])
    return _CapturedInputs(
        request=request,
        snapshot=request.snapshot,
        deck=projections["deck"],  # type: ignore[arg-type]
        full_cards=projections["full_cards"],  # type: ignore[arg-type]
        collectible_cards=projections[  # type: ignore[arg-type]
            "collectible_cards"
        ],
        source_acquisition=projections[  # type: ignore[arg-type]
            "source_acquisition"
        ],
        source_documents=projections[  # type: ignore[arg-type]
            "source_documents"
        ],
        globalvalues_baseline=projections[  # type: ignore[arg-type]
            "globalvalues_baseline"
        ],
        profile=profile,
        output_binding=derive_deck_output_binding(profile, deck_name),
    )


def test_input_snapshot_manifest_binds_exact_six_blob_projections(
    captured_inputs: _CapturedInputs,
) -> None:
    snapshot = _freeze(captured_inputs)

    assert [row.name for row in snapshot.manifest.blobs] == [
        "deck",
        "full_cards",
        "collectible_cards",
        "source_acquisition",
        "source_documents",
        "globalvalues_baseline",
    ]
    manifest = snapshot.manifest.document.to_value()
    assert set(manifest) == INPUT_SNAPSHOT_FIELDS
    assert set(manifest["compiler_inputs"]) == COMPILER_INPUT_FIELDS
    assert set(manifest["operator_bindings"]) == OPERATOR_BINDING_FIELDS
    assert manifest["schema_version"] == INPUT_SNAPSHOT_SCHEMA_VERSION
    assert manifest["compiler_inputs"]["blobs"] == [
        {
            "name": binding.name,
            "record_count": binding.record_count,
            "sha256": binding.sha256,
            "size_bytes": binding.size_bytes,
        }
        for binding in snapshot.manifest.blobs
    ]
    bound_request = ResolvedPackageRequest.from_values(
        snapshot=captured_inputs.request.snapshot,
        invocation=captured_inputs.request.invocation,
        plan_overrides=captured_inputs.request.plan_overrides.to_value(),
        acquisition_closure_input=(
            captured_inputs.request.acquisition_closure_input.to_value()
        ),
        mulligan_gap_input=(
            captured_inputs.request.mulligan_gap_input.to_value()
        ),
        frozen_compiler_inputs=snapshot,
        starter_selection=None,
    )
    assert bound_request.frozen_compiler_inputs is snapshot
    assert not hasattr(snapshot, "__dict__")
    assert not hasattr(snapshot.manifest, "__dict__")
    for name in _BLOB_ORDER:
        document = getattr(snapshot, name)
        binding = next(
            row for row in snapshot.manifest.blobs if row.name == name
        )
        assert binding.sha256 == _digest(document.canonical_json)
        assert binding.size_bytes == len(document.canonical_json)
    source_document_count = len(
        captured_inputs.source_documents["guide_sources"]["sources"]
    )
    assert next(
        row
        for row in snapshot.manifest.blobs
        if row.name == "source_documents"
    ).record_count == source_document_count

    original_manifest = snapshot.manifest.document.canonical_json
    original_deck = snapshot.deck.canonical_json
    captured_inputs.deck["deck_identity"]["deck_name"] = "mutated"
    captured_inputs.full_cards.clear()
    captured_inputs.globalvalues_baseline.clear()
    assert snapshot.manifest.document.canonical_json == original_manifest
    assert snapshot.deck.canonical_json == original_deck


def test_snapshot_rejects_unknown_duplicate_oversized_or_wrong_typed_values(
    captured_inputs: _CapturedInputs,
) -> None:
    frozen = _freeze(captured_inputs)
    valid = frozen.manifest.document.to_value()

    with pytest.raises(ValueError, match="frozen_json_duplicate_key"):
        FrozenJsonDocument.from_json_bytes(b'{"schema_version":1,"schema_version":1}')

    unknown = deepcopy(valid)
    unknown["unexpected"] = None
    with pytest.raises(ValueError):
        validate_input_snapshot_manifest_document(
            _reseal_manifest(unknown)
        )

    for field in ("compiler_inputs", "operator_bindings"):
        nested_unknown = deepcopy(valid)
        nested_unknown[field]["unexpected"] = None
        with pytest.raises(ValueError):
            validate_input_snapshot_manifest_document(
                _reseal_manifest(nested_unknown)
            )
    blob_unknown = deepcopy(valid)
    blob_unknown["compiler_inputs"]["blobs"][0]["unexpected"] = None
    with pytest.raises(ValueError):
        validate_input_snapshot_manifest_document(
            _reseal_manifest(blob_unknown)
        )
    precondition_unknown = deepcopy(valid)
    precondition_unknown["operator_bindings"][
        "deck_output_precondition"
    ]["unexpected"] = None
    with pytest.raises(ValueError):
        validate_input_snapshot_manifest_document(
            _reseal_manifest(precondition_unknown)
        )

    duplicate = deepcopy(valid)
    duplicate["compiler_inputs"]["blobs"].append(
        deepcopy(duplicate["compiler_inputs"]["blobs"][0])
    )
    with pytest.raises(ValueError):
        validate_input_snapshot_manifest_document(
            _reseal_manifest(duplicate)
        )

    wrong_order = deepcopy(valid)
    wrong_order["compiler_inputs"]["blobs"][0:2] = reversed(
        wrong_order["compiler_inputs"]["blobs"][0:2]
    )
    with pytest.raises(ValueError):
        validate_input_snapshot_manifest_document(
            _reseal_manifest(wrong_order)
        )

    oversized = deepcopy(valid)
    oversized["operator_bindings"]["runtime_root"] = (
        "C:\\" + ("x" * (256 * 1024))
    )
    with pytest.raises(ValueError, match="input_snapshot_manifest_size_invalid"):
        validate_input_snapshot_manifest_document(
            _reseal_manifest(oversized)
        )

    wrong_digest = deepcopy(valid)
    wrong_digest["content_sha256"] = "sha256:" + ("0" * 64)
    with pytest.raises(
        ValueError,
        match="input_snapshot_manifest_content_sha256_invalid",
    ):
        validate_input_snapshot_manifest_document(
            FrozenJsonDocument.from_value(wrong_digest)
        )

    for field, value in (
        ("deck_code_sha256", "0" * 64),
        ("roster_fingerprint", "sha256:" + ("A" * 64)),
        ("bound_date", "2026-02-30"),
        ("runtime_grammar_version", "contains a space"),
        ("compiler_contract_id", "x" * 129),
    ):
        wrong_compiler_value = deepcopy(valid)
        wrong_compiler_value["compiler_inputs"][field] = value
        with pytest.raises(ValueError):
            validate_input_snapshot_manifest_document(
                _reseal_manifest(wrong_compiler_value)
            )

    for field in ("runtime_root_identity", "output_base_root_identity"):
        wrong_identity = deepcopy(valid)
        wrong_identity["operator_bindings"][field][0] = True
        with pytest.raises(ValueError):
            validate_input_snapshot_manifest_document(
                _reseal_manifest(wrong_identity)
            )
    relative_root = deepcopy(valid)
    relative_root["operator_bindings"]["runtime_root"] = "relative"
    with pytest.raises(ValueError):
        validate_input_snapshot_manifest_document(
            _reseal_manifest(relative_root)
        )
    unsafe_namespace = deepcopy(valid)
    unsafe_namespace["operator_bindings"]["runtime_root"] = (
        "\\\\.\\PIPE\\authority"
    )
    with pytest.raises(ValueError):
        validate_input_snapshot_manifest_document(
            _reseal_manifest(unsafe_namespace)
        )
    unsafe_name = deepcopy(valid)
    for value in ("..", "unsafe:name"):
        unsafe_name["operator_bindings"]["deck_output_name"] = value
        with pytest.raises(ValueError):
            validate_input_snapshot_manifest_document(
                _reseal_manifest(unsafe_name)
            )
    mixed_precondition = deepcopy(valid)
    mixed_precondition["operator_bindings"][
        "deck_output_precondition"
    ] = {"state": "absent", "identity": [1, 2, 3]}
    with pytest.raises(ValueError):
        validate_input_snapshot_manifest_document(
            _reseal_manifest(mixed_precondition)
        )

    for boolean in (True, False):
        wrong_schema = deepcopy(valid)
        wrong_schema["schema_version"] = boolean
        with pytest.raises(ValueError):
            validate_input_snapshot_manifest_document(
                _reseal_manifest(wrong_schema)
            )
        for field in ("size_bytes", "record_count"):
            wrong_integer = deepcopy(valid)
            wrong_integer["compiler_inputs"]["blobs"][0][field] = boolean
            with pytest.raises(ValueError):
                validate_input_snapshot_manifest_document(
                    _reseal_manifest(wrong_integer)
                )

    for size, accepted in (
        (0, False),
        (1, True),
        (INPUT_BLOB_MAX_BYTES, True),
        (INPUT_BLOB_MAX_BYTES + 1, False),
    ):
        candidate = deepcopy(valid)
        candidate["compiler_inputs"]["blobs"][0]["size_bytes"] = size
        _assert_manifest_acceptance(candidate, accepted=accepted)

    for record_count, accepted in (
        (0, True),
        (INPUT_BLOB_MAX_RECORDS, True),
        (INPUT_BLOB_MAX_RECORDS + 1, False),
    ):
        candidate = deepcopy(valid)
        candidate["compiler_inputs"]["blobs"][0][
            "record_count"
        ] = record_count
        _assert_manifest_acceptance(candidate, accepted=accepted)


def test_snapshot_round_trip_binds_three_physical_input_envelopes(
    captured_inputs: _CapturedInputs,
    tmp_path: Path,
) -> None:
    frozen = _freeze(captured_inputs)
    run_root = tmp_path / "run"
    envelope_bytes = _write_frozen_inputs(run_root, frozen)

    loaded = load_frozen_compiler_inputs(run_root)

    assert loaded == frozen
    assert set(envelope_bytes) == {
        "deck.json",
        "cards.json",
        "sources.json",
    }
    assert envelope_bytes["deck.json"] == frozen.deck.canonical_json
    assert json.loads(envelope_bytes["cards.json"]) == {
        "collectible_cards": frozen.collectible_cards.to_value(),
        "full_cards": frozen.full_cards.to_value(),
        "globalvalues_baseline": frozen.globalvalues_baseline.to_value(),
    }
    assert json.loads(envelope_bytes["sources.json"]) == {
        "source_acquisition": frozen.source_acquisition.to_value(),
        "source_documents": frozen.source_documents.to_value(),
    }

    cards_path = run_root / "inputs" / "cards.json"
    cards_envelope = json.loads(cards_path.read_bytes())
    cards_envelope["unexpected"] = None
    cards_path.write_bytes(_canonical(cards_envelope))
    with pytest.raises(ValueError, match="input_cards_envelope_fields_invalid"):
        load_frozen_compiler_inputs(run_root)

    cards_path.write_bytes(envelope_bytes["cards.json"])
    manifest_path = run_root / "inputs" / "input_snapshot_manifest.json"
    manifest_path.write_bytes(
        b"\xef\xbb\xbf" + frozen.manifest.document.canonical_json
    )
    with pytest.raises(ValueError, match="input_snapshot_manifest_encoding_invalid"):
        load_frozen_compiler_inputs(run_root)

    manifest_path.write_bytes(frozen.manifest.document.canonical_json)
    captured_inputs.output_binding.output_root.mkdir()
    with pytest.raises(
        ValueError,
        match="input_snapshot_deck_output_precondition_changed",
    ):
        load_frozen_compiler_inputs(run_root)


def test_snapshot_loader_observes_each_bound_input_once(
    captured_inputs: _CapturedInputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = _freeze(captured_inputs)
    expected_manifest = frozen.manifest.document.canonical_json
    expected_digests = {
        row.name: row.sha256 for row in frozen.manifest.blobs
    }

    captured_inputs.full_cards.clear()
    captured_inputs.collectible_cards.append({"id": "CHANGED"})
    captured_inputs.source_acquisition.clear()
    captured_inputs.source_documents.clear()
    captured_inputs.globalvalues_baseline.clear()

    run_root = tmp_path / "run-counted"
    _write_frozen_inputs(run_root, frozen)
    real_read = input_snapshot_manifest.read_file_no_follow
    real_require_no_streams = (
        input_snapshot_manifest.require_no_alternate_data_streams
    )
    observations: list[Path] = []
    stream_observations: list[Path] = []

    def counted_read(
        path: Path,
        *,
        expected_status: Any,
        maximum_size: int,
    ) -> bytes:
        observations.append(Path(path))
        return real_read(
            path,
            expected_status=expected_status,
            maximum_size=maximum_size,
        )

    def counted_require_no_streams(
        path: Path,
        **kwargs: Any,
    ) -> None:
        stream_observations.append(Path(path))
        real_require_no_streams(path, **kwargs)

    monkeypatch.setattr(
        input_snapshot_manifest,
        "read_file_no_follow",
        counted_read,
    )
    monkeypatch.setattr(
        input_snapshot_manifest,
        "require_no_alternate_data_streams",
        counted_require_no_streams,
    )
    loaded = load_frozen_compiler_inputs(run_root)

    assert observations == [
        run_root / "inputs" / "input_snapshot_manifest.json",
        run_root / "inputs" / "deck.json",
        run_root / "inputs" / "cards.json",
        run_root / "inputs" / "sources.json",
    ]
    assert stream_observations == [
        run_root,
        run_root / "inputs",
        run_root / "inputs" / "input_snapshot_manifest.json",
        run_root / "inputs" / "deck.json",
        run_root / "inputs" / "cards.json",
        run_root / "inputs" / "sources.json",
    ]
    assert loaded.manifest.document.canonical_json == expected_manifest
    assert {
        row.name: row.sha256 for row in loaded.manifest.blobs
    } == expected_digests


def test_snapshot_accepts_a_fully_resolvable_uncatalogued_deck(
    captured_inputs: _CapturedInputs,
) -> None:
    uncatalogued_name = "Uncatalogued Mech Paladin"
    assert uncatalogued_name not in {
        row["deck_name"] for row in _load_audited_catalog()
    }
    preconfig = captured_inputs.snapshot.general_preconfig.to_value()
    preconfig["deck_identity"]["deck_name"] = uncatalogued_name
    preconfig["deck_identity"]["deck_slug"] = slugify_deck_name(
        uncatalogued_name
    )
    preconfig["identity_graph_report"]["deck_name"] = uncatalogued_name
    preconfig["identity_gap_report"]["deck_name"] = uncatalogued_name
    snapshot = PackageResolutionSnapshot.from_preconfig(preconfig)
    binding = derive_deck_output_binding(
        captured_inputs.profile,
        uncatalogued_name,
    )

    frozen = _freeze(
        captured_inputs,
        snapshot=snapshot,
        deck=_deck_projection(preconfig),
        output_binding=binding,
    )

    assert frozen.deck.to_value()["deck_identity"]["deck_name"] == (
        uncatalogued_name
    )
    assert frozen.manifest.compiler_inputs.to_value()[
        "roster_fingerprint"
    ].endswith(preconfig["deck_identity"]["deck_fingerprint"])


def test_snapshot_rejects_an_unknown_card_before_candidate_generation(
    captured_inputs: _CapturedInputs,
) -> None:
    deck_card_id = captured_inputs.deck["deck_identity"]["cards"][0][
        "card_id"
    ]
    captured_inputs.full_cards[:] = [
        card
        for card in captured_inputs.full_cards
        if card.get("id") != deck_card_id
    ]

    with pytest.raises(
        ValueError,
        match=f"input_snapshot_unknown_deck_card:{deck_card_id}",
    ):
        _freeze(captured_inputs)


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        pytest.param(
            "missing",
            "input_snapshot_unknown_deck_card:HERO_04",
            id="missing",
        ),
        pytest.param(
            "wrong_dbf",
            "input_snapshot_card_identity_contradiction:HERO_04",
            id="wrong-dbf",
        ),
        pytest.param(
            "contradictory_aliases",
            "input_snapshot_card_identity_contradiction",
            id="contradictory-aliases",
        ),
        pytest.param(
            "duplicate",
            "input_snapshot_duplicate_full_cards_identity:HERO_04",
            id="duplicate",
        ),
        pytest.param(
            "ambiguous",
            "input_snapshot_card_identity_ambiguous:HERO_04",
            id="ambiguous",
        ),
    ),
)
def test_snapshot_requires_unambiguous_hero_feed_identity(
    captured_inputs: _CapturedInputs,
    mutation: str,
    expected_error: str,
) -> None:
    receipt = captured_inputs.deck["cards_payload"][
        "deckstring_decode_receipt"
    ]
    hero_card_id = receipt["hero_card_id"]
    hero_dbf_id = receipt["hero_dbf_id"]
    assert hero_card_id == "HERO_04"
    assert hero_dbf_id == 671
    hero_rows = [
        row
        for row in captured_inputs.full_cards
        if row.get("id") == hero_card_id
    ]
    assert len(hero_rows) == 1

    if mutation == "missing":
        captured_inputs.full_cards[:] = [
            row
            for row in captured_inputs.full_cards
            if row.get("id") != hero_card_id
        ]
        captured_inputs.collectible_cards[:] = [
            row
            for row in captured_inputs.collectible_cards
            if row.get("id") != hero_card_id
        ]
    elif mutation == "wrong_dbf":
        hero_rows[0]["dbfId"] = 100_671
    elif mutation == "contradictory_aliases":
        hero_rows[0]["cardId"] = "HERO_04_CONTRADICTION"
    elif mutation == "duplicate":
        captured_inputs.full_cards.append(deepcopy(hero_rows[0]))
    elif mutation == "ambiguous":
        captured_inputs.full_cards.remove(hero_rows[0])
        captured_inputs.full_cards.extend(
            (
                {"id": hero_card_id},
                {"dbfId": hero_dbf_id},
            )
        )
    else:  # pragma: no cover - the parametrization is closed above
        raise AssertionError(f"unknown mutation: {mutation}")

    with pytest.raises(ValueError, match=expected_error):
        _freeze(captured_inputs)


@pytest.mark.parametrize(
    "hero_card_id",
    (
        pytest.param(" HERO_04", id="leading-whitespace"),
        pytest.param("HERO_04 ", id="trailing-whitespace"),
        pytest.param("HERO-04", id="outside-card-id-grammar"),
        pytest.param("", id="empty"),
        pytest.param(True, id="boolean"),
        pytest.param(671, id="numeric"),
    ),
)
def test_snapshot_requires_canonical_receipt_hero_card_id(
    captured_inputs: _CapturedInputs,
    hero_card_id: object,
) -> None:
    preconfig = captured_inputs.snapshot.general_preconfig.to_value()
    preconfig["cards_payload"]["deckstring_decode_receipt"][
        "hero_card_id"
    ] = hero_card_id
    snapshot = PackageResolutionSnapshot.from_preconfig(preconfig)

    with pytest.raises(ValueError, match="input_snapshot_hero_identity_invalid"):
        _freeze(
            captured_inputs,
            snapshot=snapshot,
            deck=_deck_projection(preconfig),
        )


@pytest.mark.parametrize(
    "aliases",
    (
        pytest.param({"id": True}, id="boolean"),
        pytest.param({"id": 7}, id="numeric"),
        pytest.param({"id": " HERO_01 "}, id="whitespace-padded"),
        pytest.param({"id": ""}, id="empty"),
        pytest.param({"id": None}, id="null"),
        pytest.param({"id": "HERO-01"}, id="outside-card-id-grammar"),
        pytest.param(
            {"id": "HERO_01", "cardId": 7},
            id="mixed-alias-types",
        ),
    ),
)
def test_card_feed_id_aliases_are_strict_json_card_ids(
    captured_inputs: _CapturedInputs,
    aliases: dict[str, object],
) -> None:
    row = captured_inputs.full_cards[0]
    for key in ("id", "cardId", "card_id"):
        row.pop(key, None)
    row.update(aliases)

    with pytest.raises(ValueError, match="input_snapshot_card_id_invalid"):
        _freeze(captured_inputs)


@pytest.mark.parametrize(
    ("first_alias", "second_alias", "copy_owner_to_collectible"),
    (
        pytest.param("card_id", "dbf_id", False, id="id-only-vs-dbf-only"),
        pytest.param("card_id", "full", False, id="partial-vs-full"),
        pytest.param("dbf_id", "full", True, id="across-two-card-feeds"),
    ),
)
def test_snapshot_rejects_logically_duplicate_sideboard_owner_aliases(
    captured_inputs: _CapturedInputs,
    first_alias: str,
    second_alias: str,
    copy_owner_to_collectible: bool,
) -> None:
    preconfig = captured_inputs.snapshot.general_preconfig.to_value()
    deck_sideboard = preconfig["deck_identity"]["sideboards"][0]
    owner_card_id = deck_sideboard["owner_card_id"]
    owner_dbf_id = deck_sideboard["owner_dbf_id"]
    assert owner_card_id == "TOY_330"
    assert owner_dbf_id == 102_983

    for sideboards in (
        preconfig["deck_identity"]["sideboards"],
        preconfig["cards_payload"]["sideboards"],
    ):
        original = sideboards[0]
        assert len(original["cards"]) >= 2
        first = deepcopy(original)
        second = deepcopy(original)
        first["cards"] = original["cards"][:1]
        second["sideboard_index"] = 2
        second["cards"] = original["cards"][1:]
        _set_sideboard_owner_alias(
            first,
            alias=first_alias,
            card_id=owner_card_id,
            dbf_id=owner_dbf_id,
        )
        _set_sideboard_owner_alias(
            second,
            alias=second_alias,
            card_id=owner_card_id,
            dbf_id=owner_dbf_id,
        )
        sideboards[:] = [first, second]

    if copy_owner_to_collectible:
        owner_rows = [
            row
            for row in captured_inputs.full_cards
            if row.get("id") == owner_card_id
            and row.get("dbfId") == owner_dbf_id
        ]
        assert len(owner_rows) == 1
        captured_inputs.collectible_cards.append(deepcopy(owner_rows[0]))

    snapshot = PackageResolutionSnapshot.from_preconfig(preconfig)
    with pytest.raises(
        ValueError,
        match="input_snapshot_duplicate_sideboard_owner",
    ):
        _freeze(
            captured_inputs,
            snapshot=snapshot,
            deck=_deck_projection(preconfig),
        )


def test_disabled_registered_profile_freezes_writes_and_loads_for_preview(
    captured_inputs: _CapturedInputs,
    tmp_path: Path,
) -> None:
    disabled = disable_operator_profile(
        expected_predecessor_sha256=captured_inputs.profile.content_sha256
    )
    deck_name = captured_inputs.deck["deck_identity"]["deck_name"]
    binding = derive_deck_output_binding(disabled, deck_name)

    frozen = _freeze(
        captured_inputs,
        profile=disabled,
        output_binding=binding,
    )
    run_root = tmp_path / "disabled-preview-run"
    _write_frozen_inputs(run_root, frozen)

    loaded = load_frozen_compiler_inputs(run_root)

    assert disabled.live_by_default is False
    assert loaded == frozen
    assert loaded.manifest.operator_bindings.to_value()[
        "operator_profile_sha256"
    ] == disabled.content_sha256


def test_freeze_rejects_unregistered_equal_profile_and_matching_binding(
    captured_inputs: _CapturedInputs,
) -> None:
    profile = captured_inputs.profile
    binding = captured_inputs.output_binding
    forged_profile = OperatorProfile(
        schema_version=profile.schema_version,
        live_by_default=profile.live_by_default,
        runtime_root=profile.runtime_root,
        runtime_root_identity=profile.runtime_root_identity,
        output_base_root=profile.output_base_root,
        output_base_root_identity=profile.output_base_root_identity,
        content_sha256=profile.content_sha256,
    )
    forged_binding = DeckOutputBinding(
        output_name=binding.output_name,
        output_root=binding.output_root,
        precondition_state=binding.precondition_state,
        precondition_identity=binding.precondition_identity,
    )

    with pytest.raises(ValueError, match="operator_profile_unbound"):
        _freeze(
            captured_inputs,
            profile=forged_profile,
            output_binding=forged_binding,
        )


def test_freeze_rejects_profile_changed_after_capture(
    captured_inputs: _CapturedInputs,
) -> None:
    disable_operator_profile(
        expected_predecessor_sha256=captured_inputs.profile.content_sha256
    )

    with pytest.raises(ValueError, match="operator_profile_.*_changed"):
        _freeze(captured_inputs)


@pytest.mark.parametrize("transition", ("created", "replaced"))
def test_freeze_rejects_output_child_changed_after_precondition_capture(
    captured_inputs: _CapturedInputs,
    transition: str,
) -> None:
    output_root = captured_inputs.output_binding.output_root
    stale_binding = captured_inputs.output_binding
    if transition == "replaced":
        output_root.mkdir()
        deck_name = captured_inputs.deck["deck_identity"]["deck_name"]
        stale_binding = derive_deck_output_binding(
            captured_inputs.profile,
            deck_name,
        )
        output_root.rename(output_root.with_name(output_root.name + "-old"))
    output_root.mkdir()

    with pytest.raises(
        ValueError,
        match="input_snapshot_deck_output_binding_changed",
    ):
        _freeze(captured_inputs, output_binding=stale_binding)


def test_freeze_rejects_supplied_binding_unequal_to_fresh_derivation(
    captured_inputs: _CapturedInputs,
) -> None:
    supplied = DeckOutputBinding(
        output_name=captured_inputs.output_binding.output_name,
        output_root=captured_inputs.output_binding.output_root,
        precondition_state="existing",
        precondition_identity=(1, 2, 3),
    )

    with pytest.raises(
        ValueError,
        match="input_snapshot_deck_output_binding_changed",
    ):
        _freeze(captured_inputs, output_binding=supplied)


def test_pure_manifest_validation_needs_no_envelopes_or_local_roots(
    captured_inputs: _CapturedInputs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _freeze(captured_inputs).manifest.document.to_value()
    manifest["operator_bindings"]["runtime_root"] = str(
        (tmp_path / "missing-runtime").absolute()
    )
    manifest["operator_bindings"]["output_base_root"] = str(
        (tmp_path / "missing-outputs").absolute()
    )
    document = _reseal_manifest(manifest)

    def filesystem_forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("pure_manifest_validation_touched_filesystem")

    monkeypatch.setattr(Path, "lstat", filesystem_forbidden)
    monkeypatch.setattr(Path, "resolve", filesystem_forbidden)
    monkeypatch.setattr(
        input_snapshot_manifest,
        "plain_file_status",
        filesystem_forbidden,
    )
    monkeypatch.setattr(
        input_snapshot_manifest,
        "read_file_no_follow",
        filesystem_forbidden,
    )

    validated = validate_input_snapshot_manifest_document(document)

    assert validated.document.document.canonical_json == (
        document.canonical_json
    )


def test_physical_envelope_limits_cover_exact_blob_count_and_json_overhead(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    assert DECK_INPUT_ENVELOPE_MAX_BYTES == (
        INPUT_BLOB_MAX_BYTES + INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES
    )
    assert CARDS_INPUT_ENVELOPE_MAX_BYTES == (
        3 * INPUT_BLOB_MAX_BYTES + INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES
    )
    assert SOURCES_INPUT_ENVELOPE_MAX_BYTES == (
        2 * INPUT_BLOB_MAX_BYTES + INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES
    )
    assert CARDS_INPUT_ENVELOPE_MAX_BYTES > (
        2 * INPUT_BLOB_MAX_BYTES + INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES
    )

    scaled_file_maximum = 31
    input_path = tmp_path / "scaled-input.json"
    exact_bytes = b"x" * scaled_file_maximum
    input_path.write_bytes(exact_bytes)
    assert input_snapshot_manifest._read_input_file_once(
        input_path,
        maximum_bytes=scaled_file_maximum,
    ) == exact_bytes
    input_path.write_bytes(exact_bytes + b"x")
    with pytest.raises(ValueError, match="input_envelope_size_invalid"):
        input_snapshot_manifest._read_input_file_once(
            input_path,
            maximum_bytes=scaled_file_maximum,
        )

    scaled_blob_maximum = 30
    scaled_json_overhead = 61
    scaled_cards_maximum = 151
    documents = {
        "deck": FrozenJsonDocument.from_value({}),
        "full_cards": FrozenJsonDocument.from_value(
            {"cards": [], "pad": "x" * 9}
        ),
        "collectible_cards": FrozenJsonDocument.from_value(
            {"cards": [], "pad": "x" * 9}
        ),
        "source_acquisition": FrozenJsonDocument.from_value({}),
        "source_documents": FrozenJsonDocument.from_value({}),
        "globalvalues_baseline": FrozenJsonDocument.from_value(
            {"pad": "x" * 20}
        ),
    }
    monkeypatch.setattr(
        input_snapshot_manifest,
        "INPUT_BLOB_MAX_BYTES",
        scaled_blob_maximum,
    )
    for name in (
        "full_cards",
        "collectible_cards",
        "globalvalues_baseline",
    ):
        binding = input_snapshot_manifest._binding_for_document(
            name,
            documents[name],
        )
        assert binding.size_bytes == scaled_blob_maximum
    assert scaled_cards_maximum == (
        3 * scaled_blob_maximum + scaled_json_overhead
    )
    assert scaled_cards_maximum > (
        2 * scaled_blob_maximum + scaled_json_overhead
    )
    cards_envelope = FrozenJsonDocument.from_value(
        {
            "full_cards": documents["full_cards"].to_value(),
            "collectible_cards": documents["collectible_cards"].to_value(),
            "globalvalues_baseline": documents[
                "globalvalues_baseline"
            ].to_value(),
        }
    )
    assert len(cards_envelope.canonical_json) == scaled_cards_maximum

    monkeypatch.setattr(
        input_snapshot_manifest,
        "CARDS_INPUT_ENVELOPE_MAX_BYTES",
        scaled_cards_maximum,
    )
    input_snapshot_manifest._validate_envelope_sizes(documents)
    monkeypatch.setattr(
        input_snapshot_manifest,
        "CARDS_INPUT_ENVELOPE_MAX_BYTES",
        scaled_cards_maximum - 1,
    )
    with pytest.raises(ValueError, match="input_cards_envelope_size_invalid"):
        input_snapshot_manifest._validate_envelope_sizes(documents)


def _freeze(
    captured: _CapturedInputs,
    *,
    snapshot: PackageResolutionSnapshot | None = None,
    deck: dict[str, Any] | None = None,
    profile: OperatorProfile | None = None,
    output_binding: DeckOutputBinding | None = None,
) -> FrozenCompilerInputs:
    return freeze_compiler_inputs(
        snapshot=captured.snapshot if snapshot is None else snapshot,
        deck=captured.deck if deck is None else deck,
        full_cards=captured.full_cards,
        collectible_cards=captured.collectible_cards,
        source_acquisition=captured.source_acquisition,
        source_documents=captured.source_documents,
        globalvalues_baseline=captured.globalvalues_baseline,
        bound_date="2026-07-29",
        runtime_grammar_version=_RUNTIME_GRAMMAR_VERSION,
        compiler_contract_id=_COMPILER_CONTRACT_ID,
        operator_profile=(captured.profile if profile is None else profile),
        deck_output_binding=(
            captured.output_binding
            if output_binding is None
            else output_binding
        ),
    )


def _deck_projection(preconfig: dict[str, Any]) -> dict[str, Any]:
    return {
        "cards_payload": deepcopy(preconfig["cards_payload"]),
        "deck_identity": deepcopy(preconfig["deck_identity"]),
    }


def _set_sideboard_owner_alias(
    row: dict[str, Any],
    *,
    alias: str,
    card_id: str,
    dbf_id: int,
) -> None:
    row["owner_card_id"] = card_id if alias in {"card_id", "full"} else None
    row["owner_dbf_id"] = dbf_id if alias in {"dbf_id", "full"} else None


def _write_frozen_inputs(
    run_root: Path,
    frozen: FrozenCompilerInputs,
) -> dict[str, bytes]:
    inputs = run_root / "inputs"
    inputs.mkdir(parents=True)
    cards = FrozenJsonDocument.from_value(
        {
            "full_cards": frozen.full_cards.to_value(),
            "collectible_cards": frozen.collectible_cards.to_value(),
            "globalvalues_baseline": (
                frozen.globalvalues_baseline.to_value()
            ),
        }
    ).canonical_json
    sources = FrozenJsonDocument.from_value(
        {
            "source_acquisition": frozen.source_acquisition.to_value(),
            "source_documents": frozen.source_documents.to_value(),
        }
    ).canonical_json
    envelope_bytes = {
        "deck.json": frozen.deck.canonical_json,
        "cards.json": cards,
        "sources.json": sources,
    }
    (inputs / "input_snapshot_manifest.json").write_bytes(
        frozen.manifest.document.canonical_json
    )
    for filename, content in envelope_bytes.items():
        (inputs / filename).write_bytes(content)
    return envelope_bytes


def _assert_manifest_acceptance(
    value: dict[str, Any],
    *,
    accepted: bool,
) -> None:
    document = _reseal_manifest(value)
    if accepted:
        validate_input_snapshot_manifest_document(document)
        return
    with pytest.raises(ValueError):
        validate_input_snapshot_manifest_document(document)


def _reseal_manifest(value: dict[str, Any]) -> FrozenJsonDocument:
    unsigned = deepcopy(value)
    unsigned.pop("content_sha256", None)
    digest = _digest(FrozenJsonDocument.from_value(unsigned).canonical_json)
    return FrozenJsonDocument.from_value(
        {**unsigned, "content_sha256": digest}
    )


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()
