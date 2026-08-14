from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from hsconfig.io import decode_json_bytes
from hsconfig.package_io import (
    read_optional_profile,
    read_required_baseline,
    read_required_globalvalues_authority_matrix,
)
from hsconfig.package_model import DirectoryPackageView, PackageView
from hsconfig.pre_run_metrics import (
    PRE_RUN_REPORT_PATHS,
    validate_pre_run_package_reports,
)
from hsconfig.runtime_entity_owner import (
    AUTHORIZED_HERO_POWER_OWNER,
    LINKED_RUNTIME_ENTITY_RELATION_INVALID,
    linked_runtime_entity_semantic_surface,
    runtime_entity_owner_relation_is_authorized,
)
from hsconfig.runtime_surface_ledger import (
    rederive_runtime_surface_ledger_from_package,
    rederive_runtime_surface_ledger_from_view,
)
from hsconfig.validate_package import (
    _reject_nonstandard_json_constant,
    _validate_blocks,
    _validate_top_level,
    validate_config_package,
)
from hsconfig.visionai_registry import REQUIRED_RUNTIME_SURFACES, supported_surface


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
    legacy_pre_run_contract_version: int | None = None,
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
    pre_run_contract_errors = _validate_pre_run_contract_reports(
        package_path,
        legacy_contract_version=legacy_pre_run_contract_version,
    )
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
        and not pre_run_contract_errors
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
            *pre_run_contract_errors,
        ],
    }


def validate_complete_package_from_view(
    package: PackageView,
    *,
    allow_legacy_globalvalues: bool = False,
    legacy_pre_run_contract_version: int | None = None,
) -> dict[str, Any]:
    """Run the strict complete-package contract without filesystem adaptation."""

    baseline = _required_view_mapping(
        package,
        "reports/globalvalues_baseline.json",
        "GlobalValues baseline",
    )
    profile = _optional_view_mapping(
        package,
        "reports/globalvalues_profile.json",
        "GlobalValues profile",
    )
    authority_matrix = _optional_view_mapping(
        package,
        "reports/global_values_authority_matrix.json",
        "GlobalValues authority matrix",
    )
    report = _validate_config_package_view(
        package,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        globalvalues_authority_matrix=authority_matrix,
    )
    linked_runtime_errors = _validate_linked_runtime_entities_view(package)
    physical_surface_errors = _validate_runtime_surface_ledger_view(package)
    pre_run_contract_errors = _validate_pre_run_contract_reports_view(
        package,
        legacy_contract_version=legacy_pre_run_contract_version,
    )
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
        and not pre_run_contract_errors
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
            *pre_run_contract_errors,
        ],
    }


def _validate_config_package_view(
    package: PackageView,
    *,
    globalvalues_baseline: dict[str, Any],
    globalvalues_profile: dict[str, Any] | None,
    globalvalues_authority_matrix: dict[str, Any] | None,
) -> dict[str, Any]:
    errors: list[str] = []
    checked_files = 0
    direct_paths = tuple(
        sorted(
            name
            for name in package.file_names()
            if name.startswith("CustomConfig/")
            and len(name.split("/")) == 3
        )
    )
    deck_names = tuple(sorted({name.split("/")[1] for name in direct_paths}))
    if not deck_names:
        errors.append("memory:/CustomConfig: no deck config directories found")
    elif len(deck_names) > 1:
        errors.append(
            "memory:/CustomConfig: expected exactly one deck config directory "
            f"for complete package, found {len(deck_names)}: "
            f"{', '.join(deck_names)}"
        )
    for deck_name in deck_names:
        file_names = tuple(
            sorted(
                name.rsplit("/", 1)[-1]
                for name in direct_paths
                if name.split("/")[1] == deck_name
            )
        )
        for required in sorted(REQUIRED_RUNTIME_SURFACES):
            if required not in file_names:
                errors.append(
                    f"memory:/CustomConfig/{deck_name}: "
                    f"missing required runtime file {required}"
                )
        for relative_path in (
            name
            for name in direct_paths
            if name.split("/")[1] == deck_name
        ):
            path = Path("memory:") / relative_path
            if not supported_surface(path.name):
                errors.append(f"{path}: unsupported VisionAI surface")
                continue
            checked_files += 1
            try:
                data = json.loads(
                    package.read_bytes(relative_path).decode("utf-8-sig"),
                    parse_constant=_reject_nonstandard_json_constant,
                )
            except Exception as exc:
                errors.append(f"{path}: invalid JSON: {exc}")
                continue
            if not isinstance(data, dict):
                errors.append(
                    f"{path}: top-level JSON value must be an object"
                )
                continue
            errors.extend(_validate_top_level(path, data))
            errors.extend(
                _validate_blocks(
                    path,
                    data,
                    globalvalues_baseline=globalvalues_baseline,
                    globalvalues_profile=globalvalues_profile,
                    globalvalues_authority_matrix=(
                        globalvalues_authority_matrix
                    ),
                    require_globalvalues_profile=True,
                )
            )
        if globalvalues_profile is None:
            errors.append(
                f"memory:/CustomConfig/{deck_name}: "
                "missing required GlobalValues profile"
            )
    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "checked_files": checked_files,
    }


def _validate_pre_run_contract_reports(
    package_path: Path,
    *,
    legacy_contract_version: int | None,
) -> list[str]:
    view = DirectoryPackageView(package_path)
    if not any(view.exists(path) for path in PRE_RUN_REPORT_PATHS):
        marker = None
        if view.exists("reports/input_manifest.json"):
            try:
                manifest = view.read_json("reports/input_manifest.json")
            except (OSError, UnicodeDecodeError, ValueError):
                manifest = None
            if isinstance(manifest, Mapping):
                marker = manifest.get(
                    "pre_run_contract_schema_version"
                )
        if legacy_contract_version == 0 and marker is None:
            return []
        return [
            "pre_run_contract_validation_failed:"
            "pre_run_current_reports_missing"
        ]
    try:
        validate_pre_run_package_reports(view)
    except (OSError, TypeError, ValueError) as error:
        return [f"pre_run_contract_validation_failed:{error}"]
    return []


def _validate_pre_run_contract_reports_view(
    package: PackageView,
    *,
    legacy_contract_version: int | None,
) -> list[str]:
    if not any(package.exists(path) for path in PRE_RUN_REPORT_PATHS):
        marker = None
        if package.exists("reports/input_manifest.json"):
            try:
                manifest = package.read_json(
                    "reports/input_manifest.json"
                )
            except (OSError, UnicodeDecodeError, ValueError):
                manifest = None
            if isinstance(manifest, Mapping):
                marker = manifest.get("pre_run_contract_schema_version")
        if legacy_contract_version == 0 and marker is None:
            return []
        return [
            "pre_run_contract_validation_failed:"
            "pre_run_current_reports_missing"
        ]
    try:
        validate_pre_run_package_reports(package)
    except (OSError, TypeError, ValueError) as error:
        return [f"pre_run_contract_validation_failed:{error}"]
    return []


def _validate_runtime_surface_ledger(package_path: Path) -> list[str]:
    """Validate the serialized schema-2 ledger against physical package files."""
    path = package_path / "reports" / "runtime_surface_ledger.json"
    if not path.is_file():
        return ["runtime_surface_ledger_missing"]
    try:
        ledger = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return ["runtime_surface_ledger_invalid"]
    if not isinstance(ledger, Mapping):
        return ["runtime_surface_ledger_invalid"]

    if (
        type(ledger.get("schema_version")) is not int
        or ledger.get("schema_version") != 2
    ):
        return ["runtime_surface_ledger_schema_invalid"]
    try:
        rederived = rederive_runtime_surface_ledger_from_package(package_path)
    except (OSError, ValueError, TypeError):
        return ["runtime_surface_ledger_rederive_failed"]

    errors: list[str] = []
    if ledger.get("surface_ledger_sha256") != rederived.get("surface_ledger_sha256"):
        errors.append("runtime_surface_ledger_sha256_mismatch")
    if _canonical_json(ledger) != _canonical_json(rederived):
        errors.append("runtime_surface_ledger_content_mismatch")

    for value in rederived.get("physical_errors", []):
        errors.append(f"runtime_surface_ledger_physical_error:{value}")
    for row in rederived.get("unexpected_runtime_emissions", []):
        if isinstance(row, Mapping):
            errors.append(
                "runtime_surface_ledger_unexpected_emission:"
                f"{row.get('card_id', '')}:{row.get('reason', '')}"
            )
        else:
            errors.append("runtime_surface_ledger_unexpected_emission:invalid")
    for row in rederived.get("linked_runtime_owner_collisions", []):
        if isinstance(row, Mapping):
            errors.append(
                "runtime_surface_ledger_owner_collision:"
                f"{row.get('runtime_card_id', '')}"
            )
        else:
            errors.append("runtime_surface_ledger_owner_collision:invalid")
    return sorted(set(errors))


def _validate_runtime_surface_ledger_view(
    package: PackageView,
) -> list[str]:
    path = "reports/runtime_surface_ledger.json"
    if not package.exists(path):
        return ["runtime_surface_ledger_missing"]
    try:
        ledger = decode_json_bytes(package.read_bytes(path))
    except (OSError, ValueError):
        return ["runtime_surface_ledger_invalid"]
    if not isinstance(ledger, Mapping):
        return ["runtime_surface_ledger_invalid"]
    if (
        type(ledger.get("schema_version")) is not int
        or ledger.get("schema_version") != 2
    ):
        return ["runtime_surface_ledger_schema_invalid"]
    try:
        rederived = rederive_runtime_surface_ledger_from_view(package)
    except (OSError, ValueError, TypeError):
        return ["runtime_surface_ledger_rederive_failed"]
    return _runtime_surface_ledger_errors(ledger, rederived)


def _runtime_surface_ledger_errors(
    ledger: Mapping[str, Any],
    rederived: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if (
        ledger.get("surface_ledger_sha256")
        != rederived.get("surface_ledger_sha256")
    ):
        errors.append("runtime_surface_ledger_sha256_mismatch")
    if _canonical_json(ledger) != _canonical_json(rederived):
        errors.append("runtime_surface_ledger_content_mismatch")
    for value in rederived.get("physical_errors", []):
        errors.append(f"runtime_surface_ledger_physical_error:{value}")
    for row in rederived.get("unexpected_runtime_emissions", []):
        if isinstance(row, Mapping):
            errors.append(
                "runtime_surface_ledger_unexpected_emission:"
                f"{row.get('card_id', '')}:{row.get('reason', '')}"
            )
        else:
            errors.append(
                "runtime_surface_ledger_unexpected_emission:invalid"
            )
    for row in rederived.get("linked_runtime_owner_collisions", []):
        if isinstance(row, Mapping):
            errors.append(
                "runtime_surface_ledger_owner_collision:"
                f"{row.get('runtime_card_id', '')}"
            )
        else:
            errors.append("runtime_surface_ledger_owner_collision:invalid")
    return sorted(set(errors))


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _required_view_mapping(
    package: PackageView,
    relative_path: str,
    label: str,
) -> dict[str, Any]:
    if not package.exists(relative_path):
        raise ValueError(f"Missing {label} report: {relative_path}")
    value = decode_json_bytes(package.read_bytes(relative_path))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object: {relative_path}")
    return value


def _optional_view_mapping(
    package: PackageView,
    relative_path: str,
    label: str,
) -> dict[str, Any] | None:
    if not package.exists(relative_path):
        return None
    value = decode_json_bytes(package.read_bytes(relative_path))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object: {relative_path}")
    return value


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


def _validate_linked_runtime_entities_view(
    package: PackageView,
) -> list[str]:
    behavior_path = "reports/card_behavior_plan_report.json"
    if not package.exists(behavior_path):
        if _has_curated_linked_runtime_owner_file_view(package):
            return [LINKED_RUNTIME_OWNER_EVIDENCE_MISSING]
        return []
    try:
        behavior_plan = decode_json_bytes(package.read_bytes(behavior_path))
    except (OSError, ValueError):
        return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]
    if not isinstance(behavior_plan, Mapping):
        return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]
    has_curated_owner = _has_curated_linked_runtime_owner_file_view(
        package
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
    runtime_names = set(package.file_names())
    for relation in linked_relations:
        runtime_card_id = relation["runtime_card_id"]
        filename = f"{runtime_card_id}.json"
        matching_paths = sorted(
            name
            for name in runtime_names
            if name.startswith("CustomConfig/")
            and name.endswith(f"/{filename}")
            and len(name.split("/")) == 3
        )
        if not matching_paths:
            errors.append(
                "linked runtime entity missing required owner file: "
                f"{filename}"
            )
            continue
        for relative_path in matching_paths:
            try:
                payload = decode_json_bytes(
                    package.read_bytes(relative_path)
                )
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


def _has_curated_linked_runtime_owner_file_view(
    package: PackageView,
) -> bool:
    runtime_card_id = AUTHORIZED_HERO_POWER_OWNER[3]
    return any(
        name.startswith("CustomConfig/")
        and name.endswith(f"/{runtime_card_id}.json")
        and len(name.split("/")) == 3
        for name in package.file_names()
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
