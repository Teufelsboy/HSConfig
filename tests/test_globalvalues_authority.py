import pytest

from hsconfig.globalvalues_key_authority import authority_for_key
from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_document_model import can_lower_to_globalvalues


def test_globalvalues_key_authority_classifies_core_keys():
    assert authority_for_key("FirstTurnValueWeight")["category"] == "step1_posture_overlay_allowed"
    assert authority_for_key("SecondTurnValueWeight")["category"] == "step1_posture_overlay_allowed"
    assert authority_for_key("MyHeroPowerValue")["category"] == "step1_posture_overlay_allowed"
    assert authority_for_key("OpponentSpecificMatchupTuning")["category"] == "runtime_evidence_required"


def test_aggressive_posture_allows_selected_step1_keys():
    claim, receipts = _verified_public_guide_posture_claim()
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[claim],
        deck_identity={"deck_fingerprint": "target-fingerprint"},
        verified_source_receipts=receipts,
    )

    allowed = {row["key"] for row in matrix["allowed_step1_overlays"]}
    blocked = {row["key"] for row in matrix["blocked_until_runtime_evidence"]}
    assert "FirstTurnValueWeight" in allowed
    assert "SecondTurnValueWeight" in allowed
    assert "LowHpBoardValuePenalty" in blocked


def test_globalvalues_rows_use_lifecycle_claim_id_without_rewriting_claim_refs():
    posture_claim, receipts = _verified_public_guide_posture_claim(
        claim_id="raw_posture",
        stance="weapon_pressure",
    )
    source_refs = list(posture_claim["source_refs"])
    posture_claim = {
        **posture_claim,
        "_claim_lifecycle": {
            "claim_id": "lifecycle_posture",
            "surface": "globalvalues",
        },
    }
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="baseline",
        claims=[
            posture_claim,
            {
                "claim_id": "raw_numeric",
                "claim_kind": "globalvalue_numeric_tuning",
                "key": "LowHpBoardValuePenalty",
                "_claim_lifecycle": {
                    "claim_id": "lifecycle_numeric",
                    "surface": "globalvalues",
                },
            },
        ],
        deck_identity={"deck_fingerprint": "target-fingerprint"},
        verified_source_receipts=receipts,
    )

    allowed = {row["key"]: row for row in matrix["allowed_step1_overlays"]}
    assert allowed["MyWeaponValue"]["claim_id"] == "lifecycle_posture"
    assert allowed["MyWeaponValue"]["claim_refs"] == ["raw_posture", *source_refs]

    numeric_row = next(
        row
        for row in matrix["blocked_until_runtime_evidence"]
        if row["key"] == "LowHpBoardValuePenalty"
        and row.get("claim_refs") == ["raw_numeric"]
    )
    assert numeric_row["claim_id"] == "lifecycle_numeric"


def test_globalvalues_authority_matrix_embeds_per_key_authority():
    claim, receipts = _verified_public_guide_posture_claim()
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[claim],
        deck_identity={"deck_fingerprint": "target-fingerprint"},
        verified_source_receipts=receipts,
    )

    allowed = {row["key"]: row for row in matrix["allowed_step1_overlays"]}
    blocked = {row["key"]: row for row in matrix["blocked_until_runtime_evidence"]}

    assert allowed["FirstTurnValueWeight"]["key_authority"] == authority_for_key("FirstTurnValueWeight")
    assert allowed["MyHeroPowerValue"]["key_authority"] == authority_for_key("MyHeroPowerValue")
    assert blocked["OpponentSpecificMatchupTuning"]["key_authority"] == authority_for_key(
        "OpponentSpecificMatchupTuning"
    )


def test_runtime_only_numeric_tuning_is_reported_not_applied():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[
            {
                "claim_kind": "globalvalue_numeric_tuning",
                "stance": "decrease_low_hp_penalty",
                "cards": [],
                "claim_confidence": "medium",
            }
        ],
    )

    assert any(
        row["reason"] == "requires_runtime_evidence"
        for row in matrix["blocked_until_runtime_evidence"]
    )


def test_posture_overlay_matrix_supports_named_step1_postures():
    cases = {
        "aggro_burn": {"FirstTurnValueWeight", "MyHeroPowerValue"},
        "token_board": {"GlobalMinionAttack", "GlobalMinionIntrinsicValue"},
        "weapon_pressure": {"MyWeaponValue"},
        "deathrattle_recruit": {"GlobalMinionIntrinsicValue"},
        "control_value": {"SecondTurnValueWeight"},
    }

    for posture, expected_keys in cases.items():
        claim, receipts = _verified_public_guide_posture_claim(
            stance=posture,
            claim_id=f"claim_{posture}",
        )
        matrix = build_globalvalues_authority_matrix(
            aggression_profile=posture,
            claims=[claim],
            deck_identity={"deck_fingerprint": "target-fingerprint"},
            verified_source_receipts=receipts,
        )

        rows_by_key = {row["key"]: row for row in matrix["allowed_step1_overlays"]}
        assert expected_keys <= set(rows_by_key), posture
        for key in expected_keys:
            assert rows_by_key[key]["operation"] in {"set", "increase", "decrease"}
            assert "reason" in rows_by_key[key]


def test_unknown_posture_keeps_baseline_default():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="unknown",
        claims=[{**_public_guide_posture_claim(), "stance": "unknown"}],
        deck_identity={"deck_fingerprint": "target-fingerprint"},
    )

    assert matrix["allowed_step1_overlays"] == [
        {
            "key": "baseline",
            "overlay": "none",
            "operation": "none",
            "value": None,
            "authority": "baseline_default",
            "key_authority": authority_for_key("baseline"),
            "claim_refs": [],
            "reason": "no_source_backed_posture_overlay",
        }
    ]


def test_source_posture_claim_overrides_generic_aggro_profile():
    claim, receipts = _verified_public_guide_posture_claim(
        stance="weapon_pressure",
        claim_id="claim_weapon",
    )
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggro",
        claims=[claim],
        deck_identity={"deck_fingerprint": "target-fingerprint"},
        verified_source_receipts=receipts,
    )

    allowed = {row["key"] for row in matrix["allowed_step1_overlays"]}
    assert matrix["posture"] == "weapon_pressure"
    assert "MyWeaponValue" in allowed
    assert "MyHeroPowerValue" not in allowed


def test_globalvalues_ignores_card_role_claims_even_when_source_backed():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="unknown",
        claims=[
            {
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "stance": "aggro_burn",
                "cards": ["CARD_001"],
            }
        ],
    )

    assert matrix["posture"] == "baseline"
    assert matrix["allowed_step1_overlays"][0]["reason"] == "no_source_backed_posture_overlay"


def test_globalvalues_ignores_aggro_profile_without_authorized_posture_claims():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggro",
        claims=[
            {
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "stance": "aggro_burn",
                "cards": ["CARD_001"],
                "source_refs": ["guide:1"],
            }
        ],
    )

    assert matrix["posture"] == "baseline"
    assert matrix["allowed_step1_overlays"] == [
        {
            "key": "baseline",
            "overlay": "none",
            "operation": "none",
            "value": None,
            "authority": "baseline_default",
            "key_authority": authority_for_key("baseline"),
            "claim_refs": [],
            "reason": "no_source_backed_posture_overlay",
        }
    ]


def _public_guide_posture_claim(
    *,
    deck_match_scope: str = "exact_deck_matched",
    source_lane: str = "deck_matched_public_guide",
    evidence_fingerprint: str = "target-fingerprint",
) -> dict[str, object]:
    return {
        "claim_id": f"{deck_match_scope}-posture",
        "claim_kind": "gameplan_posture",
        "stance": "aggressive",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "source_type": "public_guide",
        "source_family": "guide",
        "deck_match_scope": deck_match_scope,
        "promotion_eligible": True,
        "source_visibility": "full_text",
        "source_lane": source_lane,
        "deck_match": {
            "exact_deck_evidence": {
                "matched": True,
                "matched_deck_fingerprint": evidence_fingerprint,
            }
        },
        "source_refs": [f"guide:{deck_match_scope}"],
    }


def _verified_public_guide_posture_claim(
    *,
    stance: str = "aggressive",
    claim_id: str = "verified-posture",
) -> tuple[dict[str, object], list[dict[str, object]]]:
    deck_identity = {
        "deck_name": "Receipt Fixture",
        "deck_fingerprint": "target-fingerprint",
        "cards": [{"card_id": "CARD_001", "name": "Receipt Card", "count": 1}],
    }
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/exact-receipt",
                "source_title": "Exact receipt guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": "target-fingerprint",
                        "candidate_deck_code_hashes": ["sha256:source-code"],
                    }
                },
                "claims": [
                    {
                        "claim_id": claim_id,
                        "claim_kind": "gameplan_posture",
                        "cards": ["CARD_001"],
                        "scope": "deck",
                        "stance": stance,
                        "evidence_text_short": f"Use the {stance} posture.",
                        "source_confidence": "high",
                        "promotion_eligible": True,
                    }
                ],
            }
        ],
        current_date="2026-07-26",
    )
    return bundle["claims"][0], bundle["globalvalues_source_receipts"]


def test_archetype_only_public_guide_posture_is_visibly_suppressed() -> None:
    claim = _public_guide_posture_claim(
        deck_match_scope="archetype_matched",
        source_lane="archetype_matched_public_guide",
    )

    deck_identity = {"deck_fingerprint": "target-fingerprint"}
    decision = can_lower_to_globalvalues(claim, deck_identity=deck_identity)
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[claim],
        deck_identity=deck_identity,
    )

    assert decision.allowed is False
    assert decision.reason == "globalvalues_requires_exact_deck_match"
    assert matrix["posture"] == "baseline"
    assert matrix["allowed_step1_overlays"][0]["reason"] == (
        "no_source_backed_posture_overlay"
    )
    suppression = next(
        row
        for row in matrix["blocked_until_runtime_evidence"]
        if row.get("claim_refs") == [
            "archetype_matched-posture",
            "guide:archetype_matched",
        ]
    )
    assert suppression["authority"] == "source_contract_suppressed"
    assert suppression["reason"] == "globalvalues_requires_exact_deck_match"


def test_exact_public_guide_posture_remains_authorized() -> None:
    claim, receipts = _verified_public_guide_posture_claim()

    deck_identity = {"deck_fingerprint": "target-fingerprint"}
    decision = can_lower_to_globalvalues(
        claim,
        deck_identity=deck_identity,
        verified_source_receipts=receipts,
    )
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[claim],
        deck_identity=deck_identity,
        verified_source_receipts=receipts,
    )

    assert decision.allowed is True
    assert decision.reason == "allowed"
    assert matrix["posture"] == "aggro"
    assert {
        row["key"] for row in matrix["allowed_step1_overlays"]
    } >= {"FirstTurnValueWeight", "MyHeroPowerValue"}
    assert not any(
        row.get("authority") == "source_contract_suppressed"
        for row in matrix["blocked_until_runtime_evidence"]
    )


def test_raw_claim_cannot_self_assert_exact_public_guide_authority() -> None:
    claim = _public_guide_posture_claim()

    decision = can_lower_to_globalvalues(
        claim,
        deck_identity={"deck_fingerprint": "target-fingerprint"},
    )

    assert decision.allowed is False
    assert decision.reason == "globalvalues_requires_verified_source_receipt"


def test_contradictory_non_guide_provenance_vetoes_public_guide_identity() -> None:
    claim = {
        **_public_guide_posture_claim(),
        "source_type": "public_guide",
        "provenance": "official_card_data",
        "source_family": "card_text",
    }

    decision = can_lower_to_globalvalues(
        claim,
        deck_identity={"deck_fingerprint": "target-fingerprint"},
    )

    assert decision.allowed is False
    assert decision.reason == "globalvalues_requires_public_guide_source"


@pytest.mark.parametrize(
    "identity_field",
    ("source_type", "provenance", "source_type_family"),
)
def test_document_non_guide_identity_cannot_be_hidden_by_claim_local_public_guide_alias(
    identity_field: str,
) -> None:
    document = _exact_posture_source_document()
    document[identity_field] = "official_card_data"
    document["claims"][0][identity_field] = "public_guide"
    bundle = build_source_document_bundle(
        deck_identity=_receipt_deck_identity(),
        card_metadata={"cards": _receipt_deck_identity()["cards"]},
        source_documents=[document],
        current_date="2026-07-26",
    )
    claim = bundle["claims"][0]

    decision = can_lower_to_globalvalues(
        claim,
        deck_identity={"deck_fingerprint": "target-fingerprint"},
        verified_source_receipts=bundle["globalvalues_source_receipts"],
    )

    assert {
        (signal["origin"], signal["field"], signal["value"])
        for signal in claim["source_identity_signals"]
    } >= {
        ("document", identity_field, "official_card_data"),
        ("claim", identity_field, "public_guide"),
    }
    assert decision.allowed is False
    assert decision.reason == "globalvalues_requires_public_guide_source"


@pytest.mark.parametrize(
    ("count_field", "invalid_value"),
    (
        ("candidate_count", "not-an-int"),
        ("decoded_candidate_count", []),
        ("candidate_count", -1),
        ("decoded_candidate_count", True),
    ),
)
def test_malformed_exact_evidence_counts_fail_closed_to_baseline_suppression(
    count_field: str,
    invalid_value: object,
) -> None:
    document = _exact_posture_source_document()
    document["deck_match"]["exact_deck_evidence"][count_field] = invalid_value

    bundle = build_source_document_bundle(
        deck_identity=_receipt_deck_identity(),
        card_metadata={"cards": _receipt_deck_identity()["cards"]},
        source_documents=[document],
        current_date="2026-07-26",
    )
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=bundle["claims"],
        deck_identity={"deck_fingerprint": "target-fingerprint"},
        verified_source_receipts=bundle["globalvalues_source_receipts"],
    )

    assert bundle["globalvalues_source_receipts"] == []
    assert {row["key"] for row in matrix["allowed_step1_overlays"]} == {
        "baseline"
    }
    assert any(
        row.get("authority") == "source_contract_suppressed"
        and row.get("reason") == "globalvalues_requires_verified_source_receipt"
        for row in matrix["blocked_until_runtime_evidence"]
    )


def test_source_less_posture_is_visibly_suppressed_by_matrix() -> None:
    claim = {
        "claim_id": "source-less-posture",
        "claim_kind": "gameplan_posture",
        "stance": "aggressive",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
    }

    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[claim],
        deck_identity={"deck_fingerprint": "target-fingerprint"},
    )

    assert matrix["posture"] == "baseline"
    assert {row["key"] for row in matrix["allowed_step1_overlays"]} == {
        "baseline"
    }
    suppression = next(
        row
        for row in matrix["blocked_until_runtime_evidence"]
        if row.get("claim_id") == "source-less-posture"
    )
    assert suppression["authority"] == "source_contract_suppressed"
    assert suppression["reason"] == "globalvalues_requires_public_guide_source"


def test_mismatched_exact_guide_fingerprint_is_visibly_suppressed_by_matrix():
    claim = _public_guide_posture_claim(
        evidence_fingerprint="different-fingerprint"
    )

    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[claim],
        deck_identity={"deck_fingerprint": "target-fingerprint"},
    )

    assert matrix["posture"] == "baseline"
    assert {row["key"] for row in matrix["allowed_step1_overlays"]} == {
        "baseline"
    }
    assert any(
        row["authority"] == "source_contract_suppressed"
        and row["reason"] == "globalvalues_exact_deck_fingerprint_mismatch"
        for row in matrix["blocked_until_runtime_evidence"]
    )


def _receipt_deck_identity() -> dict[str, object]:
    return {
        "deck_name": "Receipt Fixture",
        "deck_fingerprint": "target-fingerprint",
        "cards": [{"card_id": "CARD_001", "name": "Receipt Card", "count": 1}],
    }


def _exact_posture_source_document() -> dict[str, object]:
    return {
        "source_url": "https://example.invalid/exact-receipt",
        "source_title": "Exact receipt guide",
        "source_family": "guide",
        "source_type": "public_guide",
        "retrieved_at": "2026-07-26T00:00:00Z",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "deck_match_scope": "exact_deck_matched",
        "deck_match": {
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": "target-fingerprint",
                "candidate_deck_code_hashes": ["sha256:source-code"],
            }
        },
        "claims": [
            {
                "claim_id": "verified-posture",
                "claim_kind": "gameplan_posture",
                "cards": ["CARD_001"],
                "scope": "deck",
                "stance": "aggressive",
                "evidence_text_short": "Use the aggressive posture.",
                "source_confidence": "high",
                "promotion_eligible": True,
            }
        ],
    }
