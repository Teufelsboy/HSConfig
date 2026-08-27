from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import hsconfig.optimized_start_authority as optimized_authority
from hsconfig.configuration_mode import (
    optimized_start_authority_schema_from_manifest,
)
from hsconfig.input_snapshot_manifest import (
    FrozenCompilerInputs,
    freeze_compiler_inputs,
)
from hsconfig.operator_profile import (
    derive_deck_output_binding,
    enable_operator_profile,
)
from hsconfig.optimized_start_authority import (
    ValidatedSingleStarterApproval,
    load_optimized_start_authority,
)
from hsconfig.package_request import (
    FrozenJsonDocument,
    PackageResolutionSnapshot,
    ResolvedPackageRequest,
)
from hsconfig.starter_candidate import (
    ValidatedStarterCandidate,
    validate_starter_candidate,
)
from hsconfig.starter_context import (
    StarterContext,
    build_single_candidate_starter_context,
)
from hsconfig.starter_contract import (
    SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    STARTER_REVIEW_FIELDS,
)
from hsconfig.starter_decision import ValidatedStarterSelection
from hsconfig.starter_document import StarterDocument, seal_starter_document
from hsconfig.visionai_registry import (
    LEGACY_OPTIMIZED_START_REPORT_PATHS,
    SINGLE_CANDIDATE_REVIEW_REPORT_PATHS,
    optimized_start_report_paths_for_manifest,
)
from tests.helpers.audited_package_request import (
    audited_request_with_frozen_input_projections,
)
from tests.starter_fixtures import build_shadowpriest_starter_fixture
from tests.test_starter_candidate import sealed_single_candidate


LEGACY_MANIFEST = {"configuration_mode": "LLM_OPTIMIZED_START"}
SINGLE_CANDIDATE_MANIFEST = {
    "configuration_mode": "LLM_OPTIMIZED_START",
    "optimized_start_authority_schema": "single_candidate_review_v1",
}


@dataclass(frozen=True, slots=True)
class _SingleCandidateAuthorityFixture:
    report_root: Path
    request: ResolvedPackageRequest
    snapshot: PackageResolutionSnapshot
    frozen: FrozenCompilerInputs
    context: StarterContext
    candidate: ValidatedStarterCandidate
    review: StarterDocument


def _build_single_candidate_authority(
    root: Path,
    *,
    review_status: str = "approved",
) -> _SingleCandidateAuthorityFixture:
    request, projections = audited_request_with_frozen_input_projections(
        root / "audited",
        "ShadowPriest",
    )
    preconfig = request.snapshot.general_preconfig.to_value()
    local_app_data = root / "local-app-data"
    runtime_root = root / "runtime"
    output_base_root = root / "outputs"
    for path in (local_app_data, runtime_root, output_base_root):
        path.mkdir(parents=True)
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        profile = enable_operator_profile(
            runtime_root=runtime_root,
            output_base_root=output_base_root,
            expected_predecessor_sha256=None,
        )
        frozen = freeze_compiler_inputs(
            snapshot=request.snapshot,
            deck=projections["deck"],
            full_cards=projections["full_cards"],
            collectible_cards=projections["collectible_cards"],
            source_acquisition=projections["source_acquisition"],
            source_documents=projections["source_documents"],
            globalvalues_baseline=projections["globalvalues_baseline"],
            bound_date="2026-08-25",
            runtime_grammar_version="visionai-runtime-v1",
            compiler_contract_id="hsconfig-live-start-v1",
            operator_profile=profile,
            deck_output_binding=derive_deck_output_binding(
                profile,
                str(preconfig["deck_identity"]["deck_name"]),
            ),
        )
    context = build_single_candidate_starter_context(frozen)
    candidate = validate_starter_candidate(
        sealed_single_candidate(context),
        context=context,
    )
    revision_requests = (
        []
        if review_status == "approved"
        else [
            {
                "code": "revise-candidate",
                "target": "whole_candidate",
                "message": "Revise the bounded lead candidate.",
            }
        ]
    )
    review = seal_starter_document(
        {
            "schema_version": SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
            "review_id": "review-1",
            "review_status": review_status,
            "confidence": "high",
            "starter_context_sha256": context.document.content_sha256,
            "candidate_id": candidate.candidate_id,
            "candidate_revision": candidate.candidate_revision,
            "candidate_sha256": candidate.document.content_sha256,
            "revision_requests": revision_requests,
            "review_summary": "The lead candidate is coherent and bounded.",
        },
        expected_fields=STARTER_REVIEW_FIELDS,
        schema_version=SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    )
    report_root = root / "authority"
    report_root.mkdir()
    documents = {
        "input_snapshot_manifest.json": frozen.manifest.document.canonical_json,
        "starter_context.json": context.document.canonical_json,
        "starter_config_candidate.json": candidate.document.canonical_json,
        "starter_config_review.json": review.canonical_json,
    }
    for name, content in documents.items():
        (report_root / name).write_bytes(content)
    return _SingleCandidateAuthorityFixture(
        report_root=report_root,
        request=request,
        snapshot=request.snapshot,
        frozen=frozen,
        context=context,
        candidate=candidate,
        review=review,
    )


def test_conservative_manifest_forbids_optimized_authority_discriminator() -> None:
    assert optimized_start_authority_schema_from_manifest({}) is None
    assert (
        optimized_start_report_paths_for_manifest({}) == ()
    )
    with pytest.raises(
        ValueError,
        match="^optimized_start_authority_schema_forbidden$",
    ):
        optimized_start_authority_schema_from_manifest(
            {
                "configuration_mode": "CONSERVATIVE",
                "optimized_start_authority_schema": (
                    "single_candidate_review_v1"
                ),
            }
        )


def test_legacy_optimized_manifest_omits_discriminator_and_requires_five_docs(
    tmp_path: Path,
) -> None:
    root = tmp_path / "legacy"
    fixture = build_shadowpriest_starter_fixture(root)

    assert (
        optimized_start_authority_schema_from_manifest(LEGACY_MANIFEST)
        == "legacy_five_doc"
    )
    assert optimized_start_report_paths_for_manifest(LEGACY_MANIFEST) is (
        LEGACY_OPTIMIZED_START_REPORT_PATHS
    )
    authority = load_optimized_start_authority(
        report_root=root,
        manifest=LEGACY_MANIFEST,
    )
    assert isinstance(authority, ValidatedStarterSelection)
    assert authority == fixture.selection

    (root / Path(LEGACY_OPTIMIZED_START_REPORT_PATHS[1]).name).unlink()
    with pytest.raises(
        ValueError,
        match="^optimized_start_authority_report_set_invalid$",
    ):
        load_optimized_start_authority(
            report_root=root,
            manifest=LEGACY_MANIFEST,
        )


def test_new_optimized_manifest_requires_exact_single_candidate_discriminator() -> None:
    assert (
        optimized_start_authority_schema_from_manifest(
            SINGLE_CANDIDATE_MANIFEST
        )
        == "single_candidate_review_v1"
    )
    assert optimized_start_report_paths_for_manifest(
        SINGLE_CANDIDATE_MANIFEST
    ) is SINGLE_CANDIDATE_REVIEW_REPORT_PATHS

    for invalid in ("legacy_five_doc", "unknown", None, True, 1):
        with pytest.raises(
            ValueError,
            match="^optimized_start_authority_schema_invalid$",
        ):
            optimized_start_authority_schema_from_manifest(
                {
                    "configuration_mode": "LLM_OPTIMIZED_START",
                    "optimized_start_authority_schema": invalid,
                }
            )


def test_unknown_mixed_extra_and_downgraded_authority_sets_fail_closed(
    tmp_path: Path,
) -> None:
    legacy_root = tmp_path / "legacy"
    build_shadowpriest_starter_fixture(legacy_root)

    def assert_rejected_before_semantic_load(
        *,
        report_root: Path,
        manifest: dict[str, object],
        error: str = "optimized_start_authority_report_set_invalid",
    ) -> None:
        with (
            patch.object(
                optimized_authority,
                "load_starter_document",
                side_effect=AssertionError("semantic document load reached"),
            ) as document_loader,
            patch.object(
                optimized_authority,
                "load_validated_starter_selection",
                side_effect=AssertionError("legacy semantic load reached"),
            ) as legacy_loader,
        ):
            with pytest.raises(ValueError, match=f"^{error}$"):
                load_optimized_start_authority(
                    report_root=report_root,
                    manifest=manifest,
                )
            document_loader.assert_not_called()
            legacy_loader.assert_not_called()

    assert_rejected_before_semantic_load(
        report_root=legacy_root,
        manifest={
                "configuration_mode": "LLM_OPTIMIZED_START",
                "optimized_start_authority_schema": "unknown",
        },
        error="optimized_start_authority_schema_invalid",
    )

    missing_path = legacy_root / "candidate-3.json"
    missing_bytes = missing_path.read_bytes()
    missing_path.unlink()
    assert_rejected_before_semantic_load(
        report_root=legacy_root,
        manifest=LEGACY_MANIFEST,
    )
    missing_path.write_bytes(missing_bytes)

    for unexpected in (
        "input_snapshot_manifest.json",
        "notes.txt",
        "unexpected-directory",
    ):
        path = legacy_root / unexpected
        if "." in unexpected:
            path.write_bytes(b"{}")
        else:
            path.mkdir()
        assert_rejected_before_semantic_load(
            report_root=legacy_root,
            manifest=LEGACY_MANIFEST,
        )
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()

    assert_rejected_before_semantic_load(
        report_root=legacy_root,
        manifest=SINGLE_CANDIDATE_MANIFEST,
    )

    new_root = tmp_path / "new"
    new_root.mkdir()
    for relative_path in SINGLE_CANDIDATE_REVIEW_REPORT_PATHS:
        (new_root / Path(relative_path).name).write_bytes(b"{}")
    (new_root / "starter_config_review.json").unlink()
    assert_rejected_before_semantic_load(
        report_root=new_root,
        manifest=SINGLE_CANDIDATE_MANIFEST,
    )


def test_legacy_five_document_fixture_loads_byte_unchanged(
    tmp_path: Path,
) -> None:
    root = tmp_path / "legacy"
    fixture = build_shadowpriest_starter_fixture(root)
    before = {
        path.name: path.read_bytes()
        for path in sorted(root.iterdir(), key=lambda item: item.name)
    }

    authority = load_optimized_start_authority(
        report_root=root,
        manifest=LEGACY_MANIFEST,
    )

    after = {
        path.name: path.read_bytes()
        for path in sorted(root.iterdir(), key=lambda item: item.name)
    }
    assert authority == fixture.selection
    assert before == after
    assert set(before) == set(
        Path(path).name for path in LEGACY_OPTIMIZED_START_REPORT_PATHS
    )
    assert {
        name: sha256(content).hexdigest()
        for name, content in before.items()
    } == {
        "starter_context.json": (
            "5eeb6e3fb64c88cff1e1bf435e0dd516dadbdfe2464915c6740b9582c47a69da"
        ),
        "candidate-1.json": (
            "2ac85ee39aa3bd430b7bdd9431928f82876e22368c7490384875c8011af00c9b"
        ),
        "candidate-2.json": (
            "a44a795c49fffcd3a9d3de269fd3fc6c01c4f2b8f8b548a83601bafd56f66d90"
        ),
        "candidate-3.json": (
            "3b5d882880e184a85b4fb76ff24fc733d44fb858ad49fb53e1e57f28c5767739"
        ),
        "starter_config_decision.json": (
            "1a4560c871aa4825097b410c4e0a8d84d821445f0db49c1855d4dc59e071a26f"
        ),
    }


def test_single_candidate_approval_reseals_every_document(
    tmp_path: Path,
) -> None:
    fixture = _build_single_candidate_authority(tmp_path / "single")

    with (
        patch.object(
            optimized_authority,
            "load_starter_document",
            wraps=optimized_authority.load_starter_document,
        ) as document_loader,
        patch.object(
            optimized_authority,
            "validate_input_snapshot_manifest_document",
            wraps=(
                optimized_authority.validate_input_snapshot_manifest_document
            ),
        ) as snapshot_validator,
        patch.object(
            optimized_authority,
            "validate_starter_context_document",
            wraps=optimized_authority.validate_starter_context_document,
        ) as context_validator,
        patch.object(
            optimized_authority,
            "validate_starter_candidate",
            wraps=optimized_authority.validate_starter_candidate,
        ) as candidate_validator,
        patch.object(
            optimized_authority,
            "validate_starter_review",
            wraps=optimized_authority.validate_starter_review,
        ) as review_validator,
    ):
        authority = load_optimized_start_authority(
            report_root=fixture.report_root,
            manifest=SINGLE_CANDIDATE_MANIFEST,
        )

    assert [call.args[0].name for call in document_loader.call_args_list] == [
        "input_snapshot_manifest.json",
        "starter_context.json",
        "starter_config_candidate.json",
        "starter_config_review.json",
    ]
    snapshot_validator.assert_called_once()
    context_validator.assert_called_once()
    candidate_validator.assert_called_once()
    review_validator.assert_called_once()

    assert isinstance(authority, ValidatedSingleStarterApproval)
    assert authority.snapshot == fixture.frozen.manifest
    assert authority.context == fixture.context
    assert authority.candidate == fixture.candidate
    assert authority.review.document == fixture.review
    assert not hasattr(authority, "__dict__")

    for name in (
        "input_snapshot_manifest.json",
        "starter_context.json",
        "starter_config_candidate.json",
        "starter_config_review.json",
    ):
        path = fixture.report_root / name
        original = path.read_bytes()
        value = FrozenJsonDocument.from_json_bytes(original).to_value()
        value["content_sha256"] = "sha256:" + "0" * 64
        path.write_bytes(FrozenJsonDocument.from_value(value).canonical_json)
        with pytest.raises(ValueError):
            load_optimized_start_authority(
                report_root=fixture.report_root,
                manifest=SINGLE_CANDIDATE_MANIFEST,
            )
        path.write_bytes(original)


def test_single_candidate_approval_rejects_cross_document_rebinding(
    tmp_path: Path,
) -> None:
    first = _build_single_candidate_authority(tmp_path / "first")
    second = _build_single_candidate_authority(tmp_path / "second")

    for name in (
        "input_snapshot_manifest.json",
        "starter_context.json",
        "starter_config_candidate.json",
        "starter_config_review.json",
    ):
        target = first.report_root / name
        original = target.read_bytes()
        target.write_bytes((second.report_root / name).read_bytes())
        with pytest.raises(ValueError):
            load_optimized_start_authority(
                report_root=first.report_root,
                manifest=SINGLE_CANDIDATE_MANIFEST,
            )
        target.write_bytes(original)


def test_revision_requested_review_is_not_durable_compile_authority(
    tmp_path: Path,
) -> None:
    fixture = _build_single_candidate_authority(
        tmp_path / "revision",
        review_status="revision_requested",
    )

    with pytest.raises(
        ValueError,
        match="^single_starter_approval_invalid$",
    ):
        load_optimized_start_authority(
            report_root=fixture.report_root,
            manifest=SINGLE_CANDIDATE_MANIFEST,
        )
