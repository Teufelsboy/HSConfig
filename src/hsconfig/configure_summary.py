"""Stable in-memory configure summary projections."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_configure_summary(
    status: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not status:
        raise ValueError("configure_summary_status_required")
    return {
        "schema_version": 1,
        "status": status,
        **deepcopy(payload),
    }


def build_stage_failure_summary(
    stage: str,
    error: BaseException,
) -> dict[str, Any]:
    if not stage:
        raise ValueError("configure_failure_stage_required")
    return build_configure_summary(
        "failed",
        {
            "stage": stage,
            "errors": [str(error)],
        },
    )
