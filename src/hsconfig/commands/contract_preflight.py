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
            "source_status_apply_blocking": False,
            "notes": [
                f"research context preflight unavailable for {root}: {type(exc).__name__}"
            ],
        }


def run_contract_preflight_command(args: Namespace) -> int:
    repo_root = getattr(args, "repo_root", ".")
    try:
        payload = build_contract_preflight(
            repo_root,
            skill_install_root=getattr(args, "skill_install_root", None),
        )
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
            "runtime_apply_authority": "reports/operator_summary.json",
            "source_status_apply_blocking": False,
            "diagnostic_only": True,
        }
    return emit_result(
        payload,
        bool(getattr(args, "json", False)),
        0 if payload["status"] == "PASS" else 1,
    )
