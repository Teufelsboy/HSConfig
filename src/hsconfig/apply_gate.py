from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.io import read_json


OPTIONAL_NORMAL_PATH_SURFACES = ("Presume.json", "Concede.json")


def evaluate_apply_gate(
    package_root: str | Path,
    *,
    allow_source_informed: bool = False,
) -> dict[str, Any]:
    package = Path(package_root)
    operator_path = package / "reports" / "operator_summary.json"
    if not operator_path.is_file():
        return _blocked(
            operator_path,
            {
                "reason": "missing_operator_summary",
                "path": str(operator_path),
            },
        )

    summary = read_json(operator_path)
    if not isinstance(summary, dict):
        return _blocked(
            operator_path,
            {
                "reason": "invalid_operator_summary",
                "path": str(operator_path),
            },
        )

    optional_surface_reasons = _optional_surface_reasons(summary)
    if optional_surface_reasons:
        return _blocked(operator_path, *optional_surface_reasons)

    technical_status = str(summary.get("technical_status", ""))
    semantic_status = str(summary.get("semantic_status", ""))
    next_action = str(summary.get("next_action", ""))
    apply_policy = str(summary.get("apply_policy", ""))

    if technical_status != "VALID_PACKAGE":
        return _blocked(
            operator_path,
            {
                "reason": "operator_summary_not_valid_package",
                "technical_status": technical_status,
                "next_action": next_action,
                "apply_policy": apply_policy,
            },
        )

    if (
        semantic_status == "SOURCE_BACKED_STRONG"
        and next_action == "READY_TO_APPLY_OR_HANDOFF"
        and apply_policy == "ALLOWED"
        and not summary.get("semantic_blockers")
    ):
        return _allowed(operator_path, mode="source_backed_strong", reasons=[])

    if (
        allow_source_informed
        and semantic_status in {"VALID_BUT_NOT_GUIDE_STRONG", "STATIC_SEMANTICS_USABLE"}
        and apply_policy == "ALLOWED_WITH_WARNINGS"
        and next_action
        in {
            "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "READY_WITH_WARNINGS",
            "RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG",
        }
    ):
        return _allowed(
            operator_path,
            mode="source_informed_with_warnings",
            reasons=[
                {
                    "reason": "source_informed_escape_hatch_used",
                    "semantic_status": semantic_status,
                    "next_action": next_action,
                    "apply_policy": apply_policy,
                }
            ],
        )

    return _blocked(
        operator_path,
        {
            "reason": "operator_summary_not_ready_to_apply",
            "technical_status": technical_status,
            "semantic_status": semantic_status,
            "next_action": next_action,
            "apply_policy": apply_policy,
        },
    )


def _optional_surface_reasons(summary: dict[str, Any]) -> list[dict[str, str]]:
    generated = summary.get("generated_files", [])
    if not isinstance(generated, list):
        return []
    reasons: list[dict[str, str]] = []
    for item in generated:
        generated_file = str(item)
        if generated_file.endswith(OPTIONAL_NORMAL_PATH_SURFACES):
            reasons.append(
                {
                    "reason": "normal_path_optional_surface_present",
                    "generated_file": generated_file,
                }
            )
    return reasons


def _allowed(
    operator_path: Path,
    *,
    mode: str,
    reasons: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "allowed",
        "operator_summary_path": str(operator_path),
        "mode": mode,
        "reasons": reasons,
    }


def _blocked(operator_path: Path, *reasons: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "blocked",
        "operator_summary_path": str(operator_path),
        "mode": "blocked",
        "reasons": list(reasons),
    }
