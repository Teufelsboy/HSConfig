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


def run_contract_preflight_command(args: Namespace) -> int:
    repo_root = getattr(args, "repo_root", ".")
    try:
        payload = build_contract_preflight(repo_root)
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
            "runtime_apply_authority": "reports/operator_summary.json",
            "source_status_apply_blocking": False,
            "diagnostic_only": True,
        }
    return emit_result(
        payload,
        bool(getattr(args, "json", False)),
        0 if payload["status"] == "PASS" else 1,
    )
