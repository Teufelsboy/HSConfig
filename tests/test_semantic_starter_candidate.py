"""Schema4 candidate semantics from genuine offline frozen input authority."""

from copy import deepcopy
import json

import pytest

from hsconfig import starter_semantics


def selector_function():
    assert hasattr(starter_semantics, "semantic_selector"), "lossless selector missing"
    return starter_semantics.semantic_selector


@pytest.mark.parametrize("selector", ["A,A", "A,A,B"])
def test_semantic_comma_duplicates_are_rejected(selector):
    semantic_selector = selector_function()
    with pytest.raises(ValueError, match="^starter_candidate_mulligan_selector_duplicate_member$"):
        semantic_selector({"selector": selector}, {"A": 2, "B": 1})


@pytest.mark.parametrize("selector,kind,multiset", [
    ("A,B", "card_list", [{"card_id": "A", "count": 1}, {"card_id": "B", "count": 1}]),
    ("A+A", "plus_combo", [{"card_id": "A", "count": 2}]),
    ("A+B", "plus_combo", [{"card_id": "A", "count": 1}, {"card_id": "B", "count": 1}]),
])
def test_semantic_selector_preserves_kind_and_multiplicity(selector, kind, multiset):
    from hsconfig.mulligan_selector import normalize_mulligan_selector

    actual = selector_function()({"selector": selector}, {"A": 2, "B": 1})
    assert actual["selector"] == selector
    assert actual["selector_kind"] == kind
    assert actual["selector_multiset"] == multiset
    assert normalize_mulligan_selector({"selector": actual["selector"], "selector_kind": actual["selector_kind"]})["supported"] is True


def test_semantic_selector_copy_limit_and_canonical_member_order():
    select = selector_function()
    assert select({"selector": "B+A+A"}, {"A": 2, "B": 1}) == {
        "selector": "A+A+B", "selector_kind": "plus_combo", "selector_cards": ("A", "B"),
        "selector_multiset": [{"card_id": "A", "count": 2}, {"card_id": "B", "count": 1}],
    }
    with pytest.raises(ValueError, match="^starter_candidate_mulligan_copy_count_exceeded$"):
        select({"selector": "A+A"}, {"A": 1})


ASSUMPTION = "This explicit bounded rule is a starting inference."
HAND = "my_hand(count()) == 3"


@pytest.fixture(scope="module")
def semantic_context(tmp_path_factory):
    from hsconfig.starter_context import build_semantic_starter_context
    from tests.helpers.semantic_start import semantic_frozen_inputs

    with pytest.MonkeyPatch.context() as monkeypatch:
        frozen = semantic_frozen_inputs(tmp_path_factory.mktemp("semantic-candidate"), monkeypatch)
        return build_semantic_starter_context(frozen)


def semantic_draft(context):
    from tests.test_quality_starter_candidate import quality_draft

    draft = quality_draft(context)
    draft["schema_version"] = 4
    draft["assumptions"].append(ASSUMPTION)
    draft["rule_justifications"] = {}
    return synchronize_rules(draft, context)


def synchronize_rules(draft, context):
    """Keep fixture coverage explicit when tests replace rule surfaces."""
    expected = {row["card_id"]: [] for row in context.document.to_value()["cards"]}
    rules = [(row["rule_id"], row["selector"].replace("+", ",").split(",")) for row in draft["mulligan"]]
    rules += [(row["rule_id"], [row["source_card_id"]]) for row in draft["card_rules"]]
    if draft["combo"] is not None:
        rules.append((draft["combo"]["rule_id"], draft["combo"]["cards"]))
    for rule_id, cards in rules:
        for card in set(cards):
            if card in expected:
                expected[card].append(rule_id)
    draft["rule_rationales"] = {rule_id: "Explicit bounded starting rule." for rule_id, _ in rules}
    draft["rule_justifications"] = {
        rule_id: {"basis": "inference", "evidence_refs": [], "assumption": ASSUMPTION}
        for rule_id, _ in rules
    }
    for row in draft["card_dispositions"]:
        row["rule_ids"] = list(dict.fromkeys(expected[row["card_id"]]))
        row["disposition"] = "configured" if row["rule_ids"] else "deliberately_unconfigured"
    return draft


def validate(draft, context):
    from hsconfig.starter_candidate import validate_starter_candidate
    from hsconfig.starter_contract import SEMANTIC_STARTER_CANDIDATE_FIELDS
    from hsconfig.starter_document import seal_starter_document

    return validate_starter_candidate(seal_starter_document(
        draft, expected_fields=SEMANTIC_STARTER_CANDIDATE_FIELDS, schema_version=4,
    ), context=context)


def test_candidate_genuine_schema4_acceptance(semantic_context):
    candidate = validate(semantic_draft(semantic_context), semantic_context)
    assert candidate.document.to_value()["schema_version"] == 4
    assert len(candidate.globalvalues.to_value()) == 38
    assert candidate.mulligan_plan.rules[0].source_claim_ids == ()
    assert candidate.card_behavior_rows[0].to_value()["source_claim_ids"] == []


@pytest.mark.parametrize("selector,kind", [
    ("TOY_518,SW_448", "card_list"), ("TOY_518+TOY_518", "plus_combo"),
    ("TOY_518+SW_448", "plus_combo"),
])
def test_candidate_lossless_multiset_identity(semantic_context, selector, kind):
    draft = semantic_draft(semantic_context)
    draft["mulligan"][0].update(selector=selector, selector_kind=kind)
    candidate = validate(synchronize_rules(draft, semantic_context), semantic_context)
    canonical = {"TOY_518,SW_448": "SW_448,TOY_518", "TOY_518+SW_448": "SW_448+TOY_518", "TOY_518+TOY_518": "TOY_518+TOY_518"}[selector]
    rule = candidate.mulligan_plan.rules[0]
    assert rule.selector_kind == kind
    assert json.loads(rule.selector_canonical_json) == canonical
    assert rule.identity[1:3] == (kind, json.dumps(canonical).encode())
    assert candidate.mulligan_plan.to_report()["rules"][0]["selector"] == canonical


def test_candidate_selector_kinds_and_copies_have_distinct_intents(semantic_context):
    digests = []
    for selector, kind in [("TOY_518", "card"), ("SW_448,TOY_518", "card_list"), ("SW_448+TOY_518", "plus_combo"), ("TOY_518+TOY_518", "plus_combo")]:
        draft = semantic_draft(semantic_context)
        draft["mulligan"][0].update(selector=selector, selector_kind=kind)
        digests.append(validate(synchronize_rules(draft, semantic_context), semantic_context).runtime_intent_sha256)
    assert len(set(digests)) == 4


@pytest.mark.parametrize("selector,kind,error", [
    ("TOY_518,TOY_518", "card_list", "selector_duplicate_member"),
    ("TOY_518,TOY_518,SW_448", "card_list", "selector_duplicate_member"),
    ("SW_448+SW_448", "plus_combo", "copy_count_exceeded"),
    ("TOY_518+TOY_518+TOY_518", "plus_combo", "copy_count_exceeded"),
    ("UNKNOWN", "card", "card_invalid"),
])
def test_candidate_invalid_physical_multisets(semantic_context, selector, kind, error):
    draft = semantic_draft(semantic_context)
    counts = {row["card_id"]: row["count"] for row in semantic_context.document.to_value()["cards"]}
    assert counts["TOY_518"] == 2 and counts["SW_448"] == 1
    draft["mulligan"][0].update(selector=selector, selector_kind=kind)
    with pytest.raises(ValueError, match=f"^starter_candidate_mulligan_{error}$"):
        validate(synchronize_rules(draft, semantic_context), semantic_context)


def test_candidate_reverse_identity_order_and_rationale_only_intent(semantic_context):
    draft = semantic_draft(semantic_context)
    draft["mulligan"].append({**draft["mulligan"][0], "selector": "SW_448", "rule_id": "keep-sw"})
    synchronize_rules(draft, semantic_context)
    before = validate(draft, semantic_context)
    assert [r.card_id for r in before.mulligan_plan.rules] == ["TOY_518", "SW_448"]
    assert before.mulligan_plan.rules[0].identity > before.mulligan_plan.rules[1].identity
    assert [r["selector"] for r in before.mulligan_plan.to_report()["rules"]] == ["TOY_518", "SW_448"]
    draft["rule_rationales"]["keep-sw"] = "Different prose only."
    assert validate(draft, semantic_context).runtime_intent_sha256 == before.runtime_intent_sha256
    draft["mulligan"].reverse()
    assert validate(draft, semantic_context).runtime_intent_sha256 != before.runtime_intent_sha256


def test_candidate_card_rows_preserve_same_owner_evaluation_order(semantic_context):
    draft = semantic_draft(semantic_context)
    draft["card_rules"][0]["condition"] = HAND
    draft["card_rules"].append({**draft["card_rules"][0], "rule_id": "fallback", "condition": "*", "value": "2"})
    synchronize_rules(draft, semantic_context)
    before = validate(draft, semantic_context)
    assert [row.to_value()["condition"] for row in before.card_behavior_rows] == [HAND, "*"]
    draft["card_rules"].reverse()
    after = validate(draft, semantic_context)
    assert [row.to_value()["condition"] for row in after.card_behavior_rows] == ["*", HAND]
    assert after.runtime_intent_sha256 != before.runtime_intent_sha256


@pytest.mark.parametrize("value,error", [("12", "duplicate"), ("13", "conflict")])
def test_candidate_card_duplicate_detector_retained(semantic_context, value, error):
    draft = semantic_draft(semantic_context)
    draft["card_rules"].append({**draft["card_rules"][0], "rule_id": "second", "value": value})
    with pytest.raises(ValueError, match=f"^starter_candidate_runtime_row_{error}$"):
        validate(synchronize_rules(draft, semantic_context), semantic_context)


def test_candidate_copy_only_keys_and_full_38_key_boundary(semantic_context):
    from hsconfig.visionai_registry import STARTER_GLOBALVALUE_CONSTRAINTS

    draft = semantic_draft(semantic_context)
    del draft["globalvalues"]["FirstTurnValueWeight"]
    with pytest.raises(ValueError, match="^starter_candidate_globalvalues_keys_invalid$"):
        validate(draft, semantic_context)
    for key, constraint in STARTER_GLOBALVALUE_CONSTRAINTS.items():
        if constraint.copy_baseline_only:
            draft = semantic_draft(semantic_context)
            draft["globalvalues"][key] = "changed metadata"
            with pytest.raises(ValueError, match="^starter_candidate_globalvalues_metadata_mismatch$"):
                validate(draft, semantic_context)


def test_candidate_duplicate_rule_ids_across_surfaces_rejected(semantic_context):
    draft = semantic_draft(semantic_context)
    draft["card_rules"][0]["rule_id"] = "keep-toy-518"
    with pytest.raises(ValueError, match="^starter_candidate_rule_id_duplicate$"):
        validate(synchronize_rules(draft, semantic_context), semantic_context)


@pytest.mark.parametrize("action,error", [("hold", "duplicate"), ("discard", "conflict")])
def test_candidate_exact_mulligan_duplicates_conflicts(semantic_context, action, error):
    draft = semantic_draft(semantic_context)
    draft["mulligan"].append({**draft["mulligan"][0], "rule_id": "second", "action": action})
    with pytest.raises(ValueError, match=f"^starter_candidate_mulligan_{error}$"):
        validate(synchronize_rules(draft, semantic_context), semantic_context)


def test_candidate_ordered_conditional_then_discard_not_global_overlap_solver(semantic_context):
    draft = semantic_draft(semantic_context)
    draft["mulligan"][0]["condition"] = "coin"
    draft["mulligan"].append({**draft["mulligan"][0], "rule_id": "discard-fallback", "condition": "*", "action": "discard"})
    candidate = validate(synchronize_rules(draft, semantic_context), semantic_context)
    assert [r.action for r in candidate.mulligan_plan.rules] == ["hold", "discard"]


def test_candidate_nonempty_discard_only_and_empty_rejection(semantic_context):
    draft = semantic_draft(semantic_context)
    draft["mulligan"][0]["action"] = "discard"
    draft["card_rules"] = []
    draft["globalvalues"] = deepcopy(semantic_context.document.to_value()["globalvalues_baseline"]["values"])
    draft["globalvalues_justifications"] = {}
    candidate = validate(synchronize_rules(draft, semantic_context), semantic_context)
    assert [r.action for r in candidate.mulligan_plan.rules] == ["discard"]
    draft["mulligan"] = []
    with pytest.raises(ValueError, match="^starter_candidate_mulligan_required$"):
        validate(synchronize_rules(draft, semantic_context), semantic_context)


def add_combo(draft):
    draft["combo"] = {"rule_id": "gameplay", "cards": ["SW_448", "TOY_518", "SW_448"], "timing": "same_turn", "values": ["2", "3", "4"], "condition": "*"}


def test_candidate_gameplay_combo_keeps_order_and_repeats_without_opening_limit(semantic_context):
    draft = semantic_draft(semantic_context)
    add_combo(draft)
    candidate = validate(synchronize_rules(draft, semantic_context), semantic_context)
    assert candidate.combo_plan.decisions[0].cards == ("SW_448", "TOY_518", "SW_448")
    draft["combo"]["cards"] = ["SW_448", "SW_448", "TOY_518"]
    assert validate(draft, semantic_context).runtime_intent_sha256 != candidate.runtime_intent_sha256


def test_basis_ordered_globalvalues_projection_and_keys():
    from hsconfig import starter_candidate as module

    assert hasattr(module, "semantic_globalvalues_projection"), "ordered public projection missing"
    assert hasattr(module, "changed_semantic_globalvalue_keys"), "ordered change detector missing"
    baseline = {"FirstTurnValueWeight": {"values": [{"condition": HAND, "value": "0.5"}, {"condition": "*", "value": "0.7"}]}}
    desired = deepcopy(baseline)
    desired["FirstTurnValueWeight"]["values"].reverse()
    assert module.changed_semantic_globalvalue_keys(baseline, desired) == ("FirstTurnValueWeight",)
    assert module.changed_globalvalue_keys(baseline, desired) == ()
    assert [r["condition"] for r in module.semantic_globalvalues_projection(baseline)["FirstTurnValueWeight"]["values"]] == [HAND, "*"]
    same = deepcopy(baseline)
    same["FirstTurnValueWeight"]["values"][0]["value"] = "0.50"
    assert module.changed_semantic_globalvalue_keys(baseline, same) == ()
    with pytest.raises(ValueError, match="^starter_candidate_globalvalues_keys_invalid$"):
        module.changed_semantic_globalvalue_keys(baseline, {})


def test_basis_globalvalues_reorder_intent_requires_full_justification(semantic_context):
    draft = semantic_draft(semantic_context)
    draft["globalvalues"]["FirstTurnValueWeight"]["values"].append({"condition": HAND, "value": "0.5"})
    first = validate(draft, semantic_context)
    draft["globalvalues"]["FirstTurnValueWeight"]["values"].reverse()
    second = validate(draft, semantic_context)
    assert first.runtime_intent_sha256 != second.runtime_intent_sha256
    for field in ("decision", "baseline_gap"):
        invalid = deepcopy(draft)
        invalid["globalvalues_justifications"]["FirstTurnValueWeight"][field] = ""
        with pytest.raises(ValueError, match="^starter_candidate_globalvalues_justifications_invalid$"):
            validate(invalid, semantic_context)
    draft["globalvalues_justifications"] = {}
    with pytest.raises(ValueError, match="^starter_candidate_globalvalues_justifications_invalid$"):
        validate(draft, semantic_context)


@pytest.mark.parametrize("defect,error", [
    ("missing", "justifications_invalid"), ("extra", "justifications_invalid"),
    ("false_map", "justifications_invalid"), ("false_row", "justifications_invalid"),
    ("false_basis", "justifications_invalid"), ("extra_field", "justifications_invalid"),
    ("false_refs", "evidence_invalid"), ("unknown", "evidence_invalid"),
    ("foreign", "evidence_invalid"), ("duplicate", "evidence_invalid"),
    ("no_evidence", "justifications_invalid"), ("evidence_assumption", "justifications_invalid"),
    ("undeclared", "justifications_invalid"), ("padded", "justifications_invalid"),
    ("false_assumption", "justifications_invalid"),
])
def test_basis_candidate_closed_schema_and_exact_assumptions(semantic_context, defect, error):
    draft = semantic_draft(semantic_context)
    row = draft["rule_justifications"]["keep-toy-518"]
    claims = semantic_context.document.to_value()["existing_claims"]
    applicable = next(c["claim_id"] for c in claims if "TOY_518" in c["cards"] or c.get("scope") == "deck")
    foreign = next(c["claim_id"] for c in claims if "TOY_518" not in c["cards"] and c.get("scope") != "deck")
    if defect == "missing":
        del draft["rule_justifications"]["keep-toy-518"]
    elif defect == "extra":
        draft["rule_justifications"]["foreign-rule"] = deepcopy(row)
    elif defect == "false_map":
        draft["rule_justifications"] = False
    elif defect == "false_row":
        draft["rule_justifications"]["keep-toy-518"] = False
    elif defect == "false_basis":
        row["basis"] = False
    elif defect == "extra_field":
        row["rationale"] = "belongs elsewhere"
    elif defect == "false_refs":
        row["evidence_refs"] = False
    elif defect in {"unknown", "foreign", "duplicate"}:
        row.update(basis="evidence", assumption=None, evidence_refs={"unknown": ["missing"], "foreign": [foreign], "duplicate": [applicable, applicable]}[defect])
    elif defect in {"no_evidence", "evidence_assumption"}:
        row.update(basis="evidence", evidence_refs=[] if defect == "no_evidence" else [applicable], assumption=None if defect == "no_evidence" else ASSUMPTION)
    elif defect == "undeclared":
        draft["assumptions"].remove(ASSUMPTION)
    elif defect == "padded":
        row["assumption"] = " " + ASSUMPTION
    else:
        row["assumption"] = False
    with pytest.raises(ValueError, match=f"^starter_candidate_rule_{error}$"):
        validate(draft, semantic_context)


def test_basis_candidate_existing_claim_and_all_surface_union(semantic_context):
    draft = semantic_draft(semantic_context)
    add_combo(draft)
    synchronize_rules(draft, semantic_context)
    claim_id = next(c["claim_id"] for c in semantic_context.document.to_value()["existing_claims"] if c.get("scope") == "deck")
    draft["rule_justifications"]["keep-toy-518"] = {"basis": "evidence", "evidence_refs": [claim_id], "assumption": None}
    candidate = validate(draft, semantic_context)
    assert set(candidate.document.to_value()["rule_justifications"]) == {"keep-toy-518", "darkbishop-play", "gameplay"}
    assert candidate.mulligan_plan.rules[0].source_claim_ids == ()
    del draft["rule_justifications"]["gameplay"]
    with pytest.raises(ValueError, match="^starter_candidate_rule_justifications_invalid$"):
        validate(draft, semantic_context)


@pytest.mark.parametrize("refs,claims,observations,accepted", [
    (["both"], [{"claim_id": "both", "cards": ["A", "B"]}], [], True),
    (["deck"], [{"claim_id": "deck", "cards": [], "scope": "deck"}], [], True),
    (["a", "b"], [{"claim_id": "a", "cards": ["A"]}, {"claim_id": "b", "cards": ["B"]}], [], False),
    (["a"], [{"claim_id": "a", "cards": ["A"], "deck_match_scope": "exact_list", "sequence": ["A", "B"]}], [], False),
    (["empty"], [{"claim_id": "empty", "cards": [], "scope": "DECK"}], [], False),
    (["unknown"], [{"claim_id": "unknown"}], [], False),
    (["obs"], [], [{"observation_id": "obs", "card_ids": ["A", "B"]}], True),
    (["obs"], [], [{"observation_id": "obs", "card_ids": ["A"], "applicability": "exact_list", "scope": "deck"}], False),
    (["a", "b"], [], [{"observation_id": "a", "card_ids": ["A"]}, {"observation_id": "b", "card_ids": ["B"]}], False),
    (["both", "partial"], [{"claim_id": "both", "cards": ["A", "B"]}, {"claim_id": "partial", "cards": ["A"]}], [], False),
    (["linked"], [{"claim_id": "linked", "cards": ["EX1_625t"]}], [], False),
])
def test_basis_each_reference_covers_every_physical_source(refs, claims, observations, accepted):
    assert hasattr(starter_semantics, "semantic_rule_justifications"), "scoped rule basis missing"
    payload = {"rule": {"basis": "evidence", "evidence_refs": refs, "assumption": None}}
    kwargs = {"physical_rule_ids": {"A": {"rule"}, "B": {"rule"}}, "context_value": {"existing_claims": claims, "research_evidence": {"observations": observations}}, "assumptions": [ASSUMPTION]}
    if accepted:
        assert starter_semantics.semantic_rule_justifications(payload, **kwargs) == payload
    else:
        with pytest.raises(ValueError, match="^starter_candidate_rule_evidence_invalid$"):
            starter_semantics.semantic_rule_justifications(payload, **kwargs)


def reseal_semantic_context(value):
    """Pure document boundary fixture; no new frozen-source provenance claim."""
    from hsconfig.starter_context import validate_starter_context_document
    from hsconfig.starter_contract import SEMANTIC_STARTER_CONTEXT_FIELDS
    from hsconfig.starter_document import seal_starter_document

    value = deepcopy(value)
    value.pop("content_sha256")
    return validate_starter_context_document(seal_starter_document(
        value, expected_fields=SEMANTIC_STARTER_CONTEXT_FIELDS, schema_version=4,
    ))


def test_basis_order_only_baseline_change_requires_justification(semantic_context):
    from hsconfig.globalvalues_decisions import canonical_globalvalues_baseline_sha256

    value = semantic_context.document.to_value()
    baseline = value["globalvalues_baseline"]["values"]
    baseline["FirstTurnValueWeight"]["values"].append({"condition": HAND, "value": "0.5"})
    value["globalvalues_baseline"]["content_sha256"] = canonical_globalvalues_baseline_sha256(baseline)
    context = reseal_semantic_context(value)
    draft = semantic_draft(context)
    draft["globalvalues"] = deepcopy(baseline)
    draft["globalvalues"]["FirstTurnValueWeight"]["values"].reverse()
    draft["globalvalues_justifications"] = {}
    with pytest.raises(ValueError, match="^starter_candidate_globalvalues_justifications_invalid$"):
        validate(draft, context)


@pytest.mark.parametrize("surface", ["mulligan", "card_rules", "combo", "globalvalues"])
@pytest.mark.parametrize("condition", [None, "", " ", {}, {"runtime_condition": "*"}, {"hand_contains_any": ["A"]}, [], False, " *", "* ", "\t*", "coin  AND nocoin", "coin\tAND nocoin", "DELETE"])
def test_raw_condition_complete_candidate_never_coerced(semantic_context, surface, condition):
    draft = semantic_draft(semantic_context)
    add_combo(draft)
    synchronize_rules(draft, semantic_context)
    validate(draft, semantic_context)  # All four populated surfaces and bases are valid.
    row = draft[surface][0] if surface in {"mulligan", "card_rules"} else draft["combo"] if surface == "combo" else draft["globalvalues"]["FirstTurnValueWeight"]["values"][0]
    if condition == "DELETE":
        del row["condition"]
    else:
        row["condition"] = condition
    with pytest.raises(ValueError, match="^starter_candidate_condition_invalid$"):
        validate(draft, semantic_context)
    row["condition"] = "*"
    assert validate(draft, semantic_context).document.to_value()["schema_version"] == 4


@pytest.mark.parametrize("surface,error", [("mulligan", "mulligan_fields"), ("card_rules", "card_rule_fields"), ("combo", "combo_fields"), ("globalvalues", "globalvalue_row")])
def test_raw_condition_nonmapping_keeps_structural_error(semantic_context, surface, error):
    draft = semantic_draft(semantic_context)
    add_combo(draft)
    synchronize_rules(draft, semantic_context)
    if surface in {"mulligan", "card_rules"}:
        draft[surface][0] = False
    elif surface == "combo":
        draft["combo"] = False
    else:
        draft["globalvalues"]["FirstTurnValueWeight"]["values"][0] = False
    with pytest.raises(ValueError, match=f"^starter_candidate_{error}_invalid$"):
        validate(draft, semantic_context)


@pytest.mark.parametrize("surface,condition,error", [
    ("mulligan", "coin AND nocoin", "contradiction"),
    ("mulligan", f"coin AND {HAND} OR nocoin", "mixed_logic"),
    ("card_rules", "coin", "context_invalid"),
    ("combo", "coin", "context_invalid"),
    ("globalvalues", "coin", "context_invalid"),
    ("card_rules", "my_minion(count(),cardid=TOY_518) > 0", "context_invalid"),
    ("card_rules", "my_minions(count(),cardid=TOY_518) > 0", "invalid"),
])
def test_raw_condition_phase_policy_reaches_all_callers(semantic_context, surface, condition, error):
    draft = semantic_draft(semantic_context)
    add_combo(draft)
    synchronize_rules(draft, semantic_context)
    row = draft[surface][0] if surface in {"mulligan", "card_rules"} else draft["combo"] if surface == "combo" else draft["globalvalues"]["FirstTurnValueWeight"]["values"][0]
    row["condition"] = condition
    with pytest.raises(ValueError, match=f"^starter_candidate_condition_{error}$"):
        validate(draft, semantic_context)


@pytest.mark.parametrize("block", ["BeforeUseHeroPowerBonus", "OnChooseOneCardBonus", "OnDiscoverCardBonus", "BeforeBattlecryTargetBonus"])
def test_raw_condition_owner_capability_enforced_in_candidate(semantic_context, block):
    draft = semantic_draft(semantic_context)
    draft["card_rules"][0].update(source_card_id="TOY_518", runtime_card_id="TOY_518", behavior_block=block)
    with pytest.raises(ValueError, match="^starter_candidate_surface_owner_unproven$"):
        validate(synchronize_rules(draft, semantic_context), semantic_context)


@pytest.mark.parametrize("source_kind", ["claim", "observation"])
@pytest.mark.parametrize("scopes,accepted", [
    ([["TOY_518", "SW_448"]], True),
    ([["TOY_518"], ["SW_448"]], False),
    ([["TOY_518", "SW_448"], ["TOY_518"]], False),
])
def test_basis_complete_candidate_each_ref_must_cover_all_cards(semantic_context, source_kind, scopes, accepted):
    """Actual context/research/candidate validators; injected document evidence only."""
    from hashlib import sha256
    from hsconfig.live_start_research import build_research_result
    from hsconfig.package_request import FrozenJsonDocument

    value = semantic_context.document.to_value()
    refs = []
    if source_kind == "claim":
        for row, cards in zip(value["existing_claims"], scopes, strict=False):
            row["cards"] = sorted(cards)
            row.pop("scope", None)
            refs.append(row["claim_id"])
        assert len(refs) == len(scopes)
        value["existing_claims"].sort(key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
    else:
        records = [{
            "source_url": f"https://example.org/semantic/{index}", "evidence_id": f"scope-{index}",
            "content_sha256": str(index + 1) * 64, "retrieved_at": "2026-09-09T00:00:00Z",
            "normalized_text": "Keep " + " and ".join(value["card_metadata"][card]["name"] for card in cards) + " early.",
            "conflicts": [],
        } for index, cards in enumerate(scopes)]
        result = build_research_result(
            acquired={"source_records": records}, discovery_outcome="completed",
            attempts=[{"url": row["source_url"], "state": "completed", "error": None,
                       "record_sha256": "sha256:" + sha256(FrozenJsonDocument.from_value(row).canonical_json).hexdigest()} for row in records],
            deadline_utc=100.0, card_metadata=value["card_metadata"],
        ).to_value()
        assert len(result["observations"]) == len(scopes)
        for observation, cards in zip(result["observations"], scopes, strict=True):
            assert set(observation["card_ids"]) == set(cards)
            refs.append(observation["observation_id"])
        value["research_evidence"] = result
    context = reseal_semantic_context(value)
    draft = semantic_draft(context)
    draft["mulligan"][0].update(selector="SW_448+TOY_518", selector_kind="plus_combo")
    synchronize_rules(draft, context)
    validate(draft, context)  # Injection passed real structural validators independently of basis.
    draft["rule_justifications"]["keep-toy-518"] = {"basis": "evidence", "evidence_refs": refs, "assumption": None}
    if accepted:
        candidate = validate(draft, context)
        assert candidate.mulligan_plan.rules[0].source_claim_ids == ()
    else:
        with pytest.raises(ValueError, match="^starter_candidate_rule_evidence_invalid$"):
            validate(draft, context)
        draft["rule_justifications"]["keep-toy-518"] = {"basis": "inference", "evidence_refs": [], "assumption": ASSUMPTION}
        assert validate(draft, context).mulligan_plan.rules


def test_raw_condition_frozen_owner_positive_and_actual_runtime_type(tmp_path, monkeypatch):
    """Synthetic capabilities enter before real normalization/snapshot/freeze."""
    from hsconfig.starter_context import build_semantic_starter_context
    from tests.helpers.semantic_start import semantic_frozen_inputs

    def source_rows(rows, main_ids):
        assert "TOY_518" in main_ids
        result = []
        for raw in rows:
            if raw["id"] == "TOY_518":
                raw = {**raw, "type": "MINION", "mechanics": ["BATTLECRY", "CHOOSE_ONE", "DISCOVER"], "playRequirements": {"REQ_TARGET_TO_PLAY": 0}}
            if raw["id"] == "EX1_625t":
                raw = {**raw, "type": "HERO_POWER"}
            result.append(raw)
        if not any(row["id"] == "EX1_625t" for row in result):
            result.append({"id": "EX1_625t", "dbfId": 999001, "name": "Mind Spike", "type": "HERO_POWER", "cost": 2, "collectible": False})
        return result

    context = build_semantic_starter_context(semantic_frozen_inputs(tmp_path, monkeypatch, transform_rows=source_rows))
    for block in ("BeforeBattlecryTargetBonus", "OnChooseOneCardBonus", "OnDiscoverCardBonus", "BeforeOverkilledBonus", "OnBoardBonus"):
        draft = semantic_draft(context)
        draft["card_rules"][0].update(source_card_id="TOY_518", runtime_card_id="TOY_518", behavior_block=block)
        candidate = validate(synchronize_rules(draft, context), context)
        assert candidate.card_behavior_rows[0].to_value()["behavior_block"] == block
    draft = semantic_draft(context)
    draft["card_rules"][0].update(runtime_card_id="EX1_625t", link_kind="hero_power_transform", behavior_block="BeforeUseHeroPowerBonus")
    assert validate(draft, context).card_behavior_rows[0].to_value()["runtime_card_id"] == "EX1_625t"
    draft["card_rules"][0].update(source_card_id="TOY_518")
    with pytest.raises(ValueError, match="^starter_candidate_runtime_owner_unauthorized$"):
        validate(synchronize_rules(draft, context), context)
