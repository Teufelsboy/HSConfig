from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

import hsconfig.package_request as package_request
import hsconfig.input_snapshot_manifest as input_snapshot_manifest
from hsconfig.optimized_start_authority import ValidatedSingleStarterApproval
from hsconfig.operator_profile import derive_deck_output_binding, enable_operator_profile
from hsconfig.package_compiler import compile_package
from hsconfig.package_request import PackageResolutionSnapshot
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_context import build_single_candidate_starter_context
from hsconfig.starter_review import validate_starter_review
from tests.test_input_snapshot_manifest import (
    _CapturedInputs,
    _freeze,
    _write_frozen_inputs,
)
from tests.helpers.audited_package_request import audited_request_with_frozen_input_projections
from tests.test_starter_candidate import sealed_single_candidate
from tests.test_starter_review import _ReviewAuthority, review_document


@pytest.fixture
def captured_inputs(tmp_path, monkeypatch):
    request, projections = audited_request_with_frozen_input_projections(
        tmp_path / "audited", "ShadowPriest"
    )
    for name in ("local-app-data", "runtime", "outputs"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    profile = enable_operator_profile(
        runtime_root=tmp_path / "runtime",
        output_base_root=tmp_path / "outputs",
        expected_predecessor_sha256=None,
    )
    return _CapturedInputs(
        request=request,
        snapshot=request.snapshot,
        **projections,
        profile=profile,
        output_binding=derive_deck_output_binding(profile, "ShadowPriest"),
    )


def _freeze_with_code(captured: _CapturedInputs, code: object):
    preconfig = captured.snapshot.general_preconfig.to_value()
    preconfig["cards_payload"]["deck_code"] = code
    return _freeze(
        captured,
        snapshot=PackageResolutionSnapshot.from_preconfig(preconfig),
        deck={
            "cards_payload": preconfig["cards_payload"],
            "deck_identity": preconfig["deck_identity"],
        },
    )


def _approval(frozen):
    context = build_single_candidate_starter_context(frozen)
    candidate = validate_starter_candidate(
        sealed_single_candidate(context), context=context
    )
    review = validate_starter_review(
        review_document(_ReviewAuthority(context, candidate)),
        context=context,
        candidate=candidate,
    )
    return ValidatedSingleStarterApproval(
        snapshot=frozen.manifest,
        context=context,
        candidate=candidate,
        review=review,
    )


def _request(frozen, approval):
    request_type = getattr(
        package_request, "FrozenApprovedLiveConfigureRequest", None
    )
    assert request_type is not None, "frozen approved compile request is missing"
    return request_type.from_values(
        frozen_compiler_inputs=frozen, starter_approval=approval
    )


def test_real_compile_accepts_only_frozen_approved_inputs(captured_inputs):
    raw_code = captured_inputs.request.invocation.deck_code
    frozen = _freeze_with_code(captured_inputs, raw_code)
    request = _request(frozen, _approval(frozen))

    compiled = compile_package(request)

    reports = {
        row.relative_path: row.document.to_value()
        for row in compiled.json_projections
    }
    manifest = reports["reports/input_manifest.json"]
    assert compiled.deck_name == "ShadowPriest"
    assert compiled.deck_code_sha256 == sha256(raw_code.encode("utf-8")).hexdigest()
    assert manifest["deck_code"] == raw_code
    assert manifest["runtime_root"] == str(captured_inputs.profile.runtime_root)
    assert manifest["configuration_mode"] == "LLM_OPTIMIZED_START"
    assert manifest["target_config_mode"] == "preview"
    assert manifest["optimized_start_authority_schema"] == "single_candidate_review_v1"
    assert manifest["cards_json"] is None
    assert manifest["claims_json"] is None
    assert manifest["guide_sources_json"] is None
    assert manifest["plan_reports_dir"] is None
    assert {row.file_name for row in compiled.runtime_surfaces} >= {
        "GlobalValues.json", "Mulligan.json"
    }
    assert set(frozen.deck.to_value()) == {"cards_payload", "deck_identity"}
    assert len(frozen.manifest.blobs) == 6
    assert not hasattr(request, "snapshot")
    assert not hasattr(request, "plan_overrides")
    assert not hasattr(request, "acquisition_closure_input")
    assert not hasattr(request, "mulligan_gap_input")


def test_old_frozen_inputs_remain_readable_but_cannot_compile_live(captured_inputs):
    frozen = _freeze(captured_inputs)
    approval = _approval(frozen)
    with pytest.raises(ValueError, match="deck_code"):
        _request(frozen, approval)


@pytest.mark.parametrize("code", ["not-the-bound-code", "", None, 7])
def test_frozen_inputs_reject_present_invalid_raw_deck_code(captured_inputs, code):
    with pytest.raises(ValueError, match="deck_code"):
        _freeze_with_code(captured_inputs, code)


def test_request_rejects_unvalidated_approval(captured_inputs):
    frozen = _freeze_with_code(
        captured_inputs, captured_inputs.request.invocation.deck_code
    )
    with pytest.raises(ValueError, match="starter_approval"):
        _request(frozen, object())


def test_request_rejects_mutated_review_authority(captured_inputs):
    frozen = _freeze_with_code(
        captured_inputs, captured_inputs.request.invocation.deck_code
    )
    approval = _approval(frozen)
    changed = replace(approval, review=replace(approval.review, confidence="limited"))
    with pytest.raises(ValueError, match="starter_approval"):
        _request(frozen, changed)


def test_compile_rechecks_approval_after_request_construction(captured_inputs):
    frozen = _freeze_with_code(
        captured_inputs, captured_inputs.request.invocation.deck_code
    )
    approval = _approval(frozen)
    request = _request(frozen, approval)
    object.__setattr__(approval.review, "confidence", "limited")
    with pytest.raises(ValueError, match="starter_approval"):
        compile_package(request)


def test_internal_frozen_reader_preserves_blobs_after_output_creation(
    captured_inputs, tmp_path
):
    frozen = _freeze_with_code(
        captured_inputs, captured_inputs.request.invocation.deck_code
    )
    run_root = tmp_path / "run"
    _write_frozen_inputs(run_root, frozen)
    captured_inputs.output_binding.output_root.mkdir()
    with pytest.raises(ValueError, match="deck_output_precondition_changed"):
        input_snapshot_manifest.load_frozen_compiler_inputs(run_root)

    reader = getattr(input_snapshot_manifest, "_load_frozen_compiler_inputs", None)
    assert reader is not None, "internal frozen reader is missing"
    assert reader(run_root, rebind_operator=False) == frozen
    deck_path = run_root / "inputs" / "deck.json"
    deck = frozen.deck.to_value()
    deck["cards_payload"]["deck_code"] = "changed"
    deck_path.write_bytes(package_request.FrozenJsonDocument.from_value(deck).canonical_json)
    with pytest.raises(ValueError, match="blob_binding_mismatch:deck"):
        reader(run_root, rebind_operator=False)
