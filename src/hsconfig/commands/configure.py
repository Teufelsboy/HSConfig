from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hsconfig.commands.apply import apply_payload, validate_payload
from hsconfig.commands.common import emit_result
from hsconfig.commands.source_workflow import (
    draft_source_documents_payload,
    research_deck_payload,
    source_manifest_payload,
)
from hsconfig.package_builder import prepare_package_payload
from hsconfig.io import write_json
from hsconfig.package_io import prepare_research_output_dir


def run_configure_command(args: argparse.Namespace) -> int:
    try:
        payload, status = configure_payload(args)
    except Exception as exc:
        payload, status = _finish_stage_exception_for_args(args, "configure", exc)
    return emit_result(payload, bool(getattr(args, "json", False)), status)


def configure_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)

    manifest_dir = out / "01_manifest"
    draft_dir = out / "02_source_documents"
    research_dir = out / "03_research"
    package_dir = out / "04_package"
    for stage_dir in (manifest_dir, draft_dir, research_dir, package_dir):
        stage_dir.mkdir(parents=True, exist_ok=True)

    common = {
        "deck_name": args.deck_name,
        "deck_code": args.deck_code,
        "cards_json": getattr(args, "cards_json", None),
        "collectible_cards_json": getattr(args, "collectible_cards_json", None),
        "full_cards_json": getattr(args, "full_cards_json", None),
        "allow_placeholder": bool(getattr(args, "allow_placeholder", False)),
        "json": True,
    }

    try:
        manifest_payload, manifest_status = source_manifest_payload(
            SimpleNamespace(**common, out=str(manifest_dir))
        )
    except Exception as exc:
        return _finish_stage_exception(out, "source-manifest", exc)
    if manifest_status != 0:
        return _finish(
            out,
            "failed",
            {"stage": "source-manifest", **manifest_payload},
            manifest_status,
        )

    source_documents_json = None
    if getattr(args, "source_evidence_json", None):
        try:
            draft_payload, draft_status = draft_source_documents_payload(
                SimpleNamespace(
                    **common,
                    source_evidence_json=args.source_evidence_json,
                    out=str(draft_dir),
                )
            )
        except Exception as exc:
            return _finish_stage_exception(out, "draft-source-documents", exc)
        if draft_status != 0:
            return _finish(
                out,
                "failed",
                {"stage": "draft-source-documents", **draft_payload},
                draft_status,
            )
        source_documents_json = draft_dir / "source_documents.json"

    research_source_evidence_json = None
    if source_documents_json is None:
        research_source_evidence_json = getattr(args, "source_evidence_json", None)
    try:
        research_payload, research_status = research_deck_payload(
            SimpleNamespace(
                **common,
                out=str(research_dir),
                source_documents_json=str(source_documents_json) if source_documents_json else None,
                source_evidence_json=research_source_evidence_json,
                guide_sources_json=None,
                claims_json=None,
                skip_semantic_fetch=False,
                auto_research_fallback=True,
            )
        )
    except Exception as exc:
        return _finish_stage_exception(out, "research-deck", exc)
    if research_status != 0:
        return _finish(
            out,
            "failed",
            {"stage": "research-deck", **research_payload},
            research_status,
        )

    try:
        prepare_payload, prepare_status = prepare_package_payload(
            SimpleNamespace(
                deck_name=args.deck_name,
                deck_code=args.deck_code,
                out=str(package_dir),
                runtime_root=args.runtime_root,
                guide_sources_json=str(research_dir / "guide_sources.json"),
                source_documents_json=(
                    str(source_documents_json) if source_documents_json else None
                ),
                cards_json=getattr(args, "cards_json", None),
                collectible_cards_json=getattr(args, "collectible_cards_json", None),
                full_cards_json=getattr(args, "full_cards_json", None),
                claims_json=None,
                plan_reports_dir=None,
                allow_placeholder=bool(getattr(args, "allow_placeholder", False)),
                auto_research_fallback=True,
                json=True,
            )
        )
    except Exception as exc:
        return _finish_stage_exception(out, "prepare", exc)
    if prepare_status != 0:
        return _finish(out, "failed", {"stage": "prepare", **prepare_payload}, prepare_status)

    try:
        validate_payload_result, validate_status = validate_payload(
            SimpleNamespace(package=str(package_dir), json=True)
        )
    except Exception as exc:
        return _finish_stage_exception(out, "validate", exc)
    if validate_status != 0:
        return _finish(
            out,
            "failed",
            {"stage": "validate", **validate_payload_result},
            validate_status,
        )

    apply_status = None
    if bool(getattr(args, "apply", False)):
        try:
            apply_payload_result, apply_status = apply_payload(
                SimpleNamespace(
                    package=str(package_dir),
                    runtime_root=args.runtime_root,
                    allow_source_informed=False,
                    fake=False,
                    from_fake_receipt=None,
                    json=True,
                )
            )
        except Exception as exc:
            return _finish_stage_exception(out, "apply", exc)
        if apply_status != 0:
            return _finish(out, "failed", {"stage": "apply", **apply_payload_result}, apply_status)

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


def _finish_stage_exception(out: Path, stage: str, exc: Exception) -> tuple[dict[str, Any], int]:
    return _finish(out, "failed", _stage_exception_payload(stage, exc), 1)


def _finish_stage_exception_for_args(
    args: argparse.Namespace,
    stage: str,
    exc: Exception,
) -> tuple[dict[str, Any], int]:
    payload = {
        "schema_version": 1,
        "status": "failed",
        **_stage_exception_payload(stage, exc),
    }
    out_value = getattr(args, "out", None)
    if out_value is None:
        return payload, 1
    try:
        return _finish(Path(out_value), "failed", _stage_exception_payload(stage, exc), 1)
    except Exception:
        return payload, 1


def _stage_exception_payload(stage: str, exc: Exception) -> dict[str, Any]:
    return {"stage": stage, "errors": [str(exc)]}
