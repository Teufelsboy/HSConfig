"""New admission closes semantic gaps without reinterpreting stored authority."""

import pytest

from hsconfig import live_start_controller as controller
from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.condition_format import classify_runtime_condition
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_context import validate_starter_context_document
from hsconfig.starter_review import build_candidate_review_facts
from tests.helpers.starter_historical import load_historical_document
from tests.test_quality_starter_candidate import (
    quality_draft,
    reseal_context,
    seal_quality_candidate,
)
from tests.test_quality_live_start_controller import quality_request as quality_request


@pytest.fixture
def quality_context():
    # Frozen real schema-3 fixture; no profile, network or runtime acquisition.
    return validate_starter_context_document(
        load_historical_document(3, "starter_context")
    )


def _finding(context, draft, tmp_path, monkeypatch):
    """Exercise actual file loading, full validation and controller admission."""
    starter = tmp_path / "starter"
    starter.mkdir(exist_ok=True)
    (starter / "starter_context.json").write_bytes(context.document.canonical_json)
    (starter / "starter_config_candidate.json").write_bytes(
        seal_quality_candidate(draft).canonical_json
    )
    # Only the expensive session/manifest lookup is outside this unit boundary.
    # Real-session tests below cover the receipt and revision authority boundary.
    monkeypatch.setattr(controller, "_persisted_live_document_version", lambda _: 3)
    return controller._candidate_validation_finding(session_root=tmp_path)


def _mulligan_pair(draft, first, second):
    draft["mulligan"][0]["condition"] = first
    draft["mulligan"].append({
        **draft["mulligan"][0], "rule_id": "other-matchup",
        "condition": second, "action": "discard",
    })
    draft["rule_rationales"]["other-matchup"] = "Different opposing class."
    next(row for row in draft["card_dispositions"] if row["card_id"] == "TOY_518")[
        "rule_ids"
    ].append("other-matchup")


@pytest.mark.parametrize("condition", [
    "coin AND nocoin",
    "opp_hero(count(),mage=true) > 0 AND opp_hero(count(),warrior=true) > 0",
    "my_hand(count()) == 3 AND my_hand(count()) == 4",
])
def test_unreachable_only_mulligan_cannot_earn_new_receipt(
    quality_context, tmp_path, monkeypatch, condition,
):
    # Break caught: syntactically accepted but impossible rows mint authority.
    draft = quality_draft(quality_context, mulligan_only=True)
    draft["mulligan"][0]["condition"] = condition
    candidate = validate_starter_candidate(seal_quality_candidate(draft), context=quality_context)
    assert classify_runtime_condition(condition).status == "runtime_safe"
    assert compile_mulligan(candidate.mulligan_plan)["Mulligan"]["values"][0]["condition"] == condition
    assert _finding(quality_context, draft, tmp_path, monkeypatch) == "starter_candidate_condition_impossible"


@pytest.mark.parametrize("first,second", [
    ("opp_hero(count(),mage=true) > 0", "opp_hero(count(),warrior=true) > 0"),
    ("coin AND opp_hero(count(), hero_class=mage | priest ) > 0",
     "coin AND opp_hero(count(), hero_class=warrior | shaman ) > 0"),
])
def test_disjoint_matchup_actions_are_admitted(quality_context, tmp_path, monkeypatch, first, second):
    # Break caught: an overly broad conflict check rejects disjoint classes.
    draft = quality_draft(quality_context, mulligan_only=True)
    _mulligan_pair(draft, first, second)
    assert _finding(quality_context, draft, tmp_path, monkeypatch) is None


@pytest.mark.parametrize("first,second", [
    ("opp_hero(count(), hero_class=mage | priest ) > 0",
     "opp_hero(count(), hero_class=priest | warrior ) > 0"),
    ("my_hand(count(),cardid=TOY_518) > 0", "my_hand(count(),cardid=SW_448) > 0"),
    ("coin OR opp_hero(count(),mage=true) > 0", "nocoin"),
])
def test_potentially_overlapping_mulligan_actions_still_conflict(
    quality_context, tmp_path, monkeypatch, first, second,
):
    # Break caught: unsupported reasoning assumes independent hand states disjoint.
    draft = quality_draft(quality_context, mulligan_only=True)
    _mulligan_pair(draft, first, second)
    assert _finding(quality_context, draft, tmp_path, monkeypatch) == "starter_candidate_mulligan_conflict"


def test_mixed_boolean_precedence_requires_revision(quality_context, tmp_path, monkeypatch):
    # Break caught: admission silently assumes an undocumented AND/OR precedence.
    draft = quality_draft(quality_context, mulligan_only=True)
    draft["mulligan"][0]["condition"] = "coin AND nocoin OR my_hand(count()) == 3"
    assert _finding(quality_context, draft, tmp_path, monkeypatch) == "starter_candidate_condition_precedence_ambiguous"


def test_wrong_card_type_remains_reconstructable_but_not_newly_admitted(
    quality_context, tmp_path, monkeypatch,
):
    # Break caught: a minion's hero-power block earns a normal validation receipt.
    draft = quality_draft(quality_context)
    draft["card_rules"][0].update(
        source_card_id="TOY_518", runtime_card_id="TOY_518",
        behavior_block="BeforeUseHeroPowerBonus",
    )
    for row in draft["card_dispositions"]:
        if row["card_id"] == "SW_448":
            row.update(disposition="deliberately_unconfigured", rule_ids=[])
        if row["card_id"] == "TOY_518":
            row["rule_ids"].append("darkbishop-play")
    candidate = validate_starter_candidate(seal_quality_candidate(draft), context=quality_context)
    facts = build_candidate_review_facts(context=quality_context, candidate=candidate)
    assert facts.to_value()["runtime_authorized"] is False
    assert _finding(quality_context, draft, tmp_path, monkeypatch) == "starter_candidate_card_surface_type_invalid"


def _card_pair(draft, first="coin", second="*", second_value="12"):
    original = draft["card_rules"][0]
    original.update(condition=second, value=second_value)
    draft["card_rules"].insert(0, {
        **original, "rule_id": "specific-play", "condition": first, "value": "-12",
    })
    draft["rule_rationales"]["specific-play"] = "Specific conditional override."
    next(row for row in draft["card_dispositions"] if row["card_id"] == "SW_448")[
        "rule_ids"
    ].append("specific-play")


def test_cardid_priority_reversal_is_reported_not_silently_fixed(quality_context, tmp_path, monkeypatch):
    # Break caught: authored specific-before-default becomes default-before-specific.
    draft = quality_draft(quality_context)
    _card_pair(draft)
    candidate = validate_starter_candidate(seal_quality_candidate(draft), context=quality_context)
    runtime = compile_cardid_behaviors(rows=[row.to_value() for row in candidate.card_behavior_rows])
    assert [row["condition"] for row in runtime["SW_448.json"]["BeforePlayCardBonus"]["values"]] == ["*", "coin"]
    assert _finding(quality_context, draft, tmp_path, monkeypatch) == "starter_candidate_card_order_ambiguous"


@pytest.mark.parametrize("first,second,value", [
    ("nocoin", "coin", "12"),
    ("coin", "*", "-12.0"),
])
def test_harmless_cardid_reordering_remains_admitted(quality_context, tmp_path, monkeypatch, first, second, value):
    draft = quality_draft(quality_context)
    _card_pair(draft, first, second, value)
    assert _finding(quality_context, draft, tmp_path, monkeypatch) is None


def test_same_action_mulligan_reordering_is_harmless(quality_context, tmp_path, monkeypatch):
    draft = quality_draft(quality_context, mulligan_only=True)
    _mulligan_pair(draft, "coin", "*")
    draft["mulligan"][1]["action"] = "hold"
    assert _finding(quality_context, draft, tmp_path, monkeypatch) is None


@pytest.mark.parametrize("reverse", [False, True])
def test_overlapping_globalvalue_permutations_cannot_hide_behind_old_intent(
    quality_context, tmp_path, monkeypatch, reverse,
):
    # Break caught: neither permutation equals baseline, yet both share old intent.
    draft = quality_draft(quality_context)
    rows = [{"condition": "coin", "value": "0.5"}, {"condition": "*", "value": "0.75"}]
    draft["globalvalues"]["FirstTurnValueWeight"]["values"] = rows[::-1] if reverse else rows
    assert _finding(quality_context, draft, tmp_path, monkeypatch) == "starter_candidate_globalvalue_order_ambiguous"


@pytest.mark.parametrize("rows", [
    [{"condition": "coin", "value": "0.5"}, {"condition": "nocoin", "value": "0.75"}],
    [{"condition": "coin", "value": "0.5"}, {"condition": "*", "value": "0.50"}],
])
def test_order_insensitive_globalvalue_rows_are_admitted(quality_context, tmp_path, monkeypatch, rows):
    draft = quality_draft(quality_context)
    draft["globalvalues"]["FirstTurnValueWeight"]["values"] = rows
    assert _finding(quality_context, draft, tmp_path, monkeypatch) is None


def test_globalvalue_baseline_order_only_change_requires_revision(quality_context, tmp_path, monkeypatch):
    from hsconfig.globalvalues_decisions import canonical_globalvalues_baseline_sha256

    value = quality_context.document.to_value()
    baseline = value["globalvalues_baseline"]["values"]
    baseline["FirstTurnValueWeight"]["values"] = [
        {"condition": "coin", "value": "0.5"}, {"condition": "*", "value": "0.75"},
    ]
    value["globalvalues_baseline"]["content_sha256"] = canonical_globalvalues_baseline_sha256(baseline)
    context = reseal_context(value)
    draft = quality_draft(context, mulligan_only=True)
    draft["globalvalues"]["FirstTurnValueWeight"]["values"].reverse()
    assert _finding(context, draft, tmp_path, monkeypatch) == "starter_candidate_globalvalue_order_ambiguous"


def test_disjoint_class_extension_does_not_change_historical_projection(quality_context):
    from tests.helpers.starter_historical import capture_historical_mutations, load_historical_json

    # Break caught: accepted old schema-3 values, facts or digest are reinterpreted.
    assert capture_historical_mutations(quality_context, schema=3) == load_historical_json(3, "mutations")


def _prepare_quality_candidate(quality_request, tmp_path):
    from hsconfig.input_snapshot_manifest import load_frozen_compiler_inputs
    from hsconfig.starter_context import build_quality_starter_context
    from tests.test_quality_live_start_controller import _empty_draft

    discovery = controller.prepare_quality_live_start(quality_request)
    prepared = controller.complete_live_start_research(
        session_root=discovery.run_root, draft_path=_empty_draft(tmp_path, discovery),
    )
    return prepared, build_quality_starter_context(load_frozen_compiler_inputs(prepared.run_root))


def _write_draft(tmp_path, draft):
    from hsconfig.package_request import FrozenJsonDocument

    path = tmp_path / "candidate-draft.json"
    path.write_bytes(FrozenJsonDocument.from_value(draft).canonical_json)
    return path


def test_new_admission_failure_repeats_without_receipt_or_extra_revision_charge(quality_request, tmp_path):
    from hsconfig.live_start_session import load_live_start_session

    # Break caught: intake mints a receipt before new checks, or resume bypasses them.
    prepared, context = _prepare_quality_candidate(quality_request, tmp_path)
    draft = quality_draft(context, mulligan_only=True)
    draft["mulligan"][0]["condition"] = "coin AND nocoin"
    first = controller.validate_live_start_candidate(
        session_root=prepared.run_root, draft_path=_write_draft(tmp_path, draft),
    )
    assert first.to_value()["status"] == "revision_required"
    assert first.to_value()["findings"] == ["starter_candidate_condition_impossible"]
    rejected = load_live_start_session(prepared.run_root)
    assert rejected.revisions_used == 1
    assert "receipts/candidate_validation.json" not in rejected.artifact_bindings
    resumed = controller.resume_live_start(session_root=prepared.run_root)
    assert resumed.canonical_json == first.canonical_json
    assert load_live_start_session(prepared.run_root).canonical_json == rejected.canonical_json
    draft["mulligan"][0]["condition"] = "coin"
    draft["candidate_revision"] = 2
    valid = controller.validate_live_start_candidate(
        session_root=prepared.run_root, draft_path=_write_draft(tmp_path, draft),
    )
    assert valid.to_value()["status"] == "valid"
    accepted = load_live_start_session(prepared.run_root)
    assert accepted.revisions_used == 1
    assert accepted.phase.value == "CANDIDATE_VALIDATED"
    assert accepted.apply_invocation_sha256 is None


def test_previously_charged_class_conflict_retains_diagnostic_without_granting_authority(
    quality_request, tmp_path, monkeypatch,
):
    import hsconfig.starter_candidate as candidates
    from hsconfig.live_start_session import load_live_start_session

    # Break caught: relaxing class overlap re-admits a charged historical rejection.
    prepared, context = _prepare_quality_candidate(quality_request, tmp_path)
    draft = quality_draft(context, mulligan_only=True)
    _mulligan_pair(draft, "opp_hero(count(),mage=true) > 0", "opp_hero(count(),warrior=true) > 0")
    # Reproduce the former predicate while real code stages and charges rejection.
    # This stub changes no session, receipt, file-loader or authority behavior.
    with monkeypatch.context() as historic:
        historic.setattr(candidates, "_mulligan_conditions_overlap", lambda _a, _b: True)
        first = controller.validate_live_start_candidate(
            session_root=prepared.run_root, draft_path=_write_draft(tmp_path, draft),
        )
    assert first.to_value()["findings"] == ["starter_candidate_mulligan_conflict"]
    before = load_live_start_session(prepared.run_root)
    resumed = controller.resume_live_start(session_root=prepared.run_root)
    assert resumed.canonical_json == first.canonical_json
    after = load_live_start_session(prepared.run_root)
    assert after.canonical_json == before.canonical_json
    assert after.revisions_used == 1
    assert "receipts/candidate_validation.json" not in after.artifact_bindings
