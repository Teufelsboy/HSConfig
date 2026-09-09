from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import patch

import pytest

from hsconfig import input_snapshot_manifest
from hsconfig.guide_source_builder import (
    build_guide_builder_receipt,
    research_required_guide_sources,
)
from hsconfig.input_snapshot_manifest import (
    FrozenCompilerInputs,
    INPUT_SNAPSHOT_FIELDS,
    INPUT_SNAPSHOT_SCHEMA_VERSION,
    freeze_compiler_inputs,
    validate_input_snapshot_manifest_document,
)
from hsconfig.operator_profile import (
    derive_deck_output_binding,
    enable_operator_profile,
)
from hsconfig.package_request import FrozenJsonDocument, PackageResolutionSnapshot
from hsconfig.starter_context import (
    StarterContext,
    _enforce_starter_context_max_bytes,
    build_single_candidate_starter_context,
    build_starter_context,
    validate_starter_context_document,
)
from hsconfig.starter_contract import (
    SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS,
    SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_document import StarterDocument, seal_starter_document
from tests.helpers.audited_package_request import (
    audited_request,
    audited_request_with_frozen_input_projections,
)


SHADOWPRIEST_CARD_COUNTS = {
    "CFM_637": 1,
    "DRG_056": 2,
    "DS1_233": 2,
    "GVG_009": 2,
    "NX2_019": 2,
    "REV_290": 2,
    "SCH_514": 2,
    "SW_444": 2,
    "SW_446": 2,
    "SW_448": 1,
    "TOY_381": 2,
    "TOY_518": 2,
    "VAC_419": 2,
    "VAC_512": 2,
    "WON_065": 2,
    "YOD_032": 2,
}


@pytest.fixture(scope="module")
def single_candidate_inputs(
    tmp_path_factory: pytest.TempPathFactory,
) -> FrozenCompilerInputs:
    root = tmp_path_factory.mktemp("single-candidate-context")
    request, projections = audited_request_with_frozen_input_projections(
        root,
        "MechPala",
    )
    preconfig = request.snapshot.general_preconfig.to_value()
    local_app_data = root / "local-app-data"
    runtime_root = root / "runtime"
    output_base_root = root / "outputs"
    for path in (local_app_data, runtime_root, output_base_root):
        path.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        profile = enable_operator_profile(
            runtime_root=runtime_root,
            output_base_root=output_base_root,
            expected_predecessor_sha256=None,
        )
        return freeze_compiler_inputs(
            snapshot=request.snapshot,
            deck=projections["deck"],
            full_cards=projections["full_cards"],
            collectible_cards=projections["collectible_cards"],
            source_acquisition=projections["source_acquisition"],
            source_documents=projections["source_documents"],
            globalvalues_baseline=projections["globalvalues_baseline"],
            bound_date="2026-08-25",
            runtime_grammar_version="visionai-runtime-v1",
            compiler_contract_id="hsconfig-live-start-v1",
            operator_profile=profile,
            deck_output_binding=derive_deck_output_binding(
                profile,
                str(preconfig["deck_identity"]["deck_name"]),
            ),
        )


def _replace_frozen_input_blob(
    inputs: FrozenCompilerInputs,
    name: str,
    value: object,
) -> FrozenCompilerInputs:
    document = FrozenJsonDocument.from_value(value)
    manifest_value = inputs.manifest.document.to_value()
    del manifest_value["content_sha256"]
    binding = next(
        row
        for row in manifest_value["compiler_inputs"]["blobs"]
        if row["name"] == name
    )
    binding.update(
        {
            "sha256": "sha256:" + sha256(document.canonical_json).hexdigest(),
            "size_bytes": len(document.canonical_json),
            "record_count": input_snapshot_manifest._record_count(name, value),
        }
    )
    sealed_manifest = seal_starter_document(
        manifest_value,
        expected_fields=INPUT_SNAPSHOT_FIELDS,
        schema_version=INPUT_SNAPSHOT_SCHEMA_VERSION,
    )
    manifest = validate_input_snapshot_manifest_document(
        sealed_manifest.document
    )
    return replace(inputs, manifest=manifest, **{name: document})


def _replace_frozen_source_pair(
    inputs: FrozenCompilerInputs,
    *,
    source_acquisition: object,
    source_documents: object,
) -> FrozenCompilerInputs:
    rebound = _replace_frozen_input_blob(
        inputs,
        "source_documents",
        source_documents,
    )
    return _replace_frozen_input_blob(
        rebound,
        "source_acquisition",
        source_acquisition,
    )


def _set_stale_without_downgraded_source(value: dict[str, Any]) -> None:
    evidence = value["source_evidence"]
    evidence["guide_builder_receipt"]["stale_source_count"] = 1
    evidence["guide_sources_summary"]["stale_source_count"] = 1
    evidence["guide_sources_summary"]["downgraded_source_count"] = 0


def test_schema_two_context_binds_frozen_snapshot_and_exact_cards(
    single_candidate_inputs: FrozenCompilerInputs,
) -> None:
    # Break caught: a V2 context can omit its sealed input authority or project
    # a physical-card roster different from the already frozen deck.
    context = build_single_candidate_starter_context(single_candidate_inputs)
    value = context.document.to_value()
    manifest = single_candidate_inputs.manifest.document.to_value()
    compiler = manifest["compiler_inputs"]
    frozen_deck = single_candidate_inputs.deck.to_value()["deck_identity"]

    assert value["schema_version"] == SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION
    assert set(value) == SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS
    assert value["input_snapshot_manifest_sha256"] == (
        single_candidate_inputs.manifest.document.content_sha256
    )
    assert value["deck_identity"] == {
        "card_count_total": frozen_deck["card_count_total"],
        "deck_code_sha256": frozen_deck["deck_code_hash"],
        "deck_fingerprint": frozen_deck["deck_fingerprint"],
        "deck_name": frozen_deck["deck_name"],
        "format": frozen_deck["format"],
        "hero_dbf_id": frozen_deck["hero_dbf_id"],
        "unique_card_count": len(frozen_deck["main_deck"]),
    }
    assert {
        row["card_id"]: row["count"] for row in value["cards"]
    } == {
        row["card_id"]: row["count"] for row in frozen_deck["main_deck"]
    }
    assert value["globalvalues_baseline"] == {
        "content_sha256": context.globalvalues_baseline_sha256,
        "key_count": 38,
        "values": single_candidate_inputs.globalvalues_baseline.to_value(),
    }
    assert set(value["source_evidence"]) == {
        "guide_builder_receipt",
        "guide_sources_summary",
    }
    assert "receipt" not in value["globalvalues_baseline"]
    assert "hs_id" not in value["deck_identity"]
    assert "hdt_deck_id" not in value["deck_identity"]
    assert compiler["deck_code_sha256"] == (
        "sha256:" + value["deck_identity"]["deck_code_sha256"]
    )
    assert compiler["roster_fingerprint"] == (
        "sha256:" + value["deck_identity"]["deck_fingerprint"]
    )
    assert validate_starter_context_document(context.document) == context


def test_schema_two_context_normalizes_source_card_line_breaks_before_sealing(
    single_candidate_inputs: FrozenCompilerInputs,
) -> None:
    # Break caught: ordinary CR/LF presentation breaks from the public card
    # source reach the sealed context and are rejected as unsafe controls.
    deck = single_candidate_inputs.deck.to_value()
    card = next(
        row
        for row in deck["cards_payload"]["cards"]
        if row["card_id"] == "BOT_020"
    )
    card["text"] = (
        "[x]After you play a Pirate,\r\nsummon this minion\n"
        "from your deck.\r<b>Charge</b>"
    )
    rebound = _replace_frozen_input_blob(
        single_candidate_inputs,
        "deck",
        deck,
    )

    context = build_single_candidate_starter_context(rebound)
    projected = next(
        row
        for row in context.document.to_value()["cards"]
        if row["card_id"] == "BOT_020"
    )

    assert projected["text"] == (
        "[x]After you play a Pirate, summon this minion "
        "from your deck. <b>Charge</b>"
    )


@pytest.mark.parametrize("forbidden_control", ("\t", "\x00"))
def test_schema_two_context_rejects_other_source_card_controls(
    single_candidate_inputs: FrozenCompilerInputs,
    forbidden_control: str,
) -> None:
    # Break caught: the source line-break exception broadens into arbitrary
    # control-character normalization before sealing.
    deck = single_candidate_inputs.deck.to_value()
    card = next(
        row
        for row in deck["cards_payload"]["cards"]
        if row["card_id"] == "BOT_020"
    )
    card["text"] = f"Before{forbidden_control}After"
    rebound = _replace_frozen_input_blob(
        single_candidate_inputs,
        "deck",
        deck,
    )

    with pytest.raises(ValueError, match="^starter_context_document_invalid$"):
        build_single_candidate_starter_context(rebound)


def test_starter_context_validator_rejects_resealed_card_text_line_break(
    single_candidate_inputs: FrozenCompilerInputs,
) -> None:
    # Break caught: accepting CR/LF in an already projected document weakens
    # the strict sealed-context boundary instead of fixing source projection.
    context = build_single_candidate_starter_context(single_candidate_inputs)
    value = context.document.to_value()
    del value["content_sha256"]
    value["cards"][0]["text"] = "Before\nAfter"
    tampered = seal_starter_document(
        value,
        expected_fields=SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS,
        schema_version=SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    )

    with pytest.raises(ValueError, match="^starter_context_document_invalid$"):
        validate_starter_context_document(tampered)


def test_schema_two_context_closes_frozen_source_receipts_rows_and_claim_counts(
    single_candidate_inputs: FrozenCompilerInputs,
) -> None:
    # Breaks caught: copying a partially validated receipt/summary or silently
    # dropping unknown source-row/raw-claim fields before claim validation.
    context = build_single_candidate_starter_context(single_candidate_inputs)
    evidence = context.document.to_value()["source_evidence"]
    receipt = evidence["guide_builder_receipt"]
    summary = evidence["guide_sources_summary"]
    source_documents = single_candidate_inputs.source_documents.to_value()
    guide_sources = source_documents["guide_sources"]
    sources = guide_sources["sources"]
    flattened_claims = [
        claim for source in sources for claim in source["claims"]
    ]

    assert set(receipt) == {
        "claim_count",
        "deck_code_hash",
        "deck_name",
        "schema_version",
        "source_count",
        "source_depth_status",
        "stale_source_count",
        "static_card_semantics_used",
    }
    assert set(summary) == {
        "claim_count",
        "downgraded_source_count",
        "source_count",
        "stale_source_count",
        "static_card_semantics_used",
        "unsupported_claim_count",
    }
    assert receipt["source_count"] == summary["source_count"] == len(sources)
    assert (
        receipt["claim_count"]
        == summary["claim_count"]
        == len(flattened_claims)
        == len(context.document.to_value()["existing_claims"])
    )
    assert receipt["deck_name"] == guide_sources["deck_name"]
    assert receipt["deck_code_hash"] == guide_sources["deck_code_hash"]
    assert (
        receipt["source_depth_status"]
        == guide_sources["source_depth_status"]
    )

    mutations: tuple[tuple[str, Callable[[dict[str, Any]], None]], ...] = (
        (
            "source_acquisition",
            lambda value: value["guide_builder_receipt"].__setitem__(
                "invented", "hidden"
            ),
        ),
        (
            "source_acquisition",
            lambda value: value["guide_builder_receipt"].__setitem__(
                "schema_version", True
            ),
        ),
        (
            "source_acquisition",
            lambda value: value["guide_builder_receipt"].__setitem__(
                "source_count", True
            ),
        ),
        (
            "source_acquisition",
            lambda value: value["guide_builder_receipt"].__setitem__(
                "static_card_semantics_used", 1
            ),
        ),
        (
            "source_acquisition",
            lambda value: value["guide_builder_receipt"].__setitem__(
                "deck_name", "WrongDeck"
            ),
        ),
        (
            "source_acquisition",
            lambda value: value["guide_builder_receipt"].__setitem__(
                "deck_code_hash", "0" * 64
            ),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"]["sources"][0].__setitem__(
                "invented", "hidden"
            ),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"]["sources"][0]["claims"][
                0
            ].__setitem__("invented", "hidden"),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"]["sources"][0]["claims"][
                0
            ].update({"source_family": "metadata", "source": "metadata"}),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"]["sources"][0]["claims"][
                0
            ].__setitem__(
                "source_refs",
                [
                    "source:999",
                    value["guide_sources"]["sources"][0]["source_url"],
                ],
            ),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"]["sources"][0]["claims"][
                0
            ].__setitem__("source_url", "https://example.invalid/wrong"),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"]["sources"][0].__setitem__(
                "source_family", "metadata"
            ),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"].__setitem__(
                "schema_version", True
            ),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"].__setitem__(
                "source_depth_status", "different"
            ),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"]["sources"].pop(),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"]["sources"][0]["claims"].pop(),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"]["summary"].__setitem__(
                "source_count", True
            ),
        ),
        (
            "source_documents",
            lambda value: value["guide_sources"]["sources"][0].__setitem__(
                "unsupported_claim_count", True
            ),
        ),
    )
    for name, mutate in mutations:
        mutated = getattr(single_candidate_inputs, name).to_value()
        mutate(mutated)
        rebound = _replace_frozen_input_blob(single_candidate_inputs, name, mutated)
        with pytest.raises(ValueError):
            build_single_candidate_starter_context(rebound)


@pytest.mark.parametrize(
    "defect",
    (
        "stale_exceeds_sources",
        "downgraded_exceeds_sources",
        "static_semantics_with_sources",
        "wrong_clean_source_depth",
    ),
)
def test_schema_two_context_rejects_impossible_guide_source_summary_matrix(
    single_candidate_inputs: FrozenCompilerInputs,
    defect: str,
) -> None:
    # Break caught: mutually consistent copied receipt/summary values can still
    # contradict the source rows and the guide_source_builder state matrix.
    source_acquisition = single_candidate_inputs.source_acquisition.to_value()
    source_documents = single_candidate_inputs.source_documents.to_value()
    receipt = source_acquisition["guide_builder_receipt"]
    guide_sources = source_documents["guide_sources"]
    summary = guide_sources["summary"]
    source_count = len(guide_sources["sources"])
    assert source_count > 0
    assert summary["claim_count"] > 0
    assert summary["downgraded_source_count"] == 0

    if defect == "stale_exceeds_sources":
        receipt["stale_source_count"] = source_count + 1
        summary["stale_source_count"] = source_count + 1
    elif defect == "downgraded_exceeds_sources":
        summary["downgraded_source_count"] = source_count + 1
    elif defect == "static_semantics_with_sources":
        receipt["static_card_semantics_used"] = True
        summary["static_card_semantics_used"] = True
    elif defect == "wrong_clean_source_depth":
        receipt["source_depth_status"] = "needs_more_research"
        guide_sources["source_depth_status"] = "needs_more_research"
    else:  # pragma: no cover - closed parametrization
        raise AssertionError(f"unknown_source_matrix_defect:{defect}")

    rebound = _replace_frozen_source_pair(
        single_candidate_inputs,
        source_acquisition=source_acquisition,
        source_documents=source_documents,
    )
    with pytest.raises(ValueError):
        build_single_candidate_starter_context(rebound)


def test_schema_two_context_accepts_warning_derived_guide_source_matrix(
    single_candidate_inputs: FrozenCompilerInputs,
) -> None:
    # Control: one warning-bearing source derives one stale and one downgraded
    # source and therefore the needs-more-research depth.
    source_acquisition = single_candidate_inputs.source_acquisition.to_value()
    source_documents = single_candidate_inputs.source_documents.to_value()
    receipt = source_acquisition["guide_builder_receipt"]
    guide_sources = source_documents["guide_sources"]
    summary = guide_sources["summary"]
    guide_sources["sources"][0]["warnings"] = [{"reason": "stale_source"}]
    receipt["stale_source_count"] = 1
    summary["stale_source_count"] = 1
    summary["downgraded_source_count"] = 1
    receipt["source_depth_status"] = "needs_more_research"
    guide_sources["source_depth_status"] = "needs_more_research"
    rebound = _replace_frozen_source_pair(
        single_candidate_inputs,
        source_acquisition=source_acquisition,
        source_documents=source_documents,
    )

    context = build_single_candidate_starter_context(rebound)

    assert context.document.to_value()["source_evidence"] == {
        "guide_builder_receipt": receipt,
        "guide_sources_summary": summary,
    }


def test_schema_two_context_accepts_exact_deck_name_mismatch_warning(
    single_candidate_inputs: FrozenCompilerInputs,
) -> None:
    # Control: the producer emits this warning when one source document names a
    # different deck; that downgraded source remains valid frozen evidence.
    source_acquisition = single_candidate_inputs.source_acquisition.to_value()
    source_documents = single_candidate_inputs.source_documents.to_value()
    receipt = source_acquisition["guide_builder_receipt"]
    guide_sources = source_documents["guide_sources"]
    summary = guide_sources["summary"]
    guide_sources["sources"][0]["deck_name"] = "Different Deck"
    guide_sources["sources"][0]["warnings"] = [
        {"reason": "deck_name_mismatch"}
    ]
    summary["downgraded_source_count"] = 1
    receipt["source_depth_status"] = "needs_more_research"
    guide_sources["source_depth_status"] = "needs_more_research"
    rebound = _replace_frozen_source_pair(
        single_candidate_inputs,
        source_acquisition=source_acquisition,
        source_documents=source_documents,
    )

    context = build_single_candidate_starter_context(rebound)

    assert context.document.to_value()["source_evidence"] == {
        "guide_builder_receipt": receipt,
        "guide_sources_summary": summary,
    }


@pytest.mark.parametrize(
    "defect",
    ("mismatch_without_warning", "warning_without_mismatch"),
)
def test_schema_two_context_rejects_deck_name_warning_contradictions(
    single_candidate_inputs: FrozenCompilerInputs,
    defect: str,
) -> None:
    source_acquisition = single_candidate_inputs.source_acquisition.to_value()
    source_documents = single_candidate_inputs.source_documents.to_value()
    receipt = source_acquisition["guide_builder_receipt"]
    guide_sources = source_documents["guide_sources"]
    summary = guide_sources["summary"]
    source = guide_sources["sources"][0]
    if defect == "mismatch_without_warning":
        source["deck_name"] = "Different Deck"
    elif defect == "warning_without_mismatch":
        source["warnings"] = [{"reason": "deck_name_mismatch"}]
        summary["downgraded_source_count"] = 1
        receipt["source_depth_status"] = "needs_more_research"
        guide_sources["source_depth_status"] = "needs_more_research"
    else:  # pragma: no cover - closed parametrization
        raise AssertionError(f"unknown_deck_name_warning_defect:{defect}")
    rebound = _replace_frozen_source_pair(
        single_candidate_inputs,
        source_acquisition=source_acquisition,
        source_documents=source_documents,
    )

    with pytest.raises(ValueError):
        build_single_candidate_starter_context(rebound)


def test_schema_two_context_accepts_only_closed_research_required_zero_sources(
    single_candidate_inputs: FrozenCompilerInputs,
) -> None:
    # Break caught: rejecting the legitimate no-source producer merely because
    # its closed five-field summary does not fabricate unsupported_claim_count.
    deck_identity = single_candidate_inputs.deck.to_value()["deck_identity"]
    guide_sources = research_required_guide_sources(
        str(deck_identity["deck_name"]),
        deck_identity,
    )
    assert "unsupported_claim_count" not in guide_sources["summary"]
    source_documents = {"guide_sources": guide_sources}
    source_acquisition = single_candidate_inputs.source_acquisition.to_value()
    source_acquisition["guide_builder_receipt"] = build_guide_builder_receipt(
        deck_name=str(deck_identity["deck_name"]),
        deck_identity=deck_identity,
        source_documents=[],
        guide_sources=guide_sources,
    )
    rebound = _replace_frozen_input_blob(
        single_candidate_inputs,
        "source_documents",
        source_documents,
    )
    rebound = _replace_frozen_input_blob(
        rebound,
        "source_acquisition",
        source_acquisition,
    )

    context = build_single_candidate_starter_context(rebound)
    value = context.document.to_value()

    assert value["source_evidence"]["guide_sources_summary"] == (
        guide_sources["summary"]
    )
    assert "unsupported_claim_count" not in (
        value["source_evidence"]["guide_sources_summary"]
    )
    assert value["existing_claims"] == []

    static_sources = deepcopy(source_documents)
    static_sources["guide_sources"]["source_depth_status"] = (
        "static_semantics_only"
    )
    static_sources["guide_sources"]["summary"].update(
        {
            "unsupported_claim_count": 0,
            "static_card_semantics_used": True,
        }
    )
    static_acquisition = deepcopy(source_acquisition)
    static_acquisition["guide_builder_receipt"] = build_guide_builder_receipt(
        deck_name=str(deck_identity["deck_name"]),
        deck_identity=deck_identity,
        source_documents=[],
        guide_sources=static_sources["guide_sources"],
    )
    static_rebound = _replace_frozen_source_pair(
        single_candidate_inputs,
        source_acquisition=static_acquisition,
        source_documents=static_sources,
    )
    static_context = build_single_candidate_starter_context(static_rebound)
    assert static_context.document.to_value()["source_evidence"][
        "guide_sources_summary"
    ]["unsupported_claim_count"] == 0

    invalid_mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
        lambda value: value["guide_sources"].__setitem__(
            "source_depth_status", "source_backed"
        ),
        lambda value: value["guide_sources"]["summary"].__setitem__(
            "source_count", 1
        ),
        lambda value: value["guide_sources"]["summary"].__setitem__(
            "claim_count", 1
        ),
        lambda value: value["guide_sources"]["summary"].__setitem__(
            "stale_source_count", 1
        ),
        lambda value: value["guide_sources"]["summary"].__setitem__(
            "downgraded_source_count", 1
        ),
        lambda value: value["guide_sources"]["summary"].__setitem__(
            "static_card_semantics_used", True
        ),
    )
    for mutate in invalid_mutations:
        invalid_weak = deepcopy(source_documents)
        mutate(invalid_weak)
        invalid_rebound = _replace_frozen_input_blob(
            rebound,
            "source_documents",
            invalid_weak,
        )
        with pytest.raises(ValueError):
            build_single_candidate_starter_context(invalid_rebound)


def test_schema_two_context_validator_rejects_inner_source_summary_drift(
    single_candidate_inputs: FrozenCompilerInputs,
) -> None:
    # Break caught: validating only the two outer source-evidence keys while
    # trusting copied nested counts, types, deck bindings, or claim totals.
    context = build_single_candidate_starter_context(single_candidate_inputs)
    mutations: tuple[Callable[[dict[str, Any]], None], ...] = (
        lambda value: value["source_evidence"]["guide_builder_receipt"].__setitem__(
            "invented", "hidden"
        ),
        lambda value: value["source_evidence"]["guide_builder_receipt"].__setitem__(
            "schema_version", True
        ),
        lambda value: value["source_evidence"]["guide_builder_receipt"].__setitem__(
            "claim_count", True
        ),
        lambda value: value["source_evidence"]["guide_builder_receipt"].__setitem__(
            "deck_name", "WrongDeck"
        ),
        lambda value: value["source_evidence"]["guide_builder_receipt"].__setitem__(
            "deck_code_hash", "0" * 64
        ),
        lambda value: value["source_evidence"]["guide_sources_summary"].__setitem__(
            "source_count", True
        ),
        lambda value: value["source_evidence"]["guide_sources_summary"].__setitem__(
            "static_card_semantics_used", 1
        ),
        lambda value: value["existing_claims"].pop(),
        _set_stale_without_downgraded_source,
    )
    for mutate in mutations:
        value = context.document.to_value()
        del value["content_sha256"]
        mutate(value)
        document = seal_starter_document(
            value,
            expected_fields=SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS,
            schema_version=SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
        )
        with pytest.raises(ValueError, match="^starter_context_document_invalid$"):
            validate_starter_context_document(document)


def test_schema_two_context_never_reobserves_sources_cards_or_baseline(
    single_candidate_inputs: FrozenCompilerInputs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: rebuilding V2 through the legacy resolver, a catalog, or an
    # operator-root rebind instead of consuming the six in-memory blobs.
    def unexpected_call(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("single_candidate_context_reobserved_input")

    monkeypatch.setattr(
        "hsconfig.starter_context.build_starter_context",
        unexpected_call,
    )
    monkeypatch.setattr(
        "hsconfig.starter_context.load_audited_deck_catalog",
        unexpected_call,
    )
    monkeypatch.setattr(
        "hsconfig.starter_context.load_packaged_audited_build_inputs",
        unexpected_call,
    )
    monkeypatch.setattr(
        "hsconfig.input_snapshot_manifest._rebind_operator_bindings",
        unexpected_call,
    )

    first = build_single_candidate_starter_context(single_candidate_inputs)
    second = build_single_candidate_starter_context(single_candidate_inputs)

    assert first == second
    assert first.document.canonical_json == second.document.canonical_json


def test_schema_two_context_rejects_unknown_fields_and_snapshot_drift(
    single_candidate_inputs: FrozenCompilerInputs,
) -> None:
    # Break caught: accepting cross-schema context fields or trusting forged
    # FrozenCompilerInputs caches whose bytes no longer match the manifest.
    context = build_single_candidate_starter_context(single_candidate_inputs)
    unknown = context.document.to_value()
    unknown["invented_authority"] = "hidden"
    unknown_document = StarterDocument(
        document=FrozenJsonDocument.from_value(unknown),
        content_sha256=context.document.content_sha256,
    )
    with pytest.raises(ValueError, match="^starter_context_document_invalid$"):
        validate_starter_context_document(unknown_document)

    cross_schema_value = context.document.to_value()
    del cross_schema_value["content_sha256"]
    cross_schema_value["schema_version"] = STARTER_SCHEMA_VERSION
    cross_schema = seal_starter_document(
        cross_schema_value,
        expected_fields=SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    with pytest.raises(ValueError, match="^starter_context_document_invalid$"):
        validate_starter_context_document(cross_schema)

    drifted_deck = FrozenJsonDocument.from_value(
        {
            **single_candidate_inputs.deck.to_value(),
            "unbound": True,
        }
    )
    with pytest.raises(ValueError, match="^starter_context_inputs_invalid$"):
        build_single_candidate_starter_context(
            replace(single_candidate_inputs, deck=drifted_deck)
        )

    forged_manifest_cache = replace(single_candidate_inputs.manifest, blobs=())
    with pytest.raises(ValueError, match="^starter_context_inputs_invalid$"):
        build_single_candidate_starter_context(
            replace(single_candidate_inputs, manifest=forged_manifest_cache)
        )


def test_sealed_starter_context_validator_accepts_canonical_shadowpriest(
    tmp_path: Path,
) -> None:
    from hsconfig.starter_context import validate_starter_context_document

    context = build_starter_context(
        audited_request(tmp_path, "ShadowPriest").snapshot
    )

    validated = validate_starter_context_document(context.document)

    assert validated == context
    assert validated.document.canonical_json == context.document.canonical_json
    assert validated.deck_fingerprint == (
        "831b989cf8d076bff87848b4d0d6f382c9d306fddea7619017f0c361bfc92327"
    )


@pytest.mark.parametrize(
    "defect",
    (
        "source_evidence_wrong_type",
        "source_row_unknown_key",
        "source_gap_missing_key",
        "source_provenance_drift",
        "source_claim_count_drift",
        "deck_identity_unknown_key",
        "cards_missing_key",
        "linked_entity_unknown_key",
        "identity_card_count_drift",
        "deck_shape_drift",
        "runtime_contract_unknown_key",
        "baseline_missing_key",
        "baseline_receipt_drift",
        "existing_claim_unknown_key",
        "claim_card_unbound",
        "claim_deck_match_drift",
        "claim_source_family_drift",
        "safety_boundary_missing_key",
    ),
)
def test_sealed_starter_context_validator_rejects_nested_family_drift(
    tmp_path: Path,
    defect: str,
) -> None:
    from hsconfig.starter_context import validate_starter_context_document

    context = build_starter_context(
        audited_request(tmp_path, "ShadowPriest").snapshot
    )
    value = context.document.to_value()
    del value["content_sha256"]

    if defect == "source_evidence_wrong_type":
        value["source_evidence"] = "invalid"
    elif defect == "source_row_unknown_key":
        value["source_evidence"]["rows"][0]["captured_at"] = (
            "2026-07-29T00:00:00Z"
        )
    elif defect == "source_gap_missing_key":
        del value["source_evidence"]["gaps"][0]["value"]
    elif defect == "source_provenance_drift":
        value["source_evidence"]["rows"][0]["provenance"]["mode"] = (
            "invented"
        )
    elif defect == "source_claim_count_drift":
        value["source_evidence"]["rows"][0]["claim_count"] = 2
    elif defect == "deck_identity_unknown_key":
        value["deck_identity"]["invented_authority"] = "hidden"
    elif defect == "cards_missing_key":
        del value["cards"][0]["name"]
    elif defect == "linked_entity_unknown_key":
        linked_card = next(card for card in value["cards"] if card["linked_entities"])
        linked_card["linked_entities"][0]["invented_authority"] = "hidden"
    elif defect == "identity_card_count_drift":
        value["deck_identity"]["card_count_total"] = 29
    elif defect == "deck_shape_drift":
        value["deck_shape"]["physical_card_count"] = 29
    elif defect == "runtime_contract_unknown_key":
        value["supported_runtime_contract"]["invented_surface"] = {}
    elif defect == "baseline_missing_key":
        del value["globalvalues_baseline"]["values"]["GlobalTaunt"]
    elif defect == "baseline_receipt_drift":
        value["globalvalues_baseline"]["receipt"]["snapshot_status"] = (
            "live_runtime"
        )
    elif defect == "existing_claim_unknown_key":
        value["existing_claims"][0]["invented_authority"] = "hidden"
    elif defect == "claim_card_unbound":
        value["existing_claims"][0]["cards"] = ["EX1_001"]
    elif defect == "claim_deck_match_drift":
        value["existing_claims"][0]["deck_match"][
            "target_deck_code_sha256"
        ] = "f" * 64
    elif defect == "claim_source_family_drift":
        value["existing_claims"][0]["source_family"] = "invented"
    elif defect == "safety_boundary_missing_key":
        del value["known_safety_boundaries"][0]["restrictions"]
    else:
        raise AssertionError(f"unknown_test_defect:{defect}")

    rebound = seal_starter_document(
        value,
        expected_fields=STARTER_CONTEXT_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )

    with pytest.raises(
        ValueError,
        match="^starter_context_document_invalid$",
    ):
        validate_starter_context_document(rebound)


def test_shadowpriest_starter_context_closes_identity_cards_and_runtime_contract(
    tmp_path: Path,
) -> None:
    # Break caught: resolving physical copies as duplicate rows or omitting
    # strategy-critical card, registry, baseline, or Darkbishop authority.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot

    context = build_starter_context(snapshot)
    value = context.document.to_value()
    identity = value["deck_identity"]
    cards = value["cards"]
    card_by_id = {row["card_id"]: row for row in cards}

    assert context.deck_fingerprint == (
        "831b989cf8d076bff87848b4d0d6f382c9d306fddea7619017f0c361bfc92327"
    )
    assert identity == {
        "card_count_total": 30,
        "deck_code_sha256": (
            "fd7afada1f4a7f60bb269dc56188ddf83603e4bb0147a163d3e337be388917f2"
        ),
        "deck_fingerprint": context.deck_fingerprint,
        "deck_name": "ShadowPriest",
        "format": "FT_WILD",
        "hdt_deck_id": "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602",
        "hero_dbf_id": 813,
        "hs_id": "2737726722",
        "unique_card_count": 16,
    }
    assert len(cards) == 16
    assert {row["card_id"]: row["count"] for row in cards} == (SHADOWPRIEST_CARD_COUNTS)
    assert all(row["count"] > 0 for row in cards)
    assert sum(row["count"] for row in cards) == 30
    assert all(
        {"card_id", "count", "cost", "type", "text", "mechanics", "linked_entities"}
        <= set(row)
        for row in cards
    )
    assert card_by_id["SW_448"]["cost"] == 5
    assert card_by_id["SW_448"]["type"] == "MINION"
    assert "Start of Game" in card_by_id["SW_448"]["text"]
    assert card_by_id["SW_448"]["linked_entities"] == [
        {
            "card_id": "EX1_625t",
            "dbf_id": 1622,
            "link_kind": "hero_power_transform",
            "name": "Mind Spike",
            "type": "HERO_POWER",
        }
    ]

    assert value["deck_shape"] == {
        "curve_counts": {"0": 2, "1": 13, "2": 10, "3": 2, "4": 2, "5": 1},
        "mechanic_counts": {
            "battlecry": 4,
            "damage": 18,
            "deckbuilding_modifier": 1,
            "draw": 4,
            "hero_power": 3,
            "hero_power_pressure": 1,
            "hero_power_transform": 1,
            "location": 2,
            "location_activation": 2,
            "minion": 20,
            "passive_start_effect": 1,
            "shadowform": 1,
            "spell": 8,
            "spell_school": 2,
            "start_of_game": 1,
            "start_of_game_modifier": 1,
            "summon": 7,
            "summon_trigger_board_engine": 4,
        },
        "physical_card_count": 30,
        "type_counts": {"LOCATION": 2, "MINION": 20, "SPELL": 8},
        "unique_card_count": 16,
    }

    runtime = value["supported_runtime_contract"]
    assert set(runtime["surface_registry"]) == {
        "CARDID.json",
        "CardBehavior.json",
        "Combo.json",
        "Concede.json",
        "GlobalValues.json",
        "Mulligan.json",
        "Presume.json",
    }
    assert len(runtime["globalvalue_constraints"]) == 38
    assert runtime["globalvalue_constraints"]["GlobalTaunt"] == {
        "copy_baseline_only": False,
        "maximum": "1000",
        "minimum": "-1000",
        "value_type_id": "safe_numeric_expression",
    }
    assert runtime["globalvalue_constraints"]["GameCardId"] == {
        "copy_baseline_only": True,
        "maximum": None,
        "minimum": None,
        "value_type_id": "copy_baseline",
    }
    assert runtime["card_value_constraint"] == {
        "copy_baseline_only": False,
        "maximum": "10000",
        "minimum": "-10000",
        "value_type_id": "finite_decimal",
    }
    assert runtime["combo_value_constraint"] == runtime["card_value_constraint"]
    assert "BeforeUseHeroPowerBonus" in runtime["card_behavior_blocks"]

    baseline = value["globalvalues_baseline"]
    assert context.globalvalues_baseline_sha256 == (
        "sha256:67e6f87a792c86ffbd28b10b6289ba6d88ef17c7e8204eff3b7d968be77b5177"
    )
    assert baseline["content_sha256"] == context.globalvalues_baseline_sha256
    assert baseline["key_count"] == 38
    assert len(baseline["values"]) == 38
    assert baseline["receipt"] == {
        "key_count": 38,
        "snapshot_date": "2026-07-25",
        "snapshot_status": "known_runtime_snapshot",
        "source": "bundled_fallback",
    }

    assert {
        "boundary_id": "darkbishop_transformed_hero_power_owner",
        "behavior_block": "BeforeUseHeroPowerBonus",
        "linked_card_id": "EX1_625t",
        "restrictions": [
            "do_not_infer_mulligan_keep",
            "do_not_target_source_card_for_transformed_hero_power",
        ],
        "source_card_id": "SW_448",
    } in value["known_safety_boundaries"]


def test_starter_context_digest_ignores_volatile_source_transport_but_binds_semantics(
    tmp_path: Path,
) -> None:
    # Break caught: hashing timestamps/paths or failing to bind semantic card changes.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()

    volatile = deepcopy(preconfig)
    volatile["guide_claim_bundle"]["source_evidence_index"][0]["retrieved_at"] = (
        "2099-12-31T23:59:59Z"
    )
    volatile_context = build_starter_context(
        PackageResolutionSnapshot.from_preconfig(volatile)
    )

    semantic = deepcopy(preconfig)
    semantic["card_metadata"]["cards"][0]["text"] += " Changed semantics."
    semantic_context = build_starter_context(
        PackageResolutionSnapshot.from_preconfig(semantic)
    )

    assert volatile_context.document.content_sha256 == (
        original.document.content_sha256
    )
    assert volatile_context.document.canonical_json == original.document.canonical_json
    assert semantic_context.document.content_sha256 != original.document.content_sha256

    value = original.document.to_value()
    assert value["content_sha256"] == original.document.content_sha256
    assert value["source_evidence"]["gaps"] == [
        {
            "gap_kind": "missing_deck_identity",
            "value": "starting_hero_power_id",
        }
    ]
    assert value["source_evidence"]["rows"]
    assert value["existing_claims"]
    _assert_no_volatile_or_raw_source_fields(value["source_evidence"])
    _assert_no_volatile_or_raw_source_fields(value["existing_claims"])


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda value: value["deck_identity"]["main_deck"][0].__setitem__(
                "count", 99
            ),
            "starter_context_deck_roster_mismatch",
        ),
        (
            lambda value: value["card_metadata"]["cards"][0].__setitem__(
                "count", 99
            ),
            "starter_context_deck_roster_mismatch",
        ),
        (
            lambda value: value["deck_identity"]["main_deck"].append(
                deepcopy(value["deck_identity"]["main_deck"][0])
            ),
            "starter_context_deck_roster_duplicate",
        ),
        (
            lambda value: value["deck_identity"].__setitem__(
                "card_count_total", 29
            ),
            "starter_context_deck_card_count_mismatch",
        ),
        (
            lambda value: value["deck_identity"].__setitem__(
                "deck_fingerprint", "f" * 64
            ),
            "starter_context_deck_fingerprint_mismatch",
        ),
    ],
)
def test_starter_context_cross_binds_projected_cards_to_exact_deck_identity(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    error: str,
) -> None:
    # Break caught: allowing card metadata, roster totals, or fingerprint to
    # disagree while projecting them as one authoritative deck.
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(ValueError, match=error):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        (
            "deck_code_hash",
            "sha256:not-a-hash",
            "starter_context_deck_code_sha256_invalid",
        ),
        (
            "deck_fingerprint",
            "A" * 64,
            "starter_context_deck_fingerprint_invalid",
        ),
    ],
)
def test_starter_context_validates_identity_hash_formats(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    preconfig["deck_identity"][field] = value

    with pytest.raises(ValueError, match=error):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_rejects_catalog_ids_without_exact_audited_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    identity = snapshot.general_preconfig.to_value()["deck_identity"]
    monkeypatch.setattr(
        "hsconfig.starter_context.load_audited_deck_catalog",
        lambda: [
            {
                "deck_name": "ShadowPriest",
                "deck_code": "different-deck-code",
                "hs_id": "2737726722",
                "hdt_deck_id": "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602",
            }
        ],
    )
    monkeypatch.setattr(
        "hsconfig.starter_context.load_packaged_audited_build_inputs",
        lambda: SimpleNamespace(
            builds=(
                SimpleNamespace(
                    deck_name="ShadowPriest",
                    deck_code_sha256=str(identity["deck_code_hash"]),
                    deck_fingerprint=str(identity["deck_fingerprint"]),
                ),
            )
        ),
    )

    with pytest.raises(ValueError, match="starter_context_audited_identity_mismatch"):
        build_starter_context(snapshot)


def test_starter_context_rejects_ids_when_audited_build_fingerprint_disagrees(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    identity = snapshot.general_preconfig.to_value()["deck_identity"]
    monkeypatch.setattr(
        "hsconfig.starter_context.load_packaged_audited_build_inputs",
        lambda: SimpleNamespace(
            builds=(
                SimpleNamespace(
                    deck_name="ShadowPriest",
                    deck_code_sha256=str(identity["deck_code_hash"]),
                    deck_fingerprint="f" * 64,
                ),
            )
        ),
    )

    with pytest.raises(ValueError, match="starter_context_audited_identity_mismatch"):
        build_starter_context(snapshot)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda claim: claim.__setitem__(
            "conditions", {"runtime_path": "C:\\private\\runtime.xml"}
        ),
        lambda claim: claim.__setitem__(
            "semantic_qualifiers",
            {"timing": "start_of_game", "transport": {"raw_html": "<html>"}},
        ),
        lambda claim: claim.__setitem__(
            "semantic_qualifiers", {"timing": "<html>secret</html>"}
        ),
        lambda claim: claim["acquisition_provenance"].__setitem__(
            "retrieved_at", "2099-01-01T00:00:00Z"
        ),
        lambda claim: claim["source_identity_signals"][0].__setitem__(
            "path", "D:" + "/capture/raw.json"
        ),
        lambda claim: claim["deck_match"]["exact_deck_evidence"].__setitem__(
            "runtime_path", "D:" + "/runtime/CustomConfig"
        ),
    ],
)
def test_starter_context_rejects_unclosed_claim_semantics_and_transport_leaks(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig["guide_claim_bundle"]["claims"][0])

    with pytest.raises(ValueError, match="starter_context_claim_semantics_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_digest_binds_claim_authority_fields(tmp_path: Path) -> None:
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0]["trust_ceiling"] = (
        "static_semantics"
    )
    changed_claim_id = preconfig["guide_claim_bundle"]["claims"][0]["claim_id"]
    changed = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))

    assert changed.document.content_sha256 != original.document.content_sha256
    claim = next(
        row
        for row in changed.document.to_value()["existing_claims"]
        if row["claim_id"] == changed_claim_id
    )
    assert "trust_ceiling" in claim
    assert claim["deck_match"]["exact_deck_evidence"]["matched"] is True
    _assert_no_volatile_or_raw_source_fields(claim)


def test_starter_context_projects_and_binds_closed_source_record_strength(
    tmp_path: Path,
) -> None:
    # Break caught: source-record authority from the normalized public guide
    # was either rejected or omitted from the sealed starter-context digest.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()
    claim = preconfig["guide_claim_bundle"]["claims"][0]
    claim["source_record_strength"] = "candidate_strong"

    changed = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))
    projected = next(
        row
        for row in changed.document.to_value()["existing_claims"]
        if row["claim_id"] == claim["claim_id"]
    )

    assert projected["source_record_strength"] == "candidate_strong"
    assert changed.document.content_sha256 != original.document.content_sha256

    claim["source_record_strength"] = "https://example.invalid/authority"
    with pytest.raises(ValueError, match="starter_context_claim_semantics_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_accepts_static_sw_448_hero_power_transform_mechanics(
    tmp_path: Path,
) -> None:
    # Break caught: static SW_448 hero-power-transform semantics were rejected
    # even though both mechanism tokens are canonical authority.
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = next(
        row
        for row in preconfig["guide_claim_bundle"]["claims"]
        if row["claim_kind"] == "hero_power_transform" and row["cards"] == ["SW_448"]
    )
    claim.update(
        {
            "mechanic": "hero_power_transform",
            "mechanic_family": "hero_power_transform",
        }
    )

    context = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))
    projected = next(
        row
        for row in context.document.to_value()["existing_claims"]
        if row["claim_id"] == claim["claim_id"]
    )

    assert projected["mechanic"] == "hero_power_transform"
    assert projected["mechanic_family"] == "hero_power_transform"


def test_starter_context_rejects_transform_mechanics_on_unrelated_claim_kind(
    tmp_path: Path,
) -> None:
    # Break caught: allowing transform mechanism fields on any claim kind
    # would widen the existing semantic-authority surface.
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = next(
        row
        for row in preconfig["guide_claim_bundle"]["claims"]
        if row["claim_kind"] == "card_role"
    )
    claim.update(
        {
            "mechanic": "hero_power_transform",
            "mechanic_family": "hero_power_transform",
        }
    )

    with pytest.raises(ValueError, match="starter_context_claim_semantics_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["globalvalues_baseline_receipt"].__setitem__(
            "key_count", True
        ),
        lambda value: value["globalvalues_baseline_receipt"].__setitem__(
            "source", "unknown_transport"
        ),
        lambda value: value["globalvalues_baseline_receipt"].__setitem__(
            "snapshot_status", "live_runtime"
        ),
        lambda value: value["globalvalues_baseline_receipt"].__setitem__(
            "snapshot_date", "2026-7-5"
        ),
        lambda value: value["globalvalues_baseline_receipt"].__setitem__(
            "retrieved_at", "2099-01-01T00:00:00Z"
        ),
        lambda value: _replace_baseline_value(
            value, "GlobalTaunt", {"values": [{"condition": "*", "value": True}]}
        ),
        lambda value: _replace_baseline_value(
            value, "ConfigComment", {"path": "D:" + "/runtime/GlobalValues.json"}
        ),
    ],
)
def test_starter_context_validates_closed_typed_globalvalues_receipt(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(
        ValueError,
        match="starter_context_globalvalues_baseline_invalid",
    ):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def _replace_baseline_value(
    preconfig: dict[str, Any],
    key: str,
    value: object,
) -> None:
    preconfig["globalvalues_baseline"][key] = value
    preconfig["globalvalues_baseline_receipt"]["baseline"][key] = deepcopy(value)


def test_starter_context_maximum_applies_to_final_canonical_bytes() -> None:
    _enforce_starter_context_max_bytes(b"x" * STARTER_CONTEXT_MAX_BYTES)

    with pytest.raises(ValueError, match="starter_context_maximum_bytes_exceeded"):
        _enforce_starter_context_max_bytes(
            b"x" * (STARTER_CONTEXT_MAX_BYTES + 1)
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "source_url", "file:///" + "C:" + "/private/source.html"
        ),
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "source_url", "https://127.0.0.1/private/source.html"
        ),
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "source_ref", "C:\\private\\source.json"
        ),
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "source_ref", "/private/source.json"
        ),
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "source_title", "<html>captured transport</html>"
        ),
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "acquisition_provenance",
            {
                "authority": "fabricated",
                "content_sha256": "sha256:not-a-digest",
                "mode": "transport",
            },
        ),
        lambda value: value["guide_claim_bundle"]["claims"][0].__setitem__(
            "source_refs", ["C:\\private\\claim.json"]
        ),
        lambda value: value["identity_gap_report"]["missing_identity_fields"].append(
            "/private/runtime/path"
        ),
    ],
)
def test_starter_context_rejects_unclosed_source_evidence_values(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(ValueError, match="starter_context_source_evidence_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_claim_cards_bind_to_exact_deck_and_linked_cardids(
    tmp_path: Path,
) -> None:
    # Break caught: claim cards were generic strings rather than exact deck or
    # registered linked-runtime CardID references.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot).document.to_value()
    projected_card_ids = {
        card_id
        for claim in original["existing_claims"]
        for card_id in claim["cards"]
    }
    assert projected_card_ids == set(SHADOWPRIEST_CARD_COUNTS)

    preconfig = snapshot.general_preconfig.to_value()
    transform = next(
        claim
        for claim in preconfig["guide_claim_bundle"]["claims"]
        if claim["claim_kind"] == "hero_power_transform"
        and "deck_match" in claim
    )
    transform["cards"] = ["EX1_625t"]

    linked = build_starter_context(
        PackageResolutionSnapshot.from_preconfig(preconfig)
    ).document.to_value()
    projected = next(
        claim
        for claim in linked["existing_claims"]
        if claim["claim_id"] == transform["claim_id"]
    )
    assert projected["cards"] == ["EX1_625t"]


@pytest.mark.parametrize(
    "card_reference",
    [
        "Darkbishop Benedictus",
        "C:\\private\\claim.json",
        "/private/claim.json",
        "https://example.com/SW_448",
        "<b>SW_448</b>",
        "SW_448?transport=1",
        f"{'A' * 65}_1",
        "EX1_001",
    ],
)
def test_starter_context_rejects_unclosed_or_unbound_claim_card_references(
    tmp_path: Path,
    card_reference: str,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0]["cards"] = [card_reference]

    with pytest.raises(ValueError, match="starter_context_claim_cards_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_requires_physical_cardids_for_mulligan_claims(
    tmp_path: Path,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mulligan = next(
        claim
        for claim in preconfig["guide_claim_bundle"]["claims"]
        if claim["claim_kind"] == "mulligan_keep"
    )
    mulligan["cards"] = ["EX1_625t"]

    with pytest.raises(ValueError, match="starter_context_claim_cards_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("field", "changed_value"),
    [
        ("stance", "changed_strategy_stance"),
        ("archetype", "changed_strategy_archetype"),
    ],
)
def test_starter_context_digest_binds_authoritative_claim_semantics(
    tmp_path: Path,
    field: str,
    changed_value: str,
) -> None:
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()
    source_claim = next(
        claim
        for claim in preconfig["guide_claim_bundle"]["claims"]
        if claim.get(field)
    )
    claim_id = source_claim["claim_id"]
    source_claim[field] = changed_value

    changed = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))
    projected = next(
        claim
        for claim in changed.document.to_value()["existing_claims"]
        if claim["claim_id"] == claim_id
    )

    assert changed.document.content_sha256 != original.document.content_sha256
    assert projected[field] == changed_value


def test_starter_context_digest_binds_normalized_substantive_claim_text(
    tmp_path: Path,
) -> None:
    # Break caught: omitting the source's substantive claim made strategy-text
    # changes invisible to the canonical context digest.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()
    source_claim = preconfig["guide_claim_bundle"]["claims"][0]
    claim_id = source_claim["claim_id"]
    source_claim["claim"] = "  Changed   semantic strategy claim.  "

    changed = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))
    projected = next(
        claim
        for claim in changed.document.to_value()["existing_claims"]
        if claim["claim_id"] == claim_id
    )

    assert changed.document.content_sha256 != original.document.content_sha256
    assert projected["claim"] == "Changed semantic strategy claim."


def test_starter_context_rejects_unknown_raw_claim_fields(tmp_path: Path) -> None:
    # Break caught: new upstream fields were silently omitted and therefore
    # could carry digest-invisible semantic authority.
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0]["unknown_semantic_field"] = (
        "hidden authority"
    )

    with pytest.raises(ValueError, match="starter_context_claim_schema_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_ignores_known_claim_transport_timestamp(
    tmp_path: Path,
) -> None:
    # Break caught: a known retrieval timestamp is transport provenance, not
    # strategy authority, and must remain outside canonical digest material.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0]["retrieved_at"] = (
        "2099-12-31T23:59:59Z"
    )

    changed = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))

    assert changed.document.canonical_json == original.document.canonical_json


@pytest.mark.parametrize(
    "claim_text",
    [
        None,
        42,
        "",
        "   ",
        "x" * 4097,
        "C:\\private\\claim.txt",
        "/private/claim.txt",
        "<html>raw semantic claim</html>",
        "2026-08-19T12:00:00Z",
    ],
)
def test_starter_context_rejects_malformed_or_transport_claim_text(
    tmp_path: Path,
    claim_text: object,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0]["claim"] = claim_text

    with pytest.raises(ValueError, match="starter_context_claim_text_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("claim", "semantic <b", "starter_context_claim_text_invalid"),
        ("claim", "semantic >", "starter_context_claim_text_invalid"),
        (
            "evidence_text_short",
            "evidence <b",
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_text_short",
            "2099-12-31T23:59:59Z",
            "starter_context_claim_semantics_invalid",
        ),
        ("claim", "<b>unpaired presentation", "starter_context_claim_text_invalid"),
        (
            "evidence_text_short",
            "unpaired presentation</i>",
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_text_short",
            "2099-12-31",
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_text_short",
            "PT15M",
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_text_short",
            "x" * 4097,
            "starter_context_claim_semantics_invalid",
        ),
    ],
)
def test_starter_context_rejects_open_markup_or_transport_claim_prose(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0][field] = value

    with pytest.raises(ValueError, match=error):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("family", "mutate", "error"),
    [
        (
            "claim_prose_posix_path_token",
            lambda value: _claim_with_field(value, "claim").__setitem__(
                "claim", "Use /private/runtime/GlobalValues.json"
            ),
            "starter_context_claim_text_invalid",
        ),
        (
            "claim_prose_windows_path_token",
            lambda value: _claim_with_field(value, "claim").__setitem__(
                "claim", "Use " + "C:" + "/private/runtime/GlobalValues.json"
            ),
            "starter_context_claim_text_invalid",
        ),
        (
            "claim_prose_windows_backslash_path_token",
            lambda value: _claim_with_field(value, "claim").__setitem__(
                "claim", "Use C:\\private\\runtime\\GlobalValues.json"
            ),
            "starter_context_claim_text_invalid",
        ),
        (
            "claim_prose_unc_path_token",
            lambda value: _claim_with_field(value, "claim").__setitem__(
                "claim", "Use \\\\private-server\\capture\\guide.html"
            ),
            "starter_context_claim_text_invalid",
        ),
        (
            "evidence_prose_posix_path_token",
            lambda value: _claim_with_field(
                value, "evidence_text_short"
            ).__setitem__(
                "evidence_text_short", "Evidence from /private/capture.html"
            ),
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_prose_uri_token",
            lambda value: _claim_with_field(
                value, "evidence_text_short"
            ).__setitem__(
                "evidence_text_short", "Source https://example.com/raw-guide"
            ),
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_prose_non_https_uri_scheme",
            lambda value: _claim_with_field(
                value, "evidence_text_short"
            ).__setitem__(
                "evidence_text_short", "Source urn:hearthstone:raw-guide"
            ),
            "starter_context_claim_semantics_invalid",
        ),
        (
            "claim_authority_transport_scalar",
            lambda value: _claim_with_field(value, "support_status").__setitem__(
                "support_status", "2099-12-31T23:59:59Z"
            ),
            "starter_context_claim_semantics_invalid",
        ),
        (
            "claim_source_alias_open_markup",
            lambda value: _claim_with_field(value, "source_family").update(
                {"source": "source <b", "source_family": "source <b"}
            ),
            "starter_context_claim_semantics_invalid",
        ),
        (
            "source_evidence_title_open_markup",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("source_title", "Captured <b"),
            "starter_context_source_evidence_invalid",
        ),
    ],
)
def test_starter_context_rejects_reviewed_unsafe_emitted_scalars(
    tmp_path: Path,
    family: str,
    mutate: Callable[[dict[str, Any]], None],
    error: str,
) -> None:
    # Break caught: context scalar validation was start-anchored and split
    # across projections, so unsafe tokens survived in otherwise valid prose
    # and semantic fields.  ``family`` makes each emitted family explicit.
    del family
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(ValueError, match=error):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    "field",
    [
        "claim_confidence",
        "deck_match_scope",
        "freshness_status",
        "source_confidence",
        "source_family",
        "source_lane",
        "source_type",
        "source_visibility",
        "specificity_status",
        "scope",
        "support_status",
        "trust_ceiling",
    ],
)
def test_starter_context_rejects_transport_values_in_every_claim_authority_token(
    tmp_path: Path,
    field: str,
) -> None:
    # Break caught: all projected claim-authority scalars shared the permissive
    # semantic-text path, so an ISO transport value could masquerade as any of
    # these structured authority tokens.
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = _claim_with_field(preconfig, field)
    claim[field] = "2099-12-31T23:59:59Z"
    if field == "source_family":
        claim["source"] = claim[field]

    with pytest.raises(ValueError, match="starter_context_claim_semantics_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("family", "mutate"),
    [
        (
            "claim_id_reference",
            lambda value: _set_claim_id(
                _claim_with_field(value, "claim_id"), "2099-12-31"
            ),
        ),
        (
            "archetype_token",
            lambda value: _claim_with_field(value, "archetype").__setitem__(
                "archetype", "2099-12-31"
            ),
        ),
        (
            "stance_token",
            lambda value: _claim_with_field(value, "stance").__setitem__(
                "stance", "2099-12-31"
            ),
        ),
        (
            "mechanic_token",
            lambda value: _claim_with_field(value, "mechanic").__setitem__(
                "mechanic", "2099-12-31"
            ),
        ),
        (
            "mechanic_family_token",
            lambda value: _claim_with_field(value, "mechanic_family").__setitem__(
                "mechanic_family", "2099-12-31"
            ),
        ),
        (
            "runtime_value_scalar",
            lambda value: _claim_with_field(value, "runtime_value").__setitem__(
                "runtime_value", "2099-12-31"
            ),
        ),
        (
            "identity_signal_field_token",
            lambda value: _first_identity_signal(value).__setitem__(
                "field", "2099-12-31"
            ),
        ),
        (
            "identity_signal_origin_token",
            lambda value: _first_identity_signal(value).__setitem__(
                "origin", "2099-12-31"
            ),
        ),
        (
            "identity_signal_value_token",
            lambda value: _first_identity_signal(value).__setitem__(
                "value", "2099-12-31"
            ),
        ),
        (
            "semantic_qualifier_scalar",
            lambda value: _claim_with_field(
                value, "semantic_qualifiers"
            )["semantic_qualifiers"].__setitem__("timing", "2099-12-31"),
        ),
        (
            "semantic_qualifier_list",
            lambda value: _claim_with_field(
                value, "semantic_qualifiers"
            )["semantic_qualifiers"].__setitem__(
                "state_requirements", ["2099-12-31"]
            ),
        ),
    ],
)
def test_starter_context_rejects_transport_values_in_projected_semantic_families(
    tmp_path: Path,
    family: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    del family
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(ValueError, match="starter_context_claim_semantics_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("family", "mutate", "error"),
    [
        (
            "source_evidence_family_token",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("source_family", "2099-12-31"),
            "starter_context_source_evidence_invalid",
        ),
        (
            "source_evidence_id_reference",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("source_id", "2099-12-31"),
            "starter_context_source_evidence_invalid",
        ),
        (
            "source_evidence_reference",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("source_ref", "2099-12-31"),
            "starter_context_source_evidence_invalid",
        ),
        (
            "source_evidence_missing_key_reference_list",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("missing_source_keys", ["2099-12-31"]),
            "starter_context_source_evidence_invalid",
        ),
        (
            "source_evidence_title_prose",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("source_title", "2099-12-31"),
            "starter_context_source_evidence_invalid",
        ),
        (
            "deck_match_candidate_reference_list",
            lambda value: _claim_with_field(value, "deck_match")["deck_match"][
                "exact_deck_evidence"
            ].__setitem__("candidate_deck_code_hashes", ["2099-12-31"]),
            "starter_context_claim_deck_match_invalid",
        ),
        (
            "evidence_gap_reference",
            lambda value: value["identity_gap_report"][
                "missing_identity_fields"
            ].append("2099-12-31"),
            "starter_context_source_evidence_invalid",
        ),
    ],
)
def test_starter_context_rejects_transport_values_in_source_reference_families(
    tmp_path: Path,
    family: str,
    mutate: Callable[[dict[str, Any]], None],
    error: str,
) -> None:
    del family
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(ValueError, match=error):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "PT15M",
        "15ms",
        "23:59:59Z",
        "https://example.com/raw-guide",
        "token\x00value",
        "token\rvalue",
        "token\x1fvalue",
        "x" * 4097,
    ],
)
def test_starter_context_rejects_unsafe_or_oversized_structured_scalars(
    tmp_path: Path,
    unsafe_value: str,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    _claim_with_field(preconfig, "support_status")["support_status"] = unsafe_value

    with pytest.raises(ValueError, match="starter_context_claim_semantics_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_shadowpriest_context_safe_scalar_layer_preserves_canonical_projection(
    tmp_path: Path,
) -> None:
    # Break caught: safety validation must not rewrite already canonical game
    # semantics while closing unsafe alternate inputs.
    context = build_starter_context(
        audited_request(tmp_path, "ShadowPriest").snapshot
    )
    value = context.document.to_value()

    assert context.document.content_sha256 == (
        "sha256:1b87f3279050212e80b483cdd66bfc31adaaee5f164dc5b65d8ac021c10887dc"
    )
    assert len(context.document.canonical_json) == 72971
    assert len(value["existing_claims"]) == 42
    assert len(value["source_evidence"]["rows"]) == 17
    assert value["source_evidence"]["gaps"] == [
        {
            "gap_kind": "missing_deck_identity",
            "value": "starting_hero_power_id",
        }
    ]


def test_starter_context_keeps_public_https_in_dedicated_source_references(
    tmp_path: Path,
) -> None:
    # Break caught: generic path-token checks must not narrow the existing
    # public-HTTPS authority for dedicated source_url/source-reference fields.
    public_url = "https://example.com/guide?next=/cards"
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    evidence = preconfig["guide_claim_bundle"]["source_evidence_index"][0]
    original_source_ref = evidence["source_ref"]
    matching_claims = [
        row
        for row in preconfig["guide_claim_bundle"]["claims"]
        if original_source_ref in row.get("source_refs", [])
    ]
    assert len(matching_claims) == evidence["claim_count"]
    evidence["source_url"] = public_url
    evidence["source_ref"] = public_url
    for claim in matching_claims:
        claim["source_refs"] = [
            public_url if value == original_source_ref else value
            for value in claim["source_refs"]
        ]

    value = build_starter_context(
        PackageResolutionSnapshot.from_preconfig(preconfig)
    ).document.to_value()

    assert any(
        row.get("source_url") == public_url and row["source_ref"] == public_url
        for row in value["source_evidence"]["rows"]
    )
    matching_claim_ids = {row["claim_id"] for row in matching_claims}
    projected_claims = [
        row
        for row in value["existing_claims"]
        if row["claim_id"] in matching_claim_ids
    ]
    assert len(projected_claims) == len(matching_claims)
    assert all(public_url in row["source_refs"] for row in projected_claims)
    assert all(
        original_source_ref not in row["source_refs"] for row in projected_claims
    )


def test_starter_context_normalizes_legitimate_claim_prose_and_paired_tags(
    tmp_path: Path,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = preconfig["guide_claim_bundle"]["claims"][0]
    claim["claim"] = (
        "  Give a 1/1 minion +1/+1; use <b>Battlecry</b> with <i>tempo</i>.  "
    )
    claim["evidence_text_short"] = (
        "  Legitimate prose with <b><i>nested emphasis</i></b>.  "
    )

    context = build_starter_context(
        PackageResolutionSnapshot.from_preconfig(preconfig)
    ).document.to_value()
    projected = next(
        row for row in context["existing_claims"] if row["claim_id"] == claim["claim_id"]
    )

    assert projected["claim"] == (
        "Give a 1/1 minion +1/+1; use Battlecry with tempo."
    )
    assert projected["evidence_text_short"] == (
        "Legitimate prose with nested emphasis."
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda claim: claim.__setitem__("claim_type", "targeting"),
        lambda claim: claim.__setitem__("condition", "opponent_class=PRIEST"),
    ],
)
def test_starter_context_rejects_inconsistent_legacy_claim_aliases(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = preconfig["guide_claim_bundle"]["claims"][0]
    mutate(claim)

    with pytest.raises(ValueError, match="starter_context_claim_alias_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda evidence: evidence.__setitem__(
            "matched_deck_fingerprint", "f" * 64
        ),
        lambda evidence: evidence.__setitem__("candidate_count", 2),
        lambda evidence: evidence.__setitem__("decoded_candidate_count", 0),
        lambda evidence: evidence.__setitem__("candidate_count", True),
        lambda evidence: evidence.update(
            {"matched": False, "matched_deck_fingerprint": "f" * 64}
        ),
    ],
)
def test_starter_context_cross_binds_exact_deck_match_authority(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = next(
        row
        for row in preconfig["guide_claim_bundle"]["claims"]
        if row.get("deck_match")
    )
    mutate(claim["deck_match"]["exact_deck_evidence"])

    with pytest.raises(ValueError, match="starter_context_claim_deck_match_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_closes_consistent_unmatched_deck_evidence(
    tmp_path: Path,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = next(
        row
        for row in preconfig["guide_claim_bundle"]["claims"]
        if row.get("deck_match")
    )
    claim["deck_match"]["exact_deck_evidence"] = {
        "candidate_count": 0,
        "candidate_deck_code_hashes": [],
        "decoded_candidate_count": 0,
        "matched": False,
        "matched_deck_fingerprint": None,
    }

    context = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))
    projected = next(
        row
        for row in context.document.to_value()["existing_claims"]
        if row["claim_id"] == claim["claim_id"]
    )

    assert projected["deck_match"]["exact_deck_evidence"]["matched"] is False
    assert projected["deck_match"]["target_deck_code_sha256"] == (
        preconfig["deck_identity"]["deck_code_hash"]
    )


def _assert_no_volatile_or_raw_source_fields(value: object) -> None:
    forbidden_fields = {
        "captured_at",
        "fetch_duration",
        "fetch_duration_ms",
        "html",
        "path",
        "raw_html",
        "retrieved_at",
    }
    if isinstance(value, dict):
        assert not (set(value) & forbidden_fields)
        for item in value.values():
            _assert_no_volatile_or_raw_source_fields(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_volatile_or_raw_source_fields(item)
    elif isinstance(value, str):
        assert "<html" not in value.lower()


def _claim_with_field(
    preconfig: dict[str, Any],
    field: str,
) -> dict[str, Any]:
    return next(
        claim
        for claim in preconfig["guide_claim_bundle"]["claims"]
        if field in claim
    )


def _set_claim_id(claim: dict[str, Any], claim_id: str) -> None:
    claim["claim_id"] = claim_id
    claim["source_claim_ids"] = [claim_id]


def _first_identity_signal(preconfig: dict[str, Any]) -> dict[str, Any]:
    return _claim_with_field(preconfig, "source_identity_signals")[
        "source_identity_signals"
    ][0]


@pytest.fixture(scope="module")
def adversarial_starter_context_seed(
    tmp_path_factory: pytest.TempPathFactory,
) -> StarterContext:
    return build_starter_context(
        audited_request(
            tmp_path_factory.mktemp("starter-context-adversarial"),
            "ShadowPriest",
        ).snapshot
    )


def _canonical_fixture_sort(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _mutate_context_boundary(value: dict[str, Any], defect: str) -> None:
    cards = value["cards"]
    claims = value["existing_claims"]
    source = value["source_evidence"]
    linked_card = next(card for card in cards if card["linked_entities"])

    if defect == "empty_cards":
        cards.clear()
    elif defect == "duplicate_card_dbf_id":
        cards[1]["dbf_id"] = cards[0]["dbf_id"]
    elif defect == "cards_unsorted":
        cards.reverse()
    elif defect == "duplicate_linked_entity":
        linked_card["linked_entities"].append(
            deepcopy(linked_card["linked_entities"][0])
        )
    elif defect == "linked_entities_unsorted":
        linked_card["linked_entities"].append(
            {
                "card_id": "AAA_001",
                "dbf_id": 1,
                "link_kind": "related_entity",
                "name": "Synthetic linked boundary",
                "type": "HERO_POWER",
            }
        )
    elif defect == "duplicate_mechanic_token":
        cards[0]["mechanics"] = ["BATTLECRY", "BATTLECRY"]
    elif defect == "card_name_wrong_type":
        cards[0]["name"] = 7
    elif defect == "empty_card_text_allowed":
        cards[0]["text"] = ""
    elif defect == "card_name_empty":
        cards[0]["name"] = ""
    elif defect == "card_name_too_long":
        cards[0]["name"] = "x" * 4097
    elif defect == "baseline_extra_field":
        value["globalvalues_baseline"]["transport"] = "forbidden"
    elif defect == "baseline_digest_mismatch":
        value["globalvalues_baseline"]["content_sha256"] = "f" * 64
    elif defect == "baseline_key_count_mismatch":
        value["globalvalues_baseline"]["key_count"] = 37
    elif defect == "baseline_receipt_extra_field":
        value["globalvalues_baseline"]["receipt"]["path"] = "runtime.json"
    elif defect == "baseline_receipt_count_mismatch":
        value["globalvalues_baseline"]["receipt"]["key_count"] = 37
    elif defect == "runtime_default_receipt_allowed":
        value["globalvalues_baseline"]["receipt"].update(
            {
                "snapshot_date": None,
                "snapshot_status": "live_runtime",
                "source": "runtime_default",
            }
        )
    elif defect == "baseline_source_unknown":
        value["globalvalues_baseline"]["receipt"]["source"] = "invented"
    elif defect == "source_evidence_extra_field":
        source["transport"] = "forbidden"
    elif defect == "source_row_without_url_allowed":
        source["rows"][0].pop("source_url")
        source["rows"].sort(key=_canonical_fixture_sort)
    elif defect == "source_row_empty_url":
        source["rows"][0]["source_url"] = ""
    elif defect == "source_gaps_unsorted":
        source["gaps"].append(
            {"gap_kind": "missing_deck_identity", "value": "format"}
        )
    elif defect == "duplicate_source_id":
        source["rows"][1]["source_id"] = source["rows"][0]["source_id"]
        source["rows"].sort(key=_canonical_fixture_sort)
    elif defect == "negative_supported_claim_count":
        source["rows"][0]["unsupported_claim_count"] = (
            source["rows"][0]["claim_count"] + 1
        )
        source["rows"].sort(key=_canonical_fixture_sort)
    elif defect == "duplicate_claim_id":
        claims[1]["claim_id"] = claims[0]["claim_id"]
    elif defect == "runtime_lowerable_not_bool":
        claims[0]["runtime_lowerable"] = 1
    elif defect == "duplicate_claim_source_ref":
        claims[0]["source_refs"].append(claims[0]["source_refs"][0])
    elif defect == "promotion_eligible_not_bool":
        claim = next(row for row in claims if "promotion_eligible" in row)
        claim["promotion_eligible"] = 1
    elif defect == "claims_unsorted":
        claims.reverse()
    elif defect == "conditions_fields_unknown":
        claims[0]["conditions"]["turn"] = "early"
    elif defect == "conditions_runtime_unsafe":
        claims[0]["conditions"]["runtime_condition"] = "coin OR"
    elif defect == "conditions_report_only_empty":
        claims[0]["conditions"]["report_only"] = {}
    elif defect == "conditions_report_only_allowed":
        claims[0]["conditions"]["report_only"] = {"phase": "early"}
        claims.sort(key=_canonical_fixture_sort)
    elif defect == "deck_match_fields_unknown":
        claim = next(row for row in claims if "deck_match" in row)
        claim["deck_match"]["transport"] = "forbidden"
    elif defect == "unbound_option_card":
        claim = next(row for row in claims if row["claim_kind"] == "gameplan_posture")
        claim["claim_kind"] = "discover_choice"
        claim.pop("archetype")
        claim["intent"] = "select"
        claim["option_card_id"] = "EX1_999"
    elif defect == "invalid_runtime_block":
        claim = next(row for row in claims if row["claim_kind"] == "card_role")
        claim["runtime_block"] = "InventedBlock"
    elif defect == "invalid_globalvalue_operation":
        claim = next(row for row in claims if row["claim_kind"] == "gameplan_posture")
        claim["claim_kind"] = "globalvalue_numeric_tuning"
        claim.pop("archetype")
        claim.update(
            {"key": "FirstTurnValueWeight", "operation": "multiply", "value": "1"}
        )
    elif defect == "invalid_globalvalue_key":
        claim = next(row for row in claims if row["claim_kind"] == "gameplan_posture")
        claim["claim_kind"] = "globalvalue_numeric_tuning"
        claim.pop("archetype")
        claim.update({"key": "InventedValue", "operation": "set", "value": "1"})
    elif defect == "globalvalue_value_without_key":
        claim = next(row for row in claims if row["claim_kind"] == "gameplan_posture")
        claim["claim_kind"] = "globalvalue_numeric_tuning"
        claim.pop("archetype")
        claim.update({"operation": "set", "value": "1"})
    elif defect == "empty_combo_sequence":
        claim = next(row for row in claims if row["claim_kind"] == "gameplan_posture")
        claim["claim_kind"] = "combo_sequence"
        claim.pop("archetype")
        claim.update({"intent": "play_in_order", "sequence": []})
    else:
        raise AssertionError(f"unknown_context_boundary:{defect}")


@pytest.mark.parametrize(
    ("defect", "accepted"),
    [
        ("wrong_document_type", False),
        ("unsealed_extra_field", False),
        ("empty_cards", False),
        ("duplicate_card_dbf_id", False),
        ("cards_unsorted", False),
        ("duplicate_linked_entity", False),
        ("linked_entities_unsorted", False),
        ("duplicate_mechanic_token", False),
        ("card_name_wrong_type", False),
        ("empty_card_text_allowed", True),
        ("card_name_empty", False),
        ("card_name_too_long", False),
        ("baseline_extra_field", False),
        ("baseline_digest_mismatch", False),
        ("baseline_key_count_mismatch", False),
        ("baseline_receipt_extra_field", False),
        ("baseline_receipt_count_mismatch", False),
        ("runtime_default_receipt_allowed", True),
        ("baseline_source_unknown", False),
        ("source_evidence_extra_field", False),
        ("source_row_without_url_allowed", True),
        ("source_row_empty_url", False),
        ("source_gaps_unsorted", False),
        ("duplicate_source_id", False),
        ("negative_supported_claim_count", False),
        ("duplicate_claim_id", False),
        ("runtime_lowerable_not_bool", False),
        ("duplicate_claim_source_ref", False),
        ("promotion_eligible_not_bool", False),
        ("claims_unsorted", False),
        ("conditions_fields_unknown", False),
        ("conditions_runtime_unsafe", False),
        ("conditions_report_only_empty", False),
        ("conditions_report_only_allowed", True),
        ("deck_match_fields_unknown", False),
        ("unbound_option_card", False),
        ("invalid_runtime_block", False),
        ("invalid_globalvalue_operation", False),
        ("invalid_globalvalue_key", False),
        ("globalvalue_value_without_key", False),
        ("empty_combo_sequence", False),
    ],
)
def test_starter_context_validator_enforces_nested_authority_boundaries(
    adversarial_starter_context_seed: StarterContext,
    defect: str,
    accepted: bool,
) -> None:
    # Breaks caught: accepting malformed identity, evidence, claim, baseline, or
    # cross-authority relationships after an attacker recomputes the self digest.
    seed = adversarial_starter_context_seed
    if defect == "wrong_document_type":
        document: object = object()
    elif defect == "unsealed_extra_field":
        value = seed.document.to_value()
        value["invented_authority"] = "hidden"
        document = StarterDocument(
            document=FrozenJsonDocument.from_value(value),
            content_sha256=seed.document.content_sha256,
        )
    else:
        value = seed.document.to_value()
        del value["content_sha256"]
        _mutate_context_boundary(value, defect)
        document = seal_starter_document(
            value,
            expected_fields=STARTER_CONTEXT_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )

    if accepted:
        validated = validate_starter_context_document(document)  # type: ignore[arg-type]
        assert validated.document.canonical_json == document.canonical_json
    else:
        with pytest.raises(ValueError, match="^starter_context_document_invalid$"):
            validate_starter_context_document(document)  # type: ignore[arg-type]
