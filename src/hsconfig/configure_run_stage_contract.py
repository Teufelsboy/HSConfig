"""Dependency-light grammar for configure-run stage artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping


_MANIFEST_PATH = "package_manifest.json"
_SUMMARY_PATH = "configure_summary.json"


def configure_summary_bytes(
    *,
    deck_name: str,
    deck_fingerprint: str,
    paths: tuple[str, ...],
) -> bytes:
    """Return the canonical summary bound to one stage-path selection."""

    return _json_bytes(
        {
            "schema_version": 1,
            "deck_name": deck_name,
            "deck_fingerprint": deck_fingerprint,
            "unavailable_stages": _unavailable_stages(paths),
        }
    )


def validate_configure_run_stage_files(
    *,
    deck_name: str,
    deck_fingerprint: str,
    stage_files: Mapping[str, bytes],
) -> None:
    """Validate required-stage grammar and exact summary authority."""

    files = dict(stage_files)
    paths = tuple(sorted(files))
    _validate_required_stages(paths)
    expected = configure_summary_bytes(
        deck_name=deck_name,
        deck_fingerprint=deck_fingerprint,
        paths=paths,
    )
    if files.get(_SUMMARY_PATH) != expected:
        raise ValueError("configure_run_summary_mismatch")


def _validate_required_stages(paths: tuple[str, ...]) -> None:
    if any(
        path.casefold() == "04_package"
        or path.casefold().startswith("04_package/")
        or path.casefold() == _MANIFEST_PATH.casefold()
        or path.casefold().startswith(
            f"{_MANIFEST_PATH.casefold()}/"
        )
        or path.casefold().startswith(f"{_SUMMARY_PATH}/")
        for path in paths
    ):
        raise ValueError("configure_run_reserved_path")
    required = ("01_manifest/", "03_research/")
    if any(
        not any(path.startswith(prefix) for path in paths)
        for prefix in required
    ):
        raise ValueError("configure_run_required_stage_missing")
    source_paths = any(
        path.startswith("02_source_documents/") for path in paths
    )
    acquisition_paths = any(
        path.startswith("02_source_acquisition/") for path in paths
    )
    if source_paths == acquisition_paths:
        raise ValueError("configure_run_source_stage_invalid")
    autopilot_02 = any(
        path.startswith("02_source_autopilot/") for path in paths
    )
    autopilot_03 = any(
        path.startswith("03_source_autopilot/") for path in paths
    )
    if (
        (autopilot_02 and autopilot_03)
        or (source_paths and autopilot_03)
        or (acquisition_paths and autopilot_02)
    ):
        raise ValueError("configure_run_autopilot_stage_invalid")


def _unavailable_stages(paths: tuple[str, ...]) -> dict[str, str]:
    documents = any(
        path.startswith("02_source_documents/") for path in paths
    )
    acquisition = any(
        path.startswith("02_source_acquisition/") for path in paths
    )
    unavailable: dict[str, str] = {}
    if documents:
        unavailable["02_source_acquisition"] = (
            "02_source_documents_selected"
        )
    elif acquisition:
        unavailable["02_source_documents"] = (
            "02_source_acquisition_selected"
        )
    else:
        unavailable["02_source_documents"] = "not_requested"
        unavailable["02_source_acquisition"] = "not_requested"
    autopilot_02 = any(
        path.startswith("02_source_autopilot/") for path in paths
    )
    autopilot_03 = any(
        path.startswith("03_source_autopilot/") for path in paths
    )
    if not autopilot_02 and not autopilot_03:
        unavailable["02_source_autopilot"] = "not_requested"
        unavailable["03_source_autopilot"] = "not_requested"
    elif autopilot_02:
        unavailable["03_source_autopilot"] = (
            "02_source_autopilot_selected"
        )
    else:
        unavailable["02_source_autopilot"] = (
            "03_source_autopilot_selected"
        )
    return dict(sorted(unavailable.items()))


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        .encode("utf-8")
        + b"\n"
    )


__all__ = (
    "configure_summary_bytes",
    "validate_configure_run_stage_files",
)
