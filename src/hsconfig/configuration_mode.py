"""Configuration-mode authority at the frozen package boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal


ConfigurationMode = Literal["CONSERVATIVE", "LLM_OPTIMIZED_START"]
CONSERVATIVE: ConfigurationMode = "CONSERVATIVE"
LLM_OPTIMIZED_START: ConfigurationMode = "LLM_OPTIMIZED_START"


def configuration_mode_from_manifest(
    manifest: Mapping[str, Any],
) -> ConfigurationMode:
    if not isinstance(manifest, Mapping):
        raise ValueError("configuration_mode_invalid")
    if "configuration_mode" not in manifest:
        return CONSERVATIVE
    value = manifest["configuration_mode"]
    if isinstance(value, str) and value in {
        CONSERVATIVE,
        LLM_OPTIMIZED_START,
    }:
        return value
    raise ValueError("configuration_mode_invalid")


__all__ = (
    "CONSERVATIVE",
    "LLM_OPTIMIZED_START",
    "ConfigurationMode",
    "configuration_mode_from_manifest",
)
