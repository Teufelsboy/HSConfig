import copy

from hsconfig.package_derivation_receipt import (
    canonical_source_receipt_reasons,
)
from tests.mulligan_authority_fixtures import (
    build_canonical_mulligan_bundle,
)


def _current_bundle_and_identity() -> tuple[dict, dict]:
    return build_canonical_mulligan_bundle([{"cards": ["CARD_A"]}])


def test_canonical_source_receipt_validator_accepts_exact_binding() -> None:
    bundle, deck_identity = _current_bundle_and_identity()

    assert canonical_source_receipt_reasons(
        bundle=bundle,
        deck_identity=deck_identity,
    ) == []


def test_canonical_source_receipt_validator_rejects_invalid_receipt_kind() -> None:
    bundle, deck_identity = _current_bundle_and_identity()
    tampered = copy.deepcopy(bundle)
    tampered["canonical_source_receipts"][0][
        "receipt_kind"
    ] = "diagnostic_source_document"

    reasons = canonical_source_receipt_reasons(
        bundle=tampered,
        deck_identity=deck_identity,
    )

    assert reasons[0]["code"] == "source_authority_receipt_invalid"
