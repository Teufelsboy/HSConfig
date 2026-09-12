"""Ordered Mulligan authority without weakening historical domain checks."""

from dataclasses import FrozenInstanceError, fields

import pytest

from hsconfig import package_domain as domain


def rule(card="B"):
    return domain.MulliganRuleModel(
        card_id=card, selector_kind="card", selector_canonical_json=f'"{card}"'.encode(),
        action="discard", condition_canonical_json=b'"*"', reason="Explicit rule.",
        confidence="llm_optimized_start", source_claim_ids=(), claim_id="candidate:rule",
    )


def model(**overrides):
    assert hasattr(domain, "SemanticMulliganPlanModel"), "ordered authority missing"
    return domain.SemanticMulliganPlanModel(**{
        "deck_name": "Test", "rules": (rule("B"), rule("A")), "suppressed": (),
        "bot_delegated": (), "merged_duplicate_rule_count": 0, **overrides,
    })


def test_semantic_order_is_immutable_and_report_is_inherited():
    value = model()
    assert isinstance(value, domain.MulliganPlanModel)
    assert [r.card_id for r in value.rules] == ["B", "A"]
    assert [r["card"] for r in value.to_report()["rules"]] == ["B", "A"]
    assert type(value).to_report is domain.MulliganPlanModel.to_report
    assert fields(value) == fields(domain.MulliganPlanModel)
    assert not hasattr(value, "__dict__")
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        value.rules = ()
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(value, "rules", ())
    with pytest.raises(ValueError, match="^mulligan_rule_order_unstable$"):
        domain.MulliganPlanModel(*tuple(value))


@pytest.mark.parametrize("overrides,error", [
    ({"rules": ()}, "starter_candidate_mulligan_required"),
    ({"rules": (rule(), rule())}, "mulligan_duplicate_rule_identity"),
    ({"merged_duplicate_rule_count": -1}, "mulligan_merged_duplicate_count_invalid"),
    ({"suppressed": tuple(domain.MulliganSuppressionModel(c, "none", "gap", ()) for c in ("B", "A"))}, "mulligan_suppression_order_unstable"),
    ({"bot_delegated": tuple(domain.BotDelegationModel(c, "E", "BOT_NATIVE_PRE_RUN", "gap") for c in ("Z", "Y"))}, "mulligan_delegation_order_unstable"),
    ({"bot_delegated": (domain.BotDelegationModel("A", "E", "BOT_NATIVE_PRE_RUN", "gap"),)}, "mulligan_card_ruled_and_delegated"),
])
def test_semantic_keeps_base_invariants(overrides, error):
    with pytest.raises(ValueError, match=f"^{error}$"):
        model(**overrides)


def test_historical_empty_plan_is_unchanged():
    assert domain.MulliganPlanModel("Test", (), (), (), 0).rules == ()
