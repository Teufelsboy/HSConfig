"""Truthful schema4 decision facts and independently bound review authority."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256

import pytest

from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_document import seal_starter_document
from hsconfig.starter_review import build_candidate_review_facts, validate_starter_review
from tests.test_semantic_starter_candidate import (
    HAND,
    add_combo,
    reseal_semantic_context,
    semantic_context as semantic_context,
    semantic_draft,
    synchronize_rules,
    validate,
)


def ordered_draft(context):
    draft = semantic_draft(context)
    draft["mulligan"][0]["condition"] = "coin"
    draft["mulligan"] += [
        {"rule_id": "discard-sw", "selector": "SW_448", "selector_kind": "card",
         "action": "discard", "condition": "*"},
        {"rule_id": "pair", "selector": "TOY_518+SW_448", "selector_kind": "plus_combo",
         "action": "hold", "condition": "*"},
        {"rule_id": "double", "selector": "TOY_518+TOY_518", "selector_kind": "plus_combo",
         "action": "hold", "condition": "*"},
    ]
    draft["card_rules"][0]["condition"] = HAND
    draft["card_rules"] += [
        {**draft["card_rules"][0], "rule_id": "toy-play", "source_card_id": "TOY_518",
         "runtime_card_id": "TOY_518", "condition": "*"},
        {**draft["card_rules"][0], "rule_id": "sw-board", "behavior_block": "OnBoardBonus",
         "condition": "*"},
        {**draft["card_rules"][0], "rule_id": "sw-fallback", "condition": "*", "value": "2"},
    ]
    add_combo(draft)
    return synchronize_rules(draft, context)


@pytest.fixture(scope="module")
def semantic_candidate_pair(semantic_context):
    return semantic_context, validate(ordered_draft(semantic_context), semantic_context)


@pytest.mark.parametrize("mode", ["ordered", "alternatives", "discard_only"])
def test_semantic_facts_match_actual_mulligan_emission(semantic_context, mode):
    """Break: sorted/collapsed selectors or coverage-based indices misreport execution."""
    from hsconfig.compile_mulligan import compile_mulligan

    draft = ordered_draft(semantic_context)
    if mode == "alternatives":
        draft["mulligan"][2].update(selector="TOY_518,SW_448", selector_kind="card_list")
    elif mode == "discard_only":
        draft["mulligan"] = [draft["mulligan"][1]]
    candidate = validate(synchronize_rules(draft, semantic_context), semantic_context)
    facts = build_candidate_review_facts(context=semantic_context, candidate=candidate).to_value()
    runtime = compile_mulligan(candidate.mulligan_plan)["Mulligan"]["values"]
    rows = [r for r in facts["rules_by_runtime_owner"] if r["surface"] == "Mulligan"]
    assert len(rows) == (1 if mode == "discard_only" else 5)
    for row in rows:
        assert type(row["evaluation_index"]) is int
        emitted = runtime[row["evaluation_index"] - 1]
        assert (row["normalized_selector"], row["condition"], row["action"]) == (
            emitted["mulligan"], emitted["condition"], emitted["value"],
        )
    by_rule = {r["rule_id"]: r for r in rows}
    if mode != "discard_only":
        assert {k: r["evaluation_index"] for k, r in by_rule.items()} == {
            "keep-toy-518": 1, "discard-sw": 2, "pair": 3, "double": 4,
        }
        assert by_rule["double"]["selector_multiset"] == [{"card_id": "TOY_518", "count": 2}]
        assert by_rule["pair"]["selector_kind"] == ("card_list" if mode == "alternatives" else "plus_combo")
        assert by_rule["pair"]["selector_multiset"] == [
            {"card_id": "SW_448", "count": 1}, {"card_id": "TOY_518", "count": 1},
        ]
    assert facts["schema_version"] == 2
    assert facts["validation_scope"] == {
        "structural_checks": ["exact_duplicate", "identical_condition_conflict",
                              "owner_surface", "condition_context", "opening_copy_count"],
        "semantic_coherence": "independent_review_required", "overlap_analysis": "not_exhaustive",
    }
    assert facts["runtime_authorized"] is False


def test_semantic_facts_keep_owner_surface_evaluation_indices(semantic_candidate_pair, tmp_path, monkeypatch):
    """Break: source-owner/global counting or content sorting changes owner-local order."""
    context, candidate = semantic_candidate_pair
    rows = build_candidate_review_facts(context=context, candidate=candidate).to_value()["rules_by_runtime_owner"]
    card_rows = [r for r in rows if r["surface"] not in {"Mulligan", "Combo"}]
    assert [(r["runtime_card_id"], r["surface"], r["evaluation_index"], r["rule_id"]) for r in card_rows] == [
        ("SW_448", "BeforePlayCardBonus", 1, "darkbishop-play"),
        ("SW_448", "BeforePlayCardBonus", 2, "sw-fallback"),
        ("SW_448", "OnBoardBonus", 1, "sw-board"),
        ("TOY_518", "BeforePlayCardBonus", 1, "toy-play"),
    ]
    assert [r["condition"] for r in card_rows[:2]] == [HAND, "*"]
    assert rows == sorted(rows, key=lambda r: (r["runtime_card_id"], r["surface"], r["evaluation_index"], r["rule_id"]))

    from hsconfig.starter_context import build_semantic_starter_context
    from tests.helpers.semantic_start import semantic_frozen_inputs

    def linked_source_rows(source_rows, _main_ids):
        # Synthetic target capability enters before real snapshot/freeze validation.
        rows = [{**row, "type": "HERO_POWER"} if row["id"] == "EX1_625t" else row for row in source_rows]
        if not any(row["id"] == "EX1_625t" for row in rows):
            rows.append({"id": "EX1_625t", "dbfId": 999001, "name": "Mind Spike",
                         "type": "HERO_POWER", "cost": 2, "collectible": False})
        return rows

    linked_context = build_semantic_starter_context(
        semantic_frozen_inputs(tmp_path, monkeypatch, transform_rows=linked_source_rows),
    )
    draft = semantic_draft(linked_context)
    draft["card_rules"][0].update(runtime_card_id="EX1_625t", link_kind="hero_power_transform",
                                 behavior_block="BeforeUseHeroPowerBonus")
    linked_candidate = validate(draft, linked_context)
    linked_facts = build_candidate_review_facts(context=linked_context, candidate=linked_candidate).to_value()
    linked = next(r for r in linked_facts["rules_by_runtime_owner"] if r["surface"] == "BeforeUseHeroPowerBonus")
    assert (linked["runtime_card_id"], linked["source_card_ids"], linked["evaluation_index"]) == (
        "EX1_625t", ["SW_448"], 1,
    )


def test_semantic_facts_combo_coverage_uses_emitted_decision_index(semantic_candidate_pair):
    """Break: expanding repeated coverage creates fictitious Combo decisions."""
    from hsconfig.compile_combo import compile_combo

    context, candidate = semantic_candidate_pair
    rows = build_candidate_review_facts(context=context, candidate=candidate).to_value()["rules_by_runtime_owner"]
    rows = [r for r in rows if r["surface"] == "Combo"]
    runtime = compile_combo(candidate.combo_plan)["ComboList"]["values"]
    assert len(runtime) == 1 and len(rows) == 3
    assert [r["runtime_card_id"] for r in rows] == ["SW_448", "SW_448", "TOY_518"]
    for row in rows:
        assert row["evaluation_index"] == 1
        assert type(row["evaluation_index"]) is int
        assert row["source_card_ids"] == ["SW_448", "TOY_518", "SW_448"]
        assert row["condition"] == runtime[row["evaluation_index"] - 1]["condition"]
        assert row["values"] == ["2", "3", "4"]


def test_semantic_facts_globalvalues_order_only_change_is_visible(semantic_context):
    """Break: facts1's sorted projection hides a validated order-only decision."""
    from hsconfig.globalvalues_decisions import canonical_globalvalues_baseline_sha256

    value = semantic_context.document.to_value()
    baseline = value["globalvalues_baseline"]["values"]
    baseline["FirstTurnValueWeight"]["values"] = [
        {"condition": HAND, "value": "0.5"}, {"condition": "*", "value": "0.75"},
    ]
    value["globalvalues_baseline"]["content_sha256"] = canonical_globalvalues_baseline_sha256(baseline)
    context = reseal_semantic_context(value)
    draft = semantic_draft(context)
    draft["globalvalues"] = deepcopy(baseline)
    draft["globalvalues"]["FirstTurnValueWeight"]["values"].reverse()
    candidate = validate(draft, context)
    changes = build_candidate_review_facts(context=context, candidate=candidate).to_value()["globalvalues_changes"]
    assert list(changes) == ["FirstTurnValueWeight"]
    change = changes["FirstTurnValueWeight"]
    assert change["before"]["values"] == [
        {"condition": HAND, "value": "0x1.0000000000000p-1"},
        {"condition": "*", "value": "0x1.8000000000000p-1"},
    ]
    assert change["after"]["values"] == list(reversed(change["before"]["values"]))
    assert change["justification"] == draft["globalvalues_justifications"]["FirstTurnValueWeight"]


def evidence_context(context):
    """Pure document-boundary evidence; no acquired or runtime authority claimed."""
    from hsconfig.live_start_research import build_research_result

    value = context.document.to_value()
    refs = []
    for row in value["existing_claims"][:3]:
        row["cards"] = ["SW_448", "TOY_518"]
        row.pop("scope", None)
        refs.append(row["claim_id"])
    assert len(refs) == 3
    value["existing_claims"].sort(key=lambda r: FrozenJsonDocument.from_value(r).canonical_json)
    record = {
        "source_url": "https://example.org/semantic-facts", "evidence_id": "facts-page",
        "content_sha256": "a" * 64, "retrieved_at": "2026-09-09T00:00:00Z",
        "normalized_text": "Keep " + value["card_metadata"]["TOY_518"]["name"] + " early.",
        "conflicts": ["Independent opening advice differs"],
    }
    result = build_research_result(
        acquired={"source_records": [record]}, discovery_outcome="completed",
        attempts=[{"url": record["source_url"], "state": "completed", "error": None,
                   "record_sha256": "sha256:" + sha256(FrozenJsonDocument.from_value(record).canonical_json).hexdigest()}],
        deadline_utc=100.0, card_metadata=value["card_metadata"],
    ).to_value()
    value["research_evidence"] = result
    return reseal_semantic_context(value), refs, result["observations"][0]["observation_id"]


def test_semantic_facts_project_complete_rule_bases_and_reference_union(semantic_context):
    """Break: GlobalValues-only refs lose per-rule evidence and declared assumptions."""
    context, refs, observation = evidence_context(semantic_context)
    draft = ordered_draft(context)
    for rule, selected in [("pair", [refs[0]]), ("darkbishop-play", [refs[1]]), ("gameplay", [refs[2]])]:
        draft["rule_justifications"][rule] = {"basis": "evidence", "evidence_refs": selected, "assumption": None}
    draft["rule_justifications"]["keep-toy-518"]["evidence_refs"] = [observation]
    draft["globalvalues_justifications"]["FirstTurnValueWeight"].update(
        basis="evidence", evidence_refs=[refs[2]], assumption=None,
    )
    candidate = validate(draft, context)
    facts = build_candidate_review_facts(context=context, candidate=candidate).to_value()
    assert facts["evidence_references"] == [
        {"reference_id": ref, "kind": "observation" if ref == observation else "claim"}
        for ref in sorted([*refs, observation])
    ]
    assert {r["rule_id"] for r in facts["rules_by_runtime_owner"]} == set(draft["rule_justifications"])
    for row in facts["rules_by_runtime_owner"]:
        assert row["rule_justification"] == draft["rule_justifications"][row["rule_id"]]
        assert row["rationale"] == draft["rule_rationales"][row["rule_id"]]
    assert facts["findings"]["research_conflicts"] == [
        {"observation_id": observation, "conflict": "Independent opening advice differs"},
    ]
    assert candidate.mulligan_plan.rules[0].source_claim_ids == ()


@pytest.mark.parametrize("carrier", ["context", "card_rows", "mulligan_order"])
def test_semantic_facts_reject_forged_reconstructed_carriers(semantic_candidate_pair, carrier):
    """Break: trusting a valid document while accepting a forged derived carrier."""
    context, candidate = semantic_candidate_pair
    if carrier == "context":
        context = replace(context, deck_fingerprint="Forged")
    elif carrier == "card_rows":
        candidate = replace(candidate, card_behavior_rows=())
    else:
        candidate = replace(candidate, mulligan_plan=replace(candidate.mulligan_plan, rules=tuple(reversed(candidate.mulligan_plan.rules))))
    with pytest.raises(ValueError, match="^starter_review_(context|candidate)_invalid$"):
        build_candidate_review_facts(context=context, candidate=candidate)


def semantic_receipt(context, candidate, *, run_id="a" * 32, mutate=None):
    from hsconfig.starter_contract import QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS

    value = {
        "schema_version": 3, "receipt_kind": "candidate_validation", "run_id": run_id,
        "candidate_revision": candidate.candidate_revision,
        "starter_context_sha256": context.document.content_sha256,
        "candidate_sha256": candidate.document.content_sha256,
        "status": "valid", "findings": [],
        "review_facts": build_candidate_review_facts(context=context, candidate=candidate).to_value(),
    }
    if mutate is not None:
        mutate(value)
    return FrozenJsonDocument.from_value(seal_starter_document(
        value, expected_fields=QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
        schema_version=value["schema_version"],
    ).to_value())


def semantic_review(context, candidate, receipt, *, confidence="limited", mutate=None):
    from hsconfig.starter_contract import SEMANTIC_STARTER_REVIEW_FIELDS

    value = {
        "schema_version": 4, "review_id": "semantic-review", "review_status": "approved",
        "confidence": confidence, "starter_context_sha256": context.document.content_sha256,
        "candidate_id": candidate.candidate_id, "candidate_revision": candidate.candidate_revision,
        "candidate_sha256": candidate.document.content_sha256,
        "candidate_validation_receipt_sha256": receipt.to_value()["content_sha256"],
        "revision_requests": [], "review_summary": "Independent bounded review of the starting decisions.",
    }
    if mutate is not None:
        mutate(value)
    return seal_starter_document(value, expected_fields=SEMANTIC_STARTER_REVIEW_FIELDS,
                                 schema_version=value["schema_version"])


def assert_bound_review(context, candidate, confidence="limited"):
    receipt = semantic_receipt(context, candidate)
    document = semantic_review(context, candidate, receipt, confidence=confidence)
    review = validate_starter_review(document, context=context, candidate=candidate, validation_receipt=receipt)
    assert review.confidence == confidence and review.review_status == "approved"
    return receipt, document


@pytest.mark.parametrize("confidence", ["high", "limited"])
def test_semantic_review_accepts_fresh_bound_receipt(semantic_candidate_pair, confidence):
    """Break: schema4 is rejected or high confidence is mistakenly treated as authority."""
    context, candidate = semantic_candidate_pair
    receipt, _ = assert_bound_review(context, candidate, confidence)
    assert receipt.to_value()["schema_version"] == 3
    assert receipt.to_value()["review_facts"]["schema_version"] == 2
    assert receipt.to_value()["review_facts"]["runtime_authorized"] is False


def test_semantic_review_requires_receipt(semantic_candidate_pair):
    """Break: the review4 branch skips the mandatory fresh receipt consumer."""
    context, candidate = semantic_candidate_pair
    _, document = assert_bound_review(context, candidate)
    with pytest.raises(ValueError, match="^starter_review_validation_receipt_invalid$"):
        validate_starter_review(document, context=context, candidate=candidate)


@pytest.mark.parametrize("mixed", ["review3", "receipt2", "facts1", "review_bool", "review_float", "receipt_bool", "receipt_float", "facts_bool", "facts_float", "context3", "candidate3"])
def test_semantic_review_rejects_mixed_contracts(semantic_candidate_pair, mixed):
    """Break: only checking outer version or numeric equality admits a mixed route."""
    from hsconfig.starter_document import StarterDocument

    context, candidate = semantic_candidate_pair
    receipt, document = assert_bound_review(context, candidate)
    if mixed.startswith("review"):
        raw = document.to_value()
        raw["schema_version"] = {"review3": 3, "review_bool": True, "review_float": 4.0}[mixed]
        if mixed == "review3":
            raw.pop("content_sha256")
            document = seal_starter_document(raw, expected_fields=frozenset(document.to_value()), schema_version=3)
        else:
            document = StarterDocument(FrozenJsonDocument.from_value(raw), document.content_sha256)
    elif mixed.startswith("receipt"):
        if mixed == "receipt2":
            receipt = semantic_receipt(context, candidate, mutate=lambda v: v.update(schema_version=2))
        else:
            raw = receipt.to_value()
            raw["schema_version"] = True if mixed == "receipt_bool" else 3.0
            receipt = FrozenJsonDocument.from_value(raw)
        document = semantic_review(context, candidate, receipt)
    elif mixed.startswith("facts"):
        bad = {"facts1": 1, "facts_bool": True, "facts_float": 2.0}[mixed]
        receipt = semantic_receipt(context, candidate, mutate=lambda v: v["review_facts"].update(schema_version=bad))
        document = semantic_review(context, candidate, receipt)
    else:
        carrier = context if mixed == "context3" else candidate
        raw = carrier.document.to_value()
        raw["schema_version"] = 3
        raw.pop("content_sha256")
        fields = frozenset(carrier.document.to_value())
        replaced = replace(carrier, document=seal_starter_document(raw, expected_fields=fields, schema_version=3))
        if mixed == "context3":
            context = replaced
        else:
            candidate = replaced
    with pytest.raises(ValueError, match="^starter_review_"):
        validate_starter_review(document, context=context, candidate=candidate, validation_receipt=receipt)


@pytest.mark.parametrize("confidence", ["high", "limited"])
@pytest.mark.parametrize("defect", ["order", "index", "multiset", "basis", "assumption", "refs", "covered_rule", "scope", "global_order"])
def test_semantic_review_rejects_resealed_facts_mutations(semantic_candidate_pair, confidence, defect):
    """Break: trusting coherently resealed supplied facts instead of fresh reconstruction."""
    context, candidate = semantic_candidate_pair
    assert_bound_review(context, candidate, confidence)

    def mutate(value):
        facts = value["review_facts"]
        rows = facts["rules_by_runtime_owner"]
        first = next(r for r in rows if r["surface"] == "Mulligan")
        if defect == "order":
            rows.reverse()
        elif defect == "index":
            first["evaluation_index"] = 99
        elif defect == "multiset":
            first["selector_multiset"][0]["count"] = 9
        elif defect == "basis":
            del first["rule_justification"]
        elif defect == "assumption":
            first["rule_justification"]["assumption"] = "Changed reasoning."
        elif defect == "refs":
            first["rule_justification"]["evidence_refs"] = ["unknown-ref"]
        elif defect == "covered_rule":
            rows.remove(first)
        elif defect == "scope":
            facts["validation_scope"]["semantic_coherence"] = "proved"
        else:
            facts["globalvalues_changes"]["FirstTurnValueWeight"]["after"] = facts["globalvalues_changes"]["FirstTurnValueWeight"]["before"]
        fields = frozenset(facts)
        facts.pop("content_sha256")
        value["review_facts"] = seal_starter_document(facts, expected_fields=fields, schema_version=2).to_value()

    receipt = semantic_receipt(context, candidate, mutate=mutate)
    document = semantic_review(context, candidate, receipt, confidence=confidence)
    with pytest.raises(ValueError, match="^starter_review_validation_receipt_invalid$"):
        validate_starter_review(document, context=context, candidate=candidate, validation_receipt=receipt)


@pytest.mark.parametrize("confidence", ["high", "limited"])
@pytest.mark.parametrize("defect", ["candidate", "context", "revision", "digest", "run_id", "status", "findings"])
def test_semantic_review_rejects_stale_candidate_binding(semantic_candidate_pair, confidence, defect):
    """Break: review confidence masks invalid receipt identity or structural status."""
    context, candidate = semantic_candidate_pair
    assert_bound_review(context, candidate, confidence)
    changes = {
        "candidate": {"candidate_sha256": "sha256:" + "0" * 64},
        "context": {"starter_context_sha256": "sha256:" + "0" * 64},
        "revision": {"candidate_revision": 2}, "run_id": {"run_id": "not-a-run"},
        "status": {"status": "invalid"}, "findings": {"findings": ["conflict"]}, "digest": {},
    }
    receipt = semantic_receipt(context, candidate, mutate=lambda v: v.update(changes[defect]))
    document = semantic_review(context, candidate, receipt, confidence=confidence,
                               mutate=(lambda v: v.update(candidate_validation_receipt_sha256="sha256:" + "0" * 64)) if defect == "digest" else None)
    with pytest.raises(ValueError, match="^starter_review_validation_receipt_invalid$"):
        validate_starter_review(document, context=context, candidate=candidate, validation_receipt=receipt)


@pytest.mark.parametrize("confidence", ["high", "limited"])
@pytest.mark.parametrize("carrier", ["context", "candidate"])
def test_semantic_review_rejects_forged_reconstructed_carriers(semantic_candidate_pair, confidence, carrier):
    """Break: fresh facts validation is skipped when the supplied review says high."""
    context, candidate = semantic_candidate_pair
    receipt, document = assert_bound_review(context, candidate, confidence)
    if carrier == "context":
        context = replace(context, deck_fingerprint="Forged")
    else:
        candidate = replace(candidate, card_behavior_rows=())
    with pytest.raises(ValueError, match="^starter_review_(context|candidate)_invalid$"):
        validate_starter_review(document, context=context, candidate=candidate, validation_receipt=receipt)
