import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.deck_identity import build_deck_identity
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import read_json, write_json
from hsconfig.source_autopilot import build_source_autopilot_bundle
from hsconfig.source_document_model import qualify_source_claim
from tests.helpers.fixture_prepare import (
    load_archetype_matrix,
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
