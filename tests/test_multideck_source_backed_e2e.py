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
    prepare_fixture_deck,
    read_json as read_fixture_json,
)


DECKS = {
    "ShadowPriest": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    "MechPala": "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
    "BigShaman": "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
}

SOURCE_SEARCH_MATRIX = Path("tests/fixtures/source_search_11_deck_matrix.json")

EXPECTED_REPRESENTATIVE_SOURCE_STATUS = {
    "ShadowPriest": "SOURCE_BACKED_STRONG",
    "MechPala": "SOURCE_BACKED_STRONG",
    "PirateRogue": "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH",
    "BigShaman": "SOURCE_BACKED_STRONG",
    "Boarlock": "SOURCE_BACKED_PARTIAL",
    "ImbueMage": "SOURCE_BACKED_STRONG",
    "TreantDruid": "SOURCE_BACKED_PARTIAL",
    "Discolock": "SOURCE_BACKED_PARTIAL",
    "PirateDH": "SOURCE_BACKED_PARTIAL",
    "CtAPaladin": "SOURCE_BACKED_PARTIAL_UNLESS_EXACT_GUIDE_MATCHED",
    "Kingslayer": "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH",
}

EXPECTED_EVIDENCE_STATUS = EXPECTED_REPRESENTATIVE_SOURCE_STATUS

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
        assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
        assert summary["guide_strength_summary"]["cards_needing_runtime_surface"] == 0
        assert summary["semantic_blockers"] == []
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
        expected = EXPECTED_REPRESENTATIVE_SOURCE_STATUS[deck_name]
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
            assert report["strong_candidate"] is True, report
        if expected == "SOURCE_BACKED_PARTIAL":
            assert report["strong_candidate"] is False, report
            assert {
                record["source_record_strength"] for record in records
            } <= NON_STRONG_SOURCE_RECORD_STRENGTHS


def test_source_autopilot_blocks_non_promoting_partial_record_even_if_it_looks_exact():
    records_by_deck = _source_search_records_by_deck()
    matrix_by_deck = {deck["deck_name"]: deck for deck in load_archetype_matrix()}
    strong_record = records_by_deck["PirateRogue"][0]
    partial_record = {
        **strong_record,
        "source_record_strength": "partial",
        "promotion_eligible": False,
        "source_visibility": "full_text",
        "publication_year": 2026,
        "published_at": "2026-07-03T00:00:00Z",
        "deck_match_scope": "deck_or_archetype_matched",
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
        deck_identity=_deck_identity_for(matrix_by_deck["PirateRogue"]),
        source_search_records=[partial_record],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    assert report["strong_candidate"] is False, report
    blocker_text = " ".join(report["strong_candidate_blockers"])
    assert "non_promoting" in blocker_text, report
    assert "partial" in blocker_text, report


def test_source_autopilot_drafted_documents_preserve_non_promoting_partial_metadata():
    records_by_deck = _source_search_records_by_deck()
    matrix_by_deck = {deck["deck_name"]: deck for deck in load_archetype_matrix()}
    strong_record = records_by_deck["PirateRogue"][0]
    partial_record = {
        **strong_record,
        "source_record_strength": "partial",
        "promotion_eligible": False,
        "source_visibility": "full_text",
        "publication_year": 2026,
        "published_at": "2026-07-03T00:00:00Z",
        "deck_match_scope": "deck_or_archetype_matched",
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
        deck_identity=_deck_identity_for(matrix_by_deck["PirateRogue"]),
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
    strong_record = records_by_deck["PirateRogue"][0]
    partial_record = {
        **strong_record,
        "source_url": "https://example.invalid/partial-piraterogue-guide",
        "source_record_strength": "partial",
        "promotion_eligible": False,
        "source_visibility": "full_text",
        "publication_year": 2026,
        "published_at": "2026-07-03T00:00:00Z",
        "deck_match_scope": "deck_or_archetype_matched",
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
        deck_identity=_deck_identity_for(matrix_by_deck["PirateRogue"]),
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
        assert row["runtime_apply_allowed"] is True, row
        assert row["default_only_runtime_surfaces"] == [], row
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
            if "deck_or_archetype_matched" not in row["deck_match_scopes"]:
                assert row["semantic_status"] != "SOURCE_BACKED_STRONG", row
                assert row["promotion_ready"] is False, row
        else:
            raise AssertionError(f"unhandled expected evidence status: {expected}")
