from __future__ import annotations

from hsconfig.source_closure_intake import build_source_closure_intake_receipt


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
BIG_SHAMAN_CODE = (
    "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbG"
    "pgakpwb44gas/QYAAA=="
)
MECH_PALA_CODE = (
    "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8"
    "Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="
)


def test_shadowpriest_receipt_is_diagnostic_and_current_source_ready():
    receipt = build_source_closure_intake_receipt("ShadowPriest", SHADOWPRIEST_CODE)

    assert receipt["schema_version"] == 1
    assert receipt["authority"] == "diagnostic_only"
    assert receipt["source_status_apply_blocking"] is False
    assert receipt["first_missing_source_action"] == "none"
    assert any("hearthpwn.com" in url for url in receipt["used_urls"])
    assert receipt["promotion_eligible_seed_count"] >= 1


def test_big_shaman_current_seed_still_preserves_aggregate_partial_action():
    receipt = build_source_closure_intake_receipt("BigShaman", BIG_SHAMAN_CODE)

    assert receipt["authority"] == "diagnostic_only"
    assert receipt["source_status_apply_blocking"] is False
    assert receipt["first_missing_source_action"] == (
        "add_current_big_shaman_full_text_mulligan_or_gameplan_source"
    )
    assert receipt["promotion_eligible_seed_count"] == 1
    assert receipt["source_rows"][0]["first_missing_source_action"] == "none"
    assert receipt["source_rows"][0]["promotion_eligible_seed"] is True
    assert any(
        row["first_missing_source_action"]
        == "add_current_big_shaman_full_text_mulligan_or_gameplan_source"
        for row in receipt["source_rows"][1:]
    )


def test_context_only_rows_do_not_become_runtime_claims():
    receipt = build_source_closure_intake_receipt("MechPala", MECH_PALA_CODE)

    context_only_rows = [
        row
        for row in receipt["source_rows"]
        if row["strength_ceiling"] == "context_only"
    ]

    assert context_only_rows
    assert all(row["expected_claim_kinds"] == [] for row in context_only_rows)
    assert all(not row["promotion_eligible_seed"] for row in context_only_rows)
    assert receipt["source_status_apply_blocking"] is False


def test_receipt_records_fetched_record_count_without_fetching_network():
    receipt = build_source_closure_intake_receipt(
        "ShadowPriest",
        SHADOWPRIEST_CODE,
        fetched_records=(
            {"url": "https://example.test/a", "status": "ok"},
            {"url": "https://example.test/b", "status": "skipped"},
        ),
    )

    assert receipt["fetched_record_count"] == 2
    assert receipt["authority"] == "diagnostic_only"
