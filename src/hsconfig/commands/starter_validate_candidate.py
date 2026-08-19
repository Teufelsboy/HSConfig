"""Deterministic read-only validation of one starter candidate."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_context import StarterContext
from hsconfig.starter_contract import (
    STARTER_CANDIDATE_FIELDS,
    STARTER_CANDIDATE_MAX_BYTES,
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_document import load_starter_document


def run_starter_validate_candidate_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, _starter_validate_candidate_payload)


def _starter_validate_candidate_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    context_path = Path(args.starter_context_json)
    candidate_path = Path(args.candidate_json)
    context_document = load_starter_document(
        context_path,
        maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
        expected_fields=STARTER_CONTEXT_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    context = _reconstruct_starter_context(context_document)
    candidate_document = load_starter_document(
        candidate_path,
        maximum_bytes=STARTER_CANDIDATE_MAX_BYTES,
        expected_fields=STARTER_CANDIDATE_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    candidate = validate_starter_candidate(
        candidate_document,
        context=context,
    )
    return (
        {
            "candidate_id": candidate.candidate_id,
            "candidate_revision": candidate.candidate_revision,
            "content_sha256": candidate.document.content_sha256,
            "runtime_intent_sha256": candidate.runtime_intent_sha256,
            "starter_context_sha256": context.document.content_sha256,
            "strategy_role": candidate.strategy_role,
            "valid": True,
        },
        0,
    )


def _reconstruct_starter_context(document: Any) -> StarterContext:
    value = document.to_value()
    identity = value.get("deck_identity")
    baseline = value.get("globalvalues_baseline")
    if not isinstance(identity, Mapping) or not isinstance(baseline, Mapping):
        raise ValueError("starter_context_document_invalid")
    deck_fingerprint = identity.get("deck_fingerprint")
    baseline_sha256 = baseline.get("content_sha256")
    if not isinstance(deck_fingerprint, str) or not isinstance(
        baseline_sha256, str
    ):
        raise ValueError("starter_context_document_invalid")
    return StarterContext(
        document=document,
        deck_fingerprint=deck_fingerprint,
        globalvalues_baseline_sha256=baseline_sha256,
    )


__all__ = ("run_starter_validate_candidate_command",)
