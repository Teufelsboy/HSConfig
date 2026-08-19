from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from hsconfig.package_request import PackageResolutionSnapshot
from hsconfig.starter_context import (
    _enforce_starter_context_max_bytes,
    build_starter_context,
)
from hsconfig.starter_contract import (
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_document import seal_starter_document
from tests.helpers.audited_package_request import audited_request


SHADOWPRIEST_CARD_COUNTS = {
    "CFM_637": 1,
    "DRG_056": 2,
    "DS1_233": 2,
    "GVG_009": 2,
    "NX2_019": 2,
    "REV_290": 2,
    "SCH_514": 2,
    "SW_444": 2,
    "SW_446": 2,
    "SW_448": 1,
    "TOY_381": 2,
    "TOY_518": 2,
    "VAC_419": 2,
    "VAC_512": 2,
    "WON_065": 2,
    "YOD_032": 2,
}


def test_sealed_starter_context_validator_accepts_canonical_shadowpriest(
    tmp_path: Path,
) -> None:
    from hsconfig.starter_context import validate_starter_context_document

    context = build_starter_context(
        audited_request(tmp_path, "ShadowPriest").snapshot
    )

    validated = validate_starter_context_document(context.document)

    assert validated == context
    assert validated.document.canonical_json == context.document.canonical_json
    assert validated.deck_fingerprint == (
        "831b989cf8d076bff87848b4d0d6f382c9d306fddea7619017f0c361bfc92327"
    )


@pytest.mark.parametrize(
    "defect",
    (
        "source_evidence_wrong_type",
        "source_row_unknown_key",
        "source_gap_missing_key",
        "source_provenance_drift",
        "source_claim_count_drift",
        "deck_identity_unknown_key",
        "cards_missing_key",
        "linked_entity_unknown_key",
        "identity_card_count_drift",
        "deck_shape_drift",
        "runtime_contract_unknown_key",
        "baseline_missing_key",
        "baseline_receipt_drift",
        "existing_claim_unknown_key",
        "claim_card_unbound",
        "claim_deck_match_drift",
        "claim_source_family_drift",
        "safety_boundary_missing_key",
    ),
)
def test_sealed_starter_context_validator_rejects_nested_family_drift(
    tmp_path: Path,
    defect: str,
) -> None:
    from hsconfig.starter_context import validate_starter_context_document

    context = build_starter_context(
        audited_request(tmp_path, "ShadowPriest").snapshot
    )
    value = context.document.to_value()
    del value["content_sha256"]

    if defect == "source_evidence_wrong_type":
        value["source_evidence"] = "invalid"
    elif defect == "source_row_unknown_key":
        value["source_evidence"]["rows"][0]["captured_at"] = (
            "2026-07-29T00:00:00Z"
        )
    elif defect == "source_gap_missing_key":
        del value["source_evidence"]["gaps"][0]["value"]
    elif defect == "source_provenance_drift":
        value["source_evidence"]["rows"][0]["provenance"]["mode"] = (
            "invented"
        )
    elif defect == "source_claim_count_drift":
        value["source_evidence"]["rows"][0]["claim_count"] = 2
    elif defect == "deck_identity_unknown_key":
        value["deck_identity"]["invented_authority"] = "hidden"
    elif defect == "cards_missing_key":
        del value["cards"][0]["name"]
    elif defect == "linked_entity_unknown_key":
        linked_card = next(card for card in value["cards"] if card["linked_entities"])
        linked_card["linked_entities"][0]["invented_authority"] = "hidden"
    elif defect == "identity_card_count_drift":
        value["deck_identity"]["card_count_total"] = 29
    elif defect == "deck_shape_drift":
        value["deck_shape"]["physical_card_count"] = 29
    elif defect == "runtime_contract_unknown_key":
        value["supported_runtime_contract"]["invented_surface"] = {}
    elif defect == "baseline_missing_key":
        del value["globalvalues_baseline"]["values"]["GlobalTaunt"]
    elif defect == "baseline_receipt_drift":
        value["globalvalues_baseline"]["receipt"]["snapshot_status"] = (
            "live_runtime"
        )
    elif defect == "existing_claim_unknown_key":
        value["existing_claims"][0]["invented_authority"] = "hidden"
    elif defect == "claim_card_unbound":
        value["existing_claims"][0]["cards"] = ["EX1_001"]
    elif defect == "claim_deck_match_drift":
        value["existing_claims"][0]["deck_match"][
            "target_deck_code_sha256"
        ] = "f" * 64
    elif defect == "claim_source_family_drift":
        value["existing_claims"][0]["source_family"] = "invented"
    elif defect == "safety_boundary_missing_key":
        del value["known_safety_boundaries"][0]["restrictions"]
    else:
        raise AssertionError(f"unknown_test_defect:{defect}")

    rebound = seal_starter_document(
        value,
        expected_fields=STARTER_CONTEXT_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )

    with pytest.raises(
        ValueError,
        match="^starter_context_document_invalid$",
    ):
        validate_starter_context_document(rebound)


def test_shadowpriest_starter_context_closes_identity_cards_and_runtime_contract(
    tmp_path: Path,
) -> None:
    # Break caught: resolving physical copies as duplicate rows or omitting
    # strategy-critical card, registry, baseline, or Darkbishop authority.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot

    context = build_starter_context(snapshot)
    value = context.document.to_value()
    identity = value["deck_identity"]
    cards = value["cards"]
    card_by_id = {row["card_id"]: row for row in cards}

    assert context.deck_fingerprint == (
        "831b989cf8d076bff87848b4d0d6f382c9d306fddea7619017f0c361bfc92327"
    )
    assert identity == {
        "card_count_total": 30,
        "deck_code_sha256": (
            "fd7afada1f4a7f60bb269dc56188ddf83603e4bb0147a163d3e337be388917f2"
        ),
        "deck_fingerprint": context.deck_fingerprint,
        "deck_name": "ShadowPriest",
        "format": "FT_WILD",
        "hdt_deck_id": "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602",
        "hero_dbf_id": 813,
        "hs_id": "2737726722",
        "unique_card_count": 16,
    }
    assert len(cards) == 16
    assert {row["card_id"]: row["count"] for row in cards} == (SHADOWPRIEST_CARD_COUNTS)
    assert all(row["count"] > 0 for row in cards)
    assert sum(row["count"] for row in cards) == 30
    assert all(
        {"card_id", "count", "cost", "type", "text", "mechanics", "linked_entities"}
        <= set(row)
        for row in cards
    )
    assert card_by_id["SW_448"]["cost"] == 5
    assert card_by_id["SW_448"]["type"] == "MINION"
    assert "Start of Game" in card_by_id["SW_448"]["text"]
    assert card_by_id["SW_448"]["linked_entities"] == [
        {
            "card_id": "EX1_625t",
            "dbf_id": 1622,
            "link_kind": "hero_power_transform",
            "name": "Mind Spike",
            "type": "HERO_POWER",
        }
    ]

    assert value["deck_shape"] == {
        "curve_counts": {"0": 2, "1": 13, "2": 10, "3": 2, "4": 2, "5": 1},
        "mechanic_counts": {
            "battlecry": 4,
            "damage": 18,
            "deckbuilding_modifier": 1,
            "draw": 4,
            "hero_power": 3,
            "hero_power_pressure": 1,
            "hero_power_transform": 1,
            "location": 2,
            "location_activation": 2,
            "minion": 20,
            "passive_start_effect": 1,
            "shadowform": 1,
            "spell": 8,
            "spell_school": 2,
            "start_of_game": 1,
            "start_of_game_modifier": 1,
            "summon": 7,
            "summon_trigger_board_engine": 4,
        },
        "physical_card_count": 30,
        "type_counts": {"LOCATION": 2, "MINION": 20, "SPELL": 8},
        "unique_card_count": 16,
    }

    runtime = value["supported_runtime_contract"]
    assert set(runtime["surface_registry"]) == {
        "CARDID.json",
        "CardBehavior.json",
        "Combo.json",
        "Concede.json",
        "GlobalValues.json",
        "Mulligan.json",
        "Presume.json",
    }
    assert len(runtime["globalvalue_constraints"]) == 38
    assert runtime["globalvalue_constraints"]["GlobalTaunt"] == {
        "copy_baseline_only": False,
        "maximum": "1000",
        "minimum": "-1000",
        "value_type_id": "safe_numeric_expression",
    }
    assert runtime["globalvalue_constraints"]["GameCardId"] == {
        "copy_baseline_only": True,
        "maximum": None,
        "minimum": None,
        "value_type_id": "copy_baseline",
    }
    assert runtime["card_value_constraint"] == {
        "copy_baseline_only": False,
        "maximum": "10000",
        "minimum": "-10000",
        "value_type_id": "finite_decimal",
    }
    assert runtime["combo_value_constraint"] == runtime["card_value_constraint"]
    assert "BeforeUseHeroPowerBonus" in runtime["card_behavior_blocks"]

    baseline = value["globalvalues_baseline"]
    assert context.globalvalues_baseline_sha256 == (
        "sha256:67e6f87a792c86ffbd28b10b6289ba6d88ef17c7e8204eff3b7d968be77b5177"
    )
    assert baseline["content_sha256"] == context.globalvalues_baseline_sha256
    assert baseline["key_count"] == 38
    assert len(baseline["values"]) == 38
    assert baseline["receipt"] == {
        "key_count": 38,
        "snapshot_date": "2026-07-25",
        "snapshot_status": "known_runtime_snapshot",
        "source": "bundled_fallback",
    }

    assert {
        "boundary_id": "darkbishop_transformed_hero_power_owner",
        "behavior_block": "BeforeUseHeroPowerBonus",
        "linked_card_id": "EX1_625t",
        "restrictions": [
            "do_not_infer_mulligan_keep",
            "do_not_target_source_card_for_transformed_hero_power",
        ],
        "source_card_id": "SW_448",
    } in value["known_safety_boundaries"]


def test_starter_context_digest_ignores_volatile_source_transport_but_binds_semantics(
    tmp_path: Path,
) -> None:
    # Break caught: hashing timestamps/paths or failing to bind semantic card changes.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()

    volatile = deepcopy(preconfig)
    volatile["guide_claim_bundle"]["source_evidence_index"][0]["retrieved_at"] = (
        "2099-12-31T23:59:59Z"
    )
    volatile_context = build_starter_context(
        PackageResolutionSnapshot.from_preconfig(volatile)
    )

    semantic = deepcopy(preconfig)
    semantic["card_metadata"]["cards"][0]["text"] += " Changed semantics."
    semantic_context = build_starter_context(
        PackageResolutionSnapshot.from_preconfig(semantic)
    )

    assert volatile_context.document.content_sha256 == (
        original.document.content_sha256
    )
    assert volatile_context.document.canonical_json == original.document.canonical_json
    assert semantic_context.document.content_sha256 != original.document.content_sha256

    value = original.document.to_value()
    assert value["content_sha256"] == original.document.content_sha256
    assert value["source_evidence"]["gaps"] == [
        {
            "gap_kind": "missing_deck_identity",
            "value": "starting_hero_power_id",
        }
    ]
    assert value["source_evidence"]["rows"]
    assert value["existing_claims"]
    _assert_no_volatile_or_raw_source_fields(value["source_evidence"])
    _assert_no_volatile_or_raw_source_fields(value["existing_claims"])


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda value: value["deck_identity"]["main_deck"][0].__setitem__(
                "count", 99
            ),
            "starter_context_deck_roster_mismatch",
        ),
        (
            lambda value: value["card_metadata"]["cards"][0].__setitem__(
                "count", 99
            ),
            "starter_context_deck_roster_mismatch",
        ),
        (
            lambda value: value["deck_identity"]["main_deck"].append(
                deepcopy(value["deck_identity"]["main_deck"][0])
            ),
            "starter_context_deck_roster_duplicate",
        ),
        (
            lambda value: value["deck_identity"].__setitem__(
                "card_count_total", 29
            ),
            "starter_context_deck_card_count_mismatch",
        ),
        (
            lambda value: value["deck_identity"].__setitem__(
                "deck_fingerprint", "f" * 64
            ),
            "starter_context_deck_fingerprint_mismatch",
        ),
    ],
)
def test_starter_context_cross_binds_projected_cards_to_exact_deck_identity(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    error: str,
) -> None:
    # Break caught: allowing card metadata, roster totals, or fingerprint to
    # disagree while projecting them as one authoritative deck.
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(ValueError, match=error):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        (
            "deck_code_hash",
            "sha256:not-a-hash",
            "starter_context_deck_code_sha256_invalid",
        ),
        (
            "deck_fingerprint",
            "A" * 64,
            "starter_context_deck_fingerprint_invalid",
        ),
    ],
)
def test_starter_context_validates_identity_hash_formats(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    preconfig["deck_identity"][field] = value

    with pytest.raises(ValueError, match=error):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_rejects_catalog_ids_without_exact_audited_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    identity = snapshot.general_preconfig.to_value()["deck_identity"]
    monkeypatch.setattr(
        "hsconfig.starter_context.load_audited_deck_catalog",
        lambda: [
            {
                "deck_name": "ShadowPriest",
                "deck_code": "different-deck-code",
                "hs_id": "2737726722",
                "hdt_deck_id": "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602",
            }
        ],
    )
    monkeypatch.setattr(
        "hsconfig.starter_context.load_packaged_audited_build_inputs",
        lambda: SimpleNamespace(
            builds=(
                SimpleNamespace(
                    deck_name="ShadowPriest",
                    deck_code_sha256=str(identity["deck_code_hash"]),
                    deck_fingerprint=str(identity["deck_fingerprint"]),
                ),
            )
        ),
    )

    with pytest.raises(ValueError, match="starter_context_audited_identity_mismatch"):
        build_starter_context(snapshot)


def test_starter_context_rejects_ids_when_audited_build_fingerprint_disagrees(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    identity = snapshot.general_preconfig.to_value()["deck_identity"]
    monkeypatch.setattr(
        "hsconfig.starter_context.load_packaged_audited_build_inputs",
        lambda: SimpleNamespace(
            builds=(
                SimpleNamespace(
                    deck_name="ShadowPriest",
                    deck_code_sha256=str(identity["deck_code_hash"]),
                    deck_fingerprint="f" * 64,
                ),
            )
        ),
    )

    with pytest.raises(ValueError, match="starter_context_audited_identity_mismatch"):
        build_starter_context(snapshot)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda claim: claim.__setitem__(
            "conditions", {"runtime_path": "C:\\private\\runtime.xml"}
        ),
        lambda claim: claim.__setitem__(
            "semantic_qualifiers",
            {"timing": "start_of_game", "transport": {"raw_html": "<html>"}},
        ),
        lambda claim: claim.__setitem__(
            "semantic_qualifiers", {"timing": "<html>secret</html>"}
        ),
        lambda claim: claim["acquisition_provenance"].__setitem__(
            "retrieved_at", "2099-01-01T00:00:00Z"
        ),
        lambda claim: claim["source_identity_signals"][0].__setitem__(
            "path", "D:/capture/raw.json"
        ),
        lambda claim: claim["deck_match"]["exact_deck_evidence"].__setitem__(
            "runtime_path", "D:/runtime/CustomConfig"
        ),
    ],
)
def test_starter_context_rejects_unclosed_claim_semantics_and_transport_leaks(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig["guide_claim_bundle"]["claims"][0])

    with pytest.raises(ValueError, match="starter_context_claim_semantics_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_digest_binds_claim_authority_fields(tmp_path: Path) -> None:
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0]["trust_ceiling"] = (
        "static_semantics"
    )
    changed_claim_id = preconfig["guide_claim_bundle"]["claims"][0]["claim_id"]
    changed = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))

    assert changed.document.content_sha256 != original.document.content_sha256
    claim = next(
        row
        for row in changed.document.to_value()["existing_claims"]
        if row["claim_id"] == changed_claim_id
    )
    assert "trust_ceiling" in claim
    assert claim["deck_match"]["exact_deck_evidence"]["matched"] is True
    _assert_no_volatile_or_raw_source_fields(claim)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["globalvalues_baseline_receipt"].__setitem__(
            "key_count", True
        ),
        lambda value: value["globalvalues_baseline_receipt"].__setitem__(
            "source", "unknown_transport"
        ),
        lambda value: value["globalvalues_baseline_receipt"].__setitem__(
            "snapshot_status", "live_runtime"
        ),
        lambda value: value["globalvalues_baseline_receipt"].__setitem__(
            "snapshot_date", "2026-7-5"
        ),
        lambda value: value["globalvalues_baseline_receipt"].__setitem__(
            "retrieved_at", "2099-01-01T00:00:00Z"
        ),
        lambda value: _replace_baseline_value(
            value, "GlobalTaunt", {"values": [{"condition": "*", "value": True}]}
        ),
        lambda value: _replace_baseline_value(
            value, "ConfigComment", {"path": "D:/runtime/GlobalValues.json"}
        ),
    ],
)
def test_starter_context_validates_closed_typed_globalvalues_receipt(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(
        ValueError,
        match="starter_context_globalvalues_baseline_invalid",
    ):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def _replace_baseline_value(
    preconfig: dict[str, Any],
    key: str,
    value: object,
) -> None:
    preconfig["globalvalues_baseline"][key] = value
    preconfig["globalvalues_baseline_receipt"]["baseline"][key] = deepcopy(value)


def test_starter_context_maximum_applies_to_final_canonical_bytes() -> None:
    _enforce_starter_context_max_bytes(b"x" * STARTER_CONTEXT_MAX_BYTES)

    with pytest.raises(ValueError, match="starter_context_maximum_bytes_exceeded"):
        _enforce_starter_context_max_bytes(
            b"x" * (STARTER_CONTEXT_MAX_BYTES + 1)
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "source_url", "file:///C:/private/source.html"
        ),
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "source_url", "https://127.0.0.1/private/source.html"
        ),
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "source_ref", "C:\\private\\source.json"
        ),
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "source_ref", "/private/source.json"
        ),
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "source_title", "<html>captured transport</html>"
        ),
        lambda value: value["guide_claim_bundle"]["source_evidence_index"][0].__setitem__(
            "acquisition_provenance",
            {
                "authority": "fabricated",
                "content_sha256": "sha256:not-a-digest",
                "mode": "transport",
            },
        ),
        lambda value: value["guide_claim_bundle"]["claims"][0].__setitem__(
            "source_refs", ["C:\\private\\claim.json"]
        ),
        lambda value: value["identity_gap_report"]["missing_identity_fields"].append(
            "/private/runtime/path"
        ),
    ],
)
def test_starter_context_rejects_unclosed_source_evidence_values(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(ValueError, match="starter_context_source_evidence_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_claim_cards_bind_to_exact_deck_and_linked_cardids(
    tmp_path: Path,
) -> None:
    # Break caught: claim cards were generic strings rather than exact deck or
    # registered linked-runtime CardID references.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot).document.to_value()
    projected_card_ids = {
        card_id
        for claim in original["existing_claims"]
        for card_id in claim["cards"]
    }
    assert projected_card_ids == set(SHADOWPRIEST_CARD_COUNTS)

    preconfig = snapshot.general_preconfig.to_value()
    transform = next(
        claim
        for claim in preconfig["guide_claim_bundle"]["claims"]
        if claim["claim_kind"] == "hero_power_transform"
        and "deck_match" in claim
    )
    transform["cards"] = ["EX1_625t"]

    linked = build_starter_context(
        PackageResolutionSnapshot.from_preconfig(preconfig)
    ).document.to_value()
    projected = next(
        claim
        for claim in linked["existing_claims"]
        if claim["claim_id"] == transform["claim_id"]
    )
    assert projected["cards"] == ["EX1_625t"]


@pytest.mark.parametrize(
    "card_reference",
    [
        "Darkbishop Benedictus",
        "C:\\private\\claim.json",
        "/private/claim.json",
        "https://example.com/SW_448",
        "<b>SW_448</b>",
        "SW_448?transport=1",
        f"{'A' * 65}_1",
        "EX1_001",
    ],
)
def test_starter_context_rejects_unclosed_or_unbound_claim_card_references(
    tmp_path: Path,
    card_reference: str,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0]["cards"] = [card_reference]

    with pytest.raises(ValueError, match="starter_context_claim_cards_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_requires_physical_cardids_for_mulligan_claims(
    tmp_path: Path,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mulligan = next(
        claim
        for claim in preconfig["guide_claim_bundle"]["claims"]
        if claim["claim_kind"] == "mulligan_keep"
    )
    mulligan["cards"] = ["EX1_625t"]

    with pytest.raises(ValueError, match="starter_context_claim_cards_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("field", "changed_value"),
    [
        ("stance", "changed_strategy_stance"),
        ("archetype", "changed_strategy_archetype"),
    ],
)
def test_starter_context_digest_binds_authoritative_claim_semantics(
    tmp_path: Path,
    field: str,
    changed_value: str,
) -> None:
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()
    source_claim = next(
        claim
        for claim in preconfig["guide_claim_bundle"]["claims"]
        if claim.get(field)
    )
    claim_id = source_claim["claim_id"]
    source_claim[field] = changed_value

    changed = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))
    projected = next(
        claim
        for claim in changed.document.to_value()["existing_claims"]
        if claim["claim_id"] == claim_id
    )

    assert changed.document.content_sha256 != original.document.content_sha256
    assert projected[field] == changed_value


def test_starter_context_digest_binds_normalized_substantive_claim_text(
    tmp_path: Path,
) -> None:
    # Break caught: omitting the source's substantive claim made strategy-text
    # changes invisible to the canonical context digest.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()
    source_claim = preconfig["guide_claim_bundle"]["claims"][0]
    claim_id = source_claim["claim_id"]
    source_claim["claim"] = "  Changed   semantic strategy claim.  "

    changed = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))
    projected = next(
        claim
        for claim in changed.document.to_value()["existing_claims"]
        if claim["claim_id"] == claim_id
    )

    assert changed.document.content_sha256 != original.document.content_sha256
    assert projected["claim"] == "Changed semantic strategy claim."


def test_starter_context_rejects_unknown_raw_claim_fields(tmp_path: Path) -> None:
    # Break caught: new upstream fields were silently omitted and therefore
    # could carry digest-invisible semantic authority.
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0]["unknown_semantic_field"] = (
        "hidden authority"
    )

    with pytest.raises(ValueError, match="starter_context_claim_schema_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_ignores_known_claim_transport_timestamp(
    tmp_path: Path,
) -> None:
    # Break caught: a known retrieval timestamp is transport provenance, not
    # strategy authority, and must remain outside canonical digest material.
    snapshot = audited_request(tmp_path, "ShadowPriest").snapshot
    original = build_starter_context(snapshot)
    preconfig = snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0]["retrieved_at"] = (
        "2099-12-31T23:59:59Z"
    )

    changed = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))

    assert changed.document.canonical_json == original.document.canonical_json


@pytest.mark.parametrize(
    "claim_text",
    [
        None,
        42,
        "",
        "   ",
        "x" * 4097,
        "C:\\private\\claim.txt",
        "/private/claim.txt",
        "<html>raw semantic claim</html>",
        "2026-08-19T12:00:00Z",
    ],
)
def test_starter_context_rejects_malformed_or_transport_claim_text(
    tmp_path: Path,
    claim_text: object,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0]["claim"] = claim_text

    with pytest.raises(ValueError, match="starter_context_claim_text_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("claim", "semantic <b", "starter_context_claim_text_invalid"),
        ("claim", "semantic >", "starter_context_claim_text_invalid"),
        (
            "evidence_text_short",
            "evidence <b",
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_text_short",
            "2099-12-31T23:59:59Z",
            "starter_context_claim_semantics_invalid",
        ),
        ("claim", "<b>unpaired presentation", "starter_context_claim_text_invalid"),
        (
            "evidence_text_short",
            "unpaired presentation</i>",
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_text_short",
            "2099-12-31",
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_text_short",
            "PT15M",
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_text_short",
            "x" * 4097,
            "starter_context_claim_semantics_invalid",
        ),
    ],
)
def test_starter_context_rejects_open_markup_or_transport_claim_prose(
    tmp_path: Path,
    field: str,
    value: str,
    error: str,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    preconfig["guide_claim_bundle"]["claims"][0][field] = value

    with pytest.raises(ValueError, match=error):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("family", "mutate", "error"),
    [
        (
            "claim_prose_posix_path_token",
            lambda value: _claim_with_field(value, "claim").__setitem__(
                "claim", "Use /private/runtime/GlobalValues.json"
            ),
            "starter_context_claim_text_invalid",
        ),
        (
            "claim_prose_windows_path_token",
            lambda value: _claim_with_field(value, "claim").__setitem__(
                "claim", "Use C:/private/runtime/GlobalValues.json"
            ),
            "starter_context_claim_text_invalid",
        ),
        (
            "claim_prose_windows_backslash_path_token",
            lambda value: _claim_with_field(value, "claim").__setitem__(
                "claim", "Use C:\\private\\runtime\\GlobalValues.json"
            ),
            "starter_context_claim_text_invalid",
        ),
        (
            "claim_prose_unc_path_token",
            lambda value: _claim_with_field(value, "claim").__setitem__(
                "claim", "Use \\\\private-server\\capture\\guide.html"
            ),
            "starter_context_claim_text_invalid",
        ),
        (
            "evidence_prose_posix_path_token",
            lambda value: _claim_with_field(
                value, "evidence_text_short"
            ).__setitem__(
                "evidence_text_short", "Evidence from /private/capture.html"
            ),
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_prose_uri_token",
            lambda value: _claim_with_field(
                value, "evidence_text_short"
            ).__setitem__(
                "evidence_text_short", "Source https://example.com/raw-guide"
            ),
            "starter_context_claim_semantics_invalid",
        ),
        (
            "evidence_prose_non_https_uri_scheme",
            lambda value: _claim_with_field(
                value, "evidence_text_short"
            ).__setitem__(
                "evidence_text_short", "Source urn:hearthstone:raw-guide"
            ),
            "starter_context_claim_semantics_invalid",
        ),
        (
            "claim_authority_transport_scalar",
            lambda value: _claim_with_field(value, "support_status").__setitem__(
                "support_status", "2099-12-31T23:59:59Z"
            ),
            "starter_context_claim_semantics_invalid",
        ),
        (
            "claim_source_alias_open_markup",
            lambda value: _claim_with_field(value, "source_family").update(
                {"source": "source <b", "source_family": "source <b"}
            ),
            "starter_context_claim_semantics_invalid",
        ),
        (
            "source_evidence_title_open_markup",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("source_title", "Captured <b"),
            "starter_context_source_evidence_invalid",
        ),
    ],
)
def test_starter_context_rejects_reviewed_unsafe_emitted_scalars(
    tmp_path: Path,
    family: str,
    mutate: Callable[[dict[str, Any]], None],
    error: str,
) -> None:
    # Break caught: context scalar validation was start-anchored and split
    # across projections, so unsafe tokens survived in otherwise valid prose
    # and semantic fields.  ``family`` makes each emitted family explicit.
    del family
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(ValueError, match=error):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    "field",
    [
        "claim_confidence",
        "deck_match_scope",
        "freshness_status",
        "source_confidence",
        "source_family",
        "source_lane",
        "source_type",
        "source_visibility",
        "specificity_status",
        "scope",
        "support_status",
        "trust_ceiling",
    ],
)
def test_starter_context_rejects_transport_values_in_every_claim_authority_token(
    tmp_path: Path,
    field: str,
) -> None:
    # Break caught: all projected claim-authority scalars shared the permissive
    # semantic-text path, so an ISO transport value could masquerade as any of
    # these structured authority tokens.
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = _claim_with_field(preconfig, field)
    claim[field] = "2099-12-31T23:59:59Z"
    if field == "source_family":
        claim["source"] = claim[field]

    with pytest.raises(ValueError, match="starter_context_claim_semantics_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("family", "mutate"),
    [
        (
            "claim_id_reference",
            lambda value: _set_claim_id(
                _claim_with_field(value, "claim_id"), "2099-12-31"
            ),
        ),
        (
            "archetype_token",
            lambda value: _claim_with_field(value, "archetype").__setitem__(
                "archetype", "2099-12-31"
            ),
        ),
        (
            "stance_token",
            lambda value: _claim_with_field(value, "stance").__setitem__(
                "stance", "2099-12-31"
            ),
        ),
        (
            "mechanic_token",
            lambda value: _claim_with_field(value, "mechanic").__setitem__(
                "mechanic", "2099-12-31"
            ),
        ),
        (
            "mechanic_family_token",
            lambda value: _claim_with_field(value, "mechanic_family").__setitem__(
                "mechanic_family", "2099-12-31"
            ),
        ),
        (
            "runtime_value_scalar",
            lambda value: _claim_with_field(value, "runtime_value").__setitem__(
                "runtime_value", "2099-12-31"
            ),
        ),
        (
            "identity_signal_field_token",
            lambda value: _first_identity_signal(value).__setitem__(
                "field", "2099-12-31"
            ),
        ),
        (
            "identity_signal_origin_token",
            lambda value: _first_identity_signal(value).__setitem__(
                "origin", "2099-12-31"
            ),
        ),
        (
            "identity_signal_value_token",
            lambda value: _first_identity_signal(value).__setitem__(
                "value", "2099-12-31"
            ),
        ),
        (
            "semantic_qualifier_scalar",
            lambda value: _claim_with_field(
                value, "semantic_qualifiers"
            )["semantic_qualifiers"].__setitem__("timing", "2099-12-31"),
        ),
        (
            "semantic_qualifier_list",
            lambda value: _claim_with_field(
                value, "semantic_qualifiers"
            )["semantic_qualifiers"].__setitem__(
                "state_requirements", ["2099-12-31"]
            ),
        ),
    ],
)
def test_starter_context_rejects_transport_values_in_projected_semantic_families(
    tmp_path: Path,
    family: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    del family
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(ValueError, match="starter_context_claim_semantics_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    ("family", "mutate", "error"),
    [
        (
            "source_evidence_family_token",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("source_family", "2099-12-31"),
            "starter_context_source_evidence_invalid",
        ),
        (
            "source_evidence_id_reference",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("source_id", "2099-12-31"),
            "starter_context_source_evidence_invalid",
        ),
        (
            "source_evidence_reference",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("source_ref", "2099-12-31"),
            "starter_context_source_evidence_invalid",
        ),
        (
            "source_evidence_missing_key_reference_list",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("missing_source_keys", ["2099-12-31"]),
            "starter_context_source_evidence_invalid",
        ),
        (
            "source_evidence_title_prose",
            lambda value: value["guide_claim_bundle"]["source_evidence_index"][
                0
            ].__setitem__("source_title", "2099-12-31"),
            "starter_context_source_evidence_invalid",
        ),
        (
            "deck_match_candidate_reference_list",
            lambda value: _claim_with_field(value, "deck_match")["deck_match"][
                "exact_deck_evidence"
            ].__setitem__("candidate_deck_code_hashes", ["2099-12-31"]),
            "starter_context_claim_deck_match_invalid",
        ),
        (
            "evidence_gap_reference",
            lambda value: value["identity_gap_report"][
                "missing_identity_fields"
            ].append("2099-12-31"),
            "starter_context_source_evidence_invalid",
        ),
    ],
)
def test_starter_context_rejects_transport_values_in_source_reference_families(
    tmp_path: Path,
    family: str,
    mutate: Callable[[dict[str, Any]], None],
    error: str,
) -> None:
    del family
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    mutate(preconfig)

    with pytest.raises(ValueError, match=error):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "PT15M",
        "15ms",
        "23:59:59Z",
        "https://example.com/raw-guide",
        "token\x00value",
        "token\rvalue",
        "token\x1fvalue",
        "x" * 4097,
    ],
)
def test_starter_context_rejects_unsafe_or_oversized_structured_scalars(
    tmp_path: Path,
    unsafe_value: str,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    _claim_with_field(preconfig, "support_status")["support_status"] = unsafe_value

    with pytest.raises(ValueError, match="starter_context_claim_semantics_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_shadowpriest_context_safe_scalar_layer_preserves_canonical_projection(
    tmp_path: Path,
) -> None:
    # Break caught: safety validation must not rewrite already canonical game
    # semantics while closing unsafe alternate inputs.
    context = build_starter_context(
        audited_request(tmp_path, "ShadowPriest").snapshot
    )
    value = context.document.to_value()

    assert context.document.content_sha256 == (
        "sha256:1b87f3279050212e80b483cdd66bfc31adaaee5f164dc5b65d8ac021c10887dc"
    )
    assert len(context.document.canonical_json) == 72971
    assert len(value["existing_claims"]) == 42
    assert len(value["source_evidence"]["rows"]) == 17
    assert value["source_evidence"]["gaps"] == [
        {
            "gap_kind": "missing_deck_identity",
            "value": "starting_hero_power_id",
        }
    ]


def test_starter_context_keeps_public_https_in_dedicated_source_references(
    tmp_path: Path,
) -> None:
    # Break caught: generic path-token checks must not narrow the existing
    # public-HTTPS authority for dedicated source_url/source-reference fields.
    public_url = "https://example.com/guide?next=/cards"
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    evidence = preconfig["guide_claim_bundle"]["source_evidence_index"][0]
    evidence["source_url"] = public_url
    evidence["source_ref"] = public_url
    claim = _claim_with_field(preconfig, "source_refs")
    claim["source_refs"] = [public_url]

    value = build_starter_context(
        PackageResolutionSnapshot.from_preconfig(preconfig)
    ).document.to_value()

    assert any(
        row.get("source_url") == public_url and row["source_ref"] == public_url
        for row in value["source_evidence"]["rows"]
    )
    projected_claim = next(
        row
        for row in value["existing_claims"]
        if row["claim_id"] == claim["claim_id"]
    )
    assert projected_claim["source_refs"] == [public_url]


def test_starter_context_normalizes_legitimate_claim_prose_and_paired_tags(
    tmp_path: Path,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = preconfig["guide_claim_bundle"]["claims"][0]
    claim["claim"] = (
        "  Give a 1/1 minion +1/+1; use <b>Battlecry</b> with <i>tempo</i>.  "
    )
    claim["evidence_text_short"] = (
        "  Legitimate prose with <b><i>nested emphasis</i></b>.  "
    )

    context = build_starter_context(
        PackageResolutionSnapshot.from_preconfig(preconfig)
    ).document.to_value()
    projected = next(
        row for row in context["existing_claims"] if row["claim_id"] == claim["claim_id"]
    )

    assert projected["claim"] == (
        "Give a 1/1 minion +1/+1; use Battlecry with tempo."
    )
    assert projected["evidence_text_short"] == (
        "Legitimate prose with nested emphasis."
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda claim: claim.__setitem__("claim_type", "targeting"),
        lambda claim: claim.__setitem__("condition", "opponent_class=PRIEST"),
    ],
)
def test_starter_context_rejects_inconsistent_legacy_claim_aliases(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = preconfig["guide_claim_bundle"]["claims"][0]
    mutate(claim)

    with pytest.raises(ValueError, match="starter_context_claim_alias_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda evidence: evidence.__setitem__(
            "matched_deck_fingerprint", "f" * 64
        ),
        lambda evidence: evidence.__setitem__("candidate_count", 2),
        lambda evidence: evidence.__setitem__("decoded_candidate_count", 0),
        lambda evidence: evidence.__setitem__("candidate_count", True),
        lambda evidence: evidence.update(
            {"matched": False, "matched_deck_fingerprint": "f" * 64}
        ),
    ],
)
def test_starter_context_cross_binds_exact_deck_match_authority(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = next(
        row
        for row in preconfig["guide_claim_bundle"]["claims"]
        if row.get("deck_match")
    )
    mutate(claim["deck_match"]["exact_deck_evidence"])

    with pytest.raises(ValueError, match="starter_context_claim_deck_match_invalid"):
        build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))


def test_starter_context_closes_consistent_unmatched_deck_evidence(
    tmp_path: Path,
) -> None:
    preconfig = audited_request(
        tmp_path,
        "ShadowPriest",
    ).snapshot.general_preconfig.to_value()
    claim = next(
        row
        for row in preconfig["guide_claim_bundle"]["claims"]
        if row.get("deck_match")
    )
    claim["deck_match"]["exact_deck_evidence"] = {
        "candidate_count": 0,
        "candidate_deck_code_hashes": [],
        "decoded_candidate_count": 0,
        "matched": False,
        "matched_deck_fingerprint": None,
    }

    context = build_starter_context(PackageResolutionSnapshot.from_preconfig(preconfig))
    projected = next(
        row
        for row in context.document.to_value()["existing_claims"]
        if row["claim_id"] == claim["claim_id"]
    )

    assert projected["deck_match"]["exact_deck_evidence"]["matched"] is False
    assert projected["deck_match"]["target_deck_code_sha256"] == (
        preconfig["deck_identity"]["deck_code_hash"]
    )


def _assert_no_volatile_or_raw_source_fields(value: object) -> None:
    forbidden_fields = {
        "captured_at",
        "fetch_duration",
        "fetch_duration_ms",
        "html",
        "path",
        "raw_html",
        "retrieved_at",
    }
    if isinstance(value, dict):
        assert not (set(value) & forbidden_fields)
        for item in value.values():
            _assert_no_volatile_or_raw_source_fields(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_volatile_or_raw_source_fields(item)
    elif isinstance(value, str):
        assert "<html" not in value.lower()


def _claim_with_field(
    preconfig: dict[str, Any],
    field: str,
) -> dict[str, Any]:
    return next(
        claim
        for claim in preconfig["guide_claim_bundle"]["claims"]
        if field in claim
    )


def _set_claim_id(claim: dict[str, Any], claim_id: str) -> None:
    claim["claim_id"] = claim_id
    claim["source_claim_ids"] = [claim_id]


def _first_identity_signal(preconfig: dict[str, Any]) -> dict[str, Any]:
    return _claim_with_field(preconfig, "source_identity_signals")[
        "source_identity_signals"
    ][0]
