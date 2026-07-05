from hsconfig.guide_research import normalize_source_claims


def test_normalize_source_claims_is_deterministic_and_source_backed():
    first = {
        "source": "guide",
        "url": "https://example.invalid/deck",
        "claim": "Always keep Shadowbomber and push face damage early.",
        "cards": ["EX1_001", "EX1_001"],
        "claim_type": "mulligan_and_gameplan",
    }
    second = {
        "source": "stats",
        "url": "https://example.invalid/stats",
        "claim": "Use Voidtouched Attendant with Shadowbomber for burst turns.",
        "cards": ["EX1_002", "EX1_001"],
        "claim_type": "combo",
    }

    left = normalize_source_claims([second, first])
    right = normalize_source_claims([first, second])

    assert left == right
    assert [claim["claim_id"] for claim in left["claims"]] == sorted(
        claim["claim_id"] for claim in left["claims"]
    )
    assert left["claims"][0]["confidence"] == "source_backed"
    assert left["claims"][0]["cards"] == list(dict.fromkeys(left["claims"][0]["cards"]))


def test_normalize_source_claims_preserves_combo_card_order():
    claims = normalize_source_claims(
        [
            {
                "source": "guide",
                "claim": "Play setup before payoff.",
                "cards": ["ZZZ_002", "AAA_001", "ZZZ_002"],
                "claim_type": "combo",
            }
        ]
    )

    assert claims["claims"][0]["cards"] == ["ZZZ_002", "AAA_001"]


def test_normalize_source_claims_deduplicates_identical_claims():
    raw_claim = {
        "source": "guide",
        "url": "https://example.invalid/deck",
        "claim": "Never keep expensive refill cards in the opener.",
        "cards": ["EX1_003"],
        "claim_type": "bad_pattern",
    }

    claims = normalize_source_claims([raw_claim, dict(raw_claim)])

    assert claims["claim_count"] == 1
    assert claims["claims"][0]["claim_id"].startswith("claim_")
