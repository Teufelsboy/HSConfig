"""Fixed-sibling loading and independent critic selection validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from hsconfig.starter_candidate import (
    ValidatedStarterCandidate,
    validate_starter_candidate,
)
from hsconfig.starter_context import StarterContext
from hsconfig.starter_contract import (
    STARTER_CANDIDATE_FILENAMES,
    STARTER_CANDIDATE_FIELDS,
    STARTER_CANDIDATE_MAX_BYTES,
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_FILENAME,
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_CRITIC_IDENTITY_FIELDS,
    STARTER_DECISION_FIELDS,
    STARTER_DECISION_FILENAME,
    STARTER_DECISION_MAX_BYTES,
    STARTER_REVIEWED_CANDIDATE_FIELDS,
    STARTER_SCHEMA_VERSION,
    StarterStrategyRole,
    reject_path_like_fields,
    validate_candidate_revision,
)
from hsconfig.starter_document import (
    StarterDocument,
    load_starter_document,
)


_CONTENT_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_CRITIC_ROWS = 32
_MAX_CRITIC_TEXT = 4096


@dataclass(frozen=True, slots=True)
class ValidatedStarterSelection:
    context: StarterContext
    candidates: tuple[ValidatedStarterCandidate, ...]
    decision: StarterDocument
    selected: ValidatedStarterCandidate


def load_validated_starter_selection(
    decision_path: Path,
    *,
    current_context: StarterContext,
) -> ValidatedStarterSelection:
    """Read exactly the fixed sibling bundle and bind one critic selection."""

    path = Path(decision_path)
    if path.name != STARTER_DECISION_FILENAME:
        raise ValueError("starter_decision_filename_invalid")
    if not isinstance(current_context, StarterContext):
        raise TypeError("starter_selection_context_invalid")
    parent = path.parent
    context_document = load_starter_document(
        parent / STARTER_CONTEXT_FILENAME,
        maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
        expected_fields=STARTER_CONTEXT_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    if (
        context_document.content_sha256
        != current_context.document.content_sha256
        or context_document.canonical_json
        != current_context.document.canonical_json
    ):
        raise ValueError("starter_selection_context_mismatch")

    candidates = tuple(
        validate_starter_candidate(
            load_starter_document(
                parent / filename,
                maximum_bytes=STARTER_CANDIDATE_MAX_BYTES,
                expected_fields=STARTER_CANDIDATE_FIELDS,
                schema_version=STARTER_SCHEMA_VERSION,
            ),
            context=current_context,
        )
        for filename in STARTER_CANDIDATE_FILENAMES
    )
    _validate_candidate_set(candidates)

    decision = load_starter_document(
        path,
        maximum_bytes=STARTER_DECISION_MAX_BYTES,
        expected_fields=STARTER_DECISION_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    selected_id = _validate_decision(
        decision,
        current_context=current_context,
        candidates=candidates,
    )
    selected = next(
        candidate
        for candidate in candidates
        if candidate.candidate_id == selected_id
    )
    return ValidatedStarterSelection(
        context=current_context,
        candidates=candidates,
        decision=decision,
        selected=selected,
    )


def _validate_candidate_set(
    candidates: tuple[ValidatedStarterCandidate, ...],
) -> None:
    if len(candidates) != 3:
        raise ValueError("starter_selection_candidate_count_invalid")
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    if len(set(candidate_ids)) != 3:
        raise ValueError("starter_selection_candidate_ids_invalid")
    content_digests = [
        candidate.document.content_sha256 for candidate in candidates
    ]
    if len(set(content_digests)) != 3:
        raise ValueError("starter_selection_candidate_digests_invalid")
    if {candidate.strategy_role for candidate in candidates} != {
        role.value for role in StarterStrategyRole
    }:
        raise ValueError("starter_selection_candidate_roles_invalid")
    if len(
        {candidate.runtime_intent_sha256 for candidate in candidates}
    ) != 3:
        raise ValueError("starter_selection_runtime_intents_not_distinct")


def _validate_decision(
    decision: StarterDocument,
    *,
    current_context: StarterContext,
    candidates: tuple[ValidatedStarterCandidate, ...],
) -> str:
    value = decision.to_value()
    if set(value) != STARTER_DECISION_FIELDS:
        raise ValueError("starter_decision_fields_invalid")
    reject_path_like_fields(value, error="starter_decision_path_forbidden")
    if value.get("starter_context_sha256") != (
        current_context.document.content_sha256
    ):
        raise ValueError("starter_decision_context_sha256_mismatch")
    candidate_by_id = {
        candidate.candidate_id: candidate for candidate in candidates
    }
    candidate_ids = set(candidate_by_id)
    _validate_reviewed_candidates(
        value.get("reviewed_candidates"),
        candidate_by_id=candidate_by_id,
    )

    ranking = value.get("ranking")
    if (
        not isinstance(ranking, list)
        or len(ranking) != 3
        or any(not isinstance(candidate_id, str) for candidate_id in ranking)
        or len(set(ranking)) != 3
        or set(ranking) != candidate_ids
    ):
        raise ValueError("starter_decision_ranking_invalid")
    selected_id = value.get("selected_candidate_id")
    if (
        not isinstance(selected_id, str)
        or selected_id not in candidate_ids
        or ranking[0] != selected_id
    ):
        raise ValueError("starter_decision_selected_candidate_invalid")
    rejected_ids = candidate_ids - {str(selected_id)}
    rejection_reasons = value.get("rejection_reasons")
    if (
        not isinstance(rejection_reasons, Mapping)
        or set(rejection_reasons) != rejected_ids
        or any(
            not _nonempty_text(reason)
            for reason in rejection_reasons.values()
        )
    ):
        raise ValueError("starter_decision_rejection_reasons_invalid")

    if not _nonempty_text(value.get("selection_rationale")):
        raise ValueError("starter_decision_selection_rationale_invalid")
    _validate_critic_text_list(value.get("strengths"), field="strengths")
    _validate_critic_text_list(value.get("risks"), field="risks")
    _validate_critic_identity(value.get("critic_identity"))
    return str(selected_id)


def _validate_reviewed_candidates(
    value: object,
    *,
    candidate_by_id: Mapping[str, ValidatedStarterCandidate],
) -> None:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("starter_decision_reviewed_candidates_invalid")
    reviewed: dict[str, dict[str, Any]] = {}
    for raw_row in value:
        if not isinstance(raw_row, Mapping) or set(raw_row) != (
            STARTER_REVIEWED_CANDIDATE_FIELDS
        ):
            raise ValueError("starter_decision_reviewed_candidates_invalid")
        candidate_id = raw_row.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id in reviewed:
            raise ValueError("starter_decision_reviewed_candidates_invalid")
        revision = validate_candidate_revision(
            raw_row.get("candidate_revision")
        )
        content_sha256 = raw_row.get("content_sha256")
        if (
            not isinstance(content_sha256, str)
            or _CONTENT_SHA256_RE.fullmatch(content_sha256) is None
        ):
            raise ValueError("starter_decision_reviewed_candidates_invalid")
        reviewed[candidate_id] = {
            "candidate_revision": revision,
            "content_sha256": content_sha256,
        }
    if set(reviewed) != set(candidate_by_id):
        raise ValueError("starter_decision_reviewed_candidates_invalid")
    for candidate_id, candidate in candidate_by_id.items():
        row = reviewed[candidate_id]
        if (
            row["candidate_revision"] != candidate.candidate_revision
            or row["content_sha256"] != candidate.document.content_sha256
        ):
            raise ValueError("starter_decision_candidate_digest_mismatch")


def _validate_critic_text_list(value: object, *, field: str) -> None:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > _MAX_CRITIC_ROWS
        or any(not _nonempty_text(item) for item in value)
    ):
        raise ValueError(f"starter_decision_{field}_invalid")


def _validate_critic_identity(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) != (
        STARTER_CRITIC_IDENTITY_FIELDS
    ):
        raise ValueError("starter_decision_critic_identity_invalid")
    confidence = value.get("confidence")
    if (
        value.get("kind") != "independent_codex_agent"
        or not _nonempty_text(value.get("review_id"))
        or not isinstance(confidence, str)
        or confidence not in {"high", "low"}
    ):
        raise ValueError("starter_decision_critic_identity_invalid")


def _nonempty_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= _MAX_CRITIC_TEXT
        and not any(ord(character) < 32 for character in value)
    )


__all__ = (
    "ValidatedStarterSelection",
    "load_validated_starter_selection",
)
