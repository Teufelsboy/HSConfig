from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from hsconfig.operator_summary import build_operator_summary_from_inputs
from hsconfig.operator_summary_inputs import load_operator_summary_inputs
from hsconfig.package_assembler import ArtifactPhase, assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.package_derivation_receipt import (
    verify_package_derivation_receipt_from_view,
)
from hsconfig.package_render_authority import (
    ArtifactSet,
    RenderFaultPoint,
    _pre_authority_files,
    render_package_authority,
)
from hsconfig.starter_context import build_starter_context
from hsconfig.starter_decision import load_validated_starter_selection
from hsconfig.visionai_registry import OPTIMIZED_START_REPORT_PATHS
from hsconfig.strict_package_validation import (
    validate_complete_package,
    validate_complete_package_from_view,
)
from tests.helpers.package_byte_contract import (
    AUDITED_DECK_NAMES,
    content_root_sha256,
    load_fixture,
)
from tests.helpers.audited_package_request import audited_request
from tests.test_starter_decision import (
    three_candidates,
    write_selection_bundle,
)


FIXTURE_PATH = Path("tests/fixtures/package-byte-contract-v1.json")
RESERVED_PATHS = frozenset(
    {
        "reports/runtime_surface_ledger.json",
        "reports/validation_report.json",
        "reports/output_ownership_manifest.json",
        "package_derivation_receipt.json",
        "reports/operator_summary.json",
        "reports/card_semantic_audit.md",
        "reports/strong_promotion_report.json",
        "reports/source_evidence_closure.json",
    }
)


def _model(tmp_path: Path, deck_name: str = "ShadowPriest"):
    return assemble_package(
        compile_package(
            audited_request(
                tmp_path,
                deck_name,
                fixture_paths=True,
            )
        )
    )


def _optimized_model(tmp_path: Path):
    conservative = audited_request(
        tmp_path / "request",
        "ShadowPriest",
        fixture_paths=True,
    )
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
        invocation=replace(
            conservative.invocation,
            configuration_mode="LLM_OPTIMIZED_START",
        ),
        starter_selection=selection,
    )
    return assemble_package(compile_package(optimized))


def _metadata(artifacts: ArtifactSet) -> list[dict[str, object]]:
    return [
        {
            "relative_path": artifact.relative_path,
            "size": artifact.size,
            "sha256": artifact.sha256,
        }
        for artifact in artifacts.artifacts
    ]


def test_optimized_reports_preserve_all_five_frozen_canonical_bytes(
    tmp_path: Path,
) -> None:
    model = _optimized_model(tmp_path)
    files = _pre_authority_files(model)
    projections = {
        row.relative_path: row.document
        for row in model.compiled.json_projections
    }

    assert set(OPTIMIZED_START_REPORT_PATHS) == {
        path for path in files if path.startswith("reports/optimized_start/")
    }
    for path in OPTIMIZED_START_REPORT_PATHS:
        assert files[path] == projections[path].canonical_json


def test_conservative_json_projection_rendering_remains_pretty(
    tmp_path: Path,
) -> None:
    model = _model(tmp_path)
    files = _pre_authority_files(model)
    projection = next(
        row
        for row in model.compiled.json_projections
        if row.relative_path == "reports/input_manifest.json"
    )
    expected = (
        json.dumps(
            projection.document.to_value(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )

    assert files[projection.relative_path] == expected


def test_optimized_strict_validation_rejects_globalvalues_runtime_tamper(
    tmp_path: Path,
) -> None:
    rendered = render_package_authority(_optimized_model(tmp_path))
    files = {
        row.relative_path: row.content
        for row in rendered.artifacts.artifacts
    }
    globalvalues_path = next(
        path
        for path in files
        if path.endswith("/GlobalValues.json")
    )
    tampered = json.loads(files[globalvalues_path])
    tampered["FirstTurnValueWeight"]["values"][0]["value"] = "9.99"
    files[globalvalues_path] = json.dumps(
        tampered,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"

    report = validate_complete_package_from_view(
        ArtifactSet.from_files(files)
    )

    assert report["status"] == "failed"
    assert any(
        "does not match optimized decision ledger" in error
        for error in report["errors"]
    )


def test_render_authority_completes_the_exact_shadowpriest_plan_in_memory(
    tmp_path: Path,
) -> None:
    model = _model(tmp_path)
    rendered = render_package_authority(model)

    expected_names = tuple(
        row.relative_path for row in model.artifact_plan.artifacts
    )
    assert rendered.model is model
    assert isinstance(rendered.artifacts, ArtifactSet)
    assert rendered.artifacts.file_names() == expected_names
    assert RESERVED_PATHS.issubset(expected_names)
    assert rendered.content_root_sha256 == content_root_sha256(
        _metadata(rendered.artifacts)
    )
    assert rendered.artifacts.read_json(
        "reports/validation_report.json"
    )["status"] == "passed"

    receipt = rendered.artifacts.read_json(
        "package_derivation_receipt.json"
    )
    verified, reasons = verify_package_derivation_receipt_from_view(
        rendered.artifacts,
        receipt,
    )
    assert verified is True
    assert reasons == []

    replay_inputs = load_operator_summary_inputs(rendered.artifacts)
    assert replay_inputs.authority.package_summary_parity is True
    assert build_operator_summary_from_inputs(
        replay_inputs
    ) == rendered.artifacts.read_json("reports/operator_summary.json")


def test_render_authority_never_uses_filesystem_mutators(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model(tmp_path)

    def unexpected_write(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("render_authority_filesystem_write")

    monkeypatch.setattr(Path, "mkdir", unexpected_write)
    monkeypatch.setattr(Path, "write_bytes", unexpected_write)
    monkeypatch.setattr(Path, "write_text", unexpected_write)

    rendered = render_package_authority(model)

    assert rendered.artifacts.file_names()


@pytest.mark.parametrize("fault_point", tuple(RenderFaultPoint))
def test_every_render_fault_is_explicit_and_leaves_no_output(
    tmp_path: Path,
    fault_point: RenderFaultPoint,
) -> None:
    model = _model(tmp_path, "CuteWarrior")
    output = tmp_path / "must-not-exist"

    def fail_at(
        point: RenderFaultPoint,
        _snapshot: ArtifactSet,
    ) -> None:
        if point is fault_point:
            raise RuntimeError(f"fault:{point.value}")

    with pytest.raises(RuntimeError, match=f"fault:{fault_point.value}"):
        render_package_authority(model, fault_hook=fail_at)

    assert not output.exists()


def test_render_hooks_are_ordered_unique_cumulative_phase_snapshots(
    tmp_path: Path,
) -> None:
    model = _model(tmp_path)
    trace: list[RenderFaultPoint] = []
    snapshots: dict[RenderFaultPoint, ArtifactSet] = {}

    def observe(
        point: RenderFaultPoint,
        snapshot: ArtifactSet,
    ) -> None:
        trace.append(point)
        snapshots[point] = snapshot

    rendered = render_package_authority(model, fault_hook=observe)

    expected_order = tuple(RenderFaultPoint)
    assert tuple(trace) == expected_order
    assert len(trace) == len(set(trace))
    phase_by_point = {
        RenderFaultPoint.FINAL_PLAN: None,
        RenderFaultPoint.CORE_RUNTIME: ArtifactPhase.CORE_RUNTIME,
        RenderFaultPoint.PRE_AUTHORITY: ArtifactPhase.PRE_AUTHORITY,
        RenderFaultPoint.RUNTIME_LEDGER: (
            ArtifactPhase.PHYSICAL_RUNTIME_LEDGER
        ),
        RenderFaultPoint.VALIDATION: ArtifactPhase.VALIDATION,
        RenderFaultPoint.OWNERSHIP: ArtifactPhase.OWNERSHIP,
        RenderFaultPoint.RECEIPT: ArtifactPhase.RECEIPT,
        RenderFaultPoint.AUTHORITY: ArtifactPhase.AUTHORITY,
        RenderFaultPoint.SUMMARY_DEPENDENT: (
            ArtifactPhase.SUMMARY_DEPENDENT
        ),
        RenderFaultPoint.FINAL_VERIFICATION: None,
    }
    cumulative_phases: set[ArtifactPhase] = set()
    for point in expected_order:
        phase = phase_by_point[point]
        if phase is not None:
            cumulative_phases.add(phase)
        expected_paths = tuple(
            sorted(
                row.relative_path
                for row in model.artifact_plan.artifacts
                if row.phase in cumulative_phases
            )
        )
        assert snapshots[point].file_names() == expected_paths
    assert snapshots[RenderFaultPoint.FINAL_VERIFICATION] == (
        rendered.artifacts
    )


def test_artifact_set_is_sorted_unique_immutable_and_detached() -> None:
    first = ArtifactSet.from_files(
        {
            "reports/b.json": b'{"b":2}\n',
            "reports/a.json": b'{"a":1}\n',
        }
    )

    assert first.file_names() == (
        "reports/a.json",
        "reports/b.json",
    )
    assert first.read_json("reports/a.json") == {"a": 1}
    with pytest.raises((AttributeError, TypeError)):
        first.artifacts = ()  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(first, "artifacts", ())
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(
            first.artifacts[0],
            "content",
            b"forged",
        )
    with pytest.raises(ValueError, match="package_artifact_path_duplicate"):
        ArtifactSet((first.artifacts[0], first.artifacts[0]))


def test_rendered_authority_boundary_rejects_coordinated_object_setattr(
    tmp_path: Path,
) -> None:
    rendered = render_package_authority(_model(tmp_path))

    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(rendered, "artifacts", ArtifactSet.empty())
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(rendered, "content_root_sha256", "0" * 64)


def test_view_strict_validation_rejects_the_same_unsupported_direct_file_as_path(
    tmp_path: Path,
) -> None:
    rendered = render_package_authority(_model(tmp_path / "inputs"))
    files = {
        artifact.relative_path: artifact.content
        for artifact in rendered.artifacts.artifacts
    }
    files[
        "CustomConfig/shadowpriest/UNSUPPORTED.txt"
    ] = b"not-a-runtime-surface\n"
    tampered = ArtifactSet.from_files(files)

    view_report = validate_complete_package_from_view(tampered)
    physical_root = tmp_path / "physical"
    for relative_path, content in files.items():
        target = physical_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    path_report = validate_complete_package(physical_root)

    assert view_report["status"] == path_report["status"] == "failed"
    assert any(
        "UNSUPPORTED.txt: unsupported VisionAI surface" in error
        for error in view_report["errors"]
    )
    assert any(
        "UNSUPPORTED.txt: unsupported VisionAI surface" in error
        for error in path_report["errors"]
    )


def test_all_audited_decks_match_the_frozen_complete_byte_contract(
    tmp_path: Path,
) -> None:
    fixture = load_fixture(FIXTURE_PATH)
    total_artifacts = 0
    reserved_artifacts = 0

    for deck_name in AUDITED_DECK_NAMES:
        rendered = render_package_authority(
            _model(tmp_path / deck_name, deck_name)
        )
        actual = _metadata(rendered.artifacts)
        expected = fixture["decks"][deck_name]
        assert actual == expected["artifacts"], deck_name
        assert rendered.content_root_sha256 == expected[
            "content_root_sha256"
        ], deck_name
        total_artifacts += len(actual)
        reserved_artifacts += sum(
            row["relative_path"] in RESERVED_PATHS for row in actual
        )

    assert total_artifacts == 878
    assert reserved_artifacts == 96
