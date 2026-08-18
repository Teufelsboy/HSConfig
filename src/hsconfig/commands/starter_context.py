"""Read-only starter-context CLI handler."""

from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path
from typing import Any

from hsconfig.atomic_io import atomic_write_bytes
from hsconfig.commands.common import run_payload_command
from hsconfig.guide_source_builder import research_required_guide_sources
from hsconfig.hearthstonejson import fetch_latest_cards
from hsconfig.package_io import (
    FilesystemPathGuard,
    capture_plain_ancestor_guard,
    hold_plain_directory,
    path_identity,
    path_lexists,
    require_plain_directory,
    secure_create_directory,
)
from hsconfig.package_request import resolve_package_request
from hsconfig.starter_context import build_starter_context
from hsconfig.starter_contract import STARTER_CONTEXT_FILENAME


def run_starter_context_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, _starter_context_payload)


def _starter_context_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out).absolute()
    runtime_root = Path(args.runtime_root).absolute()
    if _is_same_or_descendant(out, runtime_root):
        raise ValueError("starter_context_output_inside_runtime_root")
    if path_lexists(out):
        raise ValueError("starter_context_output_directory_exists")
    require_plain_directory(out.parent)
    require_plain_directory(runtime_root)
    output_guard = capture_plain_ancestor_guard(out)
    runtime_guard = capture_plain_ancestor_guard(runtime_root)
    output_parent_identity = path_identity(out.parent)
    runtime_root_identity = path_identity(runtime_root)
    request = resolve_package_request(
        args,
        current_date=_current_date(args),
        fetch_latest_cards_fn=fetch_latest_cards,
        research_required_guide_sources_fn=research_required_guide_sources,
        include_disposition_diagnostics=False,
    )
    _revalidate_output_boundary(
        out=out,
        runtime_root=runtime_root,
        output_guard=output_guard,
        runtime_guard=runtime_guard,
    )
    context = build_starter_context(request.snapshot)
    _revalidate_output_boundary(
        out=out,
        runtime_root=runtime_root,
        output_guard=output_guard,
        runtime_guard=runtime_guard,
    )
    with hold_plain_directory(
        runtime_root,
        expected_identity=runtime_root_identity,
    ):
        _revalidate_output_boundary(
            out=out,
            runtime_root=runtime_root,
            output_guard=output_guard,
            runtime_guard=runtime_guard,
        )
        output_identity = secure_create_directory(
            out,
            expected_parent_identity=output_parent_identity,
        )
        target = out / STARTER_CONTEXT_FILENAME
        atomic_write_bytes(
            target,
            context.document.canonical_json,
            expected_parent_identity=output_identity,
        )
    return (
        {
            "content_sha256": context.document.content_sha256,
            "deck_fingerprint": context.deck_fingerprint,
            "output": str(target),
            "runtime_write_performed": False,
            "status": "passed",
        },
        0,
    )


def _revalidate_output_boundary(
    *,
    out: Path,
    runtime_root: Path,
    output_guard: FilesystemPathGuard,
    runtime_guard: FilesystemPathGuard,
) -> None:
    output_guard.validate()
    runtime_guard.validate()
    if path_lexists(out):
        raise ValueError("starter_context_output_boundary_changed")
    if _is_same_or_descendant(out, runtime_root):
        raise ValueError("starter_context_output_inside_runtime_root")


def _current_date(args: argparse.Namespace) -> date:
    value = getattr(args, "current_date", None)
    return date.today() if value is None else date.fromisoformat(str(value))


def _is_same_or_descendant(candidate: Path, root: Path) -> bool:
    candidate_text = os.path.normcase(str(candidate.resolve(strict=False)))
    root_text = os.path.normcase(str(root.resolve(strict=False)))
    try:
        return os.path.commonpath((candidate_text, root_text)) == root_text
    except ValueError:
        return False


__all__ = ("run_starter_context_command",)
