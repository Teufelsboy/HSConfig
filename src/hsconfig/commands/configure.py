from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hsconfig.commands.apply import run_apply_command, run_validate_command
from hsconfig.commands.common import emit_result
from hsconfig.commands.prepare import run_prepare_command
from hsconfig.commands.source_workflow import (
    draft_source_documents_payload,
    research_deck_payload,
    source_manifest_payload,
)
from hsconfig.io import write_json
from hsconfig.package_io import prepare_research_output_dir


def run_configure_command(args: argparse.Namespace) -> int:
    payload, status = configure_payload(args)
    return emit_result(payload, bool(getattr(args, "json", False)), status)


def configure_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)

    manifest_dir = out / "01_manifest"
    draft_dir = out / "02_source_documents"
    research_dir = out / "03_research"
    package_dir = out / "04_package"

    common = {
        "deck_name": args.deck_name,
        "deck_code": args.deck_code,
        "cards_json": getattr(args, "cards_json", None),
        "collectible_cards_json": getattr(args, "collectible_cards_json", None),
        "full_cards_json": getattr(args, "full_cards_json", None),
        "allow_placeholder": bool(getattr(args, "allow_placeholder", False)),
        "json": True,
    }

    manifest_payload, manifest_status = source_manifest_payload(
        SimpleNamespace(**common, out=str(manifest_dir))
    )
    if manifest_status != 0:
        return _finish(out, "failed", manifest_payload, manifest_status)

    source_documents_json = None
    if getattr(args, "source_evidence_json", None):
        draft_payload, draft_status = draft_source_documents_payload(
            SimpleNamespace(
                **common,
                source_evidence_json=args.source_evidence_json,
                out=str(draft_dir),
            )
        )
        if draft_status != 0:
            return _finish(out, "failed", draft_payload, draft_status)
        source_documents_json = draft_dir / "source_documents.json"

    research_payload, research_status = research_deck_payload(
        SimpleNamespace(
            **common,
            out=str(research_dir),
            source_documents_json=str(source_documents_json) if source_documents_json else None,
            source_evidence_json=getattr(args, "source_evidence_json", None),
            guide_sources_json=None,
            claims_json=None,
            skip_semantic_fetch=False,
            auto_research_fallback=True,
        )
    )
    if research_status != 0:
        return _finish(out, "failed", research_payload, research_status)

    prepare_status = run_prepare_command(
        SimpleNamespace(
            deck_name=args.deck_name,
            deck_code=args.deck_code,
            out=str(package_dir),
            runtime_root=args.runtime_root,
            guide_sources_json=str(research_dir / "guide_sources.json"),
            source_documents_json=str(source_documents_json) if source_documents_json else None,
            cards_json=getattr(args, "cards_json", None),
            claims_json=None,
            plan_reports_dir=None,
            allow_placeholder=bool(getattr(args, "allow_placeholder", False)),
            auto_research_fallback=True,
            json=True,
        ),
        expert_mode=False,
    )
    if prepare_status != 0:
        return _finish(out, "failed", {"stage": "prepare"}, prepare_status)

    validate_status = run_validate_command(SimpleNamespace(package=str(package_dir), json=True))
    if validate_status != 0:
        return _finish(out, "failed", {"stage": "validate"}, validate_status)

    apply_status = None
    if bool(getattr(args, "apply", False)):
        apply_status = run_apply_command(
            SimpleNamespace(
                package=str(package_dir),
                runtime_root=args.runtime_root,
                allow_source_informed=False,
                fake=False,
                from_fake_receipt=None,
                json=True,
            )
        )
        if apply_status != 0:
            return _finish(out, "failed", {"stage": "apply"}, apply_status)

    return _finish(
        out,
        "OK",
        {
            "manifest_path": str(manifest_dir / "source_research_manifest.json"),
            "research_path": str(research_dir),
            "package_path": str(package_dir),
            "apply_performed": bool(getattr(args, "apply", False)),
            "apply_status": apply_status,
        },
        0,
    )


def _finish(
    out: Path,
    status: str,
    payload: dict[str, Any],
    exit_code: int,
) -> tuple[dict[str, Any], int]:
    summary = {"schema_version": 1, "status": status, **payload}
    write_json(out / "configure_summary.json", summary)
    return summary, exit_code
