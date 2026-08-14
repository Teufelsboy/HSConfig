import json
from pathlib import Path

import pytest

from hsconfig.configure_run_model import (
    ConfigureRunModel,
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
    write_rendered_configure_run,
)
from hsconfig.package_assembler import (
    PackageModel,
    assemble_package,
)
from hsconfig.package_compiler import compile_package
from tests.helpers.audited_package_request import audited_request


@pytest.fixture
def package_model(tmp_path: Path) -> PackageModel:
    return assemble_package(
        compile_package(audited_request(tmp_path, "ShadowPriest"))
    )


def test_configure_run_is_immutable_complete_and_deterministic(
    package_model: PackageModel,
) -> None:
    run = create_configure_run_model(
        package=package_model,
        stage_artifacts={
            "01_manifest/input.json": b"{}",
            "02_source_documents/source.json": b"{}",
            "03_research/research.json": b"{}",
        },
    )

    rendered = render_configure_run_model(run)

    assert rendered == render_configure_run_model(run)
    assert tuple(item.relative_path for item in rendered.artifacts) == tuple(
        sorted(item.relative_path for item in rendered.artifacts)
    )
    assert any(
        item.relative_path.startswith("04_package/CustomConfig/")
        and item.relative_path.endswith("/GlobalValues.json")
        for item in rendered.artifacts
    )
    assert "configure_summary.json" in {
        item.relative_path for item in rendered.artifacts
    }


@pytest.mark.parametrize(
    ("source_stage", "autopilot_stage", "expected_unavailable"),
    [
        (
            "02_source_documents",
            None,
            {
                "02_source_acquisition": "02_source_documents_selected",
                "02_source_autopilot": "not_requested",
                "03_source_autopilot": "not_requested",
            },
        ),
        (
            "02_source_documents",
            "02_source_autopilot",
            {
                "02_source_acquisition": "02_source_documents_selected",
                "03_source_autopilot": "02_source_autopilot_selected",
            },
        ),
        (
            "02_source_acquisition",
            None,
            {
                "02_source_autopilot": "not_requested",
                "02_source_documents": "02_source_acquisition_selected",
                "03_source_autopilot": "not_requested",
            },
        ),
        (
            "02_source_acquisition",
            "03_source_autopilot",
            {
                "02_source_autopilot": "03_source_autopilot_selected",
                "02_source_documents": "02_source_acquisition_selected",
            },
        ),
    ],
)
def test_configure_run_accepts_the_full_legal_source_autopilot_matrix(
    source_stage: str,
    autopilot_stage: str | None,
    expected_unavailable: dict[str, str],
    package_model: PackageModel,
) -> None:
    stage_artifacts = {
        "01_manifest/input.json": b"{}",
        f"{source_stage}/source.json": b"{}",
        "03_research/research.json": b"{}",
    }
    if autopilot_stage is not None:
        stage_artifacts[f"{autopilot_stage}/autopilot.json"] = b"{}"

    rendered = render_configure_run_model(
        create_configure_run_model(
            package=package_model,
            stage_artifacts=stage_artifacts,
        )
    )
    summary = json.loads(
        next(
            artifact.content
            for artifact in rendered.artifacts
            if artifact.relative_path == "configure_summary.json"
        )
    )

    assert summary["unavailable_stages"] == expected_unavailable


@pytest.mark.parametrize(
    ("source_stage", "autopilot_stages"),
    [
        ("02_source_documents", ("03_source_autopilot",)),
        ("02_source_acquisition", ("02_source_autopilot",)),
        (
            "02_source_documents",
            ("02_source_autopilot", "03_source_autopilot"),
        ),
    ],
)
def test_configure_run_rejects_illegal_source_autopilot_combinations(
    source_stage: str,
    autopilot_stages: tuple[str, ...],
    package_model: PackageModel,
) -> None:
    stage_artifacts = {
        "01_manifest/input.json": b"{}",
        f"{source_stage}/source.json": b"{}",
        "03_research/research.json": b"{}",
        **{
            f"{stage}/autopilot.json": b"{}"
            for stage in autopilot_stages
        },
    }

    with pytest.raises(ValueError, match="configure_run_autopilot_stage_invalid"):
        create_configure_run_model(
            package=package_model,
            stage_artifacts=stage_artifacts,
        )


@pytest.mark.parametrize(
    "source_paths",
    [
        (),
        (
            "02_source_documents/source.json",
            "02_source_acquisition/source.json",
        ),
    ],
)
def test_configure_run_requires_exactly_one_source_alternative(
    source_paths: tuple[str, ...],
    package_model: PackageModel,
) -> None:
    with pytest.raises(ValueError, match="configure_run_source_stage_invalid"):
        create_configure_run_model(
            package=package_model,
            stage_artifacts={
                "01_manifest/input.json": b"{}",
                "03_research/research.json": b"{}",
                **{path: b"{}" for path in source_paths},
            },
        )


@pytest.mark.parametrize(
    "reserved_path",
    [
        "configure_summary.json/child.json",
        "04_package",
        "04_package/reports/caller.json",
        "04_package/CustomConfig/caller.json",
    ],
)
def test_configure_run_rejects_reserved_paths(
    reserved_path: str,
    package_model: PackageModel,
) -> None:
    with pytest.raises(ValueError, match="configure_run_reserved_path"):
        create_configure_run_model(
            package=package_model,
            stage_artifacts={
                "01_manifest/input.json": b"{}",
                "02_source_documents/source.json": b"{}",
                "03_research/research.json": b"{}",
                reserved_path: b"{}",
            },
        )


def test_configure_run_rejects_file_ancestor_collisions_before_destination_creation(
    tmp_path: Path,
    package_model: PackageModel,
) -> None:
    destination = tmp_path / "configure"

    with pytest.raises(
        ValueError,
        match="configure_run_artifact_path_collision",
    ):
        create_configure_run_model(
            package=package_model,
            stage_artifacts={
                "01_manifest/input.json": b"{}",
                "02_source_documents/source.json": b"{}",
                "03_research/research.json": b"{}",
                "a": b"file",
                "a/b.json": b"descendant",
            },
        )

    assert not destination.exists()


def test_configure_tuple_fields_copy_caller_lists(
    package_model: PackageModel,
) -> None:
    canonical = create_configure_run_model(
        package=package_model,
        stage_artifacts={
            "01_manifest/input.json": b"{}",
            "02_source_documents/source.json": b"{}",
            "03_research/research.json": b"{}",
        },
    )
    caller_stage_artifacts = list(canonical.stage_artifacts)
    run = ConfigureRunModel(
        canonical.deck_name,
        canonical.deck_fingerprint,
        canonical.package,
        caller_stage_artifacts,
    )
    canonical_rendered = render_configure_run_model(run)
    caller_rendered_artifacts = list(canonical_rendered.artifacts)
    rendered = RenderedConfigureRun(
        run,
        caller_rendered_artifacts,
        canonical_rendered.content_root_sha256,
    )

    caller_stage_artifacts.clear()
    caller_rendered_artifacts.clear()

    assert len(run.stage_artifacts) == 4
    assert rendered.artifacts == canonical_rendered.artifacts


def test_configure_model_rejects_a_forged_revision_before_writing(
    tmp_path: Path,
    package_model: PackageModel,
) -> None:
    rendered = render_configure_run_model(
        create_configure_run_model(
            package=package_model,
            stage_artifacts={
                "01_manifest/input.json": b"{}",
                "02_source_documents/source.json": b"{}",
                "03_research/research.json": b"{}",
            },
        )
    )
    destination = tmp_path / "configure"

    with pytest.raises(
        ValueError,
        match="rendered_configure_run_content_root_mismatch",
    ):
        RenderedConfigureRun(
            rendered.model,
            rendered.artifacts,
            "0" * 64,
        )

    assert not destination.exists()


def test_configure_writer_writes_the_pure_render(
    tmp_path: Path,
    package_model: PackageModel,
) -> None:
    rendered = render_configure_run_model(
        create_configure_run_model(
            package=package_model,
            stage_artifacts={
                "01_manifest/input.json": b"{}",
                "02_source_documents/stage_status.json": b"{}",
                "03_research/research.json": b"{}",
            },
        )
    )
    destination = tmp_path / "configure"

    write_rendered_configure_run(rendered, destination)

    assert {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    } == {artifact.relative_path for artifact in rendered.artifacts}
