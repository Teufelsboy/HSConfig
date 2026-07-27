from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.cli import main
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import write_json
from hsconfig.strict_package_validation import validate_complete_package
from tests.helpers.fixture_prepare import prepare_fixture_deck, read_json


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
SUPPLEMENTAL_PATH = Path("docs/operator/supplemental-proof-decks.json")
DIAGNOSTIC_APPLY_REASON = "diagnostic_source_not_apply_eligible"
CARD_METADATA_KEYS = {"ConfigComment", "GameCardId"}


def audited_decks() -> list[dict[str, Any]]:
    matrix = read_json(MATRIX_PATH)["decks"]
    supplemental = read_json(SUPPLEMENTAL_PATH)["decks"]
    cute_warrior = next(
        row for row in supplemental if row["deck_name"] == "CuteWarrior"
    )
    return [*matrix, cute_warrior]


def _captured_source_documents(deck: Mapping[str, Any]) -> dict[str, Any]:
    fixture_bytes = f"{deck['deck_name']}:diagnostic-fixture".encode()
    return {
        "source_documents": [
            {
                "source_url": "https://example.invalid/diagnostic-fixture",
                "source_title": f"{deck['deck_name']} diagnostic fixture",
                "source_family": "guide",
                "retrieved_at": "2026-07-27T00:00:00Z",
                "acquisition_provenance": {
                    "mode": "captured_record",
                    "authority": "captured_unverified",
                    "content_sha256": f"sha256:{sha256(fixture_bytes).hexdigest()}",
                },
                "source_visibility": "full_text",
                "source_lane": "archetype_matched_public_guide",
                "deck_name": str(deck["deck_name"]),
                "archetype": "diagnostic_fixture",
                "deck_match_scope": "archetype_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 0,
                        "decoded_candidate_count": 0,
                        "matched": False,
                        "matched_deck_fingerprint": "",
                        "candidate_deck_code_hashes": [],
                    }
                },
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "scope": "deck",
                        "cards": [],
                        "stance": "diagnostic_fixture",
                        "evidence_text_short": (
                            "Diagnostic captured source used for read-only acceptance."
                        ),
                        "source_confidence": "medium",
                        "promotion_eligible": False,
                    }
                ],
            }
        ]
    }


def _prepare_audited_deck(
    tmp_path: Path,
    deck: dict[str, Any],
) -> dict[str, Any]:
    if deck["deck_name"] != "CuteWarrior":
        return prepare_fixture_deck(tmp_path, deck)

    source_path = tmp_path / "cutewarrior-diagnostic-source.json"
    write_json(source_path, _captured_source_documents(deck))
    out = tmp_path / "CuteWarrior"
    exit_code = main(
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
            str(source_path),
            "--json",
        ]
    )
    return {
        "exit_code": exit_code,
        "out": out,
        "operator": read_json(out / "reports" / "operator_summary.json"),
    }


def _deck_dir(package: Mapping[str, Any]) -> Path:
    directories = [
        path
        for path in (Path(package["out"]) / "CustomConfig").iterdir()
        if path.is_dir()
    ]
    assert len(directories) == 1
    return directories[0]


def _card_payloads(package: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        path.stem: read_json(path)
        for path in _deck_dir(package).glob("*.json")
        if path.name not in {"GlobalValues.json", "Mulligan.json", "Combo.json"}
    }


def _physical_card_rows(
    payloads: Mapping[str, Mapping[str, Any]],
) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for card_id, payload in payloads.items():
        for block, block_payload in payload.items():
            if block in CARD_METADATA_KEYS or not isinstance(block_payload, Mapping):
                continue
            values = block_payload.get("values", [])
            assert isinstance(values, list)
            for row in values:
                assert isinstance(row, Mapping)
                rows.append(
                    (
                        card_id,
                        block,
                        str(row.get("condition", "")),
                        str(row.get("value", "")),
                    )
                )
    return rows


def _mulligan_hold_cards(package: Mapping[str, Any]) -> set[str]:
    mulligan = read_json(_deck_dir(package) / "Mulligan.json")
    return {
        str(row["mulligan"])
        for row in mulligan["Mulligan"]["values"]
        if row.get("value") == "hold"
    }


def _assert_global_semantic_invariants(package: Mapping[str, Any]) -> None:
    out = Path(package["out"])
    reports = out / "reports"
    identity = read_json(reports / "deck_identity.json")
    behavior = read_json(reports / "card_behavior_plan_report.json")
    mulligan_plan = read_json(reports / "mulligan_plan_report.json")
    payloads = _card_payloads(package)
    card_types = {
        str(card["card_id"]): str(card.get("type", ""))
        for card in identity["cards"]
    }

    for row in behavior["rows"]:
        if row.get("meaningful_runtime_surface") is not True:
            continue
        source_card_id = str(row.get("source_card_id", row["card_id"]))
        if row.get("behavior_block") in {
            "OnBoardBonus",
            "BeforeBattlecryTargetBonus",
        }:
            assert card_types[source_card_id] != "SPELL"

    report_rows = {
        (
            str(row.get("runtime_card_id", row["card_id"])),
            str(row["behavior_block"]),
            str(row["condition"]),
            str(row["value"]),
        ): row
        for row in behavior["rows"]
        if row.get("meaningful_runtime_surface") is True
    }
    for physical_row in _physical_card_rows(payloads):
        assert physical_row in report_rows
        provenance = report_rows[physical_row]
        assert provenance["source_claim_ids"]
        assert provenance["source_refs"]

    card_condition_suppressions = {
        str(row["claim_id"])
        for row in behavior["suppressed"]
        if "condition" in str(row.get("reason", ""))
        and (
            str(row.get("reason", "")).endswith("_not_encoded")
            or "unsupported" in str(row.get("reason", ""))
        )
    }
    emitted_card_claims = {
        str(claim_id)
        for row in behavior["rows"]
        for claim_id in row.get("source_claim_ids", [])
    }
    assert card_condition_suppressions.isdisjoint(emitted_card_claims)

    mulligan_condition_suppressions = {
        str(row["claim_id"])
        for row in mulligan_plan["suppressed_rules"]
        if row.get("reason") == "unsupported_mulligan_condition"
    }
    emitted_mulligan_claims = {
        str(claim_id)
        for row in mulligan_plan["rules"]
        for claim_id in row.get("source_claim_ids", [])
    }
    assert mulligan_condition_suppressions.isdisjoint(emitted_mulligan_claims)


def _assert_deck_specific_invariants(
    deck_name: str,
    package: Mapping[str, Any],
) -> None:
    out = Path(package["out"])
    reports = out / "reports"
    payloads = _card_payloads(package)
    holds = _mulligan_hold_cards(package)

    if deck_name == "ShadowPriest":
        assert "BeforeUseHeroPowerBonus" not in payloads["SW_448"]
        assert len(payloads["EX1_625t"]["BeforeUseHeroPowerBonus"]["values"]) == 1
        behavior = read_json(reports / "card_behavior_plan_report.json")
        reciprocal = [
            row
            for row in behavior["suppressed"]
            if row.get("reason") == "reciprocal_burn_report_only"
        ]
        assert reciprocal
        assert "GVG_009" in {
            card for row in reciprocal for card in row["cards"]
        }
        reciprocal_claims = {
            str(claim_id)
            for row in reciprocal
            for claim_id in row["source_claim_ids"]
        }
        emitted_claims = {
            str(claim_id)
            for row in behavior["rows"]
            for claim_id in row.get("source_claim_ids", [])
        }
        assert reciprocal_claims.isdisjoint(emitted_claims)
        for card_id in ("TOY_518", "WON_065"):
            assert len(payloads[card_id]["OnBoardBonus"]["values"]) == 1
        return

    if deck_name == "MechPala":
        module_ids = {"TOY_330t95", "TOY_330t98", "TOY_330t11"}
        metadata = read_json(reports / "semantic_enrichment_report.json")
        readiness = read_json(reports / "per_card_config_readiness_report.json")
        metadata_by_card = {row["card_id"]: row for row in metadata["cards"]}
        assert module_ids <= set(metadata_by_card)
        assert module_ids <= set(readiness["cards"])
        for card_id in module_ids:
            assert metadata_by_card[card_id]["deck_zone"] == "sideboard"
            assert metadata_by_card[card_id]["sideboard_owner_card_id"] == "TOY_330"
            assert readiness["cards"][card_id]["deck_zone"] == "sideboard"
            assert readiness["cards"][card_id]["runtime_surfaces"] == []
        assert "TOY_330" not in holds
        return

    if deck_name == "Kingslayer":
        assert "DEEP_014" not in holds
        for card_id in ("VAC_938", "VAC_701"):
            assert "BeforePhysicalAttackBonus" not in payloads[card_id]
        return

    if deck_name == "Boarlock":
        assert "WW_092" not in holds
        assert not (_deck_dir(package) / "Combo.json").exists()
        globalvalues = read_json(_deck_dir(package) / "GlobalValues.json")
        assert "MyHeroPowerValue" not in globalvalues
        return

    if deck_name == "Discolock":
        assert all(
            "InHandPlayPriority" not in payload for payload in payloads.values()
        )
        profile = read_json(reports / "globalvalues_profile.json")
        assert profile["authority_parity"] == {
            "authorized_overlay_keys": [],
            "emitted_overlay_keys": [],
            "status": "matched",
        }
        return

    if deck_name == "ImbueMage":
        readiness = read_json(reports / "per_card_config_readiness_report.json")
        readiness_mulligan_cards = {
            card_id
            for card_id, row in readiness["cards"].items()
            if "Mulligan.json" in row["runtime_surfaces"]
        }
        mulligan = read_json(_deck_dir(package) / "Mulligan.json")
        physical_mulligan_cards = {
            str(row["mulligan"])
            for row in mulligan["Mulligan"]["values"]
            if row.get("mulligan") != "*"
        }
        assert physical_mulligan_cards == readiness_mulligan_cards
        assert "FIR_911" in physical_mulligan_cards


@pytest.mark.parametrize(
    "deck",
    audited_decks(),
    ids=lambda row: row["deck_name"],
)
def test_audited_deck_contract_is_current(
    deck: dict[str, Any],
    tmp_path: Path,
) -> None:
    decoded = decode_deck_code(str(deck["deck_code"]))
    assert decoded["card_count"] == 30
    assert decoded["unresolved_card_count"] == 0
    assert deck["fixture_expected_load_safe"] is True
    assert deck["fixture_runtime_apply_authority"] == "diagnostic_only"

    package = _prepare_audited_deck(tmp_path, deck)

    assert package["exit_code"] == 0
    summary = package["operator"]
    assert (Path(package["out"]) / "package_derivation_receipt.json").is_file()
    assert summary["package_derivation"]["verified"] is True
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_load_safe"] is True
    assert summary["fixture_classification"] == "load_safe_fixture"
    assert summary["runtime_apply_mode"] == "blocked"
    assert summary["runtime_apply_allowed"] is False
    assert summary["runtime_apply_reason"] == DIAGNOSTIC_APPLY_REASON
    assert summary["runtime_apply_contract"] == {
        "apply_authority": "reports/operator_summary.json",
        "authority_scope": "current_package_operator_gate",
    }
    assert summary["no_block_failure_mode_summary"]["hard_block"] is False
    assert summary["no_block_failure_mode_summary"]["runtime_apply_reason"] == (
        DIAGNOSTIC_APPLY_REASON
    )

    _assert_global_semantic_invariants(package)
    _assert_deck_specific_invariants(str(deck["deck_name"]), package)


def test_exact_live_verified_fixture_requires_strict_validation_for_eligibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deck = next(
        row for row in audited_decks() if row["deck_name"] == "ShadowPriest"
    )
    html = f"""
    <html>
      <head><title>ShadowPriest exact deck guide</title></head>
      <body><main>
        <time datetime="2026-07-27"></time>
        <h1>ShadowPriest guide</h1>
        <p>Deck code: {deck["deck_code"]}</p>
        <h2>Mulligan</h2>
        <p>Keep Voidtouched Attendant in the opening hand.</p>
        <p>Darkbishop Benedictus establishes Shadowform.</p>
      </main></body>
    </html>
    """.encode()
    monkeypatch.setattr(
        "hsconfig.source_acquisition._default_resolver",
        lambda _hostname: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "hsconfig.source_acquisition._fetch_with_validated_address",
        lambda _url, _timeout, _address: (200, "text/html", html),
    )
    out = tmp_path / "live-verified"

    exit_code = main(
        [
            "configure",
            "--deck-name",
            str(deck["deck_name"]),
            "--deck-code",
            str(deck["deck_code"]),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--online-source",
            "--auto-source",
            "--source-url",
            "https://example.test/exact-guide",
            "--current-date",
            "2026-07-27",
            "--json",
        ]
    )
    package = out / "04_package"
    summary = read_json(package / "reports" / "operator_summary.json")
    bundle = read_json(package / "reports" / "guide_claim_bundle.json")
    validation = validate_complete_package(package)
    gate = evaluate_apply_gate(package)

    assert exit_code == 0
    assert bundle["canonical_source_receipts"]
    assert all(
        receipt["acquisition_provenance"]["mode"] == "live_http"
        and receipt["acquisition_provenance"]["authority"] == "live_verified"
        for receipt in bundle["canonical_source_receipts"]
    )
    assert validation["status"] == "passed"
    assert validation["errors"] == []
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["source_apply_eligible"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert gate["status"] == "allowed"
    assert gate["allowed"] is True

    (package / "reports" / "globalvalues_profile.json").unlink()
    invalid_validation = validate_complete_package(package)
    invalid_gate = evaluate_apply_gate(package)

    assert invalid_validation["status"] == "failed"
    assert invalid_gate["status"] == "blocked"
    assert invalid_gate["allowed"] is False
    assert invalid_gate["reasons"][0]["reason"] == "strict_package_validation_failed"
