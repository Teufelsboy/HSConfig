from __future__ import annotations

import io
import hashlib
import importlib.util
from contextlib import contextmanager
from itertools import product
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Any, Iterator
import zipfile

import pytest
import yaml

from hsconfig.release_gate import (
    CHECK_NAMES,
    _CommandSpec,
    ReleaseCheck,
    ReleaseGateError,
    ReleaseGateResult,
    _archive_rows,
    _active_runtime_paths,
    _assert_snapshot_unchanged,
    _build_base_evidence,
    _capture_snapshot,
    _claim_authority_lane,
    _collect_live_github_state,
    _command_specs,
    _controlled_environment,
    _dirty_tree_fingerprint,
    _execute_bounded,
    _execute_bounded_process,
    _gh_json,
    _load_json_file,
    _path_violations,
    _process_tree_gate_interpreter,
    _portable_value,
    _produce_semantic_rows,
    _repository_identity,
    _run_one,
    _safe_detail,
    _scan_current_packages,
    _scan_distributions,
    _shannon_entropy,
    _stage_tracked_source,
    _text_violations,
    _validate_live_github_state,
    _validate_git_binding,
    _validate_selected_audit_projection,
    _validate_repository,
    _walk_regular_tree,
    check_repository_hygiene,
    run_release_gate,
    scan_publishable_content,
)
from hsconfig.near100_scorecard import build_near100_scorecard
from hsconfig.semantic_inventory import canonical_semantic_claim
from tests.helpers.package_byte_contract import (
    AUDITED_DECK_NAMES,
    prepare_audited_packages,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_release_gate.py"
_BOOTSTRAP_SPEC = importlib.util.spec_from_file_location("hsconfig_release_bootstrap", SCRIPT)
assert _BOOTSTRAP_SPEC is not None and _BOOTSTRAP_SPEC.loader is not None
BOOTSTRAP = importlib.util.module_from_spec(_BOOTSTRAP_SPEC)
_BOOTSTRAP_SPEC.loader.exec_module(BOOTSTRAP)
_COVERAGE_RUNNER = importlib.import_module("scripts.run_coverage_gate")
EXPECTED_CHECKS = (
    "ruff",
    "full_tests_and_coverage",
    "contract_spine",
    "twelve_deck_acceptance",
    "contract_mutations",
    "dependency_audit",
    "distribution",
    "twelve_deck_determinism",
    "publishable_path_scan",
    "output_inventory",
    "package_immutability",
    "transaction_fault_matrix",
    "repository_hygiene",
    "version_consistency",
    "near100_scorecard",
)
_BACKSLASH = chr(92)
_COVERAGE_TEST_REPOSITORY_ROOT = "HSCONFIG_COVERAGE_TEST_REPOSITORY_ROOT"
_COVERAGE_TEST_REPOSITORY_BINDING = "HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING"
_AUDITED_REPORT_BYTES: dict[str, tuple[bytes, bytes]] | None = None
_AUDITED_REPORT_BYTES_LOCK = threading.Lock()


def _local_windows_path() -> str:
    return "C:" + _BACKSLASH + _BACKSLASH.join(("Users", "operator", "repo"))


def _unc_path() -> str:
    return (_BACKSLASH * 2) + _BACKSLASH.join(("server", "share", "operator"))


def _extended_windows_path() -> str:
    return (_BACKSLASH * 2) + "?" + _BACKSLASH + "C:" + _BACKSLASH + "operator"


def _initialize_full_repository_fixture(repository: Path) -> None:
    _git(repository, "init", "-q")
    for key, value in (
        ("core.autocrlf", "false"),
        ("core.longpaths", "true"),
    ):
        _git(repository, "config", "--local", key, value)
    _git(repository, "add", ".")


def _coverage_test_repository(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    repository.mkdir(parents=True)
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "tests@example.invalid")
    _git(repository, "config", "user.name", "HSConfig Tests")
    tracked = repository / "tracked.txt"
    tracked.write_text("bound repository\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-q", "-m", "bound repository")
    return repository.resolve(strict=True), tracked


def _coverage_test_binding(
    repository: Path,
    *,
    commit_oid: str | None = None,
    tree_oid: str | None = None,
    repository_value: str | None = None,
) -> str:
    metadata = repository.lstat()
    document = {
        "schema_version": 1,
        "repository": repository_value or str(repository),
        "commit_oid": commit_oid or _git(repository, "rev-parse", "HEAD"),
        "tree_oid": tree_oid or _git(repository, "rev-parse", "HEAD^{tree}"),
        "root_identity": {
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
            "size": metadata.st_size,
            "modified_ns": metadata.st_mtime_ns,
            "changed_ns": metadata.st_ctime_ns,
            "mode": metadata.st_mode,
        },
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":"))


def test_coverage_scan_repository_defaults_to_committed_test_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_COVERAGE_TEST_REPOSITORY_ROOT, raising=False)
    monkeypatch.delenv(_COVERAGE_TEST_REPOSITORY_BINDING, raising=False)

    with _coverage_scan_repository() as repository:
        assert repository == ROOT


@pytest.mark.parametrize(
    "kind",
    (
        "empty",
        "malformed",
        "partial",
        "float-schema",
        "bool-schema",
        "relative",
        "missing",
        "file",
        "non-git",
        "dirty-git",
    ),
)
def test_coverage_scan_repository_rejects_invalid_bound_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    if kind == "empty":
        supplied = ""
    elif kind == "malformed":
        supplied = "{not-json"
    elif kind == "partial":
        supplied = json.dumps({"schema_version": 1, "repository": str(tmp_path)})
    elif kind in {"float-schema", "bool-schema"}:
        repository, _tracked = _coverage_test_repository(tmp_path)
        document = json.loads(_coverage_test_binding(repository))
        document["schema_version"] = 1.0 if kind == "float-schema" else True
        supplied = json.dumps(document, sort_keys=True, separators=(",", ":"))
    elif kind == "relative":
        supplied = json.dumps(
            {
                "schema_version": 1,
                "repository": "relative-repository",
                "commit_oid": "a" * 40,
                "tree_oid": "b" * 40,
                "root_identity": {
                    "device": 1,
                    "inode": 1,
                    "size": 0,
                    "modified_ns": 0,
                    "changed_ns": 0,
                    "mode": stat.S_IFDIR,
                },
            }
        )
    elif kind == "missing":
        repository, _tracked = _coverage_test_repository(tmp_path)
        supplied = _coverage_test_binding(
            repository,
            repository_value=str(tmp_path / "missing-repository"),
        )
    elif kind == "file":
        candidate = tmp_path / "repository-file"
        candidate.write_text("not a repository\n", encoding="utf-8")
        repository, _tracked = _coverage_test_repository(tmp_path / "fixture")
        supplied = _coverage_test_binding(
            repository,
            repository_value=str(candidate),
        )
    elif kind == "non-git":
        candidate = tmp_path / "plain-directory"
        candidate.mkdir()
        metadata = candidate.lstat()
        supplied = json.dumps(
            {
                "schema_version": 1,
                "repository": str(candidate.resolve(strict=True)),
                "commit_oid": "a" * 40,
                "tree_oid": "b" * 40,
                "root_identity": {
                    "device": metadata.st_dev,
                    "inode": metadata.st_ino,
                    "size": metadata.st_size,
                    "modified_ns": metadata.st_mtime_ns,
                    "changed_ns": metadata.st_ctime_ns,
                    "mode": metadata.st_mode,
                },
            }
        )
    else:
        candidate, tracked = _coverage_test_repository(tmp_path)
        supplied = _coverage_test_binding(candidate)
        tracked.write_text("dirty\n", encoding="utf-8")
    outputs = tmp_path / "scan-outputs"
    outputs.mkdir(exist_ok=True)
    monkeypatch.setenv(_COVERAGE_TEST_REPOSITORY_BINDING, supplied)

    with pytest.raises(AssertionError, match="coverage test repository binding"):
        _scan_coverage_publishable_content(
            outputs_root=outputs,
            tree_mode="working-pre-cutover",
            build_distributions=False,
        )


def test_coverage_scan_repository_uses_clean_bound_git_worktree_from_git_free_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _tracked = _coverage_test_repository(tmp_path)
    committed_source = tmp_path / "bootstrap" / "committed-source"
    committed_source.mkdir(parents=True)
    monkeypatch.setattr(sys.modules[__name__], "ROOT", committed_source)
    monkeypatch.setenv(
        _COVERAGE_TEST_REPOSITORY_BINDING,
        _coverage_test_binding(repository),
    )

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    result = _scan_coverage_publishable_content(
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
        build_distributions=False,
    )

    assert result["tracked_files_scanned"] == 1


@pytest.mark.parametrize("mismatch", ("commit", "tree"))
def test_coverage_scan_repository_rejects_exact_manifest_oid_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    repository, tracked = _coverage_test_repository(tmp_path)
    first_commit = _git(repository, "rev-parse", "HEAD")
    first_tree = _git(repository, "rev-parse", "HEAD^{tree}")
    tracked.write_text("second commit\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-q", "-m", "second commit")
    current_commit = _git(repository, "rev-parse", "HEAD")
    current_tree = _git(repository, "rev-parse", "HEAD^{tree}")
    supplied = _coverage_test_binding(
        repository,
        commit_oid=first_commit if mismatch == "commit" else current_commit,
        tree_oid=first_tree if mismatch == "tree" else current_tree,
    )
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv(_COVERAGE_TEST_REPOSITORY_BINDING, supplied)

    with pytest.raises(AssertionError, match="coverage test repository binding"):
        _scan_coverage_publishable_content(
            outputs_root=outputs,
            tree_mode="working-pre-cutover",
            build_distributions=False,
        )


def test_coverage_scan_repository_rejects_clean_ref_advance_after_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, tracked = _coverage_test_repository(tmp_path)
    supplied = _coverage_test_binding(repository)
    tracked.write_text("advanced ref\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-q", "-m", "advanced ref")
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv(_COVERAGE_TEST_REPOSITORY_BINDING, supplied)

    with pytest.raises(AssertionError, match="coverage test repository binding"):
        _scan_coverage_publishable_content(
            outputs_root=outputs,
            tree_mode="working-pre-cutover",
            build_distributions=False,
        )


def test_coverage_scan_repository_rejects_assume_unchanged_byte_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, tracked = _coverage_test_repository(tmp_path)
    supplied = _coverage_test_binding(repository)
    _git(repository, "update-index", "--assume-unchanged", "tracked.txt")
    tracked.write_text("hidden mutation\n", encoding="utf-8")
    assert _git(repository, "status", "--porcelain=v1", "--untracked-files=all") == ""
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv(_COVERAGE_TEST_REPOSITORY_BINDING, supplied)

    with pytest.raises(AssertionError, match="coverage test repository binding"):
        _scan_coverage_publishable_content(
            outputs_root=outputs,
            tree_mode="working-pre-cutover",
            build_distributions=False,
        )


def test_coverage_scan_repository_rejects_root_identity_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _tracked = _coverage_test_repository(tmp_path)
    supplied = _coverage_test_binding(repository)
    displaced = tmp_path / "displaced-repository"
    repository.rename(displaced)
    shutil.copytree(displaced, repository)
    assert _git(repository, "status", "--porcelain=v1", "--untracked-files=all") == ""
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv(_COVERAGE_TEST_REPOSITORY_BINDING, supplied)

    with pytest.raises(AssertionError, match="coverage test repository binding"):
        _scan_coverage_publishable_content(
            outputs_root=outputs,
            tree_mode="working-pre-cutover",
            build_distributions=False,
        )


def test_coverage_scan_repository_revalidates_after_scan_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, tracked = _coverage_test_repository(tmp_path)
    monkeypatch.setenv(
        _COVERAGE_TEST_REPOSITORY_BINDING,
        _coverage_test_binding(repository),
    )

    with pytest.raises(AssertionError, match="coverage test repository binding"):
        with _coverage_scan_repository() as candidate:
            assert candidate == repository
            tracked.write_text("mutated during scan\n", encoding="utf-8")
            raise RuntimeError("scanner failed after repository mutation")


@pytest.mark.parametrize(
    ("committed_source", "transient"),
    (
        pytest.param(
            b"first line\nsecond line\n",
            b"substantive scanner bytes\n",
            id="substantive-mutation",
        ),
        pytest.param(
            b"first line\nsecond line\n",
            b"first line\r\nsecond line\n",
            id="mixed-line-endings",
        ),
        pytest.param(
            b"first line\nsecond line\n",
            b"first line\rsecond line\r",
            id="bare-carriage-returns",
        ),
        pytest.param(
            b"first line\nsecond line\n",
            b"FIRST LINE\nSECOND LINE\n",
            id="unknown-transformation",
        ),
        pytest.param(
            b"first line\rsecond line\n",
            b"first line\rsecond line\r\n",
            id="canonical-source-already-contains-carriage-return",
        ),
    ),
)
def test_coverage_scan_repository_rejects_transient_bytes_read_then_restored(
    tmp_path: Path,
    committed_source: bytes,
    transient: bytes,
) -> None:
    repository, tracked = _coverage_test_repository(tmp_path)
    tracked.write_bytes(committed_source)
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-q", "-m", "adversarial source")
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    original = tracked.read_bytes()
    release_gate_module = sys.modules[scan_publishable_content.__module__]
    request_document = json.loads(_coverage_test_binding(repository))
    request_document.update(
        {
            "source_root": str(_COVERAGE_RUNNER.ROOT.resolve(strict=True)),
            "outputs_root": str(outputs.resolve(strict=True)),
            "tree_mode": "working-pre-cutover",
            "build_distributions": False,
        }
    )
    request = _COVERAGE_RUNNER._coverage_scan_request_document(
        json.dumps(request_document, sort_keys=True, separators=(",", ":")).encode()
    )
    inventory = _COVERAGE_RUNNER._coverage_scan_inventory(request)
    tracked.write_bytes(transient)
    try:
        observed = release_gate_module._secure_read_bytes(
            repository,
            PurePosixPath("tracked.txt"),
            context="publishable tracked source",
        )
        with pytest.raises(AssertionError, match="coverage test repository binding"):
            _COVERAGE_RUNNER._validate_coverage_scan_read(
                request,
                inventory,
                repository,
                PurePosixPath("tracked.txt"),
                observed,
            )
    finally:
        tracked.write_bytes(original)

    assert observed == transient
    assert tracked.read_bytes() == original


@pytest.mark.parametrize(
    "parent_mutation",
    (
        "public-scanner",
        "public-reader",
        "decorated-reader-helper",
        "sensitive-suffix-set",
        "runtime-name-set",
        "allowance-map",
    ),
)
def test_bound_coverage_scan_uses_fresh_child_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parent_mutation: str,
) -> None:
    repository, _tracked = _coverage_test_repository(tmp_path)
    readme = repository / "README.md"
    marker = "PLACE" + "HOLDER"
    readme.write_text(marker + "\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-q", "-m", "scanner namespace fixture")
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    release_gate_module = sys.modules[scan_publishable_content.__module__]
    publishable_tree_module = release_gate_module.publishable_tree_module
    cleanups: list[Any] = []

    def parent_reader(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("parent public reader reached")

    def parent_reader_helper(*args: object, **kwargs: object) -> Any:
        raise AssertionError("parent decorated reader helper reached")

    if parent_mutation == "public-scanner":
        monkeypatch.setattr(
            release_gate_module,
            "scan_publishable_content",
            parent_reader_helper,
        )
    elif parent_mutation == "public-reader":
        monkeypatch.setattr(release_gate_module, "_secure_read_bytes", parent_reader)
    elif parent_mutation == "decorated-reader-helper":
        monkeypatch.setattr(release_gate_module, "_path_snapshots", parent_reader_helper)
    elif parent_mutation == "sensitive-suffix-set":
        publishable_tree_module._SENSITIVE_SUFFIXES.add(".txt")
        cleanups.append(
            lambda: publishable_tree_module._SENSITIVE_SUFFIXES.discard(".txt")
        )
    elif parent_mutation == "runtime-name-set":
        publishable_tree_module._RUNTIME_COMPACT.add("tracked")
        cleanups.append(
            lambda: publishable_tree_module._RUNTIME_COMPACT.discard("tracked")
        )
    else:
        marker_digest = hashlib.sha256(marker.encode()).hexdigest()
        allowances = publishable_tree_module.EXACT_PLACEHOLDER_REFERENCE_SHA256
        previous = allowances.get("README.md")
        allowances["README.md"] = {1: marker_digest}

        def restore_allowance() -> None:
            if previous is None:
                allowances.pop("README.md", None)
            else:
                allowances["README.md"] = previous

        cleanups.append(restore_allowance)
    monkeypatch.setenv(
        _COVERAGE_TEST_REPOSITORY_BINDING,
        _coverage_test_binding(repository),
    )

    try:
        result = _scan_coverage_publishable_content(
            outputs_root=outputs,
            tree_mode="working-pre-cutover",
            build_distributions=False,
        )
    finally:
        for cleanup in reversed(cleanups):
            cleanup()

    assert result == {
        "passed": False,
        "violations": [
            "current package catalog path cannot be inspected: "
            "docs/operator/audited-deck-catalog.json",
            "public_placeholder:README.md:1",
            "unexpected_root:tracked.txt",
        ],
        "tracked_files_scanned": 2,
        "current_packages_scanned": 0,
        "distribution_artifacts_scanned": 0,
    }


def test_bound_coverage_scan_rejects_callback_path_without_invoking_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _tracked = _coverage_test_repository(tmp_path)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    callback_invoked = False

    class CallbackPath(os.PathLike[str]):
        def __fspath__(self) -> str:
            nonlocal callback_invoked
            callback_invoked = True
            return str(outputs)

    monkeypatch.setenv(
        _COVERAGE_TEST_REPOSITORY_BINDING,
        _coverage_test_binding(repository),
    )

    with pytest.raises(AssertionError, match="coverage test repository binding"):
        _scan_coverage_publishable_content(
            outputs_root=CallbackPath(),
            tree_mode="working-pre-cutover",
            build_distributions=False,
        )

    assert callback_invoked is False


def test_coverage_scan_repository_accepts_clean_autocrlf_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "autocrlf-repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "tests@example.invalid")
    _git(repository, "config", "user.name", "HSConfig Tests")
    _git(repository, "config", "core.autocrlf", "true")
    tracked = repository / "tracked.txt"
    committed = b"first line\nsecond line\n"
    tracked.write_bytes(committed)
    _git(repository, "add", "tracked.txt")
    _git(repository, "commit", "-q", "-m", "autocrlf materialization")
    tracked.write_bytes(b"force Git checkout materialization")
    _git(repository, "read-tree", "--reset", "-u", "HEAD")
    repository = repository.resolve(strict=True)
    assert _git(repository, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert tracked.read_bytes() == committed.replace(b"\n", b"\r\n")
    assert (
        _COVERAGE_RUNNER._bound_git_output(
            "cat-file",
            "blob",
            "HEAD:tracked.txt",
            maximum_bytes=1024,
            repository=repository,
        )
        == committed
    )
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv(
        _COVERAGE_TEST_REPOSITORY_BINDING,
        _coverage_test_binding(repository),
    )

    result = _scan_coverage_publishable_content(
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
        build_distributions=False,
    )

    assert result["tracked_files_scanned"] == 1


def _jwt_value() -> str:
    return "ey" + "JhbGciOiJIUzI1NiJ9." + "ey" + "JzdWIiOiIxMjMifQ." + "signature1234567890"


def _git(root: Path, *args: str) -> str:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.upper().startswith("GIT_"):
            environment.pop(key, None)
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return completed.stdout.strip()


def _coverage_scan_binding() -> tuple[Path, str, str, object]:
    supplied = os.environ.get(_COVERAGE_TEST_REPOSITORY_BINDING)
    legacy = os.environ.get(_COVERAGE_TEST_REPOSITORY_ROOT)
    if supplied is None or legacy is not None:
        raise AssertionError("coverage test repository binding is invalid")
    try:
        encoded = supplied.encode("utf-8")
        if not encoded or len(encoded) > 16 * 1024:
            raise ValueError("binding size")
        document = _COVERAGE_RUNNER.json.loads(
            encoded,
            object_pairs_hook=_COVERAGE_RUNNER._closed_object,
        )
        if not isinstance(document, dict) or set(document) != {
            "schema_version",
            "repository",
            "commit_oid",
            "tree_oid",
            "root_identity",
        }:
            raise ValueError("binding shape")
        identity = document["root_identity"]
        if not isinstance(identity, dict) or set(identity) != {
            "device",
            "inode",
            "size",
            "modified_ns",
            "changed_ns",
            "mode",
        }:
            raise ValueError("identity shape")
        identity_values = tuple(
            identity[key]
            for key in (
                "device",
                "inode",
                "size",
                "modified_ns",
                "changed_ns",
                "mode",
            )
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in identity_values
        ):
            raise ValueError("identity values")
        repository_value = document["repository"]
        commit_oid = document["commit_oid"]
        tree_oid = document["tree_oid"]
        schema_version = document["schema_version"]
        if (
            not isinstance(schema_version, int)
            or isinstance(schema_version, bool)
            or schema_version != 1
            or not isinstance(repository_value, str)
            or not repository_value
            or not isinstance(commit_oid, str)
            or re.fullmatch(r"[0-9a-f]{40}", commit_oid) is None
            or not isinstance(tree_oid, str)
            or re.fullmatch(r"[0-9a-f]{40}", tree_oid) is None
        ):
            raise ValueError("binding values")
        candidate = Path(repository_value)
        metadata = candidate.lstat()
        repository = candidate.resolve(strict=True)
        root_identity = _COVERAGE_RUNNER._PathIdentity(*identity_values)
    except (KeyError, OSError, RuntimeError, TypeError, UnicodeError, ValueError) as exc:
        raise AssertionError("coverage test repository binding is invalid") from exc
    if (
        not candidate.is_absolute()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _COVERAGE_RUNNER._is_reparse(metadata)
        or repository != candidate
        or _COVERAGE_RUNNER._identity(metadata) != root_identity
    ):
        raise AssertionError("coverage test repository binding is invalid")
    return repository, commit_oid, tree_oid, root_identity


def _validate_coverage_scan_binding(
    repository: Path,
    commit_oid: str,
    tree_oid: str,
    root_identity: object,
) -> None:
    try:
        before = repository.lstat()
        top_level_source = _COVERAGE_RUNNER._bound_git_output(
            "rev-parse",
            "--show-toplevel",
            maximum_bytes=32 * 1024,
            repository=repository,
        )
        top_level = Path(top_level_source.decode("utf-8").strip()).resolve(strict=True)
        head = _COVERAGE_RUNNER._bound_git_oid("HEAD", repository=repository)
        head_tree = _COVERAGE_RUNNER._bound_git_oid("HEAD^{tree}", repository=repository)
        committed_tree = _COVERAGE_RUNNER._bound_git_oid(
            f"{commit_oid}^{{tree}}",
            repository=repository,
        )
        _COVERAGE_RUNNER._assert_default_git_index(repository=repository)
        status = _COVERAGE_RUNNER._bound_git_output(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            maximum_bytes=1024 * 1024,
            repository=repository,
        )
        after = repository.lstat()
    except (OSError, RuntimeError, UnicodeError) as exc:
        raise AssertionError("coverage test repository binding is invalid") from exc
    if (
        _COVERAGE_RUNNER._identity(before) != root_identity
        or _COVERAGE_RUNNER._identity(after) != root_identity
        or top_level != repository
        or head != commit_oid
        or head_tree != tree_oid
        or committed_tree != tree_oid
        or status != b""
    ):
        raise AssertionError("coverage test repository binding is invalid")


@contextmanager
def _coverage_scan_repository() -> Iterator[Path]:
    supplied = os.environ.get(_COVERAGE_TEST_REPOSITORY_BINDING)
    legacy = os.environ.get(_COVERAGE_TEST_REPOSITORY_ROOT)
    if supplied is None and legacy is None:
        yield ROOT
        return
    repository, commit_oid, tree_oid, root_identity = _coverage_scan_binding()
    _validate_coverage_scan_binding(repository, commit_oid, tree_oid, root_identity)
    try:
        yield repository
    finally:
        _validate_coverage_scan_binding(
            repository,
            commit_oid,
            tree_oid,
            root_identity,
        )


def _scan_coverage_publishable_content(
    *,
    outputs_root: Any,
    tree_mode: str,
    build_distributions: bool,
) -> dict[str, Any]:
    supplied = os.environ.get(_COVERAGE_TEST_REPOSITORY_BINDING)
    legacy = os.environ.get(_COVERAGE_TEST_REPOSITORY_ROOT)
    if supplied is None and legacy is None:
        return scan_publishable_content(
            repository=ROOT,
            outputs_root=outputs_root,
            tree_mode=tree_mode,
            build_distributions=build_distributions,
        )
    if supplied is None or legacy is not None:
        raise AssertionError("coverage test repository binding is invalid")
    return _COVERAGE_RUNNER._run_bound_coverage_scan(
        binding_json=supplied,
        outputs_root=outputs_root,
        tree_mode=tree_mode,
        build_distributions=build_distributions,
    )


def _audited_report_bytes() -> dict[str, tuple[bytes, bytes]]:
    global _AUDITED_REPORT_BYTES
    with _AUDITED_REPORT_BYTES_LOCK:
        if _AUDITED_REPORT_BYTES is None:
            temporary_path: Path | None = None
            with tempfile.TemporaryDirectory(prefix="hsconfig-release-gate-reports-") as temporary:
                temporary_path = Path(temporary)
                packages = prepare_audited_packages(temporary_path)
                if tuple(packages) != AUDITED_DECK_NAMES:
                    raise AssertionError("release_gate_audited_package_catalog_mismatch")
                _AUDITED_REPORT_BYTES = {
                    deck_name: (
                        (package / "reports" / "disposition_ledger.json").read_bytes(),
                        (package / "reports" / "source_contract_audit.json").read_bytes(),
                    )
                    for deck_name, package in packages.items()
                }
            if temporary_path is None or temporary_path.exists():
                raise AssertionError("release_gate_audited_package_cache_residue")
        return _AUDITED_REPORT_BYTES


def _repository(tmp_path: Path) -> tuple[Path, Path]:
    report_bytes = _audited_report_bytes()
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "-c", "core.longpaths=true", "init", "-q")
    _git(root, "config", "--local", "core.longpaths", "true")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "HSConfig Tests")
    _git(root, "remote", "add", "origin", "https://github.com/Teufelsboy/HSConfig.git")
    (root / "pyproject.toml").write_text(
        '[project]\nname="hsconfig"\ndynamic=["version"]\n', encoding="utf-8"
    )
    (root / ".gitignore").write_text(
        "*.local-release-evidence\n",
        encoding="utf-8",
    )
    (root / "src" / "hsconfig").mkdir(parents=True)
    (root / "src" / "hsconfig" / "version.py").write_text(
        '__version__ = "1.0.0"\n', encoding="utf-8"
    )
    (root / "src" / "hsconfig" / "release_gate.py").write_bytes(
        (ROOT / "src" / "hsconfig" / "release_gate.py").read_bytes()
    )
    (root / "src" / "hsconfig" / "publishable_tree.py").write_bytes(
        (ROOT / "src" / "hsconfig" / "publishable_tree.py").read_bytes()
    )
    (root / "docs" / "operator").mkdir(parents=True)
    (root / "docs" / "operator" / "README.md").write_text(
        "Canonical release gate.\n", encoding="utf-8"
    )
    outputs = root / "outputs"
    outputs.mkdir()
    catalog = json.loads(
        (ROOT / "docs" / "operator" / "audited-deck-catalog.json").read_text(
            encoding="utf-8"
        )
    )
    (root / "docs" / "operator" / "audited-deck-catalog.json").write_text(
        json.dumps(catalog, sort_keys=True), encoding="utf-8"
    )
    near100_fixtures = root / "tests" / "fixtures" / "near100"
    near100_fixtures.mkdir(parents=True)
    for name in ("current_semantic_inventory.json", "score_metric_contract.json"):
        (near100_fixtures / name).write_bytes(
            (ROOT / "tests" / "fixtures" / "near100" / name).read_bytes()
    )
    semantic_inventory = json.loads(
        (ROOT / "tests" / "fixtures" / "near100" / "current_semantic_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    semantic_by_deck = {row["deck_name"]: row for row in semantic_inventory["decks"]}
    for row in catalog["decks"]:
        deck_root = outputs / row["deck_name"]
        semantic_deck = semantic_by_deck[row["deck_name"]]
        content_root = "a" * 64
        revision = deck_root / "revisions" / f"sha256-{content_root}"
        revision.mkdir(parents=True)
        (revision / "package.json").write_text("{}\n", encoding="utf-8")
        reports = revision / "04_package" / "reports"
        reports.mkdir(parents=True)
        for report_name, data in zip(
            ("disposition_ledger.json", "source_contract_audit.json"),
            report_bytes[row["deck_name"]],
            strict=True,
        ):
            (reports / report_name).write_bytes(data)
        (deck_root / "current.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "deck_name": row["deck_name"],
                    "deck_fingerprint": semantic_deck["deck_fingerprint"],
                    "content_root_sha256": content_root,
                    "revision": f"revisions/sha256-{content_root}",
                }
            ),
            encoding="utf-8",
        )
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "fixture")
    return root, outputs


def _first_report(repository: Path, outputs: Path, name: str) -> Path:
    inventory = json.loads(
        (repository / "tests/fixtures/near100/current_semantic_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    deck_name = inventory["decks"][0]["deck_name"]
    current = json.loads((outputs / deck_name / "current.json").read_text(encoding="utf-8"))
    return outputs / deck_name / current["revision"] / "04_package" / "reports" / name


def _rehash_inventory(inventory: dict[str, Any]) -> None:
    content = {
        key: value for key, value in inventory.items() if key != "canonical_content_sha256"
    }
    inventory["canonical_content_sha256"] = hashlib.sha256(
        json.dumps(content, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _completed(command: tuple[str, ...], *, passed: bool = True) -> subprocess.CompletedProcess[str]:
    name = command[-1] if command and command[-1] in EXPECTED_CHECKS else "check"
    payload: dict[str, Any] = {"passed": passed, "check": name}
    if "check_near100_scorecard.py" in " ".join(command):
        payload.update(
            {
                "version": "1.0.0",
                "overall_score": "100",
                "metrics": [],
                "open_p0_findings": 0,
                "open_p1_findings": 0,
            }
        )
    return subprocess.CompletedProcess(
        command,
        0 if passed else 7,
        stdout=json.dumps(payload),
        stderr="",
    )


@pytest.mark.skipif(os.name != "nt", reason="Git for Windows path handling only")
def test_repository_fixture_supports_runner_length_paths_with_local_git_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows_max_path = 260
    process_cwd_safety_margin = 20
    runner_prefix = "runner-temp-"
    report_relative = (
        Path("repository")
        / "outputs"
        / "ShadowPriest"
        / "revisions"
        / ("sha256-" + ("a" * 64))
        / "04_package"
        / "reports"
        / "source_contract_audit.json"
    )
    unpadded_report = tmp_path / runner_prefix / report_relative
    padding_length = max(0, windows_max_path - len(str(unpadded_report)))
    runner_length_tmp = tmp_path / (runner_prefix + ("x" * padding_length))
    runner_length_tmp.mkdir(parents=True)
    repository_cwd = runner_length_tmp / "repository"
    deepest_report = runner_length_tmp / report_relative
    assert len(str(deepest_report)) >= windows_max_path
    assert len(str(repository_cwd)) <= windows_max_path - process_cwd_safety_margin
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.longpaths")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")

    repository, outputs = _repository(runner_length_tmp)

    assert outputs.is_dir()
    assert deepest_report.is_file()
    assert _git(repository, "status", "--porcelain") == ""
    assert _git(repository, "config", "--local", "--get", "core.longpaths") == "true"


def test_gate_declares_the_exact_named_checks() -> None:
    assert CHECK_NAMES == EXPECTED_CHECKS


def test_result_json_is_stable_and_contains_the_public_contract() -> None:
    result = ReleaseGateResult(
        passed=False,
        final_release_ready=False,
        version="1.0.0",
        commit_oid="a" * 40,
        checks=(
            ReleaseCheck(
                name="ruff",
                passed=True,
                command=("python", "-m", "ruff", "check", "."),
                details={"returncode": 0},
            ),
        ),
    )

    first = result.to_json()
    second = result.to_json()

    assert first == second
    assert first == json.dumps(
        result.to_document(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def test_gate_uses_argument_arrays_timeouts_and_propagates_failed_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    def runner(command: tuple[str, ...] | list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = tuple(command)
        calls.append((argv, kwargs))
        if "run_contract_mutations.py" in " ".join(argv):
            return _completed(argv, passed=False)
        return _completed(argv)

    monkeypatch.setattr("hsconfig.release_gate._execute_bounded", runner)
    monkeypatch.setattr("hsconfig.release_gate._verify_module_binding", lambda *_: None)
    monkeypatch.setattr(
        "hsconfig.release_gate._validate_repository",
        lambda repository, outputs_root, tree_mode, **_: (
            Path(repository).resolve(),
            Path(outputs_root).resolve(),
            "a" * 40,
        ),
    )
    monkeypatch.setattr(
        "hsconfig.release_gate._capture_snapshot",
        lambda repository, outputs_root, **_: type(
            "Snapshot", (), {"commit_oid": "a" * 40}
        )(),
    )
    monkeypatch.setattr(
        "hsconfig.release_gate._assert_snapshot_unchanged", lambda *_, **__: None
    )

    result = run_release_gate(
        repository=repository,
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
    )

    assert result.passed is False
    failed = next(check for check in result.checks if check.name == "contract_mutations")
    assert failed.details["returncode"] == 7
    assert tuple(check.name for check in result.checks) == EXPECTED_CHECKS
    assert calls
    assert all(isinstance(command, tuple) for command, _ in calls)
    assert all(isinstance(options["timeout"], int) for _, options in calls)


def test_gate_subprocess_environment_discards_host_python_and_pip_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    observed: list[dict[str, str]] = []
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "hostile"))
    monkeypatch.setenv("PYTHONHOME", str(tmp_path / "fake-home"))
    monkeypatch.setenv("PIP_INDEX_URL", "https://attacker.invalid/simple")
    monkeypatch.setenv("PIP_CONFIG_FILE", str(tmp_path / "pip.ini"))

    def runner(command: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed.append(kwargs["env"])
        return _completed(command)

    monkeypatch.setattr("hsconfig.release_gate._execute_bounded", runner)
    monkeypatch.setattr("hsconfig.release_gate._verify_module_binding", lambda *_: None)
    monkeypatch.setattr(
        "hsconfig.release_gate._validate_repository",
        lambda repository, outputs_root, tree_mode, **_: (
            Path(repository).resolve(),
            Path(outputs_root).resolve(),
            "a" * 40,
        ),
    )
    monkeypatch.setattr(
        "hsconfig.release_gate._build_base_evidence",
        lambda **_: {"schema_version": 1, "evidence": {}, "receipts": {}},
    )
    monkeypatch.setattr(
        "hsconfig.release_gate._capture_snapshot",
        lambda repository, outputs_root, **_: type(
            "Snapshot", (), {"commit_oid": "a" * 40}
        )(),
    )
    monkeypatch.setattr(
        "hsconfig.release_gate._assert_snapshot_unchanged", lambda *_, **__: None
    )

    run_release_gate(
        repository=repository,
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
    )

    assert observed
    assert all(environment.get("PYTHONHOME") is None for environment in observed)
    assert all(environment.get("PIP_INDEX_URL") is None for environment in observed)
    assert all(not any(key.startswith("GIT_") for key in environment) for environment in observed)
    assert all(environment["PIP_CONFIG_FILE"] == os.devnull for environment in observed)
    assert all(environment["PYTHONNOUSERSITE"] == "1" for environment in observed)
    assert all(environment["PYTHONPATH"] == str(repository / "src") for environment in observed)
    assert all(environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1" for environment in observed)
    assert all(
        environment["PYTEST_PLUGINS"]
        == "pytest_cov.plugin,_hypothesis_pytestplugin"
        for environment in observed
    )


def test_controlled_environment_runs_real_repository_property_test_without_residue() -> None:
    residue = (ROOT / ".hypothesis", ROOT / ".pytest_cache", ROOT / "coverage.json")
    assert all(not path.exists() for path in residue)
    environment = _controlled_environment(ROOT)
    completed = _execute_bounded(
        (
            sys.executable,
            "-m",
            "pytest",
            "tests/property/test_path_and_manifest_properties.py::"
            "test_canonical_relative_path_rejects_all_traversal_and_native_path_forms",
            "-q",
        ),
        cwd=ROOT,
        env=environment,
        timeout=120,
    )

    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert environment["PYTEST_PLUGINS"] == "pytest_cov.plugin,_hypothesis_pytestplugin"
    assert completed.returncode == 0, completed.stderr
    assert "1 passed" in completed.stdout
    assert all(not path.exists() for path in residue)


@pytest.fixture(scope="module")
def real_active_runtime_template(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Path]:
    fixture_root = tmp_path_factory.mktemp("real-active-runtime")
    seed_repository = fixture_root / "seed-repository"
    seed_repository.mkdir()
    archive = fixture_root / "repository.tar"
    subprocess.run(
        [
            "git",
            "-c",
            "core.autocrlf=false",
            "archive",
            "--format=tar",
            "-o",
            str(archive),
            "HEAD",
        ],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive) as source:
        source.extractall(seed_repository)
    subprocess.run(["git", "init", "-q"], cwd=seed_repository, check=True)
    subprocess.run(
        ["git", "config", "core.autocrlf", "false"],
        cwd=seed_repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "--local", "core.longpaths", "true"],
        cwd=seed_repository,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=seed_repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Active Binding Contract",
            "-c",
            "user.email=active-binding@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=seed_repository,
        check=True,
    )
    repository = fixture_root / "repository"
    subprocess.run(
        [
            "git",
            "-c",
            "core.longpaths=true",
            "-c",
            "core.autocrlf=true",
            "clone",
            "-q",
            str(seed_repository),
            str(repository),
        ],
        cwd=fixture_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "--local", "core.longpaths", "true"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "core.autocrlf", "true"],
        cwd=repository,
        check=True,
    )
    bootstrap_root = fixture_root / "bootstrap"
    bootstrap_root.mkdir()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv("GITHUB_SHA", raising=False)
        binding = BOOTSTRAP._bootstrap_environment(repository, bootstrap_root)
    sentinel = fixture_root / "sentinel.txt"
    sentinel.write_text(binding.sentinel, encoding="ascii")
    return {
        "repository": repository,
        "bootstrap_root": bootstrap_root,
        "manifest": binding.manifest_path,
        "python": binding.python,
        "sentinel": sentinel,
    }


def _write_active_runtime_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    template: dict[str, Path],
) -> dict[str, Path]:
    bootstrap_root = tmp_path / "bootstrap"
    shutil.copytree(template["bootstrap_root"], bootstrap_root)
    source_root = bootstrap_root / "committed-source"
    controller = source_root / "scripts" / "check_release_gate.py"
    build_backend_root = bootstrap_root / "build-backend"
    sentinel = "d" * 64
    manifest = json.loads(template["manifest"].read_text(encoding="utf-8"))
    old_root = template["bootstrap_root"]
    manifest["build_backend_root"] = str(build_backend_root)
    manifest["environment_root"] = str(Path(sys.prefix).resolve(strict=True))
    manifest["sentinel_sha256"] = hashlib.sha256(
        sentinel.encode("ascii")
    ).hexdigest()
    for artifact in manifest["artifacts"]:
        artifact["wheel_path"] = str(
            bootstrap_root / Path(artifact["wheel_path"]).relative_to(old_root)
        )
    manifest["local_project"]["wheel_path"] = str(
        bootstrap_root
        / Path(manifest["local_project"]["wheel_path"]).relative_to(old_root)
    )
    manifest_path = bootstrap_root / "runtime-manifest.json"
    manifest_source = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_source)
    monkeypatch.setenv("HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL", sentinel)
    monkeypatch.setenv("HSCONFIG_RUNTIME_MANIFEST", str(manifest_path))
    monkeypatch.setenv(
        "HSCONFIG_RUNTIME_MANIFEST_SHA256",
        hashlib.sha256(manifest_source).hexdigest(),
    )
    monkeypatch.setattr(sys, "argv", [str(controller), "--json"])
    return {
        "repository": template["repository"],
        "bootstrap_root": bootstrap_root,
        "source_root": source_root,
        "controller": controller,
        "bound_module": source_root / "src" / "hsconfig" / "version.py",
        "build_backend_root": build_backend_root,
        "manifest": manifest_path,
        "local_wheel": Path(manifest["local_project"]["wheel_path"]),
    }


def _rewrite_active_runtime_manifest(
    binding: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, Any],
) -> None:
    source = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    binding["manifest"].write_bytes(source)
    monkeypatch.setenv(
        "HSCONFIG_RUNTIME_MANIFEST_SHA256",
        hashlib.sha256(source).hexdigest(),
    )


@pytest.mark.parametrize(
    "values",
    (
        {"HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL": "d" * 64},
        {
            "HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL": "d" * 64,
            "HSCONFIG_RUNTIME_MANIFEST": "",
            "HSCONFIG_RUNTIME_MANIFEST_SHA256": "not-a-digest",
        },
    ),
    ids=("partial", "malformed"),
)
def test_active_runtime_binding_fails_closed_before_specs_or_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    values: dict[str, str],
) -> None:
    for name in (
        "HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL",
        "HSCONFIG_RUNTIME_MANIFEST",
        "HSCONFIG_RUNTIME_MANIFEST_SHA256",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(ROOT)
    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _command_specs(ROOT, tmp_path / "outputs", "working-pre-cutover")
    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _controlled_environment(ROOT)


def test_active_runtime_binding_rejects_post_binding_source_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    bound_module = binding["bound_module"]
    original = release_gate_module._secure_read_bytes
    mutated = False

    def mutate_after_controller_read(*args: object, **kwargs: object) -> bytes:
        nonlocal mutated
        source = original(*args, **kwargs)
        relative = args[1]
        if str(relative) == "src/hsconfig/version.py" and not mutated:
            mutated = True
            bound_module.write_text("VALUE = 2\n", encoding="utf-8")
        return source

    monkeypatch.setattr(
        release_gate_module,
        "_secure_read_bytes",
        mutate_after_controller_read,
    )

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])
    assert mutated is True


def test_active_runtime_binding_uses_committed_lock_bytes_with_autocrlf_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    repository = binding["repository"]
    lock_path = repository / "pylock.3.11.toml"
    assert b"\r\n" in lock_path.read_bytes()
    assert b"\r\n" not in (
        binding["source_root"] / "pylock.3.11.toml"
    ).read_bytes()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""

    assert _active_runtime_paths(repository) == (
        binding["source_root"],
        binding["build_backend_root"],
    )


def test_active_head_inventory_rejects_export_subst_archive_bytes(
    tmp_path: Path,
) -> None:
    import hsconfig.release_gate as release_gate_module

    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "core.autocrlf", "false"], cwd=repository, check=True
    )
    (repository / ".gitattributes").write_text(
        "version.txt export-subst\n", encoding="utf-8"
    )
    (repository / "version.txt").write_text("$Format:%H$\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    commit_oid = _git(repository, "rev-parse", "HEAD")

    with pytest.raises(ReleaseGateError, match="archive differs from tree blobs"):
        release_gate_module._active_head_source_inventory(repository, commit_oid)


def test_active_git_blob_batch_rejects_missing_object(tmp_path: Path) -> None:
    import hsconfig.release_gate as release_gate_module

    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    entries = (
        {
            "path": "missing.txt",
            "git_mode": "100644",
            "blob_oid": "f" * 40,
        },
    )

    with pytest.raises(ReleaseGateError, match="Git blob batch is invalid"):
        release_gate_module._git_blob_payloads(repository, entries)


def test_active_git_blob_batch_rejects_malformed_check_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hsconfig.release_gate as release_gate_module

    repository = tmp_path / "repository"
    repository.mkdir()
    entries = (
        {
            "path": "tracked.txt",
            "git_mode": "100644",
            "blob_oid": "1" * 40,
        },
    )

    monkeypatch.setattr(
        release_gate_module,
        "_run_git_blob_batch",
        lambda *args, **kwargs: b"malformed\n",
    )

    with pytest.raises(ReleaseGateError, match="Git blob batch is invalid"):
        release_gate_module._git_blob_payloads(repository, entries)


@pytest.mark.parametrize(
    "check_line",
    (
        b" e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 blob 0\n",
        b"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 blob 0 \n",
        b"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391\tblob 0\n",
        b"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391  blob 0\n",
    ),
    ids=("leading", "trailing", "tab", "repeated"),
)
def test_active_git_blob_batch_rejects_noncanonical_check_whitespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    check_line: bytes,
) -> None:
    import hsconfig.release_gate as release_gate_module

    oid = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    responses = iter((check_line, f"{oid} blob 0\n\n".encode("ascii")))
    monkeypatch.setattr(
        release_gate_module,
        "_run_git_blob_batch",
        lambda *args, **kwargs: next(responses),
    )

    with pytest.raises(ReleaseGateError, match="Git blob batch is invalid"):
        release_gate_module._git_blob_payloads(
            tmp_path,
            ({"path": "empty", "git_mode": "100644", "blob_oid": oid},),
        )


def test_active_runtime_binding_rejects_unmanifested_overlay_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    (binding["build_backend_root"] / "unbound.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


def test_active_runtime_binding_rejects_manifest_commit_mismatch_before_specs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    manifest_path = binding["manifest"]
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    document["commit_oid"] = "a" * 40
    source = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest_path.write_bytes(source)
    monkeypatch.setenv(
        "HSCONFIG_RUNTIME_MANIFEST_SHA256",
        hashlib.sha256(source).hexdigest(),
    )

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _command_specs(
            binding["repository"], tmp_path / "outputs", "working-pre-cutover"
        )


def test_active_runtime_binding_rejects_self_consistent_two_row_source_subset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    kept = {
        "scripts/check_release_gate.py",
        "src/hsconfig/version.py",
    }
    document["source_inventory"] = [
        row for row in document["source_inventory"] if row["path"] in kept
    ]
    assert len(document["source_inventory"]) == 2
    digest = BOOTSTRAP._source_inventory_digest(document["source_inventory"])
    document["source_inventory_sha256"] = digest
    document["local_project"]["source_inventory_sha256"] = digest
    for path in binding["source_root"].rglob("*"):
        if path.is_file() and path.relative_to(binding["source_root"]).as_posix() not in kept:
            path.unlink()
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


def test_active_runtime_binding_rejects_self_consistent_two_artifact_subset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    installed = next(row for row in document["artifacts"] if row["install"] is True)
    coverage = next(row for row in document["artifacts"] if row["name"] == "coverage")
    document["artifacts"] = sorted(
        (installed, coverage), key=lambda row: row["name"].casefold()
    )
    allowed = set(coverage["allowed_startup_surfaces"])
    expected_overlay = {
        row["path"] for row in coverage["files"] if row["path"] not in allowed
    }
    for path in binding["build_backend_root"].rglob("*"):
        if path.is_file() and path.relative_to(
            binding["build_backend_root"]
        ).as_posix() not in expected_overlay:
            path.unlink()
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


def test_active_runtime_binding_rejects_local_wheel_byte_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    with binding["local_wheel"].open("ab") as wheel:
        wheel.write(b"post-manifest mutation")

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


@pytest.mark.parametrize(
    "substitution",
    ("version", "path", "digest", "files"),
)
def test_active_runtime_binding_rejects_local_project_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    substitution: str,
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    local = document["local_project"]
    if substitution == "version":
        local["version"] = "999.0.0"
    elif substitution == "path":
        substitute = binding["bootstrap_root"] / "substitute.whl"
        shutil.copy2(binding["local_wheel"], substitute)
        local["wheel_path"] = str(substitute)
    elif substitution == "digest":
        local["sha256"] = "a" * 64
    else:
        local["files"] = []
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


def _unbounded_test_wheel_rows(wheel: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            payload = archive.read(info)
            rows.append(
                {
                    "path": info.filename,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    return sorted(rows, key=lambda row: str(row["path"]))


def _append_unsafe_wheel_members(
    wheel: Path, unsafe_kind: str
) -> list[dict[str, object]]:
    additions: list[dict[str, object]] = []
    with zipfile.ZipFile(
        wheel,
        "a",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        if unsafe_kind == "oversized":
            payload = b"0" * (1024 * 1024)
            digest = hashlib.sha256(payload).hexdigest()
            for index in range(129):
                path = f"unsafe-payload/{index:03d}.bin"
                archive.writestr(path, payload)
                additions.append(
                    {"path": path, "size": len(payload), "sha256": digest}
                )
        elif unsafe_kind == "casefold":
            for path, payload in (
                ("unsafe-package/A.py", b"A = 1\n"),
                ("unsafe-package/a.py", b"A = 2\n"),
            ):
                archive.writestr(path, payload)
                additions.append(
                    {
                        "path": path,
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
        elif unsafe_kind == "prefix":
            archive.writestr("unsafe-prefix/", b"")
            payload = b"not a directory\n"
            archive.writestr("unsafe-prefix", payload)
            additions.append(
                {
                    "path": "unsafe-prefix",
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        else:
            reserved_names = {
                "reserved_con": "package/CON.py",
                "reserved_lpt9": "package/lPt9.json",
                "reserved_com1": "package/CoM¹.Py",
                "reserved_lpt3": "package/LPT³.txt",
            }
            path = reserved_names[unsafe_kind]
            payload = b"reserved = True\n"
            archive.writestr(path, payload)
            additions.append(
                {
                    "path": path,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    return additions


@pytest.mark.parametrize("surface", ("dependency", "local"))
@pytest.mark.parametrize("unsafe_kind", ("oversized", "casefold", "prefix"))
def test_active_runtime_binding_rejects_unsafe_dependency_and_local_wheels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    surface: str,
    unsafe_kind: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    if surface == "local":
        wheel = binding["local_wheel"]
        target = document["local_project"]
    else:
        target = next(row for row in document["artifacts"] if row["install"] is True)
        wheel = Path(target["wheel_path"])
    additions = _append_unsafe_wheel_members(wheel, unsafe_kind)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    target["sha256"] = digest
    target["files"] = sorted(
        [*target["files"], *additions],
        key=lambda row: str(row["path"]),
    )
    if surface == "dependency":
        original_lock_rows = release_gate_module._active_lock_rows

        def selected_lock_rows(source: bytes) -> list[dict[str, object]]:
            rows = original_lock_rows(source)
            locked = next(row for row in rows if row["name"] == target["name"])
            candidate = next(
                row
                for row in locked["wheels"]
                if row["name"] == wheel.name
            )
            candidate["sha256"] = digest
            return rows

        monkeypatch.setattr(
            release_gate_module,
            "_active_lock_rows",
            selected_lock_rows,
        )
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


@pytest.mark.parametrize("surface", ("dependency", "local"))
@pytest.mark.parametrize(
    "unsafe_kind",
    ("reserved_con", "reserved_lpt9", "reserved_com1", "reserved_lpt3"),
)
def test_active_runtime_binding_rejects_windows_reserved_wheel_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    surface: str,
    unsafe_kind: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    target = (
        document["local_project"]
        if surface == "local"
        else next(row for row in document["artifacts"] if row["install"] is True)
    )
    wheel = Path(target["wheel_path"])
    additions = _append_unsafe_wheel_members(wheel, unsafe_kind)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    target["sha256"] = digest
    target["files"] = sorted(
        [*target["files"], *additions],
        key=lambda row: str(row["path"]),
    )
    if surface == "dependency":
        original_lock_rows = release_gate_module._active_lock_rows

        def selected_lock_rows(source: bytes) -> list[dict[str, object]]:
            rows = original_lock_rows(source)
            locked = next(row for row in rows if row["name"] == target["name"])
            candidate = next(
                row for row in locked["wheels"] if row["name"] == wheel.name
            )
            candidate["sha256"] = digest
            return rows

        monkeypatch.setattr(
            release_gate_module,
            "_active_lock_rows",
            selected_lock_rows,
        )
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


def _rewrite_wheel_member_header(
    wheel: Path,
    *,
    filename: str,
    method: int | None = None,
    set_flag_bits: int = 0,
) -> None:
    source = bytearray(wheel.read_bytes())
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        member = next(info for info in archive.infolist() if info.filename == filename)
        encoded_filename = member.filename.encode("utf-8")
        if set_flag_bits:
            flags = int.from_bytes(
                source[member.header_offset + 6 : member.header_offset + 8],
                "little",
            )
            source[member.header_offset + 6 : member.header_offset + 8] = (
                flags | set_flag_bits
            ).to_bytes(2, "little")
        if method is not None:
            source[member.header_offset + 8 : member.header_offset + 10] = (
                method.to_bytes(2, "little")
            )
    offset = 0
    found = False
    while True:
        offset = source.find(b"PK\x01\x02", offset)
        if offset < 0:
            break
        name_length = int.from_bytes(source[offset + 28 : offset + 30], "little")
        extra_length = int.from_bytes(source[offset + 30 : offset + 32], "little")
        comment_length = int.from_bytes(source[offset + 32 : offset + 34], "little")
        name_start = offset + 46
        if bytes(source[name_start : name_start + name_length]) == encoded_filename:
            if set_flag_bits:
                flags = int.from_bytes(source[offset + 8 : offset + 10], "little")
                source[offset + 8 : offset + 10] = (flags | set_flag_bits).to_bytes(
                    2, "little"
                )
            if method is not None:
                source[offset + 10 : offset + 12] = method.to_bytes(2, "little")
            found = True
            break
        offset = name_start + name_length + extra_length + comment_length
    assert found is True
    wheel.write_bytes(source)


def _set_first_wheel_member_compression_method(wheel: Path, method: int) -> None:
    with zipfile.ZipFile(wheel) as archive:
        filename = next(info.filename for info in archive.infolist() if not info.is_dir())
    _rewrite_wheel_member_header(wheel, filename=filename, method=method)


def _rewrite_local_wheel_member_header(
    wheel: Path,
    *,
    member_kind: str,
    mutation: str,
) -> None:
    if member_kind == "directory":
        with zipfile.ZipFile(wheel) as archive:
            has_directory = any(info.is_dir() for info in archive.infolist())
        if not has_directory:
            info = zipfile.ZipInfo("unsafe-local-header/")
            info.external_attr = (stat.S_IFDIR | 0o755) << 16
            with zipfile.ZipFile(wheel, "a") as archive:
                archive.writestr(info, b"")
    source = bytearray(wheel.read_bytes())
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        member = next(
            info
            for info in archive.infolist()
            if info.is_dir() is (member_kind == "directory")
        )
    offset = member.header_offset
    if mutation == "method99":
        source[offset + 8 : offset + 10] = (99).to_bytes(2, "little")
    elif mutation in {"encrypted", "descriptor", "utf8"}:
        masks = {"encrypted": 0x1, "descriptor": 0x8, "utf8": 0x800}
        flags = int.from_bytes(source[offset + 6 : offset + 8], "little")
        source[offset + 6 : offset + 8] = (flags | masks[mutation]).to_bytes(
            2, "little"
        )
    elif mutation == "signature":
        source[offset : offset + 4] = b"BAD!"
    elif mutation == "name":
        source[offset + 30] ^= 0x1
    elif mutation in {"name_length", "extra_length"}:
        field_offset = offset + (26 if mutation == "name_length" else 28)
        value = int.from_bytes(source[field_offset : field_offset + 2], "little")
        source[field_offset : field_offset + 2] = (value + 1).to_bytes(2, "little")
    else:
        field_offsets = {"crc": 14, "compressed_size": 18, "file_size": 22}
        field_offset = offset + field_offsets[mutation]
        value = int.from_bytes(source[field_offset : field_offset + 4], "little")
        source[field_offset : field_offset + 4] = (value ^ 0x1).to_bytes(
            4, "little"
        )
    wheel.write_bytes(source)


def _rewrite_central_wheel_member_header(
    wheel: Path,
    *,
    member_kind: str,
    mutation: str,
) -> None:
    source = bytearray(wheel.read_bytes())
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        member = next(
            info
            for info in archive.infolist()
            if info.is_dir() is (member_kind == "directory")
        )
    encoding = "utf-8" if member.flag_bits & 0x800 else "cp437"
    encoded_name = member.orig_filename.encode(encoding)
    offset = 0
    while True:
        offset = source.find(b"PK\x01\x02", offset)
        assert offset >= 0
        name_length = int.from_bytes(source[offset + 28 : offset + 30], "little")
        name_start = offset + 46
        if bytes(source[name_start : name_start + name_length]) == encoded_name:
            break
        extra_length = int.from_bytes(source[offset + 30 : offset + 32], "little")
        comment_length = int.from_bytes(source[offset + 32 : offset + 34], "little")
        offset = name_start + name_length + extra_length + comment_length
    if mutation == "method99":
        source[offset + 10 : offset + 12] = (99).to_bytes(2, "little")
    elif mutation in {"encrypted", "descriptor", "utf8"}:
        masks = {"encrypted": 0x1, "descriptor": 0x8, "utf8": 0x800}
        flags = int.from_bytes(source[offset + 8 : offset + 10], "little")
        source[offset + 8 : offset + 10] = (flags | masks[mutation]).to_bytes(
            2, "little"
        )
    elif mutation == "signature":
        source[offset : offset + 4] = b"BAD!"
    elif mutation == "name":
        source[offset + 46] ^= 0x1
    elif mutation in {"name_length", "extra_length"}:
        field_offset = offset + (28 if mutation == "name_length" else 30)
        value = int.from_bytes(source[field_offset : field_offset + 2], "little")
        source[field_offset : field_offset + 2] = (value + 1).to_bytes(2, "little")
    else:
        field_offsets = {"crc": 16, "compressed_size": 20, "file_size": 24}
        field_offset = offset + field_offsets[mutation]
        value = int.from_bytes(source[field_offset : field_offset + 4], "little")
        source[field_offset : field_offset + 4] = (value ^ 0x1).to_bytes(
            4, "little"
        )
    wheel.write_bytes(source)


def _wheel_raw_layout(
    source: bytes,
) -> tuple[list[zipfile.ZipInfo], list[int], int, int]:
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        infos = archive.infolist()
        central_start = archive.start_dir
    central_offsets: list[int] = []
    cursor = central_start
    for _info in infos:
        assert source[cursor : cursor + 4] == b"PK\x01\x02"
        central_offsets.append(cursor)
        name_length = int.from_bytes(source[cursor + 28 : cursor + 30], "little")
        extra_length = int.from_bytes(source[cursor + 30 : cursor + 32], "little")
        comment_length = int.from_bytes(source[cursor + 32 : cursor + 34], "little")
        cursor += 46 + name_length + extra_length + comment_length
    assert source[cursor : cursor + 4] == b"PK\x05\x06"
    return infos, central_offsets, central_start, cursor


def _insert_wheel_bytes(wheel: Path, *, offset: int, payload: bytes) -> None:
    source = bytearray(wheel.read_bytes())
    infos, central_offsets, central_start, eocd_offset = _wheel_raw_layout(source)
    delta = len(payload)
    for info, central_offset in zip(infos, central_offsets, strict=True):
        if info.header_offset >= offset:
            source[central_offset + 42 : central_offset + 46] = (
                info.header_offset + delta
            ).to_bytes(4, "little")
    if central_start >= offset:
        source[eocd_offset + 16 : eocd_offset + 20] = (
            central_start + delta
        ).to_bytes(4, "little")
    source[offset:offset] = payload
    wheel.write_bytes(source)


def _rewrite_wheel_with_member_extra(wheel: Path, extra: bytes) -> None:
    rewritten = io.BytesIO()
    with zipfile.ZipFile(wheel) as source:
        rows = [(info, source.read(info)) for info in source.infolist()]
    target = next(info for info, _payload in rows if not info.is_dir())
    target.extra = extra
    with zipfile.ZipFile(rewritten, "w") as destination:
        for info, payload in rows:
            destination.writestr(info, payload)
    wheel.write_bytes(rewritten.getvalue())


def _rewrite_wheel_with_member_comment(wheel: Path, comment: bytes) -> None:
    rewritten = io.BytesIO()
    with zipfile.ZipFile(wheel) as source:
        rows = [(info, source.read(info)) for info in source.infolist()]
    target = next(info for info, _payload in reversed(rows) if not info.is_dir())
    target.comment = comment
    with zipfile.ZipFile(rewritten, "w") as destination:
        for info, payload in rows:
            destination.writestr(info, payload)
    wheel.write_bytes(rewritten.getvalue())


def _mutate_wheel_comment_closure(wheel: Path, mutation: str) -> None:
    if mutation == "member_comment":
        _rewrite_wheel_with_member_comment(wheel, b"hidden member comment")
    elif mutation == "archive_comment":
        with zipfile.ZipFile(wheel, "a") as archive:
            archive.comment = b"hidden archive comment"
    else:
        source = bytearray(wheel.read_bytes())
        _infos, central_offsets, central_start, eocd_offset = _wheel_raw_layout(
            source
        )
        assert int.from_bytes(
            source[central_offsets[-1] + 32 : central_offsets[-1] + 34],
            "little",
        ) == 0
        assert int.from_bytes(source[eocd_offset + 20 : eocd_offset + 22], "little") == 0
        original_eocd = bytes(source[eocd_offset : eocd_offset + 22])
        source.extend(original_eocd)
        source[central_offsets[-1] + 32 : central_offsets[-1] + 34] = (22).to_bytes(
            2,
            "little",
        )
        final_eocd = eocd_offset + 22
        central_size = eocd_offset - central_start
        source[final_eocd + 12 : final_eocd + 16] = (central_size + 22).to_bytes(
            4,
            "little",
        )
        wheel.write_bytes(source)


@pytest.mark.parametrize("surface", ("dependency", "local"))
@pytest.mark.parametrize(
    "mutation",
    ("member_comment", "archive_comment", "embedded_original_eocd"),
)
def test_active_runtime_binding_rejects_hidden_wheel_comment_structure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    surface: str,
    mutation: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    target = (
        document["local_project"]
        if surface == "local"
        else next(row for row in document["artifacts"] if row["install"] is True)
    )
    wheel = Path(target["wheel_path"])
    _mutate_wheel_comment_closure(wheel, mutation)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    target["sha256"] = digest
    if surface == "dependency":
        original_lock_rows = release_gate_module._active_lock_rows

        def selected_lock_rows(source: bytes) -> list[dict[str, object]]:
            rows = original_lock_rows(source)
            locked = next(row for row in rows if row["name"] == target["name"])
            candidate = next(
                row for row in locked["wheels"] if row["name"] == wheel.name
            )
            candidate["sha256"] = digest
            return rows

        monkeypatch.setattr(
            release_gate_module,
            "_active_lock_rows",
            selected_lock_rows,
        )
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


def _append_directory_member(wheel: Path, payload: bytes = b"") -> str:
    name = "hidden-directory-payload/"
    info = zipfile.ZipInfo(name)
    info.external_attr = (stat.S_IFDIR | 0o755) << 16
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr(info, payload)
    return name


def _patch_wheel_member_integrity_fields(
    wheel: Path,
    *,
    filename: str,
    crc: int | None = None,
    compressed_size: int | None = None,
    file_size: int | None = None,
) -> None:
    source = bytearray(wheel.read_bytes())
    infos, central_offsets, _central_start, _eocd_offset = _wheel_raw_layout(source)
    member_index = next(
        index for index, info in enumerate(infos) if info.filename == filename
    )
    local_offset = infos[member_index].header_offset
    central_offset = central_offsets[member_index]
    for value, local_field, central_field in (
        (crc, 14, 16),
        (compressed_size, 18, 20),
        (file_size, 22, 24),
    ):
        if value is not None:
            encoded = value.to_bytes(4, "little")
            source[local_offset + local_field : local_offset + local_field + 4] = encoded
            source[central_offset + central_field : central_offset + central_field + 4] = encoded
    wheel.write_bytes(source)


def _mutate_wheel_closure(wheel: Path, mutation: str) -> None:
    if mutation == "zip64_extra":
        _rewrite_wheel_with_member_extra(wheel, b"\x01\x00\x00\x00")
    elif mutation == "duplicate_extra":
        _rewrite_wheel_with_member_extra(
            wheel,
            b"\xfe\xca\x00\x00\xfe\xca\x00\x00",
        )
    elif mutation == "malformed_extra":
        source = bytearray(wheel.read_bytes())
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            member = next(info for info in archive.infolist() if not info.is_dir())
        local_offset = member.header_offset
        name_length = int.from_bytes(
            source[local_offset + 26 : local_offset + 28], "little"
        )
        extra_length = int.from_bytes(
            source[local_offset + 28 : local_offset + 30], "little"
        )
        malformed = b"\xfe\xca\x04\x00\x00"
        source[local_offset + 28 : local_offset + 30] = (
            extra_length + len(malformed)
        ).to_bytes(2, "little")
        wheel.write_bytes(source)
        _insert_wheel_bytes(
            wheel,
            offset=local_offset + 30 + name_length + extra_length,
            payload=malformed,
        )
    elif mutation == "preamble":
        _insert_wheel_bytes(wheel, offset=0, payload=b"PREAMBLE")
    elif mutation == "inter_member_gap":
        source = wheel.read_bytes()
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            member = archive.infolist()[0]
        name_length = int.from_bytes(
            source[member.header_offset + 26 : member.header_offset + 28], "little"
        )
        extra_length = int.from_bytes(
            source[member.header_offset + 28 : member.header_offset + 30], "little"
        )
        payload_end = (
            member.header_offset
            + 30
            + name_length
            + extra_length
            + member.compress_size
        )
        _insert_wheel_bytes(wheel, offset=payload_end, payload=b"INTER-GAP")
    elif mutation == "precentral_gap":
        source = wheel.read_bytes()
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            central_start = archive.start_dir
        _insert_wheel_bytes(wheel, offset=central_start, payload=b"CENTRAL-GAP")
    elif mutation == "directory_payload":
        _append_directory_member(wheel, b"hidden")
    elif mutation == "directory_crc":
        name = _append_directory_member(wheel)
        _patch_wheel_member_integrity_fields(wheel, filename=name, crc=1)
    elif mutation == "directory_file_size":
        name = _append_directory_member(wheel)
        _patch_wheel_member_integrity_fields(wheel, filename=name, file_size=1)
    else:
        name = _append_directory_member(wheel, b"x")
        _patch_wheel_member_integrity_fields(
            wheel,
            filename=name,
            crc=0,
            file_size=0,
        )


@pytest.mark.parametrize("surface", ("dependency", "local"))
@pytest.mark.parametrize(
    "mutation",
    (
        "zip64_extra",
        "malformed_extra",
        "duplicate_extra",
        "preamble",
        "inter_member_gap",
        "precentral_gap",
        "directory_payload",
        "directory_crc",
        "directory_compressed_size",
        "directory_file_size",
    ),
)
def test_active_runtime_binding_rejects_unclosed_wheel_byte_structure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    surface: str,
    mutation: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    target = (
        document["local_project"]
        if surface == "local"
        else next(row for row in document["artifacts"] if row["install"] is True)
    )
    wheel = Path(target["wheel_path"])
    _mutate_wheel_closure(wheel, mutation)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    target["sha256"] = digest
    if surface == "dependency":
        original_lock_rows = release_gate_module._active_lock_rows

        def selected_lock_rows(source: bytes) -> list[dict[str, object]]:
            rows = original_lock_rows(source)
            locked = next(row for row in rows if row["name"] == target["name"])
            candidate = next(
                row for row in locked["wheels"] if row["name"] == wheel.name
            )
            candidate["sha256"] = digest
            return rows

        monkeypatch.setattr(
            release_gate_module,
            "_active_lock_rows",
            selected_lock_rows,
        )
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


@pytest.mark.parametrize(
    "trailer",
    (
        b"PK\x05\x06" + (b"\x00" * 18),
        b"PK\x06\x06" + (b"\x00" * 52),
        b"PK\x06\x07" + (b"\x00" * 16),
    ),
)
def test_active_wheel_inventory_rejects_duplicate_or_zip64_end_records(
    tmp_path: Path,
    trailer: bytes,
) -> None:
    import hsconfig.release_gate as release_gate_module

    wheel = tmp_path / "end-record.whl"
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("package/module.py", b"VALUE = 1\n")
    wheel.write_bytes(wheel.read_bytes() + trailer)

    with pytest.raises(ReleaseGateError):
        release_gate_module._active_wheel_inventory(wheel.read_bytes())


@pytest.mark.parametrize("surface", ("dependency", "local"))
@pytest.mark.parametrize("member_kind", ("file", "directory"))
@pytest.mark.parametrize("mutation", ("method99", "encrypted"))
def test_active_runtime_binding_rejects_local_only_wheel_security_header_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    surface: str,
    member_kind: str,
    mutation: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    target = (
        document["local_project"]
        if surface == "local"
        else next(row for row in document["artifacts"] if row["install"] is True)
    )
    wheel = Path(target["wheel_path"])
    _rewrite_local_wheel_member_header(
        wheel,
        member_kind=member_kind,
        mutation=mutation,
    )
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    target["sha256"] = digest
    if surface == "dependency":
        original_lock_rows = release_gate_module._active_lock_rows

        def selected_lock_rows(source: bytes) -> list[dict[str, object]]:
            rows = original_lock_rows(source)
            locked = next(row for row in rows if row["name"] == target["name"])
            candidate = next(
                row for row in locked["wheels"] if row["name"] == wheel.name
            )
            candidate["sha256"] = digest
            return rows

        monkeypatch.setattr(
            release_gate_module,
            "_active_lock_rows",
            selected_lock_rows,
        )
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


@pytest.mark.parametrize(
    ("member_kind", "mutation"),
    (
        ("directory", "descriptor"),
        ("directory", "utf8"),
        ("directory", "crc"),
        ("directory", "compressed_size"),
        ("directory", "file_size"),
        ("directory", "signature"),
        ("directory", "name"),
        ("directory", "name_length"),
        ("directory", "extra_length"),
        ("file", "descriptor"),
        ("file", "utf8"),
        ("file", "crc"),
        ("file", "compressed_size"),
        ("file", "file_size"),
    ),
)
def test_active_wheel_inventory_rejects_local_header_structural_ambiguity(
    tmp_path: Path,
    member_kind: str,
    mutation: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    wheel = tmp_path / "structural.whl"
    directory = zipfile.ZipInfo("package/")
    directory.external_attr = (stat.S_IFDIR | 0o755) << 16
    with zipfile.ZipFile(
        wheel,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(directory, b"")
        archive.writestr("package/module.py", b"VALUE = 1\n")
    _rewrite_local_wheel_member_header(
        wheel,
        member_kind=member_kind,
        mutation=mutation,
    )

    with pytest.raises(ReleaseGateError):
        release_gate_module._active_wheel_inventory(wheel.read_bytes())


@pytest.mark.parametrize("member_kind", ("directory", "file"))
@pytest.mark.parametrize(
    "mutation",
    (
        "method99",
        "encrypted",
        "descriptor",
        "utf8",
        "crc",
        "compressed_size",
        "file_size",
        "signature",
        "name",
        "name_length",
        "extra_length",
    ),
)
def test_active_wheel_inventory_rejects_central_only_header_ambiguity(
    tmp_path: Path,
    member_kind: str,
    mutation: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    wheel = tmp_path / "central-structural.whl"
    directory = zipfile.ZipInfo("package/")
    directory.external_attr = (stat.S_IFDIR | 0o755) << 16
    with zipfile.ZipFile(
        wheel,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(directory, b"")
        archive.writestr("package/module.py", b"VALUE = 1\n")
    _rewrite_central_wheel_member_header(
        wheel,
        member_kind=member_kind,
        mutation=mutation,
    )

    with pytest.raises(ReleaseGateError):
        release_gate_module._active_wheel_inventory(wheel.read_bytes())


def _append_unsafe_wheel_directory(wheel: Path, unsafe_kind: str) -> None:
    filename = "unsafe-directory/"
    info = zipfile.ZipInfo(filename)
    info.external_attr = (stat.S_IFDIR | 0o755) << 16
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr(info, b"")
    if unsafe_kind == "method99":
        _rewrite_wheel_member_header(wheel, filename=filename, method=99)
    else:
        _rewrite_wheel_member_header(wheel, filename=filename, set_flag_bits=0x1)


@pytest.mark.parametrize("surface", ("dependency", "local"))
@pytest.mark.parametrize("unsafe_kind", ("method99", "encrypted"))
def test_active_runtime_binding_rejects_unsafe_wheel_directory_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    surface: str,
    unsafe_kind: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    target = (
        document["local_project"]
        if surface == "local"
        else next(row for row in document["artifacts"] if row["install"] is True)
    )
    wheel = Path(target["wheel_path"])
    _append_unsafe_wheel_directory(wheel, unsafe_kind)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    target["sha256"] = digest
    if surface == "dependency":
        original_lock_rows = release_gate_module._active_lock_rows

        def selected_lock_rows(source: bytes) -> list[dict[str, object]]:
            rows = original_lock_rows(source)
            locked = next(row for row in rows if row["name"] == target["name"])
            candidate = next(
                row for row in locked["wheels"] if row["name"] == wheel.name
            )
            candidate["sha256"] = digest
            return rows

        monkeypatch.setattr(
            release_gate_module,
            "_active_lock_rows",
            selected_lock_rows,
        )
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


@pytest.mark.parametrize("surface", ("dependency", "local"))
def test_active_runtime_binding_translates_unsupported_wheel_compression_to_gate_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    surface: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    target = (
        document["local_project"]
        if surface == "local"
        else next(row for row in document["artifacts"] if row["install"] is True)
    )
    wheel = Path(target["wheel_path"])
    _set_first_wheel_member_compression_method(wheel, 99)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    target["sha256"] = digest
    if surface == "dependency":
        original_lock_rows = release_gate_module._active_lock_rows

        def selected_lock_rows(source: bytes) -> list[dict[str, object]]:
            rows = original_lock_rows(source)
            locked = next(row for row in rows if row["name"] == target["name"])
            candidate = next(
                row for row in locked["wheels"] if row["name"] == wheel.name
            )
            candidate["sha256"] = digest
            return rows

        monkeypatch.setattr(
            release_gate_module,
            "_active_lock_rows",
            selected_lock_rows,
        )
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


def test_unsupported_local_wheel_compression_cli_emits_one_failure_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    wheel = binding["local_wheel"]
    _set_first_wheel_member_compression_method(wheel, 99)
    document["local_project"]["sha256"] = hashlib.sha256(
        wheel.read_bytes()
    ).hexdigest()
    document["environment_root"] = str(binding["bootstrap_root"] / "environment")
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)
    python = binding["bootstrap_root"] / "environment" / "Scripts" / "python.exe"
    sentinel = real_active_runtime_template["sentinel"].read_text(encoding="ascii")
    environment = BOOTSTRAP._base_environment()
    environment.update(
        {
            BOOTSTRAP._SENTINEL: sentinel,
            BOOTSTRAP._MANIFEST: str(binding["manifest"]),
            BOOTSTRAP._MANIFEST_DIGEST: os.environ[
                "HSCONFIG_RUNTIME_MANIFEST_SHA256"
            ],
            "VIRTUAL_ENV": str(binding["bootstrap_root"] / "environment"),
            "PYTHONPATH": os.pathsep.join(
                (str(binding["source_root"]), str(binding["build_backend_root"]))
            ),
        }
    )
    completed = subprocess.run(
        (
            str(python),
            str(binding["controller"]),
            "--repo",
            str(binding["repository"]),
            "--outputs",
            str(binding["repository"] / "outputs"),
            "--tree-mode",
            "working-pre-cutover",
            "--json",
            "--internal-check",
            "repository_hygiene",
        ),
        cwd=binding["repository"],
        env=environment,
        input=sentinel + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=600,
    )

    assert completed.returncode == 2
    assert completed.stdout.count("\n") == 1
    document = json.loads(completed.stdout)
    assert document["passed"] is False
    assert document["errors"] == ["release gate bootstrap failed"]
    assert "Traceback" not in completed.stderr


@pytest.mark.parametrize(
    "filename",
    (
        "renamed-local-payload.bin",
        "other-{version}-py3-none-any.whl",
        "hsconfig-9.9.9-py3-none-any.whl",
        "hsconfig-{version}-invalid.whl",
        "hsconfig-{version}-py3-none-any.bin",
        "HSConfig-{version}-py3-none-any.whl",
    ),
)
def test_active_runtime_binding_rejects_noncanonical_local_wheel_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    filename: str,
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    version = document["local_project"]["version"]
    renamed = binding["local_wheel"].with_name(filename.format(version=version))
    binding["local_wheel"].replace(renamed)
    document["local_project"]["wheel_path"] = str(renamed)
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


def test_active_runtime_binding_rejects_local_wheel_tag_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    wheel = binding["local_wheel"]
    rewritten = io.BytesIO()
    with zipfile.ZipFile(wheel) as source, zipfile.ZipFile(
        rewritten,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as destination:
        for info in source.infolist():
            payload = source.read(info)
            if info.filename.endswith(".dist-info/WHEEL"):
                text = payload.decode("utf-8")
                payload = re.sub(
                    r"(?m)^Tag: .+$",
                    "Tag: py2-none-any",
                    text,
                ).encode("utf-8")
            destination.writestr(info, payload)
    wheel.write_bytes(rewritten.getvalue())
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    document["local_project"]["sha256"] = hashlib.sha256(
        wheel.read_bytes()
    ).hexdigest()
    document["local_project"]["files"] = _unbounded_test_wheel_rows(wheel)
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


def _rewrite_wheel_identity(wheel: Path, mutation: str) -> None:
    rewritten = io.BytesIO()
    with zipfile.ZipFile(wheel) as source, zipfile.ZipFile(
        rewritten,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as destination:
        for info in source.infolist():
            name = info.filename
            payload = source.read(info)
            if mutation == "dist_info_root" and ".dist-info/" in name:
                _root, separator, rest = name.partition("/")
                name = f"evil-999.dist-info{separator}{rest}"
            elif info.filename.endswith(".dist-info/METADATA"):
                text = payload.decode("utf-8")
                if mutation == "metadata_name":
                    text = re.sub(r"(?m)^Name: .+$", "Name: evil", text)
                elif mutation == "metadata_version":
                    text = re.sub(r"(?m)^Version: .+$", "Version: 999", text)
                elif mutation == "metadata_core_version_missing":
                    text = re.sub(r"(?m)^Metadata-Version: .+\r?\n", "", text)
                elif mutation == "metadata_core_version_unsupported":
                    text = re.sub(
                        r"(?m)^Metadata-Version: .+$",
                        "Metadata-Version: 9.9",
                        text,
                    )
                elif mutation == "metadata_core_version_duplicate":
                    text = re.sub(
                        r"(?m)^(Metadata-Version: .+\r?\n)",
                        r"\1\1",
                        text,
                        count=1,
                    )
                elif mutation == "metadata_parser_defect":
                    separator = "\r\n\r\n" if "\r\n\r\n" in text else "\n\n"
                    head, found, body = text.partition(separator)
                    assert found
                    text = head + "\nMalformed identity line" + found + body
                payload = text.encode("utf-8")
            elif info.filename.endswith(".dist-info/WHEEL"):
                text = payload.decode("utf-8")
                if mutation == "wheel_tag":
                    text = re.sub(r"(?m)^Tag: .+$", "Tag: py2-none-any", text)
                elif mutation == "root_false":
                    text = re.sub(
                        r"(?m)^Root-Is-Purelib: .+$",
                        "Root-Is-Purelib: false",
                        text,
                    )
                elif mutation == "root_missing":
                    text = re.sub(r"(?m)^Root-Is-Purelib: .+\r?\n", "", text)
                elif mutation == "root_duplicate":
                    text += "Root-Is-Purelib: true\n"
                elif mutation == "tag_duplicate":
                    tag = next(
                        line for line in text.splitlines() if line.startswith("Tag: ")
                    )
                    text += tag + "\n"
                elif mutation == "unknown_identity":
                    text += "Identity-Name: evil\n"
                payload = text.encode("utf-8")
            destination.writestr(name, payload)
    wheel.write_bytes(rewritten.getvalue())


@pytest.mark.parametrize(
    "mutation",
    (
        "root_missing",
        "root_false",
        "root_duplicate",
        "tag_duplicate",
        "unknown_identity",
    ),
)
def test_active_runtime_binding_rejects_unclosed_local_wheel_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    mutation: str,
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    wheel = binding["local_wheel"]
    _rewrite_wheel_identity(wheel, mutation)
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    document["local_project"]["sha256"] = hashlib.sha256(
        wheel.read_bytes()
    ).hexdigest()
    document["local_project"]["files"] = _unbounded_test_wheel_rows(wheel)
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


@pytest.mark.parametrize(
    "mutation",
    ("metadata_name", "metadata_version", "wheel_tag", "root_false", "dist_info_root"),
)
def test_active_runtime_binding_rejects_dependency_internal_identity_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    mutation: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    target = next(row for row in document["artifacts"] if row["install"] is True)
    wheel = Path(target["wheel_path"])
    _rewrite_wheel_identity(wheel, mutation)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    target["sha256"] = digest
    target["files"] = _unbounded_test_wheel_rows(wheel)
    original_lock_rows = release_gate_module._active_lock_rows

    def selected_lock_rows(source: bytes) -> list[dict[str, object]]:
        rows = original_lock_rows(source)
        locked = next(row for row in rows if row["name"] == target["name"])
        candidate = next(
            row for row in locked["wheels"] if row["name"] == wheel.name
        )
        candidate["sha256"] = digest
        return rows

    monkeypatch.setattr(
        release_gate_module,
        "_active_lock_rows",
        selected_lock_rows,
    )
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


@pytest.mark.parametrize("surface", ("dependency", "local"))
@pytest.mark.parametrize(
    "mutation",
    (
        "metadata_core_version_missing",
        "metadata_core_version_unsupported",
        "metadata_core_version_duplicate",
        "metadata_parser_defect",
    ),
)
def test_active_runtime_binding_rejects_invalid_core_metadata_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    surface: str,
    mutation: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    target = (
        document["local_project"]
        if surface == "local"
        else next(row for row in document["artifacts"] if row["install"] is True)
    )
    wheel = Path(target["wheel_path"])
    _rewrite_wheel_identity(wheel, mutation)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    target["sha256"] = digest
    target["files"] = _unbounded_test_wheel_rows(wheel)
    if surface == "dependency":
        original_lock_rows = release_gate_module._active_lock_rows

        def selected_lock_rows(source: bytes) -> list[dict[str, object]]:
            rows = original_lock_rows(source)
            locked = next(row for row in rows if row["name"] == target["name"])
            candidate = next(
                row for row in locked["wheels"] if row["name"] == wheel.name
            )
            candidate["sha256"] = digest
            return rows

        monkeypatch.setattr(
            release_gate_module,
            "_active_lock_rows",
            selected_lock_rows,
        )
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


@pytest.mark.parametrize("substitution", ("order", "count"))
def test_active_runtime_binding_rejects_artifact_order_or_count_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    substitution: str,
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    if substitution == "order":
        document["artifacts"].reverse()
    else:
        index = next(
            index
            for index, row in enumerate(document["artifacts"])
            if row["install"] is True
        )
        document["artifacts"].pop(index)
    _rewrite_active_runtime_manifest(binding, monkeypatch, document)

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_active_runtime_binding_rejects_nested_build_backend_junction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    external = tmp_path / "external-overlay"
    external.mkdir()
    environment = os.environ.copy()
    environment["HSCONFIG_TEST_LINK_PATH"] = str(
        binding["build_backend_root"] / "redirect"
    )
    environment["HSCONFIG_TEST_LINK_TARGET"] = str(external)
    subprocess.run(
        (
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "New-Item -ItemType Junction "
            "-Path $env:HSCONFIG_TEST_LINK_PATH "
            "-Target $env:HSCONFIG_TEST_LINK_TARGET | Out-Null",
        ),
        check=True,
        env=environment,
    )

    with pytest.raises(ReleaseGateError, match="runtime binding"):
        _active_runtime_paths(binding["repository"])


def test_distribution_build_environment_separates_staged_source_from_active_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    ambient_debug = tmp_path / "ambient-coverage-debug.txt"
    monkeypatch.setenv("COVERAGE_DEBUG_FILE", str(ambient_debug))
    monkeypatch.setenv("HYPOTHESIS_PROFILE", "ambient")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--trace")
    monkeypatch.setenv("PYTHONSTARTUP", str(tmp_path / "ambient-startup.py"))
    controlled_repositories: list[Path] = []
    staged_sources: list[Path] = []
    observed_environments: list[dict[str, str]] = []
    original_controlled_environment = release_gate_module._controlled_environment

    def record_controlled_environment(repository: Path) -> dict[str, str]:
        controlled_repositories.append(repository)
        return original_controlled_environment(repository)

    def stage_source(repository: Path, destination: Path) -> None:
        assert repository == binding["repository"]
        destination.mkdir()
        staged_sources.append(destination)

    def observe_build(
        command: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        assert cwd == staged_sources[0]
        assert Path(command[-1]) == staged_sources[0]
        assert "--no-isolation" in command
        assert timeout == 1_200
        observed_environments.append(dict(env))
        return subprocess.CompletedProcess(command, 1, "", "expected diagnostic stop")

    monkeypatch.setattr(
        release_gate_module,
        "_controlled_environment",
        record_controlled_environment,
    )
    monkeypatch.setattr(release_gate_module, "_stage_tracked_source", stage_source)
    monkeypatch.setattr(release_gate_module, "_execute_bounded", observe_build)

    violations, artifact_count = _scan_distributions(binding["repository"])

    assert controlled_repositories == [binding["repository"]]
    assert len(staged_sources) == 1
    assert artifact_count == 0
    assert violations == ["distribution_build_failed:returncode=1"]
    assert len(observed_environments) == 1
    environment = observed_environments[0]
    assert environment["PYTHONPATH"] == str(binding["build_backend_root"])
    assert all(
        name not in environment
        for name in (
            "HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL",
            "HSCONFIG_RUNTIME_MANIFEST",
            "HSCONFIG_RUNTIME_MANIFEST_SHA256",
            "COVERAGE_DEBUG_FILE",
            "HYPOTHESIS_PROFILE",
            "PYTEST_ADDOPTS",
            "PYTHONSTARTUP",
        )
    )
    assert not ambient_debug.exists()


def test_controlled_environment_preserves_only_manifest_bound_python_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
) -> None:
    binding = _write_active_runtime_binding(
        tmp_path, monkeypatch, real_active_runtime_template
    )
    source_root = binding["source_root"]
    build_backend_root = binding["build_backend_root"]
    locked_root = tmp_path / "locked-site-packages"
    locked_metadata = locked_root / "locked_pkg-1.0.dist-info" / "METADATA"
    locked_metadata.parent.mkdir(parents=True)
    locked_metadata.write_text(
        "Metadata-Version: 2.1\nName: locked-pkg\nVersion: 1.0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "ambient-pythonpath"))
    monkeypatch.setenv("PYTEST_PLUGINS", "ambient.plugin")

    environment = _controlled_environment(binding["repository"])
    completed = subprocess.run(
        (
            sys.executable,
            "-S",
            "-c",
            "import importlib.metadata,json,sys;"
            "sys.path.insert(0,sys.argv[1]);"
            "names=sorted(d.metadata['Name'] for d in importlib.metadata.distributions());"
            "print(json.dumps(names,separators=(',',':')))",
            str(locked_root),
        ),
        cwd=binding["repository"],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert environment["PYTHONPATH"].split(os.pathsep) == [
        str(source_root),
        str(build_backend_root),
    ]
    assert environment["PYTEST_PLUGINS"] == "pytest_cov.plugin,_hypothesis_pytestplugin"
    assert json.loads(completed.stdout) == ["coverage", "locked-pkg", "setuptools"]


def test_controlled_environment_runs_real_repository_tmp_path_test_without_residue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots: list[Path] = []
    original = tempfile.TemporaryDirectory

    class RecordingTemporaryDirectory:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.delegate = original(*args, **kwargs)
            roots.append(Path(self.delegate.name))

        def __enter__(self) -> str:
            return self.delegate.__enter__()

        def __exit__(self, *args: Any) -> bool | None:
            return self.delegate.__exit__(*args)

    monkeypatch.setattr(
        "hsconfig.release_gate.TemporaryDirectory", RecordingTemporaryDirectory
    )
    completed = _execute_bounded(
        (
            sys.executable,
            "-m",
            "pytest",
            "tests/test_io_and_models.py::test_json_round_trip_and_hash",
            "-q",
            "-p",
            "no:cacheprovider",
        ),
        cwd=ROOT,
        env=_controlled_environment(ROOT),
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    assert "1 passed" in completed.stdout
    assert len(roots) == 1
    assert ROOT.resolve() not in roots[0].resolve().parents
    assert not roots[0].exists()


def test_bounded_execution_cleans_unique_external_tool_state_on_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots: list[Path] = []
    original = tempfile.TemporaryDirectory

    class RecordingTemporaryDirectory:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.delegate = original(*args, **kwargs)
            roots.append(Path(self.delegate.name))

        def __enter__(self) -> str:
            return self.delegate.__enter__()

        def __exit__(self, *args: Any) -> bool | None:
            return self.delegate.__exit__(*args)

    monkeypatch.setattr(
        "hsconfig.release_gate.TemporaryDirectory", RecordingTemporaryDirectory
    )
    child = (
        "import os,pathlib,sys; "
        "keys=('HYPOTHESIS_STORAGE_DIRECTORY','PIP_CACHE_DIR','PYTHONPYCACHEPREFIX',"
        "'PYTEST_DEBUG_TEMPROOT','TOX_ENV_DIR','XDG_CACHE_HOME'); "
        "[(pathlib.Path(os.environ[k]).mkdir(parents=True,exist_ok=True),"
        "(pathlib.Path(os.environ[k])/'owned').write_text('owned')) for k in keys]; "
        "raise SystemExit(int(sys.argv[1]))"
    )
    for returncode in (0, 7):
        completed = _execute_bounded(
            (sys.executable, "-c", child, str(returncode)),
            cwd=tmp_path,
            env=_controlled_environment(ROOT),
            timeout=30,
        )
        assert completed.returncode == returncode

    assert len(roots) == 2
    assert len(set(roots)) == 2
    assert all(ROOT.resolve() not in path.resolve().parents for path in roots)
    assert all(not path.exists() for path in roots)


@pytest.mark.parametrize("mode", ("failure", "timeout"))
def test_coverage_command_cannot_leave_report_residue(
    tmp_path: Path, mode: str
) -> None:
    script = tmp_path / "run_coverage_gate.py"
    if mode == "failure":
        body = "from pathlib import Path; Path('coverage.json').write_text('x'); raise SystemExit(7)\n"
    else:
        body = (
            "from pathlib import Path; import time; "
            "Path('coverage.json').write_text('x'); time.sleep(30)\n"
        )
    script.write_text(body, encoding="utf-8")

    if mode == "failure":
        completed = _execute_bounded(
            (sys.executable, str(script)),
            cwd=tmp_path,
            env=_controlled_environment(ROOT),
            timeout=30,
        )
        assert completed.returncode == 7
    else:
        with pytest.raises(subprocess.TimeoutExpired):
            _execute_bounded(
                (sys.executable, str(script)),
                cwd=tmp_path,
                env=_controlled_environment(ROOT),
                timeout=1,
            )
    assert not (tmp_path / "coverage.json").exists()


def test_git_controller_ignores_host_git_directory_and_config_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    expected_oid = _git(repository, "rev-parse", "HEAD")
    hostile = tmp_path / "hostile.git"
    hostile.mkdir()
    monkeypatch.setenv("GIT_DIR", str(hostile))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(tmp_path))

    root, verified_outputs, oid = _validate_repository(
        repository, outputs, "working-pre-cutover"
    )

    assert root == repository.resolve()
    assert verified_outputs == outputs.resolve()
    assert oid == expected_oid


def test_bounded_subprocess_capture_digests_oversized_output(tmp_path: Path) -> None:
    completed = _execute_bounded(
        (sys.executable, "-c", "print('x' * 200000)"),
        cwd=tmp_path,
        env=_controlled_environment(ROOT),
        timeout=30,
    )

    assert completed.returncode == 0
    assert len(completed.stdout) < 70_000
    assert "truncated sha256=" in completed.stdout


@pytest.mark.parametrize("returncode", (0, 7))
def test_run_one_preserves_single_json_stdout_with_oversized_stderr(
    tmp_path: Path, returncode: int
) -> None:
    child = (
        "import json,sys; "
        "sys.stderr.write('diagnostic-' + 'x' * 70000); "
        f"print(json.dumps({{'passed': {returncode == 0!r}, 'probe': 'bounded'}})); "
        f"raise SystemExit({returncode})"
    )

    result = _run_one(
        _CommandSpec("bounded_json_probe", (sys.executable, "-c", child), 30),
        repository=tmp_path,
    )

    assert result.passed is (returncode == 0)
    assert result.details["returncode"] == returncode
    assert result.details["result"] == {
        "passed": returncode == 0,
        "probe": "bounded",
    }
    assert len(result.details["stderr_sha256"]) == 64


def test_run_one_rejects_truncated_stdout_before_it_can_masquerade_as_json(
    tmp_path: Path,
) -> None:
    child = (
        "import json; "
        "print('x' * 70000, end=''); "
        "print(json.dumps({'passed': True}))"
    )

    result = _run_one(
        _CommandSpec("truncated_stdout_probe", (sys.executable, "-c", child), 30),
        repository=tmp_path,
    )

    assert result.passed is False
    assert result.details == {
        "returncode": 0,
        "error": "subprocess stdout exceeded bounded capture",
    }


def test_dependency_audit_command_uses_the_exact_project_lock() -> None:
    command = next(
        spec.command
        for spec in _command_specs(ROOT, ROOT / "outputs", "working-pre-cutover")
        if spec.name == "dependency_audit"
    )

    assert command == (
        sys.executable,
        "-m",
        "pip_audit",
        "-r",
        str(ROOT / "constraints-ci.txt"),
        "--strict",
        "--progress-spinner",
        "off",
    )


def test_contract_spine_command_binds_the_exact_repository_root() -> None:
    command = next(
        spec.command
        for spec in _command_specs(ROOT, ROOT / "outputs", "working-pre-cutover")
        if spec.name == "contract_spine"
    )

    assert command == (
        sys.executable,
        "-m",
        "hsconfig.cli",
        "contract-spine-sentinel",
        "--repo-root",
        str(ROOT),
        "--json",
    )


def test_coverage_command_binds_the_exact_committed_source_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "mutable-repository"
    committed_source = tmp_path / "bootstrap" / "committed-source"
    build_backend = tmp_path / "bootstrap" / "build-backend"
    monkeypatch.setattr(
        "hsconfig.release_gate._active_runtime_paths",
        lambda candidate: (committed_source, build_backend),
    )

    command = next(
        spec.command
        for spec in _command_specs(
            repository,
            tmp_path / "outputs",
            "working-pre-cutover",
        )
        if spec.name == "full_tests_and_coverage"
    )

    assert command == (
        sys.executable,
        str(committed_source / "scripts" / "run_coverage_gate.py"),
    )
    assert Path(command[1]) != repository / "scripts" / "run_coverage_gate.py"


def test_selected_audit_projection_is_exactly_the_43_package_minor_lock() -> None:
    _validate_selected_audit_projection(ROOT)


def test_selected_audit_projection_rejects_a_combined_86_package_graph(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    shutil.copy2(ROOT / "pylock.3.11.toml", repository / "pylock.3.11.toml")
    constraints = (ROOT / "constraints-ci.txt").read_text(encoding="utf-8")
    (repository / "constraints-ci.txt").write_text(
        constraints + constraints,
        encoding="utf-8",
    )

    with pytest.raises(ReleaseGateError, match="duplicate|differs"):
        _validate_selected_audit_projection(repository)


def test_bootstrap_pip_uses_the_exact_locked_wheel_before_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    python = tmp_path / "environment" / "Scripts" / "python.exe"
    calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []
    downloads: list[tuple[str, Path, str]] = []
    wheel = {
        "name": "pip-99-py3-none-any.whl",
        "url": "https://example.invalid/pip-99.whl",
        "sha256": "a" * 64,
    }
    rows = {("pip", "99"): {"name": "pip", "version": "99", "wheels": [wheel]}}

    def download(url: str, destination: Path, digest: str) -> None:
        downloads.append((url, destination, digest))
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("pip/__init__.py", "")

    monkeypatch.setattr(
        BOOTSTRAP,
        "_download",
        download,
    )
    monkeypatch.setattr(
        BOOTSTRAP,
        "_run",
        lambda command, *, cwd, env: calls.append((command, cwd, dict(env))),
    )

    BOOTSTRAP._bootstrap_pip(python, rows, tmp_path, {"SAFE": "1"})

    destination = tmp_path / wheel["name"]
    assert downloads == [(wheel["url"], destination, wheel["sha256"])]
    assert calls == [
        (
            (
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                str(destination),
            ),
            tmp_path,
            {"SAFE": "1", "PYTHONPATH": str(destination)},
        )
    ]


def test_bootstrap_cleanup_retries_interruption_without_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bootstrap"
    root.mkdir()
    (root / "payload.txt").write_text("owned", encoding="utf-8")
    metadata = root.lstat()
    identity = (metadata.st_dev, metadata.st_ino)
    real_delete = BOOTSTRAP._delete_owned_bootstrap_tree
    attempts = 0
    interruption = KeyboardInterrupt("cleanup interrupted")

    def interrupt_once(path: Path, expected: tuple[int, int]) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise interruption
        real_delete(path, expected)

    monkeypatch.setattr(BOOTSTRAP, "_delete_owned_bootstrap_tree", interrupt_once)

    with pytest.raises(KeyboardInterrupt) as captured:
        BOOTSTRAP._cleanup_bootstrap_root(root, identity)

    assert captured.value is interruption
    assert attempts == 2
    assert not root.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_bootstrap_cleanup_deletes_junction_not_external_target(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")
    root = tmp_path / "bootstrap"
    root.mkdir()
    junction = root / "junction"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("junction creation unavailable")
    metadata = root.lstat()

    BOOTSTRAP._cleanup_bootstrap_root(root, (metadata.st_dev, metadata.st_ino))

    assert marker.read_text(encoding="utf-8") == "preserve"
    assert not root.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_bootstrap_bound_read_rejects_junction_parent(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "manifest.json").write_text("{}", encoding="utf-8")
    junction = tmp_path / "junction"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("junction creation unavailable")

    with pytest.raises(BOOTSTRAP._BootstrapError, match="unsafe"):
        BOOTSTRAP._read_bound(junction / "manifest.json")


def test_second_pip_report_may_omit_the_separately_bootstrapped_pip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pip_wheel = tmp_path / "pip.whl"
    with zipfile.ZipFile(pip_wheel, "w") as archive:
        archive.writestr("pip/__init__.py", "")
    pip_artifact = {
        "name": "pip",
        "version": "99",
        "url": "https://example.invalid/pip.whl",
        "sha256": "a" * 64,
        "wheel_path": str(pip_wheel),
        "files": BOOTSTRAP._wheel_inventory(pip_wheel),
    }
    rows = {
        ("pip", "99"): {
            "name": "pip",
            "version": "99",
            "wheels": [{"name": "pip.whl", "url": pip_artifact["url"], "sha256": "a" * 64}],
        },
        ("example", "1"): {
            "name": "example",
            "version": "1",
            "wheels": [
                {
                    "name": "example.whl",
                    "url": "https://example.invalid/example.whl",
                    "sha256": "b" * 64,
                }
            ],
        },
    }
    report = {
        "install": [
            {
                "metadata": {"name": "example", "version": "1"},
                "download_info": {
                    "url": "https://example.invalid/example.whl",
                    "archive_info": {"hashes": {"sha256": "b" * 64}},
                },
            }
        ]
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    def download(_url: str, destination: Path, _digest: str) -> None:
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("example/__init__.py", "")

    monkeypatch.setattr(BOOTSTRAP, "_download", download)

    artifacts = BOOTSTRAP._report_artifacts(
        report_path,
        rows,
        tmp_path,
        seeded=(pip_artifact,),
    )

    assert [(row["name"], row["version"]) for row in artifacts] == [
        ("example", "1"),
        ("pip", "99"),
    ]


def test_child_binding_rejects_caller_authored_minimal_manifest_before_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "c" * 64
    manifest = tmp_path / "manifest.json"
    source = json.dumps(
        {
            "environment_root": str(Path(sys.executable).resolve().parent.parent),
            "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
            "sentinel_sha256": hashlib.sha256(sentinel.encode("ascii")).hexdigest(),
        }
    ).encode("utf-8")
    manifest.write_bytes(source)
    monkeypatch.setenv("HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL", sentinel)
    monkeypatch.setenv("HSCONFIG_RUNTIME_MANIFEST", str(manifest))
    monkeypatch.setenv("HSCONFIG_RUNTIME_MANIFEST_SHA256", hashlib.sha256(source).hexdigest())

    class Input:
        buffer = io.BytesIO(sentinel.encode("ascii") + b"\n")

    monkeypatch.setattr(BOOTSTRAP.sys, "stdin", Input())
    args = BOOTSTRAP._parser().parse_args(
        ["--repo", str(ROOT), "--outputs", str(ROOT / "outputs"), "--json"]
    )

    assert BOOTSTRAP._child_binding(args) is False


def test_locked_coverage_check_accepts_only_the_canonical_route() -> None:
    """Catches expansion of the bootstrap parent into an arbitrary command runner."""
    canonical = [
        "--repo",
        str(ROOT),
        "--outputs",
        str(ROOT / "outputs"),
        "--locked-check",
        "full-tests-and-coverage",
        "--json",
    ]

    assert BOOTSTRAP._parser().parse_args(canonical).locked_check == "full-tests-and-coverage"
    with pytest.raises(BOOTSTRAP._CliError, match="argument_error"):
        BOOTSTRAP._parser().parse_args(
            [*canonical[:-2], "arbitrary-command", "--json"]
        )


def test_locked_coverage_check_is_not_dispatched_before_child_binding(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catches execution of coverage from an unbound caller-controlled process."""
    monkeypatch.setattr(BOOTSTRAP, "_child_binding", lambda _args: False)
    monkeypatch.setattr(
        BOOTSTRAP,
        "_bootstrap_and_reexec",
        lambda *_args: (1, {"passed": False, "route": "bootstrap"}),
    )
    monkeypatch.setattr(
        BOOTSTRAP,
        "_child_main",
        lambda _args: (_ for _ in ()).throw(AssertionError("unbound child")),
    )

    assert BOOTSTRAP.main(
        [
            "--repo",
            str(ROOT),
            "--outputs",
            str(ROOT / "outputs"),
            "--locked-check",
            "full-tests-and-coverage",
            "--json",
        ]
    ) == 1
    assert json.loads(capsys.readouterr().out) == {
        "passed": False,
        "route": "bootstrap",
    }


def test_bound_child_forwards_coverage_exit_two_without_rewriting_its_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches loss of the coverage gate's distinct infrastructure failure result."""
    document = {"passed": False, "failure": "runtime-lock"}

    class Process:
        def __init__(self) -> None:
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO((json.dumps(document) + "\n").encode())

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 2

        def kill(self) -> None:
            return None

    class Lease:
        def __init__(self, _process: Process, _baseline: set[int]) -> None:
            pass

        def terminate_remaining(self) -> None:
            return None

    monkeypatch.setattr(BOOTSTRAP.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(BOOTSTRAP, "_BootstrapProcessTreeLease", Lease)

    with pytest.raises(BOOTSTRAP._BootstrapError, match="exit status"):
        BOOTSTRAP._run_bound_child(
            Path(sys.executable),
            tmp_path,
            {},
            [],
            "a" * 64,
            controller_path=Path(BOOTSTRAP.__file__),
        )
    assert BOOTSTRAP._run_bound_child(
        Path(sys.executable),
        tmp_path,
        {},
        [],
        "a" * 64,
        allow_locked_coverage_exit_two=True,
        controller_path=Path(BOOTSTRAP.__file__),
    ) == (2, document)


def test_bound_child_delegates_the_locked_route_to_the_coverage_gate_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catches a bound locked route that substitutes a second coverage authority."""
    from scripts import run_coverage_gate

    document = {"passed": False, "failure": "coverage-runtime-lock"}
    calls: list[str] = []

    def coverage_main() -> int:
        calls.append("coverage")
        print(json.dumps(document, separators=(",", ":")))
        return 2

    monkeypatch.setattr(run_coverage_gate, "main", coverage_main)
    args = BOOTSTRAP._parser().parse_args(
        [
            "--repo",
            str(ROOT),
            "--outputs",
            str(ROOT / "outputs"),
            "--locked-check",
            "full-tests-and-coverage",
            "--json",
        ]
    )

    assert BOOTSTRAP._child_main(args) == 2
    assert calls == ["coverage"]
    assert capsys.readouterr().out == '{"passed":false,"failure":"coverage-runtime-lock"}\n'


def test_unsupported_python_minor_fails_before_lock_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = type("Version", (), {"major": 3, "minor": 13})()
    monkeypatch.setattr(
        BOOTSTRAP,
        "sys",
        type("Sys", (), {"version_info": version})(),
    )

    with pytest.raises(BOOTSTRAP._BootstrapError, match="3.11 or 3.12"):
        BOOTSTRAP._selected_lock(ROOT)


def test_unsupported_python_minor_emits_one_failure_json_exit_two(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        BOOTSTRAP,
        "_bootstrap_and_reexec",
        lambda *_args: (_ for _ in ()).throw(
            BOOTSTRAP._BootstrapError(
                "canonical release gate supports Python 3.11 or 3.12"
            )
        ),
    )

    returncode = BOOTSTRAP.main(
        ["--repo", str(ROOT), "--outputs", str(ROOT / "outputs"), "--json"]
    )
    lines = capsys.readouterr().out.splitlines()

    assert returncode == 2
    assert len(lines) == 1
    assert json.loads(lines[0])["passed"] is False
    assert json.loads(lines[0])["errors"] == ["release gate bootstrap failed"]


def test_bootstrap_archives_stored_commit_not_moving_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commit_oid = "1" * 40
    tree_oid = "2" * 40
    blob_payload = b"committed"
    blob_oid = hashlib.sha1(
        b"blob " + str(len(blob_payload)).encode("ascii") + b"\0" + blob_payload,
        usedforsecurity=False,
    ).hexdigest()
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text("locked", encoding="utf-8")
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    commands: list[tuple[str, ...]] = []
    selected_lock_roots: list[Path] = []
    inventory_checkpoints: list[int] = []

    class Builder:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def create(self, environment_root: Path) -> None:
            python = BOOTSTRAP._venv_python(environment_root)
            python.parent.mkdir(parents=True)
            python.write_bytes(b"python")

    def git(_repository: Path, *args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return commit_oid
        if args in {
            ("rev-parse", "HEAD^{tree}"),
            ("rev-parse", f"{commit_oid}^{{tree}}"),
        }:
            return tree_oid
        if args == ("status", "--porcelain=v1", "--untracked-files=all"):
            return ""
        if args == ("ls-tree", "-rz", "--full-tree", commit_oid):
            return f"100644 blob {blob_oid}\ttracked.txt\0"
        raise AssertionError(args)

    def git_blob_batch(
        _repository: Path,
        mode: str,
        requests: bytes,
        *,
        maximum: int,
    ) -> bytes:
        del maximum
        assert requests == f"{blob_oid}\n".encode("ascii")
        if mode.startswith("--batch-check="):
            return f"{blob_oid} blob {len(blob_payload)}\n".encode("ascii")
        assert mode == "--batch"
        return (
            f"{blob_oid} blob {len(blob_payload)}\n".encode("ascii")
            + blob_payload
            + b"\n"
        )

    def run(
        command: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout: int = 900,
    ) -> None:
        del cwd, env, timeout
        commands.append(command)
        if "archive" in command:
            Path(command[command.index("-o") + 1]).write_bytes(b"archive")
        if "build" in command:
            output = Path(command[command.index("--outdir") + 1])
            output.mkdir(exist_ok=True)
            with zipfile.ZipFile(output / "hsconfig.whl", "w") as wheel:
                wheel.writestr("hsconfig/__init__.py", "")

    monkeypatch.setattr(BOOTSTRAP.venv, "EnvBuilder", Builder)
    monkeypatch.setattr(BOOTSTRAP, "_git", git)
    monkeypatch.setattr(BOOTSTRAP, "_run_git_blob_batch", git_blob_batch)

    def selected_lock(root: Path) -> tuple[Path, dict[str, object], bytes]:
        selected_lock_roots.append(root)
        return lock_path, {"packages": []}, b"locked"

    monkeypatch.setattr(BOOTSTRAP, "_selected_lock", selected_lock)
    monkeypatch.setattr(BOOTSTRAP, "_lock_rows", lambda _document: {})
    monkeypatch.setattr(
        BOOTSTRAP,
        "_bootstrap_pip",
        lambda *_args: {
            "name": "pip",
            "version": "1",
            "url": "https://example.invalid/pip.whl",
            "sha256": "a" * 64,
            "wheel_path": str(bootstrap / "pip.whl"),
            "files": [],
        },
    )
    monkeypatch.setattr(
        BOOTSTRAP,
        "_audit_local_wheelhouse",
        lambda *_args, **_kwargs: [
            {"name": "coverage", "install": False},
            {"name": "setuptools", "install": False},
        ],
    )

    def extract_backend(_artifact: object, destination: Path) -> Path:
        destination.mkdir()
        return destination

    monkeypatch.setattr(BOOTSTRAP, "_extract_locked_python_overlay", extract_backend)
    monkeypatch.setattr(BOOTSTRAP, "_run", run)
    monkeypatch.setattr(
        BOOTSTRAP,
        "_safe_extract_archive",
        lambda _a, out: (out / "tracked.txt").write_bytes(b"committed"),
    )
    monkeypatch.setattr(
        BOOTSTRAP,
        "_assert_source_inventory",
        lambda _binding: inventory_checkpoints.append(len(commands)),
    )
    monkeypatch.setattr(BOOTSTRAP, "_purge_runtime_bytecode", lambda _root: None)
    monkeypatch.setattr(BOOTSTRAP, "_project_version", lambda _root: "1.0.0")
    monkeypatch.setattr(BOOTSTRAP, "_wheel_inventory", lambda _wheel: [])
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    runtime_binding = BOOTSTRAP._bootstrap_environment(ROOT, bootstrap)
    manifest_path = runtime_binding.manifest_path

    archive_commands = [command for command in commands if "archive" in command]
    locked_download_commands = [
        command
        for command in commands
        if "pip" in command and "download" in command and "-r" in command
    ]
    assert len(archive_commands) == 1
    assert archive_commands[0][-1] == commit_oid
    assert "HEAD" not in archive_commands[0]
    assert selected_lock_roots == [bootstrap / "committed-source"]
    assert len(locked_download_commands) == 1
    canonical_lock = Path(
        locked_download_commands[0][locked_download_commands[0].index("-r") + 1]
    )
    assert canonical_lock == bootstrap / "pylock.toml"
    assert canonical_lock.read_bytes() == lock_path.read_bytes() == b"locked"
    assert canonical_lock != lock_path
    build_index = next(index for index, command in enumerate(commands) if "build" in command)
    project_install_index = max(
        index
        for index, command in enumerate(commands)
        if "pip" in command and "install" in command
    )
    assert len(inventory_checkpoints) == 2
    assert inventory_checkpoints[0] == build_index
    assert inventory_checkpoints[1] == project_install_index
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_inventory_sha256"] == BOOTSTRAP._source_inventory_digest(
        manifest["source_inventory"]
    )
    assert (
        manifest["local_project"]["source_inventory_sha256"]
        == manifest["source_inventory_sha256"]
    )
    assert runtime_binding.manifest_sha256 == hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()


def test_canonical_bootstrap_ignores_an_assume_unchanged_checkout_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    archive = tmp_path / "repository.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), "HEAD"],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive) as source:
        source.extractall(repository)
    for name in ("pylock.3.11.toml", "pylock.3.12.toml"):
        shutil.copy2(ROOT / name, repository / name)
    with monkeypatch.context() as hostile_git:
        hostile_git.setenv("GIT_CONFIG_COUNT", "1")
        hostile_git.setenv("GIT_CONFIG_KEY_0", "core.longpaths")
        hostile_git.setenv("GIT_CONFIG_VALUE_0", "false")
        _initialize_full_repository_fixture(repository)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    lock = repository / f"pylock.{minor}.toml"
    committed_lock = lock.read_bytes()
    subprocess.run(
        ["git", "update-index", "--assume-unchanged", lock.name],
        cwd=repository,
        check=True,
    )
    lock.write_text("checkout lock must not be read\n", encoding="utf-8")
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    bootstrap_root = tmp_path / "bootstrap"
    bootstrap_root.mkdir()

    runtime_binding = BOOTSTRAP._bootstrap_environment(repository, bootstrap_root)
    manifest_path = runtime_binding.manifest_path

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["lock_sha256"] == hashlib.sha256(committed_lock).hexdigest()
    assert manifest["source_inventory_sha256"] == BOOTSTRAP._source_inventory_digest(
        manifest["source_inventory"]
    )
    assert not list((bootstrap_root / "build-backend").rglob("*.pth"))
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status == ""


def test_real_reexec_uses_inventory_bound_committed_controller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    archive = tmp_path / "repository.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), "HEAD"],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive) as source:
        source.extractall(repository)
    for name in (
        "pylock.3.11.toml",
        "pylock.3.12.toml",
        "scripts/check_release_gate.py",
    ):
        source = ROOT / name
        destination = repository / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (repository / "outputs").mkdir(exist_ok=True)
    _initialize_full_repository_fixture(repository)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    controller_path = repository / "scripts" / "check_release_gate.py"
    spec = importlib.util.spec_from_file_location("fixture_release_controller", controller_path)
    assert spec is not None and spec.loader is not None
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    bootstrap_root = tmp_path / "bootstrap"
    bootstrap_root.mkdir()
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    runtime_binding = controller._bootstrap_environment(repository, bootstrap_root)
    python = runtime_binding.python
    manifest_path = runtime_binding.manifest_path
    sentinel = runtime_binding.sentinel
    manifest_source = controller._read_bound(manifest_path)
    manifest = json.loads(manifest_source)
    child_environment = controller._base_environment()
    child_environment.update(
        {
            controller._SENTINEL: sentinel,
            controller._MANIFEST: str(manifest_path),
            controller._MANIFEST_DIGEST: hashlib.sha256(manifest_source).hexdigest(),
            "VIRTUAL_ENV": str(python.parent.parent),
            "PYTHONPATH": str(manifest["build_backend_root"]),
        }
    )
    argv = [
        "--repo",
        str(repository),
        "--outputs",
        str(repository / "outputs"),
        "--tree-mode",
        "working-pre-cutover",
        "--internal-check",
        "repository_hygiene",
        "--json",
    ]
    args = controller._parser().parse_args(argv)

    class Input:
        buffer = io.BytesIO(sentinel.encode("ascii") + b"\n")

    with monkeypatch.context() as binding_patch:
        binding_patch.setattr(controller.sys, "stdin", Input())
        binding_patch.setattr(controller.sys, "executable", str(python))
        for key, value in child_environment.items():
            binding_patch.setenv(key, value)
        assert controller._child_binding(args) is False

    subprocess.run(
        ["git", "update-index", "--assume-unchanged", "scripts/check_release_gate.py"],
        cwd=repository,
        check=True,
    )
    controller_path.write_text(
        "raise RuntimeError('mutable checkout controller executed')\n",
        encoding="utf-8",
    )

    returncode, document = controller._run_bound_child(
        python,
        repository,
        child_environment,
        argv,
        sentinel,
        timeout=300,
    )

    assert returncode == 0
    assert document["passed"] is True


def test_internal_command_specs_execute_the_bound_committed_controller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    archive = tmp_path / "repository.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), "HEAD"],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive) as source:
        source.extractall(repository)
    for relative in (
        ".github/workflows/ci.yml",
        "scripts/run_coverage_gate.py",
        "src/hsconfig/release_gate.py",
    ):
        (repository / relative).write_bytes((ROOT / relative).read_bytes())
    output_fixture_root = tmp_path / "canonical-output-fixture"
    output_fixture_root.mkdir()
    _fixture_repository, fixture_outputs = _repository(output_fixture_root)
    shutil.copytree(fixture_outputs, repository / "outputs")
    _initialize_full_repository_fixture(repository)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    controller_path = repository / "scripts" / "check_release_gate.py"
    controller_spec = importlib.util.spec_from_file_location(
        "internal_command_controller", controller_path
    )
    assert controller_spec is not None and controller_spec.loader is not None
    controller = importlib.util.module_from_spec(controller_spec)
    controller_spec.loader.exec_module(controller)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    bootstrap_root = tmp_path / "bootstrap"
    bootstrap_root.mkdir()
    binding = controller._bootstrap_environment(repository, bootstrap_root)
    manifest_source = binding.manifest_path.read_bytes()
    manifest = json.loads(manifest_source)
    artifact_keys = {
        "name",
        "version",
        "url",
        "sha256",
        "wheel_path",
        "files",
        "install",
        "allowed_startup_surfaces",
    }
    assert manifest["artifacts"]
    assert all(set(artifact) == artifact_keys for artifact in manifest["artifacts"])
    assert any(artifact["install"] is True for artifact in manifest["artifacts"])
    assert any(artifact["install"] is False for artifact in manifest["artifacts"])
    committed_controller = (
        bootstrap_root / "committed-source" / "scripts" / "check_release_gate.py"
    )
    environment = controller._base_environment()
    environment.update(
        {
            controller._SENTINEL: binding.sentinel,
            controller._MANIFEST: str(binding.manifest_path),
            controller._MANIFEST_DIGEST: hashlib.sha256(manifest_source).hexdigest(),
            "VIRTUAL_ENV": str(binding.python.parent.parent),
            "PYTHONPATH": os.pathsep.join(
                (
                    str(bootstrap_root / "committed-source"),
                    str(manifest["build_backend_root"]),
                )
            ),
        }
    )
    binding_probe = (
        "import argparse,importlib.util,json,sys;"
        "from pathlib import Path;"
        "path=Path(sys.argv[1]);"
        "spec=importlib.util.spec_from_file_location('bound_probe',path);"
        "module=importlib.util.module_from_spec(spec);"
        "sys.modules[spec.name]=module;spec.loader.exec_module(module);"
        "print(json.dumps({'binding':module._child_binding("
        "argparse.Namespace(repo=Path(sys.argv[2])))}))"
    )
    bound = subprocess.run(
        (
            str(binding.python),
            "-c",
            binding_probe,
            str(committed_controller),
            str(repository),
        ),
        cwd=repository,
        env=environment,
        input=(binding.sentinel + "\n").encode("ascii"),
        check=True,
        capture_output=True,
    )
    assert json.loads(bound.stdout)["binding"] is True

    committed_coverage_runner = (
        bootstrap_root / "committed-source" / "scripts" / "run_coverage_gate.py"
    )
    locked_coverage_probe = (
        "import json,subprocess,sys;"
        "from pathlib import Path;"
        "from scripts import run_coverage_gate as runner;"
        "repo=Path(sys.argv[1]);runner_path=Path(sys.argv[2]).resolve();"
        "assert Path(runner.__file__).resolve()==runner_path;"
        "assert runner.ROOT==runner_path.parents[1];"
        "assert runner.LOCK_FILE==runner.ROOT/"
        "f'pylock.{sys.version_info.major}.{sys.version_info.minor}.toml';"
        "runtime_paths=runner._assert_runtime_matches_lock();"
        "assert runtime_paths is not None;"
        "child_code=\"import coverage,pytest_cov.plugin,_hypothesis_pytestplugin,"
        "setuptools.build_meta,hsconfig,json;"
        "print(json.dumps({'coverage':coverage.__file__,'pytest_cov':pytest_cov.plugin.__file__,"
        "'hypothesis':_hypothesis_pytestplugin.__file__,'backend':setuptools.build_meta.__file__,"
        "'hsconfig':hsconfig.__file__},separators=(',',':')))\";"
        "context=runner.isolated_coverage_environment(runtime_paths);"
        "run=context.__enter__();"
        "completed=subprocess.run((sys.executable,'-c',child_code),cwd=repo,env=run.environment,"
        "capture_output=True,text=True,encoding='utf-8');"
        "context.__exit__(None,None,None);"
        "print(json.dumps({'runner':str(Path(runner.__file__).resolve()),"
        "'root':str(runner.ROOT),'lock':str(runner.LOCK_FILE),"
        "'returncode':completed.returncode,'stderr':completed.stderr,"
        "'pythonpath':run.environment['PYTHONPATH'].split(__import__('os').pathsep),"
        "'modules':json.loads(completed.stdout) if completed.returncode==0 else {}},"
        "separators=(',',':')))"
    )
    locked_coverage = subprocess.run(
        (
            str(binding.python),
            "-P",
            "-c",
            locked_coverage_probe,
            str(repository),
            str(committed_coverage_runner),
        ),
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    assert locked_coverage.returncode == 0, locked_coverage.stderr
    coverage_result = json.loads(locked_coverage.stdout)
    assert coverage_result["runner"] == str(committed_coverage_runner)
    assert coverage_result["root"] == str(bootstrap_root / "committed-source")
    assert coverage_result["lock"] == str(
        bootstrap_root / "committed-source" / f"pylock.{sys.version_info.major}.{sys.version_info.minor}.toml"
    )
    assert coverage_result["returncode"] == 0, coverage_result
    assert coverage_result["pythonpath"] == [
        str(bootstrap_root / "committed-source"),
        str(bootstrap_root / "build-backend"),
    ]
    assert str(bootstrap_root / "build-backend") in coverage_result["modules"][
        "backend"
    ]

    integration_probe = (
        "import json,os,sys;"
        "from pathlib import Path;"
        "from hsconfig.release_gate import _active_runtime_paths,_command_specs,_run_one;"
        "repo=Path(sys.argv[1]);outputs=Path(sys.argv[2]);"
        "sys.argv[0]=sys.argv[3];"
        "active=_active_runtime_paths(repo);"
        "manifest_root=Path(os.environ['HSCONFIG_RUNTIME_MANIFEST']).parent;"
        "assert active==(Path(sys.argv[3]).parents[1],manifest_root/'build-backend');"
        "wanted={'publishable_path_scan','repository_hygiene'};"
        "specs=[s for s in _command_specs(repo,outputs,'working-pre-cutover') "
        "if s.name in wanted];"
        "results=[_run_one(s,repository=repo) for s in specs];"
        "print(json.dumps([{'name':s.name,'controller':s.command[1],"
        "'passed':r.passed,'returncode':r.details.get('returncode'),"
        "'result':r.details.get('result')} for s,r in zip(specs,results)],"
        "separators=(',',':')))"
    )
    completed = subprocess.run(
        (
            str(binding.python),
            "-c",
            integration_probe,
            str(repository),
            str(repository / "outputs"),
            str(committed_controller),
        ),
        cwd=repository,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    results = json.loads(completed.stdout)

    assert [row["name"] for row in results] == [
        "publishable_path_scan",
        "repository_hygiene",
    ]
    assert all(row["controller"] == str(committed_controller) for row in results)
    for row in results:
        assert row["returncode"] == 0, json.dumps(row)
        assert row["passed"] is True, json.dumps(row)
        assert row["result"]["passed"] is True, json.dumps(row)


def test_parent_rejects_committed_controller_swap_before_process_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    archive = tmp_path / "repository.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), "HEAD"],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive) as source:
        source.extractall(repository)
    for name in (
        "pylock.3.11.toml",
        "pylock.3.12.toml",
        "scripts/check_release_gate.py",
    ):
        source = ROOT / name
        destination = repository / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    _initialize_full_repository_fixture(repository)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    controller_path = repository / "scripts" / "check_release_gate.py"
    spec = importlib.util.spec_from_file_location("tamper_release_controller", controller_path)
    assert spec is not None and spec.loader is not None
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    bootstrap_root = tmp_path / "bootstrap"
    bootstrap_root.mkdir()
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    runtime_binding = controller._bootstrap_environment(repository, bootstrap_root)
    committed_controller = bootstrap_root / "committed-source" / "scripts" / "check_release_gate.py"
    committed_controller.write_text(
        "raise RuntimeError('swapped committed controller executed')\n",
        encoding="utf-8",
    )
    process_creations = 0

    def reject_process_creation(*_args: object, **_kwargs: object) -> object:
        nonlocal process_creations
        process_creations += 1
        raise AssertionError("committed controller tamper reached process creation")

    monkeypatch.setattr(
        controller,
        "_bootstrap_environment",
        lambda *_args: runtime_binding,
    )
    monkeypatch.setattr(controller.subprocess, "Popen", reject_process_creation)
    argv = [
        "--repo",
        str(repository),
        "--outputs",
        str(tmp_path / "route-outputs"),
        "--tree-mode",
        "working-pre-cutover",
        "--internal-check",
        "repository_hygiene",
        "--json",
    ]

    assert controller.main(argv) == 2
    output = capsys.readouterr().out
    assert output.count("\n") == 1
    document = json.loads(output)
    assert document["passed"] is False
    assert document["errors"] == ["release gate bootstrap failed"]
    assert process_creations == 0


def test_verified_controller_bytes_cannot_be_swapped_at_process_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    archive = tmp_path / "repository.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), "HEAD"],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive) as source:
        source.extractall(repository)
    for name in (
        "pylock.3.11.toml",
        "pylock.3.12.toml",
        "scripts/check_release_gate.py",
    ):
        source = ROOT / name
        destination = repository / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    _initialize_full_repository_fixture(repository)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    controller_path = repository / "scripts" / "check_release_gate.py"
    spec = importlib.util.spec_from_file_location("toctou_release_controller", controller_path)
    assert spec is not None and spec.loader is not None
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    bootstrap_root = tmp_path / "bootstrap"
    bootstrap_root.mkdir()
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    bootstrap = controller._bootstrap_environment(repository, bootstrap_root)
    committed_controller = bootstrap_root / "committed-source" / "scripts" / "check_release_gate.py"
    unchecked_marker = tmp_path / "unchecked-controller-executed.txt"
    replacement = (
        "from pathlib import Path\n"
        f"Path({str(unchecked_marker)!r}).write_text('unchecked', encoding='utf-8')\n"
        "print('{\"passed\":true}')\n"
    )
    real_popen = controller.subprocess.Popen
    process_creations = 0

    def swap_at_process_creation(*args: object, **kwargs: object) -> object:
        nonlocal process_creations
        process_creations += 1
        if process_creations == 1:
            committed_controller.write_text(replacement, encoding="utf-8")
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(controller, "_bootstrap_environment", lambda *_args: bootstrap)
    monkeypatch.setattr(controller.subprocess, "Popen", swap_at_process_creation)
    argv = [
        "--repo",
        str(repository),
        "--outputs",
        str(tmp_path / "route-outputs"),
        "--tree-mode",
        "working-pre-cutover",
        "--internal-check",
        "repository_hygiene",
        "--json",
    ]

    assert controller.main(argv) == 2
    output = capfd.readouterr().out
    assert output.count("\n") == 1
    document = json.loads(output)
    assert document["passed"] is False
    assert document["errors"] == ["release gate bootstrap failed"]
    assert process_creations == 1
    assert not unchecked_marker.exists()


def test_real_reexec_preserves_exact_relative_public_operands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    archive = tmp_path / "repository.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), "HEAD"],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive) as source:
        source.extractall(repository)
    for name in (
        "pylock.3.11.toml",
        "pylock.3.12.toml",
        "scripts/check_release_gate.py",
    ):
        source = ROOT / name
        destination = repository / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (repository / "outputs").mkdir(exist_ok=True)
    _initialize_full_repository_fixture(repository)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    controller_path = repository / "scripts" / "check_release_gate.py"
    spec = importlib.util.spec_from_file_location("relative_release_controller", controller_path)
    assert spec is not None and spec.loader is not None
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.chdir(repository)
    argv = [
        "--repo",
        ".",
        "--outputs",
        "outputs",
        "--tree-mode",
        "working-pre-cutover",
        "--internal-check",
        "repository_hygiene",
        "--json",
    ]

    assert controller.main(argv) == 0
    output = capfd.readouterr().out
    assert output.count("\n") == 1
    assert json.loads(output)["passed"] is True


def test_ci_source_baseline_rejects_ref_mutated_before_capture(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "core.autocrlf", "false"], cwd=repository, check=True
    )
    (repository / "tracked.txt").write_text("first", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "first",
        ],
        cwd=repository,
        check=True,
    )
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repository / "tracked.txt").write_text("second", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "second",
        ],
        cwd=repository,
        check=True,
    )
    root = tmp_path / "baseline"
    root.mkdir()

    with pytest.raises(BOOTSTRAP._BootstrapError, match="event commit"):
        BOOTSTRAP._materialize_committed_source(repository, root, expected)
    assert list(root.iterdir()) == []


def test_ci_source_baseline_rejects_unsafe_archive_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    (repository / "tracked.txt").write_text("safe", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    original_run = BOOTSTRAP._run

    def unsafe_archive(
        command: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout: int = 900,
    ) -> None:
        if "archive" not in command:
            original_run(command, cwd=cwd, env=env, timeout=timeout)
            return
        archive_path = Path(command[command.index("-o") + 1])
        with tarfile.open(archive_path, "w") as archive:
            member = tarfile.TarInfo("linked")
            member.type = tarfile.SYMTYPE
            member.linkname = "../outside"
            archive.addfile(member)

    monkeypatch.setattr(BOOTSTRAP, "_run", unsafe_archive)
    root = tmp_path / "baseline"
    root.mkdir()

    with pytest.raises(BOOTSTRAP._BootstrapError, match="archive is unsafe"):
        BOOTSTRAP._materialize_committed_source(repository, root, expected)
    assert not (tmp_path / "outside").exists()


def test_ci_source_baseline_rejects_non_regular_git_tree_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commit_oid = "1" * 40

    monkeypatch.setattr(
        BOOTSTRAP,
        "_git",
        lambda _repository, *arguments: (
            f"120000 blob {'2' * 40}\tlinked\0"
            if arguments == ("ls-tree", "-rz", "--full-tree", commit_oid)
            else (_ for _ in ()).throw(AssertionError(arguments))
        ),
    )

    with pytest.raises(BOOTSTRAP._BootstrapError, match="non-regular"):
        BOOTSTRAP._assert_regular_git_tree(tmp_path, commit_oid)


def test_ci_blob_batch_rejects_missing_object(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    entries = (
        {
            "path": "missing.txt",
            "git_mode": "100644",
            "blob_oid": "f" * 40,
        },
    )

    with pytest.raises(BOOTSTRAP._BootstrapError, match="blob batch is invalid"):
        BOOTSTRAP._git_blob_payloads(repository, entries)


def test_ci_blob_batch_rejects_malformed_check_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    entries = (
        {
            "path": "tracked.txt",
            "git_mode": "100644",
            "blob_oid": "1" * 40,
        },
    )

    monkeypatch.setattr(
        BOOTSTRAP,
        "_run_git_blob_batch",
        lambda *args, **kwargs: b"malformed\n",
    )

    with pytest.raises(BOOTSTRAP._BootstrapError, match="blob batch is invalid"):
        BOOTSTRAP._git_blob_payloads(repository, entries)


@pytest.mark.parametrize(
    "check_line",
    (
        b" e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 blob 0\n",
        b"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 blob 0 \n",
        b"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391\tblob 0\n",
        b"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391  blob 0\n",
    ),
    ids=("leading", "trailing", "tab", "repeated"),
)
def test_ci_blob_batch_rejects_noncanonical_check_whitespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    check_line: bytes,
) -> None:
    oid = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    responses = iter((check_line, f"{oid} blob 0\n\n".encode("ascii")))
    monkeypatch.setattr(
        BOOTSTRAP,
        "_run_git_blob_batch",
        lambda *args, **kwargs: next(responses),
    )

    with pytest.raises(BOOTSTRAP._BootstrapError, match="blob batch is invalid"):
        BOOTSTRAP._git_blob_payloads(
            tmp_path,
            ({"path": "empty", "git_mode": "100644", "blob_oid": oid},),
        )


@pytest.mark.parametrize("surface", ("controller", "active"))
@pytest.mark.parametrize("stream_name", ("stdout", "stderr"))
def test_git_blob_batch_streaming_capture_is_hard_bounded_and_terminates_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    stream_name: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    module = BOOTSTRAP if surface == "controller" else release_gate_module
    error_type = BOOTSTRAP._BootstrapError if surface == "controller" else ReleaseGateError
    marker = tmp_path / f"{surface}-{stream_name}-descendant.txt"
    descendant = (
        "import pathlib,time; time.sleep(1.25); "
        f"pathlib.Path({str(marker)!r}).write_text('escaped',encoding='utf-8')"
    )
    producer = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{descendant!r}]); "
        f"stream=sys.{stream_name}.buffer; "
        "stream.write(b'x'*(1024*1024)); stream.flush(); time.sleep(30)"
    )
    monkeypatch.setattr(
        module,
        "_git_blob_command",
        lambda repository, argument: (sys.executable, "-c", producer),
    )
    started = time.monotonic()

    with pytest.raises(error_type, match=f"{stream_name}.*size limit"):
        module._run_git_blob_batch(
            tmp_path,
            "--batch",
            b"request\n",
            maximum=32,
            timeout=5,
        )

    assert time.monotonic() - started < 3
    time.sleep(1.75)
    assert not marker.exists()


@pytest.mark.parametrize("surface", ("controller", "active"))
@pytest.mark.parametrize("failure", ("timeout", "exit"))
def test_git_blob_batch_streaming_capture_rejects_timeout_or_nonzero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    failure: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    module = BOOTSTRAP if surface == "controller" else release_gate_module
    error_type = BOOTSTRAP._BootstrapError if surface == "controller" else ReleaseGateError
    producer = "import time; time.sleep(30)" if failure == "timeout" else "raise SystemExit(7)"
    expected = "timed out" if failure == "timeout" else "exited nonzero"
    timeout = 0.2 if failure == "timeout" else 5
    monkeypatch.setattr(
        module,
        "_git_blob_command",
        lambda repository, argument: (sys.executable, "-c", producer),
    )
    started = time.monotonic()

    with pytest.raises(error_type, match=expected):
        module._run_git_blob_batch(
            tmp_path,
            "--batch",
            b"request\n",
            maximum=32,
            timeout=timeout,
        )

    assert time.monotonic() - started < 3


@pytest.mark.parametrize("surface", ("controller", "active"))
def test_git_blob_batch_rejects_truncated_payload_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    module = BOOTSTRAP if surface == "controller" else release_gate_module
    error_type = BOOTSTRAP._BootstrapError if surface == "controller" else ReleaseGateError
    oid = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    responses = iter(
        (
            f"{oid} blob 0\n".encode("ascii"),
            f"{oid} blob 0\n".encode("ascii"),
        )
    )
    monkeypatch.setattr(
        module,
        "_run_git_blob_batch",
        lambda *args, **kwargs: next(responses),
    )

    with pytest.raises(error_type, match="blob batch is invalid"):
        module._git_blob_payloads(
            tmp_path,
            ({"path": "empty", "git_mode": "100644", "blob_oid": oid},),
        )


@pytest.mark.parametrize("surface", ("controller", "active"))
def test_git_blob_batch_target_cannot_launch_before_process_tree_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    module = BOOTSTRAP if surface == "controller" else release_gate_module
    lease_name = (
        "_BootstrapProcessTreeLease" if surface == "controller" else "_ProcessTreeLease"
    )
    real_lease = getattr(module, lease_name)
    marker = tmp_path / f"{surface}-pre-lease-descendant.txt"
    descendant = (
        "import pathlib,time; time.sleep(1.0); "
        f"pathlib.Path({str(marker)!r}).write_text('escaped',encoding='utf-8')"
    )
    producer = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-c',{descendant!r}]); "
        "sys.stdout.buffer.write(b'ok'); sys.stdout.buffer.flush()"
    )

    class DelayedLease:
        def __init__(self, process, baseline):
            time.sleep(0.5)
            self._lease = real_lease(process, baseline)

        def terminate_remaining(self) -> None:
            self._lease.terminate_remaining()

    monkeypatch.setattr(module, lease_name, DelayedLease)
    monkeypatch.setattr(
        module,
        "_git_blob_command",
        lambda repository, argument: (sys.executable, "-c", producer),
        raising=False,
    )

    output = module._run_git_blob_batch(
        tmp_path,
        "--batch",
        b"request\n",
        maximum=32,
        timeout=5,
    )

    assert output == b"ok"
    time.sleep(1.25)
    assert not marker.exists()


@pytest.mark.parametrize("surface", ("controller", "active"))
def test_git_blob_batch_lease_assignment_failure_never_launches_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    module = BOOTSTRAP if surface == "controller" else release_gate_module
    error_type = BOOTSTRAP._BootstrapError if surface == "controller" else ReleaseGateError
    lease_name = (
        "_BootstrapProcessTreeLease" if surface == "controller" else "_ProcessTreeLease"
    )
    marker = tmp_path / f"{surface}-assignment-failure-target.txt"
    producer = (
        "import pathlib; "
        f"pathlib.Path({str(marker)!r}).write_text('launched',encoding='utf-8')"
    )

    class FailingLease:
        def __init__(self, process, baseline):
            raise OSError("synthetic lease failure")

    monkeypatch.setattr(module, lease_name, FailingLease)
    monkeypatch.setattr(
        module,
        "_git_blob_command",
        lambda repository, argument: (sys.executable, "-c", producer),
        raising=False,
    )

    with pytest.raises(error_type, match="blob batch is invalid"):
        module._run_git_blob_batch(
            tmp_path,
            "--batch",
            b"request\n",
            maximum=32,
            timeout=5,
        )

    time.sleep(0.5)
    assert not marker.exists()


@pytest.mark.parametrize("surface", ("controller", "active"))
@pytest.mark.parametrize("lease_outcome", ("delayed", "failure"))
@pytest.mark.parametrize("checkout_shadow", ("json", "subprocess"))
def test_git_blob_launcher_is_isolated_before_lease_and_never_writes_bytecode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    lease_outcome: str,
    checkout_shadow: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    module = BOOTSTRAP if surface == "controller" else release_gate_module
    error_type = BOOTSTRAP._BootstrapError if surface == "controller" else ReleaseGateError
    lease_name = (
        "_BootstrapProcessTreeLease" if surface == "controller" else "_ProcessTreeLease"
    )
    real_lease = getattr(module, lease_name)
    repository = tmp_path / "repository"
    ambient = tmp_path / "ambient"
    repository.mkdir()
    ambient.mkdir()
    attempted_markers: list[Path] = []
    descendant_markers: list[Path] = []

    def hostile_module(path: Path, identity: str) -> None:
        attempted = tmp_path / f"{surface}-{lease_outcome}-{identity}-imported.txt"
        descendant = tmp_path / f"{surface}-{lease_outcome}-{identity}-descendant.txt"
        attempted_markers.append(attempted)
        descendant_markers.append(descendant)
        descendant_source = (
            "import time; time.sleep(1.0); "
            f"handle=open({str(descendant)!r},'w',encoding='utf-8'); "
            "handle.write('escaped'); handle.close()"
        )
        path.write_text(
            "import os,sys\n"
            f"handle=open({str(attempted)!r},'w',encoding='utf-8')\n"
            "handle.write('imported')\n"
            "handle.close()\n"
            f"os.spawnv(os.P_NOWAIT,sys.executable,[sys.executable,'-c',{descendant_source!r}])\n"
            "raise ImportError('hostile import')\n",
            encoding="utf-8",
        )

    hostile_module(repository / f"{checkout_shadow}.py", f"checkout-{checkout_shadow}")
    hostile_module(ambient / "sitecustomize.py", "sitecustomize")
    hostile_module(ambient / "usercustomize.py", "usercustomize")
    monkeypatch.setenv("PYTHONPATH", str(ambient))
    monkeypatch.setenv("PYTHONUSERBASE", str(ambient / "user-base"))

    target_marker = tmp_path / f"{surface}-{lease_outcome}-target.txt"
    producer = (
        "import pathlib,sys; "
        f"pathlib.Path({str(target_marker)!r}).write_text('launched',encoding='utf-8'); "
        "sys.stdout.buffer.write(b'ok'); sys.stdout.buffer.flush()"
    )
    monkeypatch.setattr(
        module,
        "_git_blob_command",
        lambda root, argument: (
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            producer,
        ),
    )

    if lease_outcome == "delayed":

        class SyntheticLease:
            def __init__(self, process, baseline):
                time.sleep(0.4)
                self._lease = real_lease(process, baseline)

            def terminate_remaining(self) -> None:
                self._lease.terminate_remaining()

    else:

        class SyntheticLease:
            def __init__(self, process, baseline):
                raise OSError("synthetic lease failure")

    monkeypatch.setattr(module, lease_name, SyntheticLease)

    if lease_outcome == "delayed":
        output = module._run_git_blob_batch(
            repository,
            "--batch",
            b"request\n",
            maximum=32,
            timeout=5,
        )
        assert output == b"ok"
        assert target_marker.is_file()
    else:
        with pytest.raises(error_type, match="blob batch is invalid"):
            module._run_git_blob_batch(
                repository,
                "--batch",
                b"request\n",
                maximum=32,
                timeout=5,
            )
        assert not target_marker.exists()

    time.sleep(1.25)
    assert all(not marker.exists() for marker in attempted_markers)
    assert all(not marker.exists() for marker in descendant_markers)
    assert not (repository / "__pycache__").exists()
    assert not (ambient / "__pycache__").exists()


@pytest.mark.parametrize("surface", ("controller", "active"))
def test_git_blob_launcher_uses_exact_isolated_interpreter_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    module = BOOTSTRAP if surface == "controller" else release_gate_module
    observed: list[tuple[str, ...]] = []
    real_popen = subprocess.Popen

    def observe_launcher(command: tuple[str, ...], **kwargs: object):
        observed.append(tuple(command))
        return real_popen(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", observe_launcher)
    monkeypatch.setattr(
        module,
        "_git_blob_command",
        lambda root, argument: (
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            "import sys; sys.stdout.buffer.write(b'ok')",
        ),
    )

    assert module._run_git_blob_batch(
        tmp_path,
        "--batch",
        b"request\n",
        maximum=32,
        timeout=5,
    ) == b"ok"
    assert observed[0] == (
        module._process_tree_gate_interpreter(sys.executable),
        "-I",
        "-S",
        "-B",
        "-c",
        module._GIT_BLOB_BATCH_LAUNCHER,
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows venv redirector semantics")
@pytest.mark.parametrize("surface", ("controller", "active"))
def test_windows_process_tree_gate_uses_validated_base_interpreter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    import hsconfig.release_gate as release_gate_module

    module = BOOTSTRAP if surface == "controller" else release_gate_module
    base_interpreter = tmp_path / "base-python.exe"
    base_interpreter.write_bytes(b"synthetic regular executable")
    redirector = tmp_path / "venv" / "Scripts" / "python.exe"
    monkeypatch.setattr(module.sys, "_base_executable", str(base_interpreter))

    assert module._process_tree_gate_interpreter(redirector) == str(
        base_interpreter.resolve(strict=True)
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows venv redirector semantics")
@pytest.mark.parametrize("surface", ("controller", "active"))
@pytest.mark.parametrize("invalid_base", (None, "", "relative-python.exe"))
def test_windows_process_tree_gate_rejects_unbound_base_interpreter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    invalid_base: str | None,
) -> None:
    import hsconfig.release_gate as release_gate_module

    module = BOOTSTRAP if surface == "controller" else release_gate_module
    error_type = BOOTSTRAP._BootstrapError if surface == "controller" else ReleaseGateError
    monkeypatch.setattr(module.sys, "_base_executable", invalid_base)

    with pytest.raises(error_type, match="process gate interpreter is invalid"):
        module._process_tree_gate_interpreter(tmp_path / "venv-python.exe")


def test_bounded_process_gate_uses_exact_isolated_interpreter_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hsconfig.release_gate as release_gate_module

    observed: list[tuple[str, ...]] = []
    real_popen = release_gate_module.subprocess.Popen

    def observe_launcher(command: tuple[str, ...], **kwargs: object):
        observed.append(tuple(command))
        return real_popen(command, **kwargs)

    monkeypatch.setattr(release_gate_module.subprocess, "Popen", observe_launcher)
    completed = release_gate_module._execute_bounded_process(
        (sys.executable, "-I", "-S", "-B", "-c", "print('ok')"),
        cwd=tmp_path,
        env=_controlled_environment(ROOT),
        timeout=30,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "ok"
    assert observed == [
        (
            _process_tree_gate_interpreter(sys.executable),
            "-I",
            "-S",
            "-B",
            "-c",
            release_gate_module._GATED_LAUNCHER,
        )
    ]


def test_materialized_source_inventory_binds_sorted_content_and_git_modes(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "core.autocrlf", "false"], cwd=repository, check=True
    )
    (repository / "z-script.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
    (repository / "a-data.txt").write_bytes(b"data\n")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        ["git", "update-index", "--chmod=+x", "z-script.sh"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    expected_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    root = tmp_path / "baseline"
    root.mkdir()

    binding = BOOTSTRAP._materialize_committed_source(
        repository, root, expected_commit
    )
    expected_inventory = (
        {
            "path": "a-data.txt",
            "sha256": hashlib.sha256(b"data\n").hexdigest(),
            "git_mode": "100644",
        },
        {
            "path": "z-script.sh",
            "sha256": hashlib.sha256(b"#!/bin/sh\nexit 0\n").hexdigest(),
            "git_mode": "100755",
        },
    )
    expected_digest = hashlib.sha256(
        json.dumps(
            expected_inventory,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()

    assert binding.source_root == root / "committed-source"
    assert binding.commit_oid == expected_commit
    assert binding.inventory == expected_inventory
    assert binding.inventory_sha256 == expected_digest
    BOOTSTRAP._assert_source_inventory(binding)


def test_materialized_source_inventory_ignores_ambient_autocrlf_true(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "core.autocrlf", "true"], cwd=repository, check=True
    )
    source = b"first\nsecond\n"
    (repository / "tracked.txt").write_bytes(source)
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    expected_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    root = tmp_path / "baseline"
    root.mkdir()

    binding = BOOTSTRAP._materialize_committed_source(
        repository, root, expected_commit
    )

    assert (binding.source_root / "tracked.txt").read_bytes() == source
    assert binding.inventory == (
        {
            "path": "tracked.txt",
            "sha256": hashlib.sha256(source).hexdigest(),
            "git_mode": "100644",
        },
    )
    BOOTSTRAP._assert_source_inventory(binding)


def test_materialized_source_rejects_export_subst_archive_bytes(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "core.autocrlf", "false"], cwd=repository, check=True
    )
    (repository / ".gitattributes").write_text(
        "version.txt export-subst\n", encoding="utf-8"
    )
    (repository / "version.txt").write_text("$Format:%H$\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    expected_commit = _git(repository, "rev-parse", "HEAD")
    root = tmp_path / "baseline"
    root.mkdir()

    with pytest.raises(
        BOOTSTRAP._BootstrapError,
        match="archive differs from Git blobs",
    ):
        BOOTSTRAP._materialize_committed_source(repository, root, expected_commit)


@pytest.mark.parametrize("mutation", ("content", "inventory_mode"))
def test_materialized_source_revalidation_rejects_content_or_mode_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    (repository / "tracked.txt").write_bytes(b"original")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    root = tmp_path / "baseline"
    root.mkdir()
    binding = BOOTSTRAP._materialize_committed_source(repository, root)
    if mutation == "content":
        (binding.source_root / "tracked.txt").write_bytes(b"changed")
    else:
        binding.inventory[0]["git_mode"] = "100755"

    with pytest.raises(BOOTSTRAP._BootstrapError, match="source inventory"):
        BOOTSTRAP._assert_source_inventory(binding)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_source_inventory_rejects_nested_file_redirected_by_ancestor_junction(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "committed-source"
    source_root.mkdir()
    outside = tmp_path / "outside"
    (outside / "sub").mkdir(parents=True)
    payload = b"inventory-identical-but-outside-root\n"
    (outside / "sub" / "module.py").write_bytes(payload)
    junction = source_root / "pkg"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("junction creation unavailable")
    inventory = (
        {
            "path": "pkg/sub/module.py",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "git_mode": "100644",
        },
    )
    inventory_sha256 = hashlib.sha256(
        json.dumps(
            inventory,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    ).hexdigest()
    binding = BOOTSTRAP._SourceBinding(
        source_root=source_root,
        commit_oid="1" * 40,
        tree_oid="2" * 40,
        inventory=inventory,
        inventory_sha256=inventory_sha256,
    )

    with pytest.raises(BOOTSTRAP._BootstrapError, match="source inventory.*unsafe"):
        BOOTSTRAP._assert_source_inventory(binding)


def test_safe_extract_preserves_allowed_committed_file_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "source.tar"
    with tarfile.open(archive_path, "w") as archive:
        for name, mode in (("data.txt", 0o644), ("script.sh", 0o755)):
            payload = name.encode("ascii")
            member = tarfile.TarInfo(name)
            member.mode = mode
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    observed: list[tuple[str, int]] = []
    real_chmod = os.chmod

    def record_mode(path: Path, mode: int) -> None:
        observed.append((Path(path).name, mode))
        real_chmod(path, mode)

    monkeypatch.setattr(BOOTSTRAP.os, "chmod", record_mode)
    destination = tmp_path / "source"
    destination.mkdir()

    BOOTSTRAP._safe_extract_archive(archive_path, destination)

    assert observed == [("data.txt", 0o644), ("script.sh", 0o755)]


@pytest.mark.parametrize("startup_name", ("payload.pth", "sitecustomize.py", "usercustomize.py"))
def test_dependency_wheel_inventory_rejects_python_startup_surfaces(
    tmp_path: Path,
    startup_name: str,
) -> None:
    wheel = tmp_path / "dependency.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("dependency/__init__.py", "")
        archive.writestr(startup_name, "raise RuntimeError('executed')")

    with pytest.raises(BOOTSTRAP._BootstrapError, match="startup surface"):
        BOOTSTRAP._wheel_inventory(wheel)


def test_local_wheelhouse_audit_requires_exact_complete_hash_bound_closure(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheels: list[tuple[str, bytes]] = []
    for name in ("alpha-1.0-py3-none-any.whl", "beta-2.0-py3-none-any.whl"):
        path = wheelhouse / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(f"{name.split('-', 1)[0]}/__init__.py", "")
        wheels.append((name, path.read_bytes()))
    rows = {
        ("alpha", "1.0"): {
            "name": "alpha",
            "version": "1.0",
            "wheels": [
                {
                    "name": wheels[0][0],
                    "url": "https://example.invalid/alpha.whl",
                    "sha256": hashlib.sha256(wheels[0][1]).hexdigest(),
                }
            ],
        },
        ("beta", "2.0"): {
            "name": "beta",
            "version": "2.0",
            "wheels": [
                {
                    "name": wheels[1][0],
                    "url": "https://example.invalid/beta.whl",
                    "sha256": hashlib.sha256(wheels[1][1]).hexdigest(),
                }
            ],
        },
    }

    artifacts = BOOTSTRAP._audit_local_wheelhouse(wheelhouse, rows)

    assert [row["name"] for row in artifacts] == ["alpha", "beta"]
    assert all(row["files"] for row in artifacts)
    (wheelhouse / wheels[1][0]).unlink()
    with pytest.raises(BOOTSTRAP._BootstrapError, match="wheelhouse closure"):
        BOOTSTRAP._audit_local_wheelhouse(wheelhouse, rows)


def test_setuptools_startup_hook_is_never_installed_with_dependencies(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheel = wheelhouse / "setuptools-83.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("setuptools/__init__.py", "__version__ = '83.0.0'")
        archive.writestr(
            "distutils-precedence.pth", "import _distutils_hack; _distutils_hack.add_shim()"
        )
    rows = {
        ("setuptools", "83.0.0"): {
            "name": "setuptools",
            "version": "83.0.0",
            "wheels": [
                {
                    "name": wheel.name,
                    "url": "https://example.invalid/setuptools.whl",
                    "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                }
            ],
        }
    }

    artifact = BOOTSTRAP._audit_local_wheelhouse(wheelhouse, rows)[0]
    backend = BOOTSTRAP._extract_locked_build_backend(artifact, tmp_path / "backend")

    assert artifact["install"] is False
    assert artifact["allowed_startup_surfaces"] == ["distutils-precedence.pth"]
    assert (backend / "setuptools" / "__init__.py").is_file()
    assert not list(backend.rglob("*.pth"))


@pytest.mark.parametrize(
    "mutation",
    ("missing_hooks", "wrong_hooks", "wrong_disposition", "wrong_inventory"),
)
def test_manifest_artifact_validation_fails_closed_on_policy_mismatch(
    tmp_path: Path,
    mutation: str,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheel = wheelhouse / "coverage-7.15.2-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("coverage/__init__.py", "")
        archive.writestr("a1_coverage.pth", "import coverage")
    locked = {
        "name": "coverage",
        "version": "7.15.2",
        "wheels": [
            {
                "name": wheel.name,
                "url": "https://example.invalid/coverage.whl",
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            }
        ],
    }
    artifact = BOOTSTRAP._audit_local_wheelhouse(
        wheelhouse, {("coverage", "7.15.2"): locked}
    )[0]
    if mutation == "missing_hooks":
        artifact.pop("allowed_startup_surfaces")
    elif mutation == "wrong_hooks":
        artifact["allowed_startup_surfaces"] = ["wrong.pth"]
    elif mutation == "wrong_disposition":
        artifact["install"] = True
    else:
        artifact["files"] = [*artifact["files"], {"path": "extra", "size": 0, "sha256": "0" * 64}]

    with pytest.raises(BOOTSTRAP._BootstrapError, match="artifact policy"):
        BOOTSTRAP._validate_locked_artifact(artifact, locked, tmp_path)


def test_manifest_artifact_validation_accepts_exact_central_policy(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheel = wheelhouse / "coverage-7.15.2-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("coverage/__init__.py", "")
        archive.writestr("a1_coverage.pth", "import coverage")
    locked = {
        "name": "coverage",
        "version": "7.15.2",
        "wheels": [
            {
                "name": wheel.name,
                "url": "https://example.invalid/coverage.whl",
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            }
        ],
    }
    artifact = BOOTSTRAP._audit_local_wheelhouse(
        wheelhouse, {("coverage", "7.15.2"): locked}
    )[0]

    BOOTSTRAP._validate_locked_artifact(artifact, locked, tmp_path)


def test_direct_ci_source_revalidation_accepts_intact_then_rejects_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    archive = tmp_path / "repository.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), "HEAD"],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive) as source:
        source.extractall(repository)
    _initialize_full_repository_fixture(repository)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    commit_oid = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    github_environment = tmp_path / "github-env"
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.setenv("GITHUB_SHA", commit_oid)
    monkeypatch.setenv("GITHUB_ENV", str(github_environment))
    baseline_args = [
        "--repo",
        str(repository),
        "--outputs",
        str(runner_temp / "unused-outputs"),
        "--locked-check",
        "ci-source-baseline",
        "--json",
    ]

    assert BOOTSTRAP.main(baseline_args) == 0
    capsys.readouterr()
    for line in github_environment.read_text(encoding="utf-8").splitlines():
        key, value = line.split("=", 1)
        monkeypatch.setenv(key, value)
    revalidate_args = [
        "--repo",
        str(repository),
        "--outputs",
        str(runner_temp / "unused-outputs"),
        "--locked-check",
        "ci-source-revalidate",
        "--json",
    ]

    assert BOOTSTRAP.main(revalidate_args) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True
    source_root = Path(os.environ["HSCONFIG_CI_SOURCE_ROOT"])
    (source_root / "README.md").write_bytes(b"mutated")
    assert BOOTSTRAP.main(revalidate_args) == 2
    assert json.loads(capsys.readouterr().out)["passed"] is False


@pytest.mark.parametrize("mutation", ("content", "replacement"))
def test_bootstrap_lock_binding_rejects_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    source = b"lock-version = \"1.0\"\n"
    path, binding = BOOTSTRAP._materialize_bootstrap_lock(tmp_path, source)
    if mutation == "content":
        path.write_bytes(b"lock-version = \"1.1\"\n")
    else:
        replacement = tmp_path / "replacement"
        replacement.write_bytes(source)
        os.replace(replacement, path)

    with pytest.raises(BOOTSTRAP._BootstrapError, match="bootstrap lock"):
        BOOTSTRAP._verify_bootstrap_lock_binding(path, source, binding)


@pytest.mark.skipif(
    os.name != "nt" or sys.version_info < (3, 12),
    reason="Windows Python 3.12 stat timestamp contract",
)
def test_windows_py312_bootstrap_lock_binding_matches_descriptor_identity(
    tmp_path: Path,
) -> None:
    """Catches path and descriptor ctime using incompatible Windows semantics."""
    source = b"lock-version = \"1.0\"\n"
    path = tmp_path / "pylock.toml"
    with path.open("xb") as handle:
        time.sleep(0.05)
        handle.write(source)
        handle.flush()
        os.fsync(handle.fileno())
    binding = BOOTSTRAP._bootstrap_lock_binding(path, source)

    with BOOTSTRAP._bootstrap_lock_execution_lease(path, source, binding):
        assert path.read_bytes() == source


@pytest.mark.skipif(os.name != "nt", reason="Windows stat timestamp contract")
def test_windows_binding_normalization_preserves_descriptor_ctime_monitoring() -> None:
    common = {
        "st_dev": 1,
        "st_ino": 2,
        "st_size": 3,
        "st_mtime_ns": 4,
        "st_birthtime_ns": 5,
        "st_mode": stat.S_IFREG,
    }
    before = SimpleNamespace(**common, st_ctime_ns=6)
    after = SimpleNamespace(**common, st_ctime_ns=7)

    assert BOOTSTRAP._bootstrap_lock_binding_identity(before) == (
        1,
        2,
        3,
        4,
        5,
        stat.S_IFREG,
    )
    assert BOOTSTRAP._bootstrap_lock_binding_identity(after) == (
        1,
        2,
        3,
        4,
        5,
        stat.S_IFREG,
    )
    assert BOOTSTRAP._descriptor_stat_identity(before) != (
        BOOTSTRAP._descriptor_stat_identity(after)
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing-mode contract")
def test_windows_bootstrap_lock_lease_blocks_swap_restore_during_run(
    tmp_path: Path,
) -> None:
    source = b"lock-version = \"1.0\"\n"
    path, binding = BOOTSTRAP._materialize_bootstrap_lock(tmp_path, source)
    displaced = tmp_path / "displaced-lock"
    swap = (
        "import os,sys; path,displaced=sys.argv[1:3]; "
        "\ntry: os.replace(path,displaced)"
        "\nexcept OSError: raise SystemExit(0)"
        "\nopen(path,'wb').write(b'malicious')"
        "\nos.replace(displaced,path)"
        "\nraise SystemExit(9)"
    )
    read_original = (
        "import pathlib,sys; "
        "raise SystemExit(0 if pathlib.Path(sys.argv[1]).read_bytes().hex() == "
        "sys.argv[2] else 9)"
    )

    with BOOTSTRAP._bootstrap_lock_execution_lease(path, source, binding):
        BOOTSTRAP._run(
            (sys.executable, "-c", swap, str(path), str(displaced)),
            cwd=tmp_path,
            env=BOOTSTRAP._base_environment(),
        )
        BOOTSTRAP._run(
            (sys.executable, "-c", read_original, str(path), source.hex()),
            cwd=tmp_path,
            env=BOOTSTRAP._base_environment(),
        )

    assert path.read_bytes() == source
    assert not displaced.exists()


def test_bootstrap_lock_lease_detects_mutation_during_run(tmp_path: Path) -> None:
    source = b"lock-version = \"1.0\"\n"
    path, binding = BOOTSTRAP._materialize_bootstrap_lock(tmp_path, source)
    mutate_and_restore = (
        "import os,sys; path=sys.argv[1]; source=bytes.fromhex(sys.argv[2]); "
        "\ntry: handle=open(path,'r+b')"
        "\nexcept OSError: raise SystemExit(0)"
        "\nwith handle:"
        "\n handle.write(b'malicious'); handle.flush(); os.fsync(handle.fileno())"
        "\n handle.seek(0); handle.write(source); handle.truncate(); handle.flush(); "
        "os.fsync(handle.fileno())"
    )

    def run_mutation() -> None:
        with BOOTSTRAP._bootstrap_lock_execution_lease(path, source, binding):
            BOOTSTRAP._run(
                (sys.executable, "-c", mutate_and_restore, str(path), source.hex()),
                cwd=tmp_path,
                env=BOOTSTRAP._base_environment(),
            )

    if os.name == "nt":
        run_mutation()
    else:
        with pytest.raises(BOOTSTRAP._BootstrapError, match="bootstrap lock"):
            run_mutation()

    assert path.read_bytes() == source


@pytest.mark.parametrize(
    "interruption",
    (KeyboardInterrupt(), SystemExit(7)),
    ids=("keyboard-interrupt", "system-exit"),
)
def test_bootstrap_lock_lease_releases_handles_after_base_exception(
    tmp_path: Path,
    interruption: BaseException,
) -> None:
    source = b"lock-version = \"1.0\"\n"
    path, binding = BOOTSTRAP._materialize_bootstrap_lock(tmp_path, source)

    with pytest.raises(type(interruption)):
        with BOOTSTRAP._bootstrap_lock_execution_lease(path, source, binding):
            raise interruption

    displaced = tmp_path / "released-lock"
    os.replace(path, displaced)
    os.replace(displaced, path)
    assert path.read_bytes() == source


def _module_binding_paths(
    tmp_path: Path,
    source: bytes,
    loaded: bytes,
) -> tuple[Path, Path, Path]:
    repository = tmp_path / "repository"
    expected_package = repository / "src" / "hsconfig"
    expected_package.mkdir(parents=True)
    installed_package = tmp_path / "installed"
    installed_package.mkdir()
    for module_name in ("release_gate.py", "publishable_tree.py"):
        (expected_package / module_name).write_bytes(source)
        (installed_package / module_name).write_bytes(loaded)
    return (
        repository,
        installed_package / "release_gate.py",
        installed_package / "publishable_tree.py",
    )


@pytest.mark.parametrize(
    ("repository_newline", "installed_newline"),
    ((b"\n", b"\r\n"), (b"\r\n", b"\n")),
    ids=("repository-lf-wheel-crlf", "repository-crlf-wheel-lf"),
)
def test_module_binding_accepts_only_global_lf_crlf_transformation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repository_newline: bytes,
    installed_newline: bytes,
) -> None:
    logical_lines = (b"from __future__ import annotations", b"VALUE = 'same'")
    repository, installed, installed_publishable_tree = _module_binding_paths(
        tmp_path,
        repository_newline.join(logical_lines) + repository_newline,
        installed_newline.join(logical_lines) + installed_newline,
    )
    from hsconfig import release_gate as module

    monkeypatch.setattr(module, "__file__", str(installed))
    monkeypatch.setattr(
        module.publishable_tree_module,
        "__file__",
        str(installed_publishable_tree),
    )
    module._verify_module_binding(repository)


@pytest.mark.parametrize(
    ("source", "loaded"),
    (
        (b"VALUE = 1\n", b"VALUE = 2\r\n"),
        (b"VALUE = 1\nOTHER = 2\n", b"VALUE = 1\r\nOTHER = 2\n"),
        (b"VALUE = 1\n", b"VALUE = 1\r"),
        (b"VALUE = 1\n", b"VALUE = b'\xff'\n"),
        (b"VALUE = 1\r\nOTHER = 2\n", b"VALUE = 1\nOTHER = 2\n"),
        (b"VALUE = 1\r\nOTHER = 2\n", b"VALUE = 1\r\nOTHER = 2\n"),
        (b"VALUE = 1\r", b"VALUE = 1\r"),
        (b"VALUE = b'\xff'\n", b"VALUE = b'\xff'\n"),
    ),
    ids=(
        "content-change",
        "mixed-installed-newlines",
        "bare-carriage-return",
        "invalid-utf8",
        "mixed-repository-newlines",
        "identical-mixed-newlines",
        "identical-bare-carriage-return",
        "identical-invalid-utf8",
    ),
)
def test_module_binding_rejects_noncanonical_or_changed_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: bytes,
    loaded: bytes,
) -> None:
    repository, installed, installed_publishable_tree = _module_binding_paths(
        tmp_path, source, loaded
    )
    from hsconfig import release_gate as module

    monkeypatch.setattr(module, "__file__", str(installed))
    monkeypatch.setattr(
        module.publishable_tree_module,
        "__file__",
        str(installed_publishable_tree),
    )
    with pytest.raises(ReleaseGateError, match="module is not bound"):
        module._verify_module_binding(repository)


@pytest.mark.parametrize("side", ("repository", "installed"))
@pytest.mark.parametrize("kind", ("directory", "hardlink", "symlink"))
def test_module_binding_rejects_unsafe_file_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    side: str,
    kind: str,
) -> None:
    source = b"VALUE = 1\n"
    repository, installed, installed_publishable_tree = _module_binding_paths(
        tmp_path, source, source
    )
    from hsconfig import release_gate as module

    target = repository / "src" / "hsconfig" / "release_gate.py"
    if side == "installed":
        target = installed
    target.unlink()
    if kind == "directory":
        target.mkdir()
    else:
        backing = tmp_path / f"{side}-{kind}-backing.py"
        backing.write_bytes(source)
        try:
            if kind == "hardlink":
                os.link(backing, target)
            else:
                target.symlink_to(backing)
        except OSError as exc:
            pytest.skip(f"{kind} creation is unavailable: {exc}")

    monkeypatch.setattr(module, "__file__", str(installed))
    monkeypatch.setattr(
        module.publishable_tree_module,
        "__file__",
        str(installed_publishable_tree),
    )
    with pytest.raises(ReleaseGateError):
        module._verify_module_binding(repository)


@pytest.mark.parametrize(
    ("payload", "returncode", "error"),
    (
        (b'{"passed":true}\n', 0, None),
        (b'{"passed":true}\n{"passed":true}\n', 0, "invalid JSON"),
        (b"x" * (1024 * 1024 + 1), 0, "size limit"),
    ),
    ids=("single-json", "multiple-json", "oversized"),
)
def test_parent_bounds_and_validates_child_stdout_before_forwarding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    returncode: int,
    error: str | None,
) -> None:
    class Process:
        def __init__(self) -> None:
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(payload)
            self.killed = False

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return returncode

        def kill(self) -> None:
            self.killed = True

    process = Process()
    monkeypatch.setattr(BOOTSTRAP.subprocess, "Popen", lambda *_args, **_kwargs: process)

    class Lease:
        def __init__(self, _process: Process, _baseline: set[int]) -> None:
            pass

        def terminate_remaining(self) -> None:
            return None

    monkeypatch.setattr(BOOTSTRAP, "_BootstrapProcessTreeLease", Lease)

    if error is None:
        assert BOOTSTRAP._run_bound_child(
            Path(sys.executable),
            tmp_path,
            {},
            [],
            "d" * 64,
            controller_path=Path(BOOTSTRAP.__file__),
        ) == (0, {"passed": True})
    else:
        with pytest.raises(BOOTSTRAP._BootstrapError, match=error):
            BOOTSTRAP._run_bound_child(
                Path(sys.executable),
                tmp_path,
                {},
                [],
                "d" * 64,
                controller_path=Path(BOOTSTRAP.__file__),
            )


def test_bound_child_uses_safe_path_for_both_launcher_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outer_argv: tuple[str, ...] | None = None

    class Input(io.BytesIO):
        def __init__(self) -> None:
            super().__init__()
            self.payload = b""

        def close(self) -> None:
            self.payload = self.getvalue()

    class Process:
        def __init__(self) -> None:
            self.stdin = Input()
            self.stdout = io.BytesIO(b'{"passed":true}\n')

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 0

        def kill(self) -> None:
            return None

    process = Process()

    def capture_popen(argv: tuple[str, ...], **_kwargs: object) -> Process:
        nonlocal outer_argv
        outer_argv = argv
        return process

    class Lease:
        def __init__(self, _process: Process, _baseline: set[int]) -> None:
            pass

        def terminate_remaining(self) -> None:
            return None

    monkeypatch.setattr(BOOTSTRAP.subprocess, "Popen", capture_popen)
    monkeypatch.setattr(BOOTSTRAP, "_BootstrapProcessTreeLease", Lease)
    python = tmp_path / "locked-runtime" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"synthetic venv redirector")
    controller = Path(BOOTSTRAP.__file__).resolve(strict=True)

    assert BOOTSTRAP._run_bound_child(
        python,
        tmp_path,
        {},
        ["--json"],
        "d" * 64,
        controller_path=controller,
    ) == (0, {"passed": True})

    assert outer_argv == (
        _process_tree_gate_interpreter(python),
        "-I",
        "-S",
        "-B",
        "-c",
        BOOTSTRAP._GATED_CHILD_LAUNCHER,
    )
    first_line = process.stdin.payload.splitlines()[0]
    assert tuple(json.loads(first_line)) == (
        str(python),
        "-P",
        "-c",
        BOOTSTRAP._VERIFIED_CONTROLLER_LAUNCHER,
        str(controller),
        "--json",
    )


@pytest.mark.parametrize("injection", ("construct", "start"))
def test_bootstrap_thread_setup_failure_closes_tree_pipes_and_reaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    injection: str,
) -> None:
    events: list[str] = []

    class Process:
        def __init__(self) -> None:
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(b'{"passed":true}\n')
            self.returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def kill(self) -> None:
            events.append("kill")
            self.returncode = -9

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            events.append("wait")
            return self.returncode or 0

    process = Process()

    class Lease:
        def __init__(self, leased: Process, _baseline: set[int]) -> None:
            self.process = leased

        def terminate_remaining(self) -> None:
            events.append("lease")
            self.process.kill()
            self.process.wait(timeout=30)

    class StartFailure:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def start(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(BOOTSTRAP.subprocess, "Popen", lambda *_a, **_k: process)
    monkeypatch.setattr(BOOTSTRAP, "_BootstrapProcessTreeLease", Lease)
    if injection == "construct":
        monkeypatch.setattr(
            BOOTSTRAP.threading,
            "Thread",
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("thread construct")),
        )
        expected: type[BaseException] = RuntimeError
    else:
        monkeypatch.setattr(BOOTSTRAP.threading, "Thread", StartFailure)
        expected = KeyboardInterrupt

    with pytest.raises(expected):
        BOOTSTRAP._run_bound_child(
            Path(sys.executable),
            tmp_path,
            {},
            [],
            "a" * 64,
            controller_path=Path(BOOTSTRAP.__file__),
        )

    assert events == ["lease", "kill", "wait"]
    assert process.stdin.closed is True
    assert process.stdout.closed is True
    assert not (tmp_path / "descendant-survived.txt").exists()


@pytest.mark.parametrize("injection", ("bytearray", "event"))
def test_bootstrap_state_setup_baseexception_after_popen_closes_tree_and_pipes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    injection: str,
) -> None:
    events: list[str] = []

    class Process:
        def __init__(self) -> None:
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def kill(self) -> None:
            events.append("kill")
            self.returncode = -9

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            events.append("wait")
            return self.returncode or 0

    process = Process()

    class Lease:
        def __init__(self, leased: Process, _baseline: set[int]) -> None:
            events.append("lease_init")
            self.process = leased

        def terminate_remaining(self) -> None:
            events.append("lease")
            self.process.kill()
            self.process.wait(timeout=30)

    monkeypatch.setattr(BOOTSTRAP.subprocess, "Popen", lambda *_a, **_k: process)
    monkeypatch.setattr(BOOTSTRAP, "_BootstrapProcessTreeLease", Lease)
    if injection == "bytearray":
        monkeypatch.setattr(
            BOOTSTRAP,
            "bytearray",
            lambda: (_ for _ in ()).throw(MemoryError("state allocation")),
            raising=False,
        )
        expected: type[BaseException] = MemoryError
    else:
        monkeypatch.setattr(
            BOOTSTRAP,
            "threading",
            type(
                "Threading",
                (),
                {
                    "Event": staticmethod(
                        lambda: (_ for _ in ()).throw(
                            KeyboardInterrupt("event allocation")
                        )
                    )
                },
            )(),
        )
        expected = KeyboardInterrupt

    with pytest.raises(expected):
        BOOTSTRAP._run_bound_child(
            Path(sys.executable),
            tmp_path,
            {},
            [],
            "c" * 64,
            controller_path=Path(BOOTSTRAP.__file__),
        )

    assert events == ["lease_init", "lease", "kill", "wait"]
    assert process.stdin.closed is True
    assert process.stdout.closed is True
    assert not (tmp_path / "state-descendant-survived.txt").exists()


def test_bootstrap_reader_error_after_valid_json_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingReader(io.BytesIO):
        def __init__(self) -> None:
            super().__init__(b"")
            self.calls = 0

        def read(self, _size: int = -1) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return b'{"passed":true}\n'
            raise OSError("injected read failure")

    class Process:
        def __init__(self) -> None:
            self.stdin = io.BytesIO()
            self.stdout = FailingReader()
            self.returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def kill(self) -> None:
            self.returncode = -9

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return 0 if self.returncode is None else self.returncode

    class Lease:
        def __init__(self, process: Process, _baseline: set[int]) -> None:
            self.process = process

        def terminate_remaining(self) -> None:
            self.process.kill()
            self.process.wait(timeout=30)

    process = Process()
    monkeypatch.setattr(BOOTSTRAP.subprocess, "Popen", lambda *_a, **_k: process)
    monkeypatch.setattr(BOOTSTRAP, "_BootstrapProcessTreeLease", Lease)

    with pytest.raises(BOOTSTRAP._BootstrapError, match="stdout read failed"):
        BOOTSTRAP._run_bound_child(
            Path(sys.executable),
            tmp_path,
            {},
            [],
            "b" * 64,
            controller_path=Path(BOOTSTRAP.__file__),
        )

    assert process.stdin.closed is True
    assert process.stdout.closed is True


def test_bootstrap_reader_error_emits_cause_faithful_failure_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        BOOTSTRAP,
        "_bootstrap_and_reexec",
        lambda *_args: (_ for _ in ()).throw(
            BOOTSTRAP._BootstrapError("release gate child stdout read failed")
        ),
    )

    assert BOOTSTRAP.main(
        ["--repo", str(ROOT), "--outputs", str(ROOT / "outputs"), "--json"]
    ) == 2
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["errors"] == [
        "release gate child stdout read failed"
    ]


@pytest.mark.skipif(os.name != "nt", reason="Windows job creation semantics")
def test_windows_job_creation_failure_kills_waits_and_closes_launcher_pipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes

    events: list[str] = []

    class Function:
        def __init__(self, result: int) -> None:
            self.result = result
            self.argtypes: object = None
            self.restype: object = None

        def __call__(self, *_args: object) -> int:
            return self.result

    class Kernel:
        CreateJobObjectW = Function(0)
        SetInformationJobObject = Function(0)
        AssignProcessToJobObject = Function(0)
        CloseHandle = Function(1)

    class Process:
        _handle = 123

        def __init__(self) -> None:
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()
            self.returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def kill(self) -> None:
            events.append("kill")
            self.returncode = -9

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            events.append("wait")
            return self.returncode or 0

    process = Process()
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_a, **_k: Kernel())

    with pytest.raises(BOOTSTRAP._BootstrapError, match="isolation"):
        BOOTSTRAP._BootstrapProcessTreeLease(process, set())

    assert events == ["kill", "wait"]
    assert process.stdin.closed is True
    assert process.stdout.closed is True
    assert process.stderr.closed is True


@pytest.mark.parametrize("failure_mode", ("timeout", "oversize"))
def test_bootstrap_parent_failure_terminates_stubborn_descendant_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    marker = tmp_path / f"{failure_mode}-descendant-survived.txt"
    child_script = tmp_path / "bound-child.py"
    descendant = (
        "import time; from pathlib import Path; time.sleep(2); "
        f"Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
    )
    child_script.write_text(
        "import os,subprocess,sys,time\n"
        f"descendant = {descendant!r}\n"
        "options = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} "
        "if os.name == 'nt' else {'start_new_session': True})\n"
        "subprocess.Popen([sys.executable, '-c', descendant], **options)\n"
        "if os.environ['FAILURE_MODE'] == 'oversize':\n"
        "    os.write(1, b'x' * (1024 * 1024 + 1))\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(BOOTSTRAP, "__file__", str(child_script))
    environment = os.environ.copy()
    environment["FAILURE_MODE"] = failure_mode

    with pytest.raises(BOOTSTRAP._BootstrapError, match="timed out|size limit"):
        BOOTSTRAP._run_bound_child(
            Path(sys.executable),
            tmp_path,
            environment,
            [],
            "f" * 64,
            timeout=1,
            controller_path=child_script,
        )
    time.sleep(3)

    assert not marker.exists()


def test_parent_completes_bootstrap_cleanup_before_returning_child_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    root = tmp_path / "bootstrap"
    root.mkdir()
    manifest = root / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    python = root / "environment" / "Scripts" / "python.exe"
    args = BOOTSTRAP._parser().parse_args(
        ["--repo", str(ROOT), "--outputs", str(ROOT / "outputs"), "--json"]
    )
    monkeypatch.setattr(BOOTSTRAP.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(BOOTSTRAP.tempfile, "mkdtemp", lambda **_kwargs: str(root))
    monkeypatch.setattr(
        BOOTSTRAP,
        "_bootstrap_environment",
        lambda repository, bootstrap: BOOTSTRAP._RuntimeBootstrapBinding(
            python=python,
            manifest_path=manifest,
            manifest_sha256=hashlib.sha256(b"{}").hexdigest(),
            sentinel="e" * 64,
        ),
    )
    monkeypatch.setattr(BOOTSTRAP, "_read_bound", lambda *_args, **_kwargs: b"{}")
    monkeypatch.setattr(
        BOOTSTRAP,
        "_run_bound_child",
        lambda *_args, **_kwargs: (events.append("child") or (0, {"passed": True})),
    )
    monkeypatch.setattr(
        BOOTSTRAP,
        "_cleanup_bootstrap_root",
        lambda *_args: events.append("cleanup"),
    )

    result = BOOTSTRAP._bootstrap_and_reexec(args, [])
    events.append("returned")

    assert result == (0, {"passed": True})
    assert events == ["child", "cleanup", "returned"]


@pytest.mark.parametrize(
    "stdout,returncode",
    [
        ('{"passed":false}', 0),
        ('{"passed":true}', 7),
        ('{"passed":true,"passed":false}', 0),
    ],
)
def test_safe_detail_rejects_duplicate_or_exit_contradicting_json(
    stdout: str, returncode: int
) -> None:
    with pytest.raises(ReleaseGateError, match="JSON|passed|return"):
        _safe_detail(stdout, "", returncode)


@pytest.mark.parametrize(
    ("stdout", "returncode"),
    [
        ('{"passed":true,"returncode":1}', 0),
        ('{"passed":false,"returncode":2}', 1),
        ('{"passed":false,"returncode":true}', 1),
        ('{"returncode":1}', 0),
    ],
)
def test_safe_detail_rejects_nested_returncode_contradictions(
    stdout: str, returncode: int
) -> None:
    with pytest.raises(ReleaseGateError, match="returncode"):
        _safe_detail(stdout, "", returncode)


@pytest.mark.parametrize("tree_mode", ("working-pre-cutover", "candidate"))
def test_real_pre_cutover_near100_subprocess_is_a_reachable_local_gate(
    tmp_path: Path,
    tree_mode: str,
) -> None:
    repository, outputs = _repository(tmp_path)
    script = repository / "scripts" / "check_near100_scorecard.py"
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "check_near100_scorecard.py", script)
    shutil.copytree(
        ROOT / "src" / "hsconfig",
        repository / "src" / "hsconfig",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "install real near100 cli")
    snapshot = _capture_snapshot(repository, outputs)
    checks = tuple(
        ReleaseCheck(name, True, (name,), {"returncode": 0})
        for name in CHECK_NAMES[:-1]
    )
    bundle = _build_base_evidence(
        repository=repository,
        outputs_root=outputs,
        checks=checks,
        tree_mode=tree_mode,
        snapshot=snapshot,
    )
    spec = _command_specs(repository, outputs, tree_mode)[-1]

    result = _run_one(
        spec,
        repository=repository,
        stdin_data=(
            json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n"
        ),
    )

    assert "--mode" in spec.command
    assert spec.command[spec.command.index("--mode") + 1] == "pre_cutover"
    assert result.passed is True
    assert result.details["returncode"] == 0
    assert result.details["result"]["passed"] is False
    assert result.details["result"]["open_p0_findings"] == 0
    assert result.details["result"]["open_p1_findings"] == 0


@pytest.mark.parametrize(
    "mutation",
    ("local_metric_failed", "github_passed", "open_p0", "wrong_metric_set"),
)
def test_pre_cutover_exit_zero_exception_validates_all_allowed_local_state(
    mutation: str,
) -> None:
    metric_ids = (
        "static_contract_safety",
        "safe_visionai_lowering",
        "testability_and_assurance",
        "semantic_disposition_closure",
        "layered_pre_run_source_coverage",
        "architecture_and_maintainability",
        "slimness_and_coherence",
        "github_repository_polish",
        "workspace_hygiene",
        "overall_pre_run",
        "gameplay_quality",
    )
    document = {
        "schema_version": 1,
        "version": "1.0.0",
        "metrics": [
            {
                "metric_id": metric_id,
                "status": (
                    "pending_remote"
                    if metric_id == "github_repository_polish"
                    else "not_applicable"
                    if metric_id == "gameplay_quality"
                    else "pass"
                ),
            }
            for metric_id in metric_ids
        ],
        "open_p0_findings": 0,
        "open_p1_findings": 0,
        "overall_score": "100",
        "passed": False,
    }
    if mutation == "local_metric_failed":
        document["metrics"][0]["status"] = "fail"
    elif mutation == "github_passed":
        document["metrics"][7]["status"] = "pass"
    elif mutation == "open_p0":
        document["open_p0_findings"] = 1
    else:
        document["metrics"].pop()

    with pytest.raises(ReleaseGateError, match="pre.cutover|passed|metric|finding"):
        _safe_detail(
            json.dumps(document),
            "",
            0,
            allow_pre_cutover_local=True,
        )


def test_timeout_terminates_descendant_process_tree(tmp_path: Path) -> None:
    marker = tmp_path / "descendant-survived.txt"
    child = (
        "import time; from pathlib import Path; time.sleep(2); "
        f"Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(30)"
    )

    with pytest.raises(subprocess.TimeoutExpired):
        _execute_bounded(
            (sys.executable, "-c", parent),
            cwd=tmp_path,
            env=_controlled_environment(ROOT),
            timeout=1,
        )
    time.sleep(3)

    assert not marker.exists()


@pytest.mark.parametrize("exception_type", (KeyboardInterrupt, SystemExit))
def test_baseexception_terminates_real_descendant_closes_pipes_and_reraises_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[BaseException],
) -> None:
    marker = tmp_path / "baseexception-descendant-survived.txt"
    ready = tmp_path / "parent-ready.txt"
    child = (
        "import time; from pathlib import Path; time.sleep(2); "
        f"Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
    )
    parent = (
        "import subprocess,sys,time; from pathlib import Path; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
        f"Path({str(ready)!r}).write_text('ready', encoding='utf-8'); time.sleep(5)"
    )
    real_popen = subprocess.Popen
    injected = exception_type("injected process wait interruption")
    launched: list[Any] = []

    class InterruptingProcess:
        def __init__(self, process: Any) -> None:
            self._process = process
            self._handle = process._handle
            self.pid = process.pid
            self.stdin = process.stdin
            self.stdout = process.stdout
            self.stderr = process.stderr
            self._interrupted = False

        def poll(self) -> int | None:
            return self._process.poll()

        def kill(self) -> None:
            self._process.kill()

        def wait(self, timeout: float | None = None) -> int:
            if not self._interrupted:
                deadline = time.monotonic() + 3
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self._interrupted = True
                raise injected
            return self._process.wait(timeout=timeout)

    def launch(*args: Any, **kwargs: Any) -> InterruptingProcess:
        command = args[0] if args else kwargs.get("args")
        if command and Path(command[0]).resolve() == Path(
            _process_tree_gate_interpreter(sys.executable)
        ).resolve():
            wrapped = InterruptingProcess(real_popen(*args, **kwargs))
            launched.append(wrapped)
            return wrapped
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", launch)

    with pytest.raises(exception_type) as captured:
        _execute_bounded(
            (sys.executable, "-c", parent),
            cwd=tmp_path,
            env=_controlled_environment(ROOT),
            timeout=30,
            stdin_data=b"bounded input\n",
        )
    time.sleep(3)

    assert captured.value is injected
    assert len(launched) == 1
    assert launched[0].poll() is not None
    assert launched[0].stdin is not None and launched[0].stdin.closed
    assert launched[0].stdout is not None and launched[0].stdout.closed
    assert launched[0].stderr is not None and launched[0].stderr.closed
    assert not marker.exists()


def test_baseexception_during_pipe_setup_terminates_and_closes_deterministic_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    injected = KeyboardInterrupt("injected drain-thread startup interruption")

    class DeterministicProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()
            self.terminated = False

        def poll(self) -> int | None:
            return -9 if self.terminated else None

        def kill(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> int:
            return -9 if self.terminated else 0

    process = DeterministicProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)

    class FakeLease:
        def __init__(self, candidate: Any, baseline: set[int]) -> None:
            assert candidate is process
            del baseline

        def terminate_remaining(self) -> None:
            process.kill()

    monkeypatch.setattr("hsconfig.release_gate._ProcessTreeLease", FakeLease)
    original_start = threading.Thread.start
    attempts = 0

    def interrupt_first_start(thread: threading.Thread) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise injected
        original_start(thread)

    monkeypatch.setattr(threading.Thread, "start", interrupt_first_start)

    with pytest.raises(KeyboardInterrupt) as captured:
        _execute_bounded_process(
            (sys.executable, "-c", "pass"),
            cwd=tmp_path,
            env=_controlled_environment(ROOT),
            timeout=30,
            stdin_data=b"input\n",
        )

    assert captured.value is injected
    assert process.terminated is True
    assert process.stdin.closed
    assert process.stdout.closed
    assert process.stderr.closed


def test_thread_constructor_baseexception_terminates_real_child_before_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "thread-constructor-child-survived.txt"
    child = (
        "import time; from pathlib import Path; time.sleep(1); "
        f"Path({str(marker)!r}).write_text('survived', encoding='utf-8'); time.sleep(30)"
    )
    real_popen = subprocess.Popen
    launched: list[Any] = []
    injected = KeyboardInterrupt("injected thread constructor interruption")

    def launch(*args: Any, **kwargs: Any) -> Any:
        process = real_popen(*args, **kwargs)
        command = args[0] if args else kwargs.get("args")
        if command and Path(command[0]).resolve() == Path(
            _process_tree_gate_interpreter(sys.executable)
        ).resolve():
            launched.append(process)
        return process

    def interrupt_thread_construction(*_args: Any, **_kwargs: Any) -> Any:
        raise injected

    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(threading, "Thread", interrupt_thread_construction)
    try:
        with pytest.raises(KeyboardInterrupt) as captured:
            _execute_bounded_process(
                (sys.executable, "-c", child),
                cwd=tmp_path,
                env=_controlled_environment(ROOT),
                timeout=30,
            )
        time.sleep(2)
        child_still_running = launched[0].poll() is None
        streams_closed = all(
            stream is not None and stream.closed
            for stream in (launched[0].stdout, launched[0].stderr)
        )
    finally:
        for process in launched:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()

    assert captured.value is injected
    assert len(launched) == 1
    assert child_still_running is False
    assert streams_closed is True
    assert not marker.exists()


def test_dirty_repository_is_refused_before_any_gate_runs(tmp_path: Path) -> None:
    repository, outputs = _repository(tmp_path)
    (repository / "dirty.txt").write_text("dirty", encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="dirty"):
        run_release_gate(
            repository=repository,
            outputs_root=outputs,
            tree_mode="working-pre-cutover",
        )


def test_dirty_fingerprint_rejects_untracked_symlink_before_reading(
    tmp_path: Path,
) -> None:
    repository, _outputs = _repository(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        (repository / "untracked-link.txt").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"platform does not permit test symlink: {exc}")

    with pytest.raises(ReleaseGateError, match="untracked.*link|link.*untracked"):
        _dirty_tree_fingerprint(repository)


def test_full_outputs_snapshot_changes_for_unexpected_benign_addition(tmp_path: Path) -> None:
    repository, outputs = _repository(tmp_path)
    snapshot = _capture_snapshot(repository, outputs)
    (outputs / "ShadowPriest" / "benign-note.txt").write_text("note", encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="outputs changed"):
        _assert_snapshot_unchanged(repository, outputs, snapshot)


def test_outputs_root_rejects_any_non_deck_entry(tmp_path: Path) -> None:
    repository, outputs = _repository(tmp_path)
    (outputs / "receipt.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="unexpected outputs root entry"):
        _capture_snapshot(repository, outputs)


def test_candidate_requires_detached_head_but_no_output_root_receipt(tmp_path: Path) -> None:
    owner, outputs = _repository(tmp_path)
    exclude = owner / ".git" / "info" / "exclude"
    exclude.write_text(exclude.read_text(encoding="utf-8") + "\n/.cutover-candidate/\n", encoding="utf-8")
    candidate = owner / ".cutover-candidate" / "candidate"
    temporary_candidate = tmp_path / "candidate-clone"
    _git(
        owner,
        "-c",
        "core.autocrlf=false",
        "clone",
        "-q",
        "--no-checkout",
        str(owner),
        str(temporary_candidate),
    )
    candidate.parent.mkdir()
    temporary_candidate.rename(candidate)
    _git(candidate, "config", "core.autocrlf", "false")
    _git(candidate, "config", "core.longpaths", "true")
    _git(candidate, "remote", "set-url", "origin", "https://github.com/Teufelsboy/HSConfig.git")

    with pytest.raises(ReleaseGateError, match="owner"):
        run_release_gate(repository=candidate, outputs_root=outputs, tree_mode="candidate")

    _git(candidate, "checkout", "--detach", "-q", "HEAD")
    assert _git(candidate, "status", "--porcelain=v1", "--untracked-files=all") == ""

    root, verified_outputs, oid = _validate_repository(
        candidate,
        outputs,
        "candidate",
        owner_repository=owner,
    )

    assert root == candidate.resolve()
    assert verified_outputs == outputs.resolve()
    assert oid == _git(candidate, "rev-parse", "HEAD")
    assert {path.name for path in outputs.iterdir()} == {
        row["deck_name"]
        for row in json.loads(
            (candidate / "docs/operator/audited-deck-catalog.json").read_text(
                encoding="utf-8"
            )
        )["decks"]
    }


def test_gate_revalidates_repository_and_outputs_before_terminal_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    calls = 0

    def runner(spec: Any, *, repository: Path) -> ReleaseCheck:
        nonlocal calls
        calls += 1
        if calls == 1:
            (repository / "changed-during-gate.txt").write_text("changed", encoding="utf-8")
        return ReleaseCheck(spec.name, True, spec.command, {"returncode": 0})

    monkeypatch.setattr("hsconfig.release_gate._run_one", runner)

    with pytest.raises(ReleaseGateError, match="changed during release gate"):
        run_release_gate(
            repository=repository,
            outputs_root=outputs,
            tree_mode="working-pre-cutover",
        )


def test_pre_cutover_derives_semantic_and_findings_authority_without_manual_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)

    def runner(
        spec: Any, *, repository: Path, stdin_data: bytes | None = None
    ) -> ReleaseCheck:
        if spec.name == "near100_scorecard":
            assert stdin_data is not None
            bundle = json.loads(stdin_data)
            scorecard = build_near100_scorecard(
                evidence=bundle["evidence"],
                mode="pre_cutover",
                receipt_documents=bundle["receipts"],
            )
            local_passed = all(
                metric.status in {"pass", "pending_remote", "not_applicable"}
                for metric in scorecard.metrics
            )
            return ReleaseCheck(
                spec.name,
                local_passed,
                spec.command,
                {"returncode": 0 if local_passed else 1},
            )
        return ReleaseCheck(spec.name, True, spec.command, {"returncode": 0})

    monkeypatch.setattr(
        "hsconfig.release_gate._run_one",
        runner,
    )

    result = run_release_gate(repository=repository, outputs_root=outputs, tree_mode="working-pre-cutover")

    assert result.passed is True
    assert result.final_release_ready is False
    assert not (repository / ".git" / "hsconfig-release-gate").exists()
    assert all(path.is_dir() for path in outputs.iterdir())


def test_semantic_reports_reject_duplicate_rows_and_wrong_audit_deck(
    tmp_path: Path,
) -> None:
    repository, outputs = _repository(tmp_path)
    deck = json.loads(
        (repository / "tests/fixtures/near100/current_semantic_inventory.json").read_text(
            encoding="utf-8"
        )
    )["decks"][0]
    reports = (
        outputs
        / deck["deck_name"]
        / "revisions"
        / ("sha256-" + "a" * 64)
        / "04_package"
        / "reports"
    )
    ledger_path = reports / "disposition_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["cards"].append(dict(ledger["cards"][0]))
    ledger_path.write_text(json.dumps(ledger, sort_keys=True), encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="row count"):
        _produce_semantic_rows(repository, outputs, ".git/evidence.json")

    ledger["cards"].pop()
    ledger_path.write_text(json.dumps(ledger, sort_keys=True), encoding="utf-8")
    audit_path = reports / "source_contract_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["deck_name"] = "wrong-deck"
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="audit deck binding"):
        _produce_semantic_rows(repository, outputs, ".git/evidence.json")


def test_actual_outputs_group_all_claim_occurrences_into_canonical_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_outputs = (ROOT / "outputs").resolve()
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    def reject_root_outputs_read(path: Path) -> None:
        resolved = path.resolve()
        if resolved == root_outputs or root_outputs in resolved.parents:
            raise AssertionError(f"release-gate tests read ignored outputs: {resolved}")

    def guarded_read_bytes(path: Path) -> bytes:
        reject_root_outputs_read(path)
        return original_read_bytes(path)

    def guarded_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        reject_root_outputs_read(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    repository, outputs = _repository(tmp_path)
    rows = _produce_semantic_rows(repository, outputs, ".git/evidence.json")
    inventory = json.loads(
        (ROOT / "tests/fixtures/near100/current_semantic_inventory.json").read_text(
            encoding="utf-8"
        )
    )

    assert len(rows["card_module_rows"]) == 208
    assert len(rows["claim_rows"]) == 316
    assert {row["obligation_id"] for row in rows["claim_rows"]} == {
        row["claim_key"] for row in inventory["semantic_claims"]
    }
    assert all(len(row["obligation_id"]) == 64 for row in rows["claim_rows"])
    assert {
        lane: sum(row["authority_lanes"] == [lane] for row in rows["claim_rows"])
        for lane in ("A", "B", "C", "D", "E")
    } == {"A": 267, "B": 0, "C": 49, "D": 0, "E": 0}


def test_lane_b_requires_live_verified_exact_deck_authority_and_lane_e_requires_bot() -> None:
    fingerprint = "a" * 64
    base = {
        "claim_kind": "targeting_rule",
        "claim_readiness": "guide_backed",
        "source_lane": "deck_matched_public_guide",
        "policy_lane": "runtime_lowerable",
        "trust_ceiling": "guide",
        "source_type": "public_guide",
        "lane": "runtime_lowered",
        "strategic_receipt_verified": True,
        "evidence_lane_error": None,
        "evidence_authority": {
            "as_of_date": "2026-08-04",
            "authority_id": "B:claim_0123456789ab",
            "claim_kind": "targeting_rule",
            "content_sha256": "sha256:" + "b" * 64,
            "exact_deck_fingerprint": fingerprint,
            "lane": "B",
            "reason": "live_verified_exact_deck_guide",
            "runtime_authorized": True,
            "source_identity": "public-guide:verified",
        },
    }
    lifecycle = {
        "builder_or_router_decision": "emitted",
        "emitted_files": ["CARD_001.json"],
        "runtime_surface": "CARD_001.json",
        "final_runtime_effect": "emitted_runtime_row",
    }
    assert (
        _claim_authority_lane(
            base,
            "runtime_emitted",
            deck_fingerprint=fingerprint,
            lifecycle=lifecycle,
        )
        == "B"
    )
    wrong = json.loads(json.dumps(base))
    wrong["evidence_authority"]["exact_deck_fingerprint"] = "c" * 64
    with pytest.raises(ReleaseGateError, match="authority evidence"):
        _claim_authority_lane(
            wrong,
            "runtime_emitted",
            deck_fingerprint=fingerprint,
            lifecycle=lifecycle,
        )

    legacy_context = dict(base)
    legacy_context.update(
        {
            "claim_readiness": "explicit_low_confidence",
            "source_lane": "",
            "policy_lane": "suppressed_or_conditional",
            "trust_ceiling": "report_only",
            "lane": "report_only",
            "strategic_receipt_verified": False,
            "evidence_lane_error": "evidence_lane_unclassified",
            "evidence_authority": None,
        }
    )
    no_runtime = {
        "builder_or_router_decision": "suppressed",
        "emitted_files": [],
        "runtime_surface": None,
        "final_runtime_effect": "suppressed_runtime_claim",
    }
    assert (
        _claim_authority_lane(
            legacy_context,
            "suppressed_insufficient_authority",
            deck_fingerprint=fingerprint,
            lifecycle=no_runtime,
        )
        == "C"
    )
    bot_lifecycle = dict(no_runtime)
    bot_lifecycle.update(
        {
            "builder_or_router_decision": "bot_delegated",
            "final_runtime_effect": "delegated_to_bot",
            "runtime_eligibility": "report_only",
            "surface_gate_decision": "rejected",
            "surface_gate_reason": "bot_delegated",
            "suppressed_reason": "bot_delegated",
        }
    )
    assert (
        _claim_authority_lane(
            legacy_context,
            "bot_delegated",
            deck_fingerprint=fingerprint,
            lifecycle=bot_lifecycle,
        )
        == "E"
    )


def test_semantic_reports_reject_source_payload_mismatch_after_grouping(
    tmp_path: Path,
) -> None:
    repository, outputs = _repository(tmp_path)
    deck = next(iter(outputs.iterdir()))
    current = json.loads((deck / "current.json").read_text(encoding="utf-8"))
    audit_path = (
        deck
        / current["revision"]
        / "04_package"
        / "reports"
        / "source_contract_audit.json"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    first = next(iter(audit["claim_rows"].values()))
    first["evidence_text_short"] += " changed"
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="identities do not match"):
        _produce_semantic_rows(repository, outputs, ".git/evidence.json")


def test_semantic_producer_binds_approved_inventory_checksum_and_catalog_order(
    tmp_path: Path,
) -> None:
    repository, outputs = _repository(tmp_path)
    inventory_path = repository / "tests/fixtures/near100/current_semantic_inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["canonical_content_sha256"] = "0" * 64
    inventory_path.write_text(json.dumps(inventory, sort_keys=True), encoding="utf-8")
    with pytest.raises(ReleaseGateError, match="canonical semantic inventory"):
        _produce_semantic_rows(repository, outputs, ".git/evidence.json")

    inventory = json.loads(
        (ROOT / "tests/fixtures/near100/current_semantic_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    changed = dict(inventory["semantic_claims"][0])
    changed["source_title"] += " substituted"
    changed.pop("claim_key")
    inventory["semantic_claims"][0] = canonical_semantic_claim(changed)
    _rehash_inventory(inventory)
    inventory_path.write_text(json.dumps(inventory, sort_keys=True), encoding="utf-8")
    with pytest.raises(ReleaseGateError, match="canonical semantic inventory"):
        _produce_semantic_rows(repository, outputs, ".git/evidence.json")

    inventory_path.write_bytes(
        (ROOT / "tests/fixtures/near100/current_semantic_inventory.json").read_bytes()
    )
    catalog_path = repository / "docs/operator/audited-deck-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["decks"][0], catalog["decks"][1] = catalog["decks"][1], catalog["decks"][0]
    catalog_path.write_text(json.dumps(catalog, sort_keys=True), encoding="utf-8")
    with pytest.raises(ReleaseGateError, match="canonical semantic inventory"):
        _produce_semantic_rows(repository, outputs, ".git/evidence.json")


@pytest.mark.parametrize(
    "mutation", ["unknown_readiness", "bot_delegation_without_lifecycle"]
)
def test_semantic_authority_is_closed_and_disposition_compatible(
    tmp_path: Path, mutation: str
) -> None:
    repository, outputs = _repository(tmp_path)
    audit_path = _first_report(repository, outputs, "source_contract_audit.json")
    ledger_path = _first_report(repository, outputs, "disposition_ledger.json")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if mutation == "unknown_readiness":
        first = next(iter(audit["claim_rows"].values()))
        first["claim_readiness"] = "future_unclassified"
    else:
        target = next(iter(audit["claim_rows"].values()))
        target.update(
            {
                "claim_readiness": "explicit_low_confidence",
                "source_lane": "",
                "evidence_authority": None,
                "evidence_lane_error": "evidence_lane_unclassified",
                "trust_ceiling": "report_only",
                "source_type": "",
            }
        )
        next(row for row in ledger["claims"] if row["claim_id"] == target["claim_id"])[
            "disposition"
        ] = "bot_delegated"
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")
    ledger_path.write_text(json.dumps(ledger, sort_keys=True), encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="authority|disposition|scalar"):
        _produce_semantic_rows(repository, outputs, ".git/evidence.json")


@pytest.mark.parametrize("mutation", ["summary", "lifecycle", "nested"])
def test_semantic_source_report_nested_contract_is_closed(
    tmp_path: Path, mutation: str
) -> None:
    repository, outputs = _repository(tmp_path)
    audit_path = _first_report(repository, outputs, "source_contract_audit.json")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if mutation == "summary":
        audit["summary"]["claims_total"] = -999
    elif mutation == "lifecycle":
        audit["claim_lifecycle_rows"][0]["claim_id"] = "claim_unbound"
    else:
        next(iter(audit["claim_rows"].values()))["surfaces"]["unexpected"] = True
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="summary|lifecycle|schema|binding"):
        _produce_semantic_rows(repository, outputs, ".git/evidence.json")


@pytest.mark.parametrize(
    "section,field,value",
    (
        ("claim", "first_reason", {"invented": True}),
        ("claim", "source_type", 1),
        ("claim", "claim_readiness", "future_readiness"),
        ("claim", "policy_lane", {"lane": "runtime_lowerable"}),
        ("surface", "reason", "future_surface_reason"),
        ("lifecycle", "builder_or_router_decision", "future_builder"),
        ("lifecycle", "runtime_eligibility", {"eligible": True}),
        ("lifecycle", "surface_gate_decision", 1),
        ("lifecycle", "quarantine_status", "future_quarantine"),
        ("lifecycle", "operator_impact", {"impact": "diagnostic_only"}),
        ("lifecycle", "final_runtime_effect", 0),
        ("lifecycle", "suppressed_reason", "future_reason"),
        ("lifecycle", "runtime_surface", {"file": "CARD.json"}),
        ("card", "deck_zone", "future_zone"),
        ("card", "first_missing_link", {"missing": "none"}),
    ),
)
def test_semantic_source_report_rejects_invented_or_wrongly_typed_nested_scalars(
    tmp_path: Path,
    section: str,
    field: str,
    value: Any,
) -> None:
    repository, outputs = _repository(tmp_path)
    audit_path = _first_report(repository, outputs, "source_contract_audit.json")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if section == "claim":
        next(iter(audit["claim_rows"].values()))[field] = value
    elif section == "surface":
        next(iter(audit["claim_rows"].values()))["surfaces"]["cardid"][field] = value
    elif section == "lifecycle":
        audit["claim_lifecycle_rows"][0][field] = value
        if field == "builder_or_router_decision":
            audit["summary"]["claim_lifecycle_decision_counts"] = {
                row["builder_or_router_decision"]: sum(
                    candidate["builder_or_router_decision"]
                    == row["builder_or_router_decision"]
                    for candidate in audit["claim_lifecycle_rows"]
                )
                for row in audit["claim_lifecycle_rows"]
            }
    else:
        next(iter(audit["card_rows"].values()))[field] = value
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="scalar|surface|lifecycle|binding"):
        _produce_semantic_rows(repository, outputs, ".git/evidence.json")


def test_final_uses_live_transaction_bound_github_state_without_caller_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    observed: dict[str, Any] = {"live_calls": 0}

    def live_state(*_: Any, **__: Any) -> dict[str, Any]:
        observed["live_calls"] += 1
        return {
            "schema_version": 1,
            "repository": "Teufelsboy/HSConfig",
            "commit_oid": _git(repository, "rev-parse", "HEAD"),
            "tree_oid": _git(repository, "rev-parse", "HEAD^{tree}"),
            "release_tag": "v1.0.0",
            "settings": {
                "full_name": "Teufelsboy/HSConfig",
                "default_branch": "main",
                "archived": False,
                "disabled": False,
                "visibility": "public",
                "has_issues": True,
                "has_projects": False,
                "has_wiki": False,
                "has_discussions": False,
                "allow_squash_merge": True,
                "allow_merge_commit": False,
                "allow_rebase_merge": False,
                "allow_auto_merge": False,
                "delete_branch_on_merge": True,
            },
            "ruleset": {
                "id": 77,
                "name": "main-linear-signed",
                "target": "branch",
                "enforcement": "active",
                "bypass_actors": [],
                "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
                "rules": [
                    {"type": "deletion"},
                    {"type": "non_fast_forward"},
                    {"type": "required_linear_history"},
                    {"type": "required_signatures"},
                ],
            },
            "tag": {"ref_object_oid": "c" * 40, "object_type": "commit", "peeled_commit_oid": _git(repository, "rev-parse", "HEAD")},
            "release": {
                "id": 88,
                "html_url": "https://github.com/Teufelsboy/HSConfig/releases/tag/v1.0.0",
                "tag_name": "v1.0.0",
                "target_commitish": _git(repository, "rev-parse", "HEAD"),
                "draft": False,
                "prerelease": False,
                "assets": [],
            },
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "transaction_id": "a" * 32,
        }

    monkeypatch.setattr("hsconfig.release_gate._collect_live_github_state", live_state)

    def runner(
        spec: Any, *, repository: Path, stdin_data: bytes | None = None
    ) -> ReleaseCheck:
        if spec.name == "near100_scorecard":
            assert stdin_data is not None
            bundle = json.loads(stdin_data)
            evidence = bundle["evidence"]
            observed.update(evidence)
            observed["receipts"] = bundle["receipts"]
            scorecard = build_near100_scorecard(
                evidence=evidence,
                mode="final",
                receipt_documents=bundle["receipts"],
            )
            return ReleaseCheck(spec.name, scorecard.passed, spec.command, {"returncode": 0})
        return ReleaseCheck(spec.name, True, spec.command, {"returncode": 0})

    monkeypatch.setattr("hsconfig.release_gate._run_one", runner)

    result = run_release_gate(
        repository=repository,
        outputs_root=outputs,
        tree_mode="final",
    )

    assert result.final_release_ready is True
    assert observed["live_calls"] == 1
    assert observed["findings"] == {"open_p0": 0, "open_p1": 0}
    for receipt_id, receipt in observed["receipts"].items():
        assert receipt["schema_version"] == 2
        assert set(receipt["binding"]) >= {
            "repository_identity",
            "commit_oid",
            "tree_oid",
            "tree_state",
            "dirty_tree_fingerprint",
            "generation_mode",
        }
        if receipt_id in {
            "receipts/repository_settings.json",
            "receipts/branch_ruleset.json",
            "receipts/release_tag.json",
            "receipts/github_release.json",
        }:
            assert receipt["binding"]["transaction_id"] == "a" * 32
            assert receipt["binding"]["observed_at"] == observed["_meta"]["observed_at"]
    assert not (repository / ".git" / "hsconfig-release-gate").exists()


def test_live_github_rulesets_are_paginated_and_aggregated_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    snapshot = _capture_snapshot(repository, outputs)
    calls: list[tuple[str, ...]] = []

    def gh_json(_repository: Path, *arguments: str) -> Any:
        calls.append(arguments)
        endpoint = arguments[-1]
        if endpoint.endswith("/rulesets"):
            assert "--paginate" in arguments
            assert "--slurp" in arguments
            return [
                [{"id": 20, "name": "inactive", "target": "branch", "enforcement": "disabled"}],
                [{"id": 10, "name": "main-linear-signed", "target": "branch", "enforcement": "active"}],
            ]
        if endpoint.endswith("/rulesets/10"):
            return {
                "id": 10,
                "name": "main-linear-signed",
                "target": "branch",
                "enforcement": "active",
                "bypass_actors": [],
                "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
                "rules": [
                    {"type": "deletion"},
                    {"type": "non_fast_forward"},
                    {"type": "required_linear_history"},
                    {"type": "required_signatures"},
                ],
            }
        if "/git/ref/tags/" in endpoint:
            return {"object": {"type": "commit", "sha": snapshot.commit_oid}}
        if "/releases/tags/" in endpoint:
            return {"id": 1}
        return {"full_name": snapshot.repository_identity}

    monkeypatch.setattr("hsconfig.release_gate._gh_json", gh_json)

    state = _collect_live_github_state(repository, snapshot)

    assert state["ruleset"]["id"] == 10
    assert any("--paginate" in command and "--slurp" in command for command in calls)


def test_live_github_rulesets_reject_second_page_active_or_unknown_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    snapshot = _capture_snapshot(repository, outputs)
    pages: list[list[dict[str, Any]]] = [
        [{"id": 1, "name": "main-linear-signed", "target": "branch", "enforcement": "active"}],
        [{"id": 2, "name": "duplicate", "target": "branch", "enforcement": "active"}],
    ]

    def gh_json(_repository: Path, *arguments: str) -> Any:
        endpoint = arguments[-1]
        if endpoint.endswith("/rulesets"):
            return pages
        if "/git/ref/tags/" in endpoint:
            return {"object": {"type": "commit", "sha": snapshot.commit_oid}}
        return {}

    monkeypatch.setattr("hsconfig.release_gate._gh_json", gh_json)
    with pytest.raises(ReleaseGateError, match="exactly one"):
        _collect_live_github_state(repository, snapshot)

    pages[:] = [[{"id": 1, "name": "main-linear-signed", "target": "branch", "enforcement": "active", "unexpected": True}]]
    with pytest.raises(ReleaseGateError, match="schema mismatch"):
        _collect_live_github_state(repository, snapshot)


def test_current_package_scan_rejects_symlinked_member(tmp_path: Path) -> None:
    repository, outputs = _repository(tmp_path)
    catalog = json.loads(
        (repository / "docs" / "operator" / "audited-deck-catalog.json").read_text(
            encoding="utf-8"
        )
    )
    deck = outputs / catalog["decks"][0]["deck_name"] / "revisions" / ("sha256-" + "a" * 64)
    outside = tmp_path / "private.json"
    outside.write_text('{"secret":true}', encoding="utf-8")
    try:
        (deck / "linked.json").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"platform does not permit test symlink: {exc}")

    result = scan_publishable_content(
        repository=repository,
        outputs_root=outputs,
        tree_mode="final",
        build_distributions=False,
    )

    assert result["passed"] is False
    assert any("non_regular" in row or "link" in row for row in result["violations"])


def test_source_staging_rejects_hardlinked_tracked_file(tmp_path: Path) -> None:
    repository, _outputs = _repository(tmp_path)
    original = repository / "src" / "hsconfig" / "hardlinked.py"
    alias = repository / "src" / "hsconfig" / "hardlinked_alias.py"
    original.write_text("VALUE = 1\n", encoding="utf-8")
    try:
        os.link(original, alias)
    except OSError as exc:
        pytest.skip(f"platform does not permit test hardlink: {exc}")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "hardlink fixture")

    with pytest.raises(ReleaseGateError, match="hardlink"):
        _stage_tracked_source(repository, tmp_path / "staged")


def test_source_staging_rejects_hardlink_replacement_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _outputs = _repository(tmp_path)
    source = repository / "src" / "hsconfig" / "version.py"
    outside = tmp_path / "outside-version.py"
    outside.write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    original_lstat = Path.lstat
    swapped = False

    def swap_after_lstat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        nonlocal swapped
        metadata = original_lstat(path, *args, **kwargs)
        if path == source and not swapped:
            source.unlink()
            os.link(outside, source)
            swapped = True
        return metadata

    monkeypatch.setattr(Path, "lstat", swap_after_lstat)

    with pytest.raises(ReleaseGateError, match="hardlink|changed|identity"):
        _stage_tracked_source(repository, tmp_path / "staged")

    assert swapped is True
    assert not (tmp_path / "staged" / "src" / "hsconfig" / "version.py").exists()


def test_source_staging_rejects_symlink_replacement_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _outputs = _repository(tmp_path)
    source = repository / "src" / "hsconfig" / "version.py"
    outside = tmp_path / "outside-version.py"
    outside.write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(outside)
        probe.unlink()
    except OSError as exc:
        pytest.skip(f"platform does not permit test symlink: {exc}")
    original_lstat = Path.lstat
    swapped = False

    def swap_after_lstat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        nonlocal swapped
        metadata = original_lstat(path, *args, **kwargs)
        if path == source and not swapped:
            source.unlink()
            source.symlink_to(outside)
            swapped = True
        return metadata

    monkeypatch.setattr(Path, "lstat", swap_after_lstat)

    with pytest.raises(ReleaseGateError, match="link|changed|identity"):
        _stage_tracked_source(repository, tmp_path / "staged")

    assert swapped is True
    assert not (tmp_path / "staged" / "src" / "hsconfig" / "version.py").exists()


def test_current_package_scan_rejects_regular_file_swap_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, outputs = _repository(tmp_path)
    catalog = json.loads(
        (repository / "docs" / "operator" / "audited-deck-catalog.json").read_text(
            encoding="utf-8"
        )
    )
    package = (
        outputs
        / catalog["decks"][0]["deck_name"]
        / "revisions"
        / ("sha256-" + "a" * 64)
    )
    source = package / "package.json"
    replacement = tmp_path / "replacement-package.json"
    replacement.write_text('{"swapped":true}\n', encoding="utf-8")
    original_lstat = Path.lstat
    swapped = False

    def swap_after_lstat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        nonlocal swapped
        metadata = original_lstat(path, *args, **kwargs)
        if path == source and not swapped:
            os.replace(replacement, source)
            swapped = True
        return metadata

    monkeypatch.setattr(Path, "lstat", swap_after_lstat)

    violations, scanned = _scan_current_packages(repository, outputs)

    assert swapped is True
    assert scanned == 11
    assert any("changed" in row or "identity" in row for row in violations)


def test_current_package_scan_rejects_hardlinked_member(tmp_path: Path) -> None:
    repository, outputs = _repository(tmp_path)
    catalog = json.loads(
        (repository / "docs" / "operator" / "audited-deck-catalog.json").read_text(
            encoding="utf-8"
        )
    )
    package = outputs / catalog["decks"][0]["deck_name"] / "revisions" / ("sha256-" + "a" * 64)
    alias = package / "hardlinked.json"
    try:
        os.link(package / "package.json", alias)
    except OSError as exc:
        pytest.skip(f"platform does not permit test hardlink: {exc}")

    result = scan_publishable_content(
        repository=repository,
        outputs_root=outputs,
        tree_mode="final",
        build_distributions=False,
    )

    assert any("non_regular_or_link" in row for row in result["violations"])


def test_publishable_scan_rejects_unbound_historical_content_in_every_mode(
    tmp_path: Path,
) -> None:
    repository, outputs = _repository(tmp_path)
    historical = repository / "docs" / "superpowers" / "plans" / "old.md"
    historical.parent.mkdir(parents=True)
    historical.write_text("Local path: " + _local_windows_path() + "\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "historical")

    pre = scan_publishable_content(
        repository=repository,
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
        build_distributions=False,
    )
    final = scan_publishable_content(
        repository=repository,
        outputs_root=outputs,
        tree_mode="final",
        build_distributions=False,
    )

    assert pre["passed"] is False
    assert any(
        row.startswith("legacy_inventory_mismatch:")
        for row in pre["violations"]
    )
    assert final["passed"] is False
    assert "legacy_path:docs/superpowers/plans/old.md" in final["violations"]


@pytest.mark.parametrize(
    "relative_path,content,reason",
    [
        ("README.md", "Use " + _local_windows_path(), "absolute_path"),
        ("README.md", "Use " + _unc_path(), "absolute_path"),
        ("README.md", "Use " + _extended_windows_path(), "absolute_path"),
        ("docs/operator/policy.md", "TO" + "DO publish this", "public_placeholder"),
        ("docs/operator/policy.md", "place" + "holder publish this", "public_placeholder"),
        ("scripts/release.ps1", "# TO" + "DO remove", "unallowlisted_source_placeholder"),
        ("src/hsconfig/example.py", "TOKEN='" + "ghp_" + "123456789012345678901234567890123456'", "secret"),
        ("src/hsconfig/example.py", "credential='" + "A7b9" * 12 + "'", "secret"),
        ("src/hsconfig/example.py", "auth_material='" + "ab" * 48 + "'", "secret"),
        ("src/hsconfig/example.py", "session='" + _jwt_value() + "'", "secret"),
        ("src/hsconfig/client.key.json", "{}", "secret"),
        ("src/hsconfig/HDT_runtime.xml.json", "{}", "private_runtime_evidence"),
        (".codex-qa/result.json", "{}", "residue"),
        ("nested/.codex-qa_leaked/result.json", "{}", "residue"),
        ("outputs/Deck/.staging-old/file.json", "{}", "residue"),
        ("outputs/Deck/current/reports/Power.log", "private", "private_runtime_evidence"),
    ],
)
def test_publishable_scan_fails_closed_for_forbidden_content(
    tmp_path: Path, relative_path: str, content: str, reason: str
) -> None:
    repository, outputs = _repository(tmp_path)
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if not relative_path.startswith("outputs/"):
        _git(repository, "add", relative_path)
        _git(repository, "commit", "-q", "-m", "forbidden fixture")

    result = scan_publishable_content(
        repository=repository,
        outputs_root=outputs,
        tree_mode="final",
        build_distributions=False,
    )

    assert result["passed"] is False
    assert any(reason in row for row in result["violations"])


def test_publishable_scan_rejects_non_utf8_content_with_embedded_secret(
    tmp_path: Path,
) -> None:
    repository, outputs = _repository(tmp_path)
    source = repository / "src" / "hsconfig" / "opaque.bin"
    source.write_bytes(b"\xff\n" + ("ghp_" + "A" * 36).encode("ascii"))
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "opaque fixture")

    result = scan_publishable_content(
        repository=repository,
        outputs_root=outputs,
        tree_mode="final",
        build_distributions=False,
    )

    assert result["passed"] is False
    assert any("non_utf8_content" in row for row in result["violations"])
    assert any("secret" in row for row in result["violations"])


@pytest.mark.parametrize(
    "prefix,secret",
    [
        (b"\xff", ("gh" + "p_" + "A" * 36).encode("ascii")),
        ("éx".encode(), ("gh" + "p_" + "B" * 36).encode("ascii")),
        (b"x", ("AK" + "IA" + "C" * 16).encode("ascii")),
        (b"x", _jwt_value().encode("ascii")),
    ],
)
def test_secret_scan_rejects_ascii_credentials_after_non_ascii_or_word_prefix(
    prefix: bytes, secret: bytes
) -> None:
    violations = _text_violations("src/hsconfig/opaque.bin", prefix + secret, public_doc=False)

    assert any(row.startswith("secret:") for row in violations)
    if prefix.startswith(b"\xff"):
        assert any(row.startswith("non_utf8_content:") for row in violations)


@pytest.mark.parametrize("name", ("myPassword", "databasePassword", "prefixpassword"))
def test_secret_scan_rejects_camelcase_and_concatenated_credential_assignments(
    name: str,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = f"{name}='{value}'\n".encode()

    violations = _text_violations("src/hsconfig/settings.py", content, public_doc=False)

    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "name",
    ("myPassword", "databasePassword", "prefixpassword", "clientSecret", "accessToken"),
)
def test_secret_scan_rejects_quoted_json_credential_assignments(name: str) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = json.dumps({name: value}).encode()

    violations = _text_violations("src/hsconfig/settings.json", content, public_doc=False)

    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "relative",
    (
        "src/hsconfig/settings.json",
        "outputs/Deck/current/settings.json",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.json",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.json",
    ),
)
def test_secret_scan_decodes_escaped_sensitive_json_keys_on_every_surface(
    relative: str,
) -> None:
    key = "database" + _BACKSLASH + "u0050assword"
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = ("{\"" + key + "\":" + json.dumps(value) + "}").encode()

    violations = _text_violations(relative, content, public_doc=False)

    assert json.loads(content) == {"databasePassword": value}
    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "relative",
    (
        "src/hsconfig/settings.json",
        "outputs/Deck/current/settings.json",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.json",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.json",
    ),
)
def test_secret_scan_preserves_duplicate_decoded_json_pairs_on_every_surface(
    relative: str,
) -> None:
    escaped_key = "access" + _BACKSLASH + "u0054oken"
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = (
        "{\""
        + escaped_key
        + "\":"
        + json.dumps(value)
        + ",\"accessToken\":\"safe\"}"
    ).encode()

    violations = _text_violations(relative, content, public_doc=False)

    assert json.loads(content) == {"accessToken": "safe"}
    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_secret_scan_detects_sensitive_yaml_block_scalars_on_every_surface(
    relative: str,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = f"databasePassword: |\n  {value[:28]}\n  {value[28:]}\n".encode()

    violations = _text_violations(relative, content, public_doc=False)

    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize("escape", ("u0050", "x50"))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_secret_scan_fails_closed_for_decoded_duplicate_yaml_keys(
    relative: str,
    escape: str,
) -> None:
    escaped_key = "database" + _BACKSLASH + escape + "assword"
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = (
        f'"{escaped_key}": "{value}"\n'
        '"databasePassword": "safe"\n'
    ).encode()

    violations = _text_violations(relative, content, public_doc=False)

    assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize(
    "first_key,second_key",
    (
        ("1", "01"),
        ("16", "0x10"),
        ("2", "0b10"),
        ("8", "010"),
        ("true", "True"),
        ("null", "~"),
        ("1.0", "1.00"),
        (".nan", ".NaN"),
        (".inf", ".Inf"),
        ("-.inf", "-.Inf"),
        ("-0.0", "0.0"),
    ),
)
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_semantically_equal_safe_scalar_keys_fail_closed_as_duplicates(
    relative: str,
    first_key: str,
    second_key: str,
) -> None:
    content = f"{first_key}: first\n{second_key}: second\n"

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize(
    "invalid_key",
    (
        "!!int nope",
        "!!int 0xGG",
        "!!float nope",
        "!!bool maybe",
        "!!int ''",
        "!!float ''",
        "!!bool ''",
    ),
)
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_invalid_explicit_safe_scalar_key_lexemes_fail_closed(
    relative: str,
    invalid_key: str,
) -> None:
    content = f"{invalid_key}: value\n"

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert violations == [f"invalid_yaml_content:{relative}"]


def test_publishable_scan_and_cli_report_invalid_tagged_yaml_key_without_traceback(
    tmp_path: Path,
) -> None:
    repository, outputs = _repository(tmp_path)
    invalid = repository / "config" / "invalid.yaml"
    invalid.parent.mkdir()
    invalid.write_text("!!int nope: value\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "invalid tagged YAML key fixture")

    direct = scan_publishable_content(
        repository=repository,
        outputs_root=outputs,
        tree_mode="final",
        build_distributions=False,
    )

    assert direct["passed"] is False
    assert "invalid_yaml_content:config/invalid.yaml" in direct["violations"]

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repository),
            "--outputs",
            str(outputs),
            "--tree-mode",
            "final",
            "--json",
            "--internal-check",
            "publishable_path_scan",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stdout.count("\n") == 1
    document = json.loads(completed.stdout)
    assert document["passed"] is False
    assert document["errors"] == ["release gate bootstrap failed"]
    assert "Traceback" not in completed.stderr


@pytest.mark.parametrize(
    "first_key,second_key",
    (
        ("1", '"1"'),
        ("true", '"true"'),
        ("null", '"null"'),
        ("1.0", '"1.0"'),
    ),
)
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_equal_text_with_different_safe_scalar_tags_remains_valid(
    relative: str,
    first_key: str,
    second_key: str,
) -> None:
    content = f"{first_key}: first\n{second_key}: second\n"

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert violations == []


@pytest.mark.parametrize("escape", ("u0050", "x50"))
def test_secret_scan_preserves_safe_quoted_yaml_key_controls(escape: str) -> None:
    escaped_key = "password" + _BACKSLASH + escape + "olicy"
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = f'"{escaped_key}": "{value}"\n'.encode()

    violations = _text_violations(
        "src/hsconfig/settings.yaml",
        content,
        public_doc=False,
    )

    assert not any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize("scalar_style", ("inline", "block"))
@pytest.mark.parametrize("length", (4_096, 4_097))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_sensitive_scalar_enforces_exact_bounded_length_on_every_surface(
    relative: str,
    length: int,
    scalar_style: str,
) -> None:
    escaped_key = "database" + _BACKSLASH + "u0050assword"
    alphabet = "Aa1!Bb2@Cc3#Dd4$Ee5%Ff6^Gg7&Hh8*Ii9(Jj0)"
    value = (alphabet * ((length // len(alphabet)) + 1))[:length]
    if scalar_style == "inline":
        content = f'"{escaped_key}": "{value}"\n'
    else:
        content = f'"{escaped_key}": |\n  {value[:-1]}\n'

    violations = _text_violations(relative, content.encode(), public_doc=False)

    if length == 4_096:
        assert any(row.startswith("secret:") for row in violations)
        assert not any(row.startswith("invalid_yaml_content:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize("rendered", ("q", "u12", "uD800"))
def test_yaml_sensitive_quoted_scalar_fails_closed_for_invalid_escape(
    rendered: str,
) -> None:
    escaped_key = "database" + _BACKSLASH + "u0050assword"
    content = f'"{escaped_key}": "value{_BACKSLASH}{rendered}"\n'.encode()

    violations = _text_violations(
        "src/hsconfig/settings.yaml",
        content,
        public_doc=False,
    )

    assert any(row.startswith("invalid_yaml_content:") for row in violations)


def test_yaml_safe_control_allows_exact_maximum_scalar_length() -> None:
    escaped_key = "password" + _BACKSLASH + "u0050olicy"
    content = f'"{escaped_key}": "{"A" * 4_096}"\n'.encode()

    violations = _text_violations(
        "src/hsconfig/settings.yaml",
        content,
        public_doc=False,
    )

    assert violations == []


@pytest.mark.parametrize("key_style", ("bare", "single", "double"))
@pytest.mark.parametrize("length", (128, 129))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_sensitive_key_enforces_exact_decoded_length_on_every_surface(
    relative: str,
    length: int,
    key_style: str,
) -> None:
    suffix = "databasePassword"
    decoded_key = "x" * (length - len(suffix)) + suffix
    if key_style == "bare":
        rendered_key = decoded_key
    elif key_style == "single":
        rendered_key = f"'{decoded_key}'"
    else:
        escaped_suffix = "database" + _BACKSLASH + "u0050assword"
        rendered_key = f'"{"x" * (length - len(suffix))}{escaped_suffix}"'
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"

    violations = _text_violations(
        relative,
        f'{rendered_key}: "{value}"\n'.encode(),
        public_doc=False,
    )

    if length == 128:
        assert any(row.startswith("secret:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


def test_yaml_oversized_nonsensitive_key_fails_closed_as_structural_violation() -> None:
    key = "policy" + "x" * (129 - len("policy"))

    violations = _text_violations(
        "src/hsconfig/settings.yaml",
        f'{key}: "safe"\n'.encode(),
        public_doc=False,
    )

    assert any(row.startswith("invalid_yaml_content:") for row in violations)


def test_current_ci_workflow_stays_within_publishable_yaml_scalar_limits(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    result = _scan_coverage_publishable_content(
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
        build_distributions=False,
    )

    assert "invalid_yaml_content:.github/workflows/ci.yml" not in result["violations"]


@pytest.mark.parametrize("scalar_style", ("single", "plain"))
@pytest.mark.parametrize("length", (4_096, 4_097))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_single_and_plain_scalars_share_exact_decoded_bound(
    relative: str,
    length: int,
    scalar_style: str,
) -> None:
    alphabet = "Aa1!Bb2@Cc3#Dd4$Ee5%Ff6^Gg7&Hh8*Ii9(Jj0)"
    value = (alphabet * ((length // len(alphabet)) + 1))[:length]
    if scalar_style == "single":
        value = value[:-1] + "'"
        rendered = "'" + value.replace("'", "''") + "'"
    else:
        rendered = value

    violations = _text_violations(
        relative,
        f"databasePassword: {rendered}\n".encode(),
        public_doc=False,
    )

    if length == 4_096:
        assert any(row.startswith("secret:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize("indicator", ("|", ">"))
@pytest.mark.parametrize("logical_length", (4_096, 4_097))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_block_bound_counts_blank_lines_and_logical_newlines(
    relative: str,
    logical_length: int,
    indicator: str,
) -> None:
    first_length = logical_length - (4 if indicator == "|" else 3)
    alphabet = "Aa1!Bb2@Cc3#Dd4$Ee5%Ff6^Gg7&Hh8*Ii9(Jj0)"
    first = (alphabet * ((first_length // len(alphabet)) + 1))[:first_length]
    content = f"databasePassword: {indicator}\n  {first}\n  \n  Z\n"

    violations = _text_violations(relative, content.encode(), public_doc=False)

    if logical_length == 4_096:
        assert any(row.startswith("secret:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize(
    "header,semantic_overhead,trailing_blank",
    (
        ("|", 1, False),
        (">", 1, False),
        ("|-", 0, False),
        (">-", 0, False),
        ("|+", 2, True),
        (">+", 2, True),
    ),
)
@pytest.mark.parametrize("semantic_length", (4_096, 4_097))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_block_styles_and_chomping_use_decoded_semantic_bound(
    relative: str,
    semantic_length: int,
    header: str,
    semantic_overhead: int,
    trailing_blank: bool,
) -> None:
    payload_length = semantic_length - semantic_overhead
    alphabet = "Aa1!Bb2@Cc3#Dd4$Ee5%Ff6^Gg7&Hh8*Ii9(Jj0)"
    payload = (alphabet * ((payload_length // len(alphabet)) + 1))[:payload_length]
    expected = payload + "\n" * semantic_overhead
    content = f"databasePassword: {header}\n  {payload}\n"
    if trailing_blank:
        content += "  \n"

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert len(expected) == semantic_length
    if semantic_length == 4_096:
        assert any(row.startswith("secret:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize("header", ("|2-", "|-2", ">2-", ">-2"))
@pytest.mark.parametrize("semantic_length", (4_096, 4_097))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_explicit_indent_preserves_extra_spaces_and_mixed_indentation(
    relative: str,
    semantic_length: int,
    header: str,
) -> None:
    payload_length = semantic_length - 6
    alphabet = "Aa1!Bb2@Cc3#Dd4$Ee5%Ff6^Gg7&Hh8*Ii9(Jj0)"
    payload = (alphabet * ((payload_length // len(alphabet)) + 1))[:payload_length]
    expected = payload + "\n  X\nZ"
    content = (
        f"databasePassword: {header}\n"
        f"  {payload}\n"
        "    X\n"
        "  Z\n"
    )

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert len(expected) == semantic_length
    if semantic_length == 4_096:
        assert any(row.startswith("secret:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


def test_yaml_complex_block_safe_control_remains_clean() -> None:
    content = "passwordPolicy: >2+\n  safe\n    extra\n  \n  value\n"

    violations = _text_violations(
        "src/hsconfig/settings.yaml",
        content.encode(),
        public_doc=False,
    )

    assert violations == []


@pytest.mark.parametrize("position", ("leading", "trailing"))
@pytest.mark.parametrize("header", ("|", ">", "|-", ">-", "|+", ">+"))
@pytest.mark.parametrize("semantic_length", (4_096, 4_097))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_implicit_space_only_lines_follow_real_yaml_semantics(
    relative: str,
    semantic_length: int,
    header: str,
    position: str,
) -> None:
    alphabet = "Aa1!Bb2@Cc3#Dd4$Ee5%Ff6^Gg7&Hh8*Ii9(Jj0)"

    def render(payload: str) -> str:
        if position == "leading":
            body = f" \n  {payload}\n"
        else:
            body = f"  {payload}\n    \n"
        return f"databasePassword: {header}\n{body}sibling: safe\n"

    seed = yaml.safe_load(render("Z"))["databasePassword"]
    assert isinstance(seed, str)
    semantic_overhead = len(seed) - 1
    payload_length = semantic_length - semantic_overhead
    payload = (alphabet * ((payload_length // len(alphabet)) + 1))[:payload_length]
    content = render(payload)
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert isinstance(decoded, str)
    assert len(decoded) == semantic_length
    if semantic_length == 4_096:
        assert any(row.startswith("secret:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize("blank_lines", (4_096, 4_097))
@pytest.mark.parametrize("header", ("|+", ">+"))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_keep_preserves_leading_blank_scalar_before_base_indent_sibling(
    relative: str,
    header: str,
    blank_lines: int,
) -> None:
    content = (
        f"databasePassword: {header}\n"
        + "      \n" * blank_lines
        + "sibling: safe\n"
    )
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert isinstance(decoded, str)
    assert len(decoded) == blank_lines
    if blank_lines == 4_096:
        assert not any(row.startswith("invalid_yaml_content:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize("header", ("|", ">", "|-", ">-"))
def test_yaml_clip_and_strip_bound_leading_blank_scalar_before_sibling(
    header: str,
) -> None:
    content = (
        f"databasePassword: {header}\n"
        + "        \n" * 4_097
        + "sibling: safe\n"
    )
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(
        "src/hsconfig/settings.yaml",
        content.encode(),
        public_doc=False,
    )

    assert isinstance(decoded, str)
    assert len(decoded) <= 1
    assert not any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize("semantic_length", (4_096, 4_097))
@pytest.mark.parametrize("header", ("|2-", ">2-", "|2+", ">2+"))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_explicit_indent_preserves_extra_spaces_at_exact_scalar_bound(
    relative: str,
    header: str,
    semantic_length: int,
) -> None:
    alphabet = "Aa1!Bb2@Cc3#Dd4$Ee5%Ff6^Gg7&Hh8*Ii9(Jj0)"

    def render(payload: str) -> str:
        return (
            f"databasePassword: {header}\n"
            "    \n"
            f"  {payload}\n"
            "sibling: safe\n"
        )

    seed = yaml.safe_load(render("Z"))["databasePassword"]
    assert isinstance(seed, str)
    semantic_overhead = len(seed) - 1
    payload_length = semantic_length - semantic_overhead
    payload = (alphabet * ((payload_length // len(alphabet)) + 1))[:payload_length]
    content = render(payload)
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert isinstance(decoded, str)
    assert len(decoded) == semantic_length
    assert decoded.startswith("  \n")
    if semantic_length == 4_096:
        assert any(row.startswith("secret:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize("property_prefix", ("!!str", "&vault"))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_node_properties_before_block_header_are_scanned(
    relative: str,
    property_prefix: str,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = f"databasePassword: {property_prefix} >-\n  {value}\n"

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize("anchor_style", ("inline", "block"))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_sensitive_alias_resolves_prior_source_anchor(
    relative: str,
    anchor_style: str,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    if anchor_style == "inline":
        source = f'template: &vault "{value}"\n'
    else:
        source = f"template: &vault >-\n  {value}\n"
    content = source + "databasePassword: *vault\n"

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_sensitive_alias_resolves_prior_multiline_plain_anchor(
    relative: str,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = (
        "template: &vault\n"
        f"  {value}\n"
        "databasePassword: *vault\n"
    )
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert decoded == value
    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_block_content_pseudo_anchor_is_not_registered(
    relative: str,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    block_source = (
        "passwordPolicy: |-\n"
        f'  template: &vault "{value}"\n'
    )
    content = block_source + "databasePassword: *vault\n"
    decoded = yaml.safe_load(block_source)
    with pytest.raises(yaml.composer.ComposerError, match="undefined alias"):
        yaml.safe_load(content)

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert isinstance(decoded["passwordPolicy"], str)
    assert any(row.startswith("invalid_yaml_content:") for row in violations)
    assert not any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize("document_boundary", ("---", "...\n---"))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_anchor_does_not_cross_document_boundary(
    relative: str,
    document_boundary: str,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = (
        f'template: &vault "{value}"\n'
        f"{document_boundary}\n"
        "databasePassword: *vault\n"
    )
    with pytest.raises(yaml.composer.ComposerError, match="undefined alias"):
        list(yaml.safe_load_all(content))

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert any(row.startswith("invalid_yaml_content:") for row in violations)
    assert not any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_sensitive_alias_resolves_inline_and_multiline_plain_anchor(
    relative: str,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = (
        "template: &vault safe\n"
        f"  {value}\n"
        "databasePassword: *vault\n"
    )
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert decoded == f"safe {value}"
    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_plain_continuation_pseudo_anchor_fails_closed(
    relative: str,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = (
        "template: &vault safe\n"
        f'  decoy: &hidden "{value}"\n'
        "databasePassword: *hidden\n"
    )
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(content)

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert any(row.startswith("invalid_yaml_content:") for row in violations)
    assert not any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_multiline_plain_comment_is_excluded_before_entropy_scan(
    relative: str,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    content = (
        "template: &vault safe\n"
        f"  {value} # {'A' * 100}\n"
        "databasePassword: *vault\n"
    )
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert decoded == f"safe {value}"
    assert _shannon_entropy(decoded) >= 3.5
    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize("header", (">-", ">2-"))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_folded_blank_before_more_indented_crosses_entropy_boundary(
    relative: str,
    header: str,
) -> None:
    payload = "AAAAABBBBBCCCDDDDEEEEFFFFGGHHIIIIJJJJ"
    content = (
        f"databasePassword: {header}\n"
        f"  {payload[:20]}\n"
        "  \n"
        f"    {payload[20:]}\n"
        "sibling: safe\n"
    )
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert isinstance(decoded, str)
    assert len(decoded) == 41
    assert _shannon_entropy(decoded) >= 3.5
    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize("semantic_length", (4_096, 4_097))
@pytest.mark.parametrize("header", (">-", ">", ">+", ">2-", ">2", ">2+"))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_folded_blank_before_more_indented_exact_scalar_bound(
    relative: str,
    header: str,
    semantic_length: int,
) -> None:
    alphabet = "Aa1!Bb2@Cc3#Dd4$Ee5%Ff6^Gg7&Hh8*Ii9(Jj0)"

    def render(payload: str) -> str:
        return (
            f"databasePassword: {header}\n"
            f"  {payload}\n"
            "  \n"
            "    Z\n"
            "sibling: safe\n"
        )

    seed = yaml.safe_load(render("Q"))["databasePassword"]
    assert isinstance(seed, str)
    semantic_overhead = len(seed) - 1
    payload_length = semantic_length - semantic_overhead
    payload = (alphabet * ((payload_length // len(alphabet)) + 1))[:payload_length]
    content = render(payload)
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert isinstance(decoded, str)
    assert len(decoded) == semantic_length
    if semantic_length == 4_096:
        assert any(row.startswith("secret:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize("semantic_length", (4_096, 4_097))
@pytest.mark.parametrize("header", (">-", ">2-"))
@pytest.mark.parametrize(
    "relative",
    (
        "config/settings.yaml",
        "outputs/Deck/current/settings.yml",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.yaml",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.yml",
    ),
)
def test_yaml_folded_nmbbn_transition_exact_scalar_bound(
    relative: str,
    header: str,
    semantic_length: int,
) -> None:
    alphabet = "Aa1!Bb2@Cc3#Dd4$Ee5%Ff6^Gg7&Hh8*Ii9(Jj0)"

    def render(payload: str) -> str:
        return (
            f"databasePassword: {header}\n"
            f"  {payload}\n"
            "    M\n"
            "  \n"
            "  \n"
            "  Z\n"
            "sibling: safe\n"
        )

    seed = yaml.safe_load(render("Q"))["databasePassword"]
    assert isinstance(seed, str)
    semantic_overhead = len(seed) - 1
    payload_length = semantic_length - semantic_overhead
    payload = (alphabet * ((payload_length // len(alphabet)) + 1))[:payload_length]
    content = render(payload)
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert isinstance(decoded, str)
    assert len(decoded) == semantic_length
    if semantic_length == 4_096:
        assert any(row.startswith("secret:") for row in violations)
    else:
        assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize("header", ("|", ">"))
def test_yaml_blank_only_clip_matches_real_yaml_empty_scalar(header: str) -> None:
    content = f"databasePassword: {header}\n    \nsibling: safe\n"
    decoded = yaml.safe_load(content)["databasePassword"]

    violations = _text_violations(
        "src/hsconfig/settings.yaml",
        content.encode(),
        public_doc=False,
    )

    assert decoded == ""
    assert violations == []


@pytest.mark.parametrize(
    "header",
    ("|-", "|", "|+", ">-", ">", ">+", "|2-", "|2", "|2+", ">2-", ">2", ">2+"),
)
def test_yaml_block_scalar_bounded_differential_transition_grid(header: str) -> None:
    rows = {
        "N": "  Alpha9!\n",
        "B": "  \n",
        "M": "    More8@\n",
    }
    sequences = (
        sequence
        for width in range(1, 7)
        for sequence in product(tuple(rows), repeat=width)
    )
    for sequence in sequences:
        content = (
            f"databasePassword: {header}\n"
            + "".join(rows[kind] for kind in sequence)
            + "sibling: safe\n"
        )
        try:
            decoded = yaml.safe_load(content)["databasePassword"]
        except yaml.YAMLError:
            violations = _text_violations(
                "src/hsconfig/settings.yaml",
                content.encode(),
                public_doc=False,
            )
            assert any(
                row.startswith("invalid_yaml_content:") for row in violations
            )
        else:
            document = yaml.compose(content, Loader=yaml.SafeLoader)
            assert isinstance(document, yaml.nodes.MappingNode)
            value_node = document.value[0][1]
            assert isinstance(value_node, yaml.nodes.ScalarNode)
            assert isinstance(decoded, str)
            assert value_node.value == decoded
            violations = _text_violations(
                "src/hsconfig/settings.yaml",
                content.encode(),
                public_doc=False,
            )
            assert not any(
                row.startswith("invalid_yaml_content:") for row in violations
            )


@pytest.mark.parametrize(
    "content",
    (
        "safe: first\nsafe: second\n",
        "? [first, second]\n: safe\n",
        "---\nsafe: value\n" * 33,
        "source: &vault safe\nitems: ["
        + ", ".join("*vault" for _ in range(1_025))
        + "]\n",
        "safe: " + "[" * 129 + "value" + "]" * 129 + "\n",
        "safe:\n" + "  - value\n" * 10_001,
        "safe: " + "A" * 4_097 + "\n",
        "databasePassword:\n  nested: safe\n",
    ),
    ids=(
        "duplicate-key",
        "non-scalar-key",
        "document-limit",
        "alias-limit",
        "depth-limit",
        "node-limit",
        "scalar-limit",
        "sensitive-non-scalar",
    ),
)
def test_yaml_structural_and_resource_limits_fail_closed(content: str) -> None:
    violations = _text_violations(
        "src/hsconfig/settings.yaml",
        content.encode(),
        public_doc=False,
    )

    assert any(row.startswith("invalid_yaml_content:") for row in violations)


@pytest.mark.parametrize(
    "content",
    (
        "databasePassword: *missing\n",
        "databasePassword: *vault\ntemplate: &vault safe\n",
        "template: &vault *vault\ndatabasePassword: *vault\n",
        "first: &vault safe\nsecond: &vault other\ndatabasePassword: *vault\n",
        "databasePassword: !!str !!str safe\n",
        "template: &first &second safe\ndatabasePassword: *first\n",
        "template: &vault safe\ndatabasePassword: !!str *vault\n",
        "databasePassword: |+-\n  safe\n",
    ),
)
def test_yaml_invalid_alias_property_or_modifier_fails_closed(content: str) -> None:
    violations = _text_violations(
        "src/hsconfig/settings.yaml",
        content.encode(),
        public_doc=False,
    )

    assert any(row.startswith("invalid_yaml_content:") for row in violations)


def test_yaml_safe_alias_control_remains_clean() -> None:
    content = 'template: &vault "safe"\npasswordPolicy: *vault\n'

    violations = _text_violations(
        "src/hsconfig/settings.yaml",
        content.encode(),
        public_doc=False,
    )

    assert violations == []


def test_shannon_entropy_does_not_rescan_input_per_unique_character() -> None:
    class CountForbidden(str):
        def count(self, *_args: Any, **_kwargs: Any) -> int:
            raise AssertionError("entropy calculation must be single-pass")

    value = CountForbidden("Aa1!Bb2@Cc3#Dd4$")

    assert _shannon_entropy(value) > 3


@pytest.mark.parametrize("failure", ("malformed", "trailing_document", "deep"))
@pytest.mark.parametrize(
    "relative",
    (
        "src/hsconfig/settings.json",
        "outputs/Deck/current/settings.json",
        "hsconfig-1.0.0-py3-none-any.whl!hsconfig/settings.json",
        "hsconfig-1.0.0.tar.gz!hsconfig-1.0.0/hsconfig/settings.json",
    ),
)
def test_json_publishability_fails_closed_for_invalid_or_depth_exhausted_content(
    relative: str,
    failure: str,
) -> None:
    escaped_key = "database" + _BACKSLASH + "u0050assword"
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"
    valid = "{\"" + escaped_key + "\":" + json.dumps(value) + "}"
    if failure == "malformed":
        content = valid[:-1]
    elif failure == "trailing_document":
        content = valid + "{}"
    else:
        content = "[" * 2_000 + valid + "]" * 2_000

    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert any(row.startswith("invalid_json_content:") for row in violations)


def test_json_publishability_accepts_valid_bounded_depth_safe_control() -> None:
    document: Any = {"passwordPolicy": "safe"}
    for _index in range(50):
        document = [document]

    violations = _text_violations(
        "src/hsconfig/settings.json",
        json.dumps(document).encode(),
        public_doc=False,
    )

    assert violations == []


@pytest.mark.parametrize(
    "relative,content",
    (
        (
            "src/hsconfig/settings.json",
            lambda value: json.dumps({"passwordPolicy": value}).encode(),
        ),
        (
            "src/hsconfig/settings.yaml",
            lambda value: f"tokenizer: |\n  {value[:28]}\n  {value[28:]}\n".encode(),
        ),
    ),
)
def test_structured_secret_scan_preserves_noncredential_negative_controls(
    relative: str,
    content: Any,
) -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"

    violations = _text_violations(relative, content(value), public_doc=False)

    assert not any(row.startswith("secret:") for row in violations)


def test_secret_scan_does_not_flag_noncredential_camelcase_assignment() -> None:
    value = "A7b9C2d4E6f8G1h3J5k7L9m2N4p6Q8r1S3t5U7v9W2x4"

    for relative, content in (
        ("src/hsconfig/settings.py", f"passwordPolicy='{value}'\n".encode()),
        ("src/hsconfig/settings.json", json.dumps({"passwordPolicy": value}).encode()),
    ):
        violations = _text_violations(relative, content, public_doc=False)

        assert not any(row.startswith("secret:") for row in violations)


def test_prospective_task7_files_pass_the_production_publishability_scanner(
    tmp_path: Path,
) -> None:
    prospective = (
        "src/hsconfig/near100_scorecard.py",
        "src/hsconfig/release_gate.py",
        "tests/test_near100_scorecard.py",
        "tests/test_pre_run_metrics.py",
        "tests/test_pre_run_semantic_closure_e2e.py",
        "tests/test_release_gate.py",
    )
    violations: list[str] = []
    for relative in prospective:
        data = (ROOT / relative).read_bytes()
        violations.extend(_path_violations(relative))
        violations.extend(_text_violations(relative, data, public_doc=False))

    _repository_root, outputs = _repository(tmp_path)
    result = _scan_coverage_publishable_content(
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
        build_distributions=False,
    )

    assert violations == []
    assert result["passed"] is True
    assert result["violations"] == []


def test_real_working_pre_cutover_publishability_has_no_placeholder_violation(
    tmp_path: Path,
) -> None:
    _repository_root, outputs = _repository(tmp_path)
    result = _scan_coverage_publishable_content(
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
        build_distributions=False,
    )

    marker = "place" + "holder"
    assert [row for row in result["violations"] if marker in row] == []


def test_current_operator_placeholder_reference_is_exactly_approved() -> None:
    relative = "docs/operator/README.md"
    data = (ROOT / relative).read_bytes()
    line = data.decode("utf-8").splitlines()[714]

    assert hashlib.sha256(line.strip().encode("utf-8")).hexdigest() == (
        "d0997da82e0ae641345085fcd2f3a0588c763e75f1c909f1a3826100f82da77b"
    )
    assert f"public_placeholder:{relative}:715" not in _text_violations(
        relative,
        data,
        public_doc=True,
    )


def test_placeholder_reference_exception_is_path_content_and_archive_bound() -> None:
    relative = "src/hsconfig/input_loading.py"
    data = (ROOT / relative).read_bytes()
    lines = data.decode().splitlines()
    line = lines[53]
    wheel_relative = "hsconfig-1.0.0-py3-none-any.whl!hsconfig/input_loading.py"

    assert _text_violations(relative, data, public_doc=False) == []
    assert _text_violations(wheel_relative, data, public_doc=False) == []
    assert _text_violations(relative, b"\n" + data, public_doc=False)
    duplicated = lines[:54] + [line] + lines[54:]
    assert _text_violations(
        relative, ("\n".join(duplicated) + "\n").encode(), public_doc=False
    )
    edited = list(lines)
    edited[53] = line + " open"
    assert _text_violations(
        relative, ("\n".join(edited) + "\n").encode(), public_doc=False
    )


def test_source_placeholder_allowlist_rejects_expired_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    source = repository / "src" / "hsconfig" / "unfinished.py"
    source.write_text("# TO" + "DO remove\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "expired allowlist")
    monkeypatch.setattr(
        "hsconfig.publishable_tree.SOURCE_TODO_ALLOWLIST",
        ({"file": "src/hsconfig/unfinished.py", "line": 1, "reason": "migration", "expiry_version": "1.0.0"},),
    )

    result = scan_publishable_content(
        repository=repository,
        outputs_root=outputs,
        tree_mode="final",
        build_distributions=False,
    )

    assert any("expired_source_placeholder" in row for row in result["violations"])


def test_archive_reader_rejects_traversal_and_casefold_collisions(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.whl"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("hsconfig/good.py", "ok")
        archive.writestr("hsconfig/GOOD.py", "collision")
        archive.writestr("../escape.py", "escape")

    with pytest.raises(ReleaseGateError, match="archive"):
        _archive_rows(archive_path)


def test_archive_reader_rejects_zip_and_tar_links(tmp_path: Path) -> None:
    wheel = tmp_path / "linked.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        member = zipfile.ZipInfo("hsconfig/linked.py")
        member.create_system = 3
        member.external_attr = (0o120777 << 16)
        archive.writestr(member, "outside.py")
    with pytest.raises(ReleaseGateError, match="non-regular zip"):
        _archive_rows(wheel)

    sdist = tmp_path / "linked.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        regular = tarfile.TarInfo("hsconfig-1.0.0/README.md")
        payload = b"readme"
        regular.size = len(payload)
        archive.addfile(regular, io.BytesIO(payload))
        linked = tarfile.TarInfo("hsconfig-1.0.0/src/hsconfig/linked.py")
        linked.type = tarfile.SYMTYPE
        linked.linkname = "../../outside.py"
        archive.addfile(linked)
    with pytest.raises(ReleaseGateError, match="archive"):
        _archive_rows(sdist)


def test_archive_reader_keeps_one_bound_handle_across_tar_validation_and_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "original.tar.gz"
    replacement = tmp_path / "replacement.tar.gz"

    def write_archive(path: Path, payload: bytes) -> None:
        with tarfile.open(path, "w:gz") as archive:
            member = tarfile.TarInfo("hsconfig-1.0.0/payload.bin")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))

    write_archive(archive_path, b"AAAA")
    write_archive(replacement, b"BBBB")
    real_tarfile_open = tarfile.open
    calls = 0

    replacement_blocked = False

    def replace_path_before_second_open(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        nonlocal replacement_blocked
        calls += 1
        if calls == 2:
            try:
                os.replace(replacement, archive_path)
            except PermissionError:
                replacement_blocked = True
        return real_tarfile_open(*args, **kwargs)

    monkeypatch.setattr(tarfile, "open", replace_path_before_second_open)

    rows = _archive_rows(archive_path)

    assert calls == 2
    assert replacement_blocked or not replacement.exists()
    assert rows == (("hsconfig-1.0.0/payload.bin", b"AAAA"),)


def test_archive_reader_rejects_zip_directory_symlink_before_is_dir(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "directory-link.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        member = zipfile.ZipInfo("linked-directory/")
        member.create_system = 3
        member.external_attr = (0o120777 << 16) | 0x10
        archive.writestr(member, b"")

    with pytest.raises(ReleaseGateError, match="non-regular zip"):
        _archive_rows(wheel)


def test_archive_reader_rejects_member_count_and_compression_ratio_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    too_many = tmp_path / "too-many.whl"
    with zipfile.ZipFile(too_many, "w") as archive:
        for index in range(3):
            archive.writestr(f"hsconfig/{index}.py", b"pass\n")
    monkeypatch.setattr("hsconfig.release_gate._MAX_ARCHIVE_MEMBERS", 2)
    with pytest.raises(ReleaseGateError, match="member count"):
        _archive_rows(too_many)

    compressed = tmp_path / "ratio.whl"
    with zipfile.ZipFile(compressed, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("hsconfig/data.bin", b"0" * 1_000_000)
    monkeypatch.setattr("hsconfig.release_gate._MAX_ARCHIVE_MEMBERS", 10)
    monkeypatch.setattr("hsconfig.release_gate._MAX_ARCHIVE_COMPRESSION_RATIO", 10)
    with pytest.raises(ReleaseGateError, match="compression ratio"):
        _archive_rows(compressed)

    compressed_tar = tmp_path / "ratio.tar.gz"
    with tarfile.open(compressed_tar, "w:gz") as archive:
        payload = b"0" * 1_000_000
        member = tarfile.TarInfo("hsconfig-1.0.0/data.bin")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    with pytest.raises(ReleaseGateError, match="compression ratio"):
        _archive_rows(compressed_tar)


def test_repository_hygiene_rejects_ignored_build_residue(tmp_path: Path) -> None:
    repository, outputs = _repository(tmp_path)
    exclude = repository / ".git" / "info" / "exclude"
    exclude.write_text("src/hsconfig.egg-info/\n", encoding="utf-8")
    residue = repository / "src" / "hsconfig.egg-info"
    residue.mkdir()
    (residue / "PKG-INFO").write_text("generated\n", encoding="utf-8")

    result = check_repository_hygiene(repository, outputs)

    assert result["passed"] is False
    assert "workspace_residue:src/hsconfig.egg-info" in result["violations"]


def test_repository_hygiene_rejects_linked_workspace_entry_without_traversal(
    tmp_path: Path,
) -> None:
    repository, outputs = _repository(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "build").mkdir()
    try:
        (repository / "linked-workspace").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"platform does not permit test symlink: {exc}")

    result = check_repository_hygiene(repository, outputs)

    assert result["passed"] is False
    assert "workspace_unsafe:linked-workspace" in result["violations"]
    assert "workspace_residue:linked-workspace/build" not in result["violations"]


def test_cli_emits_exactly_one_json_document_for_failure(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(missing),
            "--outputs",
            str(tmp_path / "outputs"),
            "--tree-mode",
            "final",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stdout.count("\n") == 1
    assert json.loads(completed.stdout)["passed"] is False
    assert str(tmp_path) not in completed.stdout
    assert "Traceback" not in completed.stderr


def test_copied_cli_disables_source_bytecode_before_package_import_on_early_failure(
    tmp_path: Path,
) -> None:
    isolated = tmp_path / "isolated-cli"
    copied_script = isolated / "scripts" / SCRIPT.name
    copied_script.parent.mkdir(parents=True)
    shutil.copy2(SCRIPT, copied_script)
    copied_package = isolated / "src" / "hsconfig"
    shutil.copytree(
        ROOT / "src" / "hsconfig",
        copied_package,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    environment = dict(os.environ)
    for key in tuple(environment):
        if key.upper() in {
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONPATH",
            "PYTHONPYCACHEPREFIX",
        }:
            environment.pop(key)

    completed = subprocess.run(
        [
            sys.executable,
            str(copied_script),
            "--repo",
            str(isolated / "missing"),
            "--outputs",
            str(isolated / "outputs"),
            "--tree-mode",
            "final",
            "--json",
        ],
        cwd=isolated,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stdout.count("\n") == 1
    assert json.loads(completed.stdout)["passed"] is False
    assert "Traceback" not in completed.stderr
    assert not any(path.name == "__pycache__" for path in copied_package.rglob("*"))
    assert not any(copied_package.rglob("*.pyc"))


def test_cli_emits_one_failure_json_for_argument_validation() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", ".", "--outputs", "outputs", "--tree-mode", "invalid", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stdout.count("\n") == 1
    assert json.loads(completed.stdout)["passed"] is False
    assert "Traceback" not in completed.stderr


def test_result_json_redacts_absolute_commands_and_tool_output() -> None:
    local = _local_windows_path()
    jwt = _jwt_value()
    result = ReleaseGateResult(
        passed=False,
        final_release_ready=False,
        version="1.0.0",
        commit_oid="a" * 40,
        checks=(
            ReleaseCheck(
                "ruff",
                False,
                (local, "check"),
                {"stderr_tail": local, "token": jwt, "nested": [f"failure {jwt}"]},
            ),
        ),
    )

    document = result.to_json()

    assert local not in document
    assert jwt not in document
    assert "redacted" in document


def test_portable_value_redacts_mapping_keys_and_values() -> None:
    secret = "ghp_" + "A" * 36

    document = json.dumps(_portable_value({secret: secret}), sort_keys=True)

    assert secret not in document
    assert "redacted-secret" in document


def test_fixture_documents_the_clean_repository_contract() -> None:
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "release_gate" / "clean_repository.json").read_text(
            encoding="utf-8"
        )
    )
    assert tuple(fixture["check_names"]) == EXPECTED_CHECKS
    assert fixture["working_pre_cutover_excluded_prefixes"] == [
        ".agents/",
        ".superpowers/",
        "docs/history/",
        "docs/research/",
        "docs/superpowers/",
    ]
    assert fixture["working_pre_cutover_legacy_file_count"] == 538
    assert fixture["working_pre_cutover_legacy_inventory_sha256"] == (
        "e512a342802139b4f61dc5e9a216b1c840f833fa35b924077647fcaa042f5e9d"
    )
    assert fixture["outputs_root_contract"] == "exactly_twelve_catalog_deck_directories"
    assert fixture["evidence_transport"] == "canonical_json_stdin_envelope"
    assert fixture["evidence_files_written"] is False
    assert fixture["named_evidence_workspace"] is None
    assert "evidence_workspace" not in fixture
    assert fixture["embedded_receipt_schema_version"] == 2
    assert fixture["embedded_receipt_binding_fields"] == [
        "repository_identity",
        "commit_oid",
        "tree_oid",
        "tree_state",
        "dirty_tree_fingerprint",
        "generation_mode",
    ]
    assert fixture["legacy_file_mode"] == "diagnostic_schema1_compatibility_only"
    assert fixture["authority_producer"] == "hsconfig.release_gate"
    assert fixture["semantic_claim_authority_distribution"] == {
        "A": 267,
        "B": 0,
        "C": 49,
        "D": 0,
        "E": 0,
    }
    assert fixture["final_live_transaction"] == [
        "repository_settings",
        "active_branch_ruleset",
        "version_tag",
        "github_release",
        "empty_asset_inventory",
    ]


def test_gate_transports_self_contained_evidence_only_on_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    observed: dict[str, Any] = {}

    def runner(
        spec: Any,
        *,
        repository: Path,
        stdin_data: bytes | None = None,
    ) -> ReleaseCheck:
        if spec.name != "near100_scorecard":
            return ReleaseCheck(spec.name, True, spec.command, {"returncode": 0})
        assert "--evidence-stdin" in spec.command
        assert "--evidence" not in spec.command
        assert stdin_data is not None
        bundle = json.loads(stdin_data)
        observed.update(bundle)
        scorecard = build_near100_scorecard(
            evidence=bundle["evidence"],
            mode="pre_cutover",
            receipt_documents=bundle["receipts"],
        )
        local_passed = all(
            metric.status in {"pass", "pending_remote", "not_applicable"}
            for metric in scorecard.metrics
        )
        return ReleaseCheck(
            spec.name,
            local_passed,
            spec.command,
            {"returncode": 0 if local_passed else 1},
        )

    monkeypatch.setattr("hsconfig.release_gate._run_one", runner)

    result = run_release_gate(
        repository=repository,
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
    )

    assert result.passed is True
    assert set(observed) == {"schema_version", "evidence", "receipts"}
    assert observed["schema_version"] == 1
    expected_binding_fields = {
        "repository_identity",
        "commit_oid",
        "tree_oid",
        "tree_state",
        "dirty_tree_fingerprint",
        "generation_mode",
    }
    assert all(
        receipt["schema_version"] == 2
        and set(receipt["binding"]) == expected_binding_fields
        for receipt in observed["receipts"].values()
    )
    assert not (repository / ".git" / "hsconfig-release-gate").exists()


def test_gate_never_inspects_or_mutates_a_swapped_named_evidence_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.txt"
    victim.write_text("must survive", encoding="utf-8")
    container = repository / ".git" / "hsconfig-release-gate"
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(container), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            pytest.skip("platform does not permit a directory junction fixture")
    else:
        try:
            container.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"platform does not permit a directory symlink fixture: {exc}")
    touched: list[Path] = []
    original_lstat = Path.lstat

    def recording_lstat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        if path == container or container in path.parents:
            touched.append(path)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", recording_lstat)
    monkeypatch.setattr(
        "hsconfig.release_gate._run_one",
        lambda spec, **_kwargs: ReleaseCheck(
            spec.name, True, spec.command, {"returncode": 0}
        ),
    )
    try:
        result = run_release_gate(
            repository=repository,
            outputs_root=outputs,
            tree_mode="working-pre-cutover",
        )
    finally:
        monkeypatch.setattr(Path, "lstat", original_lstat)
        if os.name == "nt":
            container.rmdir()
        else:
            container.unlink()

    assert result.passed is True
    assert touched == []
    assert victim.read_text(encoding="utf-8") == "must survive"
    assert sorted(path.name for path in outside.iterdir()) == ["victim.txt"]


def test_gate_ignores_and_preserves_a_competing_empty_evidence_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, outputs = _repository(tmp_path)
    container = repository / ".git" / "hsconfig-release-gate"
    container.mkdir()
    touched: list[Path] = []
    original_lstat = Path.lstat

    def recording_lstat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        if path == container or container in path.parents:
            touched.append(path)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", recording_lstat)
    monkeypatch.setattr(
        "hsconfig.release_gate._run_one",
        lambda spec, **_kwargs: ReleaseCheck(
            spec.name, True, spec.command, {"returncode": 0}
        ),
    )

    result = run_release_gate(
        repository=repository,
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
    )

    assert result.passed is True
    assert touched == []
    assert container.is_dir()
    assert list(container.iterdir()) == []


@pytest.mark.parametrize("exception_type", (KeyboardInterrupt, SystemExit))
def test_in_memory_evidence_baseexception_leaves_competing_container_and_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[BaseException],
) -> None:
    from hsconfig import release_gate as module

    repository, outputs = _repository(tmp_path)
    container = repository / ".git" / "hsconfig-release-gate"
    container.mkdir()
    original_producer = module._produce_semantic_rows
    injected = exception_type("injected in-memory evidence failure")
    attempts = 0

    def interrupt_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise injected
        return original_producer(*args, **kwargs)

    monkeypatch.setattr("hsconfig.release_gate._produce_semantic_rows", interrupt_once)
    monkeypatch.setattr(
        "hsconfig.release_gate._run_one",
        lambda spec, **_kwargs: ReleaseCheck(
            spec.name, True, spec.command, {"returncode": 0}
        ),
    )

    with pytest.raises(exception_type) as captured:
        run_release_gate(
            repository=repository,
            outputs_root=outputs,
            tree_mode="working-pre-cutover",
        )
    assert captured.value is injected
    assert container.is_dir()
    assert list(container.iterdir()) == []

    retry = run_release_gate(
        repository=repository,
        outputs_root=outputs,
        tree_mode="working-pre-cutover",
    )
    assert retry.passed is True
    assert container.is_dir()
    assert list(container.iterdir()) == []


def test_portable_value_redacts_sensitive_mapping_context_without_known_prefixes() -> None:
    document = {
        "safe": {"status": "failed", "attempt": 2},
        "databasePassword": "ordinary-value",
        "child": {
            "service.auth.token": "another-value",
            "api_key": "third-value",
        },
    }

    first = _portable_value(document)
    second = _portable_value(document)
    encoded = json.dumps(first, sort_keys=True)

    assert first == second
    assert first["safe"] == {"status": "failed", "attempt": 2}
    assert "databasePassword" not in encoded
    assert "service.auth.token" not in encoded
    assert "api_key" not in encoded
    assert "ordinary-value" not in encoded
    assert "another-value" not in encoded
    assert "third-value" not in encoded
    assert encoded.count("[redacted-secret]") == 3


def test_release_result_redacts_sensitive_child_check_keys_and_values() -> None:
    sensitive_key = "service.database.password"
    sensitive_value = "plain-child-value"
    result = ReleaseGateResult(
        passed=False,
        final_release_ready=False,
        version="1.0.0",
        commit_oid="a" * 40,
        checks=(
            ReleaseCheck(
                "ruff",
                False,
                ("python", "-m", "ruff"),
                {
                    "child_check": {
                        "passed": False,
                        sensitive_key: sensitive_value,
                    },
                    "safe_count": 3,
                },
            ),
        ),
    )

    encoded = result.to_json()

    assert sensitive_key not in encoded
    assert sensitive_value not in encoded
    assert '"safe_count":3' in encoded
    assert "redacted-secret" in encoded


@pytest.mark.parametrize("quoted", (False, True))
@pytest.mark.parametrize("value_kind", ("dotted", "punctuation"))
def test_secret_scan_rejects_dotted_sensitive_assignments_with_password_punctuation(
    quoted: bool,
    value_kind: str,
) -> None:
    if value_kind == "dotted":
        value = ".".join(
            ("Az7kP3", "Bm8qR4", "Cn9sT5", "Do1uV6", "Ep2wX7", "Fq3yZ8")
        )
    else:
        value = "".join(
            (
                "Aa1!", "Bb2@", "Cc3#", "Dd4$", "Ee5%",
                "Ff6^", "Gg7&", "Hh8*", "Ii9(", "Jj0)",
            )
        )
    if quoted:
        content = json.dumps({"service.database.password": value}).encode()
    else:
        content = f"service.database.password = {value}\n".encode()

    violations = _text_violations(
        "src/hsconfig/settings.json" if quoted else "src/hsconfig/settings.py",
        content,
        public_doc=False,
    )

    assert len(value) >= 40
    assert any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "name",
    ("passwordPolicy", "tokenizer", "secretary", "sessionFactory"),
)
def test_secret_scan_preserves_high_entropy_noncredential_assignment_controls(
    name: str,
) -> None:
    value = "".join(
        (
            "Aa1!", "Bb2@", "Cc3#", "Dd4$", "Ee5%",
            "Ff6^", "Gg7&", "Hh8*", "Ii9(", "Jj0)",
        )
    )

    violations = _text_violations(
        "src/hsconfig/settings.py",
        f"{name} = {value}\n".encode(),
        public_doc=False,
    )

    assert not any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "expression",
    (
        'normalize_role_token(claim.get("mechanic", claim.get("stance", "")))',
        "_validated_authority_token(handoff._token)",
    ),
)
def test_secret_scan_does_not_treat_token_code_expressions_as_credentials(
    expression: str,
) -> None:
    violations = _text_violations(
        "src/hsconfig/example.py",
        f"token = {expression}\n".encode(),
        public_doc=False,
    )

    assert not any(row.startswith("secret:") for row in violations)


@pytest.mark.parametrize(
    "render",
    (
        lambda value: f'password = r"""{value}"""\n',
        lambda value: f'token = f"""{value}"""\n',
        lambda value: f'api_key = b"{value}"\n',
        lambda value: (
            'client_secret: str = (u"'
            + value[: len(value) // 2]
            + '"\n"'
            + value[len(value) // 2 :]
            + '")\n'
        ),
    ),
)
def test_secret_scan_rejects_prefixed_parenthesized_and_triple_python_literals(
    render: Any,
) -> None:
    value = "".join(
        (
            "Aa1!", "Bb2@", "Cc3#", "Dd4$", "Ee5%",
            "Ff6^", "Gg7&", "Hh8*", "Ii9(", "Jj0)",
        )
    )

    violations = _text_violations(
        "src/hsconfig/settings.py",
        render(value).encode("utf-8"),
        public_doc=False,
    )

    assert any(row.startswith("secret:") for row in violations)


def _valid_pre_cutover_document() -> dict[str, Any]:
    metric_ids = (
        "static_contract_safety",
        "safe_visionai_lowering",
        "testability_and_assurance",
        "semantic_disposition_closure",
        "layered_pre_run_source_coverage",
        "architecture_and_maintainability",
        "slimness_and_coherence",
        "github_repository_polish",
        "workspace_hygiene",
        "overall_pre_run",
        "gameplay_quality",
    )
    return {
        "schema_version": 1,
        "version": "1.0.0",
        "metrics": [
            {
                "metric_id": metric_id,
                "status": (
                    "pending_remote"
                    if metric_id == "github_repository_polish"
                    else "not_applicable"
                    if metric_id == "gameplay_quality"
                    else "pass"
                ),
            }
            for metric_id in metric_ids
        ],
        "open_p0_findings": 0,
        "open_p1_findings": 0,
        "overall_score": "100",
        "passed": False,
    }


@pytest.mark.parametrize(
    "mutation",
    (
        "extra_field",
        "wrong_schema",
        "wrong_version",
        "passed_true",
        "boolean_findings",
        "metrics_mapping",
        "metric_non_mapping",
        "score_non_string",
        "score_invalid",
        "score_non_finite",
        "score_below_minimum",
    ),
)
def test_pre_cutover_safe_detail_rejects_identity_schema_and_score_mutations(
    mutation: str,
) -> None:
    document = _valid_pre_cutover_document()
    if mutation == "extra_field":
        document["unexpected"] = True
    elif mutation == "wrong_schema":
        document["schema_version"] = 2
    elif mutation == "wrong_version":
        document["version"] = "2.0.0"
    elif mutation == "passed_true":
        document["passed"] = True
    elif mutation == "boolean_findings":
        document["open_p1_findings"] = False
    elif mutation == "metrics_mapping":
        document["metrics"] = {}
    elif mutation == "metric_non_mapping":
        document["metrics"][0] = "not-a-metric"
    elif mutation == "score_non_string":
        document["overall_score"] = 100
    elif mutation == "score_invalid":
        document["overall_score"] = "not-a-number"
    elif mutation == "score_non_finite":
        document["overall_score"] = "NaN"
    else:
        document["overall_score"] = "97.999"

    with pytest.raises(ReleaseGateError, match="pre-cutover"):
        _safe_detail(
            json.dumps(document),
            "",
            0,
            allow_pre_cutover_local=True,
        )


def test_safe_detail_preserves_only_hashes_for_non_json_and_oversized_values() -> None:
    detail = _safe_detail("plain diagnostic", "private stderr", 3)
    rendered = ReleaseCheck(
        "bounded",
        False,
        ("bounded",),
        {"detail": "x" * 2_001},
    ).to_document()

    assert set(detail) == {"returncode", "stdout_sha256", "stderr_sha256"}
    assert rendered["details"]["detail"] == {
        "sha256": hashlib.sha256(("x" * 2_001).encode()).hexdigest(),
        "redacted": "oversized-output",
    }
    with pytest.raises(ReleaseGateError, match="invalid JSON"):
        _safe_detail("{not-json", "", 1)
    with pytest.raises(ReleaseGateError, match="successful JSON"):
        _safe_detail("[]", "", 0, allow_pre_cutover_local=True)


def _valid_live_state(snapshot: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "repository": snapshot.repository_identity,
        "commit_oid": snapshot.commit_oid,
        "tree_oid": snapshot.tree_oid,
        "release_tag": "v1.0.0",
        "settings": {
            "full_name": snapshot.repository_identity,
            "default_branch": "main",
            "archived": False,
            "disabled": False,
            "visibility": "public",
            "has_issues": True,
            "has_projects": False,
            "has_wiki": False,
            "has_discussions": False,
            "allow_squash_merge": True,
            "allow_merge_commit": False,
            "allow_rebase_merge": False,
            "allow_auto_merge": False,
            "delete_branch_on_merge": True,
        },
        "ruleset": {
            "id": 17,
            "name": "main-linear-signed",
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {
                "ref_name": {"include": ["refs/heads/main"], "exclude": []}
            },
            "rules": [
                {"type": "deletion"},
                {"type": "non_fast_forward"},
                {"type": "required_linear_history"},
                {"type": "required_signatures"},
            ],
        },
        "tag": {
            "ref_object_oid": snapshot.commit_oid,
            "object_type": "commit",
            "peeled_commit_oid": snapshot.commit_oid,
        },
        "release": {
            "id": 23,
            "html_url": "https://github.com/Teufelsboy/HSConfig/releases/tag/v1.0.0",
            "tag_name": "v1.0.0",
            "draft": False,
            "prerelease": False,
            "assets": [],
        },
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "transaction_id": "a" * 32,
    }


@pytest.mark.parametrize(
    "mutation",
    (
        "schema_version_bool",
        "extra_field",
        "repository",
        "transaction_id",
        "invalid_observed_at",
        "naive_observed_at",
        "settings_type",
        "settings_policy",
        "ruleset_extra",
        "ruleset_identifier_bool",
        "ruleset_conditions",
        "ruleset_rule_shape",
        "ruleset_rule_set",
        "tag_commit",
        "release_identifier_bool",
        "release_assets",
    ),
)
def test_live_github_state_rejects_transaction_and_policy_mutations(
    tmp_path: Path,
    mutation: str,
) -> None:
    repository, outputs = _repository(tmp_path)
    snapshot = _capture_snapshot(repository, outputs)
    state = _valid_live_state(snapshot)
    if mutation == "schema_version_bool":
        state["schema_version"] = True
    elif mutation == "extra_field":
        state["unexpected"] = True
    elif mutation == "repository":
        state["repository"] = "other/repository"
    elif mutation == "transaction_id":
        state["transaction_id"] = "g" * 32
    elif mutation == "invalid_observed_at":
        state["observed_at"] = "not-a-date"
    elif mutation == "naive_observed_at":
        state["observed_at"] = datetime.now().isoformat()
    elif mutation == "settings_type":
        state["settings"] = []
    elif mutation == "settings_policy":
        state["settings"]["allow_auto_merge"] = True
    elif mutation == "ruleset_extra":
        state["ruleset"]["unexpected"] = True
    elif mutation == "ruleset_identifier_bool":
        state["ruleset"]["id"] = True
    elif mutation == "ruleset_conditions":
        state["ruleset"]["conditions"] = {"ref_name": {"include": [], "exclude": []}}
    elif mutation == "ruleset_rule_shape":
        state["ruleset"]["rules"][0]["parameters"] = {}
    elif mutation == "ruleset_rule_set":
        state["ruleset"]["rules"].pop()
    elif mutation == "tag_commit":
        state["tag"]["peeled_commit_oid"] = "0" * 40
    elif mutation == "release_identifier_bool":
        state["release"]["id"] = True
    else:
        state["release"]["assets"] = [{"id": 1}]

    with pytest.raises(ReleaseGateError, match="live GitHub"):
        _validate_live_github_state(state, snapshot)


@pytest.mark.parametrize("bad_type", ([], {}, 1, None, True))
def test_live_github_state_rejects_non_string_rule_types(
    tmp_path: Path,
    bad_type: Any,
) -> None:
    repository, outputs = _repository(tmp_path)
    snapshot = _capture_snapshot(repository, outputs)
    state = _valid_live_state(snapshot)
    state["ruleset"]["rules"][0]["type"] = bad_type

    with pytest.raises(ReleaseGateError, match="live GitHub branch ruleset"):
        _validate_live_github_state(state, snapshot)


@pytest.mark.parametrize(
    "mutation",
    (
        "pagination_type",
        "page_type",
        "summary_extra",
        "identifier_bool",
        "duplicate_identifier",
        "no_active",
        "tag_schema",
        "annotated_schema",
        "detail_schema",
        "detail_identity",
    ),
)
def test_live_github_collection_rejects_malformed_paginated_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    repository, outputs = _repository(tmp_path)
    snapshot = _capture_snapshot(repository, outputs)
    summary: dict[str, Any] = {
        "id": 17,
        "name": "main-linear-signed",
        "target": "branch",
        "enforcement": "active",
    }
    detail = dict(_valid_live_state(snapshot)["ruleset"])

    def gh_json(_repository: Path, *arguments: str) -> Any:
        endpoint = arguments[-1]
        if endpoint.endswith("/rulesets"):
            if mutation == "pagination_type":
                return {}
            if mutation == "page_type":
                return [summary]
            if mutation == "summary_extra":
                return [[summary | {"unexpected": True}]]
            if mutation == "identifier_bool":
                return [[summary | {"id": True}]]
            if mutation == "duplicate_identifier":
                return [[summary], [dict(summary)]]
            if mutation == "no_active":
                return [[summary | {"enforcement": "disabled"}]]
            return [[summary]]
        if "/git/ref/tags/" in endpoint:
            if mutation == "tag_schema":
                return []
            if mutation == "annotated_schema":
                return {"object": {"type": "tag", "sha": "b" * 40}}
            return {"object": {"type": "commit", "sha": snapshot.commit_oid}}
        if "/git/tags/" in endpoint:
            return []
        if endpoint.endswith("/rulesets/17"):
            if mutation == "detail_schema":
                return []
            if mutation == "detail_identity":
                return detail | {"id": 18}
            return detail
        if "/releases/tags/" in endpoint:
            return {"id": 23}
        return {"full_name": snapshot.repository_identity}

    monkeypatch.setattr("hsconfig.release_gate._gh_json", gh_json)
    with pytest.raises(ReleaseGateError, match="live GitHub"):
        _collect_live_github_state(repository, snapshot)


def test_live_github_collection_peels_annotated_tag_to_release_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, outputs = _repository(tmp_path)
    snapshot = _capture_snapshot(repository, outputs)
    state = _valid_live_state(snapshot)

    def gh_json(_repository: Path, *arguments: str) -> Any:
        endpoint = arguments[-1]
        if endpoint.endswith("/rulesets"):
            return [[{
                "id": 17,
                "name": "main-linear-signed",
                "target": "branch",
                "enforcement": "active",
            }]]
        if endpoint.endswith("/rulesets/17"):
            return state["ruleset"]
        if "/git/ref/tags/" in endpoint:
            return {"object": {"type": "tag", "sha": "b" * 40}}
        if "/git/tags/" in endpoint:
            return {"object": {"sha": snapshot.commit_oid}}
        if "/releases/tags/" in endpoint:
            return state["release"]
        return state["settings"]

    monkeypatch.setattr("hsconfig.release_gate._gh_json", gh_json)

    collected = _collect_live_github_state(repository, snapshot)

    assert collected["tag"] == {
        "ref_object_oid": "b" * 40,
        "object_type": "tag",
        "peeled_commit_oid": snapshot.commit_oid,
    }


@pytest.mark.parametrize(
    "mutation",
    (
        "catalog_non_mapping",
        "catalog_missing_decks",
        "catalog_duplicate",
        "catalog_invalid_name",
        "pointer_extra_field",
        "pointer_identity",
        "fingerprint_type",
        "content_root_digest",
        "revision_type",
        "revision_absolute",
        "revision_parent",
        "revision_binding",
        "revision_regular_file",
    ),
)
def test_current_package_scan_rejects_catalog_and_pointer_contract_mutations(
    tmp_path: Path,
    mutation: str,
) -> None:
    repository, outputs = _repository(tmp_path)
    catalog_path = repository / "docs/operator/audited-deck-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if mutation == "catalog_non_mapping":
        catalog_path.write_text("[]", encoding="utf-8")
    elif mutation == "catalog_missing_decks":
        catalog_path.write_text("{}", encoding="utf-8")
    elif mutation == "catalog_duplicate":
        catalog["decks"][1]["deck_name"] = catalog["decks"][0]["deck_name"]
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    elif mutation == "catalog_invalid_name":
        catalog["decks"][0]["deck_name"] = "invalid/name"
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    else:
        deck_name = catalog["decks"][0]["deck_name"]
        pointer_path = outputs / deck_name / "current.json"
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if mutation == "pointer_extra_field":
            pointer["unexpected"] = True
        elif mutation == "pointer_identity":
            pointer["deck_name"] = "other"
        elif mutation == "fingerprint_type":
            pointer["deck_fingerprint"] = 1
        elif mutation == "content_root_digest":
            pointer["content_root_sha256"] = "not-a-digest"
        elif mutation == "revision_type":
            pointer["revision"] = 1
        elif mutation == "revision_absolute":
            pointer["revision"] = "/outside"
        elif mutation == "revision_parent":
            pointer["revision"] = "revisions/../outside"
        elif mutation == "revision_binding":
            pointer["revision"] = "revisions/sha256-" + "b" * 64
        else:
            pointer["revision"] = "regular-file"
            (outputs / deck_name / "regular-file").write_text("not a directory", encoding="utf-8")
        pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    violations, scanned = _scan_current_packages(repository, outputs)

    assert scanned < 12
    assert violations


@pytest.mark.parametrize(
    "name,match",
    (
        ("/" + "absolute.py", "absolute"),
        ("C:" + "/" + "absolute.py", "absolute"),
        ("folder\\member.py", "absolute"),
        ("folder/../member.py", "traversal"),
        ("folder/trailing. ", "unsafe"),
        ("folder/colon:name", "unsafe"),
    ),
)
def test_archive_reader_rejects_nonportable_member_names(
    tmp_path: Path,
    name: str,
    match: str,
) -> None:
    wheel = tmp_path / "names.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(name, b"payload")
    if "\\" in name:
        canonical_name = name.replace("\\", "/").encode()
        wheel.write_bytes(wheel.read_bytes().replace(canonical_name, name.encode()))

    with pytest.raises(ReleaseGateError, match=match):
        _archive_rows(wheel)


def test_archive_reader_accepts_real_directories_and_rejects_type_name_mismatch(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "directory.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("hsconfig/", b"")
        archive.writestr("hsconfig/module.py", b"VALUE = 1\n")

    assert _archive_rows(wheel) == (("hsconfig/module.py", b"VALUE = 1\n"),)

    mismatch = tmp_path / "mismatch.whl"
    with zipfile.ZipFile(mismatch, "w") as archive:
        member = zipfile.ZipInfo("hsconfig/module.py")
        member.create_system = 3
        member.external_attr = (stat.S_IFDIR | 0o755) << 16
        archive.writestr(member, b"")
    with pytest.raises(ReleaseGateError, match="type/name mismatch"):
        _archive_rows(mismatch)


def test_archive_reader_accepts_tar_directory_and_rejects_nonregular_member(
    tmp_path: Path,
) -> None:
    safe = tmp_path / "safe.tar.gz"
    with tarfile.open(safe, "w:gz") as archive:
        directory = tarfile.TarInfo("hsconfig-1.0.0/")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        payload = b"VALUE = 1\n"
        member = tarfile.TarInfo("hsconfig-1.0.0/module.py")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    assert _archive_rows(safe) == (("hsconfig-1.0.0/module.py", payload),)

    unsafe = tmp_path / "device.tar.gz"
    with tarfile.open(unsafe, "w:gz") as archive:
        member = tarfile.TarInfo("hsconfig-1.0.0/device")
        member.type = tarfile.CHRTYPE
        archive.addfile(member)
    with pytest.raises(ReleaseGateError, match="non-regular tar"):
        _archive_rows(unsafe)


def _credential_sample() -> str:
    return "Aa1!Bb2@Cc3#" + "Dd4$Ee5%Ff6^" + "Gg7&Hh8*Ii9(" + "Jj0)Kk1_Ll2+"


@pytest.mark.parametrize(
    "relative,content,expected",
    (
        ("src/hsconfig/settings.py", "client_secret='CREDENTIAL_SAMPLE'", "secret"),
        ("src/hsconfig/settings.py", "client.secret = b'CREDENTIAL_SAMPLE'", "secret"),
        ("src/hsconfig/settings.py", "configure(accessToken='CREDENTIAL_SAMPLE')", "secret"),
        ("src/hsconfig/settings.py", "settings['databasePassword'] = 'CREDENTIAL_SAMPLE'", "secret"),
        ("src/hsconfig/settings.py", "(clientSecret := 'CREDENTIAL_SAMPLE')", "secret"),
        (
            "config/settings.json",
            json.dumps({"outer": [{"clientSecret": "CREDENTIAL_SAMPLE"}]}),
            "secret",
        ),
        (
            "config/settings.yaml",
            "outer:\n  - clientSecret: CREDENTIAL_SAMPLE\n",
            "secret",
        ),
    ),
)
def test_publishability_credentials_cover_static_reachable_assignment_forms(
    relative: str,
    content: str,
    expected: str,
) -> None:
    content = content.replace("CREDENTIAL_SAMPLE", _credential_sample())
    violations = _text_violations(relative, content.encode(), public_doc=False)

    assert any(row.startswith(expected + ":") for row in violations)


@pytest.mark.parametrize(
    "limit_name,limit,content",
    (
        ("_MAX_YAML_DOCUMENT_CHARACTERS", 5, "password: safe"),
        ("_MAX_YAML_EVENTS", 1, "password: safe"),
        ("_MAX_YAML_ANCHORS", 0, "value: &anchor safe"),
        ("_MAX_YAML_NODES", 1, "outer:\n  inner: safe\n"),
        ("_MAX_STRUCTURED_DEPTH", 1, "outer:\n  inner:\n    value: safe\n"),
    ),
)
def test_publishability_yaml_resource_limits_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    limit: int,
    content: str,
) -> None:
    monkeypatch.setattr("hsconfig.publishable_tree." + limit_name, limit)

    violations = _text_violations(
        "config/settings.yaml",
        content.encode(),
        public_doc=False,
    )

    assert violations == ["invalid_yaml_content:config/settings.yaml"]


def test_publishability_yaml_rejects_recursive_alias_and_float_key_duplicates() -> None:
    recursive = _text_violations(
        "config/settings.yaml",
        b"outer: &loop [*loop]\n",
        public_doc=False,
    )
    duplicate_float = _text_violations(
        "config/settings.yaml",
        b"1.0: first\n1.00: second\n",
        public_doc=False,
    )

    assert recursive == ["invalid_yaml_content:config/settings.yaml"]
    assert duplicate_float == ["invalid_yaml_content:config/settings.yaml"]


@pytest.mark.parametrize(
    "mutation",
    (
        "audit_schema",
        "summary_schema",
        "claim_schema",
        "claim_cards_type",
        "claim_action_type",
        "claim_selector_type",
        "claim_condition_type",
        "authority_missing_error",
        "authority_content_digest",
        "authority_lane",
        "card_claim_lanes",
        "card_memberships",
        "claim_key_binding",
        "current_revision_type",
        "current_revision_absolute",
        "current_revision_file",
        "catalog_decks_type",
        "ledger_fingerprint",
        "ledger_cards_type",
        "ledger_card_identity",
        "ledger_claim_identity",
        "card_disposition",
        "claim_disposition",
    ),
)
def test_semantic_producer_rejects_reachable_contract_mutations(
    tmp_path: Path,
    mutation: str,
) -> None:
    repository, outputs = _repository(tmp_path)
    catalog_path = repository / "docs/operator/audited-deck-catalog.json"
    current_path = next(iter(outputs.iterdir())) / "current.json"
    audit_path = _first_report(repository, outputs, "source_contract_audit.json")
    ledger_path = _first_report(repository, outputs, "disposition_ledger.json")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    first_claim_key = next(iter(audit["claim_rows"]))
    first_claim = audit["claim_rows"][first_claim_key]
    first_card = next(iter(audit["card_rows"].values()))
    if mutation == "audit_schema":
        audit["unexpected"] = True
    elif mutation == "summary_schema":
        audit["summary"]["unexpected"] = True
    elif mutation == "claim_schema":
        first_claim["unexpected"] = True
    elif mutation == "claim_cards_type":
        first_claim["cards"] = "not-a-sequence"
    elif mutation in {"claim_action_type", "claim_selector_type", "claim_condition_type"}:
        field = mutation.removeprefix("claim_").removesuffix("_type")
        target = next(row for row in audit["claim_rows"].values() if field in row)
        target[field] = ["not-a-scalar"]
    elif mutation == "authority_missing_error":
        first_claim["evidence_lane_error"] = None
    elif mutation in {"authority_content_digest", "authority_lane"}:
        first_claim["evidence_lane_error"] = None
        first_claim["evidence_authority"] = {
            "as_of_date": "2026-07-07",
            "authority_id": "C:" + first_claim["claim_id"],
            "claim_kind": first_claim["claim_kind"],
            "content_sha256": "sha256:" + "a" * 64,
            "exact_deck_fingerprint": None,
            "lane": "C",
            "reason": "context_only_guide_authority",
            "runtime_authorized": False,
            "source_identity": "https://example.invalid/guide",
        }
        if mutation == "authority_content_digest":
            first_claim["evidence_authority"]["content_sha256"] = "invalid"
        else:
            first_claim["evidence_authority"]["lane"] = "future"
    elif mutation == "card_claim_lanes":
        first_card["claim_lanes"] = {"runtime_lowered": -1}
    elif mutation == "card_memberships":
        first_card["sideboard_memberships"] = "not-a-sequence"
    elif mutation == "claim_key_binding":
        audit["claim_rows"]["claim_wrong"] = audit["claim_rows"].pop(first_claim_key)
    elif mutation.startswith("current_revision_"):
        current = json.loads(current_path.read_text(encoding="utf-8"))
        if mutation == "current_revision_type":
            current["revision"] = 1
        elif mutation == "current_revision_absolute":
            current["revision"] = "/" + "outside"
        else:
            current["revision"] = "unsafe"
            (current_path.parent / "unsafe").write_text("not a directory", encoding="utf-8")
        current_path.write_text(json.dumps(current), encoding="utf-8")
    elif mutation == "catalog_decks_type":
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog["decks"] = "not-a-list"
        catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    elif mutation == "ledger_fingerprint":
        ledger["deck_fingerprint"] = "0" * 64
    elif mutation == "ledger_cards_type":
        ledger["cards"] = {}
    elif mutation == "ledger_card_identity":
        ledger["cards"][0]["physical_owner"] = 1
    elif mutation == "ledger_claim_identity":
        ledger["claims"][0]["evidence_id"] = "unbound"
    elif mutation == "card_disposition":
        ledger["cards"][0]["disposition"] = "future"
    else:
        ledger["claims"][0]["disposition"] = "future"

    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")
    ledger_path.write_text(json.dumps(ledger, sort_keys=True), encoding="utf-8")
    with pytest.raises(ReleaseGateError, match="semantic|current|canonical"):
        _produce_semantic_rows(repository, outputs, ".git/evidence.json")


def test_publishability_credential_parsers_cover_bounded_static_forms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = _credential_sample()
    assert _shannon_entropy("") == 0.0

    accepted_forms = (
        ("config/settings.txt", "clientSecret=" + sample),
        ("config/settings.txt", 'clientSecret="' + sample + '\\"tail"'),
        ("src/hsconfig/settings.py", "clientSecret: str = '" + sample + "'"),
        ("src/hsconfig/settings.py", "settings = {'clientSecret': '" + sample + "'}"),
        ("src/hsconfig/settings.py", "clientSecret = f'" + sample + "'"),
    )
    for relative, content in accepted_forms:
        assert "secret:" + relative in _text_violations(
            relative,
            content.encode(),
            public_doc=False,
        )

    monkeypatch.setattr("hsconfig.publishable_tree._MAX_STRUCTURED_DEPTH", 0)
    assert _text_violations(
        "config/settings.json",
        json.dumps({"outer": {"value": "safe"}}).encode(),
        public_doc=False,
    ) == ["invalid_json_content:config/settings.json"]


@pytest.mark.parametrize(
    "limit_name,limit,content",
    (
        ("_MAX_YAML_DOCUMENTS", 0, "value: safe"),
        ("_MAX_YAML_ALIASES", 0, "base: &anchor safe\nvalue: *anchor\n"),
        ("_MAX_YAML_SCALAR_CHARACTERS", 3, "value: longer"),
    ),
)
def test_publishability_yaml_parser_limits_cover_documents_aliases_and_scalars(
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    limit: int,
    content: str,
) -> None:
    monkeypatch.setattr("hsconfig.publishable_tree." + limit_name, limit)

    assert _text_violations(
        "config/settings.yaml",
        content.encode(),
        public_doc=False,
    ) == ["invalid_yaml_content:config/settings.yaml"]


@pytest.mark.parametrize(
    "content",
    (
        "value: &" + "a" * 129 + " safe\n",
        "[compound, key]: value\n",
        "clientSecret:\n  nested: value\n",
        "2026-08-06: value\n",
    ),
)
def test_publishability_yaml_rejects_nonportable_key_and_value_shapes(content: str) -> None:
    assert _text_violations(
        "config/settings.yaml",
        content.encode(),
        public_doc=False,
    ) == ["invalid_yaml_content:config/settings.yaml"]


def test_distribution_scan_reports_build_failure_and_artifact_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hsconfig.release_gate._stage_tracked_source", lambda *_: None)
    monkeypatch.setattr(
        "hsconfig.release_gate._execute_bounded",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 7, "", "failed"),
    )
    assert _scan_distributions(tmp_path) == (["distribution_build_failed:returncode=7"], 0)

    monkeypatch.setattr(
        "hsconfig.release_gate._execute_bounded",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
    )
    assert _scan_distributions(tmp_path) == (["distribution_artifact_count:0"], 0)


def test_distribution_scan_inspects_both_built_archive_kinds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hsconfig.release_gate._stage_tracked_source", lambda *_: None)

    def execute(command: tuple[str, ...], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        artifacts = Path(command[command.index("--outdir") + 1])
        artifacts.mkdir(parents=True)
        (artifacts / "hsconfig-1.0.0-py3-none-any.whl").write_bytes(b"wheel")
        (artifacts / "hsconfig-1.0.0.tar.gz").write_bytes(b"sdist")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("hsconfig.release_gate._execute_bounded", execute)
    monkeypatch.setattr(
        "hsconfig.release_gate._archive_rows",
        lambda path: (("hsconfig/module.py", b"VALUE = 1\n"),),
    )

    assert _scan_distributions(tmp_path) == ([], 2)


def test_github_json_is_bounded_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hsconfig.release_gate._execute_bounded",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "failed"),
    )
    with pytest.raises(ReleaseGateError, match="live GitHub verification"):
        _gh_json(tmp_path, "api", "repos/example/project")

    monkeypatch.setattr(
        "hsconfig.release_gate._execute_bounded",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, '{"ok":true}', ""),
    )
    assert _gh_json(tmp_path, "api", "repos/example/project") == {"ok": True}


def test_archive_reader_rejects_duplicate_casefold_and_resource_exhaustion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate = tmp_path / "duplicate.whl"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("hsconfig/module.py", b"one")
            archive.writestr("hsconfig/module.py", b"two")
    with pytest.raises(ReleaseGateError, match="duplicate"):
        _archive_rows(duplicate)

    collision = tmp_path / "collision.whl"
    with zipfile.ZipFile(collision, "w") as archive:
        archive.writestr("hsconfig/Module.py", b"one")
        archive.writestr("hsconfig/module.py", b"two")
    with pytest.raises(ReleaseGateError, match="casefold"):
        _archive_rows(collision)

    limited = tmp_path / "limited.whl"
    with zipfile.ZipFile(limited, "w") as archive:
        archive.writestr("hsconfig/module.py", b"payload")
    monkeypatch.setattr("hsconfig.release_gate._MAX_ARCHIVE_MEMBER_BYTES", 0)
    with pytest.raises(ReleaseGateError, match="size limit"):
        _archive_rows(limited)


def _binary_patched_zip(
    path: Path,
    names: tuple[str, ...],
    replacements: tuple[tuple[bytes, bytes], ...],
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for index, name in enumerate(names):
            archive.writestr(name, f"payload-{index}".encode())
    data = path.read_bytes()
    for original, replacement in replacements:
        assert len(original) == len(replacement)
        assert data.count(original) == 2
        data = data.replace(original, replacement)
    path.write_bytes(data)


@pytest.mark.parametrize("codepoint", (*range(32), 127))
def test_archive_reader_rejects_every_ascii_control_character_in_raw_zip_name(
    tmp_path: Path,
    codepoint: int,
) -> None:
    archive_path = tmp_path / f"control-{codepoint}.whl"
    original = b"hsconfig/control-X.py"
    replacement = original.replace(b"X", bytes((codepoint,)))
    _binary_patched_zip(
        archive_path,
        (original.decode("ascii"),),
        ((original, replacement),),
    )

    with pytest.raises(ReleaseGateError, match="control character"):
        _archive_rows(archive_path)


def test_archive_reader_rejects_binary_nul_alias_before_duplicate_resolution(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "nul-alias.whl"
    first = b"hsconfig/alias.py"
    second = b"hsconfig/alias.pyXtail"
    _binary_patched_zip(
        archive_path,
        (first.decode("ascii"), second.decode("ascii")),
        ((second, second.replace(b"X", b"\0")),),
    )

    with pytest.raises(ReleaseGateError, match="control character"):
        _archive_rows(archive_path)


def test_tar_reader_rejects_member_count_links_size_and_ratio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "bounded.tar.gz"
    payload = b"payload"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("hsconfig-1.0.0/module.py")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    monkeypatch.setattr("hsconfig.release_gate._MAX_ARCHIVE_MEMBERS", 0)
    with pytest.raises(ReleaseGateError, match="member count"):
        _archive_rows(archive_path)
    monkeypatch.setattr("hsconfig.release_gate._MAX_ARCHIVE_MEMBERS", 10_000)
    monkeypatch.setattr("hsconfig.release_gate._MAX_ARCHIVE_MEMBER_BYTES", 0)
    with pytest.raises(ReleaseGateError, match="size limit"):
        _archive_rows(archive_path)
    monkeypatch.setattr("hsconfig.release_gate._MAX_ARCHIVE_MEMBER_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr("hsconfig.release_gate._MAX_ARCHIVE_COMPRESSION_RATIO", 0)
    with pytest.raises(ReleaseGateError, match="compression ratio"):
        _archive_rows(archive_path)

    linked = tmp_path / "linked.tar.gz"
    with tarfile.open(linked, "w:gz") as archive:
        member = tarfile.TarInfo("hsconfig-1.0.0/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "module.py"
        archive.addfile(member)
    with pytest.raises(ReleaseGateError, match="link member"):
        _archive_rows(linked)


def test_safe_detail_covers_empty_and_consistent_nested_returncodes() -> None:
    assert _safe_detail("", "", 0) == {"returncode": 0}
    assert _safe_detail('{"passed":true,"returncode":0}', "", 0) == {
        "returncode": 0,
        "result": {"passed": True, "returncode": 0},
    }


def test_live_github_state_rejects_stale_aware_observation(tmp_path: Path) -> None:
    repository, outputs = _repository(tmp_path)
    snapshot = _capture_snapshot(repository, outputs)
    state = _valid_live_state(snapshot)
    state["observed_at"] = "2000-01-01T00:00:00Z"

    with pytest.raises(ReleaseGateError, match="stale"):
        _validate_live_github_state(state, snapshot)


def test_publishability_text_scan_covers_opaque_and_archive_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opaque = (
        b"\xff"
        + ("C" + chr(58) + chr(47) + "Users/example/private/file.txt\n").encode()
        + ("clientSecret=" + _credential_sample()).encode()
    )
    violations = _text_violations("opaque.bin", opaque, public_doc=False)
    assert violations == [
        "non_utf8_content:opaque.bin",
        "absolute_path:opaque.bin",
        "secret:opaque.bin",
    ]
    private_relative = "private/" + "Power" + ".log"
    assert _text_violations(
        private_relative,
        b"safe",
        public_doc=False,
    ) == ["private_runtime_evidence:" + private_relative]

    versioned = _text_violations(
        "artifact.whl!hsconfig-1.0.0/module.py",
        ("TO" + "DO remove before release").encode(),
        public_doc=True,
    )
    package = _text_violations(
        "artifact.whl!hsconfig/module.py",
        ("TO" + "DO remove before release").encode(),
        public_doc=True,
    )
    assert versioned == ["public_placeholder:artifact.whl!hsconfig-1.0.0/module.py:1"]
    assert package == ["public_placeholder:artifact.whl!hsconfig/module.py:1"]

    monkeypatch.setattr(
        "hsconfig.release_gate._contains_secret",
        lambda *args, **kwargs: (_ for _ in ()).throw(ReleaseGateError("invalid")),
    )
    with pytest.raises(ReleaseGateError, match="invalid"):
        _text_violations("config/settings.txt", b"safe", public_doc=False)


@pytest.mark.parametrize(
    "case",
    ("unsupported_mode", "missing_repository", "missing_outputs", "noncanonical_outputs"),
)
def test_repository_validation_rejects_early_boundary_failures(
    tmp_path: Path,
    case: str,
) -> None:
    repository = tmp_path / "repository"
    outputs = repository / "outputs"
    repository.mkdir()
    (repository / ".git").mkdir()
    if case != "missing_outputs":
        outputs.mkdir()
    if case == "unsupported_mode":
        mode = "future"
    else:
        mode = "final"
    if case == "missing_repository":
        repository = tmp_path / "missing"
        outputs = repository / "outputs"
    elif case == "noncanonical_outputs":
        outputs = tmp_path / "other-outputs"
        outputs.mkdir()

    with pytest.raises(ReleaseGateError):
        _validate_repository(repository, outputs, mode)  # type: ignore[arg-type]


def test_json_loader_and_regular_tree_reject_non_object_and_unsafe_roots(
    tmp_path: Path,
) -> None:
    document = tmp_path / "document.json"
    document.write_text("[]", encoding="utf-8")
    with pytest.raises(ReleaseGateError, match="must be an object"):
        _load_json_file(tmp_path, PurePosixPath("document.json"))

    with pytest.raises(ReleaseGateError, match="root is link|non-directory"):
        _walk_regular_tree(document, context="test tree")

    directory = tmp_path / "directory"
    directory.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("safe", encoding="utf-8")
    try:
        (directory / "linked.txt").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"platform does not permit test symlink: {exc}")
    with pytest.raises(ReleaseGateError, match="link"):
        _walk_regular_tree(directory, context="test tree")


@pytest.mark.parametrize(
    "case",
    ("binary_text", "invalid_utf8", "noncanonical", "symlink", "hardlink"),
)
def test_dirty_tree_fingerprint_rejects_untrusted_untracked_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    if case == "invalid_utf8":
        untracked: str | bytes = b"\xff\0"
    elif case == "noncanonical":
        untracked = b"../escape\0"
    elif case == "symlink":
        outside = tmp_path / "outside.txt"
        outside.write_text("safe", encoding="utf-8")
        try:
            (root / "linked.txt").symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"platform does not permit test symlink: {exc}")
        untracked = b"linked.txt\0"
    elif case == "hardlink":
        original = root / "original.txt"
        original.write_text("safe", encoding="utf-8")
        try:
            os.link(original, root / "linked.txt")
        except OSError as exc:
            pytest.skip(f"platform does not permit test hardlink: {exc}")
        untracked = b"linked.txt\0"
    else:
        untracked = "text"

    def git(_root: Path, *arguments: str, text: bool = True) -> str | bytes:
        if case == "binary_text":
            return "text"
        if arguments[0] == "status":
            return b"dirty"
        if arguments[0] == "diff":
            return b""
        return untracked

    monkeypatch.setattr("hsconfig.release_gate._git", git)
    with pytest.raises(ReleaseGateError, match="binary|UTF-8|canonical|link"):
        _dirty_tree_fingerprint(root)


@pytest.mark.parametrize(
    "mutation",
    (
        "package_count",
        "package_row",
        "package_name",
        "package_version",
        "duplicate_package",
        "invalid_constraint",
        "duplicate_constraint",
        "projection_mismatch",
    ),
)
def test_selected_audit_projection_rejects_closed_graph_mutations(
    tmp_path: Path,
    mutation: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    lock_path = repository / f"pylock.{minor}.toml"
    constraints_path = repository / "constraints-ci.txt"
    package_rows: list[str] = []
    constraints: list[str] = []
    for index in range(43):
        name: str | int = f"package-{index}"
        version: str | int = "1.0"
        if mutation == "package_name" and index == 0:
            name = 1
        if mutation == "package_version" and index == 0:
            version = 1
        if mutation == "duplicate_package" and index == 1:
            name = "package-0"
        package_rows.append("{name=" + json.dumps(name) + ",version=" + json.dumps(version) + "}")
        constraints.append(f"package-{index}==1.0")
    if mutation == "package_count":
        package_rows.pop()
    elif mutation == "package_row":
        package_rows[0] = "1"
    elif mutation == "invalid_constraint":
        constraints[0] = "not a pinned constraint"
    elif mutation == "duplicate_constraint":
        constraints[1] = constraints[0]
    elif mutation == "projection_mismatch":
        constraints[0] = "package-0==2.0"
    lock_path.write_text("packages = [" + ",".join(package_rows) + "]\n", encoding="utf-8")
    constraints_path.write_text("\n".join(constraints) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="selected audit"):
        _validate_selected_audit_projection(repository)


@pytest.mark.parametrize(
    "remote,expected",
    (
        ("git@github.com:owner/project.git", "owner/project"),
        ("https://github.com/owner/project.git", "owner/project"),
    ),
)
def test_repository_identity_accepts_canonical_github_remote_forms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remote: str,
    expected: str,
) -> None:
    monkeypatch.setattr("hsconfig.release_gate._git", lambda *args, **kwargs: remote)
    assert _repository_identity(tmp_path) == expected


def test_repository_identity_rejects_non_github_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hsconfig.release_gate._git", lambda *args, **kwargs: "local")
    with pytest.raises(ReleaseGateError, match="identity"):
        _repository_identity(tmp_path)


def test_base_evidence_rejects_failed_prerequisite_checks(tmp_path: Path) -> None:
    repository, outputs = _repository(tmp_path)
    snapshot = _capture_snapshot(repository, outputs)
    failed = ReleaseCheck("ruff", False, ("ruff",), {"returncode": 1})

    with pytest.raises(ReleaseGateError, match="failed checks"):
        _build_base_evidence(
            repository=repository,
            outputs_root=outputs,
            checks=(failed,),
            tree_mode="working-pre-cutover",
            snapshot=snapshot,
        )


@pytest.mark.parametrize(
    "content",
    (
        "clientSecret=",
        "clientSecret=   ",
        "clientSecret='",
        "settings[0] = 'safe'",
    ),
)
def test_publishability_credential_parser_ignores_incomplete_or_nonsensitive_forms(
    content: str,
) -> None:
    assert _text_violations(
        "src/hsconfig/settings.py",
        content.encode(),
        public_doc=False,
    ) == []


def test_publishability_yaml_handles_empty_document_and_rejects_oversized_tag() -> None:
    assert _text_violations(
        "config/settings.yaml",
        b"---\n...\n",
        public_doc=False,
    ) == []
    oversized_tag = "value: !<tag:example.invalid,2026:" + "a" * 300 + "> safe\n"
    assert _text_violations(
        "config/settings.yaml",
        oversized_tag.encode(),
        public_doc=False,
    ) == ["invalid_yaml_content:config/settings.yaml"]


def test_publishability_scanner_covers_opaque_safe_and_non_source_placeholders() -> None:
    assert _text_violations("opaque.bin", b"\xffsafe", public_doc=False) == [
        "non_utf8_content:opaque.bin"
    ]
    marker = ("TO" + "DO remove before release").encode()
    assert _text_violations(
        "artifact.whl!other/module.py",
        marker,
        public_doc=True,
    ) == ["public_placeholder:artifact.whl!other/module.py:1"]
    assert _text_violations("notes.txt", marker, public_doc=False) == []


def test_repository_validation_rejects_non_oid_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    outputs = repository / "outputs"
    outputs.mkdir(parents=True)
    (repository / ".git").mkdir()
    monkeypatch.setattr("hsconfig.release_gate._validate_git_binding", lambda *_: None)

    def git(_repository: Path, *arguments: str, **_kwargs: Any) -> str:
        return "" if arguments[0] == "status" else "short"

    monkeypatch.setattr("hsconfig.release_gate._git", git)
    with pytest.raises(ReleaseGateError, match="full commit OID"):
        _validate_repository(repository, outputs, "final")


def test_archive_reader_rejects_archive_file_over_total_byte_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "limited.whl"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("hsconfig/module.py", b"safe")
    monkeypatch.setattr("hsconfig.release_gate._MAX_ARCHIVE_TOTAL_BYTES", 0)

    with pytest.raises(ReleaseGateError, match="bounded size limit"):
        _archive_rows(archive_path)


def test_git_binding_rejects_mismatched_requested_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    def git(_repository: Path, *arguments: str, **_kwargs: Any) -> str:
        if arguments[-1] == "--show-toplevel":
            return str(tmp_path / "other")
        if arguments[-1] in {"--absolute-git-dir", "--git-common-dir"}:
            return str(repository / ".git")
        return "true"

    monkeypatch.setattr("hsconfig.release_gate._git", git)
    with pytest.raises(ReleaseGateError, match="binding"):
        _validate_git_binding(repository)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    (
        ('lock-version = "1.0"', 'lock-version = "2.0"', "selected lock is invalid"),
        (
            'version = "5.0"\n\n[[packages.wheels]]',
            'version = "5.0"\nunexpected = "value"\n\n[[packages.wheels]]',
            "selected lock is invalid",
        ),
        ('name = "boolean-py"', 'name = ""', "selected lock is invalid"),
        (
            '[packages.sdist]\nname = "charset_normalizer-3.4.9.tar.gz"',
            '[packages.sdist]\nunexpected = "value"\n'
            'name = "charset_normalizer-3.4.9.tar.gz"',
            "selected lock is invalid",
        ),
        (
            'url = "https://files.pythonhosted.org/packages/bd/2a/',
            'url = "http://files.pythonhosted.org/packages/bd/2a/',
            "selected lock is invalid",
        ),
        (
            'name = "boolean_py-5.0-py3-none-any.whl"\nurl =',
            'name = "boolean_py-5.0-py3-none-any.whl"\nunexpected = "value"\nurl =',
            "selected lock is invalid",
        ),
        (
            'sha256 = "ef28a70bd43115208441b53a045d1549e2f0ec6e3d08a9d142cbc41c1938e8d9"',
            'sha256 = "ef28a70bd43115208441b53a045d1549e2f0ec6e3d08a9d142cbc41c1938e8d9"\n'
            'unexpected = "value"',
            "selected lock is invalid",
        ),
        (
            'url = "https://files.pythonhosted.org/packages/e5/ca/',
            'url = "http://files.pythonhosted.org/packages/e5/ca/',
            "selected lock is invalid",
        ),
        ('name = "boolean-py"', 'name = "zzzz-boolean-py"', "lock order is invalid"),
    ),
    ids=(
        "root-schema",
        "package-schema",
        "package-identity",
        "sdist-schema",
        "sdist-content",
        "wheel-schema",
        "wheel-hashes-schema",
        "wheel-content",
        "package-order",
    ),
)
def test_active_lock_parser_rejects_each_closed_boundary_from_real_lock(
    old: str,
    new: str,
    message: str,
) -> None:
    """Catch acceptance of malformed package-lock boundaries or ordering."""
    import hsconfig.release_gate as release_gate_module

    source = (ROOT / "pylock.3.11.toml").read_text(encoding="utf-8")
    assert source.count(old) == 1
    mutated = source.replace(old, new, 1).encode("utf-8")

    with pytest.raises(ReleaseGateError, match=message):
        release_gate_module._active_lock_rows(mutated)


@pytest.mark.parametrize(
    "failure",
    (
        "member-count",
        "entry-schema",
        "check-framing",
        "member-size",
        "aggregate-size",
        "payload-header",
        "payload-digest",
        "payload-trailer",
    ),
)
def test_active_git_blob_protocol_rejects_each_bounded_transport_violation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """Catch any malformed or over-limit Git batch response reaching authority."""
    import hsconfig.release_gate as release_gate_module

    empty_oid = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    entries: list[dict[str, str]] = [
        {"path": "empty.txt", "git_mode": "100644", "blob_oid": empty_oid}
    ]
    responses: list[bytes] = []
    if failure == "member-count":
        entries = [
            {
                "path": f"entry-{index}.txt",
                "git_mode": "100644",
                "blob_oid": empty_oid,
            }
            for index in range(release_gate_module._MAX_ARCHIVE_MEMBERS + 1)
        ]
    elif failure == "entry-schema":
        entries.append(dict(entries[0]))
    elif failure == "check-framing":
        responses = [f"{empty_oid} blob 0".encode("ascii")]
    elif failure == "member-size":
        size = release_gate_module._MAX_ARCHIVE_MEMBER_BYTES + 1
        responses = [f"{empty_oid} blob {size}\n".encode("ascii")]
    elif failure == "aggregate-size":
        size = release_gate_module._MAX_ARCHIVE_MEMBER_BYTES
        entries = [
            {
                "path": f"entry-{index}.txt",
                "git_mode": "100644",
                "blob_oid": f"{index + 1:040x}",
            }
            for index in range(9)
        ]
        responses = [
            b"".join(
                f"{entry['blob_oid']} blob {size}\n".encode("ascii")
                for entry in entries
            )
        ]
    elif failure == "payload-header":
        responses = [
            f"{empty_oid} blob 0\n".encode("ascii"),
            f"{'1' * 40} blob 0\n\n".encode("ascii"),
        ]
    elif failure == "payload-digest":
        wrong_oid = "1" * 40
        entries[0]["blob_oid"] = wrong_oid
        responses = [
            f"{wrong_oid} blob 1\n".encode("ascii"),
            f"{wrong_oid} blob 1\nx\n".encode("ascii"),
        ]
    else:
        responses = [
            f"{empty_oid} blob 0\n".encode("ascii"),
            f"{empty_oid} blob 0\n\nextra".encode("ascii"),
        ]
    if responses:
        response_iterator = iter(responses)
        monkeypatch.setattr(
            release_gate_module,
            "_run_git_blob_batch",
            lambda *_args, **_kwargs: next(response_iterator),
        )

    with pytest.raises(ReleaseGateError, match="Git blob batch is invalid"):
        release_gate_module._git_blob_payloads(tmp_path, entries)


@pytest.mark.parametrize("value", (None, "", "nested\\file", "C:relative"))
def test_runtime_relative_path_rejects_native_or_nontext_paths(value: object) -> None:
    """Catch native, empty, or non-text paths entering a runtime manifest."""
    import hsconfig.release_gate as release_gate_module

    with pytest.raises(ReleaseGateError, match="path is invalid"):
        release_gate_module._runtime_relative_path(value, context="runtime fixture")


@pytest.mark.parametrize("value", ("/absolute", "nested/../escape", "./relative"))
def test_runtime_relative_path_rejects_noncanonical_posix_paths(value: str) -> None:
    """Catch absolute or normalized-away POSIX path components."""
    import hsconfig.release_gate as release_gate_module

    with pytest.raises(ReleaseGateError, match="path is invalid"):
        release_gate_module._runtime_relative_path(value, context="runtime fixture")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_runtime_tree_index_rejects_a_redirected_root(tmp_path: Path) -> None:
    """Catch a validated runtime root being redirected through a junction."""
    import hsconfig.release_gate as release_gate_module

    backing = tmp_path / "backing"
    backing.mkdir()
    redirected = tmp_path / "redirected"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(redirected), str(backing)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip("junction creation unavailable")

    with pytest.raises(ReleaseGateError, match="root is redirected"):
        release_gate_module._runtime_tree_index(redirected, context="runtime fixture")


def test_active_repository_snapshot_rejects_a_real_head_mismatch(tmp_path: Path) -> None:
    """Catch a repository HEAD that no longer matches its bound snapshot."""
    import hsconfig.release_gate as release_gate_module

    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    (repository / "tracked.txt").write_text("bound\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(
        repository,
        "-c",
        "user.name=Runtime Contract",
        "-c",
        "user.email=runtime-contract@example.invalid",
        "commit",
        "-q",
        "-m",
        "fixture",
    )
    tree_oid = _git(repository, "rev-parse", "HEAD^{tree}")

    with pytest.raises(ReleaseGateError, match="snapshot changed"):
        release_gate_module._assert_active_repository_snapshot(
            repository,
            commit_oid="f" * 40,
            tree_oid=tree_oid,
        )


def test_active_project_version_requires_one_literal_assignment(tmp_path: Path) -> None:
    """Catch a staged project with no authoritative literal version."""
    import hsconfig.release_gate as release_gate_module

    version = tmp_path / "src" / "hsconfig" / "version.py"
    version.parent.mkdir(parents=True)
    version.write_text("VERSION = '1.0.0'\n", encoding="utf-8")

    with pytest.raises(ReleaseGateError, match="project version is invalid"):
        release_gate_module._active_project_version(tmp_path)


def test_active_local_project_rejects_schema_and_wheel_closure_boundaries(
    tmp_path: Path,
) -> None:
    """Catch malformed local-project metadata and unbound sibling wheels."""
    import hsconfig.release_gate as release_gate_module

    with pytest.raises(ReleaseGateError, match="local project schema is invalid"):
        release_gate_module._assert_active_local_project(
            {},
            manifest_root=tmp_path,
            source_root=tmp_path,
            inventory_digest="d" * 64,
        )

    source_root = tmp_path / "committed-source"
    version = source_root / "src" / "hsconfig" / "version.py"
    version.parent.mkdir(parents=True)
    version.write_text("__version__ = '1.0.0'\n", encoding="utf-8")
    local_root = tmp_path / "local-wheel"
    local_root.mkdir()
    wheel = local_root / "hsconfig-1.0.0-py3-none-any.whl"
    wheel.write_bytes(b"")
    (local_root / "unbound.whl").write_bytes(b"")
    local = {
        "name": "hsconfig",
        "version": "1.0.0",
        "wheel_path": str(wheel),
        "sha256": hashlib.sha256(b"").hexdigest(),
        "files": [],
        "source_inventory_sha256": "d" * 64,
    }

    with pytest.raises(ReleaseGateError, match="local wheel closure is invalid"):
        release_gate_module._assert_active_local_project(
            local,
            manifest_root=tmp_path,
            source_root=source_root,
            inventory_digest="d" * 64,
        )


@pytest.mark.parametrize("tree_mode", ("working-pre-cutover", "final"))
def test_non_candidate_modes_reject_owner_repository(
    tmp_path: Path,
    tree_mode: str,
) -> None:
    repository, outputs = _repository(tmp_path)

    with pytest.raises(ReleaseGateError, match="owner"):
        _validate_repository(
            repository,
            outputs,
            tree_mode,
            owner_repository=repository,
        )


def test_candidate_rejects_repository_outside_bound_owner_container(
    tmp_path: Path,
) -> None:
    owner_fixture = tmp_path / "owner-fixture"
    outside_fixture = tmp_path / "outside-fixture"
    owner_fixture.mkdir()
    outside_fixture.mkdir()
    owner, outputs = _repository(owner_fixture)
    outside, _outside_outputs = _repository(outside_fixture)
    _git(outside, "checkout", "--detach", "-q")

    with pytest.raises(ReleaseGateError, match="candidate.*owner|owner.*candidate"):
        _validate_repository(
            outside,
            outputs,
            "candidate",
            owner_repository=owner,
        )


def test_candidate_owner_repository_is_in_every_internal_command(tmp_path: Path) -> None:
    owner, outputs = _repository(tmp_path)
    candidate = owner / ".cutover-candidate" / "candidate"

    specs = _command_specs(
        candidate,
        outputs,
        "candidate",
        owner_repository=owner,
    )

    internal = tuple(spec for spec in specs if "--internal-check" in spec.command)
    assert internal
    for spec in internal:
        assert spec.command[spec.command.index("--owner-repo") + 1] == str(owner)


def test_candidate_snapshot_rejects_owner_ref_advance(
    tmp_path: Path,
) -> None:
    owner, outputs = _repository(tmp_path)
    snapshot = _capture_snapshot(owner, outputs, owner_repository=owner)
    (owner / "owner-change.txt").write_text("advance\n", encoding="utf-8")
    _git(owner, "add", "owner-change.txt")
    _git(owner, "commit", "-q", "-m", "advance owner")

    with pytest.raises(ReleaseGateError, match="owner.*changed|changed.*owner"):
        _assert_snapshot_unchanged(
            owner,
            outputs,
            snapshot,
            owner_repository=owner,
        )

@pytest.mark.skipif(os.name != "nt", reason="Windows process-gate semantics")
def test_process_tree_gate_rejects_a_real_directory_as_interpreter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch a non-regular base executable before process creation."""
    import hsconfig.release_gate as release_gate_module

    monkeypatch.setattr(sys, "_base_executable", str(tmp_path))
    with pytest.raises(ReleaseGateError, match="interpreter is invalid"):
        release_gate_module._process_tree_gate_interpreter(sys.executable)


@pytest.mark.parametrize(
    ("failure", "message"),
    (
        ("artifact-schema", "artifact schema is invalid"),
        ("artifact-digest", "artifact changed"),
        ("lock-selection", "artifact is not selected by lock"),
        ("file-schema", "artifact inventory is invalid"),
        ("file-value", "artifact inventory is invalid"),
        ("overlay-collision", "overlay paths collide"),
        ("file-order", "artifact inventory is invalid"),
        ("wheel-inventory", "artifact inventory changed"),
        ("policy-closure", "artifact policy is incomplete"),
    ),
)
def test_runtime_artifact_inventory_rejects_each_real_manifest_boundary(
    real_active_runtime_template: dict[str, Path],
    failure: str,
    message: str,
) -> None:
    """Catch malformed, substituted, or incomplete locked artifact closure."""
    import hsconfig.release_gate as release_gate_module

    bootstrap_root = real_active_runtime_template["bootstrap_root"]
    manifest = json.loads(
        real_active_runtime_template["manifest"].read_text(encoding="utf-8")
    )
    lock_rows = release_gate_module._active_lock_rows(
        (
            bootstrap_root
            / "committed-source"
            / f"pylock.{sys.version_info.major}.{sys.version_info.minor}.toml"
        ).read_bytes()
    )
    artifacts = manifest["artifacts"]
    if failure == "artifact-schema":
        artifacts[0].pop("allowed_startup_surfaces")
    elif failure == "artifact-digest":
        artifacts[0]["sha256"] = "f" * 64
    elif failure == "lock-selection":
        artifacts[0]["url"] = "https://example.invalid/substitute.whl"
    elif failure == "file-schema":
        artifacts[0]["files"][0].pop("size")
    elif failure == "file-value":
        artifacts[0]["files"][0]["size"] = True
    elif failure == "overlay-collision":
        overlays = [artifact for artifact in artifacts if artifact["install"] is False]
        assert len(overlays) == 2
        source = next(
            row
            for row in overlays[0]["files"]
            if row["path"] not in overlays[0]["allowed_startup_surfaces"]
        )
        destination = next(
            row
            for row in overlays[1]["files"]
            if row["path"] not in overlays[1]["allowed_startup_surfaces"]
        )
        destination["path"] = source["path"]
    elif failure == "file-order":
        assert len(artifacts[0]["files"]) > 1
        artifacts[0]["files"].reverse()
    elif failure == "wheel-inventory":
        artifacts[0]["files"][0]["size"] += 1
    else:
        selected = next(
            (artifact, locked)
            for artifact, locked in zip(artifacts, lock_rows, strict=True)
            if artifact["install"] is True
        )
        artifacts, lock_rows = [selected[0]], [selected[1]]

    with pytest.raises(ReleaseGateError, match=message):
        release_gate_module._runtime_artifact_inventory(
            artifacts,
            manifest_root=bootstrap_root,
            lock_rows=lock_rows,
        )


@pytest.mark.parametrize(
    ("failure", "message"),
    (
        ("manifest-path", "runtime binding is invalid"),
        ("manifest-digest", "runtime binding is invalid"),
        ("manifest-schema", "runtime binding is invalid"),
        ("repository-identity", "runtime binding is invalid"),
        ("source-schema", "runtime binding is invalid"),
        ("source-duplicate", "runtime binding is invalid"),
        ("source-authority", "runtime binding is invalid"),
        ("controller", "runtime binding is invalid"),
        ("validation-race", "runtime binding is invalid"),
    ),
)
def test_bound_runtime_rejects_each_identity_and_revalidation_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_active_runtime_template: dict[str, Path],
    failure: str,
    message: str,
) -> None:
    """Catch every bound-runtime identity substitution and validation race."""
    import hsconfig.release_gate as release_gate_module

    binding = _write_active_runtime_binding(
        tmp_path,
        monkeypatch,
        real_active_runtime_template,
    )
    document = json.loads(binding["manifest"].read_text(encoding="utf-8"))
    if failure == "manifest-path":
        monkeypatch.setenv(
            "HSCONFIG_RUNTIME_MANIFEST",
            str(binding["manifest"].with_name("renamed-manifest.json")),
        )
    elif failure == "manifest-digest":
        with binding["manifest"].open("ab") as stream:
            stream.write(b"\n")
    elif failure == "manifest-schema":
        document.pop("schema_version")
        _rewrite_active_runtime_manifest(binding, monkeypatch, document)
    elif failure == "repository-identity":
        original_git = release_gate_module._git

        def malformed_head(repository: Path, *arguments: str, **kwargs: Any) -> Any:
            if arguments == ("rev-parse", "HEAD"):
                return "short"
            return original_git(repository, *arguments, **kwargs)

        monkeypatch.setattr(release_gate_module, "_git", malformed_head)
    elif failure in {"source-schema", "source-duplicate", "source-authority"}:
        inventory = document["source_inventory"]
        if failure == "source-schema":
            inventory[0]["git_mode"] = "100600"
        elif failure == "source-duplicate":
            inventory.append(dict(inventory[0]))
        else:
            inventory.reverse()
        digest = release_gate_module._runtime_source_digest(inventory)
        document["source_inventory_sha256"] = digest
        document["local_project"]["source_inventory_sha256"] = digest
        _rewrite_active_runtime_manifest(binding, monkeypatch, document)
    elif failure == "controller":
        monkeypatch.setattr(
            sys,
            "argv",
            [str(binding["source_root"] / "pyproject.toml"), "--json"],
        )
    else:
        original_assertion = release_gate_module._assert_runtime_tree_payloads
        mutated = False

        def mutate_manifest_after_payload_validation(*args: Any, **kwargs: Any) -> None:
            nonlocal mutated
            original_assertion(*args, **kwargs)
            if not mutated:
                mutated = True
                with binding["manifest"].open("ab") as stream:
                    stream.write(b"\n")

        monkeypatch.setattr(
            release_gate_module,
            "_assert_runtime_tree_payloads",
            mutate_manifest_after_payload_validation,
        )

    with pytest.raises(ReleaseGateError, match=message):
        _active_runtime_paths(binding["repository"])


@pytest.mark.parametrize(
    "failure",
    ("listing-framing", "listing-row", "archive-membership"),
)
def test_active_head_inventory_rejects_git_and_archive_protocol_divergence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """Catch malformed Git tree framing or archive/tree membership divergence."""
    import hsconfig.release_gate as release_gate_module

    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    (repository / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _git(repository, "add", "tracked.txt")
    _git(
        repository,
        "-c",
        "user.name=Runtime Contract",
        "-c",
        "user.email=runtime-contract@example.invalid",
        "commit",
        "-q",
        "-m",
        "fixture",
    )
    commit_oid = _git(repository, "rev-parse", "HEAD")
    original_git = release_gate_module._git
    if failure == "listing-framing":
        monkeypatch.setattr(
            release_gate_module,
            "_git",
            lambda *_args, **_kwargs: "100644 blob " + "f" * 40 + "\ttracked.txt",
        )
    elif failure == "listing-row":
        monkeypatch.setattr(
            release_gate_module,
            "_git",
            lambda *_args, **_kwargs: "100600 blob " + "f" * 40 + "\ttracked.txt\0",
        )
    else:
        empty_archive = io.BytesIO()
        with tarfile.open(fileobj=empty_archive, mode="w"):
            pass

        def archive_without_tracked_file(
            root: Path, *arguments: str, **kwargs: Any
        ) -> Any:
            if "archive" in arguments:
                return empty_archive.getvalue()
            return original_git(root, *arguments, **kwargs)

        monkeypatch.setattr(
            release_gate_module,
            "_git",
            archive_without_tracked_file,
        )

    with pytest.raises(ReleaseGateError, match="HEAD (tree|archive)"):
        release_gate_module._active_head_source_inventory(repository, commit_oid)
