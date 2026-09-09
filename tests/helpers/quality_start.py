"""Consistent synthetic quality inputs; never an operator run or relabelled v2."""

import pytest

from hsconfig.card_snapshot import build_card_snapshot
from hsconfig.card_metadata import (
    analysis_cards_from_deck_identity,
    hydrate_card_metadata,
)
from hsconfig.semantic_enrichment import enrich_card_metadata
from hsconfig.input_snapshot_manifest import freeze_compiler_inputs
from hsconfig.live_start_research import build_research_request, build_research_result
from hsconfig.operator_profile import (
    derive_deck_output_binding,
    enable_operator_profile,
)
from hsconfig.package_request import FrozenJsonDocument, PackageResolutionSnapshot
from hsconfig.starter_context import build_quality_starter_context
from tests.helpers.audited_package_request import (
    audited_request_with_frozen_input_projections,
)


def quality_frozen_inputs(tmp_path, monkeypatch):
    request, projections = audited_request_with_frozen_input_projections(
        tmp_path, "ShadowPriest"
    )
    main_ids = {row["card_id"] for row in projections["deck"]["deck_identity"]["cards"]}
    snapshot = build_card_snapshot(
        [
            {**row, "collectible": row["id"] in main_ids}
            for row in projections["full_cards"]
        ],
        captured_at="2026-09-09T00:00:00Z",
    ).to_value()
    projections["full_cards"] = snapshot["full_cards"]
    projections["collectible_cards"] = snapshot["collectible_cards"]
    preconfig = request.snapshot.general_preconfig.to_value()
    metadata = hydrate_card_metadata(
        cards=analysis_cards_from_deck_identity(preconfig["deck_identity"]),
        source_records={row["id"]: row for row in snapshot["full_cards"]},
    )
    preconfig["card_metadata"] = {
        "cards": enrich_card_metadata(
            metadata,
            hearthstonejson_cards=snapshot["full_cards"],
        )["cards"]
    }
    captured = PackageResolutionSnapshot.from_strict(
        request.snapshot.strict_build_context, preconfig
    )
    research_request = build_research_request(
        run_id="quality-fixture",
        deck_identity=projections["deck"]["deck_identity"],
        captured_input_sha256=snapshot["dataset_sha256"],
        queries=(),
    )
    research = build_research_result(
        acquired={},
        discovery_outcome="unavailable",
        attempts=[],
        deadline_utc=None,
        card_metadata={},
    )
    quality = FrozenJsonDocument.from_value(
        {
            "card_snapshot_sha256": snapshot["dataset_sha256"],
            "card_snapshot_captured_at": snapshot["captured_at"],
            "card_snapshot_upstream_version": snapshot["upstream_version"],
            "research_request_sha256": research_request.to_value()["content_sha256"],
            "research_result": research.to_value(),
        }
    )
    for name in ("local-app-data", "runtime", "outputs"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    profile = enable_operator_profile(
        runtime_root=tmp_path / "runtime",
        output_base_root=tmp_path / "outputs",
        expected_predecessor_sha256=None,
    )
    return freeze_compiler_inputs(
        snapshot=captured,
        **projections,
        bound_date="2026-09-09",
        runtime_grammar_version="visionai-runtime-v1",
        compiler_contract_id="hsconfig-live-start-v2",
        operator_profile=profile,
        deck_output_binding=derive_deck_output_binding(profile, "ShadowPriest"),
        quality_inputs=quality,
    )


@pytest.fixture
def quality_shadowpriest_context(tmp_path, monkeypatch):
    return build_quality_starter_context(quality_frozen_inputs(tmp_path, monkeypatch))
