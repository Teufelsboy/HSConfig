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


def create_configure_run_model(
    *, package: PackageModel, stage_artifacts: Mapping[str, bytes]
) -> ConfigureRunModel:
    artifacts = tuple(
        sorted(
            (
                PackageArtifact(relative_path=path, content=content)
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
        PackageArtifact(
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
    summary = PackageArtifact(
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
    if destination.exists() and any(destination.iterdir()):
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
    required = ("01_manifest/", "03_research/")
    if any(not any(path.startswith(prefix) for path in paths) for prefix in required):
        raise ValueError("configure_run_required_stage_missing")
    source_paths = [path for path in paths if path.startswith("02_source_documents/")]
    acquisition_paths = [path for path in paths if path.startswith("02_source_acquisition/")]
    if bool(source_paths) == bool(acquisition_paths):
        raise ValueError("configure_run_source_stage_invalid")


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
    if not any(path.startswith("02_source_autopilot/") for path in paths) and not any(
        path.startswith("03_source_autopilot/") for path in paths
    ):
        unavailable["02_source_autopilot"] = "not_requested"
    return dict(sorted(unavailable.items()))


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
