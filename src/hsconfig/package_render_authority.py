"""Pure in-memory completion of the closed package artifact plan."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from hsconfig.operator_summary import build_operator_summary_from_inputs
from hsconfig.operator_summary_inputs import (
    freeze_operator_summary_inputs,
    load_operator_summary_inputs,
    replay_package_authority_inputs,
)
from hsconfig.output_ownership_manifest import (
    build_output_ownership_manifest,
)
from hsconfig.package_assembler import ArtifactPhase, PackageModel
from hsconfig.package_derivation_receipt import (
    build_package_derivation_receipt_from_view,
    canonical_package_derivation_receipt_bytes,
    verify_package_derivation_receipt_from_view,
)
from hsconfig.package_model import (
    content_root_sha256 as calculate_content_root_sha256,
)
from hsconfig.package_domain import canonical_relative_path
from hsconfig.runtime_surface_ledger import (
    rederive_runtime_surface_ledger_from_view,
)
from hsconfig.semantic_audit import render_semantic_audit_markdown
from hsconfig.source_evidence_closure import (
    build_source_evidence_closure_report,
)
from hsconfig.strict_package_validation import (
    strict_validation_passed,
    validate_complete_package_from_view,
)
from hsconfig.strong_promotion_report import build_strong_promotion_report
from hsconfig.visionai_registry import OPTIMIZED_START_REPORT_PATHS


class RenderFaultPoint(StrEnum):
    FINAL_PLAN = "final_plan"
    CORE_RUNTIME = "core_runtime"
    PRE_AUTHORITY = "pre_authority"
    RUNTIME_LEDGER = "runtime_ledger"
    VALIDATION = "validation"
    OWNERSHIP = "ownership"
    RECEIPT = "receipt"
    AUTHORITY = "authority"
    SUMMARY_DEPENDENT = "summary_dependent"
    FINAL_VERIFICATION = "final_verification"


class AuthorityArtifact(tuple):
    """Slotless exact-byte row whose authority cannot be rebound."""

    __slots__ = ()

    def __new__(
        cls,
        *,
        relative_path: str,
        content: bytes,
    ) -> AuthorityArtifact:
        path = canonical_relative_path(relative_path)
        payload = bytes(content)
        return tuple.__new__(
            cls,
            (
                path,
                payload,
                len(payload),
                hashlib.sha256(payload).hexdigest(),
            ),
        )

    @classmethod
    def from_content(
        cls,
        *,
        relative_path: str,
        content: bytes,
    ) -> AuthorityArtifact:
        return cls(relative_path=relative_path, content=content)

    @property
    def relative_path(self) -> str:
        return self[0]

    @property
    def content(self) -> bytes:
        return self[1]

    @property
    def size(self) -> int:
        return self[2]

    @property
    def sha256(self) -> str:
        return self[3]

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("authority_artifact_immutable")


class ArtifactSet(tuple):
    """Immutable, exact-byte PackageView snapshot."""

    __slots__ = ()

    def __new__(
        cls,
        artifacts: tuple[AuthorityArtifact, ...],
    ) -> ArtifactSet:
        rows = tuple(artifacts)
        if any(not isinstance(row, AuthorityArtifact) for row in rows):
            raise TypeError("artifact_set_rows_invalid")
        paths = tuple(row.relative_path for row in rows)
        if len(paths) != len(set(paths)):
            raise ValueError("package_artifact_path_duplicate")
        if paths != tuple(sorted(paths)):
            rows = tuple(sorted(rows, key=lambda row: row.relative_path))
        return tuple.__new__(cls, rows)

    @property
    def artifacts(self) -> tuple[AuthorityArtifact, ...]:
        return tuple(self)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("artifact_set_immutable")

    @classmethod
    def empty(cls) -> ArtifactSet:
        return cls(())

    @classmethod
    def from_files(cls, files: Mapping[str, bytes]) -> ArtifactSet:
        return cls(
            tuple(
                AuthorityArtifact.from_content(
                    relative_path=relative_path,
                    content=bytes(content),
                )
                for relative_path, content in sorted(files.items())
            )
        )

    def file_names(self) -> tuple[str, ...]:
        return tuple(row.relative_path for row in self)

    def read_bytes(self, relative_path: str) -> bytes:
        for artifact in self:
            if artifact.relative_path == relative_path:
                return artifact.content
        raise FileNotFoundError(relative_path)

    def read_json(self, relative_path: str) -> Any:
        return json.loads(
            self.read_bytes(relative_path).decode("utf-8-sig")
        )

    def exists(self, relative_path: str) -> bool:
        return relative_path in self.file_names()

    def with_file(
        self,
        relative_path: str,
        content: bytes,
    ) -> ArtifactSet:
        if self.exists(relative_path):
            raise ValueError("package_artifact_path_duplicate")
        return ArtifactSet(
            (
                *self,
                AuthorityArtifact.from_content(
                    relative_path=relative_path,
                    content=bytes(content),
                ),
            )
        )

    def with_files(
        self,
        files: Mapping[str, bytes],
    ) -> ArtifactSet:
        snapshot = self
        for relative_path, content in sorted(files.items()):
            snapshot = snapshot.with_file(relative_path, content)
        return snapshot


class RenderedAuthorityPackage(tuple):
    """Slotless final snapshot with inseparable model, bytes, and root."""

    __slots__ = ()

    def __new__(
        cls,
        *,
        model: PackageModel,
        artifacts: ArtifactSet,
        content_root_sha256: str,
    ) -> RenderedAuthorityPackage:
        if not isinstance(model, PackageModel):
            raise TypeError("rendered_authority_model_invalid")
        if not isinstance(artifacts, ArtifactSet):
            raise TypeError("rendered_authority_artifacts_invalid")
        expected = calculate_content_root_sha256(artifacts.artifacts)
        if content_root_sha256 != expected:
            raise ValueError("rendered_authority_content_root_mismatch")
        return tuple.__new__(
            cls,
            (model, artifacts, content_root_sha256),
        )

    @property
    def model(self) -> PackageModel:
        return self[0]

    @property
    def artifacts(self) -> ArtifactSet:
        return self[1]

    @property
    def content_root_sha256(self) -> str:
        return self[2]

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("rendered_authority_package_immutable")


RenderFaultHook = Callable[[RenderFaultPoint, ArtifactSet], None]


def render_package_authority(
    model: PackageModel,
    *,
    fault_hook: RenderFaultHook | None = None,
) -> RenderedAuthorityPackage:
    """Render and verify the complete package without touching a destination."""

    if not isinstance(model, PackageModel):
        raise TypeError("package_model_required")
    artifacts = ArtifactSet.empty()
    _observe(fault_hook, RenderFaultPoint.FINAL_PLAN, artifacts)

    artifacts = artifacts.with_files(_core_runtime_files(model))
    _require_phase_exact(model, artifacts, ArtifactPhase.CORE_RUNTIME)
    _observe(fault_hook, RenderFaultPoint.CORE_RUNTIME, artifacts)

    artifacts = artifacts.with_files(_pre_authority_files(model))
    _require_phase_exact(model, artifacts, ArtifactPhase.PRE_AUTHORITY)
    _observe(fault_hook, RenderFaultPoint.PRE_AUTHORITY, artifacts)

    ledger = rederive_runtime_surface_ledger_from_view(artifacts)
    if _canonical_json(ledger) != _canonical_json(
        model.compiled.semantic_runtime_ledger.to_value()
    ):
        raise ValueError("runtime_surface_ledger_semantic_parity_failed")
    artifacts = artifacts.with_file(
        "reports/runtime_surface_ledger.json",
        _json_bytes(ledger),
    )
    _require_phase_exact(
        model,
        artifacts,
        ArtifactPhase.PHYSICAL_RUNTIME_LEDGER,
    )
    _observe(fault_hook, RenderFaultPoint.RUNTIME_LEDGER, artifacts)

    validation = validate_complete_package_from_view(artifacts)
    if not strict_validation_passed(validation):
        raise ValueError("rendered_package_strict_validation_failed")
    artifacts = artifacts.with_file(
        "reports/validation_report.json",
        _json_bytes(validation),
    )
    _require_phase_exact(model, artifacts, ArtifactPhase.VALIDATION)
    _observe(fault_hook, RenderFaultPoint.VALIDATION, artifacts)

    generated_files = [
        row.relative_path.replace("/", "\\")
        for row in model.artifact_plan.artifacts
    ]
    behavior_plan = artifacts.read_json(
        "reports/card_behavior_plan_report.json"
    )
    ownership = build_output_ownership_manifest(
        generated_files,
        card_behavior_plan=behavior_plan,
    )
    artifacts = artifacts.with_file(
        "reports/output_ownership_manifest.json",
        _json_bytes(ownership),
    )
    _require_phase_exact(model, artifacts, ArtifactPhase.OWNERSHIP)
    _observe(fault_hook, RenderFaultPoint.OWNERSHIP, artifacts)

    receipt = build_package_derivation_receipt_from_view(artifacts)
    artifacts = artifacts.with_file(
        "package_derivation_receipt.json",
        canonical_package_derivation_receipt_bytes(receipt),
    )
    _require_phase_exact(model, artifacts, ArtifactPhase.RECEIPT)
    _observe(fault_hook, RenderFaultPoint.RECEIPT, artifacts)

    package_derivation, package_authority = (
        replay_package_authority_inputs(artifacts)
    )
    summary_inputs = _operator_summary_inputs(
        model=model,
        artifacts=artifacts,
        validation=validation,
        ownership=ownership,
        ledger=ledger,
        generated_files=generated_files,
        package_derivation=package_derivation,
        package_authority=package_authority,
    )
    operator_summary = build_operator_summary_from_inputs(summary_inputs)
    artifacts = artifacts.with_file(
        "reports/operator_summary.json",
        _json_bytes(operator_summary),
    )
    _require_phase_exact(model, artifacts, ArtifactPhase.AUTHORITY)
    _observe(fault_hook, RenderFaultPoint.AUTHORITY, artifacts)

    c6_inputs = model.compiled.c6_inputs.to_value()
    artifacts = artifacts.with_files(
        {
            "reports/card_semantic_audit.md": (
                render_semantic_audit_markdown(
                    {
                        **c6_inputs["semantic_report"],
                        "configuration_assurance": operator_summary[
                            "configuration_assurance"
                        ],
                    }
                ).encode("utf-8")
            ),
            "reports/strong_promotion_report.json": _json_bytes(
                build_strong_promotion_report(
                    deck_name=model.compiled.deck_name,
                    fixture_stage="runtime_prepare",
                    operator_summary=operator_summary,
                    source_claim_gap_report=c6_inputs[
                        "source_claim_gap_report"
                    ],
                )
            ),
            "reports/source_evidence_closure.json": _json_bytes(
                build_source_evidence_closure_report(
                    deck_name=model.compiled.deck_name,
                    deck_code=str(
                        artifacts.read_json(
                            "reports/input_manifest.json"
                        ).get("deck_code", "")
                    ),
                    operator_summary=operator_summary,
                    source_to_runtime_explainability_report=c6_inputs[
                        "source_to_runtime_explainability_report"
                    ],
                    source_claim_gap_report=c6_inputs[
                        "source_claim_gap_report"
                    ],
                )
            ),
        }
    )
    _require_phase_exact(
        model,
        artifacts,
        ArtifactPhase.SUMMARY_DEPENDENT,
    )
    _observe(fault_hook, RenderFaultPoint.SUMMARY_DEPENDENT, artifacts)

    _verify_final_package(model, artifacts, validation)
    _observe(fault_hook, RenderFaultPoint.FINAL_VERIFICATION, artifacts)
    return RenderedAuthorityPackage(
        model=model,
        artifacts=artifacts,
        content_root_sha256=calculate_content_root_sha256(
            artifacts.artifacts
        ),
    )


def _core_runtime_files(model: PackageModel) -> Mapping[str, bytes]:
    return MappingProxyType(
        {
            (
                f"CustomConfig/{model.compiled.deck_slug}/"
                f"{surface.file_name}"
            ): _json_bytes(surface.document.to_value())
            for surface in model.compiled.runtime_surfaces
        }
    )


def _pre_authority_files(model: PackageModel) -> Mapping[str, bytes]:
    files = {
        projection.relative_path: (
            projection.document.canonical_json
            if projection.relative_path in OPTIMIZED_START_REPORT_PATHS
            else _json_bytes(projection.document.to_value())
        )
        for projection in model.compiled.json_projections
    }
    files.update(
        {
            projection.relative_path: projection.text.encode("utf-8")
            for projection in model.compiled.text_projections
        }
    )
    return MappingProxyType(files)


def _operator_summary_inputs(
    *,
    model: PackageModel,
    artifacts: ArtifactSet,
    validation: Mapping[str, Any],
    ownership: Mapping[str, Any],
    ledger: Mapping[str, Any],
    generated_files: list[str],
    package_derivation: Mapping[str, Any],
    package_authority: Mapping[str, Any],
):
    c6 = model.compiled.c6_inputs.to_value()
    manifest = artifacts.read_json("reports/input_manifest.json")
    guide_bundle = artifacts.read_json("reports/guide_claim_bundle.json")
    mulligan = artifacts.read_json("reports/mulligan_plan_report.json")
    return freeze_operator_summary_inputs(
        deck_name=model.compiled.deck_name,
        deck_code=manifest.get("deck_code", ""),
        technical_validation=validation,
        guide_source_depth=c6["guide_source_depth_report"],
        unsupported_conditions=mulligan.get("suppressed_rules", []),
        globalvalue_authority=c6["global_values_authority_matrix"],
        claim_coverage_report=guide_bundle.get(
            "claim_coverage_report",
            guide_bundle["coverage"],
        ),
        config_readiness_summary=c6["config_readiness_report"]["summary"],
        config_readiness_report=c6["config_readiness_report"],
        claim_conflict_report=guide_bundle.get("claim_conflict_report"),
        mulligan_plan_report=mulligan,
        card_behavior_plan_report=artifacts.read_json(
            "reports/card_behavior_plan_report.json"
        ),
        combo_plan_report=artifacts.read_json(
            "reports/combo_plan_report.json"
        ),
        globalvalues_profile_report=artifacts.read_json(
            "reports/globalvalues_profile.json"
        ),
        semantic_enrichment_report=c6["semantic_report"],
        mechanic_drift_report=artifacts.read_json(
            "reports/mechanic_drift_report.json"
        ),
        source_claim_gap_report=c6["source_claim_gap_report"],
        source_contract_audit_report=artifacts.read_json(
            "reports/source_contract_audit.json"
        ),
        source_to_runtime_explainability_report=c6[
            "source_to_runtime_explainability_report"
        ],
        output_ownership_manifest=ownership,
        gameplan_contract=c6["gameplan_contract"],
        package_derivation=package_derivation,
        package_authority=package_authority,
        deck_input_verification=manifest.get("deck_input_verification"),
        runtime_surface_ledger=ledger,
        pre_run_closure_report=artifacts.read_json(
            "reports/pre_run_closure.json"
        ),
        generated_files=generated_files,
    )


def _verify_final_package(
    model: PackageModel,
    artifacts: ArtifactSet,
    validation: Mapping[str, Any],
) -> None:
    planned = tuple(
        row.relative_path for row in model.artifact_plan.artifacts
    )
    if artifacts.file_names() != planned:
        raise ValueError("rendered_package_plan_mismatch")
    final_validation = validate_complete_package_from_view(artifacts)
    if final_validation != dict(validation):
        raise ValueError("rendered_package_validation_replay_mismatch")
    receipt = artifacts.read_json("package_derivation_receipt.json")
    verified, reasons = verify_package_derivation_receipt_from_view(
        artifacts,
        receipt,
    )
    if not verified or reasons:
        raise ValueError("rendered_package_receipt_verification_failed")
    replay_inputs = load_operator_summary_inputs(artifacts)
    stored_summary = artifacts.read_json("reports/operator_summary.json")
    if (
        replay_inputs.authority.package_summary_parity is not True
        or build_operator_summary_from_inputs(replay_inputs)
        != stored_summary
    ):
        raise ValueError("rendered_package_operator_summary_replay_failed")


def _require_phase_exact(
    model: PackageModel,
    artifacts: ArtifactSet,
    phase: ArtifactPhase,
) -> None:
    expected = {
        row.relative_path
        for row in model.artifact_plan.artifacts
        if row.phase is phase
    }
    actual = expected.intersection(artifacts.file_names())
    if actual != expected:
        raise ValueError(f"rendered_package_phase_incomplete:{phase.value}")


def _observe(
    hook: RenderFaultHook | None,
    point: RenderFaultPoint,
    artifacts: ArtifactSet,
) -> None:
    if hook is not None:
        hook(point, artifacts)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = (
    "ArtifactSet",
    "AuthorityArtifact",
    "RenderFaultHook",
    "RenderFaultPoint",
    "RenderedAuthorityPackage",
    "render_package_authority",
)
