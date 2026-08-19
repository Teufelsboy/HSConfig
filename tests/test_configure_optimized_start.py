from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import hsconfig.package_request as package_request
from hsconfig.configuration_mode import (
    CONSERVATIVE,
    LLM_OPTIMIZED_START,
    configuration_mode_from_manifest,
)
from hsconfig.package_compiler import compile_package
from hsconfig.package_request import (
    PackageInvocation,
    PackageResolutionSnapshot,
    ResolvedPackageRequest,
    resolve_package_request,
)
from hsconfig.starter_context import build_starter_context
from hsconfig.starter_decision import load_validated_starter_selection
from hsconfig.starter_contract import (
    STARTER_CANDIDATE_1_FILENAME,
    STARTER_CANDIDATE_FIELDS,
    STARTER_DECISION_FIELDS,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_document import StarterDocument, seal_starter_document
from hsconfig.package_request import FrozenJsonDocument
from tests.helpers.audited_package_request import audited_request
from tests.test_starter_decision import (
    three_candidates,
    write_selection_bundle,
)


def test_manifest_configuration_mode_is_strict_and_legacy_compatible() -> None:
    assert configuration_mode_from_manifest({}) == CONSERVATIVE
    assert configuration_mode_from_manifest(
        {"configuration_mode": CONSERVATIVE}
    ) == CONSERVATIVE
    assert configuration_mode_from_manifest(
        {"configuration_mode": LLM_OPTIMIZED_START}
    ) == LLM_OPTIMIZED_START
    for value in (None, 0, False, "unknown"):
        with pytest.raises(ValueError, match="configuration_mode_invalid"):
            configuration_mode_from_manifest({"configuration_mode": value})


def test_optimized_request_requires_one_frozen_validated_selection(
    tmp_path: Path,
) -> None:
    conservative = audited_request(tmp_path / "conservative", "ShadowPriest")
    assert conservative.invocation.configuration_mode == CONSERVATIVE
    assert conservative.starter_selection is None

    optimized_invocation = replace(
        conservative.invocation,
        configuration_mode=LLM_OPTIMIZED_START,
    )
    with pytest.raises(ValueError, match="starter_selection_required"):
        replace(conservative, invocation=optimized_invocation)

    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
    )
    selection = load_validated_starter_selection(
        decision_path,
        current_context=context,
    )
    optimized = replace(
        conservative,
        invocation=optimized_invocation,
        starter_selection=selection,
    )
    selected_bytes = optimized.starter_selection.selected.document.canonical_json
    (decision_path.parent / STARTER_CANDIDATE_1_FILENAME).write_bytes(b"{}")
    assert optimized.starter_selection.selected.document.canonical_json == selected_bytes
    manifest = next(
        projection.document.to_value()
        for projection in compile_package(optimized).json_projections
        if projection.relative_path == "reports/input_manifest.json"
    )
    assert manifest["configuration_mode"] == LLM_OPTIMIZED_START

    changed_preconfig = deepcopy(
        conservative.snapshot.general_preconfig.to_value()
    )
    changed_preconfig["card_metadata"]["cards"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="starter_context_mismatch"):
        replace(
            optimized,
            snapshot=PackageResolutionSnapshot.from_preconfig(
                changed_preconfig
            ),
        )

    with pytest.raises(ValueError, match="configuration_mode_invalid"):
        replace(
            conservative,
            invocation=replace(
                conservative.invocation,
                configuration_mode="UNRECOGNIZED",
            ),
        )


def test_optimized_request_reseals_every_public_selection_claim(
    tmp_path: Path,
) -> None:
    conservative = audited_request(tmp_path / "conservative", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
    )
    selection = load_validated_starter_selection(
        decision_path,
        current_context=context,
    )
    invocation = replace(
        conservative.invocation,
        configuration_mode=LLM_OPTIMIZED_START,
    )
    reviewed_mismatch = selection.decision.to_value()
    del reviewed_mismatch["content_sha256"]
    reviewed_mismatch["reviewed_candidates"][0]["content_sha256"] = (
        "sha256:" + "0" * 64
    )
    forged_decision = seal_starter_document(
        reviewed_mismatch,
        expected_fields=STARTER_DECISION_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    forged_document_candidate = replace(
        selection.candidates[0],
        document=selection.candidates[1].document,
    )
    forged_runtime_candidate = replace(
        selection.candidates[0],
        runtime_intent_sha256="sha256:" + "0" * 64,
    )
    forged_selections = (
        replace(selection, selected=selection.candidates[1]),
        replace(selection, decision=forged_decision),
        replace(
            selection,
            candidates=(
                forged_document_candidate,
                *selection.candidates[1:],
            ),
            selected=forged_document_candidate,
        ),
        replace(
            selection,
            candidates=(
                forged_runtime_candidate,
                *selection.candidates[1:],
            ),
            selected=forged_runtime_candidate,
        ),
    )

    for forged in forged_selections:
        with pytest.raises(ValueError, match="^starter_selection_invalid$"):
            replace(
                conservative,
                invocation=invocation,
                starter_selection=forged,
            )


def test_optimized_request_reseals_decision_document_authority(
    tmp_path: Path,
) -> None:
    conservative = audited_request(tmp_path / "conservative", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
    )
    selection = load_validated_starter_selection(
        decision_path,
        current_context=context,
    )
    invocation = replace(
        conservative.invocation,
        configuration_mode=LLM_OPTIMIZED_START,
    )
    zero_digest = "sha256:" + "0" * 64
    embedded_digest_mismatch = selection.decision.to_value()
    embedded_digest_mismatch["content_sha256"] = zero_digest
    forged_canonical_decision = StarterDocument(
        document=FrozenJsonDocument.from_value(embedded_digest_mismatch),
        content_sha256=zero_digest,
    )
    forged_decisions = (
        object(),
        replace(selection.decision, content_sha256=zero_digest),
        forged_canonical_decision,
    )

    for decision in forged_decisions:
        with pytest.raises(ValueError, match="^starter_selection_invalid$"):
            replace(
                conservative,
                invocation=invocation,
                starter_selection=replace(selection, decision=decision),
            )


def test_resolver_normalizes_decision_context_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conservative = audited_request(tmp_path / "conservative", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
        mutate_decision=lambda draft: draft.__setitem__(
            "starter_context_sha256",
            "sha256:" + "0" * 64,
        ),
    )
    preconfig = conservative.snapshot.general_preconfig.to_value()
    baseline_receipt = preconfig["globalvalues_baseline_receipt"]
    closure = conservative.acquisition_closure_input.to_value()
    monkeypatch.setattr(
        package_request,
        "build_preconfig_context",
        lambda *_args, **_kwargs: preconfig,
    )
    monkeypatch.setattr(
        package_request,
        "load_globalvalues_baseline",
        lambda _runtime_root: baseline_receipt,
    )
    monkeypatch.setattr(
        package_request,
        "_matching_strict_context",
        lambda **_kwargs: conservative.snapshot.strict_build_context,
    )
    monkeypatch.setattr(
        package_request,
        "build_source_acquisition_closure_report",
        lambda **_kwargs: {"acquisition_closure": closure},
    )

    with pytest.raises(ValueError, match="^starter_context_mismatch$"):
        resolve_package_request(
            SimpleNamespace(
                deck_name="ShadowPriest",
                deck_code=conservative.invocation.deck_code,
                runtime_root=conservative.invocation.runtime_root,
                optimized_start=True,
                starter_decision_json=decision_path,
            ),
            current_date=date(2026, 8, 19),
            fetch_latest_cards_fn=lambda: [],
            research_required_guide_sources_fn=lambda **_kwargs: {},
        )


def test_resolver_normalizes_candidate_context_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conservative = audited_request(tmp_path / "conservative", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    candidates = three_candidates(context)
    candidate_value = candidates[0].to_value()
    del candidate_value["content_sha256"]
    candidate_value["starter_context_sha256"] = "sha256:" + "0" * 64
    candidates[0] = seal_starter_document(
        candidate_value,
        expected_fields=STARTER_CANDIDATE_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        candidates,
    )
    preconfig = conservative.snapshot.general_preconfig.to_value()
    baseline_receipt = preconfig["globalvalues_baseline_receipt"]
    closure = conservative.acquisition_closure_input.to_value()
    monkeypatch.setattr(
        package_request,
        "build_preconfig_context",
        lambda *_args, **_kwargs: preconfig,
    )
    monkeypatch.setattr(
        package_request,
        "load_globalvalues_baseline",
        lambda _runtime_root: baseline_receipt,
    )
    monkeypatch.setattr(
        package_request,
        "_matching_strict_context",
        lambda **_kwargs: conservative.snapshot.strict_build_context,
    )
    monkeypatch.setattr(
        package_request,
        "build_source_acquisition_closure_report",
        lambda **_kwargs: {"acquisition_closure": closure},
    )

    with pytest.raises(ValueError, match="^starter_context_mismatch$"):
        resolve_package_request(
            SimpleNamespace(
                deck_name="ShadowPriest",
                deck_code=conservative.invocation.deck_code,
                runtime_root=conservative.invocation.runtime_root,
                optimized_start=True,
                starter_decision_json=decision_path,
            ),
            current_date=date(2026, 8, 19),
            fetch_latest_cards_fn=lambda: [],
            research_required_guide_sources_fn=lambda **_kwargs: {},
        )


def test_configure_cli_rejects_unpaired_optimized_start_values(
    tmp_path: Path,
) -> None:
    invocation = PackageInvocation(
        deck_code="fixture-code",
        runtime_root=str(tmp_path / "runtime"),
        cards_json=None,
        claims_json=None,
        guide_sources_json=None,
        plan_reports_dir=None,
        target_config_mode="preview",
        include_disposition_diagnostics=False,
    )
    assert invocation.configuration_mode == CONSERVATIVE
    assert ResolvedPackageRequest is not None
    for optimized_start, decision_path, error in (
        (True, None, "starter_decision_required"),
        (False, tmp_path / "starter_config_decision.json", "starter_decision_not_enabled"),
    ):
        with pytest.raises(ValueError, match=error):
            resolve_package_request(
                SimpleNamespace(
                    optimized_start=optimized_start,
                    starter_decision_json=decision_path,
                ),
                current_date=date(2026, 8, 19),
                fetch_latest_cards_fn=lambda: [],
                research_required_guide_sources_fn=lambda **_kwargs: {},
            )
