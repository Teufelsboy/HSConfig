"""Fresh review-facts receipts cannot authorize stale or forged candidates."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_document import seal_starter_document
from hsconfig.starter_review import validate_starter_review
from tests.helpers.quality_start import (
    quality_shadowpriest_context as quality_shadowpriest_context,
)
from tests.test_quality_starter_candidate import (
    context_with_observation,
    quality_draft,
    seal_quality_candidate,
)


def quality_receipt(context, candidate, mutate=None):
    from hsconfig.starter_contract import QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS
    from hsconfig.starter_review import build_candidate_review_facts

    value = {
        "schema_version": 2,
        "receipt_kind": "candidate_validation",
        "run_id": "a" * 32,
        "candidate_revision": candidate.candidate_revision,
        "starter_context_sha256": context.document.content_sha256,
        "candidate_sha256": candidate.document.content_sha256,
        "status": "valid",
        "findings": [],
        "review_facts": build_candidate_review_facts(
            context=context, candidate=candidate
        ).to_value(),
    }
    if mutate:
        mutate(value)
    return FrozenJsonDocument.from_value(
        seal_starter_document(
            value,
            expected_fields=QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
            schema_version=2,
        ).to_value()
    )


def quality_review(context, candidate, receipt, mutate=None):
    from hsconfig.starter_contract import QUALITY_STARTER_REVIEW_FIELDS

    value = {
        "schema_version": 3,
        "review_id": "review-1",
        "review_status": "approved",
        "confidence": "limited",
        "starter_context_sha256": context.document.content_sha256,
        "candidate_id": candidate.candidate_id,
        "candidate_revision": candidate.candidate_revision,
        "candidate_sha256": candidate.document.content_sha256,
        "candidate_validation_receipt_sha256": receipt.to_value()["content_sha256"],
        "revision_requests": [],
        "review_summary": "The opening decisions are coherent with limited evidence.",
    }
    if mutate:
        mutate(value)
    return seal_starter_document(
        value, expected_fields=QUALITY_STARTER_REVIEW_FIELDS, schema_version=3
    )


def test_quality_review_facts_show_decisions_and_exact_runtime_owner(
    quality_shadowpriest_context,
):
    from hsconfig.starter_review import build_candidate_review_facts

    context = quality_shadowpriest_context
    candidate = validate_starter_candidate(
        seal_quality_candidate(quality_draft(context)), context=context
    )
    facts = build_candidate_review_facts(
        context=context, candidate=candidate
    ).to_value()
    assert facts["starter_context_sha256"] == context.document.content_sha256
    assert facts["candidate_sha256"] == candidate.document.content_sha256
    assert facts["candidate_revision"] == 1
    assert list(facts["globalvalues_changes"]) == ["FirstTurnValueWeight"]
    assert facts["globalvalues_changes"]["FirstTurnValueWeight"]["after"] == {
        "values": [{"condition": "*", "value": "0x1.8000000000000p-1"}]
    }
    assert {
        row["card_id"]
        for row in facts["card_dispositions"]
        if row["disposition"] == "configured"
    } == {"SW_448", "TOY_518"}
    hero = next(
        row
        for row in facts["rules_by_runtime_owner"]
        if row["rule_id"] == "darkbishop-play"
    )
    assert hero["runtime_card_id"] == "SW_448"
    assert hero["source_card_ids"] == ["SW_448"]
    assert hero["surface"] == "BeforePlayCardBonus"
    assert facts["evidence_references"] == []
    assert "This curve benefits from early pressure." in facts["assumptions"]
    assert facts["findings"] == {
        "runtime_duplicates": [],
        "runtime_conflicts": [],
        "research_conflicts": [],
    }
    assert facts["runtime_authorized"] is False


def test_quality_review_requires_matching_receipt(quality_shadowpriest_context):
    context = quality_shadowpriest_context
    candidate = validate_starter_candidate(
        seal_quality_candidate(quality_draft(context, mulligan_only=True)),
        context=context,
    )
    receipt = quality_receipt(context, candidate)
    document = quality_review(context, candidate, receipt)
    assert (
        validate_starter_review(
            document, context=context, candidate=candidate, validation_receipt=receipt
        ).review_status
        == "approved"
    )
    with pytest.raises(ValueError, match="starter_review_validation_receipt_invalid"):
        validate_starter_review(document, context=context, candidate=candidate)


@pytest.mark.parametrize(
    "defect",
    [
        "facts",
        "candidate",
        "context",
        "revision",
        "status",
        "findings",
        "run_id",
        "digest",
        "schema",
    ],
)
def test_quality_review_rejects_resealed_stale_receipt(
    quality_shadowpriest_context, defect
):
    context = quality_shadowpriest_context
    candidate = validate_starter_candidate(
        seal_quality_candidate(quality_draft(context)), context=context
    )

    def mutate(value):
        if defect == "facts":
            value["review_facts"]["globalvalues_changes"] = {}
            facts = value["review_facts"]
            fields = frozenset(facts)
            facts.pop("content_sha256")
            value["review_facts"] = seal_starter_document(
                facts,
                expected_fields=fields,
                schema_version=1,
            ).to_value()
        elif defect == "candidate":
            value["candidate_sha256"] = "sha256:" + "0" * 64
        elif defect == "context":
            value["starter_context_sha256"] = "sha256:" + "0" * 64
        elif defect == "revision":
            value["candidate_revision"] = 2
        elif defect == "status":
            value["status"] = "invalid"
        elif defect == "findings":
            value["findings"] = ["conflict"]
        elif defect == "run_id":
            value["run_id"] = "arbitrary"

    receipt = quality_receipt(context, candidate, mutate)
    if defect in {"digest", "schema"}:
        value = receipt.to_value()
        value["content_sha256" if defect == "digest" else "schema_version"] = (
            "sha256:" + "0" * 64 if defect == "digest" else 1
        )
        receipt = FrozenJsonDocument.from_value(value)
    document = quality_review(context, candidate, receipt)
    with pytest.raises(ValueError, match="starter_review_validation_receipt_invalid"):
        validate_starter_review(
            document, context=context, candidate=candidate, validation_receipt=receipt
        )


@pytest.mark.parametrize(
    "field",
    [
        "candidate_sha256",
        "starter_context_sha256",
        "candidate_revision",
        "candidate_validation_receipt_sha256",
    ],
)
def test_quality_review_rejects_wrong_binding(quality_shadowpriest_context, field):
    context = quality_shadowpriest_context
    candidate = validate_starter_candidate(
        seal_quality_candidate(quality_draft(context)), context=context
    )
    receipt = quality_receipt(context, candidate)
    document = quality_review(
        context,
        candidate,
        receipt,
        lambda row: row.update(
            {field: 2 if field == "candidate_revision" else "sha256:" + "0" * 64}
        ),
    )
    with pytest.raises(ValueError, match="starter_review_"):
        validate_starter_review(
            document, context=context, candidate=candidate, validation_receipt=receipt
        )


def test_quality_facts_recompute_typed_candidate(quality_shadowpriest_context):
    from hsconfig.starter_review import build_candidate_review_facts

    context = quality_shadowpriest_context
    candidate = validate_starter_candidate(
        seal_quality_candidate(quality_draft(context)), context=context
    )
    forged = replace(candidate, card_behavior_rows=())
    with pytest.raises(ValueError, match="starter_review_candidate_invalid"):
        build_candidate_review_facts(context=context, candidate=forged)


def test_quality_review_schema_cannot_bypass_receipt(quality_shadowpriest_context):
    from hsconfig.starter_contract import STARTER_REVIEW_FIELDS

    context = quality_shadowpriest_context
    candidate = validate_starter_candidate(
        seal_quality_candidate(quality_draft(context)), context=context
    )
    receipt = quality_receipt(context, candidate)
    value = quality_review(context, candidate, receipt).to_value()
    value.pop("content_sha256")
    value.pop("candidate_validation_receipt_sha256")
    value["schema_version"] = 2
    document = seal_starter_document(
        value, expected_fields=STARTER_REVIEW_FIELDS, schema_version=2
    )
    with pytest.raises(ValueError, match="starter_review_schema_pair_invalid"):
        validate_starter_review(document, context=context, candidate=candidate)


def test_quality_facts_preserve_observation_support_and_conflicts(
    quality_shadowpriest_context,
):
    from hsconfig.starter_review import build_candidate_review_facts

    context = context_with_observation(quality_shadowpriest_context)
    observation_id = context.document.to_value()["research_evidence"]["observations"][
        0
    ]["observation_id"]
    draft = quality_draft(context)
    draft["globalvalues_justifications"]["FirstTurnValueWeight"].update(
        basis="evidence",
        evidence_refs=[observation_id],
        assumption=None,
    )
    candidate = validate_starter_candidate(
        seal_quality_candidate(draft), context=context
    )
    facts = build_candidate_review_facts(
        context=context, candidate=candidate
    ).to_value()
    assert facts["evidence_references"] == [
        {"reference_id": observation_id, "kind": "observation"}
    ]
    assert facts["findings"]["research_conflicts"] == [
        {
            "observation_id": observation_id,
            "conflict": "opening advice differs",
        }
    ]
    assert facts["runtime_authorized"] is False


def test_quality_compiler_joins_main_metadata_without_zero_filling(
    tmp_path, monkeypatch
):
    from hsconfig.starter_compiler import _single_candidate_compiler_state
    from hsconfig.starter_context import build_quality_starter_context
    from tests.helpers.quality_start import quality_frozen_inputs

    frozen = quality_frozen_inputs(tmp_path, monkeypatch)
    context = build_quality_starter_context(frozen)
    candidate = validate_starter_candidate(
        seal_quality_candidate(quality_draft(context, mulligan_only=True)),
        context=context,
    )
    original = deepcopy(context.document.to_value())
    state = _single_candidate_compiler_state(
        request=SimpleNamespace(frozen_compiler_inputs=frozen),
        approval=SimpleNamespace(context=context, candidate=candidate),
        card_behavior_plan={"rows": []},
    )
    rows = {row["card_id"]: row for row in state["card_metadata"]["cards"]}
    assert set(rows) == {row["card_id"] for row in original["cards"]}
    assert "EX1_625t" not in rows
    for card_id, row in rows.items():
        assert row["name"] == original["card_metadata"][card_id]["name"]
        assert row["attack"] == original["card_metadata"][card_id]["attack"]
    assert context.document.to_value() == original
