from __future__ import annotations

import argparse

from hsconfig.cli_parser import build_parser
from hsconfig.commands.apply import run_apply_command, run_validate_command
from hsconfig.commands.acceptance_matrix import run_acceptance_matrix_command
from hsconfig.commands.common import emit_result, run_payload_command
from hsconfig.commands.contract_doctor import run_contract_doctor_command
from hsconfig.commands.contract_spine_sentinel import (
    run_contract_spine_sentinel_command,
)
from hsconfig.commands.configure import run_configure_command
from hsconfig.commands.prepare import run_prepare_command
from hsconfig.commands.source_workflow import (
    run_draft_source_documents_command,
    run_research_deck_command,
    run_research_status_sync_command,
    run_source_acquire_command,
    run_source_autopilot_command,
    run_source_manifest_command,
)
from hsconfig.package_builder import research_contract_payload


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "configure":
        return run_configure_command(args)
    if args.command == "apply":
        return run_apply_command(args)
    if args.command == "build":
        return run_prepare_command(args, expert_mode=True)
    if args.command == "prepare":
        return run_prepare_command(args, expert_mode=False)
    if args.command == "source-manifest":
        return run_source_manifest_command(args)
    if args.command == "draft-source-documents":
        return run_draft_source_documents_command(args)
    if args.command == "source-autopilot":
        return run_source_autopilot_command(args)
    if args.command == "source-acquire":
        return run_source_acquire_command(args)
    if args.command == "research-deck":
        return run_research_deck_command(args)
    if args.command == "research-contract":
        return run_payload_command(args, research_contract_payload)
    if args.command == "acceptance-matrix":
        return run_acceptance_matrix_command(args)
    if args.command == "contract-doctor":
        return run_contract_doctor_command(args)
    if args.command == "contract-spine-sentinel":
        return run_contract_spine_sentinel_command(args)
    if args.command == "research-status-sync":
        return run_research_status_sync_command(args)
    if args.command == "validate":
        return run_validate_command(args)
    return emit_result(
        {"status": "failed", "errors": [f"Unknown command: {args.command}"]},
        bool(getattr(args, "json", False)),
        1,
    )


def _build_parser() -> argparse.ArgumentParser:
    return build_parser()


if __name__ == "__main__":
    raise SystemExit(main())
