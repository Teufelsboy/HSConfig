from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hsconfig.package_request import ResolvedPackageRequest
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_context import (
    StarterContext,
    build_starter_context,
    validate_starter_context_document,
)
from hsconfig.starter_contract import (
    STARTER_CANDIDATE_FIELDS,
    STARTER_CANDIDATE_FILENAMES,
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_FILENAME,
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_DECISION_FIELDS,
    STARTER_DECISION_FILENAME,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_decision import (
    ValidatedStarterSelection,
    load_validated_starter_selection,
)
from hsconfig.starter_document import (
    StarterDocument,
    load_starter_document,
    seal_starter_document,
)
from tests.helpers.audited_package_request import audited_request


SHADOWPRIEST_DECK_NAME = "ShadowPriest"
SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="
)
SHADOWPRIEST_DECK_FINGERPRINT = (
    "831b989cf8d076bff87848b4d0d6f382c9d306fddea7619017f0c361bfc92327"
)
SHADOWPRIEST_HS_ID = "2737726722"
SHADOWPRIEST_HDT_DECK_ID = "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602"

_CANDIDATE_SPECS = (
    (
        "candidate-1",
        "proactive_tempo",
        "Prioritize early pressure while preserving a bounded refill line.",
        "FirstTurnValueWeight",
        "0.75",
    ),
    (
        "candidate-2",
        "balanced",
        "Balance early pressure with measured resource use.",
        "SecondTurnValueWeight",
        "0.25",
    ),
    (
        "candidate-3",
        "resource_oriented",
        "Preserve resources while keeping a bounded pressure line.",
        "GlobalTaunt",
        "1.25",
    ),
)


@dataclass(frozen=True, slots=True)
class ShadowPriestStarterFixture:
    request: ResolvedPackageRequest
    context: StarterContext
    candidates: tuple[StarterDocument, ...]
    decision: StarterDocument
    decision_path: Path
    selection: ValidatedStarterSelection


def build_shadowpriest_starter_fixture(
    root: Path,
) -> ShadowPriestStarterFixture:
    request = audited_request(root / "audited", SHADOWPRIEST_DECK_NAME)
    context = build_starter_context(request.snapshot)
    candidates = tuple(
        _candidate_document(
            context,
            candidate_id=candidate_id,
            role=role,
            summary=summary,
            changed_key=changed_key,
            changed_value=changed_value,
        )
        for candidate_id, role, summary, changed_key, changed_value in (
            _CANDIDATE_SPECS
        )
    )
    for candidate in candidates:
        validate_starter_candidate(candidate, context=context)

    root.mkdir(parents=True, exist_ok=True)
    context_path = root / STARTER_CONTEXT_FILENAME
    context_path.write_bytes(context.document.canonical_json)
    for filename, candidate in zip(
        STARTER_CANDIDATE_FILENAMES,
        candidates,
        strict=True,
    ):
        (root / filename).write_bytes(candidate.canonical_json)

    decision = seal_starter_document(
        _decision_draft(context, candidates),
        expected_fields=STARTER_DECISION_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    decision_path = root / STARTER_DECISION_FILENAME
    decision_path.write_bytes(decision.canonical_json)

    loaded_context = validate_starter_context_document(
        load_starter_document(
            context_path,
            maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
            expected_fields=STARTER_CONTEXT_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )
    )
    selection = load_validated_starter_selection(
        decision_path,
        current_context=loaded_context,
    )
    return ShadowPriestStarterFixture(
        request=request,
        context=loaded_context,
        candidates=candidates,
        decision=decision,
        decision_path=decision_path,
        selection=selection,
    )


def write_invalid_selected_candidate_bundle(
    root: Path,
    fixture: ShadowPriestStarterFixture,
) -> Path:
    root.mkdir(parents=True)
    for filename in (
        STARTER_CONTEXT_FILENAME,
        *STARTER_CANDIDATE_FILENAMES,
        STARTER_DECISION_FILENAME,
    ):
        (root / filename).write_bytes(
            (fixture.decision_path.parent / filename).read_bytes()
        )

    selected_path = root / STARTER_CANDIDATE_FILENAMES[0]
    selected = fixture.candidates[0].to_value()
    del selected["content_sha256"]
    selected["card_dispositions"].pop()
    invalid_selected = seal_starter_document(
        selected,
        expected_fields=STARTER_CANDIDATE_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    selected_path.write_bytes(invalid_selected.canonical_json)

    decision = fixture.decision.to_value()
    del decision["content_sha256"]
    decision["reviewed_candidates"][0]["content_sha256"] = (
        invalid_selected.content_sha256
    )
    invalid_decision = seal_starter_document(
        decision,
        expected_fields=STARTER_DECISION_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    decision_path = root / STARTER_DECISION_FILENAME
    decision_path.write_bytes(invalid_decision.canonical_json)
    return decision_path


def _candidate_document(
    context: StarterContext,
    *,
    candidate_id: str,
    role: str,
    summary: str,
    changed_key: str,
    changed_value: str,
) -> StarterDocument:
    context_value = context.document.to_value()
    globalvalues = deepcopy(context_value["globalvalues_baseline"]["values"])
    globalvalues[changed_key]["values"][0]["value"] = changed_value
    mulligan_rule_id = "keep-toy-518"
    hero_power_rule_id = "darkbishop-mind-spike"
    dispositions = []
    for card in context_value["cards"]:
        card_id = str(card["card_id"])
        rule_ids = {
            "SW_448": [hero_power_rule_id],
            "TOY_518": [mulligan_rule_id],
        }.get(card_id, [])
        dispositions.append(
            {
                "card_id": card_id,
                "disposition": (
                    "configured" if rule_ids else "deliberately_unconfigured"
                ),
                "rule_ids": rule_ids,
                "reason": (
                    "Candidate contains one bounded explicit runtime rule."
                    if rule_ids
                    else "No additional pre-game runtime rule is justified."
                ),
            }
        )
    draft: dict[str, Any] = {
        "schema_version": STARTER_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "candidate_revision": 1,
        "starter_context_sha256": context.document.content_sha256,
        "deck_fingerprint": context.deck_fingerprint,
        "strategy_summary": {"role": role, "summary": summary},
        "mulligan": [
            {
                "rule_id": mulligan_rule_id,
                "selector_kind": "card",
                "selector": "TOY_518",
                "action": "hold",
                "condition": "*",
            }
        ],
        "globalvalues": globalvalues,
        "card_rules": [
            {
                "rule_id": hero_power_rule_id,
                "source_card_id": "SW_448",
                "runtime_card_id": "EX1_625t",
                "link_kind": "hero_power_transform",
                "behavior_block": "BeforeUseHeroPowerBonus",
                "condition": "*",
                "value": "12",
            }
        ],
        "combo": None,
        "card_dispositions": dispositions,
        "rule_rationales": {
            mulligan_rule_id: (
                "Use one physical early-pressure card as the concrete keep."
            ),
            hero_power_rule_id: (
                "The transformed hero power behavior belongs to Mind Spike."
            ),
        },
        "assumptions": [
            "This is a bounded pre-game start and makes no gameplay outcome claim."
        ],
    }
    return seal_starter_document(
        draft,
        expected_fields=STARTER_CANDIDATE_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )


def _decision_draft(
    context: StarterContext,
    candidates: tuple[StarterDocument, ...],
) -> dict[str, Any]:
    reviewed = [
        {
            "candidate_id": str(candidate.to_value()["candidate_id"]),
            "candidate_revision": int(candidate.to_value()["candidate_revision"]),
            "content_sha256": candidate.content_sha256,
        }
        for candidate in candidates
    ]
    return {
        "schema_version": STARTER_SCHEMA_VERSION,
        "starter_context_sha256": context.document.content_sha256,
        "reviewed_candidates": reviewed,
        "ranking": ["candidate-1", "candidate-2", "candidate-3"],
        "selected_candidate_id": "candidate-1",
        "selection_rationale": (
            "Candidate 1 has the clearest bounded proactive start."
        ),
        "strengths": ["Concrete Mulligan and linked hero-power runtime intent."],
        "risks": ["No in-client gameplay outcome is claimed."],
        "rejection_reasons": {
            "candidate-2": "Its early posture is less direct.",
            "candidate-3": "Its resource posture is intentionally slower.",
        },
        "critic_identity": {
            "kind": "independent_codex_agent",
            "review_id": "shadowpriest-independent-critic-1",
            "confidence": "high",
        },
    }


__all__ = (
    "SHADOWPRIEST_DECK_CODE",
    "SHADOWPRIEST_DECK_FINGERPRINT",
    "SHADOWPRIEST_DECK_NAME",
    "SHADOWPRIEST_HDT_DECK_ID",
    "SHADOWPRIEST_HS_ID",
    "ShadowPriestStarterFixture",
    "build_shadowpriest_starter_fixture",
    "write_invalid_selected_candidate_bundle",
)
