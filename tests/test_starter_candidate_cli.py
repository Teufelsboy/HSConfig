from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.cli_parser import build_parser
from hsconfig.starter_contract import (
    STARTER_CANDIDATE_1_FILENAME,
    STARTER_CANDIDATE_FIELDS,
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_FILENAME,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_document import seal_starter_document
from tests.test_starter_candidate import (
    build_shadowpriest_context,
    sealed_candidate,
)


def _write_cli_inputs(tmp_path: Path) -> tuple[Path, Path, object, object]:
    context = build_shadowpriest_context(tmp_path)
    candidate = sealed_candidate(context)
    context_path = tmp_path / STARTER_CONTEXT_FILENAME
    candidate_path = tmp_path / STARTER_CANDIDATE_1_FILENAME
    context_path.write_bytes(context.document.canonical_json)
    candidate_path.write_bytes(candidate.canonical_json)
    return context_path, candidate_path, context, candidate


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_candidate_cli_exposes_only_three_bounded_public_operands() -> None:
    # Break caught: candidate validation gains runtime, resolver, network, or write authority.
    parser = build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    candidate_parser = subparsers.choices["starter-validate-candidate"]
    operands = {
        option
        for action in candidate_parser._actions
        for option in action.option_strings
        if option not in {"--help", "-h"}
    }
    assert operands == {
        "--starter-context-json",
        "--candidate-json",
        "--json",
    }


def test_candidate_cli_validates_one_canonical_pair_without_any_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Break caught: the read-only validator resolves sources or mutates caller files.
    context_path, candidate_path, context, candidate = _write_cli_inputs(tmp_path)
    before = _tree_snapshot(tmp_path)

    code = main(
        [
            "starter-validate-candidate",
            "--starter-context-json",
            str(context_path),
            "--candidate-json",
            str(candidate_path),
            "--json",
        ]
    )

    assert code == 0
    assert _tree_snapshot(tmp_path) == before
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "candidate_id",
        "candidate_revision",
        "content_sha256",
        "runtime_intent_sha256",
        "starter_context_sha256",
        "strategy_role",
        "valid",
    }
    assert payload | {"runtime_intent_sha256": "ignored"} == {
        "candidate_id": "candidate-1",
        "candidate_revision": 1,
        "content_sha256": candidate.content_sha256,
        "runtime_intent_sha256": "ignored",
        "starter_context_sha256": context.document.content_sha256,
        "strategy_role": "proactive_tempo",
        "valid": True,
    }
    assert payload["runtime_intent_sha256"].startswith("sha256:")
    assert len(payload["runtime_intent_sha256"]) == 71


def test_candidate_cli_validates_content_independent_of_caller_basename(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Break caught: the single-file CLI accidentally adopts sibling-loader naming authority.
    context_path, candidate_path, _context, _candidate = _write_cli_inputs(tmp_path)
    renamed_context = context_path.with_name("context-input.json")
    renamed_candidate = candidate_path.with_name("candidate-input.json")
    context_path.rename(renamed_context)
    candidate_path.rename(renamed_candidate)

    code = main(
        [
            "starter-validate-candidate",
            "--starter-context-json",
            str(renamed_context),
            "--candidate-json",
            str(renamed_candidate),
            "--json",
        ]
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_candidate_cli_rejects_fully_rebound_invalid_context(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    context_path, candidate_path, context, candidate = _write_cli_inputs(
        tmp_path
    )
    context_value = context.document.to_value()
    del context_value["content_sha256"]
    context_value["source_evidence"] = "invalid"
    rebound_context = seal_starter_document(
        context_value,
        expected_fields=STARTER_CONTEXT_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    context_path.write_bytes(rebound_context.canonical_json)

    candidate_value = candidate.to_value()
    del candidate_value["content_sha256"]
    candidate_value["starter_context_sha256"] = (
        rebound_context.content_sha256
    )
    candidate_path.write_bytes(
        seal_starter_document(
            candidate_value,
            expected_fields=STARTER_CANDIDATE_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        ).canonical_json
    )

    code = main(
        [
            "starter-validate-candidate",
            "--starter-context-json",
            str(context_path),
            "--candidate-json",
            str(candidate_path),
            "--json",
        ]
    )

    assert code == 1
    assert json.loads(capsys.readouterr().out) == {
        "errors": ["starter_context_document_invalid"],
        "status": "failed",
    }


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("context_mismatch", "starter_candidate_context_sha256_mismatch"),
        ("malformed", "frozen_json_invalid"),
    ],
)
def test_candidate_cli_returns_stable_nonzero_error_for_invalid_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
    error: str,
) -> None:
    # Break caught: malformed or stale input escapes as success or unstable output.
    context_path, candidate_path, context, candidate = _write_cli_inputs(tmp_path)
    if mutation == "context_mismatch":
        value = candidate.to_value()
        del value["content_sha256"]
        value["starter_context_sha256"] = "sha256:" + "0" * 64
        from hsconfig.starter_contract import (
            STARTER_CANDIDATE_FIELDS,
            STARTER_SCHEMA_VERSION,
        )
        from hsconfig.starter_document import seal_starter_document

        candidate_path.write_bytes(
            seal_starter_document(
                value,
                expected_fields=STARTER_CANDIDATE_FIELDS,
                schema_version=STARTER_SCHEMA_VERSION,
            ).canonical_json
        )
    else:
        candidate_path.write_bytes(b"{")
    del context

    code = main(
        [
            "starter-validate-candidate",
            "--starter-context-json",
            str(context_path),
            "--candidate-json",
            str(candidate_path),
            "--json",
        ]
    )

    assert code == 1
    assert json.loads(capsys.readouterr().out) == {
        "errors": [error],
        "status": "failed",
    }


@pytest.mark.parametrize(
    "forbidden_operand",
    [
        "--runtime-root",
        "--out",
        "--decision-path",
        "--source-url",
        "--repair",
    ],
)
def test_candidate_cli_rejects_every_forbidden_authority_operand(
    forbidden_operand: str,
) -> None:
    # Break caught: validation silently acquires a source, path, repair, or write option.
    with pytest.raises(SystemExit) as error:
        main(
            [
                "starter-validate-candidate",
                "--starter-context-json",
                "starter_context.json",
                "--candidate-json",
                "candidate-1.json",
                forbidden_operand,
                "forbidden",
                "--json",
            ]
        )
    assert error.value.code == 2
