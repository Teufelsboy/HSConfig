"""Pure assembly of a compiled package into its closed artifact plan."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from types import MappingProxyType

from hsconfig.package_domain import _ImmutableAuthorityNode
from hsconfig.package_compiler import (
    PRE_AUTHORITY_OWNER_BY_PATH,
    CompiledPackage,
    ProjectionOwner,
)


class ArtifactPhase(StrEnum):
    CORE_RUNTIME = "core_runtime"
    PRE_AUTHORITY = "pre_authority"
    PHYSICAL_RUNTIME_LEDGER = "physical_runtime_ledger"
    VALIDATION = "validation"
    OWNERSHIP = "ownership"
    RECEIPT = "receipt"
    AUTHORITY = "authority"
    SUMMARY_DEPENDENT = "summary_dependent"


_RUNTIME_OWNERS = frozenset({"globalvalues", "mulligan", "cardid", "combo"})
_RESERVED_OWNERS = frozenset(
    {
        "runtime_surface_ledger",
        "strict_package_validation",
        "output_ownership_manifest",
        "package_derivation_receipt",
        "operator_summary",
        "semantic_audit",
        "strong_promotion_report",
        "source_evidence_closure",
    }
)
_ALLOWED_OWNERS = frozenset(
    {
        *(owner.value for owner in ProjectionOwner),
        *_RUNTIME_OWNERS,
        *_RESERVED_OWNERS,
    }
)


@dataclass(frozen=True, init=False)
class PlannedArtifact(_ImmutableAuthorityNode):
    relative_path: str
    owner: str
    phase: ArtifactPhase

    def __post_init__(self) -> None:
        if self.owner not in _ALLOWED_OWNERS:
            raise ValueError("artifact_owner_invalid")
        if not isinstance(self.phase, ArtifactPhase):
            raise ValueError("artifact_phase_invalid")


@dataclass(frozen=True, init=False)
class ArtifactPlan(_ImmutableAuthorityNode):
    artifacts: tuple[PlannedArtifact, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.artifacts, tuple) or any(
            not isinstance(row, PlannedArtifact) for row in self.artifacts
        ):
            raise TypeError("artifact_plan_rows_invalid")
        paths = tuple(row.relative_path for row in self.artifacts)
        for path in paths:
            if not _is_canonical_relative_path(path):
                raise ValueError("artifact_path_invalid")
        if len(paths) != len(set(paths)):
            raise ValueError("artifact_path_duplicate")
        folded = tuple(path.casefold() for path in paths)
        if len(folded) != len(set(folded)):
            raise ValueError("artifact_path_casefold_collision")
        path_parts = tuple(PurePosixPath(path).parts for path in paths)
        for index, left in enumerate(path_parts):
            for right in path_parts[index + 1 :]:
                short, long = sorted((left, right), key=len)
                if len(short) < len(long) and long[: len(short)] == short:
                    raise ValueError("artifact_path_prefix_collision")
                folded_short, folded_long = sorted(
                    (
                        tuple(part.casefold() for part in left),
                        tuple(part.casefold() for part in right),
                    ),
                    key=len,
                )
                if (
                    len(folded_short) < len(folded_long)
                    and folded_long[: len(folded_short)] == folded_short
                ):
                    raise ValueError(
                        "artifact_path_casefold_prefix_collision"
                    )
        if paths != tuple(sorted(paths)):
            raise ValueError("artifact_plan_not_sorted")
        for row in self.artifacts:
            expected_owner = PRE_AUTHORITY_OWNER_BY_PATH.get(
                row.relative_path
            )
            if row.phase is ArtifactPhase.PRE_AUTHORITY and (
                expected_owner is None
                or row.owner != expected_owner.value
            ):
                raise ValueError("artifact_projection_authority_invalid")
            if expected_owner is not None and (
                row.phase is not ArtifactPhase.PRE_AUTHORITY
            ):
                raise ValueError("artifact_projection_authority_invalid")
            reserved = _RESERVED_AUTHORITY_BY_PATH.get(row.relative_path)
            if reserved is not None and (
                (row.owner, row.phase) != reserved
            ):
                raise ValueError("artifact_reserved_authority_invalid")
            if row.phase is ArtifactPhase.CORE_RUNTIME and (
                row.owner not in _RUNTIME_OWNERS
                or not row.relative_path.startswith("CustomConfig/")
            ):
                raise ValueError("artifact_authority_invalid")
            if row.phase is ArtifactPhase.RECEIPT and (
                row.relative_path != "package_derivation_receipt.json"
                or row.owner != "package_derivation_receipt"
            ):
                raise ValueError("artifact_authority_invalid")
            if row.phase not in {
                ArtifactPhase.CORE_RUNTIME,
                ArtifactPhase.PRE_AUTHORITY,
                ArtifactPhase.RECEIPT,
            }:
                if (
                    not row.relative_path.startswith("reports/")
                    or reserved != (row.owner, row.phase)
                ):
                    raise ValueError("artifact_authority_invalid")


@dataclass(frozen=True, init=False)
class PackageModel(_ImmutableAuthorityNode):
    compiled: CompiledPackage
    artifact_plan: ArtifactPlan

    def __post_init__(self) -> None:
        if not isinstance(self.compiled, CompiledPackage):
            raise TypeError("package_model_compiled_invalid")
        if not isinstance(self.artifact_plan, ArtifactPlan):
            raise TypeError("package_model_artifact_plan_invalid")
        if not self.artifact_plan.artifacts:
            raise ValueError("package_model_artifact_plan_empty")
        if self.artifact_plan.artifacts != _planned_artifacts(self.compiled):
            raise ValueError("package_model_artifact_plan_incomplete")
        runtime_prefix = f"CustomConfig/{self.compiled.deck_slug}/"
        for row in self.artifact_plan.artifacts:
            if row.phase is ArtifactPhase.CORE_RUNTIME:
                if not row.relative_path.startswith(runtime_prefix):
                    raise ValueError("artifact_runtime_path_invalid")
            elif row.phase is ArtifactPhase.RECEIPT:
                if row.relative_path != "package_derivation_receipt.json":
                    raise ValueError("artifact_receipt_path_invalid")
            elif not row.relative_path.startswith("reports/"):
                raise ValueError("artifact_report_path_invalid")


_RESERVED_ARTIFACTS = (
    PlannedArtifact(
        "reports/runtime_surface_ledger.json",
        "runtime_surface_ledger",
        ArtifactPhase.PHYSICAL_RUNTIME_LEDGER,
    ),
    PlannedArtifact(
        "reports/validation_report.json",
        "strict_package_validation",
        ArtifactPhase.VALIDATION,
    ),
    PlannedArtifact(
        "reports/output_ownership_manifest.json",
        "output_ownership_manifest",
        ArtifactPhase.OWNERSHIP,
    ),
    PlannedArtifact(
        "package_derivation_receipt.json",
        "package_derivation_receipt",
        ArtifactPhase.RECEIPT,
    ),
    PlannedArtifact(
        "reports/operator_summary.json",
        "operator_summary",
        ArtifactPhase.AUTHORITY,
    ),
    PlannedArtifact(
        "reports/card_semantic_audit.md",
        "semantic_audit",
        ArtifactPhase.SUMMARY_DEPENDENT,
    ),
    PlannedArtifact(
        "reports/strong_promotion_report.json",
        "strong_promotion_report",
        ArtifactPhase.SUMMARY_DEPENDENT,
    ),
    PlannedArtifact(
        "reports/source_evidence_closure.json",
        "source_evidence_closure",
        ArtifactPhase.SUMMARY_DEPENDENT,
    ),
)
_RESERVED_AUTHORITY_BY_PATH = MappingProxyType({
    row.relative_path: (row.owner, row.phase)
    for row in _RESERVED_ARTIFACTS
})


def assemble_package(compiled: CompiledPackage) -> PackageModel:
    """Create the exact, sorted plan without rendering or filesystem access."""

    if not isinstance(compiled, CompiledPackage):
        raise TypeError("compiled_package_required")
    artifacts = _planned_artifacts(compiled)
    return PackageModel(
        compiled=compiled,
        artifact_plan=ArtifactPlan(artifacts),
    )


def _planned_artifacts(
    compiled: CompiledPackage,
) -> tuple[PlannedArtifact, ...]:
    rows = [
        *(
            PlannedArtifact(
                (
                    f"CustomConfig/{compiled.deck_slug}/"
                    f"{surface.file_name}"
                ),
                surface.owner,
                ArtifactPhase.CORE_RUNTIME,
            )
            for surface in compiled.runtime_surfaces
        ),
        *(
            PlannedArtifact(
                projection.relative_path,
                projection.owner.value,
                ArtifactPhase.PRE_AUTHORITY,
            )
            for projection in compiled.json_projections
        ),
        *(
            PlannedArtifact(
                projection.relative_path,
                projection.owner.value,
                ArtifactPhase.PRE_AUTHORITY,
            )
            for projection in compiled.text_projections
        ),
        *_RESERVED_ARTIFACTS,
    ]
    return tuple(
        sorted(
            rows,
            key=lambda row: row.relative_path,
        )
    )


def _is_canonical_relative_path(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 for character in value)
    ):
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith(("/", "./")):
        return False
    if any(part in {"", ".", ".."} for part in path.parts):
        return False
    reserved_names = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
    for part in path.parts:
        if part.endswith((" ", ".")):
            return False
        if part.split(".", 1)[0].casefold() in reserved_names:
            return False
    return path.as_posix() == value


__all__ = (
    "ArtifactPhase",
    "ArtifactPlan",
    "PackageModel",
    "PlannedArtifact",
    "assemble_package",
)
