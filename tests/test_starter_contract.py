from __future__ import annotations

from functools import partial
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_contract import (
    STARTER_CANDIDATE_FIELDS,
    STARTER_CANDIDATE_MAX_BYTES,
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_DECISION_FIELDS,
    STARTER_FILENAMES,
    STARTER_SCHEMA_VERSION,
    reject_path_like_fields,
    require_nonempty_string,
    require_object_list,
    require_string_list,
    validate_candidate_revision,
    validate_starter_sibling_name,
)
from hsconfig.starter_document import (
    StarterDocument,
    _validate_unsigned_shape,
    load_starter_document,
    seal_starter_document,
)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sealed_value(
    value: dict[str, Any],
    *,
    fields: frozenset[str],
) -> dict[str, Any]:
    return seal_starter_document(
        value,
        expected_fields=fields,
        schema_version=STARTER_SCHEMA_VERSION,
    ).to_value()


def _context_value() -> dict[str, Any]:
    return {
        "schema_version": STARTER_SCHEMA_VERSION,
        "deck_identity": {},
        "cards": [],
        "deck_shape": {},
        "supported_runtime_contract": {},
        "globalvalues_baseline": {},
        "source_evidence": [],
        "existing_claims": [],
        "known_safety_boundaries": [],
    }


def _candidate_value() -> dict[str, Any]:
    return {
        "schema_version": STARTER_SCHEMA_VERSION,
        "candidate_id": "candidate-1",
        "candidate_revision": 1,
        "starter_context_sha256": "sha256:" + "a" * 64,
        "deck_fingerprint": "f" * 64,
        "strategy_summary": {"role": "balanced", "summary": "steady"},
        "mulligan": [],
        "globalvalues": {},
        "card_rules": [],
        "combo": None,
        "card_dispositions": [],
        "rule_rationales": {},
        "assumptions": [],
    }


def _decision_value() -> dict[str, Any]:
    return {
        "schema_version": STARTER_SCHEMA_VERSION,
        "starter_context_sha256": "sha256:" + "a" * 64,
        "reviewed_candidates": [],
        "ranking": [],
        "selected_candidate_id": "candidate-1",
        "selection_rationale": "balanced coverage",
        "strengths": [],
        "risks": [],
        "rejection_reasons": {},
        "critic_identity": {
            "kind": "independent_codex_agent",
            "review_id": "review-1",
            "confidence": "high",
        },
    }


def test_seal_starter_document_adds_the_hand_derived_self_digest() -> None:
    # Break caught: using source bytes or a noncanonical serializer for the digest.
    source = _context_value()

    document = seal_starter_document(
        source,
        expected_fields=STARTER_CONTEXT_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )

    expected_digest = "sha256:" + sha256(_canonical_bytes(source)).hexdigest()
    expected_value = {**source, "content_sha256": expected_digest}
    assert document.canonical_json == _canonical_bytes(expected_value)
    assert document.to_value() == expected_value


@pytest.mark.parametrize(
    ("raw", "maximum_bytes"),
    [
        (b"\xef\xbb\xbf{}", STARTER_CONTEXT_MAX_BYTES),
        (b"\xff", STARTER_CONTEXT_MAX_BYTES),
        (b"{\r\n}", STARTER_CONTEXT_MAX_BYTES),
        (b"{\x00}", STARTER_CONTEXT_MAX_BYTES),
        (b'{"schema_version":1,"schema_version":1}', STARTER_CONTEXT_MAX_BYTES),
        (b"NaN", STARTER_CONTEXT_MAX_BYTES),
        (b"Infinity", STARTER_CONTEXT_MAX_BYTES),
        (b"-Infinity", STARTER_CONTEXT_MAX_BYTES),
        (b"{}", 1),
    ],
)
def test_load_starter_document_rejects_untrusted_noncanonical_bytes(
    tmp_path: Path,
    raw: bytes,
    maximum_bytes: int,
) -> None:
    # Break caught: accepting an alternate, ambiguous, or unbounded byte input.
    path = tmp_path / "starter_context.json"
    path.write_bytes(raw)

    with pytest.raises(ValueError):
        load_starter_document(
            path,
            maximum_bytes=maximum_bytes,
            expected_fields=STARTER_CONTEXT_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )


def test_load_starter_document_rejects_canonically_equivalent_source_bytes(
    tmp_path: Path,
) -> None:
    # Break caught: normalizing untrusted source before checking its byte identity.
    value = _sealed_value(_context_value(), fields=STARTER_CONTEXT_FIELDS)
    path = tmp_path / "starter_context.json"
    path.write_bytes(_canonical_bytes(value) + b"\n")

    with pytest.raises(ValueError, match="starter_document_not_canonical"):
        load_starter_document(
            path,
            maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
            expected_fields=STARTER_CONTEXT_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )


def test_load_starter_document_keeps_only_a_canonical_value_snapshot(
    tmp_path: Path,
) -> None:
    # Break caught: retaining a caller-controlled input path after one safe read.
    value = _sealed_value(_context_value(), fields=STARTER_CONTEXT_FIELDS)
    source = _canonical_bytes(value)
    path = tmp_path / "starter_context.json"
    path.write_bytes(source)

    document = load_starter_document(
        path,
        maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
        expected_fields=STARTER_CONTEXT_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    path.unlink()

    assert document.canonical_json == source
    assert document.to_value() == value
    assert not hasattr(document, "path")


@pytest.mark.parametrize(
    ("mutate", "fields"),
    [
        (lambda value: value.pop("cards"), STARTER_CONTEXT_FIELDS),
        (lambda value: value.__setitem__("unexpected", True), STARTER_CONTEXT_FIELDS),
        (lambda value: value.__setitem__("schema_version", 2), STARTER_CONTEXT_FIELDS),
        (lambda value: value.__setitem__("runtime_path", "C:" + "/unsafe"), STARTER_DECISION_FIELDS),
    ],
)
def test_seal_starter_document_rejects_closed_schema_violations(
    mutate: Any,
    fields: frozenset[str],
) -> None:
    # Break caught: allowing an unbound field or a schema-version mismatch through.
    value = _context_value() if fields is STARTER_CONTEXT_FIELDS else _decision_value()
    mutate(value)

    with pytest.raises(ValueError):
        seal_starter_document(
            value,
            expected_fields=fields,
            schema_version=STARTER_SCHEMA_VERSION,
        )


def test_load_starter_document_rejects_a_stale_self_digest(tmp_path: Path) -> None:
    # Break caught: binding a document to a digest that does not cover its content.
    value = _sealed_value(_candidate_value(), fields=STARTER_CANDIDATE_FIELDS)
    value["candidate_id"] = "candidate-2"
    path = tmp_path / "candidate-2.json"
    path.write_bytes(_canonical_bytes(value))

    with pytest.raises(ValueError, match="starter_document_content_sha256_invalid"):
        load_starter_document(
            path,
            maximum_bytes=STARTER_CANDIDATE_MAX_BYTES,
            expected_fields=STARTER_CANDIDATE_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )


def test_fixed_starter_sibling_names_reject_an_unexpected_name() -> None:
    # Break caught: adding an LLM-chosen sibling file to the authority bundle.
    assert set(STARTER_FILENAMES) == {
        "starter_context.json",
        "candidate-1.json",
        "candidate-2.json",
        "candidate-3.json",
        "starter_config_decision.json",
    }
    for name in STARTER_FILENAMES:
        validate_starter_sibling_name(name)

    with pytest.raises(ValueError, match="starter_sibling_name_invalid"):
        validate_starter_sibling_name("critic-notes.json")


def test_critic_document_rejects_a_document_controlled_path_field() -> None:
    # Break caught: accepting a critic-supplied filesystem authority subtree.
    value = _decision_value()
    value["critic_identity"]["artifact_path"] = "C:" + "/unsafe"

    with pytest.raises(ValueError, match="starter_critic_path_forbidden"):
        reject_path_like_fields(value, error="starter_critic_path_forbidden")


@pytest.mark.parametrize("revision", [0, 4, True, "1"])
def test_candidate_revision_is_limited_to_the_three_authorized_revisions(
    revision: object,
) -> None:
    # Break caught: allowing an unbounded repair loop or a non-integer revision.
    with pytest.raises(ValueError, match="starter_candidate_revision_invalid"):
        validate_candidate_revision(revision)


@pytest.mark.parametrize(
    ("boundary", "exception_type"),
    [
        ("nonempty_invalid", ValueError),
        ("nonempty_valid", None),
        ("string_list_bad_item", ValueError),
        ("string_list_valid", None),
        ("object_list_string_root", ValueError),
        ("object_list_bad_item", ValueError),
        ("object_list_valid", None),
        ("document_root_not_object", TypeError),
        ("seal_root_not_mapping", ValueError),
        ("load_digest_not_string", ValueError),
        ("load_maximum_negative", ValueError),
        ("unsigned_shape_not_object", ValueError),
        ("sealed_fields_missing", ValueError),
        ("sealed_schema_invalid", ValueError),
    ],
)
def test_starter_contract_helpers_and_documents_fail_closed_at_type_boundaries(
    tmp_path: Path,
    boundary: str,
    exception_type: type[Exception] | None,
) -> None:
    # Breaks caught: coercing attacker-controlled scalars/collections or loading
    # an unbounded, unsealed, wrongly versioned, or non-object authority document.
    if boundary == "nonempty_valid":
        assert exception_type is None
        assert require_nonempty_string("candidate-1", error="closed") == "candidate-1"
        return
    if boundary == "string_list_valid":
        assert exception_type is None
        assert require_string_list(["a", "b"], error="closed") == ["a", "b"]
        return
    if boundary == "object_list_valid":
        assert exception_type is None
        assert require_object_list([{"id": 1}], error="closed") == [{"id": 1}]
        return

    path = tmp_path / "candidate-1.json"
    if boundary == "nonempty_invalid":
        call = partial(require_nonempty_string, " candidate-1", error="closed")
        error = "closed"
    elif boundary == "string_list_bad_item":
        call = partial(require_string_list, ["a", ""], error="closed")
        error = "closed"
    elif boundary == "object_list_string_root":
        call = partial(require_object_list, "abc", error="closed")
        error = "closed"
    elif boundary == "object_list_bad_item":
        call = partial(require_object_list, [{"id": 1}, "bad"], error="closed")
        error = "closed"
    elif boundary == "document_root_not_object":
        document = StarterDocument(
            document=FrozenJsonDocument.from_value([]),
            content_sha256="sha256:" + "a" * 64,
        )
        call = document.to_value
        error = "starter_document_root_invalid"
    elif boundary == "seal_root_not_mapping":
        call = partial(
            seal_starter_document,
            "not-an-object",  # type: ignore[arg-type]
            expected_fields=STARTER_CANDIDATE_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )
        error = "starter_document_root_invalid"
    elif boundary == "load_digest_not_string":
        value = {**_candidate_value(), "content_sha256": 7}
        path.write_bytes(_canonical_bytes(value))
        call = partial(
            load_starter_document,
            path,
            maximum_bytes=STARTER_CANDIDATE_MAX_BYTES,
            expected_fields=STARTER_CANDIDATE_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )
        error = "starter_document_content_sha256_invalid"
    elif boundary == "load_maximum_negative":
        call = partial(
            load_starter_document,
            path,
            maximum_bytes=-1,
            expected_fields=STARTER_CANDIDATE_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )
        error = "starter_document_maximum_bytes_invalid"
    elif boundary == "unsigned_shape_not_object":
        call = partial(
            _validate_unsigned_shape,
            [],
            expected_fields=STARTER_CANDIDATE_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )
        error = "starter_document_fields_invalid"
    elif boundary == "sealed_fields_missing":
        path.write_bytes(_canonical_bytes(_candidate_value()))
        call = partial(
            load_starter_document,
            path,
            maximum_bytes=STARTER_CANDIDATE_MAX_BYTES,
            expected_fields=STARTER_CANDIDATE_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )
        error = "starter_document_fields_invalid"
    elif boundary == "sealed_schema_invalid":
        value = {
            **_candidate_value(),
            "schema_version": True,
            "content_sha256": "sha256:" + "a" * 64,
        }
        path.write_bytes(_canonical_bytes(value))
        call = partial(
            load_starter_document,
            path,
            maximum_bytes=STARTER_CANDIDATE_MAX_BYTES,
            expected_fields=STARTER_CANDIDATE_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )
        error = "starter_document_schema_version_invalid"
    else:
        raise AssertionError(f"unknown_contract_boundary:{boundary}")

    assert exception_type is not None
    with pytest.raises(exception_type, match=f"^{error}$"):
        call()
