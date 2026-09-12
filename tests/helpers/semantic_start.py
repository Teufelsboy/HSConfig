"""Offline semantic-v3 inputs built from source rows, never relabelled authority."""

from hsconfig.card_snapshot import build_card_snapshot
from hsconfig.card_metadata import analysis_cards_from_deck_identity, hydrate_card_metadata
from hsconfig.semantic_enrichment import enrich_card_metadata
from hsconfig.input_snapshot_manifest import freeze_compiler_inputs
from hsconfig.live_start_research import build_research_request, build_research_result
from hsconfig.operator_profile import derive_deck_output_binding, enable_operator_profile
from hsconfig.package_request import FrozenJsonDocument, PackageResolutionSnapshot
from tests.helpers.audited_package_request import audited_request_with_frozen_input_projections


def semantic_frozen_inputs(
    tmp_path, monkeypatch, *, captured_at="2026-09-09T00:00:00Z",
    upstream_version=None, compiler_contract_id="hsconfig-live-start-v3",
    transform_rows=None,
):
    request, projections = audited_request_with_frozen_input_projections(
        tmp_path, "ShadowPriest"
    )
    main_ids = {row["card_id"] for row in projections["deck"]["deck_identity"]["cards"]}
    raw_rows = [
        {**row, "collectible": row["id"] in main_ids}
        for row in projections["full_cards"]
    ]
    if transform_rows is not None:
        raw_rows = transform_rows(raw_rows, main_ids)
    snapshot = build_card_snapshot(
        raw_rows, captured_at=captured_at, upstream_version=upstream_version
    ).to_value()
    projections["full_cards"] = snapshot["full_cards"]
    projections["collectible_cards"] = snapshot["collectible_cards"]
    preconfig = request.snapshot.general_preconfig.to_value()
    projections["source_acquisition"] = {
        **projections["source_acquisition"], "policy_profile": preconfig["policy_profile"]
    }
    metadata = hydrate_card_metadata(
        cards=analysis_cards_from_deck_identity(preconfig["deck_identity"]),
        source_records={row["id"]: row for row in snapshot["full_cards"]},
    )
    preconfig["card_metadata"] = {
        "cards": enrich_card_metadata(
            metadata, hearthstonejson_cards=snapshot["full_cards"]
        )["cards"]
    }
    captured = PackageResolutionSnapshot.from_strict(
        request.snapshot.strict_build_context, preconfig
    )
    research_request = build_research_request(
        run_id="semantic-fixture",
        deck_identity=projections["deck"]["deck_identity"],
        captured_input_sha256=snapshot["dataset_sha256"], queries=(),
    )
    research = build_research_result(
        acquired={}, discovery_outcome="unavailable", attempts=[],
        deadline_utc=None, card_metadata={},
    )
    quality = FrozenJsonDocument.from_value({
        "card_snapshot_sha256": snapshot["dataset_sha256"],
        "card_snapshot_captured_at": snapshot["captured_at"],
        "card_snapshot_upstream_version": snapshot["upstream_version"],
        "research_request_sha256": research_request.to_value()["content_sha256"],
        "research_result": research.to_value(),
    })
    for name in ("local-app-data", "runtime", "outputs"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    profile = enable_operator_profile(
        runtime_root=tmp_path / "runtime", output_base_root=tmp_path / "outputs",
        expected_predecessor_sha256=None,
    )
    return freeze_compiler_inputs(
        snapshot=captured, **projections, bound_date="2026-09-09",
        runtime_grammar_version="visionai-runtime-v1",
        compiler_contract_id=compiler_contract_id, operator_profile=profile,
        deck_output_binding=derive_deck_output_binding(profile, "ShadowPriest"),
        quality_inputs=quality,
    )


def normalized_owner_context(source=None, *, linked=None, sideboard=False):
    """Exercise normalizer and facts projector for focused pure-policy cases."""
    from hsconfig.starter_card_facts import project_card_facts

    raw = {"id": "TEST_001", "dbfId": 1, "name": "Owner", "type": "MINION"}
    if source is not None:
        raw.update(source)
    deck = {"cards": [{"card_id": raw["id"], "count": 1}]}
    rows = [raw]
    if linked is not None:
        rows.append(linked)
    if sideboard:
        rows.append({"id": "TEST_002", "dbfId": 2, "name": "Main", "type": "MINION"})
        deck = {
            "cards": [{"card_id": "TEST_002", "count": 1}],
            "sideboards": [{"owner_card_id": "TEST_002", "sideboard_index": 1,
                            "cards": [{"card_id": raw["id"], "count": 1}]}],
        }
    snapshot = build_card_snapshot(rows, captured_at="offline capture")
    return {"schema_version": 4, **project_card_facts(deck, snapshot.to_value()["full_cards"])}
