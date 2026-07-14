from hsconfig.source_evidence_verifier import (
    claim_evidence_status,
    source_ref_is_public_https,
    verify_source_documents,
)


def _base_document(*, claims: list[dict] | None = None, **overrides):
    document = {
        "source_url": "https://example.com/shadowpriest-guide",
        "source_title": "ShadowPriest Guide",
        "source_family": "guide",
        "retrieved_at": "2026-07-07T10:00:00Z",
        "claims": claims
        if claims is not None
        else [
            {
                "claim_kind": "card_role",
                "cards": ["SW_446"],
                "reason": "Voidtouched Attendant increases hero damage pressure.",
                "source_confidence": "high",
            }
        ],
    }
    document.update(overrides)
    return document


def test_public_https_source_ref_checker():
    assert source_ref_is_public_https("https://example.com/guide")
    assert not source_ref_is_public_https("http://example.com/guide")
    assert not source_ref_is_public_https("fixture://local")
    assert not source_ref_is_public_https("https://localhost/guide")


def test_verifier_accepts_specific_public_source_document():
    report = verify_source_documents(
        [
            {
                "source_url": "https://example.com/shadowpriest-guide",
                "source_title": "ShadowPriest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T10:00:00Z",
                "claims": [
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["NX2_019"],
                        "stance": "prefer_enemy_hero",
                        "runtime_block": "BeforePlayCardBonus",
                        "evidence_text_short": "Mind Sear is used as face burn in aggressive Shadow Priest.",
                        "source_confidence": "high",
                    }
                ],
            }
        ]
    )

    assert report["status"] == "passed"
    assert report["summary"]["claim_count"] == 1
    assert report["summary"]["runtime_lowering_claims"] == 1
    assert report["warnings"] == []


def test_verifier_accepts_reason_only_source_document():
    report = verify_source_documents(
        [
            {
                "source_url": "https://example.com/shadowpriest-guide",
                "source_title": "ShadowPriest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T10:00:00Z",
                "claims": [
                    {
                        "claim_kind": "card_role",
                        "cards": ["SW_446"],
                        "reason": "Voidtouched Attendant increases hero damage pressure.",
                        "source_confidence": "high",
                    }
                ],
            }
        ]
    )

    assert report["status"] == "passed"
    assert report["summary"]["claim_count"] == 1
    assert report["warnings"] == []
    assert report["claims"][0]["status"] == "passed"


def test_verifier_flags_weak_runtime_lowering_claim():
    document = {
        "source_url": "https://example.com/weak-guide",
        "source_title": "Weak Guide",
        "source_family": "guide",
        "retrieved_at": "2026-07-07T10:00:00Z",
        "claims": [
            {
                "claim_kind": "targeting_rule",
                "cards": [],
                "runtime_block": "NotARealBlock",
                "evidence_text_short": "",
                "source_confidence": "low",
            }
        ],
    }
    report = verify_source_documents([document])

    assert report["status"] == "warnings"
    reasons = {warning["reason"] for warning in report["warnings"]}
    assert "claim_missing_cards" in reasons
    assert "claim_missing_evidence_text_short" in reasons
    assert "unsupported_runtime_block" in reasons
    assert "low_confidence_runtime_lowering" in reasons


def test_claim_evidence_status_returns_claim_level_details():
    row = claim_evidence_status(
        {
            "claim_kind": "card_role",
            "cards": ["SW_446"],
            "evidence_text_short": "Voidtouched Attendant increases hero damage pressure.",
            "source_confidence": "medium",
        },
        {"source_url": "https://example.com/source", "source_family": "guide"},
    )

    assert row["claim_kind"] == "card_role"
    assert row["cards"] == ["SW_446"]
    assert row["status"] == "passed"


def test_verifier_warns_when_document_source_title_is_missing():
    report = verify_source_documents([_base_document(source_title="")])

    assert report["status"] == "warnings"
    assert "source_title_missing" in {warning["reason"] for warning in report["warnings"]}


def test_verifier_warns_when_document_source_family_is_missing():
    report = verify_source_documents([_base_document(source_family="")])

    assert report["status"] == "warnings"
    assert "source_family_missing" in {warning["reason"] for warning in report["warnings"]}


def test_verifier_warns_when_document_source_family_is_unsupported():
    report = verify_source_documents([_base_document(source_family="private_fixture")])

    assert report["status"] == "warnings"
    assert "unsupported_source_family" in {warning["reason"] for warning in report["warnings"]}


def test_verifier_warns_when_document_retrieved_at_is_missing():
    report = verify_source_documents([_base_document(retrieved_at="")])

    assert report["status"] == "warnings"
    assert "retrieved_at_missing" in {warning["reason"] for warning in report["warnings"]}


def test_verifier_warns_when_claim_source_refs_are_not_public_https():
    report = verify_source_documents(
        [
            _base_document(
                claims=[
                    {
                        "claim_kind": "card_role",
                        "cards": ["SW_446"],
                        "reason": "Voidtouched Attendant increases hero damage pressure.",
                        "source_confidence": "high",
                        "source_refs": [
                            "fixture://shadowpriest",
                            "http://example.com/not-public",
                            "https://localhost/private",
                            "https://10.0.0.5/private",
                        ],
                    }
                ]
            )
        ]
    )

    assert report["status"] == "warnings"
    warnings = [warning for warning in report["warnings"] if warning["reason"] == "claim_source_ref_not_public_https"]
    assert {warning["source_ref"] for warning in warnings} == {
        "fixture://shadowpriest",
        "http://example.com/not-public",
        "https://localhost/private",
        "https://10.0.0.5/private",
    }


def test_verifier_warns_when_runtime_lowering_claim_lacks_actionable_specificity():
    report = verify_source_documents(
        [
            _base_document(
                claims=[
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["SW_446"],
                        "runtime_block": "BeforePlayCardBonus",
                        "evidence_text_short": "Voidtouched Attendant should support the damage plan.",
                        "source_confidence": "high",
                    }
                ]
            )
        ]
    )

    assert report["status"] == "warnings"
    assert "runtime_lowering_claim_lacks_actionable_specificity" in {
        warning["reason"] for warning in report["warnings"]
    }


def test_verifier_treats_top_level_target_scope_as_actionable_specificity():
    report = verify_source_documents(
        [
            _base_document(
                claims=[
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["TARGET_001"],
                        "runtime_block": "BeforeBattlecryTargetBonus",
                        "target_scope": "Enemy Hero",
                        "evidence_text_short": "This Battlecry should target the opposing hero.",
                        "source_confidence": "high",
                    }
                ]
            )
        ]
    )

    assert "runtime_lowering_claim_lacks_actionable_specificity" not in {
        warning["reason"] for warning in report["warnings"]
    }


def test_verifier_warns_for_suspicious_exact_keep_on_non_hand_effect():
    report = verify_source_documents(
        [
            _base_document(
                claims=[
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_448"],
                        "roles": ["start_of_game", "hero_power_transform"],
                        "evidence_text_short": "Darkbishop Benedictus starts the game with Mind Spike.",
                        "source_confidence": "high",
                    }
                ]
            )
        ]
    )

    assert report["status"] == "warnings"
    assert "suspicious_mulligan_keep_non_hand_effect" in {
        warning["reason"] for warning in report["warnings"]
    }


def test_verifier_does_not_warn_for_explicit_opening_hand_keep_language():
    report = verify_source_documents(
        [
            _base_document(
                claims=[
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["EX1_001"],
                        "roles": ["mulligan_anchor"],
                        "evidence_text_short": "Always keep this one-drop in the mulligan.",
                        "source_confidence": "high",
                    }
                ]
            )
        ]
    )

    assert "suspicious_mulligan_keep_non_hand_effect" not in {
        warning["reason"] for warning in report["warnings"]
    }


def test_verifier_accepts_mulligan_timing_qualifier_as_opening_hand_evidence():
    for semantic_qualifiers in (
        {"timing": "mulligan", "zone_scope": "deck"},
        {"timing": "mulligan", "state_requirements": ["hero_power_transform"]},
    ):
        report = verify_source_documents(
            [
                _base_document(
                    claims=[
                        {
                            "claim_kind": "mulligan_keep",
                            "claim_readiness": "guide_backed",
                            "trust_ceiling": "runtime_candidate",
                            "cards": ["SW_448"],
                            "semantic_qualifiers": semantic_qualifiers,
                            "evidence_text_short": "This card enables the plan.",
                            "source_confidence": "high",
                        }
                    ]
                )
            ]
        )

        assert "suspicious_mulligan_keep_non_hand_effect" not in {
            warning["reason"] for warning in report["warnings"]
        }


def test_verifier_warns_for_non_hand_semantic_qualifier_keep_without_opening_evidence():
    for semantic_qualifiers in (
        {"deck_evaluation": "highlander"},
        {"generation_scope": "generated"},
    ):
        report = verify_source_documents(
            [
                _base_document(
                    claims=[
                        {
                            "claim_kind": "mulligan_keep",
                            "cards": ["NON_HAND_EFFECT"],
                            "semantic_qualifiers": semantic_qualifiers,
                            "evidence_text_short": "This card enables the plan.",
                            "source_confidence": "high",
                        }
                    ]
                )
            ]
        )

        assert "suspicious_mulligan_keep_non_hand_effect" in {
            warning["reason"] for warning in report["warnings"]
        }


def test_verifier_warns_for_top_level_non_hand_qualifier_keep_without_opening_evidence():
    for qualifier in (
        {"deck_evaluation": "No Duplicates"},
        {"generation_scope": "Generated Card"},
    ):
        report = verify_source_documents(
            [
                _base_document(
                    claims=[
                        {
                            "claim_kind": "mulligan_keep",
                            "cards": ["NON_HAND_EFFECT"],
                            "evidence_text_short": "This card enables the plan.",
                            "source_confidence": "high",
                            **qualifier,
                        }
                    ]
                )
            ]
        )

        assert "suspicious_mulligan_keep_non_hand_effect" in {
            warning["reason"] for warning in report["warnings"]
        }


def test_verifier_accepts_mulligan_timing_for_non_hand_semantic_qualifier_keeps():
    for semantic_qualifiers in (
        {"timing": "mulligan", "deck_evaluation": "highlander"},
        {"timing": "mulligan", "generation_scope": "generated"},
    ):
        report = verify_source_documents(
            [
                _base_document(
                    claims=[
                        {
                            "claim_kind": "mulligan_keep",
                            "cards": ["NON_HAND_EFFECT"],
                            "semantic_qualifiers": semantic_qualifiers,
                            "evidence_text_short": "This card enables the plan.",
                            "source_confidence": "high",
                        }
                    ]
                )
            ]
        )

        assert "suspicious_mulligan_keep_non_hand_effect" not in {
            warning["reason"] for warning in report["warnings"]
        }


def test_verifier_accepts_top_level_mulligan_timing_for_non_hand_qualifier_keeps():
    for qualifier in (
        {"timing": "Opening Hand", "deck_evaluation": "No Duplicates"},
        {"timing": "mulligan", "generation_scope": "Generated Card"},
    ):
        report = verify_source_documents(
            [
                _base_document(
                    claims=[
                        {
                            "claim_kind": "mulligan_keep",
                            "cards": ["NON_HAND_EFFECT"],
                            "evidence_text_short": "This card enables the plan.",
                            "source_confidence": "high",
                            **qualifier,
                        }
                    ]
                )
            ]
        )

        assert "suspicious_mulligan_keep_non_hand_effect" not in {
            warning["reason"] for warning in report["warnings"]
        }


def test_verifier_warns_for_non_list_start_of_game_role_payloads():
    report = verify_source_documents(
        [
            _base_document(
                claims=[
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_448"],
                        "roles": "start_of_game",
                        "semantic_families": ("hero_power_transform",),
                        "evidence_text_short": "Darkbishop Benedictus starts the game with Mind Spike.",
                        "source_confidence": "high",
                    }
                ]
            )
        ]
    )

    assert "suspicious_mulligan_keep_non_hand_effect" in {
        warning["reason"] for warning in report["warnings"]
    }
