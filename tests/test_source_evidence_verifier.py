from hsconfig.source_evidence_verifier import (
    claim_evidence_status,
    source_ref_is_public_https,
    verify_source_documents,
)


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
