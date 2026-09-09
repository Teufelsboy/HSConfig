"""Quality candidate boundaries, without session or live runtime authority."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256

import pytest

from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_context import validate_starter_context_document
from hsconfig.starter_contract import QUALITY_STARTER_CONTEXT_FIELDS
from hsconfig.starter_document import seal_starter_document
from tests.helpers.quality_start import (
    quality_shadowpriest_context as quality_shadowpriest_context,
)
from tests.test_starter_candidate import candidate_draft


def quality_draft(context, *, mulligan_only=False):
    draft = candidate_draft(
        context, candidate_id="lead", role="lead_strategist", schema_version=3
    )
    # The quality snapshot fixture has no resolved Mind Spike target. Use a
    # physical self-owned rule, not fabricated ownership from the old factory.
    draft["card_rules"][0].update(
        rule_id="darkbishop-play",
        runtime_card_id="SW_448",
        link_kind="self",
        behavior_block="BeforePlayCardBonus",
    )
    draft["rule_rationales"].pop("darkbishop-mind-spike")
    draft["rule_rationales"]["darkbishop-play"] = "Prefer the physical battlecry play."
    for row in draft["card_dispositions"]:
        row["rule_ids"] = [
            "darkbishop-play" if rule_id == "darkbishop-mind-spike" else rule_id
            for rule_id in row["rule_ids"]
        ]
    draft["globalvalues_justifications"] = {
        "FirstTurnValueWeight": {
            "decision": "Prefer early pressure.",
            "baseline_gap": "The generic opening weight understates this curve.",
            "basis": "inference",
            "evidence_refs": [],
            "assumption": "This curve benefits from early pressure.",
        }
    }
    draft["assumptions"].append("This curve benefits from early pressure.")
    if mulligan_only:
        draft["globalvalues"] = deepcopy(
            context.document.to_value()["globalvalues_baseline"]["values"]
        )
        draft["globalvalues_justifications"] = {}
        draft["card_rules"] = []
        draft["combo"] = None
        draft["rule_rationales"].pop("darkbishop-play")
        for row in draft["card_dispositions"]:
            row["rule_ids"] = ["keep-toy-518"] if row["card_id"] == "TOY_518" else []
            row["disposition"] = (
                "configured" if row["rule_ids"] else "deliberately_unconfigured"
            )
            row["reason"] = (
                "Opening-hand rule."
                if row["rule_ids"]
                else "No additional override justified."
            )
    return draft


def seal_quality_candidate(draft):
    from hsconfig.starter_contract import QUALITY_STARTER_CANDIDATE_FIELDS

    return seal_starter_document(
        draft, expected_fields=QUALITY_STARTER_CANDIDATE_FIELDS, schema_version=3
    )


def reseal_context(value):
    value = deepcopy(value)
    value.pop("content_sha256")
    return validate_starter_context_document(
        seal_starter_document(
            value, expected_fields=QUALITY_STARTER_CONTEXT_FIELDS, schema_version=3
        )
    )


def context_with_observation(context):
    """Pure sealed-context fixture: a synthetic page, never live acquisition."""
    from hsconfig.live_start_research import build_research_result
    from hsconfig.package_request import FrozenJsonDocument

    value = context.document.to_value()
    record = {
        "source_url": "https://example.org/guide",
        "evidence_id": "quality-page",
        "content_sha256": "a" * 64,
        "retrieved_at": "2026-09-09T00:00:00Z",
        "normalized_text": value["card_metadata"]["TOY_518"]["name"]
        + " should be kept early.",
        "conflicts": ["opening advice differs"],
    }
    result = build_research_result(
        acquired={"source_records": [record]},
        discovery_outcome="completed",
        attempts=[
            {
                "url": record["source_url"],
                "state": "completed",
                "error": None,
                "record_sha256": "sha256:"
                + sha256(
                    FrozenJsonDocument.from_value(record).canonical_json
                ).hexdigest(),
            }
        ],
        deadline_utc=100.0,
        card_metadata=value["card_metadata"],
    )
    value["research_evidence"] = result.to_value()
    return reseal_context(value)


def test_changed_keys_ignore_numeric_spelling():
    # Break caught: textual rather than numeric drift creates invented overrides.
    from hsconfig.starter_candidate import changed_globalvalue_keys

    baseline = {
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0.5"}]}
    }
    desired = deepcopy(baseline)
    desired["FirstTurnValueWeight"]["values"][0]["value"] = "0.50"
    assert changed_globalvalue_keys(baseline, desired) == ()
    desired["FirstTurnValueWeight"]["values"][0]["value"] = "0.75"
    assert changed_globalvalue_keys(baseline, desired) == ("FirstTurnValueWeight",)


def test_changed_keys_ignore_condition_order_but_require_matching_keys():
    from hsconfig.starter_candidate import changed_globalvalue_keys

    baseline = {
        "FirstTurnValueWeight": {
            "values": [
                {"condition": "*", "value": "0.5"},
                {"condition": "HasCoin", "value": "0.7"},
            ]
        }
    }
    desired = deepcopy(baseline)
    desired["FirstTurnValueWeight"]["values"].reverse()
    assert changed_globalvalue_keys(baseline, desired) == ()
    with pytest.raises(ValueError, match="starter_candidate_globalvalues_keys_invalid"):
        changed_globalvalue_keys(baseline, {})


def test_quality_candidate_accepts_only_justified_mulligan(
    quality_shadowpriest_context,
):
    context = quality_shadowpriest_context
    draft = quality_draft(context, mulligan_only=True)
    candidate = validate_starter_candidate(
        seal_quality_candidate(draft), context=context
    )
    assert candidate.candidate_id == "lead"
    assert len(candidate.mulligan_plan.rules) == 1
    assert candidate.card_behavior_rows == ()
    assert candidate.globalvalues.to_value() == draft["globalvalues"]
    draft["mulligan"] = []
    with pytest.raises(ValueError, match="starter_candidate_mulligan_required"):
        validate_starter_candidate(seal_quality_candidate(draft), context=context)


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "extra",
        "blank_decision",
        "blank_gap",
        "unknown_ref",
        "pseudo_rule_ref",
        "undeclared_inference",
        "evidence_without_refs",
        "evidence_with_assumption",
        "extra_field",
        "duplicate_refs",
    ],
)
def test_quality_justifications_fail_closed(quality_shadowpriest_context, defect):
    context = quality_shadowpriest_context
    draft = quality_draft(context)
    row = draft["globalvalues_justifications"]["FirstTurnValueWeight"]
    if defect == "missing":
        draft["globalvalues_justifications"] = {}
    elif defect == "extra":
        draft["globalvalues_justifications"]["SecondTurnValueWeight"] = deepcopy(row)
    elif defect == "blank_decision":
        row["decision"] = " "
    elif defect == "blank_gap":
        row["baseline_gap"] = ""
    elif defect in {"unknown_ref", "pseudo_rule_ref"}:
        row["evidence_refs"] = [
            "keep-toy-518" if defect == "pseudo_rule_ref" else "unknown-evidence"
        ]
    elif defect == "duplicate_refs":
        row["evidence_refs"] = [
            context.document.to_value()["existing_claims"][0]["claim_id"]
        ] * 2
    elif defect == "undeclared_inference":
        draft["assumptions"].remove(row["assumption"])
    elif defect == "extra_field":
        row["rule_id"] = "keep-toy-518"
    else:
        row["basis"] = "evidence"
        if defect == "evidence_without_refs":
            row["assumption"] = None
        else:
            row["evidence_refs"] = [
                context.document.to_value()["existing_claims"][0]["claim_id"]
            ]
    with pytest.raises(
        ValueError, match="starter_candidate_globalvalues_justifications_invalid"
    ):
        validate_starter_candidate(seal_quality_candidate(draft), context=context)


def test_quality_evidence_accepts_sealed_claim_id(quality_shadowpriest_context):
    context = quality_shadowpriest_context
    claim_id = context.document.to_value()["existing_claims"][0]["claim_id"]
    draft = quality_draft(context)
    row = draft["globalvalues_justifications"]["FirstTurnValueWeight"]
    row.update(basis="evidence", evidence_refs=[claim_id], assumption=None)
    candidate = validate_starter_candidate(
        seal_quality_candidate(draft), context=context
    )
    assert candidate.document.to_value()["globalvalues_justifications"][
        "FirstTurnValueWeight"
    ]["evidence_refs"] == [claim_id]


def test_quality_condition_order_does_not_change_intent_digest(
    quality_shadowpriest_context,
):
    context = quality_shadowpriest_context
    draft = quality_draft(context)
    draft["globalvalues"]["FirstTurnValueWeight"]["values"].append(
        {"condition": "coin", "value": "0.5"}
    )
    first = validate_starter_candidate(seal_quality_candidate(draft), context=context)
    draft["globalvalues"]["FirstTurnValueWeight"]["values"].reverse()
    second = validate_starter_candidate(seal_quality_candidate(draft), context=context)
    assert first.document.content_sha256 != second.document.content_sha256
    assert first.runtime_intent_sha256 == second.runtime_intent_sha256


def test_quality_transform_requires_resolved_corresponding_facts(
    quality_shadowpriest_context,
):
    # Pure validator coverage, not end-to-end captured-input authority.
    from hsconfig.card_snapshot import build_card_snapshot
    from hsconfig.starter_card_facts import project_card_facts
    from hsconfig.starter_context import (
        _deck_shape,
        _known_safety_boundaries,
        quality_main_card_rows,
    )

    value = quality_shadowpriest_context.document.to_value()
    records = [
        {
            **{key: item for key, item in metadata.items() if item is not None},
            "id": card_id,
        }
        for card_id, metadata in value["card_metadata"].items()
    ]
    records.append(
        {
            "id": "EX1_625t",
            "dbfId": 1623,
            "name": "Mind Spike",
            "type": "HERO_POWER",
            "cost": 2,
            "text": "Deal 2 damage.",
        }
    )
    snapshot = build_card_snapshot(records, captured_at="2026-09-09T00:00:00Z")
    value.update(
        project_card_facts(
            {"cards": value["cards"], "sideboards": []},
            snapshot.to_value()["full_cards"],
        )
    )
    main_rows = quality_main_card_rows(value)
    value["deck_shape"] = _deck_shape(main_rows)
    value["known_safety_boundaries"] = _known_safety_boundaries(main_rows)
    context = reseal_context(value)
    draft = quality_draft(context)
    draft["card_rules"][0].update(
        runtime_card_id="EX1_625t",
        link_kind="hero_power_transform",
        behavior_block="BeforeUseHeroPowerBonus",
    )
    candidate = validate_starter_candidate(
        seal_quality_candidate(draft), context=context
    )
    assert candidate.card_behavior_rows[0].to_value()["runtime_card_id"] == "EX1_625t"
    draft["card_rules"][0]["runtime_card_id"] = "SW_448"
    with pytest.raises(
        ValueError, match="starter_candidate_runtime_owner_unauthorized"
    ):
        validate_starter_candidate(seal_quality_candidate(draft), context=context)


@pytest.mark.parametrize(
    "action, error",
    [
        ("hold", "starter_candidate_mulligan_duplicate"),
        ("discard", "starter_candidate_mulligan_conflict"),
    ],
)
def test_quality_rejects_duplicate_or_conflicting_mulligan(
    quality_shadowpriest_context, action, error
):
    context = quality_shadowpriest_context
    draft = quality_draft(context, mulligan_only=True)
    draft["mulligan"].append(
        {**draft["mulligan"][0], "rule_id": "other", "action": action}
    )
    with pytest.raises(ValueError, match=error):
        validate_starter_candidate(seal_quality_candidate(draft), context=context)


def test_quality_sideboard_metadata_does_not_become_main_owner(
    quality_shadowpriest_context,
):
    value = quality_shadowpriest_context.document.to_value()
    value["card_metadata"]["SIDE_001"] = {
        **deepcopy(value["card_metadata"]["TOY_518"]),
        "dbf_id": 999999,
    }
    value["sideboards"] = [
        {"owner_card_id": "SW_448", "index": 1, "card_id": "SIDE_001", "count": 1}
    ]
    context = reseal_context(value)
    draft = quality_draft(context)
    draft["card_rules"][0].update(
        source_card_id="SIDE_001", runtime_card_id="SIDE_001", link_kind="self"
    )
    with pytest.raises(ValueError, match="starter_candidate_card_id_unknown"):
        validate_starter_candidate(seal_quality_candidate(draft), context=context)


def test_quality_revalidates_context_and_closes_lead_identity(
    quality_shadowpriest_context,
):
    context = quality_shadowpriest_context
    document = seal_quality_candidate(quality_draft(context))
    with pytest.raises(ValueError, match="starter_candidate_context_invalid"):
        validate_starter_candidate(
            document, context=replace(context, deck_fingerprint="0" * 64)
        )
    draft = quality_draft(context)
    draft["candidate_id"] = "candidate-1"
    with pytest.raises(ValueError, match="starter_candidate_id_invalid"):
        validate_starter_candidate(seal_quality_candidate(draft), context=context)


def test_quality_does_not_change_legacy_numeric_intent_projection():
    # Literal historic projection remains row-order-sensitive for schema 2.
    from hsconfig.starter_candidate import _globalvalues_semantic_projection

    assert _globalvalues_semantic_projection(
        {
            "FirstTurnValueWeight": {
                "values": [
                    {"condition": "HasCoin", "value": "0.75"},
                    {"condition": "*", "value": "0.50"},
                ]
            }
        }
    ) == {
        "FirstTurnValueWeight": {
            "values": [
                {"condition": "HasCoin", "value": "0x1.8000000000000p-1"},
                {"condition": "*", "value": "0x1.0000000000000p-1"},
            ]
        }
    }
