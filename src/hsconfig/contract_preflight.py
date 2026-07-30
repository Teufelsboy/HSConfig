from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess
from typing import Any

from hsconfig.skill_sync_status import build_installed_skill_sync_status
from hsconfig.visionai_registry import NORMAL_APPLY_AUTHORITY


REQUIRED_REFERENCE_FILES = (
    "references/workflow.md",
    "references/visionai-surfaces.md",
    "references/guide-research-policy.md",
    "references/globalvalues-policy.md",
    "references/card-behavior-policy.md",
    "references/contract-compiler-checklist.md",
)

EXPECTED_CHECK_KEYS = (
    "repo_current",
    "skill_root_present",
    "installed_skill_sync_current",
    "reference_files_present",
    "checklist_referenced_by_normal_workflow",
    "checklist_listed_in_references",
    "skill_thin_router_visible",
    "configure_acceptance_route_visible",
    "pre_run_config_contract_receipt_visible",
    "configure_acceptance_projection_not_gate_visible",
    "config_quality_summary_diagnostic_only_visible",
    "config_proof_summary_visible",
    "operator_summary_single_authority_visible",
    "source_status_nonblocking_visible",
    "source_candidate_plan_visible",
    "source_readiness_preview_visible",
    "no_default_only_visible",
    "runtime_surface_boundary_visible",
    "darkbishop_effect_not_mulligan_visible",
    "negative_scope_visible",
    "diagnostic_only_visible",
    "research_current_truth_index_visible",
    "research_result_contract_sentinel_visible",
    "historical_research_outlines_diagnostic_only",
)


@dataclass(frozen=True)
class GitPreflight:
    branch: str
    upstream: str | None
    dirty: bool
    ahead_origin_main: int
    behind_origin_main: int
    clean_for_runtime_work: bool
    ahead_upstream: int | None = None
    behind_upstream: int | None = None
    origin_main_error: str | None = None


@dataclass(frozen=True)
class ResearchContextPreflight:
    status: str
    active_evidence_index_present: bool
    active_evidence_index_path: str
    machine_evidence_index_present: bool
    machine_evidence_index_path: str
    authority: str
    operator_gate_impact: str
    normal_apply_authority: str
    recommended_research_entrypoint: str
    historical_outline_count: int
    historical_outline_paths: tuple[str, ...]
    historical_outlines_apply_authority: bool
    latest_research_result_contract_status: str
    latest_research_result_contract_path: str
    latest_research_result_contract_result_count: int
    latest_research_result_contract_invalid_count: int
    latest_research_result_contract_strict_invalid_count: int
    latest_research_result_contract_contract_invalid_count: int
    latest_research_result_contract_seed_only_count: int
    latest_research_result_contract_strong_promoting_count: int
    latest_research_result_contract_promotion_ready_deck_count: int
    latest_research_result_contract_non_promoting_count: int
    latest_research_result_contract_first_non_promoting_result: str
    latest_research_result_contract_first_non_promoting_action: str
    latest_research_result_contract_first_non_promoting_reason: str
    latest_research_result_contract_freshness_missing_count: int
    latest_research_result_contract_no_op_validation_risk: bool
    source_status_apply_blocking: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class PackageContractPreflight:
    status: str
    package: str
    present: bool
    authority: str
    validation_status: str
    validation_errors: list[str]
    validation_checked_files: int
    config_quality_status: str
    config_quality_problem_count: int
    config_quality_first_problem: dict[str, Any] | None
    ready_to_use_from_operator_summary: bool
    observed_operator_source_status_apply_blocking: bool
    observed_default_only_runtime_surfaces: list[str]
    next_report_to_open: str
    runtime_apply_authority: str
    source_status_apply_blocking: bool
    apply_blocking: bool
    runtime_write_performed: bool
    notes: tuple[str, ...]
    technical_status: str
    semantic_status: str
    runtime_apply_mode: str
    runtime_apply_allowed: bool
    load_safe_to_install: bool
    use_config_now: bool
    use_config_now_scope: str
    semantic_handoff_status: str
    semantic_handoff_reasons: list[str]
    default_only_runtime_surfaces: list[str]
    validate_config_package_status: str
    validate_config_package_errors: list[str]
    checked_runtime_files: int
    config_intent_self_audit_status: str
    config_intent_first_attention: str | None
    surface_intent_status: str
    surface_intent_present: bool
    surface_intent_surface_count: int
    surface_intent_fallback_intent_rows: int
    surface_intent_legacy_policy_surface_rows: list[str]
    surface_intent_first_attention: str | None
    closure_schema_current: bool
    cards_missing_closure: int
    package_contract_current: bool
    failures: list[str]


def _run_git(
    repo_root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _parse_counts(text: str) -> tuple[int, int]:
    parts = text.replace("\t", " ").split()
    if len(parts) < 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def _parse_status(text: str) -> tuple[str, bool]:
    lines = [line for line in text.splitlines() if line.strip()]
    branch_line = lines[0] if lines else "## unknown"
    branch = branch_line.removeprefix("## ").split("...")[0].strip()
    dirty = any(not line.startswith("## ") for line in lines)
    return branch, dirty


def build_git_preflight(repo_root: str | Path) -> GitPreflight:
    root = Path(repo_root)
    if not root.exists():
        return GitPreflight(
            branch="unknown",
            upstream=None,
            dirty=False,
            ahead_origin_main=0,
            behind_origin_main=0,
            clean_for_runtime_work=False,
            ahead_upstream=None,
            behind_upstream=None,
            origin_main_error=f"repo root does not exist: {root.resolve()}",
        )

    status_result = _run_git(root, "status", "--short", "--branch", check=False)
    if status_result.returncode != 0:
        error = (
            status_result.stderr.strip()
            or status_result.stdout.strip()
            or f"git status exited with status {status_result.returncode}"
        )
        return GitPreflight(
            branch="unknown",
            upstream=None,
            dirty=False,
            ahead_origin_main=0,
            behind_origin_main=0,
            clean_for_runtime_work=False,
            ahead_upstream=None,
            behind_upstream=None,
            origin_main_error=error,
        )

    status = status_result.stdout
    branch, dirty = _parse_status(status)

    upstream_result = _run_git(
        root,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
        check=False,
    )
    upstream = upstream_result.stdout.strip() or None

    origin_main_result = _run_git(
        root,
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main",
        check=False,
    )
    origin_main_error: str | None = None
    if origin_main_result.returncode == 0:
        try:
            ahead_origin_main, behind_origin_main = _parse_counts(
                origin_main_result.stdout
            )
        except ValueError as exc:
            ahead_origin_main, behind_origin_main = 0, 0
            origin_main_error = f"invalid origin/main count output: {exc}"
    else:
        ahead_origin_main, behind_origin_main = 0, 0
        origin_main_error = (
            origin_main_result.stderr.strip()
            or origin_main_result.stdout.strip()
            or f"git rev-list exited with status {origin_main_result.returncode}"
        )

    ahead_upstream: int | None = None
    behind_upstream: int | None = None
    if upstream:
        upstream_result = _run_git(
            root,
            "rev-list",
            "--left-right",
            "--count",
            f"HEAD...{upstream}",
            check=False,
        )
        ahead_upstream, behind_upstream = _parse_counts(upstream_result.stdout)

    return GitPreflight(
        branch=branch,
        upstream=upstream,
        dirty=dirty,
        ahead_origin_main=ahead_origin_main,
        behind_origin_main=behind_origin_main,
        clean_for_runtime_work=(
            not dirty and origin_main_error is None and behind_origin_main == 0
        ),
        ahead_upstream=ahead_upstream,
        behind_upstream=behind_upstream,
        origin_main_error=origin_main_error,
    )


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_items(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _first_problem(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    return dict(first) if isinstance(first, Mapping) else {"value": str(first)}


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _surface_intent_contract_receipt(
    surface_intent: Mapping[str, Any],
) -> dict[str, Any]:
    fallback_rows = [
        row
        for row in surface_intent.get("fallback_intent_rows", [])
        if isinstance(row, Mapping)
    ]
    legacy_policy_rows = [
        row
        for row in surface_intent.get("legacy_policy_surface_rows", [])
        if isinstance(row, Mapping)
    ]
    first_attention_value = surface_intent.get("first_attention")
    return {
        "surface_intent_status": str(surface_intent.get("status") or "missing"),
        "surface_intent_present": bool(surface_intent.get("present", False)),
        "surface_intent_surface_count": _int_value(
            surface_intent.get("surface_count", 0)
        ),
        "surface_intent_fallback_intent_rows": len(fallback_rows),
        "surface_intent_legacy_policy_surface_rows": [
            str(row.get("surface"))
            for row in legacy_policy_rows
            if str(row.get("surface") or "")
        ],
        "surface_intent_first_attention": (
            str(first_attention_value) if first_attention_value else None
        ),
    }


def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _references_line(skill_text: str) -> str:
    lines = skill_text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("## References:"):
            block = [line]
            for following in lines[index + 1 :]:
                if following.startswith("## "):
                    break
                if following.strip():
                    block.append(following)
            return "\n".join(block)
    return ""


def _skill_thin_router_visible(skill_text: str) -> bool:
    lines = [line.rstrip() for line in skill_text.splitlines() if line.strip()]
    return (
        len(lines) <= 70
        and all(len(line) <= 220 for line in lines)
        and skill_text.count("## References:") == 1
        and "docs/operator/README.md" in skill_text
        and all(
            relative_path in skill_text
            for relative_path in REQUIRED_REFERENCE_FILES
        )
        and "`reports/operator_summary.json` remains the only normal apply authority."
        in skill_text
        and "`source_status_apply_blocking` must remain `false`" in skill_text
    )


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _configure_acceptance_route_visible(combined: str) -> bool:
    return all(
        term in combined
        for term in (
            "<out>/configure_summary.json.acceptance_summary",
            "acceptance_summary",
            "use_config_now",
            "technical_status",
            "runtime_apply_allowed",
            "source_strength",
            "default_only_clean",
            "next_report_to_open",
            "<out>/configure_summary.json.config_quality_summary",
            "config_quality_summary",
            NORMAL_APPLY_AUTHORITY,
        )
    )


def _pre_run_config_contract_receipt_visible(combined: str) -> bool:
    return all(
        term in combined
        for term in (
            "pre-run config contract receipt",
            "configure_summary.json.handoff_contract",
            "diagnostic-only handoff proof",
            "single authority",
            "no-default-only status",
            "forbidden-surface status",
            "source-to-runtime trace status",
            "Darkbishop boundary",
            "does not replace `reports/operator_summary.json`",
            "operator_summary.json remains the only normal apply authority",
        )
    )


def _configure_acceptance_projection_not_gate_visible(combined: str) -> bool:
    return (
        "operator projection" in combined
        and _has_any(
            combined,
            (
                "does not replace `reports/operator_summary.json` as apply authority",
                "does not replace `reports/operator_summary.json`",
                "does not replace `operator_summary.json`",
            ),
        )
        and _has_any(
            combined,
            (
                "operator_summary.json remains the only normal apply authority",
                "operator_summary.json` remains the only normal apply authority",
                "operator_summary.json` remains the normal apply authority",
                "reports/operator_summary.json` as the apply authority",
            ),
        )
    )


def _config_quality_summary_diagnostic_only_visible(combined: str) -> bool:
    return (
        "<out>/configure_summary.json.config_quality_summary" in combined
        and "config_quality_summary" in combined
        and "diagnostic-only" in combined
        and "non-blocking" in combined
        and "contract-doctor" in combined
        and _has_any(
            combined,
            (
                "operator_summary.json remains the only normal apply authority",
                "operator_summary.json` remains the only normal apply authority",
                "operator_summary.json` remains the normal apply authority",
            ),
        )
    )


def _config_proof_summary_visible(combined: str) -> bool:
    return (
        "config_proof_summary" in combined
        and "diagnostic-only config proof" in combined
        and "not another apply gate" in combined
    )


def _source_candidate_plan_contract_visible(
    operator_text: str,
    source_builder_workflow_text: str,
    source_candidate_plan_text: str,
) -> bool:
    operator_terms = (
        "source-candidate plan visibility",
        "source_candidate_plan.json",
        "does not replace `reports/operator_summary.json`",
    )
    workflow_terms = (
        "Queries are for Codex/operator research only",
        "The plan cannot promote, block apply, write runtime config, "
        "or replace `reports/operator_summary.json`.",
    )
    implementation_terms = (
        '"authority": "diagnostic_source_candidate_plan"',
        '"apply_blocking": False',
        '"runtime_write_performed": False',
        '"source_status_apply_blocking": False',
        '"candidate_plan_can_promote": False',
        '"candidate_plan_can_block_apply": False',
        '"normal_apply_authority": _NORMAL_APPLY_AUTHORITY',
    )
    return (
        all(term in operator_text for term in operator_terms)
        and _has_any(
            source_builder_workflow_text,
            (
                "source_candidate_plan.json is deterministic pre-acquisition guidance",
                "`source_candidate_plan.json` is deterministic pre-acquisition guidance",
            ),
        )
        and all(term in source_builder_workflow_text for term in workflow_terms)
        and all(term in source_candidate_plan_text for term in implementation_terms)
    )


def _source_candidate_plan_contract_payload(visible: bool) -> dict[str, object]:
    return {
        "status": "visible" if visible else "attention",
        "authority": "diagnostic_source_candidate_plan",
        "documentation_path": "docs/operator/source-builder-workflow.md",
        "operator_entrypoint_path": "docs/operator/README.md",
        "implementation_path": "src/hsconfig/source_candidate_plan.py",
        "runtime_apply_authority": NORMAL_APPLY_AUTHORITY,
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "candidate_plan_can_promote": False,
        "candidate_plan_can_block_apply": False,
        "normal_path": (
            "source-manifest -> configure --online-source -> "
            "source-acquire/source-autopilot -> prepare"
        ),
        "notes": [
            "source_candidate_plan.json is acquisition guidance only.",
            "Candidate plans cannot promote or block runtime apply.",
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }


def _source_readiness_preview_visible(
    source_readiness_preview_text: str,
    configure_workflow_text: str,
    source_autopilot_text: str,
    operator_text: str,
    workflow_text: str,
) -> bool:
    docs_terms = (
        "source_readiness_preview",
        "diagnostic-only",
        "does not replace `reports/operator_summary.json`",
    )
    implementation_terms = (
        "diagnostic_source_readiness_preview",
        '_NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"',
        '"diagnostic_only": True',
        '"runtime_apply_authority": _NORMAL_APPLY_AUTHORITY',
        '"apply_blocking": False',
        '"runtime_write_performed": False',
        '"source_status_apply_blocking": False',
        '"readiness_lane": readiness_lane',
        '"default_only_evaluated": default_only_evaluated',
        '"default_only_runtime_surface_status": default_only_runtime_surface_status',
        'return "default_only_runtime_surface_no_block"',
        'return "runtime_surface_not_evaluated_no_block"',
        "replace_default_only_runtime_surface_with_source_or_policy_claim",
    )
    autopilot_terms = (
        "build_source_readiness_preview",
        'report["source_readiness_preview"]',
    )
    configure_terms = (
        "build_source_readiness_preview",
        '"source_readiness_preview": source_readiness_preview',
    )
    forbidden_producer_terms = (
        "source_readiness_preview_apply_authority",
        "source_readiness_preview_apply_blocking",
        "source_readiness_preview_runtime_write",
    )
    return (
        all(term in operator_text for term in docs_terms)
        and all(term in workflow_text for term in docs_terms)
        and all(term in source_readiness_preview_text for term in implementation_terms)
        and all(term in source_autopilot_text for term in autopilot_terms)
        and all(term in configure_workflow_text for term in configure_terms)
        and not any(
            term in source_autopilot_text or term in configure_workflow_text
            for term in forbidden_producer_terms
        )
    )


def _source_readiness_preview_contract_payload(visible: bool) -> dict[str, object]:
    return {
        "status": "visible" if visible else "attention",
        "authority": "diagnostic_source_readiness_preview",
        "documentation_paths": [
            "docs/operator/source-builder-workflow.md",
            ".agents/skills/hsconfig/references/workflow.md",
        ],
        "implementation_path": "src/hsconfig/source_readiness_preview.py",
        "configure_summary_field": "source_readiness_preview",
        "autopilot_report_field": "source_readiness_preview",
        "producer_paths": [
            "src/hsconfig/source_autopilot.py",
            "src/hsconfig/configure_workflow.py",
        ],
        "runtime_apply_authority": NORMAL_APPLY_AUTHORITY,
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "notes": [
            (
                "Source readiness preview summarizes candidate, autopilot, "
                "and operator source readiness."
            ),
            (
                "Source readiness preview cannot promote SOURCE_BACKED_STRONG, "
                "block apply, apply runtime files, or write runtime config."
            ),
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }


def build_package_contract_preflight(package: str | Path | None) -> dict[str, Any] | None:
    if package is None:
        return None

    package_path = Path(package)
    normal_authority = NORMAL_APPLY_AUTHORITY
    base_notes = (
        "Package contract preflight is diagnostic only.",
        "reports/operator_summary.json remains the only normal apply authority.",
    )
    if not package_path.is_dir():
        validation_errors = [f"{package_path}: package directory not found"]
        failures = ["package_missing"]
        return asdict(
            PackageContractPreflight(
                status="attention",
                package=str(package_path),
                present=False,
                authority="diagnostic_only",
                validation_status="failed",
                validation_errors=validation_errors,
                validation_checked_files=0,
                config_quality_status="attention",
                config_quality_problem_count=1,
                config_quality_first_problem={
                    "check": "package_missing",
                    "value": str(package_path),
                },
                ready_to_use_from_operator_summary=False,
                observed_operator_source_status_apply_blocking=False,
                observed_default_only_runtime_surfaces=[],
                next_report_to_open=normal_authority,
                runtime_apply_authority=normal_authority,
                source_status_apply_blocking=False,
                apply_blocking=False,
                runtime_write_performed=False,
                notes=base_notes + ("Package directory is missing.",),
                technical_status="",
                semantic_status="",
                runtime_apply_mode="",
                runtime_apply_allowed=False,
                load_safe_to_install=False,
                use_config_now=False,
                use_config_now_scope="load_safety_only",
                semantic_handoff_status="insufficient_evidence",
                semantic_handoff_reasons=["package_missing"],
                default_only_runtime_surfaces=[],
                validate_config_package_status="failed",
                validate_config_package_errors=validation_errors,
                checked_runtime_files=0,
                config_intent_self_audit_status="missing",
                config_intent_first_attention="package_missing",
                surface_intent_status="missing",
                surface_intent_present=False,
                surface_intent_surface_count=0,
                surface_intent_fallback_intent_rows=0,
                surface_intent_legacy_policy_surface_rows=[],
                surface_intent_first_attention="package_missing",
                closure_schema_current=False,
                cards_missing_closure=0,
                package_contract_current=False,
                failures=failures,
            )
        )

    from hsconfig.config_quality_contract import (
        build_config_quality_report,
        semantic_handoff_projection,
    )
    from hsconfig.strict_package_validation import validate_complete_package

    operator = _as_mapping(_read_json(package_path / normal_authority))
    try:
        validation = validate_complete_package(package_path)
    except Exception as exc:
        validation = {
            "status": "failed",
            "errors": [f"strict package validation raised {type(exc).__name__}: {exc}"],
            "checked_files": 0,
        }
    try:
        quality = build_config_quality_report(package_path)
    except Exception as exc:
        quality = {
            "status": "attention",
            "checks": {},
            "problems": [
                {
                    "check": "config_quality_exception",
                    "value": f"{type(exc).__name__}: {exc}",
                }
            ],
        }

    quality_checks = _as_mapping(quality.get("checks"))
    operator_quality = _as_mapping(quality_checks.get("operator_summary"))
    closure = _as_mapping(quality_checks.get("closure_freshness"))
    config_intent = _as_mapping(quality_checks.get("config_intent_self_audit"))
    surface_intent_receipt = _surface_intent_contract_receipt(
        _as_mapping(quality_checks.get("surface_intent_projection"))
    )
    quality_problems = quality.get("problems", [])

    runtime_contract = _as_mapping(operator.get("runtime_apply_contract"))
    runtime_apply_authority = str(
        runtime_contract.get("apply_authority") or normal_authority
    )
    raw_runtime_apply_allowed = operator.get("runtime_apply_allowed", False)
    runtime_apply_allowed = raw_runtime_apply_allowed is True
    runtime_apply_mode = str(operator.get("runtime_apply_mode", ""))
    technical_status = str(operator.get("technical_status", ""))
    semantic_status = str(operator.get("semantic_status", ""))
    observed_source_blocking = bool(
        operator_quality.get(
            "source_status_apply_blocking",
            operator.get("source_status_apply_blocking", False),
        )
    )
    default_only = _string_items(
        operator_quality.get(
            "default_only_runtime_surfaces",
            operator.get("default_only_runtime_surfaces", []),
        )
    )

    validation_status = str(validation.get("status", "failed"))
    validation_errors = _string_items(validation.get("errors", []))
    validation_checked_files = _int_value(validation.get("checked_files", 0))
    config_quality_status = str(quality.get("status", "attention"))
    config_quality_problem_count = (
        len(quality_problems) if isinstance(quality_problems, list) else 0
    )
    config_intent_status = str(config_intent.get("status", "missing"))
    config_intent_first_attention_value = config_intent.get("first_attention")
    config_intent_first_attention = (
        str(config_intent_first_attention_value)
        if config_intent_first_attention_value
        else None
    )
    closure_schema_current = bool(closure.get("closure_schema_current", False))
    cards_missing_closure = _int_value(closure.get("cards_missing_closure", 0))
    semantic_handoff = semantic_handoff_projection(quality)
    load_safe_to_install = (
        technical_status == "VALID_PACKAGE"
        and runtime_apply_allowed is True
        and runtime_apply_mode == "load_safe_apply"
        and validation_status == "passed"
    )

    ready_to_use = (
        technical_status == "VALID_PACKAGE"
        and runtime_apply_mode == "load_safe_apply"
        and runtime_apply_allowed is True
        and runtime_apply_authority == normal_authority
    )

    failures: list[str] = []
    if validation_status != "passed":
        failures.append("validate_config_package_failed")
    if config_quality_status != "clean":
        failures.append("config_quality_attention")
    if technical_status != "VALID_PACKAGE":
        failures.append("technical_status_not_valid_package")
    if runtime_apply_mode != "load_safe_apply":
        failures.append("runtime_apply_mode_not_load_safe_apply")
    if raw_runtime_apply_allowed is not True:
        failures.append("runtime_apply_allowed_not_true")
    if runtime_apply_authority != normal_authority:
        failures.append("runtime_apply_authority_not_operator_summary")
    if observed_source_blocking:
        failures.append("observed_operator_source_status_apply_blocking_true")
    if default_only:
        failures.append("default_only_runtime_surfaces_present")
    if config_intent_status != "clean":
        failures.append("config_intent_self_audit_attention")
    if closure_schema_current is not True:
        failures.append("closure_schema_not_current")
    if cards_missing_closure:
        failures.append("cards_missing_closure")

    package_contract_current = not failures
    next_report = (
        normal_authority if package_contract_current else "reports/contract_doctor.json"
    )
    notes = base_notes
    if not operator:
        notes += ("operator_summary.json is missing or invalid.",)
    if default_only:
        notes += ("Default-only runtime surfaces require operator attention.",)

    return asdict(
        PackageContractPreflight(
            status="clean" if package_contract_current else "attention",
            package=str(package_path),
            present=True,
            authority="diagnostic_only",
            validation_status=validation_status,
            validation_errors=validation_errors,
            validation_checked_files=validation_checked_files,
            config_quality_status=config_quality_status,
            config_quality_problem_count=config_quality_problem_count,
            config_quality_first_problem=_first_problem(quality_problems),
            ready_to_use_from_operator_summary=ready_to_use,
            observed_operator_source_status_apply_blocking=observed_source_blocking,
            observed_default_only_runtime_surfaces=default_only,
            next_report_to_open=next_report,
            runtime_apply_authority=runtime_apply_authority,
            source_status_apply_blocking=False,
            apply_blocking=False,
            runtime_write_performed=False,
            notes=notes,
            technical_status=technical_status,
            semantic_status=semantic_status,
            runtime_apply_mode=runtime_apply_mode,
            runtime_apply_allowed=runtime_apply_allowed,
            load_safe_to_install=load_safe_to_install,
            use_config_now=load_safe_to_install,
            use_config_now_scope="load_safety_only",
            semantic_handoff_status=semantic_handoff["semantic_handoff_status"],
            semantic_handoff_reasons=semantic_handoff[
                "semantic_handoff_reasons"
            ],
            default_only_runtime_surfaces=default_only,
            validate_config_package_status=validation_status,
            validate_config_package_errors=validation_errors,
            checked_runtime_files=validation_checked_files,
            config_intent_self_audit_status=config_intent_status,
            config_intent_first_attention=config_intent_first_attention,
            surface_intent_status=surface_intent_receipt["surface_intent_status"],
            surface_intent_present=surface_intent_receipt["surface_intent_present"],
            surface_intent_surface_count=surface_intent_receipt[
                "surface_intent_surface_count"
            ],
            surface_intent_fallback_intent_rows=surface_intent_receipt[
                "surface_intent_fallback_intent_rows"
            ],
            surface_intent_legacy_policy_surface_rows=surface_intent_receipt[
                "surface_intent_legacy_policy_surface_rows"
            ],
            surface_intent_first_attention=surface_intent_receipt[
                "surface_intent_first_attention"
            ],
            closure_schema_current=closure_schema_current,
            cards_missing_closure=cards_missing_closure,
            package_contract_current=package_contract_current,
            failures=failures,
        )
    )


def _latest_research_result_contract(root: Path) -> dict[str, object]:
    research_root = root / "docs" / "research"
    if not research_root.is_dir():
        return {
            "status": "not_found",
            "path": "",
            "result_count": 0,
            "invalid_count": 0,
            "strict_invalid_count": 0,
            "contract_invalid_count": 0,
            "seed_only_count": 0,
            "strong_promoting_count": 0,
            "promotion_ready_deck_count": 0,
            "non_promoting_count": 0,
            "first_non_promoting_result": "",
            "first_non_promoting_action": "none",
            "first_non_promoting_reason": "none",
            "freshness_missing_count": 0,
            "no_op_validation_risk": False,
        }

    candidates = sorted(path for path in research_root.iterdir() if path.is_dir())
    if not candidates:
        return {
            "status": "not_found",
            "path": "",
            "result_count": 0,
            "invalid_count": 0,
            "strict_invalid_count": 0,
            "contract_invalid_count": 0,
            "seed_only_count": 0,
            "strong_promoting_count": 0,
            "promotion_ready_deck_count": 0,
            "non_promoting_count": 0,
            "first_non_promoting_result": "",
            "first_non_promoting_action": "none",
            "first_non_promoting_reason": "none",
            "freshness_missing_count": 0,
            "no_op_validation_risk": False,
        }

    latest = candidates[-1]
    fields_path = latest / "fields.yaml"
    results_dir = latest / "results"
    if not fields_path.is_file() or not results_dir.is_dir():
        return {
            "status": "attention",
            "path": _relative_posix(root, latest),
            "result_count": 0,
            "invalid_count": 0,
            "strict_invalid_count": 0,
            "contract_invalid_count": 0,
            "seed_only_count": 0,
            "strong_promoting_count": 0,
            "promotion_ready_deck_count": 0,
            "non_promoting_count": 0,
            "first_non_promoting_result": "",
            "first_non_promoting_action": "none",
            "first_non_promoting_reason": "none",
            "freshness_missing_count": 0,
            "no_op_validation_risk": True,
        }

    try:
        from hsconfig.research_result_contract_sentinel import (
            build_research_result_contract_sentinel,
        )

        sentinel = build_research_result_contract_sentinel(fields_path, results_dir)
        summary = sentinel["summary"]
    except Exception:
        return {
            "status": "attention",
            "path": _relative_posix(root, latest),
            "result_count": 0,
            "invalid_count": 0,
            "strict_invalid_count": 0,
            "contract_invalid_count": 0,
            "seed_only_count": 0,
            "strong_promoting_count": 0,
            "promotion_ready_deck_count": 0,
            "non_promoting_count": 0,
            "first_non_promoting_result": "",
            "first_non_promoting_action": "none",
            "first_non_promoting_reason": "none",
            "freshness_missing_count": 0,
            "no_op_validation_risk": True,
        }
    strict_invalid_count = int(summary.get("strict_invalid_count") or 0)
    contract_invalid_count = int(summary.get("contract_invalid_count") or 0)
    return {
        "status": str(summary["status"]),
        "path": _relative_posix(root, latest),
        "result_count": int(summary["result_count"]),
        "invalid_count": strict_invalid_count + contract_invalid_count,
        "strict_invalid_count": strict_invalid_count,
        "contract_invalid_count": contract_invalid_count,
        "seed_only_count": int(summary.get("seed_only_count") or 0),
        "strong_promoting_count": int(summary.get("strong_promoting_count") or 0),
        "promotion_ready_deck_count": int(
            summary.get("promotion_ready_deck_count")
            or summary.get("strong_promoting_count")
            or 0
        ),
        "non_promoting_count": int(summary.get("non_promoting_count") or 0),
        "first_non_promoting_result": str(
            summary.get("first_non_promoting_result") or ""
        ),
        "first_non_promoting_action": str(
            summary.get("first_non_promoting_action") or "none"
        ),
        "first_non_promoting_reason": str(
            summary.get("first_non_promoting_reason") or "none"
        ),
        "freshness_missing_count": int(summary.get("freshness_missing_count") or 0),
        "no_op_validation_risk": bool(summary["no_op_validation_risk"]),
    }


def build_research_context_preflight(repo_root: str | Path) -> ResearchContextPreflight:
    root = Path(repo_root).resolve()
    current_truth_path = root / "docs" / "research" / "current-truth.md"
    current_truth_index_path = root / "docs" / "research" / "current-truth-index.json"
    current_truth_text = _read(current_truth_path)
    index_text = _read(current_truth_index_path)
    index_payload: dict[str, object] = {}
    if index_text:
        try:
            parsed = json.loads(index_text)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            index_payload = parsed

    research_root = root / "docs" / "research"
    historical_outline_paths: tuple[str, ...] = ()
    if research_root.exists():
        historical_outline_paths = tuple(
            sorted(
                _relative_posix(root, path)
                for path in research_root.glob("*/outline.yaml")
                if path.is_file()
            )
        )

    active_evidence_index_present = (
        current_truth_path.exists()
        and current_truth_index_path.exists()
        and "# HSConfig Current Truth Index" in current_truth_text
        and "Research artifacts are evidence, not operator instructions."
        in current_truth_text
    )
    machine_evidence_index_present = (
        current_truth_index_path.exists()
        and index_payload.get("authority") == "evidence_index_only"
        and index_payload.get("operator_gate_impact") == "diagnostic_only"
        and index_payload.get("normal_apply_authority") == NORMAL_APPLY_AUTHORITY
    )
    historical_outlines_apply_authority = False
    sync_policy = index_payload.get("research_snapshot_sync_policy")
    source_status_apply_blocking = bool(
        sync_policy.get("source_status_apply_blocking", False)
        if isinstance(sync_policy, dict)
        else False
    )
    latest_research_contract = _latest_research_result_contract(root)
    status = (
        "current"
        if active_evidence_index_present
        and machine_evidence_index_present
        and not historical_outlines_apply_authority
        and not source_status_apply_blocking
        else "attention"
    )

    return ResearchContextPreflight(
        status=status,
        active_evidence_index_present=active_evidence_index_present,
        active_evidence_index_path="docs/research/current-truth.md",
        machine_evidence_index_present=machine_evidence_index_present,
        machine_evidence_index_path="docs/research/current-truth-index.json",
        authority=str(index_payload.get("authority") or "missing"),
        operator_gate_impact=str(index_payload.get("operator_gate_impact") or "missing"),
        normal_apply_authority=str(
            index_payload.get("normal_apply_authority")
            or NORMAL_APPLY_AUTHORITY
        ),
        recommended_research_entrypoint="docs/research/current-truth.md",
        historical_outline_count=len(historical_outline_paths),
        historical_outline_paths=historical_outline_paths,
        historical_outlines_apply_authority=historical_outlines_apply_authority,
        latest_research_result_contract_status=str(
            latest_research_contract["status"]
        ),
        latest_research_result_contract_path=str(latest_research_contract["path"]),
        latest_research_result_contract_result_count=int(
            latest_research_contract["result_count"]
        ),
        latest_research_result_contract_invalid_count=int(
            latest_research_contract["invalid_count"]
        ),
        latest_research_result_contract_strict_invalid_count=int(
            latest_research_contract["strict_invalid_count"]
        ),
        latest_research_result_contract_contract_invalid_count=int(
            latest_research_contract["contract_invalid_count"]
        ),
        latest_research_result_contract_seed_only_count=int(
            latest_research_contract["seed_only_count"]
        ),
        latest_research_result_contract_strong_promoting_count=int(
            latest_research_contract["strong_promoting_count"]
        ),
        latest_research_result_contract_promotion_ready_deck_count=int(
            latest_research_contract["promotion_ready_deck_count"]
        ),
        latest_research_result_contract_non_promoting_count=int(
            latest_research_contract["non_promoting_count"]
        ),
        latest_research_result_contract_first_non_promoting_result=str(
            latest_research_contract["first_non_promoting_result"]
        ),
        latest_research_result_contract_first_non_promoting_action=str(
            latest_research_contract["first_non_promoting_action"]
        ),
        latest_research_result_contract_first_non_promoting_reason=str(
            latest_research_contract["first_non_promoting_reason"]
        ),
        latest_research_result_contract_freshness_missing_count=int(
            latest_research_contract["freshness_missing_count"]
        ),
        latest_research_result_contract_no_op_validation_risk=bool(
            latest_research_contract["no_op_validation_risk"]
        ),
        source_status_apply_blocking=source_status_apply_blocking,
        notes=(
            "Historical research outline files are evidence only.",
            "Use docs/research/current-truth.md before opening dated research folders.",
            "Research context diagnostics do not replace reports/operator_summary.json.",
        ),
    )


def build_contract_preflight(
    repo_root: str | Path = ".",
    *,
    git: GitPreflight | None = None,
    skill_install_root: str | Path | None = None,
    package: str | Path | None = None,
) -> dict[str, object]:
    root = Path(repo_root).resolve()
    repo_root_exists = root.exists()
    skill_root = root / ".agents" / "skills" / "hsconfig"
    skill_text = _read(skill_root / "SKILL.md")
    workflow_text = _read(skill_root / "references" / "workflow.md")
    checklist_text = _read(skill_root / "references" / "contract-compiler-checklist.md")
    operator_text = _read(root / "docs" / "operator" / "README.md")
    source_builder_workflow_text = _read(
        root / "docs" / "operator" / "source-builder-workflow.md"
    )
    source_candidate_plan_text = _read(
        root / "src" / "hsconfig" / "source_candidate_plan.py"
    )
    source_readiness_preview_text = _read(
        root / "src" / "hsconfig" / "source_readiness_preview.py"
    )
    source_autopilot_text = _read(root / "src" / "hsconfig" / "source_autopilot.py")
    configure_command_text = _read(
        root / "src" / "hsconfig" / "commands" / "configure.py"
    )
    configure_workflow_text = _read(
        root / "src" / "hsconfig" / "configure_workflow.py"
    )
    combined = "\n".join(
        [
            skill_text,
            workflow_text,
            checklist_text,
            operator_text,
            source_builder_workflow_text,
            source_candidate_plan_text,
            source_readiness_preview_text,
            source_autopilot_text,
            configure_command_text,
            configure_workflow_text,
        ]
    )
    references_line = _references_line(skill_text)
    git_snapshot = git or build_git_preflight(root)
    research_context = build_research_context_preflight(root)
    installed_skill_sync = build_installed_skill_sync_status(root, skill_install_root)
    source_candidate_plan_visible = _source_candidate_plan_contract_visible(
        operator_text,
        source_builder_workflow_text,
        source_candidate_plan_text,
    )
    source_readiness_preview_visible = _source_readiness_preview_visible(
        source_readiness_preview_text,
        configure_workflow_text,
        source_autopilot_text,
        source_builder_workflow_text,
        workflow_text,
    )

    checks = {
        "repo_current": (
            git_snapshot.clean_for_runtime_work
            and git_snapshot.origin_main_error is None
            and git_snapshot.behind_origin_main == 0
        ),
        "skill_root_present": skill_root.exists(),
        "installed_skill_sync_current": (
            installed_skill_sync.get("matches_repo_skill") is True
            and installed_skill_sync.get("diagnostic_only") is True
            and installed_skill_sync.get("runtime_apply_authority")
            == NORMAL_APPLY_AUTHORITY
        ),
        "reference_files_present": all(
            (skill_root / relative_path).exists()
            for relative_path in REQUIRED_REFERENCE_FILES
        ),
        "checklist_referenced_by_normal_workflow": (
            "Contract compiler checklist: `references/contract-compiler-checklist.md`."
            in skill_text
            and "Contract compiler checklist: `references/contract-compiler-checklist.md`."
            in workflow_text
        ),
        "checklist_listed_in_references": (
            "references/contract-compiler-checklist.md" in references_line
        ),
        "skill_thin_router_visible": _skill_thin_router_visible(skill_text),
        "configure_acceptance_route_visible": _configure_acceptance_route_visible(
            combined
        ),
        "pre_run_config_contract_receipt_visible": (
            _pre_run_config_contract_receipt_visible(combined)
        ),
        "configure_acceptance_projection_not_gate_visible": (
            _configure_acceptance_projection_not_gate_visible(combined)
        ),
        "config_quality_summary_diagnostic_only_visible": (
            _config_quality_summary_diagnostic_only_visible(combined)
        ),
        "config_proof_summary_visible": _config_proof_summary_visible(combined),
        "operator_summary_single_authority_visible": (
            "operator_summary.json remains the only normal apply authority" in combined
            or "operator_summary.json` remains the only normal apply authority"
            in combined
        ),
        "source_status_nonblocking_visible": (
            "source_status_apply_blocking" in combined
            and "must remain `false`" in combined
            and (
                "SOURCE_BACKED_STRONG is an evidence-quality label" in combined
                or "`SOURCE_BACKED_STRONG` is an evidence-quality label" in combined
            )
        ),
        "source_candidate_plan_visible": source_candidate_plan_visible,
        "source_readiness_preview_visible": source_readiness_preview_visible,
        "no_default_only_visible": (
            "No hidden default-only runtime" in combined
            and "default_only_runtime_surfaces=[]" in combined
        ),
        "runtime_surface_boundary_visible": all(
            term in combined
            for term in (
                "`GlobalValues.json`",
                "`Mulligan.json`",
                "`per-card <CARDID>.json`",
                "`Combo.json`",
                "`Presume.json`",
                "`Concede.json`",
                "outside the normal HSConfig output path",
            )
        ),
        "darkbishop_effect_not_mulligan_visible": (
            "Darkbishop" in combined
            and "hero-power-transform" in combined
            and "do not emit a Mulligan keep without explicit opening-hand source text"
            in combined
        ),
        "negative_scope_visible": all(
            term in combined
            for term in (
                "does not parse replays",
                "inspect " + "win" + "rate",
                "analyze runtime logs",
                "tune after games",
            )
        ),
        "diagnostic_only_visible": (
            "diagnostic-only" in combined
            and "not another operator gate" in checklist_text
            and "not another runtime apply gate" in combined
        ),
        "research_current_truth_index_visible": (
            research_context.status == "current"
            and research_context.active_evidence_index_present
            and research_context.machine_evidence_index_present
            and research_context.authority == "evidence_index_only"
            and research_context.operator_gate_impact == "diagnostic_only"
            and research_context.normal_apply_authority == NORMAL_APPLY_AUTHORITY
            and research_context.source_status_apply_blocking is False
        ),
        "research_result_contract_sentinel_visible": (
            research_context.latest_research_result_contract_status
            in {"clean", "attention", "not_found"}
            and research_context.source_status_apply_blocking is False
        ),
        "historical_research_outlines_diagnostic_only": (
            research_context.historical_outlines_apply_authority is False
        ),
    }
    package_contract = build_package_contract_preflight(package)
    if package_contract is not None:
        checks["package_contract_current"] = bool(
            package_contract.get("package_contract_current", False)
        )

    failures = [key for key in EXPECTED_CHECK_KEYS if not checks[key]]
    if package_contract is not None and not checks["package_contract_current"]:
        failures.append("package_contract_current")
    payload: dict[str, object] = {
        "status": "PASS" if not failures else "ATTENTION",
        "repo_root": str(root),
        "git": asdict(git_snapshot),
        "checks": checks,
        "failures": failures,
        "research_context": asdict(research_context),
        "installed_skill_sync": installed_skill_sync,
        "source_candidate_plan_contract": _source_candidate_plan_contract_payload(
            source_candidate_plan_visible
        ),
        "source_readiness_preview_contract": (
            _source_readiness_preview_contract_payload(
                source_readiness_preview_visible
            )
        ),
        "runtime_apply_authority": NORMAL_APPLY_AUTHORITY,
        "source_status_apply_blocking": False,
        "diagnostic_only": True,
    }
    if package_contract is not None:
        payload["package_contract"] = package_contract
    if not repo_root_exists:
        payload["error"] = {
            "type": "FileNotFoundError",
            "message": f"repo root does not exist: {root}",
        }
    return payload
