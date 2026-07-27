from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from hsconfig.package_io import (
    read_optional_profile,
    read_required_baseline,
    read_required_globalvalues_authority_matrix,
)
from hsconfig.runtime_entity_owner import (
    AUTHORIZED_HERO_POWER_OWNER,
    LINKED_RUNTIME_ENTITY_RELATION_INVALID,
    linked_runtime_entity_semantic_surface,
    runtime_entity_owner_relation_is_authorized,
)
from hsconfig.validate_package import validate_config_package


LINKED_RUNTIME_OWNER_EVIDENCE_MISSING = (
    "linked_runtime_owner_evidence_missing"
)
LINKED_RUNTIME_OWNER_EVIDENCE_INVALID = (
    "linked_runtime_owner_evidence_invalid"
)


def strict_validation_passed(report: dict[str, Any]) -> bool:
    return report.get("status") == "passed" and not report.get("errors")


def validate_complete_package(
    package: str | Path,
    *,
    allow_legacy_globalvalues: bool = False,
) -> dict[str, Any]:
    """Run the strict complete-package contract used by every caller."""
    package_path = Path(package)
    baseline = read_required_baseline(package_path)
    profile = read_optional_profile(package_path)
    authority_matrix_path = (
        package_path / "reports" / "global_values_authority_matrix.json"
    )
    authority_matrix = (
        read_required_globalvalues_authority_matrix(package_path)
        if authority_matrix_path.is_file()
        else None
    )
    report = validate_config_package(
        package_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        globalvalues_authority_matrix=authority_matrix,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    linked_runtime_errors = _validate_linked_runtime_entities(package_path)
    physical_surface_errors = _validate_runtime_surface_ledger(package_path)
    globalvalues_contract_errors = []
    if authority_matrix is None and not allow_legacy_globalvalues:
        globalvalues_contract_errors.append(
            "GlobalValues current contract requires authority matrix "
            "reports/global_values_authority_matrix.json"
        )
    if (
        not linked_runtime_errors
        and not physical_surface_errors
        and not globalvalues_contract_errors
    ):
        return report
    return {
        **report,
        "status": "failed",
        "errors": [
            *report.get("errors", []),
            *globalvalues_contract_errors,
            *linked_runtime_errors,
            *physical_surface_errors,
        ],
    }


def _validate_runtime_surface_ledger(package_path: Path) -> list[str]:
    """Fail strict validation when the physical ledger reports unsafe output."""
    path = package_path / "reports" / "runtime_surface_ledger.json"
    if not path.is_file():
        return []
    try:
        ledger = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return ["runtime_surface_ledger_invalid"]
    if not isinstance(ledger, Mapping):
        return ["runtime_surface_ledger_invalid"]

    errors: list[str] = []
    for value in ledger.get("physical_errors", []):
        errors.append(f"runtime_surface_ledger_physical_error:{value}")
    for row in ledger.get("unexpected_runtime_emissions", []):
        if isinstance(row, Mapping):
            errors.append(
                "runtime_surface_ledger_unexpected_emission:"
                f"{row.get('card_id', '')}:{row.get('reason', '')}"
            )
        else:
            errors.append("runtime_surface_ledger_unexpected_emission:invalid")
    for row in ledger.get("linked_runtime_owner_collisions", []):
        if isinstance(row, Mapping):
            errors.append(
                "runtime_surface_ledger_owner_collision:"
                f"{row.get('runtime_card_id', '')}"
            )
        else:
            errors.append("runtime_surface_ledger_owner_collision:invalid")
    return sorted(set(errors))


def _validate_linked_runtime_entities(package_path: Path) -> list[str]:
    behavior_plan_path = (
        package_path / "reports" / "card_behavior_plan_report.json"
    )
    if not behavior_plan_path.is_file():
        if _has_curated_linked_runtime_owner_file(package_path):
            return [LINKED_RUNTIME_OWNER_EVIDENCE_MISSING]
        return []
    try:
        behavior_plan = json.loads(
            behavior_plan_path.read_text(encoding="utf-8-sig")
        )
    except (OSError, ValueError):
        return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]
    if not isinstance(behavior_plan, Mapping):
        return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]

    has_curated_owner = _has_curated_linked_runtime_owner_file(package_path)

    deck_dirs = sorted(
        path
        for path in (package_path / "CustomConfig").glob("*")
        if path.is_dir()
    )
    errors: list[str] = []
    try:
        linked_relations, relation_errors = _linked_runtime_relations(
            behavior_plan
        )
    except ValueError as error:
        if str(error) == LINKED_RUNTIME_OWNER_EVIDENCE_INVALID:
            return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]
        raise
    errors.extend(relation_errors)
    if has_curated_owner and not _has_curated_linked_runtime_owner_relation(
        linked_relations
    ):
        errors.append(LINKED_RUNTIME_OWNER_EVIDENCE_MISSING)
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


def _has_curated_linked_runtime_owner_relation(
    relations: list[dict[str, str]],
) -> bool:
    (
        source_card_id,
        semantic_surface,
        link_kind,
        runtime_card_id,
    ) = AUTHORIZED_HERO_POWER_OWNER
    return any(
        relation
        == {
            "source_card_id": source_card_id,
            "runtime_card_id": runtime_card_id,
            "link_kind": link_kind,
            "semantic_surface": semantic_surface,
            "behavior_block": "BeforeUseHeroPowerBonus",
        }
        for relation in relations
    )


def _has_curated_linked_runtime_owner_file(package_path: Path) -> bool:
    runtime_card_id = AUTHORIZED_HERO_POWER_OWNER[3]
    return any(
        path.is_file()
        for path in (package_path / "CustomConfig").glob(
            f"*/{runtime_card_id}.json"
        )
    )


def linked_runtime_owner_projection(
    behavior_plan: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Return the canonical, sorted linked-owner authority projection."""
    projection, _errors = _linked_runtime_relations(behavior_plan)
    return projection


def _linked_runtime_relations(
    behavior_plan: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[str]]:
    relations: list[dict[str, str]] = []
    errors: list[str] = []
    for row in _validated_behavior_plan_rows(behavior_plan):
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
        authorization_relation = {
            "source_card_id": source_card_id,
            "semantic_reason": semantic_surface or "",
            "link_kind": link_kind,
            "runtime_card_id": runtime_card_id,
        }
        if (
            row.get("meaningful_runtime_surface") is not True
            or semantic_surface is None
            or not runtime_entity_owner_relation_is_authorized(
                **authorization_relation
            )
        ):
            errors.append(
                f"{LINKED_RUNTIME_ENTITY_RELATION_INVALID}: "
                f"source={source_card_id}, "
                f"semantic={semantic_surface or 'unauthorized'}, "
                f"link={link_kind}, block={behavior_block or 'missing'}, "
                f"runtime={runtime_card_id}"
            )
            continue
        relations.append(
            {
                "source_card_id": source_card_id,
                "runtime_card_id": runtime_card_id,
                "link_kind": link_kind,
                "semantic_surface": semantic_surface,
                "behavior_block": behavior_block,
            }
        )
    return (
        sorted(
            relations,
            key=lambda row: (
                row["source_card_id"],
                row["runtime_card_id"],
                row["link_kind"],
                row["semantic_surface"],
                row["behavior_block"],
            ),
        ),
        errors,
    )


def _validated_behavior_plan_rows(
    behavior_plan: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    rows = behavior_plan.get("rows")
    if not isinstance(rows, list) or any(
        not isinstance(row, Mapping) for row in rows
    ):
        raise ValueError(LINKED_RUNTIME_OWNER_EVIDENCE_INVALID)
    return rows
