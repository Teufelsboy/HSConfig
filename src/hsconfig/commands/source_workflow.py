from __future__ import annotations

import argparse


def run_source_manifest_command(args: argparse.Namespace) -> int:
    from hsconfig.cli import _run_source_manifest_command

    return _run_source_manifest_command(args)


def run_draft_source_documents_command(args: argparse.Namespace) -> int:
    from hsconfig.cli import _run_draft_source_documents_command

    return _run_draft_source_documents_command(args)


def run_research_deck_command(args: argparse.Namespace) -> int:
    from hsconfig.cli import _run_research_deck_command

    return _run_research_deck_command(args)
