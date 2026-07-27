from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hsconfig.package_io import read_optional_profile, read_required_baseline
from hsconfig.runtime_entity_owner import (
    LINKED_RUNTIME_ENTITY_RELATION_INVALID,
    linked_runtime_entity_semantic_surface,
    runtime_entity_owner_relation_is_authorized,
)
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
    linked_relations, relation_errors = _linked_runtime_relations(
        behavior_plan
    )
    errors.extend(relation_errors)
    for relation in linked_relations:
        runtime_card_id = relation["runtime_card_id"]
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


def _linked_runtime_relations(
    behavior_plan: dict[str, Any],
) -> tuple[list[dict[str, str]], list[str]]:
    relations: list[dict[str, str]] = []
    errors: list[str] = []
    for row in behavior_plan.get("rows", []):
        if not isinstance(row, dict):
            continue
        source_card_id = str(
            row.get("source_card_id") or row.get("card_id") or ""
        ).strip()
        runtime_card_id = str(
            row.get("runtime_card_id") or row.get("card_id") or ""
        ).strip()
        link_kind = str(row.get("link_kind") or "self").strip()
        if (
            not source_card_id
            or not runtime_card_id
            or (
                source_card_id == runtime_card_id
                and link_kind == "self"
            )
        ):
            continue
        behavior_block = str(row.get("behavior_block") or "").strip()
        semantic_surface = linked_runtime_entity_semantic_surface(
            behavior_block=behavior_block,
            link_kind=link_kind,
        )
        relation = {
            "source_card_id": source_card_id,
            "semantic_reason": semantic_surface or "",
            "link_kind": link_kind,
            "runtime_card_id": runtime_card_id,
        }
        if (
            row.get("meaningful_runtime_surface") is not True
            or semantic_surface is None
            or not runtime_entity_owner_relation_is_authorized(**relation)
        ):
            errors.append(
                f"{LINKED_RUNTIME_ENTITY_RELATION_INVALID}: "
                f"source={source_card_id}, "
                f"semantic={semantic_surface or 'unauthorized'}, "
                f"link={link_kind}, block={behavior_block or 'missing'}, "
                f"runtime={runtime_card_id}"
            )
            continue
        relations.append(relation)
    return (
        sorted(
            relations,
            key=lambda row: (
                row["source_card_id"],
                row["semantic_reason"],
                row["link_kind"],
                row["runtime_card_id"],
            ),
        ),
        errors,
    )
