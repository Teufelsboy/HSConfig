"""Real offline semantic manifest construction and physical binding tests."""

from dataclasses import replace
from hashlib import sha256

import pytest

from hsconfig.card_snapshot import build_card_snapshot
from hsconfig.card_metadata import (
    analysis_cards_from_deck_identity,
    hydrate_card_metadata,
)
from hsconfig.semantic_enrichment import enrich_card_metadata
from hsconfig.input_snapshot_manifest import freeze_compiler_inputs
from hsconfig import input_snapshot_manifest as manifests
from hsconfig.live_start_research import build_research_request, build_research_result
from hsconfig.operator_profile import (
    derive_deck_output_binding,
    enable_operator_profile,
)
from hsconfig.package_request import FrozenJsonDocument, PackageResolutionSnapshot
from tests.helpers.audited_package_request import (
    audited_request_with_frozen_input_projections,
)


def semantic_frozen_inputs(
    tmp_path, monkeypatch, *, compiler="hsconfig-live-start-v3", include_quality=True
):
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
    projections["source_acquisition"] = {
        **projections["source_acquisition"],
        "policy_profile": preconfig["policy_profile"],
    }
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
        compiler_contract_id=compiler,
        operator_profile=profile,
        deck_output_binding=derive_deck_output_binding(profile, "ShadowPriest"),
        quality_inputs=quality if include_quality else None,
    )


@pytest.fixture
def semantic_frozen(tmp_path, monkeypatch):
    return semantic_frozen_inputs(tmp_path, monkeypatch)


def test_semantic_manifest_has_exact_new_tuple(tmp_path, monkeypatch):
    semantic_frozen = semantic_frozen_inputs(tmp_path, monkeypatch)
    value = semantic_frozen.manifest.document.to_value()
    assert value["schema_version"] == 3
    assert value["compiler_inputs"]["compiler_contract_id"] == "hsconfig-live-start-v3"
    assert value["compiler_inputs"]["runtime_grammar_version"] == "visionai-runtime-v1"
    assert semantic_frozen.quality_inputs is not None
    assert len(value["compiler_inputs"]["blobs"]) == 7


def test_semantic_freezer_requires_quality(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="quality"):
        semantic_frozen_inputs(tmp_path, monkeypatch, include_quality=False)


@pytest.mark.parametrize(
    "version,compiler",
    [
        (3, "hsconfig-live-start-v2"),
        (True, "hsconfig-live-start-v3"),
        (4, "hsconfig-live-start-v3"),
    ],
)
def test_semantic_manifest_rejects_mixed_or_invalid_version(
    semantic_frozen, version, compiler
):
    value = semantic_frozen.manifest.document.to_value()
    value["schema_version"] = version
    value["compiler_inputs"]["compiler_contract_id"] = compiler
    value.pop("content_sha256")
    # Canonical resealing makes rejection about the closed route, not stale bytes.
    value["content_sha256"] = (
        "sha256:"
        + sha256(FrozenJsonDocument.from_value(value).canonical_json).hexdigest()
    )
    with pytest.raises(ValueError):
        manifests.validate_input_snapshot_manifest_document(
            FrozenJsonDocument.from_value(value)
        )


@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_semantic_frozen_rechecks_quality_blob(semantic_frozen, mutation):
    quality = None
    if mutation == "tampered":
        value = semantic_frozen.quality_inputs.to_value()
        value["card_snapshot_captured_at"] = "2026-09-10T00:00:00Z"
        quality = FrozenJsonDocument.from_value(value)
    with pytest.raises(ValueError):
        manifests._require_manifest_blob_match(
            replace(semantic_frozen, quality_inputs=quality)
        )
