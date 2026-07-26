import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.deck_identity import stable_deck_fingerprint


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _fixture_documents(payload):
    if isinstance(payload, list):
        return payload
    return payload["source_documents"]


def _claim_card_ids(claim):
    return set(claim.get("cards", [])) | set(claim.get("card_ids", []))


def _darkbishop_claims(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    claims = []
    for document in _fixture_documents(payload):
        for claim in document["claims"]:
            if "SW_448" in _claim_card_ids(claim):
                claims.append(claim)
    return claims


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_shadowpriest_depth_fixture(tmp_path: Path):
    package = tmp_path / "shadowpriest_strong"
    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )

    assert code == 0
    return package


def test_shadowpriest_darkbishop_fixtures_mark_effect_as_non_opening_hand_claim():
    fixture_expectations = {
        Path("tests/fixtures/shadowpriest_guide_sources.json"): {"public_guide"},
        Path("tests/fixtures/source_documents_shadowpriest_strong.json"): {
            "official_card_data",
            "public_guide",
        },
    }

    for path, expected_source_types in fixture_expectations.items():
        claims = _darkbishop_claims(path)

        assert claims
        assert {claim["claim_kind"] for claim in claims} == {"hero_power_transform"}
        assert {claim.get("source_type") for claim in claims} == expected_source_types
        assert all(claim.get("card_ids") == ["SW_448"] for claim in claims)
        if path.name == "source_documents_shadowpriest_strong.json":
            assert all(claim.get("timing") == "start_of_game" for claim in claims)
            assert all(claim.get("promotion_eligible") is True for claim in claims)
        assert all(claim.get("opening_hand_relevant") is False for claim in claims)


def test_shadowpriest_source_documents_surface_readiness_gaps(tmp_path: Path):
    out = tmp_path / "shadowpriest"
    source_docs = Path("tests/fixtures/source_documents_shadowpriest_depth.json")

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            str(source_docs),
            "--json",
        ]
    )

    assert code == 0
    summary = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["guide_strength_summary"]["cards_needing_runtime_surface"] == 0
    assert summary["semantic_blockers"]


def test_shadowpriest_guide_depth_package_has_real_plans_and_clean_runtime(tmp_path: Path, capsys):
    cards_json = tmp_path / "shadow_cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "SW_448",
                        "dbf_id": 1,
                        "count": 1,
                        "name": "Darkbishop Benedictus",
                        "text": "At the start of the game, if the spells in your deck are all Shadow, enter Shadowform.",
                    },
                    {
                        "card_id": "TOY_518",
                        "dbf_id": 2,
                        "count": 2,
                        "name": "Treasure Distributor",
                        "text": "After you summon a Pirate, give it +1 Attack.",
                    },
                    {
                        "card_id": "SW_446",
                        "dbf_id": 3,
                        "count": 1,
                        "name": "Mind Spike",
                        "text": "Hero Power: Deal 2 damage.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    guide_sources = tmp_path / "shadowpriest_guide_sources.json"
    guide_payload = json.loads(
        Path("tests/fixtures/shadowpriest_guide_sources.json").read_text(encoding="utf-8")
    )
    guide_document = guide_payload[0]
    guide_document.update(
        {
            "source_visibility": "full_text",
            "source_lane": "deck_matched_public_guide",
            "deck_match_scope": "exact_deck_matched",
            "deck_match": {
                "exact_deck_evidence": {
                    "matched": True,
                    "matched_deck_fingerprint": stable_deck_fingerprint(
                        [("SW_448", 1), ("TOY_518", 2), ("SW_446", 1)]
                    ),
                }
            },
        }
    )
    for claim in guide_document["claims"]:
        if claim["claim_kind"] in {"mulligan_keep", "gameplan_posture"}:
            claim["promotion_eligible"] = True
    guide_sources.write_text(json.dumps(guide_payload), encoding="utf-8")
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--guide-sources-json",
            str(guide_sources),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    reports = package / "reports"
    deck_dir = package / "CustomConfig" / "shadowpriest"
    guide_claims = json.loads((reports / "guide_claim_bundle.json").read_text(encoding="utf-8"))
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    cardid = json.loads((deck_dir / "SW_446.json").read_text(encoding="utf-8"))
    behavior_report = json.loads((reports / "card_behavior_plan_report.json").read_text(encoding="utf-8"))
    mulligan_report = json.loads((reports / "mulligan_plan_report.json").read_text(encoding="utf-8"))
    global_authority = json.loads(
        (reports / "global_values_authority_matrix.json").read_text(encoding="utf-8")
    )

    mulligan_values = mulligan["Mulligan"]["values"]

    assert code == 0
    assert payload["status"] == "passed"
    assert guide_claims["claims"]
    concrete_keeps = [
        row["mulligan"]
        for row in mulligan_values
        if row["value"] == "hold" and row["mulligan"] != "*"
    ]
    assert "SW_448" not in concrete_keeps
    assert "SW_446" in concrete_keeps
    assert mulligan_values[-1]["mulligan"] == "*"
    assert all(set(row) == {"comment", "mulligan", "condition", "value"} for row in mulligan_values)
    assert set(cardid) == {"ConfigComment", "GameCardId", "OnBoardBonus"}
    assert [row["value"] for row in cardid["OnBoardBonus"]["values"]] == ["10"]
    assert all("source_claim_ids" not in row for block in cardid.values() if isinstance(block, dict) for row in block.get("values", []))
    assert (
        behavior_report["card_rows"]["SW_446"][0]["intent"]
        == "use_aura_according_to_card_text"
    )
    assert mulligan_report["quality"]["has_concrete_keeps"] is True
    assert any(row["key"] == "FirstTurnValueWeight" for row in global_authority["allowed_step1_overlays"])


def test_real_shadowpriest_deckcode_depth_prepare_has_clean_runtime(tmp_path: Path, capsys):
    guide_sources = tmp_path / "real_shadow_sources.json"
    guide_sources.write_text(
        json.dumps(
            [
                {
                    "source_url": "https://example.invalid/shadow-priest-real",
                    "source_title": "Shadow Priest Fixture",
                    "source_family": "guide_fixture",
                    "retrieved_at": "2026-07-07T00:00:00Z",
                    "claims": [
                        {
                            "claim_kind": "hero_power_transform",
                            "cards": ["SW_448"],
                            "stance": "shadowform_mind_spike",
                            "evidence_text_short": "Darkbishop Benedictus enables the Start of Game hero power plan without needing to be kept.",
                            "source_confidence": "high",
                        },
                        {
                            "claim_kind": "gameplan_posture",
                            "scope": "deck",
                            "stance": "aggressive",
                            "evidence_text_short": "Shadow Priest is an aggressive pressure deck.",
                            "source_confidence": "medium",
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--guide-sources-json",
            str(guide_sources),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    reports = package / "reports"
    deck_identity = json.loads((reports / "deck_identity.json").read_text(encoding="utf-8"))
    validation = json.loads((reports / "validation_report.json").read_text(encoding="utf-8"))
    guide_claims = json.loads((reports / "guide_claim_bundle.json").read_text(encoding="utf-8"))
    deck_dir = package / "CustomConfig" / "shadowpriest"

    assert code == 0
    assert payload["status"] == "passed"
    assert deck_identity["card_count_total"] == 30
    assert validation["status"] == "passed"
    assert any(claim["claim_kind"] == "gameplan_posture" and claim["scope"] == "deck" for claim in guide_claims["claims"])
    assert (deck_dir / "SW_448.json").exists()
    deck_card_ids = {card["card_id"] for card in deck_identity["cards"]}
    for path in deck_dir.glob("*.json"):
        if path.name not in {"GlobalValues.json", "Mulligan.json", "Combo.json"}:
            assert path.stem in deck_card_ids
    for path in deck_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for block in payload.values():
            if isinstance(block, dict):
                for row in block.get("values", []):
                    assert "source_claim_ids" not in row
                    assert "confidence" not in row


def test_shadowpriest_depth_reports_show_broad_card_coverage(tmp_path: Path, capsys):
    out = tmp_path / "shadowpriest_depth"

    result = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path),
            "--out",
            str(out),
            "--guide-sources-json",
            "tests/fixtures/shadowpriest_guide_sources.json",
            "--json",
        ]
    )
    capsys.readouterr()

    reports = out / "reports"
    coverage = json.loads((reports / "claim_coverage_report.json").read_text(encoding="utf-8"))
    readiness = json.loads(
        (reports / "per_card_config_readiness_report.json").read_text(encoding="utf-8")
    )
    depth = json.loads((reports / "guide_source_depth_report.json").read_text(encoding="utf-8"))
    mulligan = json.loads(
        (out / "CustomConfig" / "shadowpriest" / "Mulligan.json").read_text(
            encoding="utf-8"
        )
    )
    voidtouched = json.loads(
        (out / "CustomConfig" / "shadowpriest" / "SW_446.json").read_text(
            encoding="utf-8"
        )
    )
    physical_card_ids = {
        "CFM_637",
        "DRG_056",
        "DS1_233",
        "GVG_009",
        "NX2_019",
        "REV_290",
        "SCH_514",
        "SW_444",
        "SW_446",
        "SW_448",
        "TOY_381",
        "TOY_518",
        "VAC_419",
        "VAC_512",
        "WON_065",
        "YOD_032",
    }
    metadata_keys = {"ConfigComment", "GameCardId"}
    card_payloads = {
        card_id: json.loads(
            (out / "CustomConfig" / "shadowpriest" / f"{card_id}.json").read_text(
                encoding="utf-8"
            )
        )
        for card_id in physical_card_ids
    }
    active_card_ids = {
        card_id
        for card_id, payload in card_payloads.items()
        if set(payload) - metadata_keys
    }
    report_only_card_ids = physical_card_ids - active_card_ids

    assert result == 0
    assert coverage["guide_backed_cards"] >= 8
    assert len(coverage["uncovered_cards"]) <= 4
    assert depth["depth_status"] in {"strong", "usable", "usable_with_runtime_gaps"}
    assert depth["summary"]["cards_needing_runtime_surface"] == 0
    assert depth["summary"]["warnings_count"] == 10
    assert readiness["summary"]["generic_low_confidence"] == 0
    assert readiness["summary"]["runtime_emitted"] == 6
    assert readiness["summary"]["cards_needing_mechanic_lowering"] == 0
    assert len(mulligan["Mulligan"]["values"]) == 4
    assert active_card_ids == {
        "DS1_233",
        "REV_290",
        "SW_446",
        "SW_448",
        "TOY_518",
        "WON_065",
    }
    assert report_only_card_ids == {
        "CFM_637",
        "DRG_056",
        "GVG_009",
        "NX2_019",
        "SCH_514",
        "SW_444",
        "TOY_381",
        "VAC_419",
        "VAC_512",
        "YOD_032",
    }
    assert set(voidtouched) == {"ConfigComment", "GameCardId", "OnBoardBonus"}
    assert [row["value"] for row in voidtouched["OnBoardBonus"]["values"]] == ["10"]
    behavior_report = json.loads(
        (reports / "card_behavior_plan_report.json").read_text(encoding="utf-8")
    )
    assert behavior_report["runtime_row_conflicts"] == []
    assert behavior_report["compiler_runtime_row_conflicts"] == []


def test_shadowpriest_darkbishop_effect_visible_without_mulligan_keep(tmp_path: Path, capsys):
    out = tmp_path / "shadowpriest_darkbishop"

    result = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--guide-sources-json",
            "tests/fixtures/shadowpriest_guide_sources.json",
            "--json",
        ]
    )
    capsys.readouterr()

    deck_dir = out / "CustomConfig" / "shadowpriest"
    reports = out / "reports"
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    darkbishop = json.loads((deck_dir / "SW_448.json").read_text(encoding="utf-8"))
    explainability = json.loads(
        (reports / "source_to_runtime_explainability.json").read_text(encoding="utf-8")
    )
    behavior_report = json.loads(
        (reports / "card_behavior_plan_report.json").read_text(encoding="utf-8")
    )

    concrete_keeps = [
        row["mulligan"]
        for row in mulligan["Mulligan"]["values"]
        if row["value"] == "hold" and row["mulligan"] != "*"
    ]
    hero_power_values = darkbishop["BeforeUseHeroPowerBonus"]["values"]
    darkbishop_attention = [
        row for row in explainability["operator_attention"] if row["card_id"] == "SW_448"
    ]

    assert result == 0
    assert "SW_448" not in concrete_keeps
    assert "SW_448" not in json.dumps(mulligan, sort_keys=True)
    assert hero_power_values
    assert any(
        row["comment"] == "ShadowPriest: SW_448_shadowform_mind_spike"
        and row["condition"] == "*"
        and row["value"] == "10"
        for row in hero_power_values
    )
    sw448_behavior_rows = behavior_report["card_rows"]["SW_448"]
    assert any(
        row.get("semantic_score", {}).get("reason") == "hero_power_transform"
        and row["value"] == "10"
        for row in sw448_behavior_rows
    )
    assert behavior_report["runtime_row_conflicts"] == []
    assert behavior_report["compiler_runtime_row_conflicts"] == []
    assert len(darkbishop_attention) == 1
    assert darkbishop_attention[0]["status"] == "runtime_backed"
    assert darkbishop_attention[0]["strongest_claim_kind"] == "hero_power_transform"
    assert darkbishop_attention[0]["default_only_risk"] is False
    darkbishop_card_row = next(
        row for row in explainability["card_rows"] if row["card_id"] == "SW_448"
    )
    assert darkbishop_card_row["strongest_claim_kind"] == "hero_power_transform"
    assert darkbishop_card_row["closure"]["default_only_risk"] is False


def test_shadowpriest_semantic_gate_preserves_darkbishop_effect_not_keep(tmp_path):
    package = prepare_shadowpriest_depth_fixture(tmp_path)
    operator = read_json(package / "reports" / "operator_summary.json")
    mulligan = read_json(package / "CustomConfig" / "shadowpriest" / "Mulligan.json")
    darkbishop = read_json(package / "CustomConfig" / "shadowpriest" / "SW_448.json")
    explainability = read_json(package / "reports" / "source_to_runtime_explainability.json")
    behavior_report = read_json(package / "reports" / "card_behavior_plan_report.json")
    closure = read_json(package / "reports" / "source_evidence_closure.json")

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["default_only_runtime_surfaces"] == []
    concrete_keeps = [
        row["mulligan"]
        for row in mulligan["Mulligan"]["values"]
        if row["value"] == "hold" and row["mulligan"] != "*"
    ]
    hero_power_values = darkbishop["BeforeUseHeroPowerBonus"]["values"]

    assert "SW_448" not in concrete_keeps
    assert hero_power_values
    assert any(
        row["comment"] == "ShadowPriest: SW_448_shadowform_mind_spike"
        and row["condition"] == "*"
        and row["value"] == "10"
        for row in hero_power_values
    )
    sw448_behavior_rows = behavior_report["card_rows"]["SW_448"]
    assert any(
        row.get("semantic_score", {}).get("reason") == "hero_power_transform"
        and row["value"] == "10"
        for row in sw448_behavior_rows
    )
    sw448 = next(row for row in explainability["card_rows"] if row["card_id"] == "SW_448")
    assert sw448["strongest_claim_kind"] == "hero_power_transform"
    assert sw448["first_missing_source_action"] == "none"
    claim_kinds = {row["claim_kind"] for row in sw448["evidence_chain"]}
    assert "hero_power_transform" in claim_kinds
    assert "mulligan_keep" not in claim_kinds
    assert closure["authority"] == "diagnostic_only"
    assert closure["apply_blocking"] is False
    assert closure["operator_gate"] == "reports/operator_summary.json"
    assert closure["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
