from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hsconfig.package_io import read_optional_profile, read_required_baseline
from hsconfig.validate_package import validate_config_package


def strict_validation_passed(report: dict[str, Any]) -> bool:
    return report.get("status") == "passed" and not report.get("errors")


def validate_complete_package(package: str | Path) -> dict[str, Any]:
    """Run the strict complete-package contract used by every caller."""
    package_path = Path(package)
    baseline = read_required_baseline(package_path)
    profile = read_optional_profile(package_path)
    report = validate_config_package(
        package_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    linked_runtime_errors = _validate_linked_runtime_entities(package_path)
    if not linked_runtime_errors:
        return report
    return {
        **report,
        "status": "failed",
        "errors": [*report.get("errors", []), *linked_runtime_errors],
    }


def _validate_linked_runtime_entities(package_path: Path) -> list[str]:
    behavior_plan_path = (
        package_path / "reports" / "card_behavior_plan_report.json"
    )
    if not behavior_plan_path.is_file():
        return []
    try:
        behavior_plan = json.loads(
            behavior_plan_path.read_text(encoding="utf-8-sig")
        )
    except (OSError, ValueError):
        return []
    if not isinstance(behavior_plan, dict):
        return []

    deck_dirs = sorted(
        path
        for path in (package_path / "CustomConfig").glob("*")
        if path.is_dir()
    )
    errors: list[str] = []
    for runtime_card_id in _linked_runtime_card_ids(behavior_plan):
        filename = f"{runtime_card_id}.json"
        matching_paths = [
            deck_dir / filename
            for deck_dir in deck_dirs
            if (deck_dir / filename).is_file()
        ]
        if not matching_paths:
            errors.append(
                "linked runtime entity missing required owner file: "
                f"{filename}"
            )
            continue
        for path in matching_paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            actual = payload.get("GameCardId")
            if actual != runtime_card_id:
                errors.append(
                    "linked runtime entity filename/GameCardId mismatch: "
                    f"{filename} owns {runtime_card_id}, got {actual}"
                )
    return errors


def _linked_runtime_card_ids(behavior_plan: dict[str, Any]) -> list[str]:
    runtime_card_ids: set[str] = set()
    for row in behavior_plan.get("rows", []):
        if not isinstance(row, dict):
            continue
        source_card_id = str(row.get("source_card_id") or row.get("card_id") or "")
        runtime_card_id = str(row.get("runtime_card_id") or row.get("card_id") or "")
        if (
            row.get("meaningful_runtime_surface") is True
            and source_card_id
            and runtime_card_id
            and source_card_id != runtime_card_id
        ):
            runtime_card_ids.add(runtime_card_id)
    return sorted(runtime_card_ids)
