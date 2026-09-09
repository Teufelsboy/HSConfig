from __future__ import annotations

from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.package_domain import MulliganPlanModel, MulliganRuleModel


def _plan(
    *, candidate_hash: str, reason: str = "Keep the early minion.",
    action: str = "hold", confidence: str = "llm_optimized_start",
) -> MulliganPlanModel:
    claim_id = f"starter:sha256:{candidate_hash}:lead:early-keep"
    return MulliganPlanModel(
        deck_name="Fixture",
        rules=(MulliganRuleModel(
            card_id="EX1_001",
            selector_kind="card",
            selector_canonical_json=b'"EX1_001"',
            action=action,
            condition_canonical_json=b'"*"',
            reason=reason,
            confidence=confidence,
            source_claim_ids=() if confidence == "llm_optimized_start" else (claim_id,),
            claim_id=claim_id,
        ),),
        suppressed=(),
        bot_delegated=(),
        merged_duplicate_rule_count=0,
    )


def test_starter_runtime_comment_is_stable_while_full_review_provenance_changes() -> None:
    first = _plan(candidate_hash="a" * 64)
    second = _plan(candidate_hash="b" * 64, reason="A fresh independent review of the same keep.")

    # An independently frozen approval must not create a new runtime revision
    # solely because its candidate hash or audit explanation changed.
    assert compile_mulligan(first) == compile_mulligan(second)
    assert first.rules[0].claim_id != second.rules[0].claim_id
    assert first.to_report()["rules"][0]["claim_id"] == first.rules[0].claim_id
    assert second.to_report()["rules"][0]["claim_id"] == second.rules[0].claim_id
    assert first.to_report()["rules"][0]["reason"] != second.to_report()["rules"][0]["reason"]


def test_stable_starter_comment_does_not_hide_changed_runtime_behavior() -> None:
    keep = compile_mulligan(_plan(candidate_hash="a" * 64))
    discard = compile_mulligan(_plan(candidate_hash="a" * 64, action="discard"))

    assert keep != discard
    assert keep["Mulligan"]["values"][0]["value"] == "hold"
    assert discard["Mulligan"]["values"][0]["value"] == "discard"


def test_source_backed_runtime_comment_keeps_its_existing_claim_label() -> None:
    plan = _plan(candidate_hash="a" * 64, confidence="source_backed")

    assert compile_mulligan(plan)["Mulligan"]["values"][0]["comment"] == (
        f"Fixture: {plan.rules[0].claim_id}"
    )
