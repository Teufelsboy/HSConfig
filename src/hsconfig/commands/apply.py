from __future__ import annotations

import argparse


def run_apply_command(args: argparse.Namespace) -> int:
    from hsconfig.cli import _run_apply_command

    return _run_apply_command(args)
