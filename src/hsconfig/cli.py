from __future__ import annotations

import argparse

from hsconfig.cli_parser import build_parser


def run_apply_command(args: argparse.Namespace) -> int:
    from hsconfig.commands.apply import run_apply_command as implementation

    return implementation(args)


def run_validate_command(args: argparse.Namespace) -> int:
    from hsconfig.commands.apply import run_validate_command as implementation

    return implementation(args)


def run_contract_doctor_command(args: argparse.Namespace) -> int:
    from hsconfig.commands.contract_doctor import run_contract_doctor_command as implementation

    return implementation(args)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "configure":
        from hsconfig.commands.configure import run_configure_command

        return run_configure_command(args)
    if args.command == "apply":
        return run_apply_command(args)
    if args.command == "runtime-match":
        from hsconfig.commands.runtime_match import run_runtime_match_command

        return run_runtime_match_command(args)
    if args.command == "build":
        from hsconfig.commands.prepare import run_prepare_command

        return run_prepare_command(args, expert_mode=True)
    if args.command == "prepare":
        from hsconfig.commands.prepare import run_prepare_command

        return run_prepare_command(args, expert_mode=False)
    if args.command == "source-manifest":
        from hsconfig.commands.source_workflow import run_source_manifest_command

        return run_source_manifest_command(args)
    if args.command == "draft-source-documents":
        from hsconfig.commands.source_workflow import run_draft_source_documents_command

        return run_draft_source_documents_command(args)
    if args.command == "source-autopilot":
        from hsconfig.commands.source_workflow import run_source_autopilot_command

        return run_source_autopilot_command(args)
    if args.command == "source-acquire":
        from hsconfig.commands.source_workflow import run_source_acquire_command

        return run_source_acquire_command(args)
    if args.command == "research-deck":
        from hsconfig.commands.source_workflow import run_research_deck_command

        return run_research_deck_command(args)
    if args.command == "research-contract":
        from hsconfig.commands.common import run_payload_command
        from hsconfig.package_builder import research_contract_payload

        return run_payload_command(args, research_contract_payload)
    if args.command == "acceptance-matrix":
        from hsconfig.commands.acceptance_matrix import run_acceptance_matrix_command

        return run_acceptance_matrix_command(args)
    if args.command == "contract-doctor":
        return run_contract_doctor_command(args)
    if args.command == "contract-spine-sentinel":
        from hsconfig.commands.contract_spine_sentinel import (
            run_contract_spine_sentinel_command,
        )

        return run_contract_spine_sentinel_command(args)
    if args.command == "contract-preflight":
        from hsconfig.commands.contract_preflight import run_contract_preflight_command

        return run_contract_preflight_command(args)
    if args.command == "research-status-sync":
        from hsconfig.commands.source_workflow import run_research_status_sync_command

        return run_research_status_sync_command(args)
    if args.command == "strong-closure-dossier":
        from hsconfig.commands.source_workflow import run_strong_closure_dossier_command

        return run_strong_closure_dossier_command(args)
    if args.command == "source-closure-optimizer":
        from hsconfig.commands.source_workflow import run_source_closure_optimizer_command

        return run_source_closure_optimizer_command(args)
    if args.command == "validate":
        return run_validate_command(args)
    from hsconfig.commands.common import emit_result

    return emit_result(
        {"status": "failed", "errors": [f"Unknown command: {args.command}"]},
        bool(getattr(args, "json", False)),
        1,
    )


def _build_parser() -> argparse.ArgumentParser:
    return build_parser()


if __name__ == "__main__":
    raise SystemExit(main())
