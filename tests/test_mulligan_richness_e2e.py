import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.deck_identity import stable_deck_fingerprint
from tests.helpers.verified_deck_input import (
    VERIFIED_SYNTHETIC_CARDS,
    deck_code_for_cards,
    remap_card_ids,
)


CARDS = [
    {**VERIFIED_SYNTHETIC_CARDS[0], "name": "Card A", "cost": 1, "type": "MINION"},
    {**VERIFIED_SYNTHETIC_CARDS[1], "name": "Card B", "cost": 2, "type": "MINION"},
    {**VERIFIED_SYNTHETIC_CARDS[2], "name": "Card C", "cost": 3, "type": "SPELL"},
]
CARD_ALIASES = {
    "TEST_001": CARDS[0]["card_id"],
    "TEST_002": CARDS[1]["card_id"],
    "TEST_003": CARDS[2]["card_id"],
}


def test_prepare_with_rich_captured_mulligan_sources_stays_suppressed(
    tmp_path: Path, capsys, monkeypatch
):
    result = _run_prepare(
        tmp_path,
        capsys,
        monkeypatch,
        source_documents="tests/fixtures/source_documents_mulligan_rich.json",
    )

    operator = result["operator_summary"]
    mulligan_surface = operator["config_usefulness"]["surfaces"]["mulligan"]
    mulligan_values = result["mulligan_json"]["Mulligan"]["values"]

    assert result["exit_code"] == 0
    assert result["payload"]["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "blocked"
    assert operator["runtime_apply_allowed"] is False
    assert mulligan_surface["status"] == "thin"
    assert mulligan_surface["source_backed_rule_count"] == 0
    assert result["mulligan_plan"]["quality"]["suppressed_reasons"][
        "strategic_provenance_not_live_verified"
    ] == 3
    assert mulligan_values == []
    assert result["mulligan_plan"]["quality"]["policy_backed_keep_rule_count"] == 0
    assert result["mulligan_plan"]["quality"]["default_only"] is False
    assert len(result["mulligan_plan"]["bot_delegated"]) == 3


def test_prepare_rejected_guide_claim_vetoes_policy_fallback_for_that_card(
    tmp_path: Path, capsys, monkeypatch
):
    source_documents = tmp_path / "rejected-guide-policy-fallback.json"
    source_documents.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/untrusted-guide",
                        "source_title": "Untrusted Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T00:00:00Z",
                        "claims": [
                            {
                                "claim_kind": "mulligan_keep",
                                "cards": [CARDS[0]["card_id"]],
                                "evidence_text_short": "Keep Card A.",
                                "source_confidence": "high",
                            }
                        ],
                    },
                    {
                        "source_url": "https://example.invalid/card-text",
                        "source_title": "Static Card Text",
                        "source_family": "card_text",
                        "retrieved_at": "2026-07-07T00:00:00Z",
                        "claims": [
                            {
                                "claim_kind": "card_role",
                                "cards": [CARDS[0]["card_id"]],
                                "stance": "early_pressure",
                                "evidence_text_short": "Card A is early pressure.",
                                "source_confidence": "high",
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = _run_prepare(
        tmp_path,
        capsys,
        monkeypatch,
        source_documents=str(source_documents),
    )

    plan = result["mulligan_plan"]
    holds = [row for row in plan["rules"] if row.get("action") == "hold"]

    assert not any(row.get("card") == CARDS[0]["card_id"] for row in holds)
    assert any(
        row.get("card_id") == CARDS[0]["card_id"]
        for row in plan["bot_delegated"]
    )


def test_prepare_rejected_guide_claim_does_not_create_policy_role_evidence(
    tmp_path: Path, capsys, monkeypatch
):
    source_documents = tmp_path / "rejected-guide-no-policy-evidence.json"
    source_documents.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/untrusted-guide",
                        "source_title": "Untrusted Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T00:00:00Z",
                        "claims": [
                            {
                                "claim_kind": "mulligan_keep",
                                "cards": [VERIFIED_SYNTHETIC_CARDS[3]["card_id"]],
                                "evidence_text_short": "Keep Rejected Candidate.",
                                "source_confidence": "high",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = _run_prepare(
        tmp_path,
        capsys,
        monkeypatch,
        source_documents=str(source_documents),
        cards=[
            {
                **VERIFIED_SYNTHETIC_CARDS[3],
                "name": "Rejected Candidate",
                "cost": 4,
                "type": "MINION",
            }
        ],
    )

    rejected_card_id = VERIFIED_SYNTHETIC_CARDS[3]["card_id"]
    assert "mulligan_anchor" not in result["research_card_roles"][rejected_card_id]["roles"]
    assert not any(
        row.get("mulligan") == rejected_card_id
        and row.get("value") == "hold"
        for row in result["mulligan_json"]["Mulligan"]["values"]
    )


def test_prepare_with_thin_mulligan_sources_stays_applyable_and_diagnosed(
    tmp_path: Path, capsys, monkeypatch
):
    result = _run_prepare(
        tmp_path,
        capsys,
        monkeypatch,
        source_documents="tests/fixtures/source_documents_mulligan_thin.json",
    )

    operator = result["operator_summary"]
    mulligan_surface = operator["config_usefulness"]["surfaces"]["mulligan"]

    assert result["exit_code"] == 0
    assert result["payload"]["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "blocked"
    assert operator["runtime_apply_allowed"] is False
    assert operator["source_apply_eligibility_reasons"] == [
        "diagnostic_source_not_apply_eligible"
    ]
    assert operator["config_usefulness"]["blocking"] is False
    assert operator["config_usefulness"]["first_usefulness_gap"] == (
        "runtime_surface_gap"
    )
    assert mulligan_surface["status"] == "thin"
    assert mulligan_surface["first_gap_reason"] == (
        "no_physical_mulligan_keep"
    )
    assert mulligan_surface["next_source_need"] == (
        "source_backed_or_policy_backed_mulligan_keeps"
    )


def _run_prepare(
    tmp_path: Path,
    capsys,
    monkeypatch,
    *,
    source_documents: str,
    cards: list[dict] | None = None,
) -> dict:
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    roster = cards or CARDS
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(json.dumps({"cards": roster}), encoding="utf-8")
    source_documents_payload = remap_card_ids(
        json.loads(Path(source_documents).read_text(encoding="utf-8")),
        CARD_ALIASES,
    )
    exact_evidence = (
        source_documents_payload
        .get("source_documents", [{}])[0]
        .get("deck_match", {})
        .get("exact_deck_evidence")
    )
    if isinstance(exact_evidence, dict):
        exact_evidence["matched_deck_fingerprint"] = stable_deck_fingerprint(
            (str(card["card_id"]), int(card["count"]))
            for card in roster
        )
    remapped_source_documents = tmp_path / "source_documents.json"
    remapped_source_documents.write_text(
        json.dumps(source_documents_payload),
        encoding="utf-8",
    )
    package = tmp_path / "package"
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            "Mulligan Fixture",
            "--deck-code",
            deck_code_for_cards(roster),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(remapped_source_documents),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    mulligan_path = next((package / "CustomConfig").rglob("Mulligan.json"))
    return {
        "exit_code": exit_code,
        "payload": payload,
        "operator_summary": _read_json(reports / "operator_summary.json"),
        "mulligan_json": _read_json(mulligan_path),
        "mulligan_plan": _read_json(reports / "mulligan_plan_report.json"),
        "research_card_roles": _read_json(reports / "research" / "card_role_map.json"),
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
