from __future__ import annotations

import argparse


def run_prepare_command(args: argparse.Namespace, *, expert_mode: bool) -> int:
    from hsconfig.cli import _run_prepare_command

    return _run_prepare_command(args, expert_mode=expert_mode)
