from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any, Literal

from hearthstone import cardxml
from hearthstone.deckstrings import FormatType, write_deckstring

from hsconfig.deckstring_decode import MECHANIC_ATTRS, decode_deck_code
from hsconfig.evidence_contract import load_policy_profile
from hsconfig.globalvalues_baseline import load_globalvalues_baseline
from hsconfig.globalvalues_decisions import normalize_globalvalues_decision_baseline
from hsconfig.input_snapshot_manifest import FrozenCompilerInputs, freeze_compiler_inputs
from hsconfig.operator_profile import (
    OperatorProfile,
    derive_deck_output_binding,
    enable_operator_profile,
)
from hsconfig.package_request import (
    FrozenJsonDocument,
    PackageResolutionSnapshot,
    ResolvedPackageRequest,
)
from hsconfig.preconfig_context import build_preconfig_context
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_context import (
    StarterContext,
    build_single_candidate_starter_context,
    build_starter_context,
    validate_starter_context_document,
)
from hsconfig.starter_contract import (
    SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
    SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    STARTER_CANDIDATE_FIELDS,
    STARTER_CANDIDATE_FILENAMES,
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_FILENAME,
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_DECISION_FIELDS,
    STARTER_DECISION_FILENAME,
    STARTER_SCHEMA_VERSION,
    STARTER_REVIEW_FIELDS,
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
from hsconfig.starter_review import validate_starter_review
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

# Fixed Wild priest/neutral singletons plus Prince Renathal, not a catalog deck.
_CODEX_FORTY_DBF_IDS = (
    8, 9, 12, 30, 34, 37, 41, 45, 61, 67, 68, 69, 90, 132, 134,
    138, 145, 157, 158, 175, 179, 186, 191, 211, 216, 220, 237,
    242, 251, 257, 272, 279, 281, 284, 289, 290, 308, 336, 339, 79767,
)


@dataclass(frozen=True, slots=True)
class CodexFirstFixture:
    deck_name: str
    deck_code: str
    frozen_inputs: FrozenCompilerInputs
    context: StarterContext
    candidate: StarterDocument
    review: StarterDocument
    profile: OperatorProfile


def build_codex_first_fixture(
    root: Path,
    *,
    deck_kind: Literal["shadowpriest", "uncatalogued_40"] = "shadowpriest",
    existing_profile: OperatorProfile | None = None,
    confidence: Literal["high", "limited"] = "high",
) -> CodexFirstFixture:
    """Build real frozen inputs; callers must isolate LOCALAPPDATA for the test."""
    if deck_kind == "shadowpriest":
        deck_name, deck_code = SHADOWPRIEST_DECK_NAME, SHADOWPRIEST_DECK_CODE
    elif deck_kind == "uncatalogued_40":
        deck_name = "CodexFortyPriest"
        deck_code = write_deckstring(
            [(dbf_id, 1) for dbf_id in _CODEX_FORTY_DBF_IDS],
            [813], FormatType.FT_WILD,
        )
    else:
        raise ValueError("codex_first_fixture_deck_kind_invalid")
    if confidence not in {"high", "limited"}:
        raise ValueError("codex_first_fixture_confidence_invalid")
    root.mkdir(parents=True, exist_ok=True)
    profile = existing_profile
    if profile is None:
        runtime_root, output_root = root / "runtime", root / "outputs"
        runtime_root.mkdir()
        output_root.mkdir()
        profile = enable_operator_profile(
            runtime_root=runtime_root,
            output_base_root=output_root,
            expected_predecessor_sha256=None,
        )

    decoded = decode_deck_code(deck_code)
    if decoded["unresolved_identity_count"]:
        raise ValueError("codex_first_fixture_card_database_incomplete")
    full_cards = _codex_first_card_feed(decoded)
    collectible_cards = [row for row in full_cards if row["collectible"]]
    full_path, collectible_path = root / "full-cards.json", root / "collectible-cards.json"
    full_path.write_bytes(FrozenJsonDocument.from_value(full_cards).canonical_json)
    collectible_path.write_bytes(FrozenJsonDocument.from_value(collectible_cards).canonical_json)
    args = argparse.Namespace(
        deck_name=deck_name, deck_code=deck_code, cards_json=None,
        allow_placeholder=False, full_cards_json=str(full_path),
        collectible_cards_json=str(collectible_path), skip_semantic_fetch=True,
        auto_research_fallback=True,
    )
    preconfig = build_preconfig_context(args, current_date=date(2026, 8, 25))
    preconfig["cards_payload"]["deck_code"] = deck_code
    baseline_receipt = load_globalvalues_baseline(profile.runtime_root)
    baseline = normalize_globalvalues_decision_baseline(baseline_receipt["baseline"])
    policy = load_policy_profile()
    preconfig.update({
        "globalvalues_baseline": baseline,
        "globalvalues_baseline_receipt": baseline_receipt,
        "policy_profile": {
            "policy_id": policy.policy_id, "version": policy.version,
            "effective_date": policy.effective_date,
            "content_sha256": policy.content_sha256,
            "rules": json.loads(policy.rules_canonical_json),
        },
    })
    frozen = freeze_compiler_inputs(
        snapshot=PackageResolutionSnapshot.from_preconfig(preconfig),
        deck={key: preconfig[key] for key in ("cards_payload", "deck_identity")},
        full_cards=full_cards, collectible_cards=collectible_cards,
        source_acquisition={
            "guide_builder_receipt": preconfig["guide_builder_receipt"],
            "source_evidence_report": preconfig["source_evidence_report"],
        },
        source_documents={"guide_sources": preconfig["guide_sources_generated"]},
        globalvalues_baseline=baseline, bound_date="2026-08-25",
        runtime_grammar_version="visionai-runtime-v1",
        compiler_contract_id="hsconfig-live-start-v1", operator_profile=profile,
        deck_output_binding=derive_deck_output_binding(profile, deck_name),
    )
    context = build_single_candidate_starter_context(frozen)
    candidate = _codex_first_candidate(context)
    validated_candidate = validate_starter_candidate(candidate, context=context)
    review = seal_starter_document({
        "schema_version": SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
        "review_id": "codex-first-independent-review",
        "review_status": "approved", "confidence": confidence,
        "starter_context_sha256": context.document.content_sha256,
        "candidate_id": validated_candidate.candidate_id,
        "candidate_revision": validated_candidate.candidate_revision,
        "candidate_sha256": candidate.content_sha256,
        "revision_requests": [],
        "review_summary": "The bounded physical-card start is technically coherent; no gameplay outcome is claimed.",
    }, expected_fields=STARTER_REVIEW_FIELDS, schema_version=SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION)
    validate_starter_review(review, context=context, candidate=validated_candidate)
    return CodexFirstFixture(deck_name, deck_code, frozen, context, candidate, review, profile)


def _codex_first_card_feed(decoded: dict[str, Any]) -> list[dict[str, Any]]:
    cards_db, _ = cardxml.load_dbf()
    dbf_ids = {row["dbf_id"] for row in decoded["cards"]}
    # Retain the real priest hero and Mind Spike companion identity in the feed.
    dbf_ids.update({decoded["hero_dbf_id"], 1622})
    rows = []
    for dbf_id in sorted(dbf_ids):
        card = cards_db[dbf_id]
        rows.append({
            "id": card.card_id, "dbfId": dbf_id,
            "name": str(card.english_name or card.name or card.card_id),
            "cost": int(card.cost or 0), "type": card.type.name,
            "cardClass": card.card_class.name,
            "text": str(card.english_description or "").replace("\n", " "),
            "mechanics": sorted(name.upper() for name in MECHANIC_ATTRS if getattr(card, name, None)),
            "collectible": bool(card.collectible),
        })
    return rows


def _codex_first_candidate(context: StarterContext) -> StarterDocument:
    value = context.document.to_value()
    cards = value["cards"]
    early_minions = [row for row in cards if row["type"] == "MINION" and 0 < row["cost"] <= 2]
    kept = min(early_minions or cards, key=lambda row: (row["cost"], row["card_id"]))["card_id"]
    rule_id = "physical-early-keep"
    globalvalues = deepcopy(value["globalvalues_baseline"]["values"])
    globalvalues["FirstTurnValueWeight"]["values"][0]["value"] = "0.75"
    return seal_starter_document({
        "schema_version": SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
        "candidate_id": "lead", "candidate_revision": 1,
        "starter_context_sha256": context.document.content_sha256,
        "deck_fingerprint": context.deck_fingerprint,
        "strategy_summary": {
            "role": "lead_strategist",
            "summary": "Keep one physical early resource and use a bounded opening posture; leave unsupported behavior explicit.",
        },
        "mulligan": [{"rule_id": rule_id, "selector_kind": "card", "selector": kept, "action": "hold", "condition": "*"}],
        "globalvalues": globalvalues, "card_rules": [], "combo": None,
        "card_dispositions": [{
            "card_id": row["card_id"],
            "disposition": "configured" if row["card_id"] == kept else "deliberately_unconfigured",
            "rule_ids": [rule_id] if row["card_id"] == kept else [],
            "reason": "Explicit physical Mulligan keep." if row["card_id"] == kept else "No additional pre-run rule is justified by the fixture evidence.",
        } for row in cards],
        "rule_rationales": {rule_id: "Use a concrete low-cost physical card for the opening-hand rule."},
        "assumptions": ["Deterministic contract fixture, not proof of gameplay optimality."],
    }, expected_fields=SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS, schema_version=SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION)

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
    audited_root = root.parent / f"{root.name}-audited"
    request = audited_request(audited_root, SHADOWPRIEST_DECK_NAME)
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
    "CodexFirstFixture",
    "build_codex_first_fixture",
    "SHADOWPRIEST_DECK_CODE",
    "SHADOWPRIEST_DECK_FINGERPRINT",
    "SHADOWPRIEST_DECK_NAME",
    "SHADOWPRIEST_HDT_DECK_ID",
    "SHADOWPRIEST_HS_ID",
    "ShadowPriestStarterFixture",
    "build_shadowpriest_starter_fixture",
    "write_invalid_selected_candidate_bundle",
)
