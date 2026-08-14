from __future__ import annotations

import argparse

from hsconfig.commands.common import run_payload_command
from hsconfig.package_builder import build_package_payload, prepare_package_payload


def run_prepare_command(args: argparse.Namespace, *, expert_mode: bool) -> int:
    worker = build_package_payload if expert_mode else prepare_package_payload
    return run_payload_command(args, worker)
