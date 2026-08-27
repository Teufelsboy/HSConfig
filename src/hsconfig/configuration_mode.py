"""Configuration-mode authority at the frozen package boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal


ConfigurationMode = Literal["CONSERVATIVE", "LLM_OPTIMIZED_START"]
OptimizedStartAuthoritySchema = Literal[
    "legacy_five_doc",
    "single_candidate_review_v1",
]
CONSERVATIVE: ConfigurationMode = "CONSERVATIVE"
LLM_OPTIMIZED_START: ConfigurationMode = "LLM_OPTIMIZED_START"
SINGLE_CANDIDATE_REVIEW_V1 = "single_candidate_review_v1"


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


def optimized_start_authority_schema_from_manifest(
    manifest: Mapping[str, Any],
) -> OptimizedStartAuthoritySchema | None:
    mode = configuration_mode_from_manifest(manifest)
    present = "optimized_start_authority_schema" in manifest
    if mode == CONSERVATIVE:
        if present:
            raise ValueError("optimized_start_authority_schema_forbidden")
        return None
    if not present:
        return "legacy_five_doc"
    if manifest["optimized_start_authority_schema"] != (
        SINGLE_CANDIDATE_REVIEW_V1
    ):
        raise ValueError("optimized_start_authority_schema_invalid")
    return SINGLE_CANDIDATE_REVIEW_V1


__all__ = (
    "CONSERVATIVE",
    "LLM_OPTIMIZED_START",
    "ConfigurationMode",
    "OptimizedStartAuthoritySchema",
    "SINGLE_CANDIDATE_REVIEW_V1",
    "configuration_mode_from_manifest",
    "optimized_start_authority_schema_from_manifest",
)
