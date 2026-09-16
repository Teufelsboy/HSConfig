"""Pinned real rosters through QUALITY contracts, not current strategy evidence.

The small candidates deliberately exercise transmission of decisions, not whether
those decisions win games. Research is unavailable; no fixture approval authorizes
a live write. The audited snapshot lacks some rich fields, which must stay missing.
"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from hsconfig.globalvalues_decisions import GLOBALVALUES_BASELINE_DECISION_KEYS
from hsconfig.optimized_start_authority import ValidatedSingleStarterApproval
from hsconfig.package_compiler import compile_package
from hsconfig.package_request import FrozenApprovedLiveConfigureRequest
from hsconfig.quality_candidate_admission import validate_quality_candidate_admission
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_card_facts import project_card_facts
from hsconfig.starter_context import build_quality_starter_context
from hsconfig.starter_review import validate_starter_review
from tests.helpers.quality_start import quality_frozen_inputs
from tests.helpers.starter_historical import load_historical_document
from tests.test_audited_deck_set_acceptance import (
    AUDITED_CARD_DB_METADATA,
    AUDITED_CARD_DB_PATH,
    EXPECTED_AUDITED_DECK_CATALOG,
    _snapshot_sha256,
)
from tests.test_quality_starter_candidate import reseal_context, seal_quality_candidate
from tests.test_quality_starter_review import quality_receipt, quality_review


CLASSES = {
    "ShadowPriest": "PRIEST",
    "CtAPaladin": "PALADIN",
    "PirateRogue": "ROGUE",
    "BigShaman": "SHAMAN",
    "Discolock": "WARLOCK",
    "TreantDruid": "DRUID",
    "ImbueMage": "MAGE",
    "MechPala": "PALADIN",
    "Kingslayer": "ROGUE",
    "Boarlock": "WARLOCK",
    "PirateDH": "DEMONHUNTER",
}
REPRESENTATIVES = tuple(
    row
    for row in EXPECTED_AUDITED_DECK_CATALOG
    if row["matrix_role"] == "representative"
)


def _draft(context):
    value = context.document.to_value()
    # A real physical minion from each exact roster, not a fabricated semantic
    # card or a name-derived archetype. This is a compiler contract stimulus.
    card_id = next(
        row["card_id"]
        for row in value["cards"]
        if value["card_metadata"][row["card_id"]]["type"] == "MINION"
    )
    return {
        "schema_version": 3,
        "candidate_id": "lead",
        "candidate_revision": 1,
        "starter_context_sha256": context.document.content_sha256,
        "deck_fingerprint": context.deck_fingerprint,
        "strategy_summary": {
            "role": "lead_strategist",
            "summary": "Static compiler contract fixture, not a researched strategy.",
        },
        "mulligan": [
            {
                "rule_id": "opening",
                "selector_kind": "card",
                "selector": card_id,
                "action": "hold",
                "condition": "coin",
            }
        ],
        "globalvalues": deepcopy(value["globalvalues_baseline"]["values"]),
        "globalvalues_justifications": {},
        "card_rules": [
            {
                "rule_id": "physical-play",
                "source_card_id": card_id,
                "runtime_card_id": card_id,
                "link_kind": "self",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "1",
            }
        ],
        "combo": None,
        "card_dispositions": [
            {
                "card_id": row["card_id"],
                "disposition": "configured"
                if row["card_id"] == card_id
                else "deliberately_unconfigured",
                "rule_ids": ["opening", "physical-play"]
                if row["card_id"] == card_id
                else [],
                "reason": "Contract stimulus only; no extra strategy inferred from missing evidence.",
            }
            for row in value["cards"]
        ],
        "rule_rationales": {
            "opening": "Exercise coin-conditioned physical-card serialization only.",
            "physical-play": "Exercise self-owned minion serialization only.",
        },
        "assumptions": [
            "No current guide research, gameplay or live runtime evidence."
        ],
    }


@pytest.fixture(scope="module")
def catalog_cases(tmp_path_factory):
    class Cases(dict):
        def __missing__(self, name):
            root = tmp_path_factory.mktemp("quality-" + name)
            with pytest.MonkeyPatch.context() as monkeypatch:
                frozen = quality_frozen_inputs(
                    root,
                    monkeypatch,
                    deck_name=name,
                    captured_at=AUDITED_CARD_DB_METADATA["captured_at"],
                    upstream_version=str(AUDITED_CARD_DB_METADATA["source_build"]),
                    include_source_documents=False,
                    bind_deck_code=True,
                )
            context = build_quality_starter_context(frozen)
            result = (frozen, context, _draft(context))
            self[name] = result
            return result

    return Cases()


def _admit(context, draft):
    candidate = validate_starter_candidate(
        seal_quality_candidate(draft), context=context
    )
    validate_quality_candidate_admission(candidate, context)
    return candidate


def test_catalog_and_full_source_snapshot_are_the_pinned_audited_inputs():
    catalog = json.loads(Path("docs/operator/audited-deck-catalog.json").read_bytes())
    assert catalog["decks"] == EXPECTED_AUDITED_DECK_CATALOG
    assert len(REPRESENTATIVES) == 11
    assert {row["deck_name"] for row in REPRESENTATIVES} == set(CLASSES)
    assert [
        row["deck_name"]
        for row in catalog["decks"]
        if row["matrix_role"] == "supplemental"
    ] == ["CuteWarrior"]
    source = json.loads(AUDITED_CARD_DB_PATH.read_bytes())
    assert len(source["cards"]) == 192
    assert source["metadata"] == AUDITED_CARD_DB_METADATA
    assert _snapshot_sha256(source) == AUDITED_CARD_DB_METADATA["snapshot_sha256"]


@pytest.mark.parametrize("entry", REPRESENTATIVES, ids=lambda row: row["deck_name"])
def test_exact_catalog_deck_validates_admits_and_compiles(entry, catalog_cases):
    frozen, context, draft = catalog_cases[entry["deck_name"]]
    value = context.document.to_value()
    deck = frozen.deck.to_value()
    identity = deck["deck_identity"]
    # HS/HDT IDs belong to the pinned catalog (checked above), not the schema-3
    # compiler identity. Do not invent additional authority-bearing fields.
    assert (
        identity["deck_name"]
        == value["deck_identity"]["deck_name"]
        == entry["deck_name"]
    )
    assert deck["cards_payload"]["deck_code"] == entry["deck_code"]
    code_hash = sha256(entry["deck_code"].encode()).hexdigest()
    assert identity["deck_code_hash"] == code_hash
    assert sum(row["count"] for row in value["cards"]) == 30
    main_ids = {row["card_id"] for row in value["cards"]}
    assert main_ids == {row["card_id"] for row in identity["cards"]}
    hero = next(
        row
        for row in frozen.full_cards.to_value()
        if row["dbf_id"] == identity["hero_dbf_id"]
    )
    assert hero["card_class"] == CLASSES[entry["deck_name"]]
    assert len(frozen.full_cards.to_value()) == 192
    assert main_ids <= value["card_metadata"].keys()
    assert all(
        value["card_metadata"][card_id]["dbf_id"] is not None for card_id in main_ids
    )
    assert value["research_evidence"]["discovery_outcome"] == "unavailable"
    assert any(row["missing_fields"] for row in value["card_metadata"].values())

    candidate = _admit(context, draft)
    receipt = quality_receipt(context, candidate)
    review = validate_starter_review(
        quality_review(
            context,
            candidate,
            receipt,
            mutate=lambda row: row.update(
                review_summary="Static contract fixture only; no strategic or runtime approval."
            ),
        ),
        context=context,
        candidate=candidate,
        validation_receipt=receipt,
    )
    approval = ValidatedSingleStarterApproval(
        snapshot=frozen.manifest,
        context=context,
        candidate=candidate,
        review=review,
        validation_receipt=receipt,
    )
    compiled = compile_package(
        FrozenApprovedLiveConfigureRequest.from_values(
            frozen_compiler_inputs=frozen,
            starter_approval=approval,
        )
    )
    assert compiled.deck_name == entry["deck_name"]
    assert compiled.deck_fingerprint == context.deck_fingerprint
    assert compiled.deck_code_sha256 == code_hash
    assert len(compiled.globalvalues_ledger.decisions) == 38
    assert {row.key for row in compiled.globalvalues_ledger.decisions} == set(
        GLOBALVALUES_BASELINE_DECISION_KEYS
    )
    assert {row["card_id"] for row in draft["card_dispositions"]} == main_ids
    assert len(draft["card_dispositions"]) == len(main_ids)
    compiled_cards = [
        row.composite_card_key.rsplit(":", 1)[-1]
        for row in compiled.disposition_ledger.cards
    ]
    assert all(compiled_cards.count(card_id) == 1 for card_id in main_ids)
    surfaces = {
        row.file_name: row.document.to_value() for row in compiled.runtime_surfaces
    }
    physical = draft["card_rules"][0]["source_card_id"]
    assert {
        row.file_name for row in compiled.runtime_surfaces if row.family == "CardID"
    } == {physical + ".json"}
    assert surfaces[physical + ".json"]["GameCardId"] == physical
    assert surfaces["Mulligan.json"]["Mulligan"]["values"][0]["condition"] == "coin"
    assert surfaces["Mulligan.json"]["Mulligan"]["values"][0]["mulligan"] == physical
    assert surfaces["Mulligan.json"]["Mulligan"]["values"][0]["value"] == "hold"
    assert "Combo.json" not in surfaces
    facts = receipt.to_value()["review_facts"]
    assert facts["globalvalues_changes"] == {}
    assert {row["card_id"] for row in facts["card_dispositions"]} == main_ids
    assert facts["runtime_authorized"] is False
    assert facts["evidence_references"] == []
    assert value["existing_claims"] == []
    assert value["source_evidence"]["guide_sources_summary"]["source_count"] == 0


def test_mechpala_preserves_real_zilliax_sideboard_without_extra_main_owners(
    catalog_cases,
):
    frozen, context, _ = catalog_cases["MechPala"]
    value = context.document.to_value()
    assert value["sideboards"] == [
        {"owner_card_id": "TOY_330", "index": 1, "card_id": card_id, "count": 1}
        for card_id in ("TOY_330t95", "TOY_330t98", "TOY_330t11")
    ]
    assert "TOY_330" in {row["card_id"] for row in value["cards"]}
    assert "ETC_080" not in {row["card_id"] for row in value["cards"]}
    for card_id in ("TOY_330t95", "TOY_330t98", "TOY_330t11"):
        assert card_id in value["card_metadata"]
        assert card_id not in {row["card_id"] for row in value["cards"]}
    assert (
        frozen.deck.to_value()["deck_identity"]["sideboards"][0]["owner_card_id"]
        == "TOY_330"
    )


def test_kingslayer_name_does_not_invent_a_kingsbane_weapon(catalog_cases):
    _, context, draft = catalog_cases["Kingslayer"]
    value = context.document.to_value()
    assert value["deck_identity"]["deck_name"] == "Kingslayer"
    assert "LOOT_542" not in value["card_metadata"]  # Actual Kingsbane CardID.
    assert all(row["name"] != "Kingsbane" for row in value["card_metadata"].values())
    foreign = deepcopy(draft)
    foreign["mulligan"][0]["selector"] = "LOOT_542"
    with pytest.raises(ValueError, match="starter_candidate_mulligan_card_invalid"):
        _admit(context, foreign)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "sideboard"])
def test_exact_main_deck_dispositions_cannot_be_missing_or_substituted(
    catalog_cases, defect
):
    _, context, original = catalog_cases["MechPala"]
    draft = deepcopy(original)
    if defect == "missing":
        draft["card_dispositions"].pop()
    elif defect == "duplicate":
        draft["card_dispositions"][-1] = deepcopy(draft["card_dispositions"][0])
    else:
        draft["card_dispositions"][-1]["card_id"] = "TOY_330t95"
    with pytest.raises(ValueError, match="starter_candidate_card_dispositions_invalid"):
        _admit(context, draft)


@pytest.mark.parametrize("defect", ["missing-source", "foreign-owner"])
def test_real_sideboard_requires_resolved_identity_and_physical_owner(
    catalog_cases, defect
):
    frozen, _, _ = catalog_cases["MechPala"]
    deck = frozen.deck.to_value()["deck_identity"]
    cards = frozen.full_cards.to_value()
    if defect == "missing-source":
        cards = [row for row in cards if row["id"] != "TOY_330t95"]
        error = "starter_card_facts_required_identity_unresolved"
    else:
        deck["sideboards"][0]["owner_card_id"] = "ETC_080"
        error = "starter_card_facts_sideboard_invalid"
    with pytest.raises(ValueError, match=error):
        project_card_facts(deck, cards)


@pytest.mark.parametrize(
    "defect",
    ["wrong-deck", "missing-globalvalue", "unsupported-condition", "impossible-coin"],
)
def test_catalog_candidate_boundaries_are_rejected(catalog_cases, defect):
    _, context, original = catalog_cases["Kingslayer"]
    draft = deepcopy(original)
    if defect == "wrong-deck":
        draft["deck_fingerprint"] = catalog_cases["PirateRogue"][1].deck_fingerprint
        error = "starter_candidate_deck_fingerprint_mismatch"
    elif defect == "missing-globalvalue":
        draft["globalvalues"].pop("FirstTurnValueWeight")
        error = "starter_candidate_globalvalues_keys_invalid"
    else:
        draft["mulligan"][0]["condition"] = (
            "coin AND nocoin" if defect == "impossible-coin" else "Turn >= 5"
        )
        error = (
            "starter_candidate_condition_impossible"
            if defect == "impossible-coin"
            else "starter_candidate_condition_invalid"
        )
    with pytest.raises(ValueError, match=error):
        _admit(context, draft)


@pytest.mark.parametrize(
    "deck_name,card_id", [("Boarlock", "SW_075"), ("PirateDH", "AV_204")]
)
def test_original_dynamic_card_text_survives_context_build_and_revalidation(
    catalog_cases, deck_name, card_id
):
    _, context, _ = catalog_cases[deck_name]
    source = json.loads(AUDITED_CARD_DB_PATH.read_bytes())
    original = next(row[6] for row in source["cards"] if row[1] == card_id)
    value = context.document.to_value()
    assert value["card_metadata"][card_id]["text"] == original
    assert (
        reseal_context(value).document.canonical_json == context.document.canonical_json
    )


@pytest.mark.parametrize(
    "text", ["@/4", "Summon two @/4 Demons.", "Progress (@/10)", "<i>(@/10)</i>"]
)
def test_complete_numeric_placeholders_are_card_text_only(text):
    value = load_historical_document(3, "starter_context").to_value()
    value["card_metadata"]["TOY_518"]["text"] = text
    context = reseal_context(value)
    assert context.document.to_value()["card_metadata"]["TOY_518"]["text"] == text


@pytest.mark.parametrize(
    "text",
    [
        "@/10/secret",
        "@/../secret",
        "@/10secret",
        "@/10_foo",
        "@/10\\secret",
        "/10",
        "@/0",
        "@/01",
        "@/-1",
        "prefix@/10",
        "@/10suffix",
        "C:\\secret",
        "\\\\server\\share",
        "@/10 /private/file",
        "@/10 https://example.org",
        "<b>@/10",
        "@/10\t",
        "@/10\u200b",
        "@/10 " + "x" * 20000,
    ],
)
def test_card_text_placeholders_do_not_bypass_safety_guards(text):
    value = load_historical_document(3, "starter_context").to_value()
    value["card_metadata"]["TOY_518"]["text"] = text
    with pytest.raises(ValueError, match="starter_context_document_invalid"):
        reseal_context(value)


@pytest.mark.parametrize("field", ["name", "general-prose"])
def test_counter_exception_does_not_expand_name_or_general_prose(field):
    value = load_historical_document(3, "starter_context").to_value()
    if field == "name":
        value["card_metadata"]["TOY_518"]["name"] = "@/10"
        with pytest.raises(ValueError, match="starter_context_document_invalid"):
            reseal_context(value)
    else:
        from hsconfig.starter_context import _validated_context_prose

        with pytest.raises(ValueError, match="starter_context_document_invalid"):
            _validated_context_prose("@/10")
