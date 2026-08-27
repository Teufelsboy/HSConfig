from __future__ import annotations

from dataclasses import dataclass, replace
import os
from typing import Any, Callable
from unittest.mock import patch

import pytest

from hsconfig.input_snapshot_manifest import freeze_compiler_inputs
from hsconfig.operator_profile import (
    derive_deck_output_binding,
    enable_operator_profile,
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
from hsconfig.starter_document import StarterDocument, seal_starter_document
from hsconfig.starter_review import (
    ValidatedStarterReview,
    validate_starter_review,
)
from tests.helpers.audited_package_request import (
    audited_request_with_frozen_input_projections,
)
from tests.test_starter_candidate import sealed_single_candidate


@dataclass(frozen=True, slots=True)
class _ReviewAuthority:
    context: StarterContext
    candidate: ValidatedStarterCandidate


@dataclass(frozen=True, slots=True, eq=False)
class _EqualityForgingStarterContext(StarterContext):
    def __eq__(self, _other: object) -> bool:
        return True

    def __ne__(self, _other: object) -> bool:
        return False


@dataclass(frozen=True, slots=True, eq=False)
class _EqualityForgingStarterCandidate(ValidatedStarterCandidate):
    def __eq__(self, _other: object) -> bool:
        return True

    def __ne__(self, _other: object) -> bool:
        return False


@pytest.fixture(scope="module")
def review_authority(
    tmp_path_factory: pytest.TempPathFactory,
) -> _ReviewAuthority:
    root = tmp_path_factory.mktemp("single-candidate-review")
    request, projections = audited_request_with_frozen_input_projections(
        root,
        "ShadowPriest",
    )
    preconfig = request.snapshot.general_preconfig.to_value()
    local_app_data = root / "local-app-data"
    runtime_root = root / "runtime"
    output_base_root = root / "outputs"
    for path in (local_app_data, runtime_root, output_base_root):
        path.mkdir()
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
    return _ReviewAuthority(context=context, candidate=candidate)


def review_document(
    authority: _ReviewAuthority,
    *,
    review_id: Any = "review-1",
    review_status: Any = "approved",
    confidence: Any = "high",
    revision_requests: Any = None,
    review_summary: Any = "The lead candidate is coherent and bounded.",
    mutate: Callable[[dict[str, Any]], None] | None = None,
) -> StarterDocument:
    candidate = authority.candidate
    draft = {
        "schema_version": SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
        "review_id": review_id,
        "review_status": review_status,
        "confidence": confidence,
        "starter_context_sha256": authority.context.document.content_sha256,
        "candidate_id": candidate.candidate_id,
        "candidate_revision": candidate.candidate_revision,
        "candidate_sha256": candidate.document.content_sha256,
        "revision_requests": (
            [] if revision_requests is None else revision_requests
        ),
        "review_summary": review_summary,
    }
    if mutate is not None:
        mutate(draft)
    return seal_starter_document(
        draft,
        expected_fields=STARTER_REVIEW_FIELDS,
        schema_version=SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    )


def test_approved_review_binds_context_candidate_revision_and_digest(
    review_authority: _ReviewAuthority,
) -> None:
    # Break caught: approval does not bind all four upstream candidate/context
    # identity values or returns a mutable/untyped cache.
    authority = review_authority
    document = review_document(authority)

    validated = validate_starter_review(
        document,
        context=authority.context,
        candidate=authority.candidate,
    )

    assert isinstance(validated, ValidatedStarterReview)
    assert validated.document is document
    assert validated.review_id == "review-1"
    assert validated.review_status == "approved"
    assert validated.confidence == "high"
    assert validated.starter_context_sha256 == (
        authority.context.document.content_sha256
    )
    assert validated.candidate_id == "lead"
    assert validated.candidate_revision == 1
    assert validated.candidate_sha256 == (
        authority.candidate.document.content_sha256
    )
    assert validated.revision_requests == ()


def test_limited_approval_remains_valid_and_visible(
    review_authority: _ReviewAuthority,
) -> None:
    # Break caught: mapping the V2 visible `limited` confidence to legacy `low`
    # or rejecting it despite a valid empty approval request list.
    validated = validate_starter_review(
        review_document(review_authority, confidence="limited"),
        context=review_authority.context,
        candidate=review_authority.candidate,
    )

    assert validated.review_status == "approved"
    assert validated.confidence == "limited"
    assert validated.document.to_value()["confidence"] == "limited"


def test_revision_request_requires_closed_ordered_rows(
    review_authority: _ReviewAuthority,
) -> None:
    # Break caught: sorting/deduplicating reviewer rows silently or accepting an
    # out-of-order, unknown-field, or unknown-target request list.
    rows = [
        {
            "code": "a-mulligan",
            "target": "mulligan",
            "message": "Tighten the conditional keep.",
        },
        {
            "code": "b-rationale",
            "target": "rule_rationales",
            "message": "Explain the transformed owner more directly.",
        },
    ]
    validated = validate_starter_review(
        review_document(
            review_authority,
            review_status="revision_requested",
            revision_requests=rows,
        ),
        context=review_authority.context,
        candidate=review_authority.candidate,
    )
    assert [row.to_value()["code"] for row in validated.revision_requests] == [
        "a-mulligan",
        "b-rationale",
    ]
    duplicate_rows = [rows[0], rows[0]]
    duplicate_review = validate_starter_review(
        review_document(
            review_authority,
            review_status="revision_requested",
            revision_requests=duplicate_rows,
        ),
        context=review_authority.context,
        candidate=review_authority.candidate,
    )
    assert len(duplicate_review.revision_requests) == 2

    invalid_rows = (
        list(reversed(rows)),
        [{**rows[0], "unknown": True}],
        [{**rows[0], "target": "runtime"}],
    )
    for invalid in invalid_rows:
        with pytest.raises(ValueError):
            validate_starter_review(
                review_document(
                    review_authority,
                    review_status="revision_requested",
                    revision_requests=invalid,
                ),
                context=review_authority.context,
                candidate=review_authority.candidate,
            )


def test_review_rejects_wrong_digest_revision_status_confidence_or_size(
    review_authority: _ReviewAuthority,
) -> None:
    # Break caught: approval survives stale bindings, incoherent status/confidence,
    # or canonical final bytes beyond the fixed 64-KiB ceiling.
    mutations = (
        lambda draft: draft.__setitem__(
            "starter_context_sha256", "sha256:" + "0" * 64
        ),
        lambda draft: draft.__setitem__(
            "candidate_sha256", "sha256:" + "0" * 64
        ),
        lambda draft: draft.__setitem__("candidate_id", "candidate-1"),
        lambda draft: draft.__setitem__("candidate_revision", 2),
        lambda draft: draft.__setitem__("review_status", "accepted"),
        lambda draft: draft.__setitem__("confidence", "low"),
        lambda draft: draft.update(
            {
                "review_status": "approved",
                "revision_requests": [
                    {
                        "code": "unexpected",
                        "target": "whole_candidate",
                        "message": "A revision is still required.",
                    }
                ],
            }
        ),
        lambda draft: draft.update(
            {
                "review_status": "revision_requested",
                "revision_requests": [],
            }
        ),
    )
    for mutate in mutations:
        with pytest.raises(ValueError):
            validate_starter_review(
                review_document(review_authority, mutate=mutate),
                context=review_authority.context,
                candidate=review_authority.candidate,
            )

    oversized_rows = [
        {
            "code": f"request-{index:02d}",
            "target": "whole_candidate",
            "message": "😀" * 500,
        }
        for index in range(32)
    ]
    oversized = review_document(
        review_authority,
        review_status="revision_requested",
        revision_requests=oversized_rows,
    )
    assert len(oversized.canonical_json) > 64 * 1024
    with pytest.raises(ValueError, match="^starter_review_size_invalid$"):
        validate_starter_review(
            oversized,
            context=review_authority.context,
            candidate=review_authority.candidate,
        )


def test_review_rejects_forged_context_or_candidate_dataclass(
    review_authority: _ReviewAuthority,
) -> None:
    # Break caught: trusting caller-supplied derived dataclass fields without
    # freshly resealing and revalidating the underlying authority documents.
    document = review_document(review_authority)
    wrong_context = replace(
        review_authority.context,
        deck_fingerprint="f" * 64,
    )
    with pytest.raises(ValueError, match="^starter_review_context_invalid$"):
        validate_starter_review(
            document,
            context=wrong_context,
            candidate=review_authority.candidate,
        )

    wrong_candidate = replace(
        review_authority.candidate,
        candidate_id="candidate-1",
    )
    with pytest.raises(ValueError, match="^starter_review_candidate_invalid$"):
        validate_starter_review(
            document,
            context=review_authority.context,
            candidate=wrong_candidate,
        )


def test_review_rejects_equality_forging_authority_subclasses(
    review_authority: _ReviewAuthority,
) -> None:
    # Break caught: an overriding subclass equality can make forged cache
    # fields compare equal to freshly revalidated authority values.
    authority = review_authority
    document = review_document(authority)
    forged_context = _EqualityForgingStarterContext(
        document=authority.context.document,
        deck_fingerprint="f" * 64,
        globalvalues_baseline_sha256=(
            authority.context.globalvalues_baseline_sha256
        ),
    )
    forged_candidate = _EqualityForgingStarterCandidate(
        document=authority.candidate.document,
        candidate_id="candidate-1",
        candidate_revision=authority.candidate.candidate_revision,
        strategy_role=authority.candidate.strategy_role,
        runtime_intent_sha256=authority.candidate.runtime_intent_sha256,
        mulligan_plan=authority.candidate.mulligan_plan,
        globalvalues=authority.candidate.globalvalues,
        card_behavior_rows=authority.candidate.card_behavior_rows,
        combo_plan=authority.candidate.combo_plan,
    )
    assert forged_context == authority.context
    assert forged_candidate == authority.candidate

    with pytest.raises(TypeError, match="^starter_review_context_invalid$"):
        validate_starter_review(
            document,
            context=forged_context,
            candidate=authority.candidate,
        )
    with pytest.raises(TypeError, match="^starter_review_candidate_invalid$"):
        validate_starter_review(
            document,
            context=authority.context,
            candidate=forged_candidate,
        )


def test_review_identifier_summary_and_request_row_boundaries(
    review_authority: _ReviewAuthority,
) -> None:
    # Break caught: off-by-one length handling or acceptance of open identifiers,
    # control/path/URL transport prose, wrong types, or unknown request fields.
    boundary = validate_starter_review(
        review_document(
            review_authority,
            review_id="r" * 64,
            review_summary="s" * 2_000,
            review_status="revision_requested",
            revision_requests=[
                {
                    "code": "c" * 64,
                    "target": "whole_candidate",
                    "message": "m" * 500,
                }
            ],
        ),
        context=review_authority.context,
        candidate=review_authority.candidate,
    )
    assert len(boundary.review_id) == 64
    assert len(boundary.review_summary) == 2_000
    assert len(boundary.revision_requests[0].to_value()["message"]) == 500

    unicode_prose = "Prüfung: Die Konfiguration bleibt kohärent und begrenzt."
    unicode_review = validate_starter_review(
        review_document(review_authority, review_summary=unicode_prose),
        context=review_authority.context,
        candidate=review_authority.candidate,
    )
    assert unicode_review.review_summary == unicode_prose

    invalid_review_ids: tuple[Any, ...] = (
        "",
        "r" * 65,
        "Review-1",
        "revіew-1",
        7,
    )
    for review_id in invalid_review_ids:
        with pytest.raises(ValueError, match="^starter_review_id_invalid$"):
            validate_starter_review(
                review_document(review_authority, review_id=review_id),
                context=review_authority.context,
                candidate=review_authority.candidate,
            )

    invalid_summaries: tuple[Any, ...] = (
        "",
        "s" * 2_001,
        "Read C:\\private\\review.txt",
        "Read \\\\server\\share\\review.txt",
        "Read /private/review.txt",
        "Read ../private/review.txt",
        "Read private/review.txt",
        "Read private\\review.txt",
        "Read .\\private\\review.txt",
        "See www.example.invalid",
        "See WWW.EXAMPLE.INVALID",
        "See WwW.Example.Invalid",
        "See www.example.invalid.",
        "See www.example.invalid/review",
        "See https://example.invalid/review",
        "See https ://example.invalid/review",
        "captured_at=2026-08-25T00:00:00Z",
        "Two\nlines",
        "Two\u2028lines",
        "Two\u2029lines",
        "Invisible\u200btext",
        7,
    )
    for summary in invalid_summaries:
        with pytest.raises(ValueError, match="^starter_review_summary_invalid$"):
            validate_starter_review(
                review_document(review_authority, review_summary=summary),
                context=review_authority.context,
                candidate=review_authority.candidate,
            )

    invalid_rows: tuple[dict[str, Any], ...] = (
        {"code": "", "target": "mulligan", "message": "Revise."},
        {"code": "c" * 65, "target": "mulligan", "message": "Revise."},
        {"code": "Code", "target": "mulligan", "message": "Revise."},
        {"code": "cοde", "target": "mulligan", "message": "Revise."},
        {"code": 7, "target": "mulligan", "message": "Revise."},
        {"code": "empty", "target": "mulligan", "message": ""},
        {"code": "long", "target": "mulligan", "message": "m" * 501},
        {
            "code": "path",
            "target": "mulligan",
            "message": "Read C:\\private\\review.txt",
        },
        {
            "code": "url",
            "target": "mulligan",
            "message": "See https://example.invalid/review",
        },
        {
            "code": "unc",
            "target": "mulligan",
            "message": "Read \\\\server\\share\\review.txt",
        },
        {
            "code": "posix",
            "target": "mulligan",
            "message": "Read /private/review.txt",
        },
        {
            "code": "traversal",
            "target": "mulligan",
            "message": "Read ../private/review.txt",
        },
        {
            "code": "control",
            "target": "mulligan",
            "message": "Two\nlines",
        },
        {"code": "wrong", "target": "mulligan", "message": 7},
        {
            "code": "extra",
            "target": "mulligan",
            "message": "Revise.",
            "unknown": True,
        },
    )
    for row in invalid_rows:
        with pytest.raises(ValueError):
            validate_starter_review(
                review_document(
                    review_authority,
                    review_status="revision_requested",
                    revision_requests=[row],
                ),
                context=review_authority.context,
                candidate=review_authority.candidate,
            )

    maximum_rows = [
        {
            "code": f"request-{index:02d}",
            "target": "whole_candidate",
            "message": "Revise this bounded point.",
        }
        for index in range(32)
    ]
    accepted_maximum = validate_starter_review(
        review_document(
            review_authority,
            review_status="revision_requested",
            revision_requests=maximum_rows,
        ),
        context=review_authority.context,
        candidate=review_authority.candidate,
    )
    assert len(accepted_maximum.revision_requests) == 32
    with pytest.raises(ValueError, match="^starter_review_requests_invalid$"):
        validate_starter_review(
            review_document(
                review_authority,
                review_status="revision_requested",
                revision_requests=[
                    *maximum_rows,
                    {
                        "code": "request-32",
                        "target": "whole_candidate",
                        "message": "One row too many.",
                    },
                ],
            ),
            context=review_authority.context,
            candidate=review_authority.candidate,
        )
