from copy import deepcopy
from dataclasses import replace

import pytest

from hsconfig.card_snapshot import build_card_snapshot
from hsconfig.package_request import FrozenJsonDocument


def test_sideboard_identity_is_shared_but_membership_is_not_lost():
    from hsconfig.starter_card_facts import project_card_facts

    deck = {
        "cards": [
            {"card_id": "TEST_OWNER", "count": 1},
            {"card_id": "TEST_MEMBER", "count": 1},
        ],
        "sideboards": [
            {
                "owner_card_id": "TEST_OWNER",
                "sideboard_index": 1,
                "cards": [{"card_id": "TEST_MEMBER", "count": 2}],
            }
        ],
    }
    full = [
        {
            "id": "TEST_OWNER",
            "dbfId": 1,
            "type": "MINION",
            "name": "Owner",
            "cost": 3,
            "attack": 2,
            "health": 4,
        },
        {
            "id": "TEST_MEMBER",
            "dbfId": 2,
            "type": "MINION",
            "name": "Member",
            "cost": 1,
            "attack": 1,
            "health": 2,
        },
    ]
    snapshot = build_card_snapshot(full, captured_at="2026-09-09T00:00:00Z")
    facts = project_card_facts(deck, snapshot.to_value()["full_cards"])
    assert len(facts["card_metadata"]) == 2
    assert facts["card_metadata"]["TEST_MEMBER"]["health"] == 2
    assert facts["sideboards"] == [
        {
            "owner_card_id": "TEST_OWNER",
            "index": 1,
            "card_id": "TEST_MEMBER",
            "count": 2,
        }
    ]
    assert facts["cards"] == deck["cards"]


def test_linked_facts_missing_stats_zero_and_crlf():
    from hsconfig.starter_card_facts import project_card_facts

    snapshot = build_card_snapshot(
        [
            {
                "id": "TEST_001",
                "dbfId": 1,
                "type": "MINION",
                "name": "Owner",
                "cost": 0,
                "text": "First\r\nSecond\rThird",
                "heroPowerDbfId": 2,
            },
            {
                "id": "TEST_002",
                "dbfId": 2,
                "type": "HERO_POWER",
                "name": "Power",
                "cost": 2,
                "text": "Deal damage.",
                "entourage": ["TEST_003"],
            },
            {"id": "TEST_003", "dbfId": 3, "type": "MINION", "name": "Indirect"},
        ],
        captured_at="2026-09-09T00:00:00Z",
    )
    facts = project_card_facts(
        {"cards": [{"card_id": "TEST_001", "count": 1}]},
        snapshot.to_value()["full_cards"],
    )
    owner = facts["card_metadata"]["TEST_001"]
    assert owner["cost"] == 0
    assert owner["attack"] is None and "attack" in owner["missing_fields"]
    assert owner["durability"] is None and "durability" in owner["inapplicable_fields"]
    assert owner["text"] == "First Second Third"
    assert facts["card_metadata"]["TEST_002"]["cost"] == 2
    assert "TEST_003" not in facts["card_metadata"]
    assert facts["linked_entities"] == [
        {
            "source_card_id": "TEST_001",
            "card_id": "TEST_002",
            "link_kind": "starting_hero_power",
            "status": "resolved",
        }
    ]
    from hsconfig.starter_card_facts import validate_card_facts

    forged = deepcopy(facts)
    forged["card_metadata"]["TEST_001"]["mechanics"] = ["INVALID\tTOKEN"]
    forged["card_metadata"]["TEST_001"]["missing_fields"].remove("mechanics")
    with pytest.raises(ValueError):
        validate_card_facts(forged)


@pytest.mark.parametrize("count", [True, 0, -1, "2", 1.5])
def test_projection_rejects_malformed_membership_count(count):
    from hsconfig.starter_card_facts import project_card_facts

    with pytest.raises(ValueError):
        project_card_facts({"cards": [{"card_id": "TEST_001", "count": count}]}, [])


def test_quality_context_and_physical_manifest_round_trip(tmp_path, monkeypatch):
    from tests.helpers.quality_start import quality_frozen_inputs
    from tests.test_input_snapshot_manifest import _write_frozen_inputs
    from hsconfig.input_snapshot_manifest import load_frozen_compiler_inputs
    from hsconfig.starter_context import (
        build_quality_starter_context,
        build_single_candidate_starter_context,
        validate_starter_context_document,
    )

    frozen = quality_frozen_inputs(tmp_path, monkeypatch)
    legacy_before = build_single_candidate_starter_context(
        frozen
    ).document.canonical_json
    context = build_quality_starter_context(frozen)
    assert (
        build_single_candidate_starter_context(frozen).document.canonical_json
        == legacy_before
    )
    value = context.document.to_value()
    assert value["schema_version"] == 3
    assert all(set(card) == {"card_id", "count"} for card in value["cards"])
    assert len(value["globalvalues_baseline"]["values"]) == 38
    assert "discovery_unavailable" in value["research_evidence"]["limitations"]
    assert validate_starter_context_document(context.document) == context
    root = tmp_path / "run"
    _write_frozen_inputs(root, frozen)
    (root / "inputs" / "quality.json").write_bytes(frozen.quality_inputs.canonical_json)
    loaded = load_frozen_compiler_inputs(root)
    assert loaded == frozen
    assert (
        build_quality_starter_context(loaded).document.canonical_json
        == context.document.canonical_json
    )


@pytest.mark.parametrize("defect", ["digest", "collectible", "extra", "research_extra"])
def test_quality_payload_rejects_stale_or_open_input(tmp_path, monkeypatch, defect):
    from tests.helpers.quality_start import quality_frozen_inputs
    from hsconfig.starter_context import build_quality_starter_context
    from hsconfig.input_snapshot_manifest import validate_quality_inputs

    frozen = quality_frozen_inputs(tmp_path, monkeypatch)
    quality = frozen.quality_inputs.to_value()
    if defect == "digest":
        quality["card_snapshot_sha256"] = "sha256:" + "0" * 64
    elif defect == "extra":
        quality["runtime_root"] = "injected"
    elif defect == "research_extra":
        quality["research_result"]["authority"] = "live_verified"
    if defect == "collectible":
        forged = replace(frozen, collectible_cards=FrozenJsonDocument.from_value([]))
    else:
        forged = replace(frozen, quality_inputs=FrozenJsonDocument.from_value(quality))
    with pytest.raises(ValueError):
        build_quality_starter_context(forged)
    with pytest.raises(ValueError):
        validate_quality_inputs(
            forged.quality_inputs,
            full_cards=forged.full_cards.to_value(),
            collectible_cards=forged.collectible_cards.to_value(),
        )


def test_schema_three_rejects_resealed_excess_fields_and_bad_counts(
    tmp_path, monkeypatch
):
    from tests.helpers.quality_start import quality_frozen_inputs
    from hsconfig.starter_context import (
        build_quality_starter_context,
        validate_starter_context_document,
    )
    from hsconfig.starter_contract import QUALITY_STARTER_CONTEXT_FIELDS
    from hsconfig.starter_document import seal_starter_document

    value = build_quality_starter_context(
        quality_frozen_inputs(tmp_path, monkeypatch)
    ).document.to_value()
    value.pop("content_sha256")
    for defect in ("metadata", "count"):
        draft = deepcopy(value)
        if defect == "metadata":
            next(iter(draft["card_metadata"].values()))["authority"] = "live_verified"
        else:
            draft["cards"][0]["count"] = True
        sealed = seal_starter_document(
            draft, expected_fields=QUALITY_STARTER_CONTEXT_FIELDS, schema_version=3
        )
        with pytest.raises(ValueError):
            validate_starter_context_document(sealed)


def test_research_urls_are_context_only_and_conflicts_are_closed():
    from hashlib import sha256
    from hsconfig.input_snapshot_manifest import validate_research_result
    from hsconfig.live_start_research import build_research_result

    record = {
        "source_url": "https://example.org/guide",
        "evidence_id": "guide-one",
        "content_sha256": "a" * 64,
        "retrieved_at": "2026-09-09T00:00:00Z",
        "normalized_text": "Owner should be kept in the mulligan.",
    }
    digest = (
        "sha256:"
        + sha256(FrozenJsonDocument.from_value(record).canonical_json).hexdigest()
    )
    result = build_research_result(
        acquired={"source_records": [record]},
        discovery_outcome="completed",
        deadline_utc=100.0,
        attempts=[
            {
                "url": record["source_url"],
                "state": "completed",
                "record_sha256": digest,
                "error": None,
            }
        ],
        card_metadata={"TEST_001": {"name": "Owner"}},
    ).to_value()
    assert validate_research_result(result, card_ids={"TEST_001"}) == result
    assert result["observations"][0]["applicability"] == "card_only"
    forged = deepcopy(result)
    forged["observations"][0]["conflicts"] = [{"runtime_root": "injected"}]
    forged.pop("content_sha256")
    forged["content_sha256"] = (
        "sha256:"
        + sha256(FrozenJsonDocument.from_value(forged).canonical_json).hexdigest()
    )
    with pytest.raises(ValueError):
        validate_research_result(forged, card_ids={"TEST_001"})


def test_unresolved_and_random_relations_never_create_metadata():
    from hsconfig.starter_card_facts import project_card_facts, validate_card_facts

    snapshot = build_card_snapshot(
        [
            {
                "id": "TEST_001",
                "dbfId": 1,
                "type": "SPELL",
                "name": "Random",
                "text": "Summon a random minion.",
                "entourage": ["TEST_MISSING"],
            }
        ],
        captured_at="2026-09-09T00:00:00Z",
    )
    facts = project_card_facts(
        {"cards": [{"card_id": "TEST_001", "count": 1}]},
        snapshot.to_value()["full_cards"],
    )
    assert set(facts["card_metadata"]) == {"TEST_001"}
    malformed = deepcopy(facts)
    malformed["sideboards"] = {}
    with pytest.raises(ValueError):
        validate_card_facts(malformed)
    assert facts["linked_entities"] == [
        {
            "source_card_id": "TEST_001",
            "card_id": "TEST_MISSING",
            "link_kind": "entourage",
            "status": "unresolved",
        },
        {
            "source_card_id": "TEST_001",
            "card_id": None,
            "link_kind": "random_pool",
            "status": "random",
        },
    ]
