"""Immutable configure-run model rendered from the canonical package model."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hsconfig.package_assembler import PackageModel
from hsconfig.package_domain import _ImmutableAuthorityNode
from hsconfig.package_model import content_root_sha256
from hsconfig.package_render_authority import (
    AuthorityArtifact,
    render_package_authority,
)


@dataclass(frozen=True, init=False)
class ConfigureRunModel(_ImmutableAuthorityNode):
    deck_name: str
    deck_fingerprint: str
    package: PackageModel
    stage_artifacts: tuple[AuthorityArtifact, ...]

    @classmethod
    def _normalize_authority_values(
        cls,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(values)
        normalized["stage_artifacts"] = tuple(values["stage_artifacts"])
        return normalized

    def __post_init__(self) -> None:
        if not isinstance(self.package, PackageModel):
            raise TypeError("configure_run_package_model_invalid")
        compiled = self.package.compiled
        if (
            self.deck_name != compiled.deck_name
            or self.deck_fingerprint != compiled.deck_fingerprint
        ):
            raise ValueError("configure_run_package_identity_mismatch")
        if any(
            not isinstance(artifact, AuthorityArtifact)
            for artifact in self.stage_artifacts
        ):
            raise TypeError("configure_run_stage_artifact_invalid")
        paths = tuple(
            artifact.relative_path for artifact in self.stage_artifacts
        )
        if tuple(sorted(paths)) != paths or len(set(paths)) != len(paths):
            raise ValueError("configure_run_stage_artifacts_not_unique_sorted")
        _validate_required_stages(paths)
        _validate_no_file_ancestor_collisions(paths)


@dataclass(frozen=True, init=False)
class RenderedConfigureRun(_ImmutableAuthorityNode):
    model: ConfigureRunModel
    artifacts: tuple[AuthorityArtifact, ...]
    content_root_sha256: str

    @classmethod
    def _normalize_authority_values(
        cls,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(values)
        normalized["artifacts"] = tuple(values["artifacts"])
        return normalized

    def __post_init__(self) -> None:
        if not isinstance(self.model, ConfigureRunModel):
            raise TypeError("rendered_configure_run_model_invalid")
        if any(
            not isinstance(artifact, AuthorityArtifact)
            for artifact in self.artifacts
        ):
            raise TypeError("rendered_configure_run_artifact_invalid")
        paths = tuple(artifact.relative_path for artifact in self.artifacts)
        if tuple(sorted(paths)) != paths or len(set(paths)) != len(paths):
            raise ValueError("rendered_configure_run_artifacts_invalid")
        _validate_no_file_ancestor_collisions(paths)
        if content_root_sha256(self.artifacts) != self.content_root_sha256:
            raise ValueError("rendered_configure_run_content_root_mismatch")


def create_configure_run_model(
    *,
    package: PackageModel,
    stage_artifacts: Mapping[str, bytes],
) -> ConfigureRunModel:
    if not isinstance(package, PackageModel):
        raise TypeError("package_model_required")
    stage_files = dict(stage_artifacts)
    if "configure_summary.json" not in stage_files:
        stage_files["configure_summary.json"] = _json_bytes(
            {
                "schema_version": 1,
                "deck_name": package.compiled.deck_name,
                "deck_fingerprint": package.compiled.deck_fingerprint,
                "unavailable_stages": _unavailable_stages(
                    tuple(sorted(stage_files))
                ),
            }
        )
    artifacts = tuple(
        AuthorityArtifact.from_content(
            relative_path=relative_path,
            content=content,
        )
        for relative_path, content in sorted(stage_files.items())
    )
    return ConfigureRunModel(
        deck_name=package.compiled.deck_name,
        deck_fingerprint=package.compiled.deck_fingerprint,
        package=package,
        stage_artifacts=artifacts,
    )


def render_configure_run_model(model: ConfigureRunModel) -> RenderedConfigureRun:
    if not isinstance(model, ConfigureRunModel):
        raise TypeError("configure_run_model_required")
    package = render_package_authority(model.package)
    package_artifacts = tuple(
        AuthorityArtifact.from_content(
            relative_path=f"04_package/{artifact.relative_path}",
            content=artifact.content,
        )
        for artifact in package.artifacts
    )
    artifacts = tuple(
        sorted(
            (*model.stage_artifacts, *package_artifacts),
            key=lambda artifact: artifact.relative_path,
        )
    )
    _validate_no_file_ancestor_collisions(
        tuple(artifact.relative_path for artifact in artifacts)
    )
    return RenderedConfigureRun(
        model=model,
        artifacts=artifacts,
        content_root_sha256=content_root_sha256(artifacts),
    )


def write_rendered_configure_run(
    rendered: RenderedConfigureRun,
    destination: Path,
) -> None:
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
    if content_root_sha256(rendered.artifacts) != rendered.content_root_sha256:
        raise ValueError("written_content_root_verification_failed")


def _validate_required_stages(paths: tuple[str, ...]) -> None:
    if any(
        path == "04_package"
        or path.startswith("04_package/")
        or path.startswith("configure_summary.json/")
        for path in paths
    ):
        raise ValueError("configure_run_reserved_path")
    required = ("01_manifest/", "03_research/")
    if any(
        not any(path.startswith(prefix) for path in paths)
        for prefix in required
    ):
        raise ValueError("configure_run_required_stage_missing")
    source_paths = any(
        path.startswith("02_source_documents/") for path in paths
    )
    acquisition_paths = any(
        path.startswith("02_source_acquisition/") for path in paths
    )
    if source_paths == acquisition_paths:
        raise ValueError("configure_run_source_stage_invalid")
    autopilot_02 = any(
        path.startswith("02_source_autopilot/") for path in paths
    )
    autopilot_03 = any(
        path.startswith("03_source_autopilot/") for path in paths
    )
    if (
        (autopilot_02 and autopilot_03)
        or (source_paths and autopilot_03)
        or (acquisition_paths and autopilot_02)
    ):
        raise ValueError("configure_run_autopilot_stage_invalid")


def _validate_no_file_ancestor_collisions(paths: tuple[str, ...]) -> None:
    files = set(paths)
    for path in paths:
        parts = path.split("/")
        if any(
            "/".join(parts[:index]) in files
            for index in range(1, len(parts))
        ):
            raise ValueError("configure_run_artifact_path_collision")


def _unavailable_stages(paths: tuple[str, ...]) -> dict[str, str]:
    documents = any(
        path.startswith("02_source_documents/") for path in paths
    )
    acquisition = any(
        path.startswith("02_source_acquisition/") for path in paths
    )
    unavailable: dict[str, str] = {}
    if documents:
        unavailable["02_source_acquisition"] = "02_source_documents_selected"
    elif acquisition:
        unavailable["02_source_documents"] = "02_source_acquisition_selected"
    else:
        unavailable["02_source_documents"] = "not_requested"
        unavailable["02_source_acquisition"] = "not_requested"
    autopilot_02 = any(
        path.startswith("02_source_autopilot/") for path in paths
    )
    autopilot_03 = any(
        path.startswith("03_source_autopilot/") for path in paths
    )
    if not autopilot_02 and not autopilot_03:
        unavailable["02_source_autopilot"] = "not_requested"
        unavailable["03_source_autopilot"] = "not_requested"
    elif autopilot_02:
        unavailable["03_source_autopilot"] = "02_source_autopilot_selected"
    else:
        unavailable["02_source_autopilot"] = "03_source_autopilot_selected"
    return dict(sorted(unavailable.items()))


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        .encode("utf-8")
        + b"\n"
    )
