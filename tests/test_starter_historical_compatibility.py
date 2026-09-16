"""Frozen schema-1/2/3 behavior captured before semantic schema work."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import socket

import pytest

from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_candidate import ValidatedStarterCandidate, validate_starter_candidate
from hsconfig.starter_context import StarterContext, validate_starter_context_document
from hsconfig.starter_decision import load_validated_starter_selection
from hsconfig.starter_document import StarterDocument
from hsconfig.starter_review import ValidatedStarterReview, validate_starter_review
from tests.helpers.starter_historical import (
    BASELINE_COMMIT,
    FIXTURE_ROOT,
    capture_historical_mutations,
    capture_historical_projection,
    load_historical_document,
    load_historical_json,
    load_historical_receipt,
)


@dataclass(frozen=True, slots=True)
class HistoricalCase:
    schema: int
    context_document: StarterDocument
    candidate_document: StarterDocument
    context: StarterContext
    candidate: ValidatedStarterCandidate
    receipt: FrozenJsonDocument | None
    validated_review: ValidatedStarterReview | None
    expected_projection: dict[str, object]


@pytest.fixture(autouse=True)
def isolated_localappdata_and_no_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Break caught: a historical compatibility run consults a real profile or network.
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    def denied(*_args, **_kwargs):
        raise AssertionError("historical_fixture_network_forbidden")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture(params=(1, 2, 3), ids=("schema1", "schema2", "schema3"))
def historical_case(request: pytest.FixtureRequest) -> HistoricalCase:
    schema = int(request.param)
    context_document = load_historical_document(schema, "starter_context")
    candidate_name = "candidate-1" if schema == 1 else "starter_config_candidate"
    candidate_document = load_historical_document(schema, candidate_name)
    context = validate_starter_context_document(context_document)
    candidate = validate_starter_candidate(candidate_document, context=context)
    receipt = load_historical_receipt(schema)
    validated_review = None
    if schema in {2, 3}:
        review_document = load_historical_document(schema, "starter_config_review")
        validated_review = validate_starter_review(
            review_document,
            context=context,
            candidate=candidate,
            validation_receipt=receipt,
        )
    return HistoricalCase(
        schema=schema,
        context_document=context_document,
        candidate_document=candidate_document,
        context=context,
        candidate=candidate,
        receipt=receipt,
        validated_review=validated_review,
        expected_projection=load_historical_json(schema, "projection"),
    )


def test_historical_projection_is_frozen(historical_case: HistoricalCase) -> None:
    # Break caught: fresh historical validation changes any sealed/runtime/facts bytes.
    actual = capture_historical_projection(
        historical_case.context,
        historical_case.candidate,
        receipt=historical_case.receipt,
        review=historical_case.validated_review,
    )
    assert actual == historical_case.expected_projection


def test_historical_mutation_outcomes_are_frozen(
    historical_case: HistoricalCase,
) -> None:
    # Break caught: a schema-1/2/3 semantic quirk is silently reinterpreted in place.
    assert capture_historical_mutations(
        historical_case.context,
        schema=historical_case.schema,
    ) == load_historical_json(historical_case.schema, "mutations")


def test_schema_one_selection_and_decision_are_frozen() -> None:
    # Break caught: legacy selection no longer reconstructs its real three candidates.
    context = validate_starter_context_document(
        load_historical_document(1, "starter_context")
    )
    selection = load_validated_starter_selection(
        FIXTURE_ROOT / "schema1" / "starter_config_decision.json",
        current_context=context,
    )
    assert selection.selected.document.canonical_json == (
        load_historical_document(1, "candidate-1").canonical_json
    )
    assert selection.decision.canonical_json == (
        load_historical_document(1, "starter_config_decision").canonical_json
    )
    assert [candidate.candidate_id for candidate in selection.candidates] == [
        "candidate-1",
        "candidate-2",
        "candidate-3",
    ]


def test_capture_index_binds_baseline_and_every_public_file() -> None:
    # Break caught: one expected file is replaced without updating reviewed provenance.
    index = json.loads((FIXTURE_ROOT / "capture-index.json").read_text("utf-8"))
    assert index["baseline_commit"] == BASELINE_COMMIT
    indexed = {row["path"]: row for row in index["files"]}
    actual_paths = {
        path.relative_to(FIXTURE_ROOT).as_posix()
        for path in FIXTURE_ROOT.rglob("*.json")
        if path.name != "capture-index.json"
    }
    assert set(indexed) == actual_paths
    for relative, row in indexed.items():
        raw = (FIXTURE_ROOT / relative).read_bytes()
        assert row["sha256"] == sha256(raw).hexdigest()
        assert row["size"] == len(raw)
        assert row["kind"] in {
            "sealed_context",
            "sealed_candidate",
            "sealed_decision",
            "sealed_review",
            "sealed_validation_receipt",
            "historical_projection",
            "historical_mutations",
            "historical_derivation",
        }


def test_public_historical_goldens_are_path_and_evidence_free() -> None:
    # Break caught: a committed golden leaks machine/profile/runtime authority.
    forbidden_bytes = (
        b"C:\\\\",
        b"C:" + b"/" + b"Users/",
        b"AppData",
        b"LOCALAPPDATA",
        b"Power.log",
        b".hdtreplay",
        b".hsreplay",
        b"Hearthstone\\\\Logs",
    )
    forbidden_keys = {
        "api_key",
        "authorization_header",
        "credential",
        "password",
        "raw_transport",
        "secret",
    }
    for path in FIXTURE_ROOT.rglob("*.json"):
        raw = path.read_bytes()
        assert all(token not in raw for token in forbidden_bytes), path
        value = json.loads(raw)
        assert not (_all_keys(value) & forbidden_keys), path


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value)) if value else set()
    return set()
