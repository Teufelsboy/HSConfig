from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from hsconfig import pre_run_metrics
from hsconfig.package_domain import (
    CardDisposition,
    CardDispositionRow,
    ClaimDisposition,
    ClaimDispositionRow,
    DispositionLedger,
    EvidenceLane,
    disposition_ledger_content_sha256,
)
from hsconfig.pre_run_metrics import (
    MetricRatio,
    VerifiedEmissionInput,
    VerifiedPhysicalEmission,
    VerifiedSemanticExpectation,
    eligible_emission_recall,
    emission_precision,
)


_DECK_FINGERPRINT = "sha256:" + ("a" * 64)


def _expected(identity: str) -> VerifiedSemanticExpectation:
    return VerifiedSemanticExpectation(
        deck_fingerprint=_DECK_FINGERPRINT,
        composite_identity=f"{_DECK_FINGERPRINT}:{identity}",
        row_kind="claim",
        disposition="runtime_emitted",
        expected_owner="CARD_001",
        allowed_runtime_surfaces=("CARD_001.json",),
        claim_id=identity,
        claim_linked=True,
        surface_allowed=True,
        schema_supported=True,
        authority_sufficient=True,
    )


def _physical(
    identity: str,
    *,
    physical_id: str | None = None,
    physical_owner: str = "CARD_001",
    authority_authorized: bool = True,
    composite_identity: str | None = None,
) -> VerifiedPhysicalEmission:
    return VerifiedPhysicalEmission(
        deck_fingerprint=_DECK_FINGERPRINT,
        physical_identity=(
            physical_id
            or f"{_DECK_FINGERPRINT}:CARD_001.json:{identity}"
        ),
        composite_identity=(
            f"{_DECK_FINGERPRINT}:{identity}"
            if composite_identity is None
            else composite_identity
        ),
        physical_owner=physical_owner,
        runtime_surface="CARD_001.json",
        claim_id=identity,
        claim_linked=True,
        surface_allowed=True,
        schema_supported=True,
        authority_authorized=authority_authorized,
        meaningful=True,
    )


def _verified(
    *,
    expected: tuple[VerifiedSemanticExpectation, ...] = (),
    physical: tuple[VerifiedPhysicalEmission, ...] = (),
) -> VerifiedEmissionInput:
    return VerifiedEmissionInput(
        deck_fingerprint=_DECK_FINGERPRINT,
        expectations=expected,
        physical_rows=physical,
    )


def _claim_ledger(
    *claims: tuple[str, str],
) -> DispositionLedger:
    claim_rows = tuple(
        ClaimDispositionRow(
            deck_fingerprint=_DECK_FINGERPRINT,
            claim_id=claim_id,
            claim_kind=claim_kind,
            evidence_id=f"evidence:{claim_id}",
            disposition=ClaimDisposition.CONTRACT_ONLY,
            runtime_paths=(),
            reason_code="claim_kind_has_no_runtime_surface",
        )
        for claim_id, claim_kind in claims
    )
    return DispositionLedger(
        deck_fingerprint=_DECK_FINGERPRINT,
        cards=(),
        claims=claim_rows,
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=_DECK_FINGERPRINT,
            cards=(),
            claims=claim_rows,
        ),
    )


def _card_ledger() -> DispositionLedger:
    cards = (
        CardDispositionRow(
            deck_fingerprint=_DECK_FINGERPRINT,
            composite_card_key=f"{_DECK_FINGERPRINT}:main_deck:CARD_001",
            zone="main_deck",
            official_semantics_canonical_json=b'{"GameCardId":"CARD_001"}',
            authority_lane=EvidenceLane.OFFICIAL_CARD_DATA,
            evidence_ids=("official:CARD_001",),
            claim_ids=(),
            physical_owner="CARD_001",
            disposition=CardDisposition.RUNTIME_EMITTED,
            runtime_paths=("CARD_001.json",),
            reason_code="runtime_surface_supported",
        ),
    )
    return DispositionLedger(
        deck_fingerprint=_DECK_FINGERPRINT,
        cards=cards,
        claims=(),
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=_DECK_FINGERPRINT,
            cards=cards,
            claims=(),
        ),
    )


@pytest.mark.parametrize(
    ("verified", "expected"),
    [
        (
            _verified(
                expected=(_expected("authorized"),),
                physical=(
                    _physical("authorized"),
                    _physical(
                        "unmatched",
                        composite_identity=(
                            f"{_DECK_FINGERPRINT}:not-an-expectation"
                        ),
                    ),
                ),
            ),
            {
                "numerator": 1,
                "denominator": 2,
                "fraction": "1/2",
                "value": 0.5,
                "vacuous": False,
            },
        ),
        (
            _verified(
                expected=(_expected("unauthorized"),),
                physical=(
                    _physical(
                        "unauthorized",
                        authority_authorized=False,
                    ),
                ),
            ),
            {
                "numerator": 0,
                "denominator": 1,
                "fraction": "0/1",
                "value": 0.0,
                "vacuous": False,
            },
        ),
        (
            _verified(
                expected=(_expected("authorized"),),
                physical=(_physical("authorized"),),
            ),
            {
                "numerator": 1,
                "denominator": 1,
                "fraction": "1/1",
                "value": 1.0,
                "vacuous": False,
            },
        ),
        (
            _verified(),
            {
                "numerator": 0,
                "denominator": 0,
                "fraction": "0/0",
                "value": 1.0,
                "vacuous": True,
            },
        ),
    ],
    ids=("one-of-two", "zero-of-one", "one-of-one", "vacuous-zero-of-zero"),
)
def test_emission_precision_uses_verified_physical_rows(
    verified: VerifiedEmissionInput,
    expected: dict[str, object],
) -> None:
    assert emission_precision(verified).to_document() == expected


@pytest.mark.parametrize(
    ("verified", "expected"),
    [
        (
            _verified(
                expected=(_expected("emitted"), _expected("missing")),
                physical=(_physical("emitted"),),
            ),
            {
                "numerator": 1,
                "denominator": 2,
                "fraction": "1/2",
                "value": 0.5,
                "vacuous": False,
            },
        ),
        (
            _verified(expected=(_expected("missing"),)),
            {
                "numerator": 0,
                "denominator": 1,
                "fraction": "0/1",
                "value": 0.0,
                "vacuous": False,
            },
        ),
        (
            _verified(
                expected=(_expected("emitted"),),
                physical=(_physical("emitted"),),
            ),
            {
                "numerator": 1,
                "denominator": 1,
                "fraction": "1/1",
                "value": 1.0,
                "vacuous": False,
            },
        ),
        (
            _verified(),
            {
                "numerator": 0,
                "denominator": 0,
                "fraction": "0/0",
                "value": 1.0,
                "vacuous": True,
            },
        ),
    ],
    ids=("one-of-two", "zero-of-one", "one-of-one", "vacuous-zero-of-zero"),
)
def test_eligible_emission_recall_uses_verified_eligible_rows(
    verified: VerifiedEmissionInput,
    expected: dict[str, object],
) -> None:
    assert eligible_emission_recall(verified).to_document() == expected


def test_multiple_physical_rows_can_share_one_semantic_expectation() -> None:
    verified = _verified(
        expected=(_expected("claim"),),
        physical=(
            _physical("claim", physical_id=f"{_DECK_FINGERPRINT}:physical:1"),
            _physical("claim", physical_id=f"{_DECK_FINGERPRINT}:physical:2"),
        ),
    )

    assert emission_precision(verified).to_document() == {
        "numerator": 2,
        "denominator": 2,
        "fraction": "2/2",
        "value": 1.0,
        "vacuous": False,
    }
    assert eligible_emission_recall(verified).to_document() == {
        "numerator": 1,
        "denominator": 1,
        "fraction": "1/1",
        "value": 1.0,
        "vacuous": False,
    }


def test_duplicate_physical_identity_is_rejected_before_metric_sets() -> None:
    duplicate_id = f"{_DECK_FINGERPRINT}:physical:duplicate"

    with pytest.raises(
        ValueError,
        match="verified_emission_duplicate_physical_row",
    ):
        _verified(
            expected=(_expected("claim"),),
            physical=(
                _physical("claim", physical_id=duplicate_id),
                _physical("claim", physical_id=duplicate_id),
            ),
        )


def test_physical_owner_mismatch_is_retained_and_reduces_precision() -> None:
    verified = _verified(
        expected=(_expected("claim"),),
        physical=(
            _physical(
                "claim",
                physical_owner="WRONG_OWNER",
            ),
        ),
    )

    assert emission_precision(verified).to_document() == {
        "numerator": 0,
        "denominator": 1,
        "fraction": "0/1",
        "value": 0.0,
        "vacuous": False,
    }


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("sha256:" + ("0" * 64), True),
        (None, False),
        ("sha256:" + ("0" * 63), False),
        ("digest:" + ("0" * 64), False),
        ("sha256:" + ("g" * 64), False),
    ],
)
def test_sha256_recognizer_requires_the_exact_lowercase_digest_shape(
    value: object,
    valid: bool,
) -> None:
    assert pre_run_metrics._is_sha256(value) is valid


@pytest.mark.parametrize("value", [None, "", " padded "])
def test_verified_text_fields_reject_noncanonical_values(value: object) -> None:
    with pytest.raises(ValueError, match="verified_emission_fixture_invalid"):
        pre_run_metrics._require_text(value, field="fixture")


def test_source_acquisition_binding_requires_both_mapping_projections() -> None:
    with pytest.raises(
        ValueError,
        match="source_acquisition_input_binding_invalid",
    ):
        pre_run_metrics.source_acquisition_input_binding(
            {"acquisition_closure": {}, "policy_provenance": []}
        )
    with pytest.raises(
        ValueError,
        match="source_acquisition_input_binding_invalid",
    ):
        pre_run_metrics.source_acquisition_input_binding(
            {"acquisition_closure": [], "policy_provenance": {}}
        )

    closure = {"status": "open"}
    policy = {"policy_id": "fixture"}
    assert pre_run_metrics.source_acquisition_input_binding(
        {"acquisition_closure": closure, "policy_provenance": policy}
    ) == {
        "acquisition_closure": closure,
        "policy_provenance": policy,
    }


@pytest.mark.parametrize(
    ("numerator", "denominator"),
    [
        (True, 1),
        (0, False),
        (-1, 1),
        (0, -1),
        (2, 1),
    ],
)
def test_metric_ratio_rejects_non_integer_negative_and_overfull_ratios(
    numerator: object,
    denominator: object,
) -> None:
    with pytest.raises(ValueError, match="pre_run_metric_ratio_invalid"):
        MetricRatio(numerator=numerator, denominator=denominator)  # type: ignore[arg-type]


def test_semantic_expectation_validation_rejects_each_identity_boundary() -> None:
    valid = _expected("claim")

    invalid_cases = [
        (
            {"composite_identity": "sha256:other:claim"},
            "verified_emission_composite_identity_mismatch",
        ),
        ({"row_kind": "future"}, "verified_emission_row_kind_invalid"),
        ({"disposition": "future"}, "verified_emission_disposition_invalid"),
        ({"claim_id": " padded "}, "verified_emission_claim_id_invalid"),
        (
            {"allowed_runtime_surfaces": ("B.json", "A.json")},
            "verified_emission_surface_set_invalid",
        ),
        (
            {"allowed_runtime_surfaces": ("A.json", "A.json")},
            "verified_emission_surface_set_invalid",
        ),
        ({"claim_linked": 1}, "verified_emission_claim_linked_invalid"),
        ({"surface_allowed": 1}, "verified_emission_surface_allowed_invalid"),
        ({"schema_supported": 1}, "verified_emission_schema_supported_invalid"),
        (
            {"authority_sufficient": 1},
            "verified_emission_authority_sufficient_invalid",
        ),
    ]
    for changes, reason in invalid_cases:
        with pytest.raises(ValueError, match=reason):
            replace(valid, **changes)

    card_row = replace(
        valid,
        row_kind="card",
        disposition="runtime_emitted",
        claim_id="",
    )
    assert card_row.claim_id == ""


def test_physical_emission_validation_rejects_each_identity_boundary() -> None:
    valid = _physical("claim")
    invalid_cases = [
        (
            {"physical_identity": "sha256:other:physical"},
            "verified_emission_physical_identity_mismatch",
        ),
        (
            {"composite_identity": "sha256:other:claim"},
            "verified_emission_composite_identity_mismatch",
        ),
        ({"claim_id": " padded "}, "verified_emission_claim_id_invalid"),
        (
            {"semantic_bindings": ("b", "a")},
            "verified_emission_semantic_bindings_invalid",
        ),
        (
            {"semantic_bindings": ("sha256:other:claim",)},
            "verified_emission_semantic_bindings_invalid",
        ),
        ({"claim_linked": 1}, "verified_emission_claim_linked_invalid"),
        ({"surface_allowed": 1}, "verified_emission_surface_allowed_invalid"),
        ({"schema_supported": 1}, "verified_emission_schema_supported_invalid"),
        (
            {"authority_authorized": 1},
            "verified_emission_authority_authorized_invalid",
        ),
        ({"meaningful": 1}, "verified_emission_meaningful_invalid"),
    ]
    for changes, reason in invalid_cases:
        with pytest.raises(ValueError, match=reason):
            replace(valid, **changes)

    detached = replace(valid, composite_identity=None, semantic_bindings=())
    assert detached.composite_identity is None
    assert detached.semantic_bindings == ()


def test_verified_emission_input_rejects_cross_deck_and_duplicate_semantics() -> None:
    expectation = _expected("claim")
    cross_deck = replace(
        expectation,
        deck_fingerprint="sha256:" + ("b" * 64),
        composite_identity=("sha256:" + ("b" * 64) + ":claim"),
    )
    with pytest.raises(ValueError, match="verified_emission_cross_deck_row"):
        _verified(expected=(cross_deck,))

    with pytest.raises(
        ValueError,
        match="verified_emission_duplicate_expectation",
    ):
        _verified(expected=(expectation, expectation))


@pytest.mark.parametrize(
    "changes",
    [
        {"disposition": "contract_only"},
        {"allowed_runtime_surfaces": ()},
        {"surface_allowed": False},
        {"schema_supported": False},
        {"authority_sufficient": False},
        {"claim_linked": False},
    ],
    ids=(
        "non-emittable-disposition",
        "no-runtime-surface",
        "surface-forbidden",
        "schema-unsupported",
        "authority-insufficient",
        "claim-detached",
    ),
)
def test_each_open_semantic_lowering_condition_prevents_eligibility(
    changes: dict[str, object],
) -> None:
    row = replace(_expected("claim"), **changes)

    assert not pre_run_metrics.is_emission_eligible(row)
    assert eligible_emission_recall(_verified(expected=(row,))).to_document() == {
        "numerator": 0,
        "denominator": 0,
        "fraction": "0/0",
        "value": 1.0,
        "vacuous": True,
    }


@pytest.mark.parametrize(
    ("physical_changes", "expectation_changes"),
    [
        ({"semantic_bindings": (_DECK_FINGERPRINT + ":other",)}, {}),
        ({"meaningful": False}, {}),
        ({}, {"authority_sufficient": False}),
        ({"physical_owner": "OTHER"}, {}),
        ({"runtime_surface": "OTHER.json"}, {}),
        ({"claim_linked": False}, {}),
        ({"surface_allowed": False}, {}),
        ({"schema_supported": False}, {}),
        ({"authority_authorized": False}, {}),
    ],
    ids=(
        "unbound-semantic-row",
        "nonmeaningful-row",
        "ineligible-expectation",
        "wrong-owner",
        "wrong-surface",
        "claim-detached",
        "surface-forbidden",
        "schema-unsupported",
        "authority-rejected",
    ),
)
def test_each_open_physical_authorization_condition_rejects_the_emission(
    physical_changes: dict[str, object],
    expectation_changes: dict[str, object],
) -> None:
    expectation = replace(_expected("claim"), **expectation_changes)
    physical = replace(_physical("claim"), **physical_changes)

    assert not pre_run_metrics._authorized_physical_emission(
        physical,
        expectation,
    )


def test_physical_surface_owner_is_an_authorized_owner_alias() -> None:
    expectation = replace(
        _expected("claim"),
        expected_owner="SEMANTIC_OWNER",
    )
    physical = _physical("claim", physical_owner="CARD_001")

    assert pre_run_metrics._authorized_physical_emission(
        physical,
        expectation,
    )


def _authority_projection(**changes: object) -> dict[str, object]:
    projection: dict[str, object] = {
        "lane": "C",
        "authority_id": "authority-1",
        "source_identity": "source-1",
        "as_of_date": "2026-08-01",
        "claim_kind": "mulligan",
        "content_sha256": "sha256:" + ("1" * 64),
        "exact_deck_fingerprint": None,
        "runtime_authorized": True,
        "reason": "verified",
    }
    projection.update(changes)
    return projection


def test_evidence_authority_projection_preserves_valid_classification() -> None:
    authority = pre_run_metrics.evidence_authority_from_projection(
        _authority_projection()
    )

    assert authority.lane.value == "C"
    assert authority.authority_id == "authority-1"
    assert authority.runtime_authorized is True
    assert authority.exact_deck_fingerprint is None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"exact_deck_fingerprint": ""}, "evidence_authority_projection_invalid"),
        ({"runtime_authorized": 1}, "evidence_authority_projection_invalid"),
        ({"lane": "future"}, "evidence_authority_projection_invalid"),
        ({"authority_id": " padded "}, "evidence_authority_projection_invalid"),
        ({"content_sha256": "not-a-digest"}, "evidence_authority_content_sha256_invalid"),
    ],
)
def test_evidence_authority_projection_rejects_unclassified_or_malformed_rows(
    changes: dict[str, object],
    reason: str,
) -> None:
    with pytest.raises(ValueError, match=reason):
        pre_run_metrics.evidence_authority_from_projection(
            _authority_projection(**changes)
        )


def test_metric_document_loader_requires_the_exact_canonical_projection() -> None:
    canonical = MetricRatio(1, 2).to_document()
    assert pre_run_metrics._metric_ratio_from_document(canonical) == MetricRatio(1, 2)

    for malformed in (
        [],
        {"numerator": 1},
        {**canonical, "value": 0.75},
        {**canonical, "extra": True},
    ):
        with pytest.raises(ValueError, match="pre_run_metric_document_invalid"):
            pre_run_metrics._metric_ratio_from_document(malformed)


def test_bound_evidence_authority_requires_exact_claim_and_deck_binding() -> None:
    authority = pre_run_metrics.evidence_authority_from_projection(
        _authority_projection()
    )
    bound = pre_run_metrics.BoundEvidenceAuthority(
        deck_fingerprint=_DECK_FINGERPRINT,
        composite_claim_identity=f"{_DECK_FINGERPRINT}:claim",
        claim_id="claim",
        authority=authority,
    )
    assert bound.claim_id == "claim"

    with pytest.raises(
        ValueError,
        match="evidence_authority_claim_binding_mismatch",
    ):
        replace(bound, composite_claim_identity=f"{_DECK_FINGERPRINT}:other")

    other_fingerprint = "sha256:" + ("b" * 64)
    cross_deck_authority = pre_run_metrics.evidence_authority_from_projection(
        _authority_projection(exact_deck_fingerprint=other_fingerprint)
    )
    with pytest.raises(ValueError, match="evidence_authority_cross_deck"):
        replace(bound, authority=cross_deck_authority)


def test_missing_source_acquisition_handoff_is_an_explicit_open_report() -> None:
    report = pre_run_metrics.build_source_acquisition_closure_report(
        deck_fingerprint=_DECK_FINGERPRINT,
        acquisition_closure=None,
    )

    assert report["source_acquisition_complete"] is False
    assert report["acquisition_closure"]["status"] == "open"
    assert report["acquisition_closure"]["deck_fingerprint"] == _DECK_FINGERPRINT
    assert report["content_sha256"] == pre_run_metrics._report_content_sha256(report)


def test_source_acquisition_report_rejects_a_cross_deck_typed_handoff() -> None:
    other_fingerprint = "sha256:" + ("b" * 64)
    closure = pre_run_metrics.AcquisitionClosure(
        deck_fingerprint=other_fingerprint,
        attempt_id="",
        attempted_at="",
        attempted_urls=(),
        successful_evidence_ids=(),
        failed_attempts=(),
        negative_search_documented=False,
        checked_dossier=False,
        policy_id=None,
        status="open",
        content_sha256="sha256:" + ("0" * 64),
    )
    closure = replace(
        closure,
        content_sha256=pre_run_metrics.acquisition_closure_content_sha256(
            closure,
            policy_profile=pre_run_metrics.load_policy_profile(),
        ),
    )

    with pytest.raises(
        ValueError,
        match="source_acquisition_closure_cross_deck",
    ):
        pre_run_metrics.build_source_acquisition_closure_report(
            deck_fingerprint=_DECK_FINGERPRINT,
            acquisition_closure=closure,
        )


def _rehash_acquisition_report(document: dict[str, object]) -> None:
    document["content_sha256"] = pre_run_metrics._report_content_sha256(document)


def _rehash_acquisition_closure(document: dict[str, object]) -> None:
    closure = document["acquisition_closure"]
    assert isinstance(closure, dict)
    failures = tuple(
        pre_run_metrics.AcquisitionFailure(
            source_identity=row["source_identity"],
            reason_code=row["reason_code"],
            attempted_at=row["attempted_at"],
        )
        for row in closure["failed_attempts"]
    )
    typed = pre_run_metrics.AcquisitionClosure(
        deck_fingerprint=closure["deck_fingerprint"],
        attempt_id=closure["attempt_id"],
        attempted_at=closure["attempted_at"],
        attempted_urls=tuple(closure["attempted_urls"]),
        successful_evidence_ids=tuple(closure["successful_evidence_ids"]),
        failed_attempts=failures,
        negative_search_documented=closure["negative_search_documented"],
        checked_dossier=closure["checked_dossier"],
        policy_id=closure["policy_id"],
        status=closure["status"],
        content_sha256="sha256:" + ("0" * 64),
    )
    closure["content_sha256"] = (
        pre_run_metrics.acquisition_closure_content_sha256(
            typed,
            policy_profile=pre_run_metrics.load_policy_profile(),
        )
    )
    _rehash_acquisition_report(document)


def test_acquisition_report_validator_rejects_each_envelope_boundary() -> None:
    canonical = pre_run_metrics.build_source_acquisition_closure_report(
        deck_fingerprint=_DECK_FINGERPRINT,
        acquisition_closure=None,
    )

    stale = deepcopy(canonical)
    stale["content_sha256"] = "sha256:" + ("0" * 64)

    cross_deck = deepcopy(canonical)
    cross_deck["deck_fingerprint"] = "sha256:" + ("b" * 64)
    _rehash_acquisition_report(cross_deck)

    wrong_policy = deepcopy(canonical)
    wrong_policy["policy_provenance"] = {}
    _rehash_acquisition_report(wrong_policy)

    closure_not_mapping = deepcopy(canonical)
    closure_not_mapping["acquisition_closure"] = []
    _rehash_acquisition_report(closure_not_mapping)

    wrong_fields = deepcopy(canonical)
    wrong_fields["acquisition_closure"]["extra"] = True
    _rehash_acquisition_report(wrong_fields)

    nested_cross_deck = deepcopy(canonical)
    nested_cross_deck["acquisition_closure"]["deck_fingerprint"] = (
        "sha256:" + ("b" * 64)
    )
    _rehash_acquisition_report(nested_cross_deck)

    cases = (
        (stale, "source_acquisition_closure_hash_stale"),
        (cross_deck, "source_acquisition_closure_cross_deck"),
        (wrong_policy, "source_acquisition_policy_binding_mismatch"),
        (closure_not_mapping, "source_acquisition_closure_malformed"),
        (wrong_fields, "source_acquisition_closure_malformed"),
        (nested_cross_deck, "source_acquisition_closure_cross_deck"),
    )
    for document, reason in cases:
        with pytest.raises(ValueError, match=reason):
            pre_run_metrics._validate_acquisition_report(
                document,
                deck_fingerprint=_DECK_FINGERPRINT,
            )


def test_acquisition_report_validator_rejects_each_closure_shape_boundary() -> (
    None
):
    canonical = pre_run_metrics.build_source_acquisition_closure_report(
        deck_fingerprint=_DECK_FINGERPRINT,
        acquisition_closure=None,
    )

    malformed_documents: list[dict[str, object]] = []
    for field, value in (
        ("attempt_id", 1),
        ("attempted_urls", [""]),
        ("successful_evidence_ids", "not-a-list"),
        ("failed_attempts", "not-a-list"),
        ("negative_search_documented", 1),
        ("checked_dossier", 1),
        ("policy_id", ""),
    ):
        document = deepcopy(canonical)
        document["acquisition_closure"][field] = value
        _rehash_acquisition_report(document)
        malformed_documents.append(document)

    malformed_failure = deepcopy(canonical)
    malformed_failure["acquisition_closure"]["failed_attempts"] = [
        {"source_identity": "source-only"}
    ]
    _rehash_acquisition_report(malformed_failure)
    malformed_documents.append(malformed_failure)

    invalid_status = deepcopy(canonical)
    invalid_status["acquisition_closure"]["status"] = "future"
    _rehash_acquisition_report(invalid_status)

    completion_mismatch = deepcopy(canonical)
    completion_mismatch["source_acquisition_complete"] = True
    _rehash_acquisition_report(completion_mismatch)

    invalid_hash = deepcopy(canonical)
    invalid_hash["acquisition_closure"]["content_sha256"] = "invalid"
    _rehash_acquisition_report(invalid_hash)

    for document in malformed_documents:
        with pytest.raises(ValueError, match="source_acquisition_closure_malformed"):
            pre_run_metrics._validate_acquisition_report(
                document,
                deck_fingerprint=_DECK_FINGERPRINT,
            )
    with pytest.raises(ValueError, match="source_acquisition_closure_status_invalid"):
        pre_run_metrics._validate_acquisition_report(
            invalid_status,
            deck_fingerprint=_DECK_FINGERPRINT,
        )
    with pytest.raises(ValueError, match="source_acquisition_closure_status_mismatch"):
        pre_run_metrics._validate_acquisition_report(
            completion_mismatch,
            deck_fingerprint=_DECK_FINGERPRINT,
        )
    with pytest.raises(ValueError, match="source_acquisition_closure_hash_invalid"):
        pre_run_metrics._validate_acquisition_report(
            invalid_hash,
            deck_fingerprint=_DECK_FINGERPRINT,
        )


@pytest.mark.parametrize(
    ("status", "successful", "negative_search", "reason"),
    [
        (
            "closed_with_evidence",
            [],
            False,
            "source_acquisition_closure_status_mismatch",
        ),
        (
            "closed_negative_search",
            ["evidence-1"],
            True,
            "source_acquisition_closure_status_mismatch",
        ),
        (
            "open",
            ["evidence-1"],
            False,
            "source_acquisition_closure_status_mismatch",
        ),
        (
            "closed_negative_search",
            [],
            True,
            "source_acquisition_closure_status_mismatch",
        ),
    ],
    ids=(
        "closed-without-evidence",
        "negative-search-with-evidence",
        "open-with-evidence",
        "closed-without-attempt-metadata",
    ),
)
def test_acquisition_report_validator_rejects_semantically_incomplete_statuses(
    status: str,
    successful: list[str],
    negative_search: bool,
    reason: str,
) -> None:
    document = pre_run_metrics.build_source_acquisition_closure_report(
        deck_fingerprint=_DECK_FINGERPRINT,
        acquisition_closure=None,
    )
    closure = document["acquisition_closure"]
    closure["status"] = status
    closure["successful_evidence_ids"] = successful
    closure["negative_search_documented"] = negative_search
    document["source_acquisition_complete"] = status != "open"
    _rehash_acquisition_closure(document)

    with pytest.raises(ValueError, match=reason):
        pre_run_metrics._validate_acquisition_report(
            document,
            deck_fingerprint=_DECK_FINGERPRINT,
        )


@pytest.mark.parametrize(
    ("authorities", "reason"),
    [
        (
            {"unexpected": _authority_projection()},
            "layered_evidence_unexpected_claim",
        ),
        (
            {"claim": object()},
            "evidence_authority_projection_invalid",
        ),
        (
            {
                "claim": _authority_projection(
                    claim_kind="play_order",
                )
            },
            "layered_evidence_contract_claim_semantics_mismatch",
        ),
    ],
    ids=("unexpected-claim", "unclassified-value", "wrong-claim-kind"),
)
def test_authority_handoff_rejects_unbound_or_semantically_wrong_authorities(
    authorities: dict[str, object],
    reason: str,
) -> None:
    with pytest.raises(ValueError, match=reason):
        pre_run_metrics.build_pre_run_authority_handoff(
            disposition_ledger=_claim_ledger(("claim", "mulligan")),
            classified_authorities=authorities,
        )


def test_layered_authority_report_distinguishes_missing_and_exact_authority() -> (
    None
):
    ledger = _claim_ledger(("claim", "mulligan"))

    missing = pre_run_metrics.build_layered_evidence_contract_report(
        disposition_ledger=ledger,
        classified_authorities={},
    )
    exact = pre_run_metrics.build_layered_evidence_contract_report(
        disposition_ledger=ledger,
        classified_authorities={
            "claim": _authority_projection(
                lane="B",
                exact_deck_fingerprint=_DECK_FINGERPRINT,
            )
        },
    )

    assert missing["exact_guide_authority"] is False
    assert missing["layered_coverage"] == MetricRatio(0, 1).to_document()
    assert missing["authorities"] == []
    assert exact["exact_guide_authority"] is True
    assert exact["layered_coverage"] == MetricRatio(1, 1).to_document()
    assert exact["authorities"][0]["claim_id"] == "claim"


def test_physical_observation_projection_accepts_only_emitted_canonical_paths() -> (
    None
):
    observations = pre_run_metrics._physical_cardid_observations(
        {
            "cards": {
                "CARD_001": {
                    "runtime_surfaces": (
                        "CARD_001.json",
                        "wrong.json",
                    )
                },
                "BROKEN_CARD": "not-a-row",
            },
            "linked_runtime_entities": {
                "LINK_001": {"runtime_emitted": True},
                "LINK_002": {
                    "runtime_emitted": True,
                    "runtime_surface": "wrong.json",
                },
                "LINK_003": {"runtime_emitted": False},
                "BROKEN_LINK": "not-a-row",
            },
        }
    )

    assert observations == {
        ("CARD_001", "CARD_001.json"),
        ("LINK_001", "LINK_001.json"),
    }


def test_verified_ledger_metrics_retain_unmatched_and_rejected_physical_rows() -> (
    None
):
    verified = pre_run_metrics.verified_emission_input_from_ledgers(
        disposition_ledger=_card_ledger(),
        runtime_surface_ledger={
            "cards": {
                "CARD_001": {"runtime_surfaces": ("CARD_001.json",)},
                "CARD_999": {"runtime_surfaces": ("CARD_999.json",)},
            },
            "physical_errors": ({"reason": "malformed"},),
        },
    )

    assert emission_precision(verified).to_document() == MetricRatio(
        1,
        3,
    ).to_document()
    assert eligible_emission_recall(verified) == MetricRatio(1, 1)
    assert {row.physical_owner for row in verified.physical_rows} == {
        "CARD_001",
        "CARD_999",
        "rejected_physical_emission",
    }


@pytest.mark.parametrize(
    "audit",
    [
        {"claim_rows": [], "claim_lifecycle_rows": []},
        {"claim_rows": {}, "claim_lifecycle_rows": {}},
    ],
    ids=("claim-rows-not-mapping", "lifecycle-not-sequence"),
)
def test_pre_emission_projection_rejects_malformed_source_audit_collections(
    audit: dict[str, object],
) -> None:
    with pytest.raises(
        ValueError,
        match="verified_emission_source_audit_invalid",
    ):
        pre_run_metrics.pre_emission_expectations_from_audit(
            disposition_ledger=_claim_ledger(("claim", "mulligan")),
            source_contract_audit=audit,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"meaningful": 1},
        {"schema_supported": 1},
    ],
    ids=("meaningful-not-bool", "schema-supported-not-bool"),
)
def test_physical_row_projection_requires_real_boolean_classifications(
    changes: dict[str, object],
) -> None:
    row: dict[str, object] = {
        "physical_owner": "CARD_001",
        "relative_path": "CARD_001.json",
        "meaningful": True,
        "schema_supported": True,
    }
    row.update(changes)

    with pytest.raises(
        ValueError,
        match="verified_emission_physical_row_invalid",
    ):
        pre_run_metrics.verified_emission_input_from_physical_rows(
            disposition_ledger=_claim_ledger(),
            physical_rows=(row,),
        )


def test_physical_row_projection_rejects_duplicate_owner_surface_identity() -> (
    None
):
    row = {
        "physical_owner": "CARD_001",
        "relative_path": "CARD_001.json",
        "meaningful": True,
        "schema_supported": True,
    }

    with pytest.raises(
        ValueError,
        match="verified_emission_duplicate_physical_row",
    ):
        pre_run_metrics.verified_emission_input_from_physical_rows(
            disposition_ledger=_claim_ledger(),
            physical_rows=(row, row),
        )


def test_physical_row_projection_rejects_cross_deck_semantic_expectations() -> (
    None
):
    other_fingerprint = "sha256:" + ("b" * 64)
    cross_deck = replace(
        _expected("claim"),
        deck_fingerprint=other_fingerprint,
        composite_identity=f"{other_fingerprint}:claim",
    )

    with pytest.raises(ValueError, match="verified_emission_cross_deck_row"):
        pre_run_metrics.verified_emission_input_from_physical_rows(
            disposition_ledger=_claim_ledger(),
            physical_rows=(),
            semantic_expectations=(cross_deck,),
        )


def test_verified_emission_loader_round_trips_only_the_canonical_document() -> (
    None
):
    verified = _verified(
        expected=(_expected("claim"),),
        physical=(_physical("claim"),),
    )
    document = pre_run_metrics.verified_emission_input_document(verified)

    assert pre_run_metrics._load_verified_emission_input(document) == verified

    with pytest.raises(ValueError, match="verified_emission_document_invalid"):
        pre_run_metrics._load_verified_emission_input([])

    with pytest.raises(ValueError, match="verified_emission_document_malformed"):
        pre_run_metrics._load_verified_emission_input(
            {**document, "untrusted_extra": True}
        )


def test_authority_handoff_loader_rejects_noncanonical_envelopes() -> None:
    ledger = _claim_ledger(("claim", "mulligan"))
    canonical = pre_run_metrics.build_pre_run_authority_handoff(
        disposition_ledger=ledger,
        classified_authorities={"claim": _authority_projection()},
    )

    assert set(
        pre_run_metrics._load_pre_run_authority_handoff(
            canonical,
            disposition_ledger=ledger,
        )
    ) == {"claim"}

    stale = deepcopy(canonical)
    stale["content_sha256"] = "sha256:" + ("0" * 64)

    malformed_fields = deepcopy(canonical)
    malformed_fields["extra"] = True
    malformed_fields["content_sha256"] = pre_run_metrics._report_content_sha256(
        malformed_fields
    )

    wrong_schema = deepcopy(canonical)
    wrong_schema["schema_version"] = True
    wrong_schema["content_sha256"] = pre_run_metrics._report_content_sha256(
        wrong_schema
    )

    cross_deck = deepcopy(canonical)
    cross_deck["deck_fingerprint"] = "sha256:" + ("b" * 64)
    cross_deck["content_sha256"] = pre_run_metrics._report_content_sha256(
        cross_deck
    )

    authorities_not_list = deepcopy(canonical)
    authorities_not_list["authorities"] = {}
    authorities_not_list["content_sha256"] = (
        pre_run_metrics._report_content_sha256(authorities_not_list)
    )

    malformed_row = deepcopy(canonical)
    malformed_row["authorities"][0]["extra"] = True
    malformed_row["content_sha256"] = pre_run_metrics._report_content_sha256(
        malformed_row
    )

    duplicate = deepcopy(canonical)
    duplicate["authorities"].append(deepcopy(duplicate["authorities"][0]))
    duplicate["content_sha256"] = pre_run_metrics._report_content_sha256(
        duplicate
    )

    cases = (
        (stale, "pre_run_authority_handoff_hash_stale"),
        (malformed_fields, "pre_run_authority_handoff_malformed"),
        (wrong_schema, "pre_run_authority_handoff_schema_invalid"),
        (cross_deck, "pre_run_authority_handoff_cross_deck"),
        (authorities_not_list, "pre_run_authority_handoff_malformed"),
        (malformed_row, "pre_run_authority_handoff_malformed"),
        (duplicate, "pre_run_authority_handoff_duplicate"),
    )
    for document, reason in cases:
        with pytest.raises(ValueError, match=reason):
            pre_run_metrics._load_pre_run_authority_handoff(
                document,
                disposition_ledger=ledger,
            )
