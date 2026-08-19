"""Closed top-level contracts shared by optimized starter documents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any


STARTER_SCHEMA_VERSION = 1

STARTER_CONTEXT_FILENAME = "starter_context.json"
STARTER_CANDIDATE_1_FILENAME = "candidate-1.json"
STARTER_CANDIDATE_2_FILENAME = "candidate-2.json"
STARTER_CANDIDATE_3_FILENAME = "candidate-3.json"
STARTER_DECISION_FILENAME = "starter_config_decision.json"
STARTER_FILENAMES = (
    STARTER_CONTEXT_FILENAME,
    STARTER_CANDIDATE_1_FILENAME,
    STARTER_CANDIDATE_2_FILENAME,
    STARTER_CANDIDATE_3_FILENAME,
    STARTER_DECISION_FILENAME,
)
STARTER_CANDIDATE_FILENAMES = (
    STARTER_CANDIDATE_1_FILENAME,
    STARTER_CANDIDATE_2_FILENAME,
    STARTER_CANDIDATE_3_FILENAME,
)

STARTER_CONTEXT_MAX_BYTES = 512 * 1024
STARTER_CANDIDATE_MAX_BYTES = 256 * 1024
STARTER_DECISION_MAX_BYTES = 64 * 1024

STARTER_CONTEXT_FIELDS = frozenset(
    {
        "schema_version",
        "deck_identity",
        "cards",
        "deck_shape",
        "supported_runtime_contract",
        "globalvalues_baseline",
        "source_evidence",
        "existing_claims",
        "known_safety_boundaries",
        "content_sha256",
    }
)
STARTER_CANDIDATE_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_id",
        "candidate_revision",
        "starter_context_sha256",
        "deck_fingerprint",
        "strategy_summary",
        "mulligan",
        "globalvalues",
        "card_rules",
        "combo",
        "card_dispositions",
        "rule_rationales",
        "assumptions",
        "content_sha256",
    }
)
STARTER_DECISION_FIELDS = frozenset(
    {
        "schema_version",
        "starter_context_sha256",
        "reviewed_candidates",
        "ranking",
        "selected_candidate_id",
        "selection_rationale",
        "strengths",
        "risks",
        "rejection_reasons",
        "critic_identity",
        "content_sha256",
    }
)
STARTER_STRATEGY_SUMMARY_FIELDS = frozenset({"role", "summary"})
STARTER_MULLIGAN_ROW_FIELDS = frozenset(
    {"rule_id", "selector_kind", "selector", "action", "condition"}
)
STARTER_CARD_RULE_FIELDS = frozenset(
    {
        "rule_id",
        "source_card_id",
        "runtime_card_id",
        "link_kind",
        "behavior_block",
        "condition",
        "value",
    }
)
STARTER_COMBO_FIELDS = frozenset(
    {"rule_id", "cards", "timing", "values", "condition"}
)
STARTER_CARD_DISPOSITION_FIELDS = frozenset(
    {"card_id", "disposition", "rule_ids", "reason"}
)
STARTER_REVIEWED_CANDIDATE_FIELDS = frozenset(
    {"candidate_id", "candidate_revision", "content_sha256"}
)
STARTER_CRITIC_IDENTITY_FIELDS = frozenset(
    {"kind", "review_id", "confidence"}
)


class StarterStrategyRole(str, Enum):
    """The three required materially distinct strategist roles."""

    PROACTIVE_TEMPO = "proactive_tempo"
    BALANCED = "balanced"
    RESOURCE_ORIENTED = "resource_oriented"


StarterCandidateRole = StarterStrategyRole


def validate_starter_sibling_name(value: object) -> str:
    """Return one of the closed starter-bundle filenames or fail closed."""

    if not isinstance(value, str) or value not in STARTER_FILENAMES:
        raise ValueError("starter_sibling_name_invalid")
    return value


def validate_candidate_revision(value: object) -> int:
    """Return a bounded strategist revision, excluding booleans."""

    if type(value) is not int or value not in {1, 2, 3}:
        raise ValueError("starter_candidate_revision_invalid")
    return value


def require_closed_object(
    value: object,
    *,
    expected_fields: frozenset[str],
    error: str,
) -> dict[str, Any]:
    """Copy a mapping only when its field set is exactly the contract set."""

    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError(error)
    return dict(value)


def require_nonempty_string(value: object, *, error: str) -> str:
    """Return a trimmed nonempty scalar string."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(error)
    return value


def require_string_list(value: object, *, error: str) -> list[str]:
    """Copy a JSON list containing only nonempty string scalars."""

    if (
        not isinstance(value, list)
        or any(
            not isinstance(item, str) or not item or item != item.strip()
            for item in value
        )
    ):
        raise ValueError(error)
    return list(value)


def require_object_list(value: object, *, error: str) -> list[dict[str, Any]]:
    """Copy a JSON list containing only mapping objects."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(error)
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(error)
        result.append(dict(item))
    return result


def reject_path_like_fields(value: object, *, error: str) -> None:
    """Reject document-controlled filesystem-authority field names recursively."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                not isinstance(key, str)
                or key == "path"
                or key.endswith("_path")
                or key.endswith("_paths")
            ):
                raise ValueError(error)
            reject_path_like_fields(item, error=error)
    elif isinstance(value, list):
        for item in value:
            reject_path_like_fields(item, error=error)


__all__ = (
    "STARTER_CANDIDATE_1_FILENAME",
    "STARTER_CANDIDATE_2_FILENAME",
    "STARTER_CANDIDATE_3_FILENAME",
    "STARTER_CANDIDATE_FILENAMES",
    "STARTER_CANDIDATE_FIELDS",
    "STARTER_CANDIDATE_MAX_BYTES",
    "STARTER_CONTEXT_FIELDS",
    "STARTER_CONTEXT_FILENAME",
    "STARTER_CONTEXT_MAX_BYTES",
    "STARTER_CARD_DISPOSITION_FIELDS",
    "STARTER_CARD_RULE_FIELDS",
    "STARTER_COMBO_FIELDS",
    "STARTER_CRITIC_IDENTITY_FIELDS",
    "STARTER_DECISION_FIELDS",
    "STARTER_DECISION_FILENAME",
    "STARTER_DECISION_MAX_BYTES",
    "STARTER_FILENAMES",
    "STARTER_MULLIGAN_ROW_FIELDS",
    "STARTER_REVIEWED_CANDIDATE_FIELDS",
    "STARTER_SCHEMA_VERSION",
    "STARTER_STRATEGY_SUMMARY_FIELDS",
    "StarterCandidateRole",
    "StarterStrategyRole",
    "reject_path_like_fields",
    "require_closed_object",
    "require_nonempty_string",
    "require_object_list",
    "require_string_list",
    "validate_candidate_revision",
    "validate_starter_sibling_name",
)
