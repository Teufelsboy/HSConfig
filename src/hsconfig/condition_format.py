from __future__ import annotations

from typing import Any


REPORT_ONLY_CONDITION_KEYS = {"phase", "posture"}


def lower_runtime_condition(value: Any) -> tuple[str, str | None]:
    if value in (None, "", {}):
        return "*", None
    if isinstance(value, str):
        cleaned = " ".join(value.strip().split())
        return cleaned or "*", None
    if isinstance(value, dict):
        if "runtime_condition" in value:
            return lower_runtime_condition(value["runtime_condition"])
        keys = {str(key) for key in value}
        if keys <= REPORT_ONLY_CONDITION_KEYS:
            return "*", None
        return "*", "unsupported_condition"
    return "*", "unsupported_condition"
