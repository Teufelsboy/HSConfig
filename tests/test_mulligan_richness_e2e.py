import json
from pathlib import Path

from hsconfig.cli import main


CARDS = [
    {"card_id": "TEST_001", "dbf_id": 1, "count": 2, "name": "Card A", "cost": 1, "type": "MINION"},
    {"card_id": "TEST_002", "dbf_id": 2, "count": 2, "name": "Card B", "cost": 2, "type": "MINION"},
    {"card_id": "TEST_003", "dbf_id": 3, "count": 2, "name": "Card C", "cost": 3, "type": "SPELL"},
]


def test_prepare_with_rich_captured_mulligan_sources_stays_policy_backed(
    tmp_path: Path, capsys, monkeypatch
):
    result = _run_prepare(
        tmp_path,
        capsys,
        monkeypatch,
        source_documents="tests/fixtures/source_documents_mulligan_rich.json",
    )

    operator = result["operator_summary"]
    mulligan_surface = result["mulligan_plan"]["quality"]
    mulligan_values = result["mulligan_json"]["Mulligan"]["values"]

    assert result["exit_code"] == 0
    assert result["payload"]["status"] == "passed"
    assert operator["technical_status"] == "INVALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "blocked"
    assert operator["deck_input_verification"]["status"] == "cards_json_unverified"
    assert operator["deck_input_verification"]["runtime_apply_eligible"] is False
    assert mulligan_surface["status"] == "policy_backed"
    assert mulligan_surface["source_backed_rule_count"] == 0
    assert mulligan_surface["suppressed_reasons"][
        "strategic_provenance_not_live_verified"
    ] == 4
    assert {
        (row["mulligan"], row["value"]) for row in mulligan_values
    } == {
        ("TEST_003", "hold"),
        ("*", "discard"),
    }


def test_prepare_rejected_guide_claim_does_not_veto_policy_fallback(
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
                                "cards": ["TEST_001"],
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
                                "cards": ["TEST_001"],
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

    assert any(
        row.get("card") == "TEST_001"
        and row.get("source_type") == "policy_backed_autonomous_mulligan"
        for row in holds
    )
    assert not any(
        row.get("card") == "TEST_001"
        and row.get("reason") == "excluded_source_mulligan_intent"
        for row in plan["quality"]["policy_result"]["suppressed"]
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
                                "cards": ["REJECTED_001"],
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
                "card_id": "REJECTED_001",
                "dbf_id": 4,
                "count": 1,
                "name": "Rejected Candidate",
                "cost": 4,
                "type": "MINION",
            }
        ],
    )

    assert "mulligan_anchor" not in result["research_card_roles"]["REJECTED_001"]["roles"]
    assert not any(
        row.get("mulligan") == "REJECTED_001"
        and row.get("value") == "hold"
        for row in result["mulligan_json"]["Mulligan"]["values"]
    )


def test_prepare_with_thin_mulligan_sources_stays_diagnostic_and_apply_blocked(
    tmp_path: Path, capsys, monkeypatch
):
    result = _run_prepare(
        tmp_path,
        capsys,
        monkeypatch,
        source_documents="tests/fixtures/source_documents_mulligan_thin.json",
    )

    operator = result["operator_summary"]
    mulligan_surface = result["mulligan_plan"]["quality"]

    assert result["exit_code"] == 0
    assert result["payload"]["status"] == "passed"
    assert operator["technical_status"] == "INVALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "blocked"
    assert operator["runtime_apply_allowed"] is False
    assert operator["deck_input_verification"]["status"] == "cards_json_unverified"
    assert operator["config_usefulness"]["blocking"] is False
    assert operator["config_usefulness"]["status"] == "invalid_package"
    assert mulligan_surface["status"] == "policy_backed"
    assert (
        mulligan_surface["first_gap_reason"]
        == "policy_backed_autonomous_mulligan"
    )
    assert mulligan_surface["policy_result"]["status"] == "applied"


def _run_prepare(
    tmp_path: Path,
    capsys,
    monkeypatch,
    *,
    source_documents: str,
    cards: list[dict] | None = None,
) -> dict:
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(json.dumps({"cards": cards or CARDS}), encoding="utf-8")
    package = tmp_path / "package"
    exit_code = main(
        [
            "prepare",
            "--deck-name",
            "Mulligan Fixture",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            source_documents,
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
