import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from hsconfig.cli import main
from hsconfig.deck_identity import build_deck_identity
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import read_json, write_json
from hsconfig.source_autopilot import build_source_autopilot_bundle
from hsconfig.source_document_model import qualify_source_claim
from tests.helpers.fixture_prepare import (
    load_archetype_matrix,
    prepare_fixture_deck,
    read_json as read_fixture_json,
)
from tests.helpers.live_acquisition import acquire_live_test_provenance


DECKS = {
    "ShadowPriest": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    "MechPala": "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
    "BigShaman": "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
}

SOURCE_SEARCH_MATRIX = Path("tests/fixtures/source_search_11_deck_matrix.json")

EXPECTED_REPRESENTATIVE_SOURCE_STATUS = {
    "ShadowPriest": "SOURCE_BACKED_STRONG",
    "MechPala": "SOURCE_BACKED_STRONG",
    "PirateRogue": "SOURCE_BACKED_STRONG",
    "BigShaman": "SOURCE_BACKED_STRONG",
    "Boarlock": "SOURCE_BACKED_PARTIAL",
    "ImbueMage": "SOURCE_BACKED_STRONG",
    "TreantDruid": "SOURCE_BACKED_PARTIAL",
    "Discolock": "SOURCE_BACKED_PARTIAL",
    "PirateDH": "SOURCE_BACKED_PARTIAL",
    "CtAPaladin": "SOURCE_BACKED_PARTIAL",
    "Kingslayer": "SOURCE_BACKED_PARTIAL",
}

EXPECTED_EVIDENCE_STATUS = {
    deck_name: "SOURCE_BACKED_PARTIAL"
    for deck_name in EXPECTED_REPRESENTATIVE_SOURCE_STATUS
}

PARTIAL_OR_CONDITIONAL_STATUSES = {
    "SOURCE_BACKED_PARTIAL",
    "SOURCE_BACKED_PARTIAL_UNLESS_EXACT_GUIDE_MATCHED",
    "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH",
}

NON_STRONG_SOURCE_RECORD_STRENGTHS = {"partial", "diagnostic_only"}

PLACEHOLDER_SOURCE_ACTIONS = {
    "add_card_specific_source_claim",
    "add_current_deck_guide_or_mulligan_guide",
    "add_explicit_mulligan_source",
    "close_first_missing_chain",
}


def prepared_mulligan_plan(
    tmp_path: Path,
    deck_name: str,
) -> dict[str, Any]:
    deck = next(
        row for row in load_archetype_matrix()
        if row["deck_name"] == deck_name
    )
    prepared = prepare_fixture_deck(tmp_path / deck_name, deck)
    assert prepared["exit_code"] == 0
    return read_json(
        prepared["out"] / "reports" / "mulligan_plan_report.json"
    )


def hold_cards(plan: Mapping[str, Any]) -> set[str]:
    return {
        str(row["card"])
        for row in plan["rules"]
        if row.get("action") == "hold"
        and row.get("selector_kind", "single_card") != "wildcard"
    }


def test_imbuemage_fir_911_physical_mulligan_parity_uses_surface_ledger(
    tmp_path: Path,
) -> None:
    deck = next(row for row in load_archetype_matrix() if row["deck_name"] == "ImbueMage")
    prepared = prepare_fixture_deck(tmp_path / "ImbueMage", deck)
    assert prepared["exit_code"] == 0

    reports = prepared["out"] / "reports"
    deck_dir = next((prepared["out"] / "CustomConfig").iterdir())
    mulligan = read_json(deck_dir / "Mulligan.json")
    readiness = read_json(reports / "per_card_config_readiness_report.json")
    ledger = read_json(reports / "runtime_surface_ledger.json")
    explainability = read_json(reports / "source_to_runtime_explainability.json")
    operator = read_json(reports / "operator_summary.json")
    compiled_holds = {
        str(row["mulligan"])
        for row in mulligan["Mulligan"]["values"]
        if row.get("value") == "hold"
    }

    assert "FIR_911" in compiled_holds
    assert readiness["cards"]["FIR_911"]["runtime_surfaces"] == ["Mulligan.json"]
    assert readiness["cards"]["FIR_911"]["readiness_lane"] == "mulligan_only"
    assert ledger["cards"]["FIR_911"]["runtime_surfaces"] == ["Mulligan.json"]
    assert operator["surface_ledger_sha256"] == readiness["surface_ledger_sha256"]
    assert readiness["surface_ledger_sha256"] == explainability["surface_ledger_sha256"]


def test_shadowpriest_linked_hero_power_is_separate_from_darkbishop_source_record(
    tmp_path: Path,
) -> None:
    deck = next(row for row in load_archetype_matrix() if row["deck_name"] == "ShadowPriest")
    prepared = prepare_fixture_deck(tmp_path / "ShadowPriest", deck)
    assert prepared["exit_code"] == 0

    reports = prepared["out"] / "reports"
    ledger = read_json(reports / "runtime_surface_ledger.json")
    readiness = read_json(reports / "per_card_config_readiness_report.json")

    assert ledger["cards"]["SW_448"]["runtime_surfaces"] == []
    assert ledger["linked_runtime_entities"]["EX1_625t"]["source_card_id"] == "SW_448"
    assert ledger["linked_runtime_entities"]["EX1_625t"]["runtime_card_id"] == "EX1_625t"
    assert ledger["linked_runtime_entities"]["EX1_625t"]["runtime_emitted"] is True
    assert readiness["cards"]["SW_448"]["readiness_lane"] == "linked_runtime_source"


def test_audited_cards_emit_no_semantically_invalid_runtime_block(
    tmp_path: Path,
) -> None:
    cases_by_deck = {
        "CtAPaladin": {
            "WW_336": "BeforePlayCardBonus",
            "WW_051": "BeforePlayCardBonus",
            "CATA_479": "BeforePlayCardBonus",
        },
        "PirateRogue": {
            "CS2_073": "BeforePlayCardBonus",
            "DMF_519": "BeforeBattlecryTargetBonus",
            "TTN_922": "BeforePlayCardBonus",
            "NX2_006": "BeforePhysicalAttackBonus",
        },
        "BigShaman": {
            "GVG_029": "BeforePlayCardBonus",
            "CS2_038": "BeforeBattlecryTargetBonus",
            "WON_335": "BeforeBattlecryTargetBonus",
            "TOY_877": "OnBoardBonus",
        },
        "TreantDruid": {
            "JAM_028": "BeforePlayCardBonus",
            "TTN_954": "OnBoardBonus",
        },
        "Kingslayer": {
            "VAC_938": "BeforePhysicalAttackBonus",
            "VAC_701": "BeforePhysicalAttackBonus",
        },
    }
    decks = {
        row["deck_name"]: row
        for row in load_archetype_matrix()
        if row["deck_name"] in cases_by_deck
    }

    for deck_name, expected in cases_by_deck.items():
        prepared = prepare_fixture_deck(tmp_path / deck_name, decks[deck_name])
        assert prepared["exit_code"] == 0
        plan = read_json(
            prepared["out"] / "reports" / "card_behavior_plan_report.json"
        )
        readiness = read_json(
            prepared["out"] / "reports" / "per_card_config_readiness_report.json"
        )
        source_claims = read_json(
            prepared["out"] / "reports" / "guide_claim_bundle.json"
        )["claims"]
        custom_config = next((prepared["out"] / "CustomConfig").iterdir())
        for card_id, invalid_block in expected.items():
            assert not any(
                row.get("card_id") == card_id
                and row.get("behavior_block") == invalid_block
                for row in plan["rows"]
            )
            assert invalid_block not in read_json(custom_config / f"{card_id}.json")

        exact_fixture_expectations = {
            ("BigShaman", "CS2_038"): (
                "spell_cannot_use_battlecry_target",
                "semantic_surface_not_expressible",
            ),
            ("BigShaman", "WON_335"): (
                "spell_cannot_use_battlecry_target",
                "semantic_surface_not_expressible",
            ),
            ("TreantDruid", "JAM_028"): (
                "health_cost_condition_not_encoded",
                "needs_condition_lowering",
            ),
        }
        for (expected_deck, card_id), (
            suppression_reason,
            missing_link,
        ) in exact_fixture_expectations.items():
            if deck_name != expected_deck:
                continue
            suppression = next(
                row
                for row in plan["suppressed"]
                if card_id in row.get("cards", [])
                and row.get("reason") == suppression_reason
            )
            original_claim = next(
                row
                for row in source_claims
                if row.get("claim_id") == suppression["claim_id"]
            )
            assert suppression["source_claim_ids"] == original_claim["source_claim_ids"]
            assert suppression["source_refs"] == original_claim["source_refs"]
            assert (
                suppression["acquisition_provenance"]
                == original_claim["acquisition_provenance"]
            )
            assert readiness["cards"][card_id]["first_missing_link"] == missing_link


def test_discolock_emits_no_coverage_or_owner_mismatched_runtime_rows(
    tmp_path: Path,
) -> None:
    deck = next(
        row for row in load_archetype_matrix()
        if row["deck_name"] == "Discolock"
    )
    prepared = prepare_fixture_deck(tmp_path / "Discolock", deck)
    assert prepared["exit_code"] == 0

    custom_config = next((prepared["out"] / "CustomConfig").iterdir())
    payloads = {
        path.stem: read_json(path)
        for path in custom_config.glob("*.json")
        if path.name not in {"GlobalValues.json", "Mulligan.json", "Combo.json"}
    }

    assert all("InHandPlayPriority" not in payload for payload in payloads.values())
    for card_id in ("CATA_490", "TLC_603", "VAC_940"):
        assert "BeforeBattlecryTargetBonus" not in payloads[card_id]
    for card_id in ("RLK_532", "WON_098"):
        assert "BeforePlayCardBonus" not in payloads[card_id]


@pytest.mark.parametrize("deck_name", ["ImbueMage", "Boarlock"])
def test_baseline_only_globalvalues_authority_emits_no_hidden_hero_power_overlay(
    tmp_path: Path,
    deck_name: str,
) -> None:
    deck = next(
        row for row in load_archetype_matrix()
        if row["deck_name"] == deck_name
    )
    prepared = prepare_fixture_deck(tmp_path / deck_name, deck)
    assert prepared["exit_code"] == 0

    reports = prepared["out"] / "reports"
    authority = read_json(reports / "global_values_authority_matrix.json")
    profile = read_json(reports / "globalvalues_profile.json")
    globalvalues = read_json(
        next((prepared["out"] / "CustomConfig").rglob("GlobalValues.json"))
    )

    assert {
        row["key"] for row in authority["allowed_step1_overlays"]
    } == {"baseline"}
    assert "MyHeroPowerValue" not in globalvalues
    assert profile["generated_overlay_keys"] == []
    assert profile["expected_overlay_keys"] == []
    assert profile["authority_parity"] == {
        "authorized_overlay_keys": [],
        "emitted_overlay_keys": [],
        "status": "matched",
    }


def test_policy_mulligan_honors_named_source_and_role_vetoes(
    tmp_path: Path,
) -> None:
    boarlock_plan = prepared_mulligan_plan(tmp_path, "Boarlock")
    kingslayer_plan = prepared_mulligan_plan(tmp_path, "Kingslayer")
    mechpala_plan = prepared_mulligan_plan(tmp_path, "MechPala")

    assert "WW_092" not in hold_cards(boarlock_plan)
    assert "DEEP_014" not in hold_cards(kingslayer_plan)
    assert "TOY_330" not in hold_cards(mechpala_plan)

    expected_vetoes = (
        (boarlock_plan, "WW_092", "explicit_source_gap_requires_resolution"),
        (kingslayer_plan, "DEEP_014", "explicit_source_gap_requires_resolution"),
        (mechpala_plan, "TOY_330", "sideboard_owner_not_curve_anchor"),
    )
    for plan, card_id, reason in expected_vetoes:
        assert {
            "card": card_id,
            "reason": reason,
            "policy_lane": "source_veto",
            "source_type": "policy_backed_autonomous_mulligan",
        } in plan["suppressed_rules"]

    assert any(
        row.get("card") == "WW_092"
        and row.get("reason") == "claim_not_runtime_lowerable"
        and row.get("claim_id") in row.get("source_claim_ids", [])
        and row.get("source_type") == "source_claim"
        and row.get("source_url")
        for row in boarlock_plan["suppressed_rules"]
    )
    assert any(
        row.get("card") == "DEEP_014"
        and row.get("reason") == "claim_not_runtime_lowerable"
        and row.get("claim_id") in row.get("source_claim_ids", [])
        and row.get("source_type") == "source_claim"
        and row.get("source_url")
        for row in kingslayer_plan["suppressed_rules"]
    )


@pytest.mark.parametrize("deck_name,deck_code", DECKS.items())
def test_multideck_source_backed_prepare(tmp_path: Path, deck_name: str, deck_code: str):
    fixture = json.loads(
        Path("tests/fixtures/source_documents_multiarchetype.json").read_text(
            encoding="utf-8"
        )
    )
    source_path = tmp_path / f"{deck_name}_sources.json"
    write_json(source_path, fixture[deck_name])
    out = tmp_path / deck_name

    code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            str(source_path),
            "--json",
        ]
    )

    assert code == 0
    summary = read_json(out / "reports" / "operator_summary.json")
    assert summary["technical_status"] == "VALID_PACKAGE"
    if deck_name == "MechPala":
        reports = out / "reports"
        deck_identity = read_json(reports / "deck_identity.json")
        metadata = read_json(reports / "semantic_enrichment_report.json")
        readiness = read_json(reports / "per_card_config_readiness_report.json")
        surface_ledger = read_json(reports / "runtime_surface_ledger.json")
        coverage = read_json(reports / "claim_coverage_report.json")
        explainability = read_json(reports / "source_to_runtime_explainability.json")
        roles = read_json(reports / "research" / "card_role_map.json")
        module_ids = {"TOY_330t95", "TOY_330t98", "TOY_330t11"}

        assert deck_identity["card_count_total"] == 30
        assert deck_identity["sideboard_count"] == 3
        assert coverage["total_cards"] == len(deck_identity["cards"])
        assert readiness["summary"]["total_cards"] == len(deck_identity["cards"])
        assert summary["surface_ledger_sha256"] == readiness["surface_ledger_sha256"]
        assert readiness["surface_ledger_sha256"] == explainability["surface_ledger_sha256"]
        assert surface_ledger["surface_ledger_sha256"] == readiness["surface_ledger_sha256"]
        metadata_by_card = {row["card_id"]: row for row in metadata["cards"]}
        explainability_by_card = {
            row["card_id"]: row for row in explainability["card_rows"]
        }
        operator_attention_by_card = {
            row["card_id"]: row for row in explainability["operator_attention"]
        }
        assert explainability["summary"]["cards_with_first_missing_link"] == sum(
            row.get("first_missing_link") not in {None, "", "none", "closed"}
            for row in explainability["card_rows"]
        )
        assert module_ids <= set(metadata_by_card)
        assert module_ids <= set(readiness["cards"])
        assert module_ids <= set(explainability_by_card)
        for card_id in module_ids:
            assert metadata_by_card[card_id]["deck_zone"] == "sideboard"
            assert metadata_by_card[card_id]["sideboard_owner_card_id"] == "TOY_330"
            assert metadata_by_card[card_id]["runtime_eligible"] is False
            assert readiness["cards"][card_id]["deck_zone"] == "sideboard"
            assert readiness["cards"][card_id]["runtime_surfaces"] == []
            assert surface_ledger["cards"][card_id]["runtime_surfaces"] == []
            assert surface_ledger["cards"][card_id]["deck_zone"] == "sideboard"
            assert readiness["cards"][card_id]["readiness_lane"] == "report_only_supported"
            assert readiness["cards"][card_id]["first_missing_link"] == "none"
            assert explainability_by_card[card_id]["deck_zone"] == "sideboard"
            assert explainability_by_card[card_id]["sideboard_owner_card_id"] == "TOY_330"
            assert explainability_by_card[card_id]["runtime_eligible"] is False
            assert explainability_by_card[card_id]["runtime_surfaces"] == []
            assert (
                explainability_by_card[card_id]["readiness_lane"]
                == "report_only_supported"
            )
            assert explainability_by_card[card_id]["first_missing_link"] == "none"
            assert explainability_by_card[card_id]["closure_lane"] == "report_only"
            assert explainability_by_card[card_id]["runtime_lowering_status"] == (
                "report_only_supported"
            )
            assert explainability_by_card[card_id]["next_source_action"] == "none"
            assert explainability_by_card[card_id]["first_missing_source_action"] == (
                "none"
            )
            assert explainability_by_card[card_id]["closure"]["lane"] == "report_only"
            assert (
                explainability_by_card[card_id]["closure"]["default_only_risk"]
                is False
            )
            attention = operator_attention_by_card[card_id]
            assert attention["status"] == "report_only"
            assert attention["closure_lane"] == "report_only"
            assert attention["default_only_risk"] is False
            assert attention["first_missing_link"] == "none"
            assert attention["next_source_action"] == "none"

        assert "sideboard_owner" in roles["TOY_330"]["roles"]
        assert not module_ids & {
            path.stem for path in (out / "CustomConfig").rglob("*.json")
        }
        mulligan = read_json(next((out / "CustomConfig").rglob("Mulligan.json")))
        assert all(
            row.get("mulligan") != "TOY_330"
            for row in mulligan["Mulligan"]["values"]
        )
    if deck_name == "ShadowPriest":
        assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
        assert summary["guide_strength_summary"]["cards_needing_runtime_surface"] == 0
        assert summary["guide_strength_summary"]["cards_needing_mechanic_lowering"] == 0
        assert summary["semantic_blockers"]
    else:
        assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
        assert summary["guide_strength_summary"]["cards_needing_runtime_surface"] > 0
        assert summary["semantic_blockers"]


def _source_search_records_by_deck() -> dict[str, list[dict]]:
    payload = read_fixture_json(SOURCE_SEARCH_MATRIX)
    assert payload["schema_version"] == 1
    records_by_deck = payload["records_by_deck"]
    assert isinstance(records_by_deck, dict)
    return records_by_deck


def _deck_identity_for(deck: dict) -> dict:
    decoded = decode_deck_code(deck["deck_code"])
    return build_deck_identity(
        deck_name=deck["deck_name"],
        deck_code=deck["deck_code"],
        cards=decoded["cards"],
        hero_dbf_id=decoded["hero_dbf_id"],
        format=decoded["format"],
        sideboards=decoded["sideboards"],
    )


def _source_claims(records: list[dict]) -> list[dict]:
    return [
        claim
        for record in records
        for claim in record.get("claims", [])
        if isinstance(claim, dict)
    ]


def _source_urls_from_records(records: list[dict]) -> list[str]:
    return sorted(str(record["source_url"]) for record in records)


def _source_urls_from_documents(documents: list[dict]) -> list[str]:
    return sorted(str(document["source_url"]) for document in documents)


def _duplicate_json_keys(path: Path) -> list[str]:
    duplicates: list[str] = []

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        seen = set()
        for key, _value in pairs:
            if key in seen:
                duplicates.append(key)
            seen.add(key)
        return dict(pairs)

    json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
    return duplicates


def _source_search_bundle_for_deck(deck: dict) -> dict:
    source_search_records = _source_search_records_by_deck()
    return build_source_autopilot_bundle(
        deck_name=deck["deck_name"],
        deck_identity=_deck_identity_for(deck),
        source_search_records=source_search_records[deck["deck_name"]],
        current_date="2026-07-15",
    )


def _exact_current_record(record: dict, deck_identity: dict) -> dict:
    card_ids = [str(card["card_id"]) for card in deck_identity["cards"]]
    return {
        **record,
        "acquisition_provenance": acquire_live_test_provenance(),
        "source_record_strength": "candidate_strong",
        "deck_match_scope": "exact_deck_matched",
        "deck_match": {
            **dict(record.get("deck_match", {})),
            "matched_card_ids": card_ids,
            "matched_card_count": len(card_ids),
            "unique_deck_card_count": len(card_ids),
            "card_overlap_ratio": 1.0,
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": deck_identity["deck_fingerprint"],
                "candidate_deck_code_hashes": ["sha256:multideck-source"],
            },
        },
    }


def _write_source_search_documents(tmp_path: Path, deck: dict, bundle: dict) -> Path:
    source_dir = tmp_path / "source_autopilot" / deck["deck_name"]
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source_documents.json"
    write_json(source_path, bundle["source_documents_payload"])
    return source_path


def _prepare_deck_with_source_documents(
    tmp_path: Path,
    deck: dict,
    source_documents_json: Path,
) -> dict:
    out = tmp_path / deck["deck_name"]
    code = main(
        [
            "prepare",
            "--deck-name",
            str(deck["deck_name"]),
            "--deck-code",
            str(deck["deck_code"]),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            str(source_documents_json),
            "--json",
        ]
    )

    reports = out / "reports"
    operator = read_fixture_json(reports / "operator_summary.json")
    readiness = read_fixture_json(reports / "per_card_config_readiness_report.json")
    coverage = read_fixture_json(reports / "claim_coverage_report.json")
    source_gap = read_fixture_json(reports / "source_claim_gap_report.json")
    strong_promotion = read_fixture_json(reports / "strong_promotion_report.json")
    source_evidence_index = read_fixture_json(reports / "source_evidence_index.json")
    config_root = out / "CustomConfig"
    generated_files = sorted(path.name for path in config_root.rglob("*.json"))
    return {
        "exit_code": code,
        "out": out,
        "operator": operator,
        "readiness": readiness,
        "coverage": coverage,
        "source_gap": source_gap,
        "source_claim_gap_report": source_gap,
        "strong_promotion_report": strong_promotion,
        "source_evidence_index": source_evidence_index,
        "generated_files": generated_files,
    }


def build_representative_multideck_matrix(tmp_path: Path) -> list[dict]:
    source_search_records = _source_search_records_by_deck()
    results = []
    for deck in load_archetype_matrix():
        bundle = _source_search_bundle_for_deck(deck)
        source_documents_json = _write_source_search_documents(tmp_path, deck, bundle)
        prepared = _prepare_deck_with_source_documents(
            tmp_path,
            deck,
            source_documents_json,
        )
        operator = prepared["operator"]
        documents = bundle["source_documents_payload"]["source_documents"]
        deck_match_scopes = {
            str(row.get("deck_match_scope"))
            for document in documents
            for row in [document, *document.get("claims", [])]
            if row.get("deck_match_scope")
        }
        results.append(
            {
                "deck_name": deck["deck_name"],
                "technical_status": operator["technical_status"],
                "operator_summary": operator,
                "runtime_apply_allowed": operator["runtime_apply_allowed"],
                "semantic_status": operator["semantic_status"],
                "default_only_runtime_surfaces": operator["default_only_runtime_surfaces"],
                "deck_match_scopes": deck_match_scopes,
                "source_search_records": source_search_records[deck["deck_name"]],
                "source_search_urls": _source_urls_from_records(
                    source_search_records[deck["deck_name"]]
                ),
                "source_documents_json": source_documents_json,
                "source_document_urls": _source_urls_from_documents(documents),
                "prepared_source_document_urls": sorted(
                    str(row["source_url"])
                    for row in prepared["source_evidence_index"]
                ),
                "source_autopilot_report": bundle["source_autopilot_report"],
                "strong_promotion_report": prepared["strong_promotion_report"],
                "promotion_ready": prepared["strong_promotion_report"][
                    "promotion_ready"
                ],
                "out": prepared["out"],
            }
        )
    return results


prepare_representative_source_matrix = build_representative_multideck_matrix


def test_source_search_11_deck_matrix_covers_representative_decks_with_honest_labels():
    records_by_deck = _source_search_records_by_deck()
    matrix_by_deck = {deck["deck_name"]: deck for deck in load_archetype_matrix()}

    assert set(records_by_deck) == set(EXPECTED_REPRESENTATIVE_SOURCE_STATUS)
    for deck_name, records in records_by_deck.items():
        expected = EXPECTED_EVIDENCE_STATUS[deck_name]
        assert records, deck_name
        assert _source_claims(records), deck_name

        for record in records:
            assert str(record["source_url"]).startswith("https://"), record
            assert record["source_visibility"] in {
                "full_text",
                "decklist_only",
                "snippet_only",
                "unknown",
            }, record
            assert record["source_record_strength"] in {
                "candidate_strong",
                "partial",
                "diagnostic_only",
            }, record
            if record["source_record_strength"] in NON_STRONG_SOURCE_RECORD_STRENGTHS:
                assert all(
                    claim.get("promotion_eligible") is False
                    for claim in record.get("claims", [])
                ), record

        bundle = build_source_autopilot_bundle(
            deck_name=deck_name,
            deck_identity=_deck_identity_for(matrix_by_deck[deck_name]),
            source_search_records=records,
            current_date="2026-07-15",
        )
        assert bundle["source_evidence_rows"], deck_name
        report = bundle["source_autopilot_report"]
        if expected == "SOURCE_BACKED_STRONG":
            documented_profile = matrix_by_deck[deck_name]["closure_profile"]
            assert (
                report["source_backed_strong_closure"]["closure_profile"]
                == documented_profile
            ), report
            assert report["strong_candidate"] is True, report
        if expected == "SOURCE_BACKED_PARTIAL":
            assert report["strong_candidate"] is False, report


def test_source_autopilot_blocks_non_promoting_partial_record_even_if_it_looks_exact():
    records_by_deck = _source_search_records_by_deck()
    matrix_by_deck = {deck["deck_name"]: deck for deck in load_archetype_matrix()}
    deck_identity = _deck_identity_for(matrix_by_deck["PirateRogue"])
    strong_record = _exact_current_record(
        records_by_deck["PirateRogue"][0], deck_identity
    )
    partial_record = {
        **strong_record,
        "source_record_strength": "partial",
        "promotion_eligible": False,
        "source_visibility": "full_text",
        "publication_year": 2026,
        "published_at": "2026-07-03T00:00:00Z",
        "deck_match_scope": "archetype_matched",
        "source_lane": "archetype_matched_public_guide",
        "deck_match": {"exact_deck_evidence": {"matched": False}},
        "claims": [
            {
                **claim,
                "promotion_eligible": False,
                "source_confidence": "high",
            }
            for claim in strong_record["claims"]
        ],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="PirateRogue",
        deck_identity=deck_identity,
        source_search_records=[partial_record],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    assert report["strong_candidate"] is False, report
    assert report["semantic_status"] != "SOURCE_BACKED_STRONG", report


def test_source_autopilot_drafted_documents_preserve_non_promoting_partial_metadata():
    records_by_deck = _source_search_records_by_deck()
    matrix_by_deck = {deck["deck_name"]: deck for deck in load_archetype_matrix()}
    deck_identity = _deck_identity_for(matrix_by_deck["PirateRogue"])
    strong_record = _exact_current_record(
        records_by_deck["PirateRogue"][0], deck_identity
    )
    partial_record = {
        **strong_record,
        "source_record_strength": "partial",
        "promotion_eligible": False,
        "source_visibility": "full_text",
        "publication_year": 2026,
        "published_at": "2026-07-03T00:00:00Z",
        "deck_match_scope": "archetype_matched",
        "source_lane": "archetype_matched_public_guide",
        "deck_match": {"exact_deck_evidence": {"matched": False}},
        "claims": [
            {
                **claim,
                "promotion_eligible": False,
                "source_confidence": "high",
            }
            for claim in strong_record["claims"]
        ],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="PirateRogue",
        deck_identity=deck_identity,
        source_search_records=[partial_record],
        current_date="2026-07-15",
    )

    claims = [
        claim
        for document in bundle["source_documents_payload"]["source_documents"]
        for claim in document.get("claims", [])
    ]
    assert claims
    assert {claim.get("promotion_eligible") for claim in claims} == {False}
    assert {claim.get("source_record_strength") for claim in claims} == {"partial"}
    qualified_claims = [
        qualify_source_claim({**document, **claim})
        for document in bundle["source_documents_payload"]["source_documents"]
        for claim in document.get("claims", [])
    ]
    assert {claim["promotion_eligible"] for claim in qualified_claims} == {False}
    assert {claim["strong_promotion_eligible"] for claim in qualified_claims} == {False}


def test_source_autopilot_non_promoting_partial_record_does_not_veto_separate_strong_record():
    records_by_deck = _source_search_records_by_deck()
    matrix_by_deck = {deck["deck_name"]: deck for deck in load_archetype_matrix()}
    deck_identity = _deck_identity_for(matrix_by_deck["PirateRogue"])
    strong_record = _exact_current_record(
        records_by_deck["PirateRogue"][0], deck_identity
    )
    partial_record = {
        **strong_record,
        "source_url": "https://example.invalid/partial-piraterogue-guide",
        "source_record_strength": "partial",
        "promotion_eligible": False,
        "source_visibility": "full_text",
        "publication_year": 2026,
        "published_at": "2026-07-03T00:00:00Z",
        "deck_match_scope": "archetype_matched",
        "source_lane": "archetype_matched_public_guide",
        "deck_match": {"exact_deck_evidence": {"matched": False}},
        "claims": [
            {
                **claim,
                "promotion_eligible": False,
                "source_confidence": "high",
            }
            for claim in strong_record["claims"]
        ],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="PirateRogue",
        deck_identity=deck_identity,
        source_search_records=[strong_record, partial_record],
        current_date="2026-07-15",
    )

    assert bundle["source_autopilot_report"]["strong_candidate"] is True


def test_operator_matrix_has_no_duplicate_json_keys():
    assert _duplicate_json_keys(Path("docs/operator/archetype-fixture-matrix.json")) == []


def test_operator_matrix_documents_partial_and_conditional_decks():
    matrix_by_deck = {deck["deck_name"]: deck for deck in load_archetype_matrix()}

    for deck_name, expected in EXPECTED_REPRESENTATIVE_SOURCE_STATUS.items():
        if expected not in PARTIAL_OR_CONDITIONAL_STATUSES:
            continue
        row = matrix_by_deck[deck_name]
        assert row["expected_semantic_status"] == expected, row
        assert row["first_missing_source_action"], row
        assert row["first_missing_source_action"] not in PLACEHOLDER_SOURCE_ACTIONS, row
        assert row["why_not_strong"], row


def test_representative_matrix_uses_source_search_drafted_documents_for_prepare(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    results = build_representative_multideck_matrix(tmp_path)

    for row in results:
        assert row["source_documents_json"].is_file(), row
        assert row["source_documents_json"].name == "source_documents.json", row
        assert row["source_documents_json"].parent.name == row["deck_name"], row
        assert row["source_documents_json"].parent.parent.name == "source_autopilot", row
        assert row["source_search_urls"] == row["source_document_urls"], row
        assert row["prepared_source_document_urls"] == row["source_document_urls"], row


def test_representative_decks_are_load_safe_and_do_not_fake_strong(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    results = build_representative_multideck_matrix(tmp_path)

    assert {row["deck_name"] for row in results} == set(EXPECTED_EVIDENCE_STATUS)
    for row in results:
        expected = EXPECTED_EVIDENCE_STATUS[row["deck_name"]]
        assert row["technical_status"] == "VALID_PACKAGE", row
        assert row["runtime_apply_allowed"] is False, row
        assert row["operator_summary"]["source_apply_eligibility_reasons"] == [
            "diagnostic_source_not_apply_eligible"
        ], row
        assert set(row["default_only_runtime_surfaces"]) <= {"cardid_behavior"}, row
        if expected == "SOURCE_BACKED_STRONG":
            assert row["semantic_status"] == "SOURCE_BACKED_STRONG", row
            assert row["promotion_ready"] is True, row
        elif expected == "SOURCE_BACKED_PARTIAL":
            assert row["semantic_status"] != "SOURCE_BACKED_STRONG", row
            assert row["promotion_ready"] is False, row
        elif expected == "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH":
            assert row["semantic_status"] in {
                "SOURCE_BACKED_STRONG",
                "VALID_BUT_NOT_GUIDE_STRONG",
                "STATIC_SEMANTICS_USABLE",
            }, row
            if "archetype_matched_not_exact_list" in row["deck_match_scopes"]:
                assert row["semantic_status"] != "SOURCE_BACKED_STRONG", row
                assert row["promotion_ready"] is False, row
        elif expected == "SOURCE_BACKED_PARTIAL_UNLESS_EXACT_GUIDE_MATCHED":
            if "exact_deck_matched" not in row["deck_match_scopes"]:
                assert row["semantic_status"] != "SOURCE_BACKED_STRONG", row
                assert row["promotion_ready"] is False, row
        else:
            raise AssertionError(f"unhandled expected evidence status: {expected}")


def test_multideck_matrix_never_blocks_valid_config_but_keeps_strong_honest(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    expected_partial = {
        "CtAPaladin",
        "Discolock",
        "TreantDruid",
        "Kingslayer",
        "Boarlock",
        "PirateDH",
    }
    expected_strong_or_strong_ready = {
        "ShadowPriest",
        "PirateRogue",
        "BigShaman",
        "ImbueMage",
        "MechPala",
    }

    for row in build_representative_multideck_matrix(tmp_path):
        deck_name = row["deck_name"]
        operator = row["operator_summary"]
        strong_report = row["strong_promotion_report"]

        assert operator["technical_status"] == "VALID_PACKAGE", row
        assert operator["runtime_apply_allowed"] is False, row
        assert operator["runtime_apply_mode"] == "blocked", row
        assert operator["source_apply_eligibility_reasons"] == [
            "diagnostic_source_not_apply_eligible"
        ], row
        assert operator["runtime_apply_contract"]["apply_authority"] == (
            "reports/operator_summary.json"
        )
        assert operator["next_action"] in {
            "READY_TO_APPLY_OR_HANDOFF",
            "READY_TO_APPLY_WITH_WARNINGS",
            "SOURCE_CLOSURE_NEEDED",
        }
        assert operator["source_backed_strong_closure"]["diagnostic_only"] is True
        assert operator["source_backed_strong_closure"][
            "first_missing_source_action"
        ] == strong_report["first_missing_source_action"]
        assert operator["first_missing_source_action"] == strong_report[
            "first_missing_source_action"
        ]
        assert operator["no_default_only_runtime_status"] in {
            "clean",
            "has_default_only_surfaces",
        }
        assert set(operator["default_only_runtime_surfaces"]) <= {"cardid_behavior"}

        if deck_name in expected_partial:
            assert (
                operator["semantic_status"] != "SOURCE_BACKED_STRONG"
                or strong_report["promotion_ready"] is False
            ), row
            assert strong_report["first_missing_source_action"] != "none", row
        if deck_name in expected_strong_or_strong_ready:
            assert operator["default_only_runtime_surfaces"] == [], row
