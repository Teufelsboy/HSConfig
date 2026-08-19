"""Deeply immutable inputs for operator status and summary projection."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Literal

from hsconfig.configuration_mode import (
    LLM_OPTIMIZED_START,
    configuration_mode_from_manifest,
)
from hsconfig.package_domain import canonical_relative_path
from hsconfig.package_derivation_receipt import (
    OPTIMIZED_DERIVATION_RECEIPT_SCHEMA_VERSION,
    canonical_source_receipt_reasons,
    derivation_schema_version_supported,
    package_authority_context_verified,
    package_derivation_receipt_sha256,
    verify_package_derivation_receipt_from_view,
)
from hsconfig.package_model import PackageView
from hsconfig.source_acquisition_provenance import (
    strategic_source_provenance_is_verified,
)


_MISSING = object()
_INVALID_JSON = object()
_MEMORY_LABEL = "memory://operator-summary"


@dataclass(frozen=True, slots=True)
class _SnapshotPackageView:
    names: tuple[str, ...]
    files: Mapping[str, bytes]

    def file_names(self) -> tuple[str, ...]:
        return self.names

    def read_bytes(self, relative_path: str) -> bytes:
        return self.files[relative_path]

    def read_json(self, relative_path: str) -> Any:
        return json.loads(
            self.read_bytes(relative_path).decode("utf-8-sig")
        )

    def exists(self, relative_path: str) -> bool:
        return relative_path in self.files


@dataclass(frozen=True, slots=True)
class OperatorAuthorityInputs:
    """Only facts permitted to decide runtime-apply authority."""

    technical_validation: Mapping[str, Any]
    package_derivation: Mapping[str, Any] | None
    package_authority: Mapping[str, Any] | None
    deck_input_verification_report: Mapping[str, Any] | None
    strict_package_validation: bool
    actual_runtime_surface_inventory: bool
    deck_input_verification: bool
    source_receipt_validity: bool
    source_acquisition_eligibility: bool
    derivation_receipt_validity: bool
    package_summary_parity: bool
    strategy_authority_mode: Literal[
        "source_contract",
        "llm_optimized_start",
    ] = "source_contract"
    optimized_start_derivation_validity: bool = False
    blocking_reasons: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "technical_validation",
            "package_derivation",
            "package_authority",
            "deck_input_verification_report",
            "blocking_reasons",
        ):
            object.__setattr__(self, name, _freeze(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class OperatorDiagnosticInputs:
    """Immutable diagnostic inputs with no apply-authority fields."""

    guide_source_depth: Mapping[str, Any]
    unsupported_conditions: tuple[Mapping[str, Any], ...]
    globalvalue_authority: Mapping[str, Any]
    generated_files: tuple[str, ...]
    claim_coverage_report: Mapping[str, Any]
    config_readiness_summary: Mapping[str, Any]
    config_readiness_report: Mapping[str, Any]
    claim_conflict_report: Mapping[str, Any]
    mulligan_plan_report: Mapping[str, Any]
    card_behavior_plan_report: Mapping[str, Any]
    combo_plan_report: Mapping[str, Any]
    globalvalues_profile_report: Mapping[str, Any]
    semantic_enrichment_report: Mapping[str, Any]
    mechanic_drift_report: Mapping[str, Any]
    source_claim_gap_report: Mapping[str, Any]
    source_contract_audit_report: Mapping[str, Any]
    source_to_runtime_explainability_report: Mapping[str, Any]
    output_ownership_manifest: Mapping[str, Any]
    gameplan_contract: Mapping[str, Any]
    runtime_surface_ledger: Mapping[str, Any]
    pre_run_closure_report: Mapping[str, Any]
    reason_rows: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        for name in (
            "guide_source_depth",
            "unsupported_conditions",
            "globalvalue_authority",
            "generated_files",
            "claim_coverage_report",
            "config_readiness_summary",
            "config_readiness_report",
            "claim_conflict_report",
            "mulligan_plan_report",
            "card_behavior_plan_report",
            "combo_plan_report",
            "globalvalues_profile_report",
            "semantic_enrichment_report",
            "mechanic_drift_report",
            "source_claim_gap_report",
            "source_contract_audit_report",
            "source_to_runtime_explainability_report",
            "output_ownership_manifest",
            "gameplan_contract",
            "runtime_surface_ledger",
            "pre_run_closure_report",
            "reason_rows",
        ):
            object.__setattr__(self, name, _freeze(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class OperatorSummaryInputs:
    """Complete immutable input boundary for an operator summary."""

    deck_name: str
    deck_code: str
    package_label: str
    authority: OperatorAuthorityInputs
    diagnostics: OperatorDiagnosticInputs
    legacy_kwargs: Mapping[str, Any]
    file_names: tuple[str, ...] = ()
    file_bytes: Mapping[str, bytes] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "legacy_kwargs",
            _freeze(self.legacy_kwargs),
        )
        object.__setattr__(
            self,
            "file_names",
            tuple(str(value) for value in self.file_names),
        )
        object.__setattr__(
            self,
            "file_bytes",
            _freeze(self.file_bytes),
        )


def freeze_operator_summary_inputs(**legacy_kwargs: Any) -> OperatorSummaryInputs:
    """Freeze caller-owned in-memory reports before pure projection."""

    raw = _detach_legacy_inputs(legacy_kwargs)
    normalized = _normalized_legacy_inputs(raw)
    return _inputs_from_normalized(
        normalized,
        package_label=_MEMORY_LABEL,
        file_names=(),
        file_bytes=MappingProxyType({}),
        legacy_kwargs=raw,
    )


def load_operator_summary_inputs(
    package: PackageView,
) -> OperatorSummaryInputs:
    """Snapshot a package view once for deterministic report replay."""

    raw_names = tuple(package.file_names())
    names: list[str] = []
    seen: set[str] = set()
    for value in raw_names:
        try:
            name = canonical_relative_path(value)
        except (TypeError, ValueError) as error:
            raise ValueError("operator_summary_package_path_invalid") from error
        if name in seen:
            raise ValueError("operator_summary_package_path_duplicate")
        seen.add(name)
        names.append(name)
    names_tuple = tuple(sorted(names))

    files: dict[str, bytes] = {}
    documents: dict[str, Any] = {}
    for name in names_tuple:
        raw = package.read_bytes(name)
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise TypeError("operator_summary_package_bytes_invalid")
        content = memoryview(raw).tobytes()
        files[name] = content
        if not name.endswith(".json"):
            continue
        try:
            documents[name] = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            if name == "reports/operator_summary.json":
                raise ValueError(
                    "operator_summary_package_json_invalid"
                ) from error
            documents[name] = _INVALID_JSON

    summary = documents.get("reports/operator_summary.json")
    if not isinstance(summary, Mapping):
        raise ValueError("operator_summary_package_summary_missing")
    snapshot = _SnapshotPackageView(names_tuple, MappingProxyType(files))
    normalized = _replay_legacy_inputs(documents, snapshot)
    inputs = _inputs_from_normalized(
        normalized,
        package_label=_package_label(package),
        file_names=names_tuple,
        file_bytes=MappingProxyType(files),
        legacy_kwargs=normalized,
    )
    return _with_package_summary_parity(inputs, summary)


def replay_package_authority_inputs(
    package: PackageView,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Replay receipt and apply authority before the summary is projected."""

    documents: dict[str, Any] = {}
    for name in package.file_names():
        if not name.endswith(".json"):
            continue
        try:
            documents[name] = json.loads(
                package.read_bytes(name).decode("utf-8-sig")
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            documents[name] = _INVALID_JSON
    return _replay_package_authority(documents, package)


def thaw_operator_value(value: Any) -> Any:
    """Return a detached plain JSON-like working copy."""

    value_type = value.__class__
    if value_type is MappingProxyType or value_type is dict:
        return {
            key: thaw_operator_value(nested)
            for key, nested in value.items()
        }
    if value_type is tuple or value_type is list:
        return [thaw_operator_value(item) for item in value]
    if value_type is frozenset or value_type is set:
        return sorted(thaw_operator_value(item) for item in value)
    return value


def _inputs_from_normalized(
    normalized: Mapping[str, Any],
    *,
    package_label: str,
    file_names: tuple[str, ...],
    file_bytes: Mapping[str, bytes],
    legacy_kwargs: Mapping[str, Any],
) -> OperatorSummaryInputs:
    authority = _authority_from_raw_inputs(normalized)
    diagnostics = OperatorDiagnosticInputs(
        guide_source_depth=_mapping(
            normalized.get("guide_source_depth")
        ),
        unsupported_conditions=_mapping_rows(
            normalized.get("unsupported_conditions")
        ),
        globalvalue_authority=_mapping(
            normalized.get("globalvalue_authority")
        ),
        generated_files=tuple(
            str(value)
            for value in _sequence(normalized.get("generated_files"))
        ),
        claim_coverage_report=_mapping(
            normalized.get("claim_coverage_report")
        ),
        config_readiness_summary=_mapping(
            normalized.get("config_readiness_summary")
        ),
        config_readiness_report=_mapping(
            normalized.get("config_readiness_report")
        ),
        claim_conflict_report=_mapping(
            normalized.get("claim_conflict_report")
        ),
        mulligan_plan_report=_mapping(
            normalized.get("mulligan_plan_report")
        ),
        card_behavior_plan_report=_mapping(
            normalized.get("card_behavior_plan_report")
        ),
        combo_plan_report=_mapping(
            normalized.get("combo_plan_report")
        ),
        globalvalues_profile_report=_mapping(
            normalized.get("globalvalues_profile_report")
        ),
        semantic_enrichment_report=_mapping(
            normalized.get("semantic_enrichment_report")
        ),
        mechanic_drift_report=_mapping(
            normalized.get("mechanic_drift_report")
        ),
        source_claim_gap_report=_mapping(
            normalized.get("source_claim_gap_report")
        ),
        source_contract_audit_report=_mapping(
            normalized.get("source_contract_audit_report")
        ),
        source_to_runtime_explainability_report=_mapping(
            normalized.get("source_to_runtime_explainability_report")
        ),
        output_ownership_manifest=_mapping(
            normalized.get("output_ownership_manifest")
        ),
        gameplan_contract=_mapping(normalized.get("gameplan_contract")),
        runtime_surface_ledger=_mapping(
            normalized.get("runtime_surface_ledger")
        ),
        pre_run_closure_report=_mapping(
            normalized.get("pre_run_closure_report")
        ),
        reason_rows=_raw_diagnostic_reason_rows(normalized),
    )
    return OperatorSummaryInputs(
        deck_name=str(normalized.get("deck_name") or ""),
        deck_code=str(normalized.get("deck_code") or ""),
        package_label=package_label,
        authority=authority,
        diagnostics=diagnostics,
        legacy_kwargs=_freeze(legacy_kwargs),
        file_names=file_names,
        file_bytes=file_bytes,
    )


def _authority_from_raw_inputs(
    normalized: Mapping[str, Any],
) -> OperatorAuthorityInputs:
    technical = normalized.get("technical_validation")
    technical_report = (
        technical if isinstance(technical, Mapping) else {}
    )
    strict_report_valid = (
        technical_report.get("status") == "passed"
        and not technical_report.get("errors")
    )
    package_derivation = normalized.get("package_derivation")
    package_authority = normalized.get("package_authority")
    authority = (
        package_authority
        if isinstance(package_authority, Mapping)
        else {}
    )
    has_package_context = package_derivation is not None
    technical_valid = strict_report_valid
    if has_package_context:
        derivation = (
            package_derivation
            if isinstance(package_derivation, Mapping)
            else {}
        )
        receipt_sha256 = str(derivation.get("receipt_sha256", ""))
        technical_valid = (
            strict_report_valid
            and derivation_schema_version_supported(
                derivation.get("schema_version")
            )
            and derivation.get("receipt_path")
            == "package_derivation_receipt.json"
            and derivation.get("verified") is True
            and _sha256_value_valid(receipt_sha256)
            and package_authority_context_verified(authority)
            and authority.get("receipt_sha256") == receipt_sha256
        )
    strict_valid = (
        authority.get("strict_validation_passed") is True
        if has_package_context
        else technical_valid
    )
    deck_valid = (
        authority.get("deck_input_apply_eligible") is True
        if has_package_context
        else technical_valid
    )
    source_receipt_valid = (
        authority.get("source_authority_verified") is True
        if has_package_context
        else True
    )
    derivation_valid = (
        authority.get("derivation_receipt_verified") is True
        if has_package_context
        else technical_valid
    )
    source_eligible = (
        True
        if package_authority is None
        else authority.get("source_apply_eligible") is True
    )
    strategy_authority_mode = authority.get(
        "strategy_authority_mode",
        "source_contract",
    )
    if strategy_authority_mode not in {
        "source_contract",
        "llm_optimized_start",
    }:
        raise ValueError("strategy_authority_mode_invalid")
    optimized_start_derivation_validity = (
        authority.get("optimized_start_derivation_validity") is True
    )
    blocking_rows: list[Mapping[str, Any]] = []
    if not strict_report_valid:
        errors = technical_report.get("errors", [])
        error_rows = (
            errors
            if isinstance(errors, Sequence)
            and not isinstance(errors, (str, bytes, bytearray))
            else [errors]
        )
        if not error_rows:
            error_rows = ["technical_validation_failed"]
        blocking_rows.extend(
            {"reason": str(error)}
            for error in error_rows
        )
    elif not technical_valid:
        blocking_rows.append(
            {
                "reason": "technical_validation_failed",
                "code": "technical_validation_failed",
            }
        )
    if (
        strategy_authority_mode == "source_contract"
        and not source_eligible
    ):
        reasons = authority.get(
            "source_apply_eligibility_reasons",
            [],
        )
        reason_rows = (
            reasons
            if isinstance(reasons, Sequence)
            and not isinstance(reasons, (str, bytes, bytearray))
            else ()
        )
        blocking_rows.extend(
            {"reason": str(reason), "code": str(reason)}
            for reason in (
                reason_rows
                or ("diagnostic_source_not_apply_eligible",)
            )
        )
    return OperatorAuthorityInputs(
        technical_validation=_mapping(technical_report),
        package_derivation=_optional_mapping(package_derivation),
        package_authority=_optional_mapping(package_authority),
        deck_input_verification_report=_optional_mapping(
            normalized.get("deck_input_verification")
        ),
        strict_package_validation=strict_valid,
        actual_runtime_surface_inventory=technical_valid,
        deck_input_verification=deck_valid,
        source_receipt_validity=source_receipt_valid,
        source_acquisition_eligibility=source_eligible,
        derivation_receipt_validity=derivation_valid,
        package_summary_parity=True,
        strategy_authority_mode=strategy_authority_mode,
        optimized_start_derivation_validity=(
            optimized_start_derivation_validity
        ),
        blocking_reasons=_mapping_rows(blocking_rows),
    )


def _normalized_legacy_inputs(
    values: Mapping[str, Any],
) -> Mapping[str, Any]:
    normalized = dict(values)
    technical = normalized.get("technical_validation")
    if technical is None:
        technical = normalized.get("validation_report") or {
            "status": "unknown"
        }
    normalized["technical_validation"] = technical or {
        "status": "unknown"
    }
    guide = normalized.get("guide_source_depth")
    if guide is None:
        guide = normalized.get("guide_source_depth_report")
    normalized["guide_source_depth"] = guide
    readiness = normalized.get("config_readiness_summary")
    readiness_report = normalized.get("config_readiness_report")
    if readiness is None and isinstance(readiness_report, Mapping):
        readiness = readiness_report.get("summary", readiness_report)
    normalized["config_readiness_summary"] = readiness
    mulligan = normalized.get("mulligan_plan_report")
    if hasattr(mulligan, "to_report"):
        mulligan = mulligan.to_report()
    normalized["mulligan_plan_report"] = mulligan
    return MappingProxyType(normalized)


def _detach_legacy_inputs(
    values: Mapping[str, Any],
) -> dict[str, Any]:
    detached = {
        str(key): _detach(value)
        for key, value in values.items()
        if key != "mulligan_plan_report"
    }
    mulligan = values.get("mulligan_plan_report")
    if hasattr(mulligan, "to_report"):
        detached["mulligan_plan_report"] = _detach(mulligan.to_report())
    else:
        detached["mulligan_plan_report"] = _detach(mulligan)
    return detached


def _replay_legacy_inputs(
    documents: Mapping[str, Any],
    package: PackageView,
) -> Mapping[str, Any]:
    def document(relative_path: str) -> Any:
        value = documents.get(relative_path, {})
        return value if isinstance(value, Mapping) else {}

    manifest = document("reports/input_manifest.json")
    guide_bundle = document("reports/guide_claim_bundle.json")
    readiness = document(
        "reports/per_card_config_readiness_report.json"
    )
    mulligan = document("reports/mulligan_plan_report.json")
    ownership = document("reports/output_ownership_manifest.json")
    generated_files = [
        str(row.get("file", "")).replace("/", "\\")
        for row in _sequence(ownership.get("files"))
        if isinstance(row, Mapping) and str(row.get("file", ""))
    ]
    package_derivation, package_authority = _replay_package_authority(
        documents,
        package,
    )
    return _normalized_legacy_inputs(
        {
            "deck_name": (
                manifest.get("deck_name", "")
            ),
            "deck_code": manifest.get("deck_code", ""),
            "technical_validation": document(
                "reports/validation_report.json"
            ),
            "guide_source_depth": document(
                "reports/guide_source_depth_report.json"
            ),
            "unsupported_conditions": mulligan.get(
                "suppressed_rules", []
            ),
            "globalvalue_authority": document(
                "reports/global_values_authority_matrix.json"
            ),
            "generated_files": generated_files,
            "claim_coverage_report": guide_bundle.get(
                "claim_coverage_report",
                guide_bundle.get("coverage", {}),
            ),
            "config_readiness_summary": readiness.get("summary", {}),
            "config_readiness_report": readiness,
            "claim_conflict_report": document(
                "reports/claim_conflict_report.json"
            )
            or guide_bundle.get("claim_conflict_report", {}),
            "mulligan_plan_report": mulligan,
            "card_behavior_plan_report": document(
                "reports/card_behavior_plan_report.json"
            ),
            "combo_plan_report": document(
                "reports/combo_plan_report.json"
            ),
            "globalvalues_profile_report": document(
                "reports/globalvalues_profile.json"
            ),
            "semantic_enrichment_report": document(
                "reports/semantic_enrichment_report.json"
            ),
            "mechanic_drift_report": document(
                "reports/mechanic_drift_report.json"
            ),
            "source_claim_gap_report": document(
                "reports/source_claim_gap_report.json"
            ),
            "source_contract_audit_report": document(
                "reports/source_contract_audit.json"
            ),
            "source_to_runtime_explainability_report": document(
                "reports/source_to_runtime_explainability.json"
            ),
            "output_ownership_manifest": ownership,
            "gameplan_contract": document(
                "reports/gameplan_contract.json"
            ),
            "package_derivation": package_derivation,
            "package_authority": package_authority,
            "deck_input_verification": manifest.get(
                "deck_input_verification"
            ),
            "runtime_surface_ledger": document(
                "reports/runtime_surface_ledger.json"
            ),
            "pre_run_closure_report": document(
                "reports/pre_run_closure.json"
            )
            if "reports/pre_run_closure.json" in documents
            else None,
        }
    )


def _with_package_summary_parity(
    inputs: OperatorSummaryInputs,
    stored_summary: Mapping[str, Any],
) -> OperatorSummaryInputs:
    from hsconfig.operator_summary import _evaluate_operator_summary_inputs

    expected = _evaluate_operator_summary_inputs(inputs)
    status_keys = (
        "technical_status",
        "semantic_status",
        "next_action",
        "apply_policy",
        "runtime_load_safe",
        "runtime_apply_mode",
        "runtime_apply_allowed",
        "runtime_apply_reason",
        "runtime_apply_requires_flag",
        "load_safe_to_install",
        "use_config_now",
        "use_config_now_scope",
    )
    if inputs.authority.strategy_authority_mode == "llm_optimized_start":
        status_keys = (
            *status_keys,
            "strategy_authority_mode",
            "optimized_start_derivation_validity",
        )
    parity = all(
        stored_summary.get(key) == expected.get(key)
        for key in status_keys
    )
    return replace(
        inputs,
        authority=replace(
            inputs.authority,
            package_summary_parity=parity,
        ),
    )


def _replay_package_authority(
    documents: Mapping[str, Any],
    package: PackageView,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    manifest = documents.get("reports/input_manifest.json")
    configuration_mode = configuration_mode_from_manifest(manifest)
    strategy_authority_mode = (
        "llm_optimized_start"
        if configuration_mode == LLM_OPTIMIZED_START
        else "source_contract"
    )
    receipt_present = "package_derivation_receipt.json" in documents
    receipt = documents.get("package_derivation_receipt.json")
    if not isinstance(receipt, Mapping):
        reason = (
            "package_derivation_receipt_missing"
            if not receipt_present
            else "package_derivation_receipt_invalid"
        )
        return (
            {
                "schema_version": None,
                "receipt_path": "package_derivation_receipt.json",
                "receipt_sha256": "",
                "verified": False,
            },
            {
                "strict_validation_passed": False,
                "deck_input_apply_eligible": False,
                "source_authority_verified": False,
                "canonical_receipt_count": 0,
                "exact_source_closed": False,
                "source_apply_eligible": False,
                "source_apply_eligibility_reasons": [reason],
                "derivation_receipt_verified": False,
                "strategy_authority_mode": strategy_authority_mode,
                "optimized_start_derivation_validity": False,
                "receipt_sha256": "",
            },
        )
    receipt_verified, _reasons = verify_package_derivation_receipt_from_view(
        package,
        receipt,
    )
    receipt_sha256 = package_derivation_receipt_sha256(receipt)
    guide_bundle = documents.get("reports/guide_claim_bundle.json")
    if not isinstance(guide_bundle, Mapping):
        guide_bundle = {}
    deck_identity = documents.get("reports/deck_identity.json")
    if not isinstance(deck_identity, Mapping):
        deck_identity = {}
    receipts = guide_bundle.get(
        "canonical_source_receipts",
        guide_bundle.get("globalvalues_source_receipts", []),
    )
    canonical_receipt_count = (
        len(receipts) if isinstance(receipts, list) else 0
    )
    source_authority_reasons = canonical_source_receipt_reasons(
        bundle=guide_bundle,
        deck_identity=deck_identity,
    )
    source_apply_eligible = _source_provenance_verified(guide_bundle)
    validation = documents.get("reports/validation_report.json")
    strict_valid = (
        isinstance(validation, Mapping)
        and validation.get("status") == "passed"
        and not validation.get("errors")
    )
    verification = (
        manifest.get("deck_input_verification")
        if isinstance(manifest, Mapping)
        else None
    )
    deck_valid = (
        isinstance(verification, Mapping)
        and verification.get("runtime_apply_eligible") is True
    )
    package_derivation = {
        "schema_version": receipt.get("schema_version"),
        "receipt_path": "package_derivation_receipt.json",
        "receipt_sha256": receipt_sha256,
        "verified": receipt_verified,
    }
    package_authority = {
        "strict_validation_passed": strict_valid,
        "deck_input_apply_eligible": deck_valid,
        "source_authority_verified": not source_authority_reasons,
        "canonical_receipt_count": canonical_receipt_count,
        "exact_source_closed": (
            canonical_receipt_count > 0 and not source_authority_reasons
        ),
        "source_apply_eligible": source_apply_eligible,
        "source_apply_eligibility_reasons": (
            []
            if source_apply_eligible
            else ["diagnostic_source_not_apply_eligible"]
        ),
        "derivation_receipt_verified": receipt_verified,
        "strategy_authority_mode": strategy_authority_mode,
        "optimized_start_derivation_validity": (
            strategy_authority_mode == "llm_optimized_start"
            and receipt_verified
            and receipt.get("schema_version")
            == OPTIMIZED_DERIVATION_RECEIPT_SCHEMA_VERSION
        ),
        "receipt_sha256": receipt_sha256,
    }
    return package_derivation, package_authority


def _source_provenance_verified(bundle: Mapping[str, Any]) -> bool:
    for rows in (
        bundle.get("claims", []),
        bundle.get("source_evidence_index", []),
    ):
        for row in _sequence(rows):
            if (
                isinstance(row, Mapping)
                and "acquisition_provenance" in row
                and not strategic_source_provenance_is_verified(
                    row.get("acquisition_provenance")
                )
            ):
                return False
    return True


def _raw_diagnostic_reason_rows(
    normalized: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    for value in _sequence(normalized.get("unsupported_conditions")):
        if not isinstance(value, Mapping):
            continue
        reason = str(value.get("reason") or "unsupported_condition")
        rows.append(
            {
                "reason_code": reason,
                "source": "unsupported_conditions",
                "gate_impact": "diagnostic_only",
                "apply_blocking": False,
                "details": dict(value),
            }
        )
    mechanic = normalized.get("mechanic_drift_report")
    if isinstance(mechanic, Mapping):
        for reason in _sequence(mechanic.get("unknown_mechanics")):
            rows.append(
                {
                    "reason_code": f"unknown_mechanic:{reason}",
                    "source": "mechanic_drift_report",
                    "gate_impact": "diagnostic_only",
                    "apply_blocking": False,
                    "details": {"mechanic": str(reason)},
                }
            )
    return tuple(
        _freeze(row)
        for row in sorted(
            rows,
            key=lambda row: (
                str(row["reason_code"]),
                str(row["source"]),
            ),
        )
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return _freeze(value) if isinstance(value, Mapping) else MappingProxyType({})


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    return _freeze(value) if isinstance(value, Mapping) else None


def _mapping_rows(value: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        _freeze(row)
        for row in _sequence(value)
        if isinstance(row, Mapping)
    )


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze(nested)
                for key, nested in value.items()
            }
        )
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    if value is None or type(value) in (bool, int, float, str, bytes):
        return value
    raise TypeError("operator_summary_input_value_unsupported")


def _detach(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _detach(nested)
            for key, nested in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_detach(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return {_detach(item) for item in value}
    if isinstance(value, bytearray):
        return bytes(value)
    if value is None or type(value) in (bool, int, float, str, bytes):
        return value
    raise TypeError("operator_summary_input_value_unsupported")


def _package_label(package: PackageView) -> str:
    root = getattr(package, "root", _MISSING)
    if root is not _MISSING:
        return str(root)
    return f"{package.__class__.__module__}.{package.__class__.__qualname__}"


def _sha256_value_valid(value: str) -> bool:
    return (
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


__all__ = (
    "OperatorAuthorityInputs",
    "OperatorDiagnosticInputs",
    "OperatorSummaryInputs",
    "freeze_operator_summary_inputs",
    "load_operator_summary_inputs",
    "replay_package_authority_inputs",
)
