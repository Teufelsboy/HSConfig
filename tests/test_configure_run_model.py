import json
from pathlib import Path
import subprocess
import sys

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
from hsconfig.package_model import content_root_sha256
from hsconfig.package_render_authority import AuthorityArtifact
from hsconfig.run_manifest import (
    build_tree_manifest_from_artifacts,
    write_tree_manifest,
)
from tests.helpers.audited_package_request import audited_request


@pytest.fixture
def package_model(tmp_path: Path) -> PackageModel:
    return assemble_package(
        compile_package(audited_request(tmp_path, "ShadowPriest"))
    )


@pytest.mark.parametrize(
    "modules",
    (
        (
            "hsconfig.package_builder",
            "hsconfig.strict_package_validation",
        ),
        (
            "hsconfig.strict_package_validation",
            "hsconfig.package_builder",
        ),
    ),
)
def test_package_builder_and_strict_validation_import_in_either_order(
    modules: tuple[str, str],
) -> None:
    script = "; ".join(f"import {module}" for module in modules)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


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
    assert tuple(
        item.relative_path
        for item in rendered.artifacts
        if item.relative_path == "package_manifest.json"
    ) == ("package_manifest.json",)
    manifest = json.loads(
        next(
            item.content
            for item in rendered.artifacts
            if item.relative_path == "package_manifest.json"
        )
    )
    assert tuple(
        entry["relative_path"] for entry in manifest["entries"]
    ) == tuple(
        item.relative_path
        for item in rendered.artifacts
        if item.relative_path != "package_manifest.json"
    )
    assert manifest["content_root_sha256"] == rendered.content_root_sha256


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
        "configure_summary.json",
        "package_manifest.json",
        "package_manifest.json/child.json",
        "PACKAGE_MANIFEST.JSON",
        "PACKAGE_MANIFEST.JSON/child.json",
        "04_package",
        "04_package/reports/caller.json",
        "04_package/CustomConfig/caller.json",
        "04_PACKAGE",
        "04_PACKAGE/evil.json",
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


@pytest.mark.parametrize(
    "ambiguous_paths",
    (
        ("A.json", "a.JSON"),
        ("A", "a/child.json"),
        ("Dir/a.json", "dir/b.json"),
        ("a/x.json", "A/y/z.json"),
        ("01_manifest/CON.json",),
        ("01_manifest/trailing.",),
        ("01_manifest/trailing ",),
        ("01_manifest/control\nname.json",),
        ("01_manifest/e\u0301.json",),
        ("01_manifest/" + "x" * 4097,),
        ("01_manifest/illegal?.json",),
        ("01_manifest/illegal*.json",),
        ('01_manifest/illegal".json',),
        ("01_manifest/illegal<.json",),
        ("01_manifest/illegal>.json",),
        ("01_manifest/illegal|.json",),
    ),
    ids=(
        "casefold_collision",
        "casefold_ancestor",
        "directory_sibling_casefold",
        "directory_nested_casefold",
        "windows_device",
        "windows_trailing_dot",
        "windows_trailing_space",
        "control_character",
        "unicode_not_nfc",
        "oversized_path",
        "question_mark",
        "asterisk",
        "double_quote",
        "less_than",
        "greater_than",
        "pipe",
    ),
)
def test_configure_run_rejects_ambiguous_artifact_paths(
    ambiguous_paths: tuple[str, ...],
    package_model: PackageModel,
) -> None:
    with pytest.raises(
        ValueError,
        match="configure_run_artifact_path_ambiguous",
    ):
        create_configure_run_model(
            package=package_model,
            stage_artifacts={
                "01_manifest/input.json": b"{}",
                "02_source_documents/source.json": b"{}",
                "03_research/research.json": b"{}",
                **{path: b"unsafe" for path in ambiguous_paths},
            },
        )


def test_configure_run_allows_nested_manifest_filename(
    package_model: PackageModel,
) -> None:
    rendered = render_configure_run_model(
        create_configure_run_model(
            package=package_model,
            stage_artifacts={
                "01_manifest/input.json": b"{}",
                "01_manifest/package_manifest.json": b"nested",
                "02_source_documents/source.json": b"{}",
                "03_research/research.json": b"{}",
            },
        )
    )

    assert "01_manifest/package_manifest.json" in {
        artifact.relative_path for artifact in rendered.artifacts
    }


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


def test_configure_model_rejects_forged_generated_summary(
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
    forged_artifacts = tuple(
        (
            type(artifact).from_content(
                relative_path=artifact.relative_path,
                content=b'{"deck_name":"OtherDeck"}\n',
            )
            if artifact.relative_path == "configure_summary.json"
            else artifact
        )
        for artifact in canonical.stage_artifacts
    )

    with pytest.raises(
        ValueError,
        match="configure_run_summary_mismatch",
    ):
        ConfigureRunModel(
            canonical.deck_name,
            canonical.deck_fingerprint,
            canonical.package,
            forged_artifacts,
        )


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


def test_configure_model_rejects_forged_root_manifest_bytes(
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
    forged = tuple(
        (
            type(artifact).from_content(
                relative_path=artifact.relative_path,
                content=b"{}\n",
            )
            if artifact.relative_path == "package_manifest.json"
            else artifact
        )
        for artifact in rendered.artifacts
    )

    with pytest.raises(
        ValueError,
        match="rendered_configure_run_manifest_mismatch",
    ):
        RenderedConfigureRun(
            rendered.model,
            forged,
            rendered.content_root_sha256,
        )


def test_rendered_configure_run_requires_root_manifest(
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
    content_artifacts = tuple(
        artifact
        for artifact in rendered.artifacts
        if artifact.relative_path != "package_manifest.json"
    )

    with pytest.raises(
        ValueError,
        match="rendered_configure_run_manifest_mismatch",
    ):
        RenderedConfigureRun(
            rendered.model,
            content_artifacts,
            content_root_sha256(content_artifacts),
        )


def test_rendered_configure_run_rejects_remanifested_model_stage_drift(
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
    content_artifacts = tuple(
        (
            AuthorityArtifact.from_content(
                relative_path=artifact.relative_path,
                content=b'{"forged":true}\n',
            )
            if artifact.relative_path == "01_manifest/input.json"
            else artifact
        )
        for artifact in rendered.artifacts
        if artifact.relative_path != "package_manifest.json"
    )
    manifest = AuthorityArtifact.from_content(
        relative_path="package_manifest.json",
        content=write_tree_manifest(
            build_tree_manifest_from_artifacts(
                deck_name=rendered.model.deck_name,
                deck_fingerprint=rendered.model.deck_fingerprint,
                artifacts=content_artifacts,
            )
        ),
    )
    artifacts = tuple(
        sorted(
            (*content_artifacts, manifest),
            key=lambda artifact: artifact.relative_path,
        )
    )

    with pytest.raises(
        ValueError,
        match="rendered_configure_run_model_artifacts_mismatch",
    ):
        RenderedConfigureRun(
            rendered.model,
            artifacts,
            content_root_sha256(content_artifacts),
        )


def test_rendered_configure_run_rejects_remanifested_package_drift(
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
    target = next(
        artifact.relative_path
        for artifact in rendered.artifacts
        if artifact.relative_path.startswith("04_package/")
        and artifact.relative_path.endswith("card_semantic_audit.md")
    )
    content_artifacts = tuple(
        (
            AuthorityArtifact.from_content(
                relative_path=artifact.relative_path,
                content=b"forged\n",
            )
            if artifact.relative_path == target
            else artifact
        )
        for artifact in rendered.artifacts
        if artifact.relative_path != "package_manifest.json"
    )
    manifest = AuthorityArtifact.from_content(
        relative_path="package_manifest.json",
        content=write_tree_manifest(
            build_tree_manifest_from_artifacts(
                deck_name=rendered.model.deck_name,
                deck_fingerprint=rendered.model.deck_fingerprint,
                artifacts=content_artifacts,
            )
        ),
    )
    artifacts = tuple(
        sorted(
            (*content_artifacts, manifest),
            key=lambda artifact: artifact.relative_path,
        )
    )

    with pytest.raises(
        ValueError,
        match="rendered_configure_run_model_artifacts_mismatch",
    ):
        RenderedConfigureRun(
            rendered.model,
            artifacts,
            content_root_sha256(content_artifacts),
        )


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


def test_configure_writer_publishes_root_manifest_last(
    tmp_path: Path,
    package_model: PackageModel,
    monkeypatch: pytest.MonkeyPatch,
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
    writes: list[Path] = []
    real_write_bytes = Path.write_bytes

    def record_write(path: Path, content: bytes) -> int:
        writes.append(path)
        return real_write_bytes(path, content)

    monkeypatch.setattr(Path, "write_bytes", record_write)

    write_rendered_configure_run(rendered, destination)

    assert writes[-1] == destination / "package_manifest.json"
