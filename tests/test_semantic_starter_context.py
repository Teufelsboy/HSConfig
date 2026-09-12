"""Schema4 policy tests; fixture validity is not live gameplay evidence."""

from copy import deepcopy
from dataclasses import replace

import pytest

from hsconfig.starter_context import validate_starter_context_document
from hsconfig.starter_contract import SEMANTIC_STARTER_CONTEXT_FIELDS
from hsconfig.starter_document import seal_starter_document


PHASES = (
    "Mulligan", "GlobalValues", "Combo", "BeforeUseHeroPowerBonus",
    "BeforePhysicalAttackBonus", "BeforeOverkilledBonus", "OnBoardBonus",
    "BeforeBattlecryTargetBonus", "OnDiscoverCardBonus", "OnChooseOneCardBonus",
    "OnAdaptCardBonus", "InHandBonus", "BeforePlayCardBonus", "BeforeEndTurnBonus",
    "InHandPlayPriority", "OnBoardPlayPriority", "BeforeUpgradeCardBonus",
)


@pytest.mark.parametrize("phase", ["Mulligan", "BeforePlayCardBonus", "Combo", "GlobalValues"])
@pytest.mark.parametrize("condition", [
    None, "", " ", {}, {"runtime_condition": "*"}, {"hand_contains_any": ["A"]},
    [], False, " *", "* ", "\t*", "coin  AND nocoin", "coin\tAND nocoin",
])
def test_semantic_condition_is_never_coerced(phase, condition):
    from hsconfig.starter_semantics import validate_semantic_condition

    with pytest.raises(ValueError, match="^starter_candidate_condition_invalid$"):
        validate_semantic_condition(condition, phase=phase)


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("condition", [
    "*", "my_hand(count()) == 3", "opp_hero(count(),mage=true) > 0",
    "my_hand(count()) == 3 AND opp_hero(count(),mage=true) > 0",
    "my_hand(count()) == 3 OR opp_hero(count(),mage=true) > 0",
])
def test_semantic_common_conditions_admitted(phase, condition):
    from hsconfig.starter_semantics import validate_semantic_condition

    assert validate_semantic_condition(condition, phase=phase) == condition


@pytest.mark.parametrize(("phase", "condition", "error"), [
    ("Mulligan", "coin AND nocoin", "contradiction"),
    ("Mulligan", "coin AND my_hand(count()) == 3 OR nocoin", "mixed_logic"),
    ("InHandBonus", "my_target(count(),hero=true) > 0", "context_invalid"),
    ("InHandBonus", "my_discover(count(),cardid=TEST_001) > 0", "context_invalid"),
    ("Combo", "coin", "context_invalid"),
    ("GlobalValues", "nocoin", "context_invalid"),
    ("OnAdaptCardBonus", "my_discover(count(),cardid=TEST_001) > 0", "context_invalid"),
    ("BeforePlayCardBonus", "my_minion(count(),cardid=TEST_001) > 0", "context_invalid"),
    ("BeforePlayCardBonus", "my_minions(count(),cardid=TEST_001) > 0", "invalid"),
    ("OnChooseOneCardBonus", "my_choice(count(),cardid=TEST_001) > 0", "invalid"),
])
def test_semantic_condition_phase_rejections(phase, condition, error):
    from hsconfig.starter_semantics import validate_semantic_condition

    with pytest.raises(ValueError, match=f"^starter_candidate_condition_{error}$"):
        validate_semantic_condition(condition, phase=phase)


@pytest.mark.parametrize(("phase", "condition"), [
    ("Mulligan", "coin"), ("Mulligan", "nocoin"), ("Mulligan", "coin OR nocoin"),
    ("BeforePhysicalAttackBonus", "my_target(count(),hero=true) > 0"),
    ("BeforeBattlecryTargetBonus", "my_target(count(),hero=true) > 0"),
    ("OnDiscoverCardBonus", "my_discover(count(),cardid=TEST_001) > 0"),
])
def test_semantic_phase_specific_positives(phase, condition):
    from hsconfig.starter_semantics import validate_semantic_condition

    assert validate_semantic_condition(condition, phase=phase) == condition


@pytest.mark.parametrize("phase", [None, False, {}, "", "mulligan", "FutureBonus"])
def test_semantic_unknown_phase_rejected(phase):
    from hsconfig.starter_semantics import validate_semantic_condition

    with pytest.raises(ValueError, match="^starter_candidate_condition_phase_invalid$"):
        validate_semantic_condition("*", phase=phase)


def owner_row(block, source="TEST_001", runtime=None, link="self"):
    return {"source_card_id": source, "runtime_card_id": runtime or source,
            "link_kind": link, "behavior_block": block}


@pytest.mark.parametrize(("block", "source", "admitted"), [
    ("BeforeUseHeroPowerBonus", {"type": "MINION"}, False),
    ("BeforeUseHeroPowerBonus", {"type": "HERO_POWER"}, True),
    ("BeforePhysicalAttackBonus", {"type": "HERO"}, True),
    ("BeforePhysicalAttackBonus", {"type": "MINION"}, True),
    ("BeforePhysicalAttackBonus", {"type": "WEAPON"}, False),
    ("BeforeOverkilledBonus", {"type": "MINION", "mechanics": []}, True),
    ("BeforeOverkilledBonus", {"type": "HERO"}, False),
    ("OnBoardBonus", {"type": "LOCATION"}, False),
    ("OnBoardBonus", {"type": "WEAPON"}, True),
    ("OnBoardBonus", {"type": "HERO_POWER"}, True),
    ("OnBoardBonus", {"type": "HERO"}, True),
    ("OnBoardBonus", {"type": "MINION"}, True),
    ("OnBoardBonus", {"type": None}, False),
    ("BeforeBattlecryTargetBonus", {"mechanics": ["BATTLECRY"], "playRequirements": {"REQ_TARGET_TO_PLAY": 0}}, True),
    ("BeforeBattlecryTargetBonus", {"mechanics": ["BATTLECRY"], "playRequirements": {"REQ_TARGET_IF_AVAILABLE": 0}}, False),
    ("BeforeBattlecryTargetBonus", {"mechanics": ["BATTLECRY"], "playRequirements": {"11": 0}}, False),
    ("BeforeBattlecryTargetBonus", {"mechanics": [], "playRequirements": {"REQ_TARGET_TO_PLAY": 0}}, False),
    ("BeforeBattlecryTargetBonus", {"mechanics": ["BATTLECRY"]}, False),
    ("OnDiscoverCardBonus", {"mechanics": ["DISCOVER"]}, True),
    ("OnDiscoverCardBonus", {"text": "Discover a card."}, False),
    ("OnChooseOneCardBonus", {"mechanics": ["CHOOSE_ONE"], "type": "SPELL"}, True),
    ("OnChooseOneCardBonus", {"mechanics": ["CHOOSE_ONE"], "type": "MINION"}, True),
    ("OnChooseOneCardBonus", {}, False),
    ("OnChooseOneCardBonus", {"mechanics": None}, False),
    ("OnChooseOneCardBonus", {"mechanics": []}, False),
    ("OnChooseOneCardBonus", {"mechanics": ["choose_one"]}, False),
    ("OnChooseOneCardBonus", {"text": "Choose One - Draw a card."}, False),
    ("OnChooseOneCardBonus", {"referencedTags": ["CHOOSE_ONE"]}, False),
    ("OnAdaptCardBonus", {"mechanics": []}, True),
    ("BeforeUpgradeCardBonus", {"type": "LOCATION"}, True),
])
def test_normalized_owner_surface_matrix(block, source, admitted):
    from hsconfig.starter_semantics import validate_semantic_owner
    from tests.helpers.semantic_start import normalized_owner_context

    context = normalized_owner_context(source)
    if admitted:
        assert validate_semantic_owner(context, owner_row(block)) is None
    else:
        with pytest.raises(ValueError, match="^starter_candidate_surface_owner_unproven$"):
            validate_semantic_owner(context, owner_row(block))


@pytest.mark.parametrize("number", [True, "0", 1.5])
def test_malformed_target_fact_is_not_capability(number):
    from hsconfig.starter_semantics import validate_semantic_owner
    from tests.helpers.semantic_start import normalized_owner_context

    context = normalized_owner_context({"mechanics": ["BATTLECRY"], "playRequirements": {"REQ_TARGET_TO_PLAY": 0}})
    context["card_metadata"]["TEST_001"]["play_requirements"]["REQ_TARGET_TO_PLAY"] = number
    with pytest.raises(ValueError, match="^starter_card_facts_requirements_invalid$"):
        validate_semantic_owner(context, owner_row("BeforeBattlecryTargetBonus"))


def test_sideboard_choose_one_does_not_become_physical_owner():
    from hsconfig.starter_semantics import validate_semantic_owner
    from tests.helpers.semantic_start import normalized_owner_context

    context = normalized_owner_context({"mechanics": ["CHOOSE_ONE"]}, sideboard=True)
    with pytest.raises(ValueError, match="^starter_candidate_card_id_unknown$"):
        validate_semantic_owner(context, owner_row("OnChooseOneCardBonus"))


def test_linked_option_metadata_does_not_authorize_choose_one():
    from hsconfig.starter_semantics import validate_semantic_owner
    from tests.helpers.semantic_start import normalized_owner_context

    context = normalized_owner_context(
        {"mechanics": ["CHOOSE_ONE"], "entourage": ["TEST_003"]},
        linked={"id": "TEST_003", "dbfId": 3, "name": "Option", "type": "SPELL", "mechanics": ["CHOOSE_ONE"]},
    )
    with pytest.raises(ValueError, match="^starter_candidate_runtime_owner_unauthorized$"):
        validate_semantic_owner(context, owner_row("OnChooseOneCardBonus", runtime="TEST_003", link="entourage"))


def test_semantic_policy_copies_cannot_mutate_phase_admission():
    from hsconfig.starter_semantics import semantic_runtime_policy, validate_semantic_condition

    policy = semantic_runtime_policy()
    policy["condition_atom_families_by_phase"]["Combo"].append("target")
    with pytest.raises(ValueError, match="^starter_candidate_condition_context_invalid$"):
        validate_semantic_condition("my_target(count(),hero=true) > 0", phase="Combo")
    assert "target" not in semantic_runtime_policy()["condition_atom_families_by_phase"]["Combo"]


def test_semantic_builder_requires_real_new_route(tmp_path, monkeypatch):
    from hsconfig.starter_context import build_semantic_starter_context
    from tests.helpers.semantic_start import semantic_frozen_inputs

    frozen = semantic_frozen_inputs(tmp_path, monkeypatch)
    context = build_semantic_starter_context(frozen)
    value = context.document.to_value()
    assert frozen.manifest.document.to_value()["schema_version"] == 3
    assert value["schema_version"] == 4
    assert value["temporal_provenance"] == {
        "snapshot_dataset_sha256": frozen.quality_inputs.to_value()["card_snapshot_sha256"],
        "snapshot_captured_at": "2026-09-09T00:00:00Z",
        "snapshot_upstream_version": None, "evaluation_date": "2026-09-09",
        "patch_compatibility": "unknown",
    }
    assert validate_starter_context_document(context.document) == context
    with pytest.raises(ValueError, match="^starter_context_inputs_invalid$"):
        build_semantic_starter_context(replace(frozen, quality_inputs=None))


def reseal_context(value):
    draft = deepcopy(value)
    draft.pop("content_sha256", None)
    return seal_starter_document(draft, expected_fields=SEMANTIC_STARTER_CONTEXT_FIELDS, schema_version=4)


@pytest.fixture(scope="module")
def frozen_semantic_context(tmp_path_factory):
    from hsconfig.starter_context import build_semantic_starter_context
    from tests.helpers.semantic_start import semantic_frozen_inputs

    root = tmp_path_factory.mktemp("semantic-source")
    with pytest.MonkeyPatch.context() as patch:
        frozen = semantic_frozen_inputs(
            root, patch, captured_at="  archived capture spelling  ",
            upstream_version=" offline build v9 ",
        )
        yield frozen, build_semantic_starter_context(frozen)


def test_frozen_capture_spelling_and_physical_roundtrip(frozen_semantic_context, tmp_path):
    from hsconfig.input_snapshot_manifest import load_frozen_compiler_inputs
    from hsconfig.starter_context import build_semantic_starter_context
    from tests.test_input_snapshot_manifest import _write_frozen_inputs

    frozen, context = frozen_semantic_context
    temporal = context.document.to_value()["temporal_provenance"]
    assert temporal["snapshot_captured_at"] == "  archived capture spelling  "
    assert temporal["snapshot_upstream_version"] == " offline build v9 "
    assert temporal["evaluation_date"] == "2026-09-09"
    root = tmp_path / "run"
    _write_frozen_inputs(root, frozen)
    (root / "inputs" / "quality.json").write_bytes(frozen.quality_inputs.canonical_json)
    loaded = load_frozen_compiler_inputs(root)
    assert loaded == frozen
    assert build_semantic_starter_context(loaded).document.canonical_json == context.document.canonical_json


@pytest.mark.parametrize(("field", "replacement"), [
    ("snapshot_dataset_sha256", "a" * 64),
    ("snapshot_dataset_sha256", "sha256:" + "A" * 64),
    ("snapshot_dataset_sha256", False),
    ("snapshot_captured_at", None), ("snapshot_captured_at", " "),
    ("snapshot_upstream_version", False), ("snapshot_upstream_version", ""),
    ("evaluation_date", "2026-9-09"), ("evaluation_date", "2026-02-30"),
    ("evaluation_date", "2026-09-09T00:00:00Z"), ("evaluation_date", True),
    ("patch_compatibility", "compatible"), ("patch_compatibility", None),
])
def test_frozen_temporal_closed_validation(frozen_semantic_context, field, replacement):
    value = frozen_semantic_context[1].document.to_value()
    value["temporal_provenance"][field] = replacement
    with pytest.raises(ValueError, match="^starter_context_document_invalid$"):
        validate_starter_context_document(reseal_context(value))


@pytest.mark.parametrize("change", ["missing", "extra", "not_mapping"])
def test_frozen_temporal_exact_shape(frozen_semantic_context, change):
    value = frozen_semantic_context[1].document.to_value()
    if change == "missing":
        del value["temporal_provenance"]["evaluation_date"]
    elif change == "extra":
        value["temporal_provenance"]["current_patch"] = "claimed"
    else:
        value["temporal_provenance"] = []
    with pytest.raises(ValueError, match="^starter_context_document_invalid$"):
        validate_starter_context_document(reseal_context(value))


def test_frozen_false_provenance_is_not_source_binding(frozen_semantic_context):
    from hsconfig.starter_context import build_semantic_starter_context

    frozen, context = frozen_semantic_context
    value = context.document.to_value()
    value["temporal_provenance"]["snapshot_dataset_sha256"] = "sha256:" + "0" * 64
    forged = validate_starter_context_document(reseal_context(value))
    # Shape-valid self-declaration does not equal reconstruction from actual inputs.
    assert forged.document.canonical_json != build_semantic_starter_context(frozen).document.canonical_json
    assert forged.document.to_value()["temporal_provenance"] != context.document.to_value()["temporal_provenance"]


def test_frozen_policy_tampering_rejected(frozen_semantic_context):
    value = frozen_semantic_context[1].document.to_value()
    policy = value["supported_runtime_contract"]["semantic_policy"]
    policy["condition_atom_families_by_phase"]["Combo"].append("target")
    with pytest.raises(ValueError, match="^starter_context_document_invalid$"):
        validate_starter_context_document(reseal_context(value))


def test_frozen_registry_source_gaps_preserved(frozen_semantic_context):
    contract = frozen_semantic_context[1].document.to_value()["supported_runtime_contract"]
    backing = contract["semantic_policy"]["behavior_block_source_backing"]
    assert backing["OnAdaptCardBonus"] == "repo_supported_source_gap"
    assert backing["OnBoardPlayPriority"] == "repo_supported_source_gap"
    assert backing["BeforeUpgradeCardBonus"] == "repo_supported_source_gap"
    assert backing["OnChooseOneCardBonus"] == "public_doc_confirmed"


def test_frozen_semantic_descriptor_requires_registered_identity(frozen_semantic_context, monkeypatch):
    from hsconfig import starter_context
    from hsconfig.starter_contract import SEMANTIC_LIVE_CONTRACT

    monkeypatch.setattr(starter_context, "SEMANTIC_LIVE_CONTRACT", replace(SEMANTIC_LIVE_CONTRACT))
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        starter_context.build_semantic_starter_context(frozen_semantic_context[0])


def test_frozen_quality_route_not_relabelled(tmp_path, monkeypatch):
    from hsconfig.starter_context import build_semantic_starter_context, build_quality_starter_context
    from tests.helpers.semantic_start import semantic_frozen_inputs

    old = semantic_frozen_inputs(tmp_path, monkeypatch, compiler_contract_id="hsconfig-live-start-v2")
    assert build_quality_starter_context(old).document.to_value()["schema_version"] == 3
    with pytest.raises(ValueError, match="^starter_context_semantic_inputs_required$"):
        build_semantic_starter_context(old)


def test_frozen_explicit_capabilities_and_authorized_transform(tmp_path, monkeypatch):
    from hsconfig.starter_context import build_semantic_starter_context
    from hsconfig.starter_semantics import validate_semantic_owner
    from tests.helpers.semantic_start import semantic_frozen_inputs

    selected = []

    def source_rows(rows, main_ids):
        target_id = sorted(main_ids - {"SW_448"})[0]
        selected.append(target_id)
        result = []
        for raw in rows:
            if raw["id"] == target_id:
                raw = {**raw, "type": "MINION", "mechanics": ["BATTLECRY", "CHOOSE_ONE", "DISCOVER"],
                       "playRequirements": {"REQ_TARGET_TO_PLAY": 0}}
            if raw["id"] == "EX1_625t":
                raw = {**raw, "type": "HERO_POWER"}
            result.append(raw)
        if not any(row["id"] == "EX1_625t" for row in result):
            result.append({"id": "EX1_625t", "dbfId": 999001, "name": "Mind Spike",
                           "type": "HERO_POWER", "cost": 2, "collectible": False})
        return result

    frozen = semantic_frozen_inputs(tmp_path, monkeypatch, transform_rows=source_rows)
    context = build_semantic_starter_context(frozen).document.to_value()
    card_id = selected[0]
    assert context["card_metadata"][card_id]["play_requirements"] == {"REQ_TARGET_TO_PLAY": 0}
    for block in ("BeforeBattlecryTargetBonus", "OnChooseOneCardBonus", "OnDiscoverCardBonus"):
        assert validate_semantic_owner(context, owner_row(block, source=card_id)) is None
    assert validate_semantic_owner(context, owner_row(
        "BeforeUseHeroPowerBonus", source="SW_448", runtime="EX1_625t", link="hero_power_transform"
    )) is None
    with pytest.raises(ValueError, match="^starter_candidate_runtime_owner_unauthorized$"):
        validate_semantic_owner(context, owner_row("BeforeUseHeroPowerBonus", source="SW_448"))
    with pytest.raises(ValueError, match="^starter_candidate_runtime_owner_unauthorized$"):
        validate_semantic_owner(context, owner_row(
            "BeforeUseHeroPowerBonus", source=card_id, runtime="EX1_625t", link="hero_power_transform"
        ))
