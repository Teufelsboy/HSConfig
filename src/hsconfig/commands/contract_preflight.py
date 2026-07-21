from __future__ import annotations

from argparse import Namespace

from hsconfig.commands.common import emit_result
from hsconfig.contract_preflight import build_contract_preflight


def run_contract_preflight_command(args: Namespace) -> int:
    payload = build_contract_preflight(getattr(args, "repo_root", "."))
    return emit_result(
        payload,
        bool(getattr(args, "json", False)),
        0 if payload["status"] == "PASS" else 1,
    )
