from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.source_acquisition import collect_public_source_records
from hsconfig.source_claim_compiler import compile_source_search_records
from hsconfig.source_autopilot import build_source_autopilot_bundle


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _shadow_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    del timeout_seconds
    html = """
    <html>
      <head>
        <meta property="article:published_time" content="2026-07-15T00:00:00Z">
        <title>Shadow Priest Mulligan Guide 2026</title>
      </head>
      <body>
        <p>Published July 15, 2026.</p>
        <p>Mulligan: keep Papercraft Angel, Twilight Deceptor, Raise Dead, and Shadowbomber.</p>
        <p>Do not keep any 4 cost or higher cards.</p>
        <p>Darkbishop Benedictus enables the Shadow hero power. Mind Spike can go face or clear enemy minions.</p>
        <p>Use the Mind Spike pressure plan as a runtime posture overlay for face and board decisions.</p>
      </body>
    </html>
    """
    return 200, "text/html", html.encode("utf-8")


def _resolver(hostname: str) -> list[str]:
    assert hostname == "example.test"
    return ["93.184.216.34"]


def test_shadowpriest_full_source_chain_promotes_without_benedictus_keep():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
            {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
            {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
        ],
    }
    acquired = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=["https://example.test/shadow-guide"],
        current_date="2026-07-15",
        fetcher=_shadow_fetcher,
        resolver=_resolver,
    )
    compiled = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        acquired_records=acquired["source_records"],
        current_date="2026-07-15",
    )
    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_search_records=compiled["records"],
        current_date="2026-07-15",
    )

    rows = bundle["source_evidence_rows"]
    keep_cards = {
        card_id
        for row in rows
        if row["claim_kind"] == "mulligan_keep"
        for card_id in row["cards"]
    }
    effect_cards = {
        card_id
        for row in rows
        if row["claim_kind"] == "hero_power_transform"
        for card_id in row["cards"]
    }

    assert {"TOY_381", "SW_444", "SCH_514", "GVG_009"} <= keep_cards
    assert "SW_448" not in keep_cards
    assert "SW_448" in effect_cards
    report = bundle["source_autopilot_report"]
    summary = report["strong_closure_summary"]
    assert summary["technical_no_block"] is True
    assert summary["source_backed_strong_ready"] is True
    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert summary["first_missing_source_action"] == "none"
    assert report["first_missing_source_action"] == summary["first_missing_source_action"]


def _decklist_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    del timeout_seconds
    html = """
    <html>
      <head><title>Wild Pirate Demon Hunter Decklist 2026</title></head>
      <body><p>Deck code: AAEBA-example</p><ul><li>Patches the Pirate</li></ul></body>
    </html>
    """
    return 200, "text/html", html.encode("utf-8")


def test_decklist_only_builds_evidence_but_cannot_promote_strong():
    deck_identity = {
        "deck_name": "PirateDH",
        "deck_slug": "piratedh",
        "deck_code_hash": "sha256:pirate",
        "cards": [{"card_id": "CFM_637", "name": "Patches the Pirate", "cost": 1, "count": 1}],
    }
    acquired = collect_public_source_records(
        deck_name="PirateDH",
        deck_identity=deck_identity,
        source_urls=["https://example.test/pirate-dh-list"],
        current_date="2026-07-15",
        fetcher=_decklist_fetcher,
        resolver=_resolver,
    )
    compiled = compile_source_search_records(
        deck_name="PirateDH",
        deck_identity=deck_identity,
        acquired_records=acquired["source_records"],
        current_date="2026-07-15",
    )
    bundle = build_source_autopilot_bundle(
        deck_name="PirateDH",
        deck_identity=deck_identity,
        source_search_records=compiled["records"],
        current_date="2026-07-15",
    )

    summary = bundle["source_autopilot_report"]["strong_closure_summary"]
    assert summary["technical_no_block"] is True
    assert summary["source_backed_strong_ready"] is False
    assert summary["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert summary["first_missing_source_action"] == "add_current_card_specific_runtime_source"
    assert bundle["source_autopilot_report"]["first_missing_source_action"] == summary["first_missing_source_action"]


def test_current_shadowpriest_guide_can_close_aggro_profile_without_extra_apply_surface(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )
    package_dir = tmp_path / "ShadowPriest"

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
            str(package_dir),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )
    capsys.readouterr()

    summary = json.loads(
        (package_dir / "reports" / "operator_summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    closure = summary["source_backed_strong_closure"]
    assert closure["closure_profile"] == "aggro_burn_hero_power"
    assert closure["closure_profile_closed"] is True
    assert closure["closure_profile_first_missing_link"] == "none"
    assert closure["default_only_runtime_surfaces"] == []
