from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_ONLY_RUNTIME_SURFACES_FIELD = "default_only_runtime_surfaces"


def default_only_runtime_surface_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    _collect_default_only_runtime_surface_errors(payload, errors)
    return errors


def has_default_only_runtime_surfaces(payload: Mapping[str, Any]) -> bool:
    surfaces = payload.get(DEFAULT_ONLY_RUNTIME_SURFACES_FIELD)
    if DEFAULT_ONLY_RUNTIME_SURFACES_FIELD in payload and not isinstance(
        surfaces,
        list,
    ):
        return True
    if isinstance(surfaces, list) and any(str(surface).strip() for surface in surfaces):
        return True

    records = payload.get("records")
    return isinstance(records, list) and any(
        isinstance(record, Mapping) and has_default_only_runtime_surfaces(record)
        for record in records
    )


def _collect_default_only_runtime_surface_errors(
    payload: Mapping[str, Any],
    errors: list[str],
) -> None:
    surfaces = payload.get(DEFAULT_ONLY_RUNTIME_SURFACES_FIELD)
    if DEFAULT_ONLY_RUNTIME_SURFACES_FIELD in payload and not isinstance(
        surfaces,
        list,
    ):
        errors.append(f"{DEFAULT_ONLY_RUNTIME_SURFACES_FIELD}_must_be_list")

    records = payload.get("records")
    if not isinstance(records, list):
        return
    for record in records:
        if isinstance(record, Mapping):
            _collect_default_only_runtime_surface_errors(record, errors)
