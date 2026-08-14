from __future__ import annotations

import pytest

from hsconfig.pre_run_metrics import (
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
