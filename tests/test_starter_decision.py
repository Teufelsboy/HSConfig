from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from hsconfig.starter_contract import (
    STARTER_CANDIDATE_1_FILENAME,
    STARTER_CANDIDATE_2_FILENAME,
    STARTER_CANDIDATE_3_FILENAME,
    STARTER_CANDIDATE_FIELDS,
    STARTER_DECISION_FIELDS,
    STARTER_DECISION_FILENAME,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_decision import (
    ValidatedStarterSelection,
    load_validated_starter_selection,
)
from hsconfig.starter_document import StarterDocument, seal_starter_document
from tests.test_starter_candidate import (
    ROLE_SUMMARIES,
    build_shadowpriest_context,
    sealed_candidate,
)


def three_candidates(context: Any) -> list[StarterDocument]:
    return [
        sealed_candidate(
            context,
            candidate_id="candidate-1",
            role="proactive_tempo",
            changed_globalvalue_key="FirstTurnValueWeight",
            changed_globalvalue_value="0.75",
        ),
        sealed_candidate(
            context,
            candidate_id="candidate-2",
            role="balanced",
            changed_globalvalue_key="SecondTurnValueWeight",
            changed_globalvalue_value="0.25",
        ),
        sealed_candidate(
            context,
            candidate_id="candidate-3",
            role="resource_oriented",
            changed_globalvalue_key="GlobalTaunt",
            changed_globalvalue_value="1.25",
        ),
    ]


def decision_draft(candidates: list[StarterDocument], context: Any) -> dict[str, Any]:
    reviewed = [
        {
            "candidate_id": candidate.to_value()["candidate_id"],
            "candidate_revision": candidate.to_value()["candidate_revision"],
            "content_sha256": candidate.content_sha256,
        }
        for candidate in candidates
    ]
    ranking = [row["candidate_id"] for row in reviewed]
    return {
        "schema_version": STARTER_SCHEMA_VERSION,
        "starter_context_sha256": context.document.content_sha256,
        "reviewed_candidates": reviewed,
        "ranking": ranking,
        "selected_candidate_id": ranking[0],
        "selection_rationale": "The first candidate has the clearest bounded pressure plan.",
        "strengths": ["Concrete physical runtime intent."],
        "risks": ["No gameplay outcome is claimed."],
        "rejection_reasons": {
            ranking[1]: "Less direct early pressure.",
            ranking[2]: "Slower resource posture.",
        },
        "critic_identity": {
            "kind": "independent_codex_agent",
            "review_id": "critic-review-1",
            "confidence": "high",
        },
    }


def write_selection_bundle(
    root: Path,
    context: Any,
    candidates: list[StarterDocument],
    *,
    mutate_decision: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    root.mkdir()
    (root / "starter_context.json").write_bytes(context.document.canonical_json)
    for name, candidate in zip(
        (
            STARTER_CANDIDATE_1_FILENAME,
            STARTER_CANDIDATE_2_FILENAME,
            STARTER_CANDIDATE_3_FILENAME,
        ),
        candidates,
        strict=True,
    ):
        (root / name).write_bytes(candidate.canonical_json)
    draft = decision_draft(candidates, context)
    if mutate_decision is not None:
        mutate_decision(draft)
    decision = seal_starter_document(
        draft,
        expected_fields=STARTER_DECISION_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    path = root / STARTER_DECISION_FILENAME
    path.write_bytes(decision.canonical_json)
    return path


def _duplicate_runtime_intent(candidates: list[StarterDocument], context: Any) -> None:
    candidates[1] = sealed_candidate(
        context,
        candidate_id="candidate-2",
        role="balanced",
        changed_globalvalue_key="FirstTurnValueWeight",
        changed_globalvalue_value="0.75",
    )


def _duplicate_candidate_id(candidates: list[StarterDocument], context: Any) -> None:
    candidates[1] = sealed_candidate(
        context,
        candidate_id="candidate-1",
        role="balanced",
        changed_globalvalue_key="SecondTurnValueWeight",
        changed_globalvalue_value="0.25",
    )


def _duplicate_role(candidates: list[StarterDocument], context: Any) -> None:
    candidates[1] = sealed_candidate(
        context,
        candidate_id="candidate-2",
        role="proactive_tempo",
        changed_globalvalue_key="SecondTurnValueWeight",
        changed_globalvalue_value="0.25",
    )


def _equivalent_numeric_runtime_intents(
    candidates: list[StarterDocument], context: Any
) -> None:
    spellings = (("0", "12"), ("+0.0", "12.0"), ("0/7", "+12.00"))
    roles = ("proactive_tempo", "balanced", "resource_oriented")
    candidates[:] = [
        sealed_candidate(
            context,
            candidate_id=f"candidate-{index}",
            role=role,
            changed_globalvalue_key="FirstTurnValueWeight",
            changed_globalvalue_value=globalvalue,
            mutate=lambda draft, card_value=card_value: draft["card_rules"][
                0
            ].__setitem__("value", card_value),
        )
        for index, (role, (globalvalue, card_value)) in enumerate(
            zip(roles, spellings, strict=True),
            start=1,
        )
    ]


def _equivalent_mulligan_runtime_intents(
    candidates: list[StarterDocument], context: Any
) -> None:
    selectors = (
        "TOY_518, TOY_381",
        "TOY_381,TOY_518",
        "TOY_518 ,TOY_381",
    )
    roles = ("proactive_tempo", "balanced", "resource_oriented")

    def use_card_list(draft: dict[str, Any], selector: str) -> None:
        draft["mulligan"][0]["selector_kind"] = "card_list"
        draft["mulligan"][0]["selector"] = selector
        disposition = next(
            row
            for row in draft["card_dispositions"]
            if row["card_id"] == "TOY_381"
        )
        disposition["disposition"] = "configured"
        disposition["rule_ids"] = ["keep-toy-518"]

    candidates[:] = [
        sealed_candidate(
            context,
            candidate_id=f"candidate-{index}",
            role=role,
            changed_globalvalue_key="FirstTurnValueWeight",
            changed_globalvalue_value="0.75",
            mutate=lambda draft, selector=selector: use_card_list(
                draft,
                selector,
            ),
        )
        for index, (role, selector) in enumerate(
            zip(roles, selectors, strict=True),
            start=1,
        )
    ]


def _redundant_mulligan_runtime_intents(
    candidates: list[StarterDocument], context: Any
) -> None:
    roles = ("proactive_tempo", "balanced", "resource_oriented")
    redundant_cards = (None, "TOY_381", "TOY_518")

    def add_redundant_coverage(
        draft: dict[str, Any], redundant_card: str | None
    ) -> None:
        draft["mulligan"][0]["selector_kind"] = "card_list"
        draft["mulligan"][0]["selector"] = "TOY_518,TOY_381"
        toy_381 = next(
            row
            for row in draft["card_dispositions"]
            if row["card_id"] == "TOY_381"
        )
        toy_381["disposition"] = "configured"
        toy_381["rule_ids"] = ["keep-toy-518"]
        if redundant_card is None:
            return
        redundant_rule_id = f"redundant-{redundant_card.lower()}"
        draft["mulligan"].append(
            {
                "rule_id": redundant_rule_id,
                "selector_kind": "card",
                "selector": redundant_card,
                "action": "hold",
                "condition": "*",
            }
        )
        draft["rule_rationales"][redundant_rule_id] = (
            "Repeat one already-covered physical hold."
        )
        disposition = next(
            row
            for row in draft["card_dispositions"]
            if row["card_id"] == redundant_card
        )
        disposition["rule_ids"].append(redundant_rule_id)

    candidates[:] = [
        sealed_candidate(
            context,
            candidate_id=f"candidate-{index}",
            role=role,
            changed_globalvalue_key="FirstTurnValueWeight",
            changed_globalvalue_value="0.75",
            mutate=(
                lambda draft, redundant_card=redundant_card: (
                    add_redundant_coverage(draft, redundant_card)
                )
            ),
        )
        for index, (role, redundant_card) in enumerate(
            zip(roles, redundant_cards, strict=True),
            start=1,
        )
    ]


@pytest.mark.parametrize(
    ("mutate_candidates", "mutate_decision", "error"),
    [
        (
            lambda candidates, context: _duplicate_candidate_id(candidates, context),
            None,
            "starter_selection_candidate_ids_invalid",
        ),
        (
            lambda candidates, context: _duplicate_role(candidates, context),
            None,
            "starter_selection_candidate_roles_invalid",
        ),
        (
            lambda candidates, context: _duplicate_runtime_intent(
                candidates, context
            ),
            None,
            "starter_selection_runtime_intents_not_distinct",
        ),
        (
            None,
            lambda draft: draft["reviewed_candidates"].pop(),
            "starter_decision_reviewed_candidates_invalid",
        ),
        (
            None,
            lambda draft: draft["reviewed_candidates"][0].__setitem__(
                "content_sha256", "sha256:" + "0" * 64
            ),
            "starter_decision_candidate_digest_mismatch",
        ),
        (
            None,
            lambda draft: draft["ranking"].__setitem__(1, "candidate-1"),
            "starter_decision_ranking_invalid",
        ),
        (
            None,
            lambda draft: draft["rejection_reasons"].pop("candidate-3"),
            "starter_decision_rejection_reasons_invalid",
        ),
        (
            None,
            lambda draft: draft.__setitem__("critic_identity", {}),
            "starter_decision_critic_identity_invalid",
        ),
        (
            None,
            lambda draft: draft["critic_identity"].__setitem__(
                "confidence", []
            ),
            "starter_decision_critic_identity_invalid",
        ),
        (
            lambda candidates, context: _equivalent_numeric_runtime_intents(
                candidates, context
            ),
            None,
            "starter_selection_runtime_intents_not_distinct",
        ),
    ],
)
def test_selection_rejects_invalid_candidate_set_or_critic_binding(
    tmp_path: Path,
    mutate_candidates: Callable[[list[StarterDocument], Any], None] | None,
    mutate_decision: Callable[[dict[str, Any]], None] | None,
    error: str,
) -> None:
    # Break caught: the critic can select a stale, non-diverse, or unreviewed set.
    context = build_shadowpriest_context(tmp_path)
    candidates = three_candidates(context)
    if mutate_candidates is not None:
        mutate_candidates(candidates, context)
    decision_path = write_selection_bundle(
        tmp_path / "bundle",
        context,
        candidates,
        mutate_decision=mutate_decision,
    )

    with pytest.raises(ValueError, match=error):
        load_validated_starter_selection(
            decision_path,
            current_context=context,
        )


@pytest.mark.parametrize("revision", [0, 4, True])
def test_each_candidate_revision_is_independently_bounded(
    tmp_path: Path,
    revision: object,
) -> None:
    # Break caught: one strategist bypasses the maximum two-repair boundary.
    context = build_shadowpriest_context(tmp_path)
    candidates = three_candidates(context)
    candidates[1] = sealed_candidate(
        context,
        candidate_id="candidate-2",
        revision=revision,  # type: ignore[arg-type]
        role="balanced",
        changed_globalvalue_key="SecondTurnValueWeight",
        changed_globalvalue_value="0.25",
    )
    decision_path = write_selection_bundle(
        tmp_path / "bundle",
        context,
        candidates,
    )

    with pytest.raises(ValueError, match="starter_candidate_revision_invalid"):
        load_validated_starter_selection(
            decision_path,
            current_context=context,
        )


def test_selection_rejects_three_equivalent_card_list_spellings(
    tmp_path: Path,
) -> None:
    # Break caught: selector order and whitespace manufacture runtime diversity.
    context = build_shadowpriest_context(tmp_path)
    candidates = three_candidates(context)
    _equivalent_mulligan_runtime_intents(candidates, context)
    decision_path = write_selection_bundle(
        tmp_path / "bundle",
        context,
        candidates,
    )

    with pytest.raises(
        ValueError,
        match="^starter_selection_runtime_intents_not_distinct$",
    ):
        load_validated_starter_selection(
            decision_path,
            current_context=context,
        )


def test_selection_rejects_redundant_ordinary_mulligan_coverage(
    tmp_path: Path,
) -> None:
    # Break caught: redundant same-action card rules manufacture diversity.
    context = build_shadowpriest_context(tmp_path)
    candidates = three_candidates(context)
    _redundant_mulligan_runtime_intents(candidates, context)
    decision_path = write_selection_bundle(
        tmp_path / "bundle",
        context,
        candidates,
    )

    with pytest.raises(
        ValueError,
        match="^starter_selection_runtime_intents_not_distinct$",
    ):
        load_validated_starter_selection(
            decision_path,
            current_context=context,
        )


def test_critic_cannot_mutate_a_candidate_after_review(
    tmp_path: Path,
) -> None:
    # Break caught: candidate bytes change after the critic bound their digest.
    context = build_shadowpriest_context(tmp_path)
    candidates = three_candidates(context)
    decision_path = write_selection_bundle(
        tmp_path / "bundle",
        context,
        candidates,
    )
    mutated = candidates[0].to_value()
    del mutated["content_sha256"]
    mutated["strategy_summary"]["summary"] = ROLE_SUMMARIES["proactive_tempo"] + " Now."
    resealed = seal_starter_document(
        mutated,
        expected_fields=STARTER_CANDIDATE_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    (decision_path.parent / STARTER_CANDIDATE_1_FILENAME).write_bytes(
        resealed.canonical_json
    )

    with pytest.raises(
        ValueError,
        match="starter_decision_candidate_digest_mismatch",
    ):
        load_validated_starter_selection(
            decision_path,
            current_context=context,
        )


def test_valid_selection_accepts_shared_initial_revisions_and_one_repair(
    tmp_path: Path,
) -> None:
    # Break caught: revisions are incorrectly required to be globally unique.
    context = build_shadowpriest_context(tmp_path)
    candidates = three_candidates(context)
    initial_path = write_selection_bundle(
        tmp_path / "initial",
        context,
        candidates,
    )

    initial = load_validated_starter_selection(
        initial_path,
        current_context=context,
    )

    assert isinstance(initial, ValidatedStarterSelection)
    assert [candidate.candidate_revision for candidate in initial.candidates] == [
        1,
        1,
        1,
    ]
    assert initial.selected.candidate_id == "candidate-1"

    repaired = three_candidates(context)
    repaired[1] = sealed_candidate(
        context,
        candidate_id="candidate-2",
        revision=2,
        role="balanced",
        changed_globalvalue_key="SecondTurnValueWeight",
        changed_globalvalue_value="0.5",
    )
    repaired_path = write_selection_bundle(
        tmp_path / "repaired",
        context,
        repaired,
    )
    repaired_selection = load_validated_starter_selection(
        repaired_path,
        current_context=context,
    )
    assert [
        candidate.candidate_revision for candidate in repaired_selection.candidates
    ] == [1, 2, 1]


def test_fixed_sibling_loader_rejects_noncanonical_decision_filename(
    tmp_path: Path,
) -> None:
    # Break caught: a caller-controlled decision filename changes sibling authority.
    context = build_shadowpriest_context(tmp_path)
    candidates = three_candidates(context)
    decision_path = write_selection_bundle(
        tmp_path / "bundle",
        context,
        candidates,
    )
    renamed = decision_path.with_name("critic-choice.json")
    decision_path.rename(renamed)

    with pytest.raises(ValueError, match="starter_decision_filename_invalid"):
        load_validated_starter_selection(
            renamed,
            current_context=context,
        )
