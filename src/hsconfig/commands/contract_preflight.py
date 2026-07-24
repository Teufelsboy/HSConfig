from __future__ import annotations

from argparse import Namespace
from dataclasses import asdict
from pathlib import Path

from hsconfig.commands.common import emit_result
from hsconfig.contract_preflight import (
    EXPECTED_CHECK_KEYS,
    GitPreflight,
    build_contract_preflight,
    build_research_context_preflight,
)
from hsconfig.skill_sync_status import (
    DEFAULT_INSTALL_ROOT,
    build_installed_skill_sync_status,
    installed_skill_sync_recommended_action,
)


def _unavailable_git_payload() -> dict[str, object]:
    return asdict(
        GitPreflight(
            branch="unknown",
            upstream=None,
            dirty=False,
            ahead_origin_main=0,
            behind_origin_main=0,
            clean_for_runtime_work=False,
            ahead_upstream=None,
            behind_upstream=None,
            origin_main_error="git preflight unavailable",
        )
    )


def _unavailable_installed_skill_payload(
    repo_root: str,
    install_root: object,
) -> dict[str, object]:
    try:
        return build_installed_skill_sync_status(repo_root, install_root)
    except Exception as exc:
        resolved_install_root = (
            Path(install_root).expanduser() if install_root else DEFAULT_INSTALL_ROOT
        )
        return {
            "status": "attention",
            "source_skill_path": str(
                Path(repo_root).resolve() / ".agents" / "skills" / "hsconfig"
            ),
            "installed_skill_path": str(resolved_install_root / "hsconfig"),
            "installed_skill_present": False,
            "matches_repo_skill": False,
            "reason": type(exc).__name__,
            "diffs": [],
            "recommended_action": installed_skill_sync_recommended_action(
                resolved_install_root
            ),
            "diagnostic_only": True,
            "runtime_apply_authority": "reports/operator_summary.json",
        }


def _unavailable_research_context_payload(repo_root: str) -> dict[str, object]:
    try:
        return asdict(build_research_context_preflight(repo_root))
    except Exception as exc:
        root = Path(repo_root).resolve()
        return {
            "status": "attention",
            "active_evidence_index_present": False,
            "active_evidence_index_path": "docs/research/current-truth.md",
            "machine_evidence_index_present": False,
            "machine_evidence_index_path": "docs/research/current-truth-index.json",
            "authority": "unavailable",
            "operator_gate_impact": "diagnostic_only",
            "normal_apply_authority": "reports/operator_summary.json",
            "recommended_research_entrypoint": "docs/research/current-truth.md",
            "historical_outline_count": 0,
            "historical_outline_paths": [],
            "historical_outlines_apply_authority": False,
            "latest_research_result_contract_status": "attention",
            "latest_research_result_contract_path": "",
            "latest_research_result_contract_result_count": 0,
            "latest_research_result_contract_invalid_count": 0,
            "latest_research_result_contract_strict_invalid_count": 0,
            "latest_research_result_contract_contract_invalid_count": 0,
            "latest_research_result_contract_seed_only_count": 0,
            "latest_research_result_contract_strong_promoting_count": 0,
            "latest_research_result_contract_promotion_ready_deck_count": 0,
            "latest_research_result_contract_non_promoting_count": 0,
            "latest_research_result_contract_first_non_promoting_result": "",
            "latest_research_result_contract_first_non_promoting_action": "none",
            "latest_research_result_contract_first_non_promoting_reason": "none",
            "latest_research_result_contract_freshness_missing_count": 0,
            "latest_research_result_contract_no_op_validation_risk": True,
            "source_status_apply_blocking": False,
            "notes": [
                f"research context preflight unavailable for {root}: {type(exc).__name__}"
            ],
        }


def _unavailable_source_candidate_plan_contract_payload() -> dict[str, object]:
    return {
        "status": "attention",
        "authority": "diagnostic_source_candidate_plan",
        "documentation_path": "docs/operator/source-builder-workflow.md",
        "operator_entrypoint_path": "docs/operator/README.md",
        "implementation_path": "src/hsconfig/source_candidate_plan.py",
        "runtime_apply_authority": "reports/operator_summary.json",
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
            "source candidate plan contract preflight unavailable",
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }


def _unavailable_source_readiness_preview_contract_payload() -> dict[str, object]:
    return {
        "status": "attention",
        "authority": "diagnostic_source_readiness_preview",
        "documentation_paths": [
            "docs/operator/source-builder-workflow.md",
            ".agents/skills/hsconfig/references/workflow.md",
        ],
        "implementation_path": "src/hsconfig/source_readiness_preview.py",
        "producer_paths": [
            "src/hsconfig/source_autopilot.py",
            "src/hsconfig/commands/configure.py",
        ],
        "runtime_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
        "apply_blocking": False,
        "runtime_write_performed": False,
        "notes": [
            "source readiness preview contract preflight unavailable",
            (
                "Source readiness preview cannot promote SOURCE_BACKED_STRONG, "
                "block apply, apply runtime files, or write runtime config."
            ),
            "reports/operator_summary.json remains the only normal apply authority.",
        ],
    }


def run_contract_preflight_command(args: Namespace) -> int:
    repo_root = getattr(args, "repo_root", ".")
    package = getattr(args, "package", None)
    try:
        preflight_kwargs = {
            "skill_install_root": getattr(args, "skill_install_root", None),
        }
        if package is not None:
            preflight_kwargs["package"] = package
        payload = build_contract_preflight(repo_root, **preflight_kwargs)
    except Exception as exc:
        payload = {
            "status": "ATTENTION",
            "repo_root": str(Path(repo_root).resolve()),
            "error": {
                "type": type(exc).__name__,
                "message": str(exc) or type(exc).__name__,
            },
            "git": _unavailable_git_payload(),
            "checks": {key: False for key in EXPECTED_CHECK_KEYS},
            "failures": list(EXPECTED_CHECK_KEYS),
            "research_context": _unavailable_research_context_payload(repo_root),
            "installed_skill_sync": _unavailable_installed_skill_payload(
                repo_root,
                getattr(args, "skill_install_root", None),
            ),
            "source_candidate_plan_contract": (
                _unavailable_source_candidate_plan_contract_payload()
            ),
            "source_readiness_preview_contract": (
                _unavailable_source_readiness_preview_contract_payload()
            ),
            "runtime_apply_authority": "reports/operator_summary.json",
            "source_status_apply_blocking": False,
            "diagnostic_only": True,
        }
        if package is not None:
            error_message = (
                f"contract-preflight raised {type(exc).__name__}: "
                f"{str(exc) or type(exc).__name__}"
            )
            payload["checks"]["package_contract_current"] = False
            payload["package_contract"] = {
                "status": "attention",
                "package": str(package),
                "present": Path(package).is_dir(),
                "authority": "diagnostic_only",
                "validation_status": "failed",
                "validation_errors": [error_message],
                "validation_checked_files": 0,
                "config_quality_status": "attention",
                "config_quality_problem_count": 1,
                "config_quality_first_problem": {
                    "check": "contract_preflight_exception",
                    "value": str(exc),
                },
                "ready_to_use_from_operator_summary": False,
                "observed_operator_source_status_apply_blocking": False,
                "observed_default_only_runtime_surfaces": [],
                "next_report_to_open": "reports/operator_summary.json",
                "runtime_apply_authority": "reports/operator_summary.json",
                "source_status_apply_blocking": False,
                "apply_blocking": False,
                "runtime_write_performed": False,
                "notes": [
                    "Package contract preflight is diagnostic only.",
                    (
                        "reports/operator_summary.json remains the only normal "
                        "apply authority."
                    ),
                    error_message,
                ],
                "technical_status": "",
                "semantic_status": "",
                "runtime_apply_mode": "",
                "runtime_apply_allowed": False,
                "default_only_runtime_surfaces": [],
                "validate_config_package_status": "failed",
                "validate_config_package_errors": [error_message],
                "checked_runtime_files": 0,
                "config_intent_self_audit_status": "attention",
                "config_intent_first_attention": "contract_preflight_exception",
                "closure_schema_current": False,
                "cards_missing_closure": 0,
                "package_contract_current": False,
                "failures": ["contract_preflight_exception"],
            }
            if "package_contract_current" not in payload["failures"]:
                payload["failures"].append("package_contract_current")
    return emit_result(
        payload,
        bool(getattr(args, "json", False)),
        0 if payload["status"] == "PASS" else 1,
    )
