from __future__ import annotations

from argparse import Namespace
from dataclasses import asdict
from pathlib import Path

from hsconfig.commands.common import emit_result
from hsconfig.contract_preflight import (
    EXPECTED_CHECK_KEYS,
    GitPreflight,
    build_contract_preflight,
)
from hsconfig.skill_sync_status import (
    DEFAULT_INSTALL_ROOT,
    build_installed_skill_sync_status,
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
            "recommended_action": "python scripts\\sync_installed_skill.py",
            "diagnostic_only": True,
            "runtime_apply_authority": "reports/operator_summary.json",
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
