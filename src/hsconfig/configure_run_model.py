"""Immutable configure-run revision model and deterministic stage renderer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from hsconfig.io import slugify_deck_name
from hsconfig.package_model import PackageArtifact, PackageModel, content_root_sha256
from hsconfig.package_renderer import render_package_model


@dataclass(frozen=True, slots=True)
class ConfigureRunModel:
    deck_name: str
    deck_fingerprint: str
    package: PackageModel
    stage_artifacts: tuple[PackageArtifact, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_artifacts", tuple(self.stage_artifacts))
        if (
            self.deck_name != self.package.deck_name
            or self.deck_fingerprint != self.package.deck_fingerprint
        ):
            raise ValueError("configure_run_package_identity_mismatch")
        paths = tuple(artifact.relative_path for artifact in self.stage_artifacts)
        if tuple(sorted(paths)) != paths or len(set(paths)) != len(paths):
            raise ValueError("configure_run_stage_artifacts_not_unique_sorted")
        _validate_required_stages(paths)


@dataclass(frozen=True, slots=True)
class RenderedConfigureRun:
    model: ConfigureRunModel
    artifacts: tuple[PackageArtifact, ...]
    content_root_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", tuple(self.artifacts))


def create_configure_run_model(
    *, package: PackageModel, stage_artifacts: Mapping[str, bytes]
) -> ConfigureRunModel:
    artifacts = tuple(
        sorted(
            (
                PackageArtifact.from_content(relative_path=path, content=content)
                for path, content in stage_artifacts.items()
            ),
            key=lambda artifact: artifact.relative_path,
        )
    )
    return ConfigureRunModel(
        deck_name=package.deck_name,
        deck_fingerprint=package.deck_fingerprint,
        package=package,
        stage_artifacts=artifacts,
    )


def render_configure_run_model(model: ConfigureRunModel) -> RenderedConfigureRun:
    package = render_package_model(model.package)
    slug = slugify_deck_name(model.deck_name)
    package_artifacts = tuple(
        PackageArtifact.from_content(
            relative_path=(
                f"04_package/{artifact.relative_path}"
                if artifact.relative_path.startswith("reports/")
                else f"04_package/CustomConfig/{slug}/{artifact.relative_path}"
            ),
            content=artifact.content,
        )
        for artifact in package.artifacts
    )
    all_content = (*model.stage_artifacts, *package_artifacts)
    root = content_root_sha256(tuple(all_content))
    summary = PackageArtifact.from_content(
        relative_path="configure_summary.json",
        content=_json_bytes(
            {
                "schema_version": 1,
                "deck_name": model.deck_name,
                "deck_fingerprint": model.deck_fingerprint,
                "content_root_sha256": root,
                "unavailable_stages": _unavailable_stages(model.stage_artifacts),
            }
        ),
    )
    artifacts = tuple(sorted((*all_content, summary), key=lambda artifact: artifact.relative_path))
    return RenderedConfigureRun(model=model, artifacts=artifacts, content_root_sha256=root)


def write_rendered_configure_run(rendered: RenderedConfigureRun, destination: Path) -> None:
    if render_configure_run_model(rendered.model) != rendered:
        raise ValueError("rendered_configure_run_invalid")
    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise ValueError("destination_must_be_empty")
    destination.mkdir(parents=True, exist_ok=True)
    for artifact in rendered.artifacts:
        target = destination / artifact.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.content)
        if target.read_bytes() != artifact.content:
            raise ValueError("written_artifact_verification_failed")
    content = tuple(
        artifact for artifact in rendered.artifacts if artifact.relative_path != "configure_summary.json"
    )
    if content_root_sha256(content) != rendered.content_root_sha256:
        raise ValueError("written_content_root_verification_failed")


def _validate_required_stages(paths: tuple[str, ...]) -> None:
    if any(
        path == "configure_summary.json"
        or path == "04_package"
        or path.startswith("04_package/")
        for path in paths
    ):
        raise ValueError("configure_run_reserved_path")
    required = ("01_manifest/", "03_research/")
    if any(not any(path.startswith(prefix) for path in paths) for prefix in required):
        raise ValueError("configure_run_required_stage_missing")
    source_paths = [path for path in paths if path.startswith("02_source_documents/")]
    acquisition_paths = [path for path in paths if path.startswith("02_source_acquisition/")]
    if bool(source_paths) == bool(acquisition_paths):
        raise ValueError("configure_run_source_stage_invalid")
    autopilot_02 = [path for path in paths if path.startswith("02_source_autopilot/")]
    autopilot_03 = [path for path in paths if path.startswith("03_source_autopilot/")]
    if (
        (autopilot_02 and autopilot_03)
        or (source_paths and autopilot_03)
        or (acquisition_paths and autopilot_02)
    ):
        raise ValueError("configure_run_autopilot_stage_invalid")


def _unavailable_stages(artifacts: tuple[PackageArtifact, ...]) -> dict[str, str]:
    paths = tuple(artifact.relative_path for artifact in artifacts)
    selected_source = (
        "02_source_documents" if any(path.startswith("02_source_documents/") for path in paths)
        else "02_source_acquisition"
    )
    unavailable = {
        (
            "02_source_acquisition"
            if selected_source == "02_source_documents"
            else "02_source_documents"
        ): f"{selected_source}_selected",
    }
    autopilot_02 = any(path.startswith("02_source_autopilot/") for path in paths)
    autopilot_03 = any(path.startswith("03_source_autopilot/") for path in paths)
    if not autopilot_02 and not autopilot_03:
        unavailable["02_source_autopilot"] = "not_requested"
        unavailable["03_source_autopilot"] = "not_requested"
    elif autopilot_02:
        unavailable["03_source_autopilot"] = "02_source_autopilot_selected"
    else:
        unavailable["02_source_autopilot"] = "03_source_autopilot_selected"
    return dict(sorted(unavailable.items()))


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
