"""Immutable configure-run model rendered from the canonical package model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hsconfig.package_assembler import PackageModel
from hsconfig.configure_run_stage_contract import (
    configure_summary_bytes,
    validate_configure_run_stage_files,
)
from hsconfig.package_domain import _ImmutableAuthorityNode
from hsconfig.package_model import content_root_sha256
from hsconfig.package_render_authority import (
    AuthorityArtifact,
    render_package_authority,
)
from hsconfig.run_manifest import (
    MANIFEST_PATH,
    build_tree_manifest_from_artifacts,
    validate_run_paths,
    write_tree_manifest,
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
        validate_configure_run_stage_files(
            deck_name=self.deck_name,
            deck_fingerprint=self.deck_fingerprint,
            stage_files={
                artifact.relative_path: artifact.content
                for artifact in self.stage_artifacts
            },
        )
        _validate_no_file_ancestor_collisions(paths)
        _validate_unambiguous_run_paths(paths)


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
        _validate_unambiguous_run_paths(paths)
        content_artifacts = _configure_run_content_artifacts(
            self.artifacts
        )
        if content_artifacts != _render_content_artifacts(self.model):
            raise ValueError(
                "rendered_configure_run_model_artifacts_mismatch"
            )
        if (
            content_root_sha256(content_artifacts)
            != self.content_root_sha256
        ):
            raise ValueError("rendered_configure_run_content_root_mismatch")
        manifest_artifacts = tuple(
            artifact
            for artifact in self.artifacts
            if artifact.relative_path == MANIFEST_PATH
        )
        if (
            len(manifest_artifacts) != 1
            or manifest_artifacts[0].content
            != write_tree_manifest(
                build_tree_manifest_from_artifacts(
                    deck_name=self.model.deck_name,
                    deck_fingerprint=self.model.deck_fingerprint,
                    artifacts=content_artifacts,
                )
            )
        ):
            raise ValueError("rendered_configure_run_manifest_mismatch")


def create_configure_run_model(
    *,
    package: PackageModel,
    stage_artifacts: Mapping[str, bytes],
) -> ConfigureRunModel:
    if not isinstance(package, PackageModel):
        raise TypeError("package_model_required")
    stage_files = dict(stage_artifacts)
    if any(
        path.casefold() == "configure_summary.json"
        for path in stage_files
    ):
        raise ValueError("configure_run_reserved_path")
    stage_files["configure_summary.json"] = configure_summary_bytes(
        deck_name=package.compiled.deck_name,
        deck_fingerprint=package.compiled.deck_fingerprint,
        paths=tuple(sorted(stage_files)),
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
    content_artifacts = _render_content_artifacts(model)
    content_root = content_root_sha256(content_artifacts)
    manifest_artifact = _render_manifest_artifact(
        model=model,
        content_artifacts=content_artifacts,
    )
    return RenderedConfigureRun(
        model=model,
        artifacts=tuple(
            sorted(
                (*content_artifacts, manifest_artifact),
                key=lambda artifact: artifact.relative_path,
            )
        ),
        content_root_sha256=content_root,
    )


def _render_content_artifacts(
    model: ConfigureRunModel,
) -> tuple[AuthorityArtifact, ...]:
    package = render_package_authority(model.package)
    package_artifacts = tuple(
        AuthorityArtifact.from_content(
            relative_path=f"04_package/{artifact.relative_path}",
            content=artifact.content,
        )
        for artifact in package.artifacts
    )
    content_artifacts = tuple(
        sorted(
            (*model.stage_artifacts, *package_artifacts),
            key=lambda artifact: artifact.relative_path,
        )
    )
    _validate_no_file_ancestor_collisions(
        tuple(artifact.relative_path for artifact in content_artifacts)
    )
    return content_artifacts


def _render_manifest_artifact(
    *,
    model: ConfigureRunModel,
    content_artifacts: tuple[AuthorityArtifact, ...],
) -> AuthorityArtifact:
    return AuthorityArtifact.from_content(
        relative_path=MANIFEST_PATH,
        content=write_tree_manifest(
            build_tree_manifest_from_artifacts(
                deck_name=model.deck_name,
                deck_fingerprint=model.deck_fingerprint,
                artifacts=content_artifacts,
            )
        ),
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
    content_artifacts = _configure_run_content_artifacts(
        rendered.artifacts
    )
    manifest_artifacts = tuple(
        artifact
        for artifact in rendered.artifacts
        if artifact.relative_path == MANIFEST_PATH
    )
    if len(manifest_artifacts) != 1:
        raise ValueError("rendered_configure_run_manifest_missing")
    for artifact in (*content_artifacts, *manifest_artifacts):
        target = destination / artifact.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.content)
        if target.read_bytes() != artifact.content:
            raise ValueError("written_artifact_verification_failed")
    if (
        content_root_sha256(
            _configure_run_content_artifacts(rendered.artifacts)
        )
        != rendered.content_root_sha256
    ):
        raise ValueError("written_content_root_verification_failed")


def _validate_no_file_ancestor_collisions(paths: tuple[str, ...]) -> None:
    files = set(paths)
    for path in paths:
        parts = path.split("/")
        if any(
            "/".join(parts[:index]) in files
            for index in range(1, len(parts))
        ):
            raise ValueError("configure_run_artifact_path_collision")


def _configure_run_content_artifacts(
    artifacts: tuple[AuthorityArtifact, ...],
) -> tuple[AuthorityArtifact, ...]:
    return tuple(
        artifact
        for artifact in artifacts
        if artifact.relative_path != MANIFEST_PATH
    )


def _validate_unambiguous_run_paths(paths: tuple[str, ...]) -> None:
    try:
        validate_run_paths(paths)
    except ValueError as error:
        raise ValueError(
            "configure_run_artifact_path_ambiguous"
        ) from error
