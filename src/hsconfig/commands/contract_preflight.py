from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from hsconfig.commands.common import emit_result
from hsconfig.contract_preflight import build_contract_preflight


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
            "checks": {},
            "failures": ["repo_root"],
            "runtime_apply_authority": "reports/operator_summary.json",
            "source_status_apply_blocking": False,
            "diagnostic_only": True,
        }
    return emit_result(
        payload,
        bool(getattr(args, "json", False)),
        0 if payload["status"] == "PASS" else 1,
    )
