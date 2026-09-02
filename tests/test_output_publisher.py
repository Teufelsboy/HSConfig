from __future__ import annotations

import copy
import errno
import json
import multiprocessing
import os
import pickle
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from types import SimpleNamespace

import pytest

import hsconfig.atomic_io as atomic_io
import hsconfig.output_publisher as output_publisher

from hsconfig.configure_run_model import (
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
)
from hsconfig.output_publisher import publish_configure_run, reconcile_output
from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.package_io import path_identity
from tests.helpers.audited_package_request import audited_request


_SYMLINK_UNAVAILABLE_ERRNOS = {
    errno.EPERM,
    errno.ENOSYS,
    errno.ENOTSUP,
    errno.EOPNOTSUPP,
}
_WINDOWS_PRIVILEGE_NOT_HELD = 1314


def _make_symlink(
    target: Path,
    link: Path,
    *,
    target_is_directory: bool,
) -> None:
    try:
        os.symlink(
            target,
            link,
            target_is_directory=target_is_directory,
        )
    except OSError as error:
        if (
            getattr(error, "winerror", None)
            == _WINDOWS_PRIVILEGE_NOT_HELD
            or error.errno in _SYMLINK_UNAVAILABLE_ERRNOS
        ):
            pytest.skip(f"symlinks unavailable: {error}")
        raise


def _require_windows_short_path_alias(path: Path) -> Path:
    if os.name != "nt":
        pytest.skip("Windows 8.3 path alias regression")
    import ctypes
    from ctypes import wintypes

    get_short_path = ctypes.WinDLL(
        "kernel32",
        use_last_error=True,
    ).GetShortPathNameW
    get_short_path.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
    )
    get_short_path.restype = wintypes.DWORD
    required = get_short_path(str(path), None, 0)
    if required == 0:
        pytest.skip("Windows short paths unavailable")
    buffer = ctypes.create_unicode_buffer(required)
    written = get_short_path(str(path), buffer, len(buffer))
    if written == 0 or written >= len(buffer):
        pytest.skip("Windows short path could not be obtained")
    alias = Path(buffer.value)
    if alias.resolve(strict=True) == alias.absolute():
        pytest.skip("Windows volume did not provide an alternate spelling")
    return alias


def build_rendered_run(
    root: Path,
    revision: int,
    *,
    fixture_paths: bool = False,
) -> RenderedConfigureRun:
    package = assemble_package(
        compile_package(
            audited_request(root, "ShadowPriest", fixture_paths=fixture_paths)
        )
    )
    return render_configure_run_model(
        create_configure_run_model(
            package=package,
            stage_artifacts={
                "01_manifest/input.json": (
                    f'{{"revision":{revision}}}\n'.encode()
                ),
                "02_source_documents/source.json": b'{"stage":2}\n',
                "03_research/research.json": b'{"stage":3}\n',
            },
        )
    )


def _publish_first_worker(
    source_root: str,
    output_root: str,
    ready_queue: object,
    start_event: object,
    result_queue: object,
) -> None:
    rendered = build_rendered_run(Path(source_root), 1, fixture_paths=True)
    ready_queue.put(rendered.content_root_sha256)  # type: ignore[attr-defined]
    if not start_event.wait(30):  # type: ignore[attr-defined]
        result_queue.put(("error", "start timeout"))  # type: ignore[attr-defined]
        return
    try:
        published = publish_configure_run(rendered, Path(output_root))
    except BaseException as error:
        result_queue.put(("error", repr(error)))  # type: ignore[attr-defined]
        return
    result_queue.put(  # type: ignore[attr-defined]
        (
            "ok",
            published.content_root_sha256,
            published.reused_existing_revision,
        )
    )


@pytest.fixture(scope="session", name="rendered_runs")
def rendered_runs_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[RenderedConfigureRun, RenderedConfigureRun]:
    root = tmp_path_factory.mktemp("output-publisher")
    return tuple(
        build_rendered_run(root, revision)
        for revision in (1, 2)
    )  # type: ignore[return-value]


def test_symlink_helper_reraises_unexpected_os_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unexpected = OSError(errno.EIO, "unexpected symlink failure")

    def fail_symlink(*_args: object, **_kwargs: object) -> None:
        raise unexpected

    monkeypatch.setattr(os, "symlink", fail_symlink)

    with pytest.raises(OSError) as raised:
        _make_symlink(
            tmp_path / "target",
            tmp_path / "link",
            target_is_directory=True,
        )

    assert raised.value is unexpected


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows parent-swap setup regression",
)
def test_parent_swap_setup_error_cannot_satisfy_production_error_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    unexpected = OSError(errno.EIO, "unexpected symlink setup failure")

    def fail_symlink(*_args: object, **_kwargs: object) -> None:
        raise unexpected

    real_rename = Path.rename

    def allow_revisions_swap(
        source: Path,
        target: str | os.PathLike[str],
    ) -> Path:
        if source.name == "revisions":
            return Path(target)
        return real_rename(source, target)

    monkeypatch.setattr(os, "symlink", fail_symlink)
    monkeypatch.setattr(Path, "rename", allow_revisions_swap)

    with pytest.raises(
        AssertionError,
        match="symlink setup did not complete",
    ):
        test_staging_root_parent_swap_cannot_create_external_directory(
            tmp_path,
            monkeypatch,
            rendered_runs,
        )


def test_publish_is_content_addressed_current_and_idempotent(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    first = publish_configure_run(rendered_runs[0], output_root)
    repeated = publish_configure_run(rendered_runs[0], output_root)

    assert first.revision_root == repeated.revision_root
    assert not first.reused_existing_revision
    assert repeated.reused_existing_revision
    assert repeated.package_root == repeated.revision_root / "04_package"
    assert repeated.revision_root.name == (
        f"sha256-{rendered_runs[0].content_root_sha256}"
    )
    assert json.loads((output_root / "current.json").read_bytes())[
        "revision"
    ] == f"revisions/{repeated.revision_root.name}"
    assert [
        path.name
        for path in (output_root / "revisions").iterdir()
        if path.is_dir()
    ] == [repeated.revision_root.name]


@pytest.mark.parametrize(
    "prefix",
    (
        "a-",
        "ab-",
        "path-length-even-" + "x" * 18,
        "path-length-odd-" + "x" * 19,
    ),
)
def test_windows_first_publish_supports_short_long_even_odd_paths(
    prefix: str,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    if os.name != "nt":
        pytest.skip("Windows handle-relative rename path matrix")
    with tempfile.TemporaryDirectory(prefix=prefix) as directory:
        output_root = Path(directory) / "deck-one"
        published = publish_configure_run(rendered_runs[0], output_root)

        assert published.revision_root.is_dir()
        assert published.package_root.is_dir()
        assert reconcile_output(output_root) is not None


def test_windows_publish_accepts_same_identity_short_path_alias(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    import hsconfig.package_io as package_io

    long_parent = tmp_path / "Long Ancestor Directory For Short Path Alias"
    long_parent.mkdir()
    alias_parent = _require_windows_short_path_alias(long_parent)

    assert package_io.path_identity(alias_parent) == package_io.path_identity(
        long_parent
    )

    output_root = alias_parent / "ShadowPriest"
    published = publish_configure_run(rendered_runs[0], output_root)

    assert published.revision_root.is_dir()
    assert package_io.path_identity(output_root) == package_io.path_identity(
        long_parent / "ShadowPriest"
    )
    assert reconcile_output(output_root) is not None


def test_two_first_publishers_share_creation_and_one_reuses(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "ShadowPriest"
    expected = build_rendered_run(
        tmp_path / "expected-source",
        1,
        fixture_paths=True,
    ).content_root_sha256
    worker_source_roots = [
        tmp_path / "worker-source-1",
        tmp_path / "worker-source-2",
    ]
    context = multiprocessing.get_context("spawn")
    ready_queue = context.Queue()
    result_queue = context.Queue()
    start_event = context.Event()
    processes = [
        context.Process(
            target=_publish_first_worker,
            args=(
                str(source_root),
                str(output_root),
                ready_queue,
                start_event,
                result_queue,
            ),
        )
        for source_root in worker_source_roots
    ]
    for process in processes:
        process.start()
    ready = [ready_queue.get(timeout=60) for _ in processes]
    assert ready == [expected, expected]
    start_event.set()
    for process in processes:
        process.join(timeout=90)
        assert process.exitcode == 0
    results = [result_queue.get(timeout=10) for _ in processes]

    assert sorted(results) == [
        ("ok", expected, False),
        ("ok", expected, True),
    ]
    revisions = tuple((output_root / "revisions").iterdir())
    assert len(revisions) == 1
    assert revisions[0].name == f"sha256-{expected}"
    assert reconcile_output(output_root) is not None


def test_staging_root_parent_swap_cannot_create_external_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    if os.name != "nt":
        pytest.skip("Windows parent-handle directory creation regression")
    import hsconfig.package_io as package_io

    output_root = tmp_path / "ShadowPriest"
    external = tmp_path / "external-revisions"
    external.mkdir()
    original_create = (
        package_io._create_windows_child_directory_descriptor
    )
    staging_name: str | None = None
    symlink_setup_completed = False

    def swap_then_create(
        parent: package_io.PlainDirectoryMutationGuard,
        name: str,
    ) -> int:
        nonlocal staging_name, symlink_setup_completed
        if (
            staging_name is None
            and name.startswith(".staging-")
            and parent.path.name == "revisions"
        ):
            staging_name = name
            try:
                parent.path.rename(
                    parent.path.with_name("revisions-owned-moved")
                )
            except PermissionError as error:
                if getattr(error, "winerror", None) in {5, 32}:
                    pytest.skip(f"directory swap unavailable: {error}")
                raise
            _make_symlink(
                external,
                parent.path,
                target_is_directory=True,
            )
            symlink_setup_completed = True
        return original_create(parent, name)

    monkeypatch.setattr(
        package_io,
        "_create_windows_child_directory_descriptor",
        swap_then_create,
    )

    with pytest.raises((OSError, ValueError)) as raised:
        publish_configure_run(rendered_runs[0], output_root)

    assert symlink_setup_completed, (
        "symlink setup did not complete before "
        f"{raised.value!r}"
    )
    assert staging_name is not None
    assert not (external / staging_name).exists()


def test_created_staging_directory_is_handle_bound_before_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    if os.name != "nt":
        pytest.skip("Windows created-directory handle binding regression")
    import hsconfig.package_io as package_io

    output_root = tmp_path / "ShadowPriest"
    original_create = (
        package_io._create_windows_child_directory_descriptor
    )
    attempted = False

    def swap_created_directory(
        parent: package_io.PlainDirectoryMutationGuard,
        name: str,
    ) -> int:
        nonlocal attempted
        descriptor = original_create(parent, name)
        try:
            if not attempted and name.startswith(".staging-"):
                attempted = True
                child = parent.path / name
                child.rename(child.with_name(f"{name}-owned-moved"))
                child.mkdir()
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    monkeypatch.setattr(
        package_io,
        "_create_windows_child_directory_descriptor",
        swap_created_directory,
    )

    with pytest.raises(OSError):
        publish_configure_run(rendered_runs[0], output_root)

    assert attempted
    assert not any(
        path.name.endswith("-owned-moved")
        for path in (output_root / "revisions").iterdir()
    )


def test_new_publish_removes_old_only_after_current_commit(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(rendered_runs[0], output_root)

    def fail_before_pointer(stage: str) -> None:
        if stage == "before_pointer_replace":
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        publish_configure_run(
            rendered_runs[1],
            output_root,
            fault_hook=fail_before_pointer,
        )
    assert old.revision_root.is_dir()

    current = publish_configure_run(rendered_runs[1], output_root)
    assert current.revision_root.is_dir()
    assert not old.revision_root.exists()


def test_republish_finalizes_one_canonical_current_owner(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(rendered_runs[0], output_root)

    current = publish_configure_run(rendered_runs[1], output_root)

    journal_paths = tuple(
        (output_root / ".publisher" / "transactions").iterdir()
    )
    assert len(journal_paths) == 1
    owner = output_publisher._parse_transaction(journal_paths[0].read_bytes())
    assert owner.phase == "finalized"
    assert owner.owns_revision
    assert owner.revision == f"revisions/{current.revision_root.name}"
    assert (
        owner.previous_revision,
        owner.previous_revision_identity,
        owner.previous_owner_transaction_id,
    ) == (None, None, None)
    publication, _verified = (
        output_publisher.resolve_current_publication_unlocked(output_root)
    )
    output_publisher.validate_finalized_publication_authority(
        output_root,
        publication,
    )


def test_reconcile_keeps_owner_when_a_later_nonowner_targets_current_revision(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    published = publish_configure_run(rendered_runs[0], output_root)
    transactions = output_root / ".publisher" / "transactions"
    original_path = next(transactions.iterdir())
    original_owner = output_publisher._parse_transaction(
        original_path.read_bytes()
    )
    original_path.unlink()

    owner_id = "1" * 32
    owner = replace(
        original_owner,
        transaction_id=owner_id,
        staging=f"revisions/.staging-{owner_id}",
    )
    owner_path = transactions / f"{owner_id}.json"
    owner_path.write_bytes(output_publisher._transaction_bytes(owner))
    nonowner_id = "2" * 32
    nonowner = replace(
        owner,
        transaction_id=nonowner_id,
        staging=f"revisions/.staging-{nonowner_id}",
        owns_revision=False,
    )
    nonowner_path = transactions / f"{nonowner_id}.json"
    nonowner_path.write_bytes(
        output_publisher._transaction_bytes(nonowner)
    )

    reconciled = reconcile_output(output_root)

    assert reconciled is not None
    assert reconciled.revision_root == published.revision_root
    assert tuple(transactions.iterdir()) == (owner_path,)
    assert output_publisher._parse_transaction(
        owner_path.read_bytes()
    ) == owner


def test_reconcile_canonicalizes_safe_legacy_finalized_owner(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    published = publish_configure_run(rendered_runs[0], output_root)
    journal_path = next(
        (output_root / ".publisher" / "transactions").iterdir()
    )
    owner = output_publisher._parse_transaction(journal_path.read_bytes())
    stale_revision = f"revisions/sha256-{'f' * 64}"
    assert stale_revision != owner.revision
    journal_path.write_bytes(
        output_publisher._transaction_bytes(
            replace(owner, previous_revision=stale_revision)
        )
    )

    reconciled = reconcile_output(output_root)

    assert reconciled is not None
    assert reconciled.revision_root == published.revision_root
    repaired = output_publisher._parse_transaction(journal_path.read_bytes())
    assert (
        repaired.previous_revision,
        repaired.previous_revision_identity,
        repaired.previous_owner_transaction_id,
    ) == (None, None, None)
    publication, _verified = (
        output_publisher.resolve_current_publication_unlocked(output_root)
    )
    output_publisher.validate_finalized_publication_authority(
        output_root,
        publication,
    )


@pytest.mark.parametrize("interrupted_phase", ("finalized", "cleanup_started"))
def test_reconcile_recovers_interrupted_owner_canonicalization(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
    interrupted_phase: str,
) -> None:
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(rendered_runs[0], output_root)
    journal_path = next(
        (output_root / ".publisher" / "transactions").iterdir()
    )
    owner = output_publisher._parse_transaction(journal_path.read_bytes())
    previous_revision = f"revisions/sha256-{'f' * 64}"
    buggy = replace(owner, previous_revision=previous_revision)
    if interrupted_phase == "cleanup_started":
        buggy = replace(
            buggy,
            previous_revision_identity=(1, 2, 3),
            previous_owner_transaction_id="e" * 32,
            phase="cleanup_started",
        )
    journal_path.write_bytes(output_publisher._transaction_bytes(buggy))
    repaired = replace(
        buggy,
        previous_revision=None,
        previous_revision_identity=None,
        previous_owner_transaction_id=None,
        phase="finalized",
    )
    temp_path = journal_path.with_name(
        f".{owner.transaction_id}.journal.tmp"
    )
    temp_path.write_bytes(output_publisher._transaction_bytes(repaired))

    reconciled = reconcile_output(output_root)

    assert reconciled is not None
    assert not temp_path.exists()
    assert output_publisher._parse_transaction(
        journal_path.read_bytes()
    ) == repaired


def test_legacy_canonicalization_rejects_swapped_final_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(rendered_runs[0], output_root)
    journal_path = next(
        (output_root / ".publisher" / "transactions").iterdir()
    )
    owner = output_publisher._parse_transaction(journal_path.read_bytes())
    buggy = replace(
        owner,
        previous_revision=f"revisions/sha256-{'f' * 64}",
    )
    buggy_bytes = output_publisher._transaction_bytes(buggy)
    journal_path.write_bytes(buggy_bytes)
    displaced_path = journal_path.with_name("displaced-owner")
    foreign_bytes = buggy_bytes
    write_transaction = output_publisher._write_transaction
    swapped = False

    def swap_before_canonical_write(
        path: Path,
        transaction: object,
        **kwargs: object,
    ) -> None:
        nonlocal swapped
        if path == journal_path and not swapped:
            swapped = True
            path.rename(displaced_path)
            path.write_bytes(foreign_bytes)
        write_transaction(path, transaction, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        output_publisher,
        "_write_transaction",
        swap_before_canonical_write,
    )

    with pytest.raises(ValueError, match="publisher_owned_target_changed"):
        reconcile_output(output_root)

    assert swapped
    assert journal_path.read_bytes() == foreign_bytes
    assert displaced_path.read_bytes() == buggy_bytes


def test_atomic_temp_recovery_rejects_swapped_final_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(rendered_runs[0], output_root)
    journal_path = next(
        (output_root / ".publisher" / "transactions").iterdir()
    )
    owner = output_publisher._parse_transaction(journal_path.read_bytes())
    buggy = replace(
        owner,
        previous_revision=f"revisions/sha256-{'f' * 64}",
    )
    buggy_bytes = output_publisher._transaction_bytes(buggy)
    journal_path.write_bytes(buggy_bytes)
    repaired = replace(buggy, previous_revision=None)
    temp_path = journal_path.with_name(
        f".{owner.transaction_id}.journal.tmp"
    )
    temp_path.write_bytes(output_publisher._transaction_bytes(repaired))
    displaced_path = journal_path.with_name("displaced-owner")
    foreign_bytes = b"foreign-final-journal"
    validate_residue = output_publisher._validate_publisher_residue
    swapped = False

    def swap_after_scan(*args: object, **kwargs: object) -> None:
        nonlocal swapped
        validate_residue(*args, **kwargs)  # type: ignore[arg-type]
        if not swapped:
            swapped = True
            journal_path.rename(displaced_path)
            journal_path.write_bytes(foreign_bytes)

    monkeypatch.setattr(
        output_publisher,
        "_validate_publisher_residue",
        swap_after_scan,
    )

    with pytest.raises(ValueError, match="publisher_owned_target_changed"):
        reconcile_output(output_root)

    assert swapped
    assert journal_path.read_bytes() == foreign_bytes
    assert displaced_path.read_bytes() == buggy_bytes
    assert temp_path.is_file()


@pytest.mark.parametrize(
    "unsafe_state",
    (
        "previous_root",
        "staging_root",
        "current_identity",
        "current_owner_fields",
        "previous_identity_reference",
        "previous_owner_reference",
        "extra_journal",
    ),
)
def test_reconcile_does_not_clear_ambiguous_legacy_owner_state(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
    unsafe_state: str,
) -> None:
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(rendered_runs[0], output_root)
    transactions_root = output_root / ".publisher" / "transactions"
    journal_path = next(transactions_root.iterdir())
    owner = output_publisher._parse_transaction(journal_path.read_bytes())
    previous_revision = f"revisions/sha256-{'f' * 64}"
    buggy = replace(owner, previous_revision=previous_revision)
    if unsafe_state == "current_identity":
        buggy = replace(buggy, revision_identity=(0, 0, 0))
    elif unsafe_state == "current_owner_fields":
        buggy = replace(buggy, deck_name="OtherDeck")
    journal_path.write_bytes(output_publisher._transaction_bytes(buggy))
    extra_path: Path | None = None
    if unsafe_state == "previous_root":
        (output_root / previous_revision).mkdir()
    elif unsafe_state == "staging_root":
        (output_root / owner.staging).mkdir()
    elif unsafe_state in {
        "previous_identity_reference",
        "previous_owner_reference",
    }:
        payload = json.loads(journal_path.read_bytes())
        if unsafe_state == "previous_identity_reference":
            payload["previous_revision_identity"] = [1, 2, 3]
        else:
            payload["previous_owner_transaction_id"] = "e" * 32
        journal_path.write_bytes(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    elif unsafe_state == "extra_journal":
        transaction_id = "e" * 32
        extra_path = transactions_root / f"{transaction_id}.json"
        extra_path.write_bytes(
            output_publisher._transaction_bytes(
                replace(
                    owner,
                    transaction_id=transaction_id,
                    staging=f"revisions/.staging-{transaction_id}",
                    owns_revision=False,
                )
            )
        )
    before = journal_path.read_bytes()

    with pytest.raises(ValueError):
        reconcile_output(output_root)

    assert journal_path.read_bytes() == before
    if extra_path is not None:
        assert extra_path.is_file()


def test_corrupt_owned_pre_pointer_revision_keeps_journal_on_each_reconcile(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"

    def fail_before_pointer(stage: str) -> None:
        if stage == "before_pointer_replace":
            raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        publish_configure_run(
            rendered_runs[0],
            output_root,
            fault_hook=fail_before_pointer,
        )
    revision_root = (
        output_root
        / "revisions"
        / f"sha256-{rendered_runs[0].content_root_sha256}"
    )
    (revision_root / "01_manifest" / "input.json").write_bytes(
        b'{"revision":"corrupt"}\n'
    )
    transactions = output_root / ".publisher" / "transactions"
    journal = next(transactions.iterdir())
    journal_bytes = journal.read_bytes()

    for _ in range(2):
        with pytest.raises(
            ValueError,
            match="publisher_owned_revision_cleanup_incomplete",
        ):
            reconcile_output(output_root)
        assert revision_root.is_dir()
        assert journal.read_bytes() == journal_bytes
        assert not (output_root / "current.json").exists()


def test_cleanup_started_recovers_when_old_root_and_owner_are_already_gone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    import hsconfig.output_publisher as publisher

    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(rendered_runs[0], output_root)
    write_transaction = publisher._write_transaction

    def fail_before_finalized_write(
        path: Path,
        transaction: object,
        **kwargs: object,
    ) -> None:
        if transaction.phase == "finalized":  # type: ignore[attr-defined]
            raise RuntimeError("injected-finalize")
        write_transaction(path, transaction, **kwargs)

    monkeypatch.setattr(
        publisher,
        "_write_transaction",
        fail_before_finalized_write,
    )
    with pytest.raises(RuntimeError, match="injected-finalize"):
        publish_configure_run(rendered_runs[1], output_root)
    monkeypatch.setattr(publisher, "_write_transaction", write_transaction)

    assert not old.revision_root.exists()
    recovered = reconcile_output(output_root)
    assert recovered is not None
    assert recovered.content_root_sha256 == (
        rendered_runs[1].content_root_sha256
    )
    journal_path = next(
        (output_root / ".publisher" / "transactions").iterdir()
    )
    owner = publisher._parse_transaction(journal_path.read_bytes())
    assert (
        owner.previous_revision,
        owner.previous_revision_identity,
        owner.previous_owner_transaction_id,
    ) == (None, None, None)
    publication, _verified = publisher.resolve_current_publication_unlocked(
        output_root
    )
    publisher.validate_finalized_publication_authority(
        output_root,
        publication,
    )


def _make_cleanup_bound_tree(
    root: Path,
    *,
    bound: str,
    excess: bool,
) -> None:
    root.mkdir()
    if bound == "nodes":
        for index in range(2 + int(excess)):
            (root / f"f{index}").write_bytes(b"x")
    elif bound == "directories":
        for index in range(1 + int(excess)):
            (root / f"d{index}").mkdir()
    elif bound == "depth":
        child = root / "d"
        child.mkdir()
        if excess:
            (child / "d").mkdir()
    elif bound == "path":
        (root / ("abcde" if excess else "abcd")).write_bytes(b"x")
    elif bound == "per_directory":
        for index in range(2 + int(excess)):
            (root / f"f{index}").write_bytes(b"x")
    else:
        raise AssertionError(bound)


@pytest.mark.parametrize(
    "bound,constant,limit,error",
    [
        ("nodes", "MAX_FILESYSTEM_NODES", 2, "node_limit"),
        (
            "directories",
            "MAX_FILESYSTEM_DIRECTORIES",
            1,
            "directory_limit",
        ),
        ("depth", "MAX_FILESYSTEM_DEPTH", 1, "depth_limit"),
        ("path", "MAX_RUN_PATH_BYTES", 4, "path_length_limit"),
        (
            "per_directory",
            "MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY",
            2,
            "directory_entry_limit",
        ),
    ],
)
def test_owned_cleanup_accepts_exact_bound_and_rejects_plus_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bound: str,
    constant: str,
    limit: int,
    error: str,
) -> None:
    import hsconfig.output_publisher as publisher

    monkeypatch.setattr(publisher, constant, limit)
    exact = tmp_path / f"{bound}-exact"
    _make_cleanup_bound_tree(exact, bound=bound, excess=False)
    publisher._remove_owned_tree(
        exact,
        expected_identity=publisher.path_identity(exact),
    )
    assert not exact.exists()

    excess_root = tmp_path / f"{bound}-excess"
    _make_cleanup_bound_tree(excess_root, bound=bound, excess=True)
    with pytest.raises(ValueError, match=error):
        publisher._remove_owned_tree(
            excess_root,
            expected_identity=publisher.path_identity(excess_root),
        )
    assert excess_root.is_dir()


def test_secure_replace_rejects_changed_source_identity(
    tmp_path: Path,
) -> None:
    from hsconfig.package_io import path_identity, secure_replace

    source = tmp_path / "source.tmp"
    target = tmp_path / "target.json"
    source.write_bytes(b"owned")
    target.write_bytes(b"current")
    expected_source = path_identity(source)
    source.unlink()
    source.write_bytes(b"foreign")

    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        secure_replace(
            source,
            target,
            expected_source_identity=expected_source,
            expected_source_parent_identity=path_identity(tmp_path),
            expected_target_parent_identity=path_identity(tmp_path),
        )

    assert source.read_bytes() == b"foreign"
    assert target.read_bytes() == b"current"


def test_secure_replace_does_not_reauthorize_source_swapped_before_guarded_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows handle-bound source identity regression")
    import hsconfig.package_io as package_io

    source = tmp_path / "source.tmp"
    target = tmp_path / "target.json"
    moved = tmp_path / "source-owned-moved"
    source.write_bytes(b"owned")
    target.write_bytes(b"current")
    source_identity = package_io.path_identity(source)
    parent_identity = package_io.path_identity(tmp_path)
    replace_guarded = package_io._replace_guarded
    attempted = False

    def swap_before_guarded_open(
        source_parent: package_io.PlainDirectoryMutationGuard,
        source_name: str,
        target_parent: package_io.PlainDirectoryMutationGuard,
        target_name: str,
        *,
        expected_source_identity: package_io.PathIdentity,
        expected_target_identity: package_io.PathIdentity | None,
        source_directory: bool,
        replace_if_exists: bool,
    ) -> None:
        nonlocal attempted
        attempted = True
        source.rename(moved)
        source.write_bytes(b"foreign")
        replace_guarded(
            source_parent,
            source_name,
            target_parent,
            target_name,
            expected_source_identity=expected_source_identity,
            expected_target_identity=expected_target_identity,
            source_directory=source_directory,
            replace_if_exists=replace_if_exists,
        )

    monkeypatch.setattr(
        package_io,
        "_replace_guarded",
        swap_before_guarded_open,
    )

    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        package_io.secure_replace(
            source,
            target,
            expected_source_identity=source_identity,
            expected_source_parent_identity=parent_identity,
            expected_target_parent_identity=parent_identity,
        )

    assert attempted
    assert moved.read_bytes() == b"owned"
    assert source.read_bytes() == b"foreign"
    assert target.read_bytes() == b"current"


def test_secure_replace_binds_source_identity_through_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows handle-bound rename regression")
    import hsconfig.package_io as package_io

    source = tmp_path / "source.tmp"
    target = tmp_path / "target.json"
    moved = tmp_path / "source-owned-moved"
    source.write_bytes(b"owned")
    target.write_bytes(b"current")
    source_identity = package_io.path_identity(source)
    parent_identity = package_io.path_identity(tmp_path)
    set_name = package_io._set_windows_handle_name
    attempted = False

    def swap_then_set_name(
        descriptor: int,
        destination: Path,
        *,
        target_parent_descriptor: int,
        replace_if_exists: bool = True,
    ) -> None:
        nonlocal attempted
        attempted = True
        source.rename(moved)
        source.write_bytes(b"foreign")
        set_name(
            descriptor,
            destination,
            target_parent_descriptor=target_parent_descriptor,
            replace_if_exists=replace_if_exists,
        )

    monkeypatch.setattr(
        package_io,
        "_set_windows_handle_name",
        swap_then_set_name,
    )

    with pytest.raises(OSError):
        package_io.secure_replace(
            source,
            target,
            expected_source_identity=source_identity,
            expected_source_parent_identity=parent_identity,
            expected_target_parent_identity=parent_identity,
        )

    assert attempted
    assert source.read_bytes() == b"owned"
    assert target.read_bytes() == b"current"
    assert not moved.exists()


def test_staging_directory_identity_is_bound_through_revision_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    if os.name != "nt":
        pytest.skip("Windows handle-bound directory rename regression")
    import hsconfig.package_io as package_io

    output_root = tmp_path / "ShadowPriest"
    set_name = package_io._set_windows_handle_name
    attempted = False

    def swap_then_set_name(
        descriptor: int,
        destination: Path,
        *,
        target_parent_descriptor: int,
        replace_if_exists: bool = True,
    ) -> None:
        nonlocal attempted
        if destination.name.startswith("sha256-"):
            attempted = True
            staging = next(
                (output_root / "revisions").glob(".staging-*")
            )
            staging.rename(
                staging.with_name(f"{staging.name}-owned-moved")
            )
            staging.mkdir()
        set_name(
            descriptor,
            destination,
            target_parent_descriptor=target_parent_descriptor,
            replace_if_exists=replace_if_exists,
        )

    monkeypatch.setattr(
        package_io,
        "_set_windows_handle_name",
        swap_then_set_name,
    )

    with pytest.raises(OSError):
        publish_configure_run(rendered_runs[0], output_root)

    assert attempted
    assert not any(
        path.name.endswith("-owned-moved")
        for path in (output_root / "revisions").iterdir()
    )


def test_revision_promotion_rejects_target_created_inside_handle_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    if os.name != "nt":
        pytest.skip("Windows no-replace handle rename regression")
    import hsconfig.package_io as package_io

    output_root = tmp_path / "ShadowPriest"
    set_name = package_io._set_windows_handle_name
    attempted = False
    foreign_marker: Path | None = None

    def create_target_then_set_name(
        descriptor: int,
        destination: Path,
        *,
        target_parent_descriptor: int,
        replace_if_exists: bool = True,
    ) -> None:
        nonlocal attempted, foreign_marker
        if not attempted and destination.name.startswith("sha256-"):
            attempted = True
            assert not replace_if_exists
            destination.mkdir()
            foreign_marker = destination / "foreign.txt"
            foreign_marker.write_text("foreign", encoding="utf-8")
        set_name(
            descriptor,
            destination,
            target_parent_descriptor=target_parent_descriptor,
            replace_if_exists=replace_if_exists,
        )

    monkeypatch.setattr(
        package_io,
        "_set_windows_handle_name",
        create_target_then_set_name,
    )

    with pytest.raises(OSError):
        publish_configure_run(rendered_runs[0], output_root)

    assert attempted
    assert foreign_marker is not None
    assert foreign_marker.read_text(encoding="utf-8") == "foreign"
    assert not (output_root / "current.json").exists()


@pytest.mark.parametrize("directory", (False, True))
def test_secure_delete_binds_child_identity_through_disposition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    directory: bool,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows handle-bound disposition regression")
    import hsconfig.package_io as package_io

    victim = tmp_path / ("victim-dir" if directory else "victim.txt")
    if directory:
        victim.mkdir()
    else:
        victim.write_bytes(b"owned")
    moved = victim.with_name(f"{victim.name}-owned-moved")
    victim_identity = package_io.path_identity(victim)
    parent_identity = package_io.path_identity(tmp_path)
    set_delete = package_io._set_windows_handle_delete
    attempted = False

    def swap_then_delete(descriptor: int) -> None:
        nonlocal attempted
        attempted = True
        victim.rename(moved)
        if directory:
            victim.mkdir()
        else:
            victim.write_bytes(b"foreign")
        set_delete(descriptor)

    monkeypatch.setattr(
        package_io,
        "_set_windows_handle_delete",
        swap_then_delete,
    )

    with pytest.raises(OSError):
        if directory:
            package_io.secure_rmdir(
                victim,
                expected_identity=victim_identity,
                expected_parent_identity=parent_identity,
            )
        else:
            package_io.secure_unlink(
                victim,
                expected_identity=victim_identity,
                expected_parent_identity=parent_identity,
            )

    assert attempted
    assert victim.exists()
    assert not moved.exists()
    if not directory:
        assert victim.read_bytes() == b"owned"


def test_existing_digest_target_must_verify_exactly(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(rendered_runs[0], output_root)
    target = (
        output_root
        / "revisions"
        / f"sha256-{rendered_runs[1].content_root_sha256}"
    )
    target.mkdir()
    (target / "foreign.txt").write_text("not a revision", encoding="utf-8")

    with pytest.raises(ValueError):
        publish_configure_run(rendered_runs[1], output_root)

    assert old.revision_root.is_dir()
    assert (target / "foreign.txt").read_text(encoding="utf-8") == (
        "not a revision"
    )


def test_pointer_compare_and_swap_rejects_concurrent_change(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(rendered_runs[0], output_root)

    def mutate_pointer(stage: str) -> None:
        if stage == "before_pointer_replace":
            (output_root / "current.json").write_bytes(b"concurrent\n")

    with pytest.raises(ValueError, match="current_output_concurrent_change"):
        publish_configure_run(
            rendered_runs[1],
            output_root,
            fault_hook=mutate_pointer,
        )
    assert old.revision_root.is_dir()


def test_publication_releases_lock_for_baseexception(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(rendered_runs[0], output_root)

    class InjectedBaseFault(BaseException):
        pass

    def inject(stage: str) -> None:
        if stage == "after_staging_render":
            raise InjectedBaseFault

    with pytest.raises(InjectedBaseFault):
        publish_configure_run(
            rendered_runs[1],
            output_root,
            fault_hook=inject,
        )
    assert publish_configure_run(
        rendered_runs[1],
        output_root,
    ).package_root.is_dir()
    assert not any(
        path.name.startswith(".staging-")
        for path in (output_root / "revisions").iterdir()
    )


def test_publish_fails_closed_without_deleting_unknown_revision_or_staging(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    first = publish_configure_run(rendered_runs[0], output_root)
    unknown_revision = output_root / "revisions" / f"sha256-{'0' * 64}"
    unknown_staging = output_root / "revisions" / (
        ".staging-" + "0" * 32
    )
    unknown_revision.mkdir()
    unknown_staging.mkdir()
    (unknown_revision / "owner.txt").write_text("foreign", encoding="utf-8")
    (unknown_staging / "owner.txt").write_text("foreign", encoding="utf-8")

    with pytest.raises(ValueError, match="publisher_residue_invalid"):
        publish_configure_run(rendered_runs[0], output_root)
    assert first.revision_root.is_dir()
    assert (unknown_revision / "owner.txt").is_file()
    assert (unknown_staging / "owner.txt").is_file()


def test_foreign_transaction_record_fails_closed_and_is_left_untouched(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(rendered_runs[0], output_root)
    record = (
        output_root
        / ".publisher"
        / "transactions"
        / f"{'0' * 32}.json"
    )
    record.write_bytes(b'{"damaged":true}\n')

    with pytest.raises(ValueError, match="publisher_transaction"):
        publish_configure_run(rendered_runs[0], output_root)
    assert record.read_bytes() == b'{"damaged":true}\n'


def test_journal_temp_parent_swap_cannot_create_external_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    if os.name != "nt":
        pytest.skip("Windows ancestor-lease child-open regression")
    import hsconfig.package_io as package_io

    output_root = tmp_path / "ShadowPriest"
    external = tmp_path / "external-transactions"
    external.mkdir()
    original_open = os.open
    original_child_open = package_io._open_windows_child_file_descriptor
    temp_name: str | None = None
    symlink_setup_completed = False

    def swap_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal temp_name, symlink_setup_completed
        target = Path(path)
        if temp_name is None and target.name.endswith(".journal.tmp"):
            temp_name = target.name
            try:
                target.parent.rename(
                    target.parent.with_name("transactions-owned-moved")
                )
            except PermissionError as error:
                if getattr(error, "winerror", None) in {5, 32}:
                    pytest.skip(f"directory swap unavailable: {error}")
                raise
            _make_symlink(
                external,
                target.parent,
                target_is_directory=True,
            )
            symlink_setup_completed = True
        return original_open(
            path,
            flags,
            mode,
            **({"dir_fd": dir_fd} if dir_fd is not None else {}),
        )

    def swap_then_child_open(
        target: Path,
        *,
        create: bool,
        write: bool,
    ) -> int:
        nonlocal temp_name, symlink_setup_completed
        if temp_name is None and target.name.endswith(".journal.tmp"):
            temp_name = target.name
            try:
                target.parent.rename(
                    target.parent.with_name("transactions-owned-moved")
                )
            except PermissionError as error:
                if getattr(error, "winerror", None) in {5, 32}:
                    pytest.skip(f"directory swap unavailable: {error}")
                raise
            _make_symlink(
                external,
                target.parent,
                target_is_directory=True,
            )
            symlink_setup_completed = True
        return original_child_open(
            target,
            create=create,
            write=write,
        )

    monkeypatch.setattr(os, "open", swap_then_open)
    monkeypatch.setattr(
        package_io,
        "_open_windows_child_file_descriptor",
        swap_then_child_open,
    )

    with pytest.raises((OSError, ValueError)):
        publish_configure_run(rendered_runs[0], output_root)

    assert symlink_setup_completed, "symlink setup did not complete"
    assert temp_name is not None
    assert not (external / temp_name).exists()


def test_identical_publish_is_a_physical_no_op(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    first = publish_configure_run(rendered_runs[0], output_root)
    pointer = output_root / "current.json"
    before = pointer.stat()
    journals_before = tuple(
        (output_root / ".publisher" / "transactions").iterdir()
    )

    repeated = publish_configure_run(rendered_runs[0], output_root)

    after = pointer.stat()
    assert repeated.reused_existing_revision
    assert repeated.revision_root == first.revision_root
    assert (before.st_ino, before.st_mtime_ns) == (
        after.st_ino,
        after.st_mtime_ns,
    )
    assert tuple(
        (output_root / ".publisher" / "transactions").iterdir()
    ) == journals_before
    assert not any(
        item.name.startswith(".staging-")
        for item in (output_root / "revisions").iterdir()
    )


def test_staging_symlink_cannot_write_outside_output_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    import hsconfig.output_publisher as publisher

    output_root = tmp_path / "ShadowPriest"
    external = tmp_path / "external"
    external.mkdir()
    victim = external / "input.json"
    victim.write_bytes(b"foreign")
    original = publisher._write_rendered_run

    def inject(rendered: RenderedConfigureRun, staging: Path) -> None:
        _make_symlink(
            external,
            staging / "01_manifest",
            target_is_directory=True,
        )
        original(rendered, staging)

    monkeypatch.setattr(publisher, "_write_rendered_run", inject)
    with pytest.raises(ValueError):
        publish_configure_run(rendered_runs[0], output_root)
    assert victim.read_bytes() == b"foreign"


def test_staging_hardlink_cannot_truncate_external_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    import hsconfig.output_publisher as publisher

    output_root = tmp_path / "ShadowPriest"
    victim = tmp_path / "victim.json"
    victim.write_bytes(b"foreign")
    original = publisher._write_rendered_run

    def inject(rendered: RenderedConfigureRun, staging: Path) -> None:
        directory = staging / "01_manifest"
        directory.mkdir()
        try:
            os.link(victim, directory / "input.json")
        except OSError:
            pytest.skip("hard links unavailable")
        original(rendered, staging)

    monkeypatch.setattr(publisher, "_write_rendered_run", inject)
    with pytest.raises((FileExistsError, ValueError)):
        publish_configure_run(rendered_runs[0], output_root)
    assert victim.read_bytes() == b"foreign"


def test_staging_parent_swap_cannot_create_external_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    if os.name != "nt":
        pytest.skip("Windows ancestor-lease child-open regression")
    import hsconfig.package_io as package_io
    import hsconfig.output_publisher as publisher

    output_root = tmp_path / "ShadowPriest"
    external = tmp_path / "external"
    external.mkdir()
    original_os_open = os.open
    original_relative_open = getattr(
        package_io,
        "_open_windows_child_file_descriptor",
    )
    swapped = False
    symlink_setup_completed = False

    def swap_parent(target: Path) -> None:
        nonlocal swapped, symlink_setup_completed
        if swapped:
            return
        swapped = True
        moved = target.parent.with_name("01_manifest-owned-moved")
        try:
            target.parent.rename(moved)
        except PermissionError as error:
            if getattr(error, "winerror", None) in {5, 32}:
                pytest.skip(f"directory swap unavailable: {error}")
            raise
        _make_symlink(
            external,
            target.parent,
            target_is_directory=True,
        )
        symlink_setup_completed = True

    def swap_then_os_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        target = Path(path)
        if (
            not swapped
            and target.name == "input.json"
            and target.parent.name == "01_manifest"
            and ".staging-" in str(target)
        ):
            swap_parent(target)
        return original_os_open(
            path,
            flags,
            mode,
            **({"dir_fd": dir_fd} if dir_fd is not None else {}),
        )

    def swap_then_relative_open(
        target: Path,
        *,
        create: bool,
        write: bool,
    ) -> int:
        if (
            not swapped
            and target.name == "input.json"
            and target.parent.name == "01_manifest"
            and ".staging-" in str(target)
        ):
            swap_parent(target)
        return original_relative_open(
            target,
            create=create,
            write=write,
        )

    monkeypatch.setattr(os, "open", swap_then_os_open)
    monkeypatch.setattr(
        package_io,
        "_open_windows_child_file_descriptor",
        swap_then_relative_open,
    )

    with pytest.raises((OSError, ValueError)):
        publisher.publish_configure_run(rendered_runs[0], output_root)

    assert symlink_setup_completed, "symlink setup did not complete"
    assert swapped
    assert not (external / "input.json").exists()


def test_staging_higher_ancestor_swap_cannot_escape_lease_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    if os.name != "nt":
        pytest.skip("Windows ancestor-lease child-open regression")
    import hsconfig.package_io as package_io

    output_root = tmp_path / "ShadowPriest"
    external = tmp_path / "external-revisions"
    external.mkdir()
    original_child_open = package_io._open_windows_child_file_descriptor
    attempted = False
    symlink_setup_completed = False

    def swap_then_child_open(
        target: Path,
        *,
        create: bool,
        write: bool,
    ) -> int:
        nonlocal attempted, symlink_setup_completed
        if (
            not attempted
            and target.name == "input.json"
            and target.parent.name == "01_manifest"
            and ".staging-" in str(target)
        ):
            attempted = True
            revisions = target.parents[2]
            try:
                revisions.rename(
                    revisions.with_name("revisions-owned-moved")
                )
            except PermissionError as error:
                if getattr(error, "winerror", None) in {5, 32}:
                    pytest.skip(f"directory swap unavailable: {error}")
                raise
            _make_symlink(
                external,
                revisions,
                target_is_directory=True,
            )
            symlink_setup_completed = True
        return original_child_open(
            target,
            create=create,
            write=write,
        )

    monkeypatch.setattr(
        package_io,
        "_open_windows_child_file_descriptor",
        swap_then_child_open,
    )

    with pytest.raises((OSError, ValueError)):
        publish_configure_run(rendered_runs[0], output_root)

    assert symlink_setup_completed, "symlink setup did not complete"
    assert attempted
    assert tuple(external.iterdir()) == ()


def test_symlinked_existing_ancestor_is_rejected_before_mutation(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    alias = tmp_path / "outputs-alias"
    _make_symlink(
        external,
        alias,
        target_is_directory=True,
    )

    with pytest.raises(ValueError):
        publish_configure_run(rendered_runs[0], alias / "ShadowPriest")
    assert tuple(external.iterdir()) == ()


def test_dangling_lock_symlink_cannot_create_external_target(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    output_root.mkdir()
    external = tmp_path / "external-lock"
    _make_symlink(
        external,
        output_root / ".publish.lock",
        target_is_directory=False,
    )

    with pytest.raises(ValueError):
        publish_configure_run(rendered_runs[0], output_root)
    assert not external.exists()
    assert {path.name for path in output_root.iterdir()} == {
        ".publish.lock"
    }


def test_reconcile_removes_separately_owned_noncurrent_revision(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    primary_root = tmp_path / "primary" / "ShadowPriest"
    secondary_root = tmp_path / "secondary" / "ShadowPriest"
    current = publish_configure_run(rendered_runs[0], primary_root)
    noncurrent = publish_configure_run(rendered_runs[1], secondary_root)
    primary_transactions = (
        primary_root / ".publisher" / "transactions"
    )
    secondary_transaction = next(
        (secondary_root / ".publisher" / "transactions").iterdir()
    )
    moved_revision = (
        primary_root / "revisions" / noncurrent.revision_root.name
    )
    moved_journal = primary_transactions / secondary_transaction.name
    noncurrent.revision_root.rename(moved_revision)
    secondary_transaction.rename(moved_journal)

    reconciled = reconcile_output(primary_root)

    assert reconciled is not None
    assert reconciled.revision_root == current.revision_root
    assert tuple(
        path.name for path in (primary_root / "revisions").iterdir()
    ) == (current.revision_root.name,)
    journals = tuple(primary_transactions.iterdir())
    assert len(journals) == 1
    assert noncurrent.content_root_sha256 not in journals[0].read_text(
        encoding="utf-8"
    )


def test_reconcile_resumes_detached_cleanup_after_coordinator_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    import hsconfig.output_publisher as publisher

    primary_root = tmp_path / "primary" / "ShadowPriest"
    secondary_root = tmp_path / "secondary" / "ShadowPriest"
    current = publish_configure_run(rendered_runs[0], primary_root)
    noncurrent = publish_configure_run(rendered_runs[1], secondary_root)
    primary_transactions = (
        primary_root / ".publisher" / "transactions"
    )
    secondary_transaction = next(
        (secondary_root / ".publisher" / "transactions").iterdir()
    )
    noncurrent.revision_root.rename(
        primary_root / "revisions" / noncurrent.revision_root.name
    )
    secondary_transaction.rename(
        primary_transactions / secondary_transaction.name
    )
    write_transaction = publisher._write_transaction
    interrupted = False

    def interrupt_after_coordinator_commit(
        path: Path,
        transaction: object,
        *,
        fault_hook: object = publisher.no_fault,
    ) -> None:
        nonlocal interrupted
        write_transaction(
            path,
            transaction,
            fault_hook=fault_hook,
        )
        if (
            not interrupted
            and not transaction.owns_revision
            and transaction.phase == "pointer_committed"
            and transaction.previous_revision is not None
        ):
            interrupted = True
            raise SystemExit("after_coordinator_commit")

    monkeypatch.setattr(
        publisher,
        "_write_transaction",
        interrupt_after_coordinator_commit,
    )

    with pytest.raises(SystemExit, match="after_coordinator_commit"):
        reconcile_output(primary_root)

    assert interrupted
    assert noncurrent.revision_root.name in {
        path.name for path in (primary_root / "revisions").iterdir()
    }

    reconciled = reconcile_output(primary_root)

    assert reconciled is not None
    assert reconciled.revision_root == current.revision_root
    assert tuple(
        path.name for path in (primary_root / "revisions").iterdir()
    ) == (current.revision_root.name,)
    assert len(tuple(primary_transactions.iterdir())) == 1


@pytest.mark.parametrize(
    "checkpoint",
    (
        "during_tree_delete",
        "before_owner_unlink",
        "after_owner_unlink",
    ),
)
def test_reconcile_resumes_detached_cleanup_across_delete_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
    checkpoint: str,
) -> None:
    import hsconfig.output_publisher as publisher

    primary_root = tmp_path / "primary" / "ShadowPriest"
    secondary_root = tmp_path / "secondary" / "ShadowPriest"
    current = publish_configure_run(rendered_runs[0], primary_root)
    noncurrent = publish_configure_run(rendered_runs[1], secondary_root)
    primary_transactions = (
        primary_root / ".publisher" / "transactions"
    )
    secondary_transaction = next(
        (secondary_root / ".publisher" / "transactions").iterdir()
    )
    moved_revision = (
        primary_root / "revisions" / noncurrent.revision_root.name
    )
    moved_owner = primary_transactions / secondary_transaction.name
    noncurrent.revision_root.rename(moved_revision)
    secondary_transaction.rename(moved_owner)
    remove_owned_tree = publisher._remove_owned_tree
    remove_file_if_plain = publisher._remove_file_if_plain
    interrupted = False

    def interrupt_tree_delete(
        path: Path,
        *,
        expected_identity: tuple[int, int, int],
        after_first_delete: object = publisher.no_fault,
    ) -> None:
        nonlocal interrupted
        if (
            checkpoint == "during_tree_delete"
            and not interrupted
            and path == moved_revision
        ):
            def stop_after_first_delete() -> None:
                nonlocal interrupted
                interrupted = True
                raise SystemExit(checkpoint)

            remove_owned_tree(
                path,
                expected_identity=expected_identity,
                after_first_delete=stop_after_first_delete,
            )
            return
        remove_owned_tree(
            path,
            expected_identity=expected_identity,
            after_first_delete=after_first_delete,
        )

    def interrupt_owner_unlink(path: Path) -> None:
        nonlocal interrupted
        if (
            checkpoint in {"before_owner_unlink", "after_owner_unlink"}
            and not interrupted
            and path == moved_owner
        ):
            interrupted = True
            if checkpoint == "after_owner_unlink":
                remove_file_if_plain(path)
            raise SystemExit(checkpoint)
        remove_file_if_plain(path)

    monkeypatch.setattr(
        publisher,
        "_remove_owned_tree",
        interrupt_tree_delete,
    )
    monkeypatch.setattr(
        publisher,
        "_remove_file_if_plain",
        interrupt_owner_unlink,
    )

    with pytest.raises(SystemExit, match=checkpoint):
        reconcile_output(primary_root)

    assert interrupted
    assert len(tuple(primary_transactions.iterdir())) >= 1

    reconciled = reconcile_output(primary_root)

    assert reconciled is not None
    assert reconciled.revision_root == current.revision_root
    assert tuple(
        path.name for path in (primary_root / "revisions").iterdir()
    ) == (current.revision_root.name,)
    journals = tuple(primary_transactions.iterdir())
    assert len(journals) == 1
    assert current.content_root_sha256 in journals[0].read_text(
        encoding="utf-8"
    )


def test_multiple_revision_owner_journals_fail_closed(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    import hsconfig.output_publisher as publisher

    output_root = tmp_path / "ShadowPriest"
    published = publish_configure_run(rendered_runs[0], output_root)
    transactions = output_root / ".publisher" / "transactions"
    original_path = next(transactions.iterdir())
    original = publisher._parse_transaction(original_path.read_bytes())
    duplicate_id = "0" * 32
    if original.transaction_id == duplicate_id:
        duplicate_id = "1" * 32
    duplicate = replace(
        original,
        transaction_id=duplicate_id,
        staging=f"revisions/.staging-{duplicate_id}",
    )
    duplicate_path = transactions / f"{duplicate_id}.json"
    duplicate_path.write_bytes(publisher._transaction_bytes(duplicate))
    before = {
        path.name: path.read_bytes()
        for path in transactions.iterdir()
    }

    with pytest.raises(ValueError, match="publisher_.*owner"):
        publisher.reconcile_output(output_root)

    assert published.revision_root.is_dir()
    assert {
        path.name: path.read_bytes()
        for path in transactions.iterdir()
    } == before


def _unit_transaction(
    *,
    transaction_id: str = "1" * 32,
    phase: str = "prepared",
    staging_identity: tuple[int, int, int] | None = None,
    revision_identity: tuple[int, int, int] | None = None,
    owns_revision: bool = False,
    previous_revision: str | None = None,
    previous_revision_identity: tuple[int, int, int] | None = None,
    previous_owner_transaction_id: str | None = None,
) -> output_publisher._Transaction:
    digest = "a" * 64
    return output_publisher._Transaction(
        schema_version=1,
        transaction_id=transaction_id,
        deck_name="Deck",
        deck_fingerprint="b" * 64,
        content_root_sha256=digest,
        staging=f"revisions/.staging-{transaction_id}",
        revision=f"revisions/sha256-{digest}",
        previous_revision=previous_revision,
        previous_revision_identity=previous_revision_identity,
        previous_owner_transaction_id=previous_owner_transaction_id,
        staging_identity=staging_identity,
        revision_identity=revision_identity,
        owns_revision=owns_revision,
        phase=phase,
    )


def test_transaction_and_publish_reject_invalid_contract_types(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="publisher_transaction_invalid"):
        replace(_unit_transaction(), phase="unknown")
    with pytest.raises(TypeError, match="rendered_configure_run_required"):
        publish_configure_run(object(), tmp_path)  # type: ignore[arg-type]


def test_reconcile_missing_output_is_none(tmp_path: Path) -> None:
    assert reconcile_output(tmp_path / "missing") is None


def test_finalized_authority_requires_typed_publication(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="output_publication_required"):
        output_publisher.validate_finalized_publication_authority(
            tmp_path,
            object(),  # type: ignore[arg-type]
        )


def test_finalized_authority_rejects_missing_or_inconsistent_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = SimpleNamespace(
        revision=f"revisions/sha256-{'a' * 64}",
        deck_name="Deck",
        deck_fingerprint="b" * 64,
        content_root_sha256="a" * 64,
    )
    monkeypatch.setattr(output_publisher, "OutputPublication", SimpleNamespace)
    monkeypatch.setattr(output_publisher, "_load_valid_transactions", lambda _root: [])
    with pytest.raises(ValueError, match="finalized_authority_invalid"):
        output_publisher.validate_finalized_publication_authority(tmp_path, publication)  # type: ignore[arg-type]

    owner = _unit_transaction(
        phase="revision_ready",
        revision_identity=(1, 2, 3),
        owns_revision=True,
    )
    monkeypatch.setattr(
        output_publisher,
        "_load_valid_transactions",
        lambda _root: [(Path("journal"), owner)],
    )
    monkeypatch.setattr(output_publisher, "path_identity", lambda _path: (1, 2, 3))
    with pytest.raises(ValueError, match="finalized_authority_invalid"):
        output_publisher.validate_finalized_publication_authority(tmp_path, publication)  # type: ignore[arg-type]


def test_parse_transaction_rejects_noncanonical_and_invalid_identity() -> None:
    transaction = _unit_transaction()
    canonical = output_publisher._transaction_bytes(transaction)
    payload = json.loads(canonical)
    payload["previous_revision_identity"] = [1, -1, 3]
    invalid_identity = json.dumps(payload, sort_keys=True).encode()
    with pytest.raises(ValueError, match="identity_invalid"):
        output_publisher._parse_transaction(invalid_identity)

    noncanonical = json.dumps(json.loads(canonical), separators=(",", ":")).encode()
    with pytest.raises(ValueError, match="transaction_noncanonical"):
        output_publisher._parse_transaction(noncanonical)


def test_remove_file_if_plain_handles_missing_and_nonfile(tmp_path: Path) -> None:
    output_publisher._remove_file_if_plain(tmp_path / "missing")
    directory = tmp_path / "directory"
    directory.mkdir()
    output_publisher._remove_file_if_plain(directory)
    assert directory.is_dir()


def test_canonical_revision_identity_phase_and_json_helpers() -> None:
    assert output_publisher._canonical_revision(None) is False
    transaction = _unit_transaction()
    values = {
        field: getattr(transaction, field)
        for field in transaction.__dataclass_fields__
    }
    invalid_bound = SimpleNamespace(**values)
    invalid_bound.previous_revision_identity = (1, 2, 3)
    assert output_publisher._valid_phase_state(invalid_bound) is False
    with pytest.raises(ValueError, match="duplicate_json_key"):
        output_publisher._unique_json_object([("key", 1), ("key", 2)])


def test_write_transaction_calls_generic_and_phase_specific_fault_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction = _unit_transaction()
    stages: list[str] = []

    def fake_atomic_replace(
        _path: Path,
        _content: bytes,
        *,
        fault_hook: object,
        **_kwargs: object,
    ) -> None:
        fault_hook("before_temp_write")  # type: ignore[operator]
        fault_hook("after_journal_temp_write")  # type: ignore[operator]

    monkeypatch.setattr(output_publisher, "_owned_atomic_replace", fake_atomic_replace)
    output_publisher._write_transaction(
        tmp_path / "journal.json",
        transaction,
        fault_hook=stages.append,
    )
    assert stages == [
        "before_temp_write",
        "after_journal_temp_write",
        "after_journal_prepared_temp_write",
    ]


def test_exact_directory_entries_rejects_count_file_and_reparse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = tmp_path / "child"
    child.write_bytes(b"x")
    with pytest.raises(ValueError, match="residue_count_limit"):
        output_publisher._require_exact_directory_entries(
            tmp_path,
            allowed={"child"},
            maximum=0,
        )
    with pytest.raises(ValueError, match="revision_residue_invalid"):
        output_publisher._require_exact_directory_entries(
            tmp_path,
            allowed={"child"},
            maximum=2,
            directories_only=True,
        )
    monkeypatch.setattr(output_publisher, "status_is_reparse", lambda _status: True)
    with pytest.raises(ValueError, match="residue_reparse"):
        output_publisher._require_exact_directory_entries(
            tmp_path,
            allowed={"child"},
            maximum=2,
        )


def test_exact_directory_entries_rejects_casefold_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = tmp_path / "child"
    child.mkdir()
    entries = [
        SimpleNamespace(name="Name", path=str(child)),
        SimpleNamespace(name="name", path=str(child)),
    ]

    class FakeScandir:
        def __enter__(self) -> object:
            return iter(entries)

        def __exit__(self, *_args: object) -> None:
            pass

    monkeypatch.setattr(output_publisher.os, "scandir", lambda _path: FakeScandir())
    with pytest.raises(ValueError, match="casefold_collision"):
        output_publisher._require_exact_directory_entries(
            tmp_path,
            allowed=set(),
            maximum=3,
        )


@pytest.mark.parametrize(
    "mode",
    ("staging_exists", "revision_mismatch", "verify_error", "manifest_mismatch", "success"),
)
def test_recover_interrupted_revision_move_handles_all_observable_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    identity = (1, 2, 3)
    transaction = _unit_transaction(
        phase="staging_verified",
        staging_identity=identity,
    )
    staging = tmp_path / transaction.staging

    def probe(path: Path) -> tuple[int, int, int]:
        if path == staging:
            if mode == "staging_exists":
                return identity
            raise FileNotFoundError()
        if mode == "revision_mismatch":
            return (1, 9, 3)
        return identity

    manifest = SimpleNamespace(
        content_root_sha256="wrong" if mode == "manifest_mismatch" else transaction.content_root_sha256,
        deck_name=transaction.deck_name,
        deck_fingerprint=transaction.deck_fingerprint,
    )
    monkeypatch.setattr(output_publisher, "path_identity", probe)
    if mode == "verify_error":
        monkeypatch.setattr(
            output_publisher,
            "snapshot_and_verify_revision",
            lambda _path: (_ for _ in ()).throw(ValueError("verify")),
        )
    else:
        monkeypatch.setattr(
            output_publisher,
            "snapshot_and_verify_revision",
            lambda _path: SimpleNamespace(manifest=manifest),
        )
    written: list[output_publisher._Transaction] = []
    monkeypatch.setattr(output_publisher, "_write_transaction", lambda _path, row: written.append(row))
    result = output_publisher._recover_interrupted_revision_move(
        tmp_path,
        Path("journal"),
        transaction,
    )
    if mode == "success":
        assert result.phase == "revision_ready"
        assert written == [result]
    else:
        assert result == transaction


@pytest.mark.parametrize("owner_found", (False, True))
def test_cleanup_after_commit_finalizes_or_adopts_existing_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    owner_found: bool,
) -> None:
    identity = (1, 2, 3)
    transaction = _unit_transaction(
        phase="revision_ready",
        revision_identity=identity,
        owns_revision=False,
    )
    owner = _unit_transaction(
        transaction_id="2" * 32,
        phase="finalized",
        revision_identity=identity,
        owns_revision=True,
    )
    journal = tmp_path / "journal"
    rows = [(tmp_path / "owner", owner)] if owner_found else []
    removed: list[Path] = []
    written: list[output_publisher._Transaction] = []
    monkeypatch.setattr(output_publisher, "_load_valid_transactions", lambda _root: rows)
    monkeypatch.setattr(output_publisher, "_remove_file_if_plain", removed.append)
    monkeypatch.setattr(
        output_publisher,
        "_write_transaction",
        lambda _path, row, **_kwargs: written.append(row),
    )
    output_publisher._cleanup_after_commit(
        tmp_path,
        transaction,
        journal,
        fault_hook=output_publisher.no_fault,
    )
    if owner_found:
        assert removed == [journal]
        assert written == []
    else:
        assert written[0].phase == "finalized"


def test_cleanup_after_commit_skips_nonmatching_journal_before_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = (1, 2, 3)
    transaction = _unit_transaction(
        phase="revision_ready",
        revision_identity=identity,
        owns_revision=False,
    )
    owner = _unit_transaction(
        transaction_id="2" * 32,
        phase="finalized",
        revision_identity=identity,
        owns_revision=True,
    )
    journal = tmp_path / "journal"
    rows = [(journal, transaction), (tmp_path / "owner", owner)]
    removed: list[Path] = []
    monkeypatch.setattr(output_publisher, "_load_valid_transactions", lambda _root: rows)
    monkeypatch.setattr(output_publisher, "_remove_file_if_plain", removed.append)
    monkeypatch.setattr(output_publisher, "_write_transaction", lambda *_args, **_kwargs: None)
    output_publisher._cleanup_after_commit(
        tmp_path,
        transaction,
        journal,
        fault_hook=output_publisher.no_fault,
    )
    assert removed == [journal]


def test_continue_cleanup_returns_when_no_distinct_previous_revision(
    tmp_path: Path,
) -> None:
    transaction = _unit_transaction()
    assert output_publisher._continue_or_prepare_old_cleanup(
        tmp_path,
        transaction,
        Path("journal"),
        journals=[],
        fault_hook=output_publisher.no_fault,
    ) == transaction


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("started_missing_owner", "cleanup_owner_missing"),
        ("started_identity_change", "cleanup_identity_changed"),
        ("ambiguous", "cleanup_owner_ambiguous"),
        ("manifest", "cleanup_manifest_mismatch"),
    ),
)
def test_continue_cleanup_rejects_ambiguous_or_changed_old_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    message: str,
) -> None:
    identity = (1, 2, 3)
    previous = f"revisions/sha256-{'c' * 64}"
    owner = replace(
        _unit_transaction(
            transaction_id="2" * 32,
            phase="finalized",
            revision_identity=identity,
            owns_revision=True,
        ),
        content_root_sha256="c" * 64,
        revision=previous,
    )
    if mode.startswith("started"):
        transaction = _unit_transaction(
            phase="cleanup_started",
            revision_identity=(4, 5, 6),
            previous_revision=previous,
            previous_revision_identity=identity,
            previous_owner_transaction_id=owner.transaction_id,
        )
        journals = [] if mode == "started_missing_owner" else [(Path("owner"), owner)]
    else:
        transaction = _unit_transaction(
            phase="pointer_committed",
            revision_identity=(4, 5, 6),
            previous_revision=previous,
        )
        journals = [] if mode == "ambiguous" else [(Path("owner"), owner)]
    monkeypatch.setattr(
        output_publisher,
        "path_identity",
        lambda _path: (1, 9, 3) if mode == "started_identity_change" else identity,
    )
    monkeypatch.setattr(
        output_publisher,
        "snapshot_and_verify_revision",
        lambda _path: SimpleNamespace(
            manifest=SimpleNamespace(
                content_root_sha256="wrong",
                deck_name=owner.deck_name,
                deck_fingerprint=owner.deck_fingerprint,
            )
        ),
    )
    with pytest.raises(ValueError, match=message):
        output_publisher._continue_or_prepare_old_cleanup(
            tmp_path,
            transaction,
            Path("journal"),
            journals=journals,
            fault_hook=output_publisher.no_fault,
        )


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        ("no_identity", False),
        ("missing", True),
        ("identity", False),
        ("verify_error", False),
        ("digest", False),
        ("success", True),
    ),
)
def test_remove_owned_tree_if_present_returns_verified_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected: bool,
) -> None:
    identity = (1, 2, 3)
    expected_identity = None if mode == "no_identity" else identity
    if mode == "missing":
        monkeypatch.setattr(
            output_publisher,
            "path_identity",
            lambda _path: (_ for _ in ()).throw(FileNotFoundError()),
        )
    else:
        monkeypatch.setattr(
            output_publisher,
            "path_identity",
            lambda _path: (1, 9, 3) if mode == "identity" else identity,
        )
    if mode == "verify_error":
        monkeypatch.setattr(
            output_publisher,
            "snapshot_and_verify_revision",
            lambda _path: (_ for _ in ()).throw(ValueError("verify")),
        )
    else:
        monkeypatch.setattr(
            output_publisher,
            "snapshot_and_verify_revision",
            lambda _path: SimpleNamespace(
                manifest=SimpleNamespace(
                    content_root_sha256="wrong" if mode == "digest" else "a" * 64
                )
            ),
        )
    removed: list[Path] = []
    monkeypatch.setattr(
        output_publisher,
        "_remove_owned_tree",
        lambda path, **_kwargs: removed.append(path),
    )
    result = output_publisher._remove_owned_tree_if_present(
        tmp_path / "target",
        expected_identity=expected_identity,
        require_verified_root="a" * 64 if mode in {"verify_error", "digest", "success"} else None,
    )
    assert result is expected
    assert bool(removed) is (mode == "success")


def test_write_rendered_run_requires_one_manifest(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "staging"
    destination.mkdir()
    with pytest.raises(ValueError, match="manifest_missing"):
        output_publisher._write_rendered_run(
            SimpleNamespace(artifacts=()),  # type: ignore[arg-type]
            destination,
        )


def test_owned_atomic_replace_rejects_preexisting_temp(tmp_path: Path) -> None:
    target = tmp_path / "target"
    temp = tmp_path / "temp"
    temp.write_bytes(b"owned")
    with pytest.raises(ValueError, match="owned_temp_preexisting"):
        output_publisher._owned_atomic_replace(
            target,
            b"content",
            temp_path=temp,
            temp_stage="stage",
        )


class _NoopGuard:
    def validate(self) -> None:
        pass


class _NoopLock:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def __enter__(self) -> _NoopLock:
        return self

    def __exit__(self, *_args: object) -> None:
        pass


@pytest.mark.parametrize(
    "mode",
    (
        "staging_identity",
        "staged_manifest",
        "reuse_existing",
        "existing_conflict",
        "revision_identity",
        "pointer_verification",
    ),
)
def test_publish_detects_internal_contract_failures_and_reuses_digest_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    rendered = build_rendered_run(tmp_path / "source", 1)
    root = tmp_path / "output"
    root.mkdir()
    transaction = output_publisher._new_transaction(rendered, None)
    identity = (1, 2, 3)
    staged_manifest = SimpleNamespace(
        content_root_sha256=(
            "f" * 64 if mode == "staged_manifest" else rendered.content_root_sha256
        ),
        deck_name=rendered.model.deck_name,
        deck_fingerprint=rendered.model.deck_fingerprint,
    )
    publication_rows: list[object] = []
    monkeypatch.setattr(output_publisher, "capture_plain_ancestor_guard", lambda _path: _NoopGuard())
    monkeypatch.setattr(
        output_publisher,
        "_ensure_layout",
        lambda _root, *, output_guard=None: None,
    )
    monkeypatch.setattr(output_publisher, "_capture_layout_guards", lambda _root: ())
    monkeypatch.setattr(output_publisher, "_validate_layout_guards", lambda _guards: None)
    monkeypatch.setattr(output_publisher, "ExclusiveFileLock", _NoopLock)
    monkeypatch.setattr(output_publisher, "_reconcile_locked", lambda _root: None)
    monkeypatch.setattr(output_publisher, "_snapshot_pointer", lambda _root: object())
    monkeypatch.setattr(
        output_publisher,
        "_new_transaction",
        lambda *_args, **_kwargs: transaction,
    )
    monkeypatch.setattr(output_publisher, "_write_transaction", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(output_publisher, "secure_create_directory", lambda *_args, **_kwargs: identity)

    def probe_identity(path: Path) -> tuple[int, int, int]:
        if mode == "staging_identity" and path.name.startswith(".staging-"):
            return (1, 9, 3)
        if mode == "revision_identity" and path.name.startswith("sha256-"):
            return (1, 9, 3)
        return identity

    monkeypatch.setattr(output_publisher, "path_identity", probe_identity)
    monkeypatch.setattr(output_publisher, "_write_rendered_run", lambda *_args: None)
    def snapshot(path: Path) -> SimpleNamespace:
        if mode == "existing_conflict" and path.name.startswith("sha256-"):
            return SimpleNamespace(
                manifest=SimpleNamespace(
                    content_root_sha256="f" * 64,
                    deck_name=rendered.model.deck_name,
                    deck_fingerprint=rendered.model.deck_fingerprint,
                )
            )
        return SimpleNamespace(manifest=staged_manifest)

    monkeypatch.setattr(
        output_publisher,
        "snapshot_and_verify_revision",
        snapshot,
    )
    monkeypatch.setattr(
        output_publisher,
        "path_lexists",
        lambda path: (
            path == root
            or (
                mode in {"reuse_existing", "existing_conflict"}
                and path.name.startswith("sha256-")
            )
        ),
    )
    monkeypatch.setattr(output_publisher, "plain_file_status", lambda _path: None)
    monkeypatch.setattr(output_publisher, "require_plain_directory", lambda _path: None)
    monkeypatch.setattr(output_publisher, "_remove_owned_tree", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(output_publisher, "secure_replace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(output_publisher, "_replace_pointer_if_unchanged", lambda *_args, **_kwargs: None)

    def resolve(_root: Path) -> tuple[object, object]:
        publication = output_publisher.OutputPublication(
            schema_version=output_publisher.CURRENT_SCHEMA_VERSION,
            deck_name=("Wrong" if mode == "pointer_verification" else rendered.model.deck_name),
            deck_fingerprint=rendered.model.deck_fingerprint,
            revision=transaction.revision,
            content_root_sha256=rendered.content_root_sha256,
        )
        publication_rows.append(publication)
        return publication, object()

    monkeypatch.setattr(
        output_publisher,
        "_resolve_current_publication_without_ads",
        resolve,
    )
    monkeypatch.setattr(output_publisher, "_cleanup_after_commit", lambda *_args, **_kwargs: None)
    expected_errors = {
        "staging_identity": "staging_identity_mismatch",
        "staged_manifest": "staged_revision_identity_mismatch",
        "existing_conflict": "digest_target_conflict",
        "revision_identity": "revision_identity_mismatch",
        "pointer_verification": "pointer_verification_failed",
    }
    if mode in expected_errors:
        with pytest.raises(ValueError, match=expected_errors[mode]):
            output_publisher._publish_configure_run_unwrapped(rendered, root)
    else:
        result = output_publisher._publish_configure_run_unwrapped(
            rendered,
            root,
        )
        assert result.reused_existing_revision is True


def test_finalized_authority_accepts_exact_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = (1, 2, 3)
    owner = _unit_transaction(
        phase="finalized",
        revision_identity=identity,
        owns_revision=True,
    )
    publication = output_publisher.OutputPublication(
        schema_version=output_publisher.CURRENT_SCHEMA_VERSION,
        deck_name=owner.deck_name,
        deck_fingerprint=owner.deck_fingerprint,
        revision=owner.revision,
        content_root_sha256=owner.content_root_sha256,
    )
    monkeypatch.setattr(output_publisher, "_load_valid_transactions", lambda _root: [(Path("journal"), owner)])
    monkeypatch.setattr(output_publisher, "path_identity", lambda _path: identity)
    output_publisher.validate_finalized_publication_authority(tmp_path, publication)


def test_reconcile_rejects_incomplete_owned_staging_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _unit_transaction(
        phase="finalized",
        revision_identity=(1, 2, 3),
        owns_revision=True,
    )
    publication = output_publisher.OutputPublication(
        schema_version=output_publisher.CURRENT_SCHEMA_VERSION,
        deck_name=owner.deck_name,
        deck_fingerprint=owner.deck_fingerprint,
        revision=owner.revision,
        content_root_sha256=owner.content_root_sha256,
    )
    monkeypatch.setattr(output_publisher, "path_lexists", lambda _path: True)
    monkeypatch.setattr(
        output_publisher,
        "_resolve_current_publication_without_ads",
        lambda _root: (publication, object()),
    )
    monkeypatch.setattr(output_publisher, "_recover_owned_atomic_temps", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(output_publisher, "_load_valid_transactions", lambda _root: [(Path("journal"), owner)])
    monkeypatch.setattr(output_publisher, "_validate_publisher_residue", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(output_publisher, "_recover_interrupted_revision_move", lambda *_args: owner)
    monkeypatch.setattr(output_publisher, "_cleanup_staging_if_owned", lambda *_args: False)
    with pytest.raises(ValueError, match="staging_cleanup_incomplete"):
        output_publisher._reconcile_locked(tmp_path)


def test_remove_owned_tree_rejects_root_identity_change(tmp_path: Path) -> None:
    root = tmp_path / "owned"
    root.mkdir()
    identity = output_publisher.path_identity(root)
    with pytest.raises(ValueError, match="owned_path_identity_changed"):
        output_publisher._remove_owned_tree(
            root,
            expected_identity=(identity[0], identity[1] + 1, identity[2]),
        )


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("root_reparse", "owned_path_reparse"),
        ("child_reparse", "owned_path_reparse"),
        ("invalid_name", "owned_path_invalid"),
        ("invalid_entry", "owned_path_entry_invalid"),
        ("disappears", None),
        ("identity_change", "owned_path_identity_changed"),
        ("type_change", "owned_path_identity_changed"),
        ("final_identity", "owned_path_identity_changed"),
    ),
)
def test_remove_owned_tree_handles_hostile_inventory_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    message: str | None,
) -> None:
    root = tmp_path / "owned"
    root.mkdir()
    child = root / "file"
    child.write_bytes(b"x")
    identity = output_publisher.path_identity(root)
    real_lstat = Path.lstat
    child_lstats = 0

    def hostile_lstat(path: Path) -> object:
        nonlocal child_lstats
        status = real_lstat(path)
        if path == child:
            child_lstats += 1
            if mode == "disappears" and child_lstats == 2:
                os.unlink(child)
                raise FileNotFoundError()
            if mode in {"identity_change", "type_change"} and child_lstats == 2:
                return SimpleNamespace(
                    st_dev=status.st_dev,
                    st_ino=status.st_ino + (1 if mode == "identity_change" else 0),
                    st_mode=(0 if mode == "type_change" else status.st_mode),
                    st_nlink=status.st_nlink,
                    st_size=status.st_size,
                    st_file_attributes=0,
                )
            if mode == "invalid_entry" and child_lstats == 1:
                return SimpleNamespace(
                    st_dev=status.st_dev,
                    st_ino=status.st_ino,
                    st_mode=0,
                    st_nlink=status.st_nlink,
                    st_size=status.st_size,
                    st_file_attributes=0,
                )
        return status

    monkeypatch.setattr(Path, "lstat", hostile_lstat)
    reparse_calls = 0

    def hostile_reparse(_status: object) -> bool:
        nonlocal reparse_calls
        reparse_calls += 1
        return (
            (mode == "root_reparse" and reparse_calls == 1)
            or (mode == "child_reparse" and reparse_calls == 2)
        )

    monkeypatch.setattr(output_publisher, "status_is_reparse", hostile_reparse)
    if mode == "invalid_name":
        monkeypatch.setattr(output_publisher, "canonical_relative_path", lambda _value: "different")
    real_path_identity = output_publisher.path_identity
    root_probes = 0

    def final_identity(path: Path) -> tuple[int, int, int]:
        nonlocal root_probes
        result = real_path_identity(path)
        if path == root:
            root_probes += 1
            if mode == "final_identity" and root_probes == 3:
                return (result[0], result[1] + 1, result[2])
        return result

    monkeypatch.setattr(output_publisher, "path_identity", final_identity)
    if message is not None:
        with pytest.raises(ValueError, match=message):
            output_publisher._remove_owned_tree(root, expected_identity=identity)
    else:
        output_publisher._remove_owned_tree(root, expected_identity=identity)
        assert not root.exists()


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("root_before", "staging_identity_changed"),
        ("file_identity", "staging_file_identity_invalid"),
        ("path_changed", "staging_path_changed"),
        ("write_failed", "staging_write_failed"),
        ("final_root", "staging_identity_changed"),
    ),
)
def test_write_rendered_run_detects_identity_and_write_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    message: str,
) -> None:
    destination = tmp_path / "staging"
    destination.mkdir()
    artifact = SimpleNamespace(
        relative_path="package_manifest.json",
        content=b"manifest",
    )
    rendered = SimpleNamespace(artifacts=(artifact,))
    root_identity = output_publisher.path_identity(destination)
    target = destination / artifact.relative_path
    real_path_identity = output_publisher.path_identity
    root_calls = 0

    def probe_identity(path: Path) -> tuple[int, int, int]:
        nonlocal root_calls
        result = real_path_identity(path)
        if path == destination:
            root_calls += 1
            if mode == "root_before" and root_calls == 2:
                return (result[0], result[1] + 1, result[2])
            if mode == "final_root" and root_calls == 5:
                return (result[0], result[1] + 1, result[2])
        if mode == "path_changed" and path == target:
            return (result[0], result[1] + 1, result[2])
        return result

    monkeypatch.setattr(output_publisher, "path_identity", probe_identity)
    if mode == "file_identity":
        real_status_identity = output_publisher.path_identity_from_status
        status_calls = 0

        def changed_status(status: os.stat_result) -> tuple[int, int, int]:
            nonlocal status_calls
            status_calls += 1
            result = real_status_identity(status)
            if status_calls == 2:
                return (result[0], result[1] + 1, result[2])
            return result

        monkeypatch.setattr(output_publisher, "path_identity_from_status", changed_status)
    if mode == "write_failed":
        monkeypatch.setattr(output_publisher, "read_file_no_follow", lambda *_args, **_kwargs: b"wrong")
    with pytest.raises(ValueError, match=message):
        output_publisher._write_rendered_run(rendered, destination)  # type: ignore[arg-type]
    assert root_identity == real_path_identity(destination)


@pytest.mark.parametrize("mode", ("created", "owned"))
def test_write_rendered_run_rejects_changed_nested_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    destination = tmp_path / "staging"
    destination.mkdir()
    artifacts = (
        SimpleNamespace(relative_path="nested/a.json", content=b"a"),
        SimpleNamespace(relative_path="nested/b.json", content=b"b"),
        SimpleNamespace(relative_path="package_manifest.json", content=b"m"),
    )
    nested = destination / "nested"
    real_identity = output_publisher.path_identity
    nested_calls = 0

    def changed_nested(path: Path) -> tuple[int, int, int]:
        nonlocal nested_calls
        result = real_identity(path)
        if path == nested:
            nested_calls += 1
            if (mode == "created" and nested_calls == 1) or (
                mode == "owned" and nested_calls >= 4
            ):
                return (result[0], result[1] + 1, result[2])
        return result

    monkeypatch.setattr(output_publisher, "path_identity", changed_nested)
    with pytest.raises(ValueError, match="staging_directory_changed"):
        output_publisher._write_rendered_run(
            SimpleNamespace(artifacts=artifacts),  # type: ignore[arg-type]
            destination,
        )


def test_write_rendered_run_rejects_preexisting_target(tmp_path: Path) -> None:
    destination = tmp_path / "staging"
    destination.mkdir()
    target = destination / "package_manifest.json"
    target.write_bytes(b"existing")
    with pytest.raises(ValueError, match="staging_path_preexisting"):
        output_publisher._write_rendered_run(
            SimpleNamespace(
                artifacts=(
                    SimpleNamespace(
                        relative_path="package_manifest.json",
                        content=b"manifest",
                    ),
                )
            ),  # type: ignore[arg-type]
            destination,
        )


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("identity", "owned_temp_identity_invalid"),
        ("verification", "owned_temp_verification_failed"),
    ),
)
def test_owned_atomic_replace_detects_temp_identity_or_content_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    message: str,
) -> None:
    target = tmp_path / "target"
    temp = tmp_path / "temp"
    if mode == "identity":
        real_identity = output_publisher.path_identity_from_status
        calls = 0

        def changed(status: os.stat_result) -> tuple[int, int, int]:
            nonlocal calls
            calls += 1
            result = real_identity(status)
            if calls == 2:
                return (result[0], result[1] + 1, result[2])
            return result

        monkeypatch.setattr(output_publisher, "path_identity_from_status", changed)
    else:
        monkeypatch.setattr(output_publisher, "read_file_no_follow", lambda *_args, **_kwargs: b"wrong")
    with pytest.raises(ValueError, match=message):
        output_publisher._owned_atomic_replace(
            target,
            b"content",
            temp_path=temp,
            temp_stage="stage",
        )


def test_layout_creation_races_are_revalidated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "output"
    root.mkdir()

    def race_child(path: Path, **_kwargs: object) -> None:
        path.mkdir(parents=True, exist_ok=True)
        raise FileExistsError()

    monkeypatch.setattr(output_publisher, "secure_create_directory", race_child)
    output_publisher._ensure_layout(root)
    assert (root / ".publisher" / "transactions").is_dir()

    chain = tmp_path / "chain" / "nested"
    output_publisher._secure_create_directory_chain(chain)
    assert chain.is_dir()


def _transaction_directory(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "output"
    directory = root / ".publisher" / "transactions"
    directory.mkdir(parents=True)
    return root, directory


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("count", "transaction_count_limit"),
        ("invalid_file", "transaction_file_invalid"),
        ("final_name", "transaction_name_mismatch"),
        ("temp_name", "transaction_temp_mismatch"),
        ("residue", "transaction_residue_invalid"),
        ("temp_conflict", "transaction_temp_conflict"),
        ("equal_conflict", "transaction_temp_conflict"),
        ("phase_jump", "transaction_phase_jump"),
        ("pointer_missing", "pointer_temp_owner_missing"),
        ("pointer_mismatch", "pointer_temp_owner_mismatch"),
    ),
)
def test_atomic_temp_recovery_rejects_invalid_residue_and_transitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    message: str,
) -> None:
    root, directory = _transaction_directory(tmp_path)
    transaction = _unit_transaction()
    transaction_id = transaction.transaction_id
    if mode == "count":
        monkeypatch.setattr(output_publisher, "_MAX_TRANSACTION_FILES", 0)
        (directory / "entry").write_bytes(b"x")
    elif mode == "invalid_file":
        (directory / f"{transaction_id}.json").mkdir()
    elif mode == "final_name":
        (directory / f"{'2' * 32}.json").write_bytes(
            output_publisher._transaction_bytes(transaction)
        )
    elif mode == "temp_name":
        (directory / f".{'2' * 32}.journal.tmp").write_bytes(
            output_publisher._transaction_bytes(transaction)
        )
    elif mode == "residue":
        (directory / "unexpected").write_bytes(b"x")
    elif mode in {"temp_conflict", "equal_conflict", "phase_jump"}:
        if mode == "temp_conflict":
            final = transaction
            temp = replace(
                transaction,
                deck_fingerprint="c" * 64,
            )
        elif mode == "equal_conflict":
            final = replace(
                transaction,
                phase="staging_owned",
                staging_identity=(1, 2, 3),
            )
            temp = replace(final, staging_identity=(1, 2, 4))
        else:
            final = transaction
            temp = replace(
                transaction,
                phase="staging_verified",
                staging_identity=(1, 2, 3),
            )
        (directory / f"{transaction_id}.json").write_bytes(
            output_publisher._transaction_bytes(final)
        )
        (directory / f".{transaction_id}.journal.tmp").write_bytes(
            output_publisher._transaction_bytes(temp)
        )
        if mode == "equal_conflict":
            monkeypatch.setattr(
                output_publisher,
                "_same_transaction_identity",
                lambda *_args: True,
            )
    else:
        publication = output_publisher.OutputPublication(
            schema_version=output_publisher.CURRENT_SCHEMA_VERSION,
            deck_name=("Other" if mode == "pointer_mismatch" else transaction.deck_name),
            deck_fingerprint=transaction.deck_fingerprint,
            revision=transaction.revision,
            content_root_sha256=transaction.content_root_sha256,
        )
        if mode == "pointer_mismatch":
            (directory / f"{transaction_id}.json").write_bytes(
                output_publisher._transaction_bytes(transaction)
            )
        (directory / f".{transaction_id}.current.tmp").write_bytes(
            output_publisher.output_publication_bytes(publication)
        )
    monkeypatch.setattr(output_publisher, "_validate_publisher_residue", lambda *_args, **_kwargs: None)
    with pytest.raises(ValueError, match=message):
        output_publisher._recover_owned_atomic_temps(
            root,
            current_revision=None,
        )


def test_atomic_temp_recovery_removes_lower_rank_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, directory = _transaction_directory(tmp_path)
    transaction = _unit_transaction()
    final = replace(
        transaction,
        phase="staging_owned",
        staging_identity=(1, 2, 3),
    )
    temp = transaction
    final_path = directory / f"{transaction.transaction_id}.json"
    temp_path = directory / f".{transaction.transaction_id}.journal.tmp"
    final_path.write_bytes(output_publisher._transaction_bytes(final))
    temp_path.write_bytes(output_publisher._transaction_bytes(temp))
    monkeypatch.setattr(output_publisher, "_validate_publisher_residue", lambda *_args, **_kwargs: None)
    output_publisher._recover_owned_atomic_temps(root, current_revision=None)
    assert final_path.is_file()
    assert not temp_path.exists()


def test_atomic_temp_recovery_removes_identical_rank_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, directory = _transaction_directory(tmp_path)
    transaction = _unit_transaction()
    final_path = directory / f"{transaction.transaction_id}.json"
    temp_path = directory / f".{transaction.transaction_id}.journal.tmp"
    content = output_publisher._transaction_bytes(transaction)
    final_path.write_bytes(content)
    temp_path.write_bytes(content)
    monkeypatch.setattr(output_publisher, "_validate_publisher_residue", lambda *_args, **_kwargs: None)
    output_publisher._recover_owned_atomic_temps(root, current_revision=None)
    assert final_path.read_bytes() == content
    assert not temp_path.exists()


def test_atomic_temp_recovery_promotes_or_replaces_newer_journal_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for mode in ("create", "replace"):
        case_root = tmp_path / mode
        root, directory = _transaction_directory(case_root)
        transaction = _unit_transaction()
        final_path = directory / f"{transaction.transaction_id}.json"
        temp_path = directory / f".{transaction.transaction_id}.journal.tmp"
        if mode == "create":
            temp = transaction
        else:
            final_path.write_bytes(output_publisher._transaction_bytes(transaction))
            temp = replace(
                transaction,
                phase="staging_owned",
                staging_identity=(1, 2, 3),
            )
        temp_path.write_bytes(output_publisher._transaction_bytes(temp))
        monkeypatch.setattr(output_publisher, "_validate_publisher_residue", lambda *_args, **_kwargs: None)
        output_publisher._recover_owned_atomic_temps(root, current_revision=None)
        assert output_publisher._parse_transaction(final_path.read_bytes()) == temp
        assert not temp_path.exists()


def test_atomic_temp_recovery_removes_valid_pointer_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, directory = _transaction_directory(tmp_path)
    transaction = _unit_transaction()
    final_path = directory / f"{transaction.transaction_id}.json"
    pointer_path = directory / f".{transaction.transaction_id}.current.tmp"
    final_path.write_bytes(output_publisher._transaction_bytes(transaction))
    publication = output_publisher.OutputPublication(
        schema_version=output_publisher.CURRENT_SCHEMA_VERSION,
        deck_name=transaction.deck_name,
        deck_fingerprint=transaction.deck_fingerprint,
        revision=transaction.revision,
        content_root_sha256=transaction.content_root_sha256,
    )
    pointer_path.write_bytes(output_publisher.output_publication_bytes(publication))
    monkeypatch.setattr(output_publisher, "_validate_publisher_residue", lambda *_args, **_kwargs: None)
    output_publisher._recover_owned_atomic_temps(root, current_revision=None)
    assert final_path.is_file()
    assert not pointer_path.exists()


@pytest.mark.parametrize("mode", ("journal", "pointer"))
def test_atomic_temp_recovery_rejects_identity_change_before_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    root, directory = _transaction_directory(tmp_path)
    transaction = _unit_transaction()
    if mode == "journal":
        final = replace(
            transaction,
            phase="staging_owned",
            staging_identity=(1, 2, 3),
        )
        final_path = directory / f"{transaction.transaction_id}.json"
        temp_path = directory / f".{transaction.transaction_id}.journal.tmp"
        final_path.write_bytes(output_publisher._transaction_bytes(final))
        temp_path.write_bytes(output_publisher._transaction_bytes(transaction))
    else:
        final_path = directory / f"{transaction.transaction_id}.json"
        temp_path = directory / f".{transaction.transaction_id}.current.tmp"
        final_path.write_bytes(output_publisher._transaction_bytes(transaction))
        publication = output_publisher.OutputPublication(
            schema_version=output_publisher.CURRENT_SCHEMA_VERSION,
            deck_name=transaction.deck_name,
            deck_fingerprint=transaction.deck_fingerprint,
            revision=transaction.revision,
            content_root_sha256=transaction.content_root_sha256,
        )
        temp_path.write_bytes(output_publisher.output_publication_bytes(publication))
    real_identity = output_publisher.path_identity
    if mode == "journal":
        monkeypatch.setattr(
            output_publisher,
            "_same_transaction_identity",
            lambda *_args: True,
        )
    monkeypatch.setattr(
        output_publisher,
        "path_identity",
        lambda path: (
            lambda value: (value[0], value[1] + 1, value[2])
        )(real_identity(path))
        if path == temp_path
        else real_identity(path),
    )
    monkeypatch.setattr(output_publisher, "_validate_publisher_residue", lambda *_args, **_kwargs: None)
    with pytest.raises(ValueError, match="owned_temp_identity_changed"):
        output_publisher._recover_owned_atomic_temps(root, current_revision=None)


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("count", "transaction_count_limit"),
        ("name", "transaction_residue_invalid"),
        ("file", "transaction_file_invalid"),
        ("bytes", "transaction_bytes_limit"),
        ("parse", "transaction_invalid"),
        ("mismatch", "transaction_name_mismatch"),
        ("owners", "revision_owner_ambiguous"),
    ),
)
def test_load_transactions_fails_closed_on_every_invalid_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    message: str,
) -> None:
    root, directory = _transaction_directory(tmp_path)
    transaction = _unit_transaction()
    if mode == "count":
        monkeypatch.setattr(output_publisher, "_MAX_TRANSACTION_FILES", 0)
        (directory / f"{transaction.transaction_id}.json").write_bytes(b"x")
    elif mode == "name":
        (directory / "bad").write_bytes(b"x")
    elif mode == "file":
        (directory / f"{transaction.transaction_id}.json").mkdir()
    elif mode == "bytes":
        monkeypatch.setattr(output_publisher, "_MAX_TRANSACTION_BYTES", 0)
        (directory / f"{transaction.transaction_id}.json").write_bytes(
            output_publisher._transaction_bytes(transaction)
        )
    elif mode == "parse":
        (directory / f"{transaction.transaction_id}.json").write_bytes(b"not-json")
    elif mode == "mismatch":
        (directory / f"{'2' * 32}.json").write_bytes(
            output_publisher._transaction_bytes(transaction)
        )
    else:
        identity = (1, 2, 3)
        owner = replace(
            transaction,
            phase="finalized",
            revision_identity=identity,
            owns_revision=True,
        )
        other_id = "2" * 32
        duplicate = replace(
            owner,
            transaction_id=other_id,
            staging=f"revisions/.staging-{other_id}",
        )
        (directory / f"{owner.transaction_id}.json").write_bytes(
            output_publisher._transaction_bytes(owner)
        )
        (directory / f"{duplicate.transaction_id}.json").write_bytes(
            output_publisher._transaction_bytes(duplicate)
        )
    with pytest.raises(ValueError, match=message):
        output_publisher._load_valid_transactions(root)


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("current_owner", "current_owner_invalid"),
        ("current_mismatch", "current_owner_invalid"),
        ("revision_count", "residue_count_limit"),
        ("revision_file", "revision_residue_invalid"),
        ("journal_residue", "noncurrent_journal_residue"),
        ("stale_owner", "cleanup_owner_ambiguous"),
        ("stale_phase", "cleanup_owner_not_finalized"),
        ("active_reference", "cleanup_reference_ambiguous"),
        ("stale_manifest", "cleanup_manifest_mismatch"),
    ),
)
def test_detached_cleanup_rejects_ambiguous_or_unverified_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    message: str,
) -> None:
    root = tmp_path / "output"
    revisions = root / "revisions"
    revisions.mkdir(parents=True)
    current_identity = None
    stale_identity = None
    current = _unit_transaction(
        phase="finalized",
        revision_identity=(1, 2, 3),
        owns_revision=True,
    )
    current_root = root / current.revision
    current_root.mkdir()
    current_identity = output_publisher.path_identity(current_root)
    current = replace(
        current,
        revision_identity=current_identity,
        deck_name="Wrong" if mode == "current_mismatch" else current.deck_name,
    )
    publication = output_publisher.OutputPublication(
        schema_version=output_publisher.CURRENT_SCHEMA_VERSION,
        deck_name="Deck",
        deck_fingerprint="b" * 64,
        revision=current.revision,
        content_root_sha256=current.content_root_sha256,
    )
    stale_digest = "c" * 64
    stale_revision = f"revisions/sha256-{stale_digest}"
    stale_root = root / stale_revision
    if mode != "journal_residue":
        if mode == "revision_file":
            stale_root.write_bytes(b"file")
        else:
            stale_root.mkdir()
            stale_identity = output_publisher.path_identity(stale_root)
    stale_owner = replace(
        _unit_transaction(
            transaction_id="2" * 32,
            phase="finalized",
            revision_identity=(4, 5, 6),
            owns_revision=True,
        ),
        content_root_sha256=stale_digest,
        revision=stale_revision,
        revision_identity=stale_identity or (4, 5, 6),
        phase="revision_ready" if mode == "stale_phase" else "finalized",
    )
    rows: list[tuple[Path, output_publisher._Transaction]] = (
        [] if mode == "current_owner" else [(Path("current"), current)]
    )
    if mode not in {"current_owner", "stale_owner", "journal_residue", "revision_count", "revision_file"}:
        rows.append((Path("stale"), stale_owner))
    if mode == "journal_residue":
        rows.append((Path("extra"), _unit_transaction(transaction_id="3" * 32)))
    if mode == "active_reference":
        rows.append(
            (
                Path("active"),
                _unit_transaction(
                    transaction_id="3" * 32,
                    phase="revision_ready",
                    revision_identity=current_identity,
                    previous_revision=stale_revision,
                ),
            )
        )
    monkeypatch.setattr(output_publisher, "_load_valid_transactions", lambda _root: rows)
    if mode == "revision_count":
        monkeypatch.setattr(output_publisher, "_MAX_TRANSACTION_FILES", 0)

    def verified(path: Path) -> SimpleNamespace:
        is_stale = path == stale_root
        transaction = stale_owner if is_stale else current
        return SimpleNamespace(
            manifest=SimpleNamespace(
                content_root_sha256=(
                    "wrong"
                    if mode == "stale_manifest" and is_stale
                    else transaction.content_root_sha256
                ),
                deck_name=transaction.deck_name,
                deck_fingerprint=transaction.deck_fingerprint,
            )
        )

    monkeypatch.setattr(output_publisher, "snapshot_and_verify_revision", verified)
    with pytest.raises(ValueError, match=message):
        output_publisher._cleanup_detached_owned_revisions(root, publication)


def test_owned_replace_target_rejects_content_without_identity(
    tmp_path: Path,
) -> None:
    target = tmp_path / "journal.json"

    with pytest.raises(ValueError, match="publisher_owned_target_changed"):
        output_publisher._validate_owned_replace_target(
            target,
            expected_identity=None,
            expected_content=b"unbound",
        )


def test_owned_replace_target_rejects_content_change_at_same_path_identity(
    tmp_path: Path,
) -> None:
    target = tmp_path / "journal.json"
    target.write_bytes(b"original")

    with pytest.raises(ValueError, match="publisher_owned_target_changed"):
        output_publisher._validate_owned_replace_target(
            target,
            expected_identity=output_publisher.path_identity(target),
            expected_content=b"replacement",
        )


def test_legacy_canonicalization_requires_bound_journal_identity(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(rendered_runs[0], output_root)
    journal_path = next(
        (output_root / ".publisher" / "transactions").iterdir()
    )
    owner = output_publisher._parse_transaction(journal_path.read_bytes())
    legacy = replace(
        owner,
        previous_revision=f"revisions/sha256-{'f' * 64}",
    )
    journal_path.write_bytes(output_publisher._transaction_bytes(legacy))
    current = output_publisher.resolve_current_publication_unlocked(output_root)

    with pytest.raises(
        ValueError,
        match="publisher_finalized_legacy_authority_invalid",
    ):
        output_publisher._canonicalize_legacy_finalized_owner(
            output_root,
            current=current,
            journals=[(journal_path, legacy)],
            journal_identities={},
        )


def test_canonical_temp_successor_rejects_additional_final_journal(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(rendered_runs[0], output_root)
    transactions = output_root / ".publisher" / "transactions"
    journal_path = next(transactions.iterdir())
    owner = output_publisher._parse_transaction(journal_path.read_bytes())
    legacy = replace(
        owner,
        previous_revision=f"revisions/sha256-{'f' * 64}",
    )
    journal_path.write_bytes(output_publisher._transaction_bytes(legacy))
    repaired = replace(legacy, previous_revision=None)
    journal_path.with_name(
        f".{owner.transaction_id}.journal.tmp"
    ).write_bytes(output_publisher._transaction_bytes(repaired))
    extra_transaction_id = "e" * 32
    extra = replace(
        owner,
        transaction_id=extra_transaction_id,
        staging=f"revisions/.staging-{extra_transaction_id}",
    )
    (transactions / f"{extra.transaction_id}.json").write_bytes(
        output_publisher._transaction_bytes(extra)
    )

    with pytest.raises(ValueError, match="publisher_transaction_temp_conflict"):
        reconcile_output(output_root)


# Task 8: capability-bound publisher and neutral output fencing.


def _tree_snapshot(
    root: Path,
) -> dict[str, tuple[str, tuple[int, int, int], bytes | None]]:
    if not root.exists():
        return {}
    snapshot: dict[
        str,
        tuple[str, tuple[int, int, int], bytes | None],
    ] = {".": ("directory", path_identity(root), None)}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[relative] = ("directory", path_identity(path), None)
        elif path.is_file():
            snapshot[relative] = (
                "file",
                path_identity(path),
                path.read_bytes(),
            )
        else:
            snapshot[relative] = ("unsafe", path_identity(path), None)
    return snapshot


def _swap_visible_output_root_worker(
    output_root_text: str,
    moved_root_text: str,
    ready: object,
    start: object,
    result: object,
) -> None:
    output_root = Path(output_root_text)
    moved_root = Path(moved_root_text)
    ready.put("ready")
    if not start.wait(10):
        result.put(("error", "start-timeout"))
        return
    try:
        output_root.rename(moved_root)
        output_root.mkdir()
    except PermissionError as error:
        result.put(("permission-denied", repr(error)))
    except BaseException as error:  # pragma: no cover - surfaced in parent
        result.put(("error", repr(error)))
        raise
    else:
        result.put(("swapped", ""))


def _output_child_bootstrap_route_worker(
    route_kind: str,
    payload_pickle_path: str,
    session_root_text: str | None,
    local_app_data_text: str,
    output_root_text: str,
    status_queue: object,
) -> None:
    import hsconfig.output_publisher as worker_publisher

    os.environ["LOCALAPPDATA"] = local_app_data_text
    real_lease = worker_publisher.lease_output_child_bootstrap

    @contextmanager
    def observed_lease(*, output_root: Path):
        status_queue.put(("attempted", "", ""))  # type: ignore[attr-defined]
        with real_lease(output_root=output_root) as lease:
            yield lease

    worker_publisher.lease_output_child_bootstrap = observed_lease
    try:
        payload = pickle.loads(Path(payload_pickle_path).read_bytes())
        if route_kind == "live-preview":
            if session_root_text is None:
                raise AssertionError("live preview session root missing")
            from hsconfig.operator_profile import load_operator_profile
            from tests.test_configure_prepublication_apply import (
                _controller,
                _drive_pipeline,
            )

            controller = _controller()
            if hasattr(controller, "lease_output_child_bootstrap"):
                controller.lease_output_child_bootstrap = observed_lease
            profile = load_operator_profile()
            _drive_pipeline(
                SimpleNamespace(
                    run_model=controller.build_frozen_live_configure_run(
                        request=payload
                    ),
                    session_root=Path(session_root_text),
                    local_app_data=Path(local_app_data_text),
                    runtime_root=profile.runtime_root,
                )
            )
        elif route_kind == "legacy":
            source_root_text, revision = payload
            worker_publisher.publish_configure_run(
                build_rendered_run(
                    Path(str(source_root_text)),
                    int(revision),
                ),
                Path(output_root_text),
            )
        else:
            raise AssertionError(f"unknown publisher route: {route_kind}")
    except BaseException as error:
        status_queue.put(  # type: ignore[attr-defined]
            ("error", type(error).__name__, str(error))
        )
    else:
        status_queue.put(("published", "", ""))  # type: ignore[attr-defined]


def _task8_output_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered: RenderedConfigureRun,
):
    from contextlib import ExitStack

    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
    )
    from hsconfig.package_io import hold_plain_directory

    local = tmp_path / "local-app-data"
    local.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    output_root = tmp_path / "outputs" / rendered.model.deck_name
    output_root.parent.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(exist_ok=True)
    output_publisher._bootstrap_neutral_output_locks(output_root=output_root)
    stack = ExitStack()
    operation = stack.enter_context(lease_output_operation_admission())
    bootstrap = stack.enter_context(
        output_publisher.lease_output_child_bootstrap(output_root=output_root)
    )
    guard = stack.enter_context(hold_plain_directory(output_root))
    authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
        operation_lease=operation,
        bootstrap_lease=bootstrap,
        output_guard=guard,
        operation_admission=None,
        session_lease=None,
        expected_session=None,
        profile_lease=None,
    )
    return stack, output_root, operation, bootstrap, guard, authorization


@contextmanager
def _task8_live_output_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_output_capabilities: bool = True,
    existing_legacy_current: bool = False,
):
    from contextlib import ExitStack

    from hsconfig import live_start_session
    from hsconfig.operator_profile import lease_operator_profile, load_operator_profile
    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
        observe_output_operation_admission_under_lease,
    )
    from hsconfig.package_io import hold_plain_directory
    from tests.test_configure_prepublication_apply import (
        _interrupt_pipeline,
        _prepare_pipeline,
    )

    prepared = _prepare_pipeline(
        tmp_path,
        monkeypatch,
        existing_child_precondition=existing_legacy_current,
    )
    if existing_legacy_current:
        publish_configure_run(
            render_configure_run_model(prepared.run_model),
            prepared.output_child_root,
        )
    interrupted = _interrupt_pipeline(prepared, "AFTER_OUTPUT_CHILD_BOUND")
    with ExitStack() as stack:
        session_lease = stack.enter_context(
            live_start_session.lease_live_start_session(
                prepared.session_root,
                local_app_data_root=prepared.local_app_data,
            )
        )
        current = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        assert current.content_sha256 == interrupted.content_sha256
        profile = load_operator_profile()
        profile_lease = stack.enter_context(
            lease_operator_profile(expected_profile=profile)
        )
        operation_lease = stack.enter_context(
            lease_output_operation_admission()
        )
        bootstrap_lease = None
        guard = None
        if include_output_capabilities:
            bootstrap_lease = stack.enter_context(
                output_publisher.lease_output_child_bootstrap(
                    output_root=prepared.output_child_root
                )
            )
            guard = stack.enter_context(
                hold_plain_directory(prepared.output_child_root)
            )
        operation_admission = observe_output_operation_admission_under_lease(
            operation_lease
        )
        assert operation_admission is not None
        yield SimpleNamespace(
            prepared=prepared,
            rendered=render_configure_run_model(prepared.run_model),
            session_lease=session_lease,
            current=current,
            profile_lease=profile_lease,
            operation_lease=operation_lease,
            bootstrap_lease=bootstrap_lease,
            guard=guard,
            operation_admission=operation_admission,
        )


def _leave_live_pointer_staging_bound(
    live: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, output_publisher._Transaction]:
    class PointerStagingBoundCrash(BaseException):
        pass

    real_write_transaction = output_publisher._write_transaction
    interrupted = False

    def crash_after_bound_receipt(
        path: Path,
        transaction: output_publisher._Transaction,
        **kwargs: object,
    ) -> None:
        nonlocal interrupted
        real_write_transaction(path, transaction, **kwargs)  # type: ignore[arg-type]
        if not interrupted and transaction.phase == "pointer_staging_bound":
            interrupted = True
            raise PointerStagingBoundCrash

    authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
        operation_lease=live.operation_lease,
        bootstrap_lease=live.bootstrap_lease,
        output_guard=live.guard,
        operation_admission=live.operation_admission,
        session_lease=live.session_lease,
        expected_session=live.current,
        profile_lease=live.profile_lease,
    )
    with monkeypatch.context() as crash_patch:
        crash_patch.setattr(
            output_publisher,
            "_write_transaction",
            crash_after_bound_receipt,
        )
        with pytest.raises(PointerStagingBoundCrash):
            with output_publisher.publish_configure_run_under_guard(
                live.rendered,
                output_guard=live.guard,
                operation_lease=live.operation_lease,
                bootstrap_lease=live.bootstrap_lease,
                publication_authorization=authorization,
            ):
                raise AssertionError("pointer_staging_bound_crash_not_reached")
    assert interrupted
    transactions = live.prepared.output_child_root / ".publisher" / "transactions"
    journals = [
        (path, output_publisher._parse_transaction(path.read_bytes()))
        for path in transactions.glob("[0-9a-f]*.json")
    ]
    bound = [
        (path, transaction)
        for path, transaction in journals
        if transaction.phase == "pointer_staging_bound"
        and transaction.live_start_commit_receipt is not None
    ]
    assert len(bound) == 1
    journal_path, transaction = bound[0]
    receipt = transaction.live_start_commit_receipt
    assert receipt is not None
    staging = transactions / f".{transaction.transaction_id}.current.tmp"
    assert path_identity(staging) == receipt.pointer_staging_identity
    return journal_path, transaction


def test_live_start_pointer_staging_bound_resumes_exact_identity_without_generic_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _task8_live_output_context(tmp_path, monkeypatch) as live:
        _journal_path, interrupted = _leave_live_pointer_staging_bound(
            live,
            monkeypatch,
        )
        receipt = interrupted.live_start_commit_receipt
        assert receipt is not None
        staging = (
            live.prepared.output_child_root
            / ".publisher"
            / "transactions"
            / f".{interrupted.transaction_id}.current.tmp"
        )
        staging_identity = path_identity(staging)
        authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            output_guard=live.guard,
            operation_admission=live.operation_admission,
            session_lease=live.session_lease,
            expected_session=live.current,
            profile_lease=live.profile_lease,
        )
        with output_publisher.publish_configure_run_under_guard(
            live.rendered,
            output_guard=live.guard,
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            publication_authorization=authorization,
        ) as published:
            assert path_identity(
                published.output_root / "current.json"
            ) == staging_identity
        assert not staging.exists()


def test_live_start_pointer_staging_replacement_is_rejected_before_temp_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _task8_live_output_context(tmp_path, monkeypatch) as live:
        _journal_path, interrupted = _leave_live_pointer_staging_bound(
            live,
            monkeypatch,
        )
        transactions = (
            live.prepared.output_child_root / ".publisher" / "transactions"
        )
        staging = transactions / f".{interrupted.transaction_id}.current.tmp"
        original_raw = staging.read_bytes()
        original_identity = path_identity(staging)
        staging.unlink()
        staging.write_bytes(original_raw)
        replacement_identity = path_identity(staging)
        assert replacement_identity != original_identity
        before = _tree_snapshot(live.prepared.output_child_root)
        authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            output_guard=live.guard,
            operation_admission=live.operation_admission,
            session_lease=live.session_lease,
            expected_session=live.current,
            profile_lease=live.profile_lease,
        )

        with pytest.raises(
            ValueError,
            match="^live_start_publication_current_identity_changed$",
        ):
            with output_publisher.publish_configure_run_under_guard(
                live.rendered,
                output_guard=live.guard,
                operation_lease=live.operation_lease,
                bootstrap_lease=live.bootstrap_lease,
                publication_authorization=authorization,
            ):
                raise AssertionError("tampered pointer staging was published")

        assert _tree_snapshot(live.prepared.output_child_root) == before


def test_live_start_active_journal_replacement_is_rejected_before_resume_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _task8_live_output_context(tmp_path, monkeypatch) as live:
        journal_path, _interrupted = _leave_live_pointer_staging_bound(
            live,
            monkeypatch,
        )
        raw = journal_path.read_bytes()
        original_identity = path_identity(journal_path)
        journal_path.unlink()
        journal_path.write_bytes(raw)
        replacement_identity = path_identity(journal_path)
        assert replacement_identity != original_identity
        before = _tree_snapshot(live.prepared.output_child_root)
        authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            output_guard=live.guard,
            operation_admission=live.operation_admission,
            session_lease=live.session_lease,
            expected_session=live.current,
            profile_lease=live.profile_lease,
        )

        with pytest.raises(
            ValueError,
            match="^publisher_transaction_identity_changed$",
        ):
            with output_publisher.publish_configure_run_under_guard(
                live.rendered,
                output_guard=live.guard,
                operation_lease=live.operation_lease,
                bootstrap_lease=live.bootstrap_lease,
                publication_authorization=authorization,
            ):
                raise AssertionError("replaced active journal was resumed")

        assert _tree_snapshot(live.prepared.output_child_root) == before


def _leave_legacy_finalized_owner_v2_upgrade_temp(
    live: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
    class JournalUpgradeCrash(BaseException):
        pass

    legacy = output_publisher._load_valid_transactions(
        live.prepared.output_child_root
    )
    assert len(legacy) == 1
    assert legacy[0][1].schema_version == 1
    assert legacy[0][1].phase == "finalized"

    real_write_transaction = output_publisher._write_transaction

    def crash_v2_upgrade_write(
        path: Path,
        transaction: output_publisher._Transaction,
        **kwargs: object,
    ) -> output_publisher._Transaction:
        receipt = transaction.live_start_commit_receipt
        if (
            transaction.schema_version == 2
            and transaction.phase == "finalized"
            and receipt is not None
            and receipt.disposition == "reused_existing"
        ):

            def crash_after_v2_temp_flush(stage: str) -> None:
                if stage == "after_journal_temp_write":
                    raise JournalUpgradeCrash

            kwargs["fault_hook"] = crash_after_v2_temp_flush
        return real_write_transaction(  # type: ignore[arg-type]
            path,
            transaction,
            **kwargs,
        )

    authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
        operation_lease=live.operation_lease,
        bootstrap_lease=live.bootstrap_lease,
        output_guard=live.guard,
        operation_admission=live.operation_admission,
        session_lease=live.session_lease,
        expected_session=live.current,
        profile_lease=live.profile_lease,
    )
    with monkeypatch.context() as crash_patch:
        crash_patch.setattr(
            output_publisher,
            "_write_transaction",
            crash_v2_upgrade_write,
        )
        with pytest.raises(JournalUpgradeCrash):
            with output_publisher.publish_configure_run_under_guard(
                live.rendered,
                output_guard=live.guard,
                operation_lease=live.operation_lease,
                bootstrap_lease=live.bootstrap_lease,
                publication_authorization=authorization,
            ):
                raise AssertionError("journal upgrade crash was not reached")

    transactions = (
        live.prepared.output_child_root / ".publisher" / "transactions"
    )
    final_paths = list(transactions.glob("[0-9a-f]*.json"))
    temp_paths = list(transactions.glob(".*.journal.tmp"))
    assert len(final_paths) == 1
    assert len(temp_paths) == 1
    return transactions, final_paths[0], temp_paths[0]


def test_legacy_finalized_owner_v2_upgrade_temp_converges_after_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _task8_live_output_context(
        tmp_path,
        monkeypatch,
        existing_legacy_current=True,
    ) as live:
        transactions, _final_path, _temp_path = (
            _leave_legacy_finalized_owner_v2_upgrade_temp(
                live,
                monkeypatch,
            )
        )
        second_authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            output_guard=live.guard,
            operation_admission=live.operation_admission,
            session_lease=live.session_lease,
            expected_session=live.current,
            profile_lease=live.profile_lease,
        )
        with output_publisher.publish_configure_run_under_guard(
            live.rendered,
            output_guard=live.guard,
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            publication_authorization=second_authorization,
        ) as published:
            assert published.reused_existing_revision is True

        recovered = output_publisher._load_valid_transactions(
            live.prepared.output_child_root
        )
        assert len(recovered) == 1
        assert recovered[0][1].schema_version == 2
        assert recovered[0][1].phase == "finalized"
        receipt = recovered[0][1].live_start_commit_receipt
        assert receipt is not None
        assert receipt.disposition == "reused_existing"
        assert not list(transactions.glob(".*.journal.tmp"))


def test_public_reconcile_rejects_active_live_pointer_receipt_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _task8_live_output_context(tmp_path, monkeypatch) as live:
        _leave_live_pointer_staging_bound(live, monkeypatch)
        output_root = live.prepared.output_child_root
        output_tree_root = live.prepared.output_base_root
        admission_path = live.operation_admission.admission_path
        before = (
            _tree_snapshot(output_tree_root),
            path_identity(admission_path),
            admission_path.read_bytes(),
        )

    with pytest.raises(
        ValueError,
        match="^publisher_live_start_authority_active$",
    ):
        reconcile_output(output_root)
    assert (
        _tree_snapshot(output_tree_root),
        path_identity(admission_path),
        admission_path.read_bytes(),
    ) == before


def test_public_reconcile_rejects_finalized_owner_while_live_claim_is_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _task8_live_output_context(tmp_path, monkeypatch) as live:
        authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            output_guard=live.guard,
            operation_admission=live.operation_admission,
            session_lease=live.session_lease,
            expected_session=live.current,
            profile_lease=live.profile_lease,
        )
        with output_publisher.publish_configure_run_under_guard(
            live.rendered,
            output_guard=live.guard,
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            publication_authorization=authorization,
        ):
            pass

        journals = output_publisher._load_valid_transactions(
            live.prepared.output_child_root
        )
        assert len(journals) == 1
        journal_path, transaction = journals[0]
        assert transaction.phase == "pointer_committed"
        assert transaction.live_start_commit_receipt is not None
        output_publisher._cleanup_after_commit(
            live.prepared.output_child_root,
            transaction,
            journal_path,
            fault_hook=output_publisher.no_fault,
        )
        finalized = output_publisher._load_valid_transactions(
            live.prepared.output_child_root
        )
        assert len(finalized) == 1
        assert finalized[0][1].phase == "finalized"
        assert finalized[0][1].live_start_commit_receipt is not None
        assert output_publisher.output_child_claim_path(
            live.prepared.output_child_root
        ).exists()
        output_root = live.prepared.output_child_root
        output_tree_root = live.prepared.output_base_root
        admission_path = live.operation_admission.admission_path
        before = (
            _tree_snapshot(output_tree_root),
            path_identity(admission_path),
            admission_path.read_bytes(),
        )

    with pytest.raises(
        ValueError,
        match="^publisher_live_start_authority_active$",
    ):
        reconcile_output(output_root)

    assert (
        _tree_snapshot(output_tree_root),
        path_identity(admission_path),
        admission_path.read_bytes(),
    ) == before


def test_publisher_uses_held_child_capability_on_windows_and_posix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    stack, output_root, operation, bootstrap, guard, authorization = (
        _task8_output_context(tmp_path, monkeypatch, rendered_runs[0])
    )
    with stack:
        with output_publisher.publish_configure_run_under_guard(
            rendered_runs[0],
            output_guard=guard,
            operation_lease=operation,
            bootstrap_lease=bootstrap,
            publication_authorization=authorization,
        ) as published:
            assert published.output_root == output_root
            assert (output_root / "current.json").exists()
            guard.validate()


def test_publish_under_guard_rejects_closed_or_forged_guard_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from hsconfig.package_io import hold_plain_directory
    from tests.test_configure_prepublication_apply import _physical_tree

    for dimension in ("forged", "closed"):
        with _task8_live_output_context(
            tmp_path / dimension,
            monkeypatch,
        ) as live:
            if dimension == "forged":
                authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
                    operation_lease=live.operation_lease,
                    bootstrap_lease=live.bootstrap_lease,
                    output_guard=live.guard,
                    operation_admission=live.operation_admission,
                    session_lease=live.session_lease,
                    expected_session=live.current,
                    profile_lease=live.profile_lease,
                )
                selected_guard = object()
                expected_error = "^output_publication_guard_invalid$"
            else:
                guard_manager = hold_plain_directory(
                    live.prepared.output_child_root
                )
                selected_guard = guard_manager.__enter__()
                authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
                    operation_lease=live.operation_lease,
                    bootstrap_lease=live.bootstrap_lease,
                    output_guard=selected_guard,
                    operation_admission=live.operation_admission,
                    session_lease=live.session_lease,
                    expected_session=live.current,
                    profile_lease=live.profile_lease,
                )
                guard_manager.__exit__(None, None, None)
                expected_error = "^output_publication_guard_inactive$"
            before = _physical_tree(live.prepared.output_base_root)
            with pytest.raises(ValueError, match=expected_error):
                with output_publisher.publish_configure_run_under_guard(
                    live.rendered,
                    output_guard=selected_guard,
                    operation_lease=live.operation_lease,
                    bootstrap_lease=live.bootstrap_lease,
                    publication_authorization=authorization,
                ):
                    pass
            assert _physical_tree(live.prepared.output_base_root) == before


def test_publish_under_guard_requires_active_bootstrap_lease_and_publication_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from hsconfig.package_io import hold_plain_directory
    from tests.test_configure_prepublication_apply import _physical_tree

    with _task8_live_output_context(
        tmp_path / "expired-bootstrap",
        monkeypatch,
        include_output_capabilities=False,
    ) as live:
        bootstrap_manager = output_publisher.lease_output_child_bootstrap(
            output_root=live.prepared.output_child_root
        )
        expired_bootstrap = bootstrap_manager.__enter__()
        bootstrap_manager.__exit__(None, None, None)
        with hold_plain_directory(
            live.prepared.output_child_root
        ) as active_guard:
            before = _physical_tree(live.prepared.output_base_root)
            with pytest.raises(
                ValueError,
                match="^output_publication_bootstrap_lease_inactive$",
            ):
                output_publisher.authorize_output_publication_under_bootstrap_lease(
                    operation_lease=live.operation_lease,
                    bootstrap_lease=expired_bootstrap,
                    output_guard=active_guard,
                    operation_admission=live.operation_admission,
                    session_lease=live.session_lease,
                    expected_session=live.current,
                    profile_lease=live.profile_lease,
                )
            assert _physical_tree(live.prepared.output_base_root) == before

    with _task8_live_output_context(
        tmp_path / "expired-authorization",
        monkeypatch,
        include_output_capabilities=False,
    ) as live:
        with output_publisher.lease_output_child_bootstrap(
            output_root=live.prepared.output_child_root
        ) as first_bootstrap:
            with hold_plain_directory(
                live.prepared.output_child_root
            ) as first_guard:
                expired_authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
                    operation_lease=live.operation_lease,
                    bootstrap_lease=first_bootstrap,
                    output_guard=first_guard,
                    operation_admission=live.operation_admission,
                    session_lease=live.session_lease,
                    expected_session=live.current,
                    profile_lease=live.profile_lease,
                )
        with output_publisher.lease_output_child_bootstrap(
            output_root=live.prepared.output_child_root
        ) as active_bootstrap:
            with hold_plain_directory(
                live.prepared.output_child_root
            ) as active_guard:
                before = _physical_tree(live.prepared.output_base_root)
                with pytest.raises(
                    ValueError,
                    match="^output_publication_authorization_expired$",
                ):
                    with output_publisher.publish_configure_run_under_guard(
                        live.rendered,
                        output_guard=active_guard,
                        operation_lease=live.operation_lease,
                        bootstrap_lease=active_bootstrap,
                        publication_authorization=expired_authorization,
                    ):
                        pass
                assert _physical_tree(live.prepared.output_base_root) == before

    with _task8_live_output_context(
        tmp_path / "reused-authorization",
        monkeypatch,
    ) as live:
        authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            output_guard=live.guard,
            operation_admission=live.operation_admission,
            session_lease=live.session_lease,
            expected_session=live.current,
            profile_lease=live.profile_lease,
        )
        with output_publisher.publish_configure_run_under_guard(
            live.rendered,
            output_guard=live.guard,
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            publication_authorization=authorization,
        ):
            pass
        before_reuse = _physical_tree(live.prepared.output_base_root)
        with pytest.raises(
            ValueError,
            match="^output_publication_authorization_reused$",
        ):
            with output_publisher.publish_configure_run_under_guard(
                live.rendered,
                output_guard=live.guard,
                operation_lease=live.operation_lease,
                bootstrap_lease=live.bootstrap_lease,
                publication_authorization=authorization,
            ):
                pass
        assert _physical_tree(live.prepared.output_base_root) == before_reuse


def test_output_publication_authorization_copy_shares_single_use_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from tests.test_configure_prepublication_apply import _physical_tree

    stack, output_root, operation, bootstrap, guard, authorization = (
        _task8_output_context(tmp_path, monkeypatch, rendered_runs[0])
    )
    cloned = copy.copy(authorization)
    with stack:
        with output_publisher.publish_configure_run_under_guard(
            rendered_runs[0],
            output_guard=guard,
            operation_lease=operation,
            bootstrap_lease=bootstrap,
            publication_authorization=authorization,
        ):
            pass
        before = _physical_tree(output_root)

        with pytest.raises(
            ValueError,
            match="^output_publication_authorization_reused$",
        ):
            with output_publisher.publish_configure_run_under_guard(
                rendered_runs[0],
                output_guard=guard,
                operation_lease=operation,
                bootstrap_lease=bootstrap,
                publication_authorization=cloned,
            ):
                pass

        assert _physical_tree(output_root) == before


def test_output_publication_authorization_rejects_wrong_kind_cursor_profile_or_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from contextlib import ExitStack

    from hsconfig.operator_profile import (
        enable_operator_profile,
        lease_operator_profile,
        load_operator_profile,
    )
    from tests.test_configure_prepublication_apply import _physical_tree

    for dimension in ("kind", "cursor", "profile", "claim"):
        with _task8_live_output_context(
            tmp_path / dimension,
            monkeypatch,
        ) as live:
            kwargs = {
                "operation_lease": live.operation_lease,
                "bootstrap_lease": live.bootstrap_lease,
                "output_guard": live.guard,
                "operation_admission": live.operation_admission,
                "session_lease": live.session_lease,
                "expected_session": live.current,
                "profile_lease": live.profile_lease,
            }
            before = _physical_tree(live.prepared.output_base_root)
            if dimension == "kind":
                wrong_kind_authorization = (
                    output_publisher.authorize_output_publication_under_bootstrap_lease(
                        **kwargs
                    )
                )
                wrong_kind_authorization.kind = "ORDINARY_CLAIM_ABSENT"
                with pytest.raises(
                    ValueError,
                    match="^output_publication_authorization_kind_invalid$",
                ):
                    with output_publisher.publish_configure_run_under_guard(
                        live.rendered,
                        output_guard=live.guard,
                        operation_lease=live.operation_lease,
                        bootstrap_lease=live.bootstrap_lease,
                        publication_authorization=wrong_kind_authorization,
                    ):
                        pass
            elif dimension == "cursor":
                kwargs["expected_session"] = live.prepared.approved
                with pytest.raises(
                    ValueError,
                    match="^output_publication_session_cursor_stale$",
                ):
                    output_publisher.authorize_output_publication_under_bootstrap_lease(
                        **kwargs
                    )
            elif dimension == "profile":
                primary_local = live.prepared.local_app_data
                foreign_local = tmp_path / dimension / "foreign-local-app-data"
                foreign_runtime = tmp_path / dimension / "foreign-runtime"
                foreign_outputs = tmp_path / dimension / "foreign-outputs"
                foreign_local.mkdir()
                foreign_runtime.mkdir()
                foreign_outputs.mkdir()
                monkeypatch.setenv("LOCALAPPDATA", str(foreign_local))
                foreign_profile = enable_operator_profile(
                    runtime_root=foreign_runtime,
                    output_base_root=foreign_outputs,
                    expected_predecessor_sha256=None,
                )
                assert load_operator_profile() == foreign_profile
                with ExitStack() as foreign_stack:
                    foreign_lease = foreign_stack.enter_context(
                        lease_operator_profile(
                            expected_profile=foreign_profile
                        )
                    )
                    monkeypatch.setenv("LOCALAPPDATA", str(primary_local))
                    kwargs["profile_lease"] = foreign_lease
                    with pytest.raises(
                        ValueError,
                        match="^output_publication_profile_binding_changed$",
                    ):
                        output_publisher.authorize_output_publication_under_bootstrap_lease(
                            **kwargs
                        )
            else:
                authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
                    **kwargs
                )
                claim = output_publisher.output_child_claim_path(
                    live.prepared.output_child_root
                )
                raw = claim.read_bytes()
                claim_identity = path_identity(claim)
                claim.unlink()
                claim.write_bytes(raw)
                assert path_identity(claim) != claim_identity
                before = _physical_tree(live.prepared.output_base_root)
                with pytest.raises(
                    ValueError,
                    match="^output_publication_claim_identity_changed$",
                ):
                    with output_publisher.publish_configure_run_under_guard(
                        live.rendered,
                        output_guard=live.guard,
                        operation_lease=live.operation_lease,
                        bootstrap_lease=live.bootstrap_lease,
                        publication_authorization=authorization,
                    ):
                        pass
            assert _physical_tree(live.prepared.output_base_root) == before


def test_output_publication_authorization_requires_active_owning_session_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from contextlib import ExitStack

    from hsconfig import live_start_session
    from hsconfig.operator_profile import lease_operator_profile, load_operator_profile
    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
        observe_output_operation_admission_under_lease,
    )
    from hsconfig.package_io import hold_plain_directory
    from tests.test_configure_prepublication_apply import (
        _interrupt_pipeline,
        _physical_tree,
        _prepare_pipeline,
    )

    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _interrupt_pipeline(prepared, "AFTER_OUTPUT_CHILD_BOUND")
    with live_start_session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        current = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        stale_session_lease = session_lease
    with ExitStack() as stack:
        profile = load_operator_profile()
        profile_lease = stack.enter_context(
            lease_operator_profile(expected_profile=profile)
        )
        operation = stack.enter_context(lease_output_operation_admission())
        bootstrap = stack.enter_context(
            output_publisher.lease_output_child_bootstrap(
                output_root=prepared.output_child_root
            )
        )
        guard = stack.enter_context(hold_plain_directory(prepared.output_child_root))
        evidence = observe_output_operation_admission_under_lease(operation)
        assert evidence is not None
        before = _physical_tree(prepared.output_base_root)
        with pytest.raises(
            ValueError,
            match="^output_publication_session_lease_inactive$",
        ):
            output_publisher.authorize_output_publication_under_bootstrap_lease(
                operation_lease=operation,
                bootstrap_lease=bootstrap,
                output_guard=guard,
                operation_admission=evidence,
                session_lease=stale_session_lease,
                expected_session=current,
                profile_lease=profile_lease,
            )
        assert _physical_tree(prepared.output_base_root) == before


def test_output_publication_authorization_rejects_stale_cross_thread_or_expired_session_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from queue import Queue
    from threading import Thread

    from hsconfig import live_start_session
    from hsconfig.operator_profile import lease_operator_profile, load_operator_profile
    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
        observe_output_operation_admission_under_lease,
    )
    from hsconfig.package_io import hold_plain_directory
    from tests.test_configure_prepublication_apply import (
        _interrupt_pipeline,
        _physical_tree,
        _prepare_pipeline,
    )

    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(prepared, "AFTER_OUTPUT_CHILD_BOUND")
    errors: Queue[BaseException] = Queue()
    acquired = Queue()

    with live_start_session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as owning_session_lease:
        current = live_start_session.load_live_start_session_under_lock(
            session_lease=owning_session_lease
        )
        assert current.content_sha256 == interrupted.content_sha256

        def cross_thread() -> None:
            try:
                profile = load_operator_profile()
                with lease_operator_profile(
                    expected_profile=profile
                ) as profile_lease:
                    with lease_output_operation_admission() as operation_lease:
                        with output_publisher.lease_output_child_bootstrap(
                            output_root=prepared.output_child_root
                        ) as bootstrap_lease:
                            with hold_plain_directory(
                                prepared.output_child_root
                            ) as guard:
                                evidence = observe_output_operation_admission_under_lease(
                                    operation_lease
                                )
                                assert evidence is not None
                                acquired.put("all-non-session-capabilities-active")
                                output_publisher.authorize_output_publication_under_bootstrap_lease(
                                    operation_lease=operation_lease,
                                    bootstrap_lease=bootstrap_lease,
                                    output_guard=guard,
                                    operation_admission=evidence,
                                    session_lease=owning_session_lease,
                                    expected_session=current,
                                    profile_lease=profile_lease,
                                )
            except BaseException as error:
                errors.put(error)

        before = _physical_tree(prepared.output_base_root)
        thread = Thread(target=cross_thread)
        thread.start()
        thread.join(5)
        assert not thread.is_alive()
        assert acquired.get_nowait() == "all-non-session-capabilities-active"
        error = errors.get_nowait()
        assert type(error) is ValueError
        assert str(error) == "output_publication_session_lease_cross_thread"
        assert _physical_tree(prepared.output_base_root) == before


def test_publish_under_guard_swap_at_first_mutation_never_touches_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    stack, output_root, operation, bootstrap, guard, authorization = (
        _task8_output_context(tmp_path, monkeypatch, rendered_runs[0])
    )
    held_tree = output_root.with_name("held-tree-after-swap")
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    start = context.Event()
    result = context.Queue()
    contender = context.Process(
        target=_swap_visible_output_root_worker,
        args=(str(output_root), str(held_tree), ready, start, result),
    )
    contender.start()
    assert ready.get(timeout=15) == "ready"
    swapped_snapshots: dict[str, object] = {}

    def swap_after_initial_validation(stage: str) -> None:
        if stage != "after_lock":
            return
        assert swapped_snapshots == {}
        start.set()
        disposition, detail = result.get(timeout=15)
        if disposition == "permission-denied":
            pytest.skip(f"platform prevents held-root replacement: {detail}")
        assert (disposition, detail) == ("swapped", "")
        swapped_snapshots.update(
            held_identity=path_identity(held_tree),
            visible_identity=path_identity(output_root),
            held_tree=_tree_snapshot(held_tree),
            visible_tree=_tree_snapshot(output_root),
        )

    try:
        with stack:
            with pytest.raises(ValueError, match="identity|guard"):
                with output_publisher.publish_configure_run_under_guard(
                    rendered_runs[0],
                    output_guard=guard,
                    operation_lease=operation,
                    bootstrap_lease=bootstrap,
                    publication_authorization=authorization,
                    fault_hook=swap_after_initial_validation,
                ):
                    pass
    finally:
        start.set()
        contender.join(15)
    assert contender.exitcode == 0
    assert swapped_snapshots
    assert path_identity(held_tree) == swapped_snapshots["held_identity"]
    assert path_identity(output_root) == swapped_snapshots["visible_identity"]
    assert _tree_snapshot(held_tree) == swapped_snapshots["held_tree"]
    assert _tree_snapshot(output_root) == swapped_snapshots["visible_tree"]


def test_guarded_publish_binds_first_layout_step_to_held_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    stack, output_root, operation, bootstrap, guard, authorization = (
        _task8_output_context(tmp_path, monkeypatch, rendered_runs[0])
    )
    replacement_root = output_root.with_name("replacement-root-before-layout")
    replacement_root.mkdir()
    real_ensure_layout = output_publisher._ensure_layout
    replacement_before = _tree_snapshot(replacement_root)

    def swap_before_first_layout_step(
        _root: Path,
        **kwargs: object,
    ) -> None:
        real_ensure_layout(  # type: ignore[arg-type]
            replacement_root,
            **kwargs,
        )
        raise ValueError("filesystem_path_identity_changed")

    monkeypatch.setattr(
        output_publisher,
        "_ensure_layout",
        swap_before_first_layout_step,
    )
    with stack:
        with pytest.raises(ValueError, match="identity|guard"):
            with output_publisher.publish_configure_run_under_guard(
                rendered_runs[0],
                output_guard=guard,
                operation_lease=operation,
                bootstrap_lease=bootstrap,
                publication_authorization=authorization,
            ):
                pass

    assert _tree_snapshot(replacement_root) == replacement_before


def test_guarded_reconcile_binds_first_layout_observation_and_lock_to_held_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from hsconfig.package_io import hold_plain_directory

    local = tmp_path / "local-app-data"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    output_root = tmp_path / "outputs" / "ShadowPriest"
    publish_configure_run(rendered_runs[0], output_root)
    replacement_root = output_root.with_name("replacement-root-before-reconcile")
    (replacement_root / "revisions").mkdir(parents=True)
    (replacement_root / ".publisher" / "transactions").mkdir(parents=True)
    (replacement_root / ".publish.lock").write_bytes(b"")
    real_validate_layout = output_publisher._validate_existing_layout
    real_lock = output_publisher.ExclusiveFileLock
    replacement_before = _tree_snapshot(replacement_root)
    entered_locks: list[Path] = []

    def swap_before_first_layout_observation(
        _root: Path,
        **kwargs: object,
    ) -> None:
        real_validate_layout(  # type: ignore[arg-type]
            replacement_root,
            **kwargs,
        )

    class ObservedExclusiveFileLock:
        def __init__(self, path: Path, **kwargs: object) -> None:
            self.path = replacement_root / path.name
            self.inner = real_lock(  # type: ignore[arg-type]
                self.path,
                **kwargs,
            )

        def __enter__(self) -> object:
            entered_locks.append(self.path)
            self.inner.__enter__()
            self.inner.__exit__(None, None, None)
            raise ValueError("filesystem_path_identity_changed")

        def __exit__(self, *args: object) -> None:
            self.inner.__exit__(*args)

    monkeypatch.setattr(
        output_publisher,
        "_validate_existing_layout",
        swap_before_first_layout_observation,
    )
    monkeypatch.setattr(
        output_publisher,
        "ExclusiveFileLock",
        ObservedExclusiveFileLock,
    )
    with hold_plain_directory(output_root) as output_guard:
        with pytest.raises(ValueError, match="identity|guard"):
            output_publisher._reconcile_output_under_guard(
                output_root,
                output_guard=output_guard,
            )

    assert entered_locks == []
    assert _tree_snapshot(replacement_root) == replacement_before


def test_guarded_finalize_binds_layout_observation_and_lock_to_held_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig.package_io import hold_plain_directory

    output_root = tmp_path / "output"
    output_root.mkdir()
    output_publisher._ensure_layout(output_root)
    (output_root / ".publish.lock").write_bytes(b"")
    claim_path = output_publisher.output_child_claim_path(output_root)
    claim_bytes = b"active-claim"
    claim_path.write_bytes(claim_bytes)
    claim_identity = path_identity(claim_path)
    claim_sha256 = "sha256:" + output_publisher.sha256(claim_bytes).hexdigest()

    replacement_root = tmp_path / "replacement-output"
    (replacement_root / "revisions").mkdir(parents=True)
    (replacement_root / ".publisher" / "transactions").mkdir(parents=True)
    (replacement_root / ".publish.lock").write_bytes(b"")
    replacement_before = _tree_snapshot(replacement_root)
    real_validate_layout = output_publisher._validate_existing_layout
    real_lock = output_publisher.ExclusiveFileLock
    entered_locks: list[Path] = []

    def observe_replacement_layout(
        _root: Path,
        **kwargs: object,
    ) -> None:
        real_validate_layout(  # type: ignore[arg-type]
            replacement_root,
            **kwargs,
        )

    class ObservedExclusiveFileLock:
        def __init__(self, path: Path, **kwargs: object) -> None:
            self.path = replacement_root / path.name
            self.inner = real_lock(  # type: ignore[arg-type]
                self.path,
                **kwargs,
            )

        def __enter__(self) -> object:
            entered_locks.append(self.path)
            self.inner.__enter__()
            self.inner.__exit__(None, None, None)
            raise ValueError("filesystem_path_identity_changed")

        def __exit__(self, *args: object) -> None:
            self.inner.__exit__(*args)

    operation_sha256 = "sha256:" + "a" * 64
    operation_admission = SimpleNamespace(
        admission_identity=(1, 2, 3),
        operator_profile_sha256="profile-sha256",
        operator_profile_path=tmp_path / "profile.json",
        operator_profile_identity=(4, 5, 6),
    )
    profile_lease = SimpleNamespace(
        profile=SimpleNamespace(content_sha256="profile-sha256"),
        profile_path=operation_admission.operator_profile_path,
        profile_identity=operation_admission.operator_profile_identity,
    )
    with hold_plain_directory(output_root) as output_guard:
        child_binding = {
            "claim_state": "ACTIVE",
            "claim_identity": list(claim_identity),
            "claim_sha256": claim_sha256,
            "output_child_path": str(output_root),
            "output_child_identity": output_guard.identity,
            "content_sha256": "child-binding-sha256",
        }
        current = SimpleNamespace(
            phase=output_publisher.live_session.LiveStartPhase.PUBLICATION_COMMITTED,
            output_child_binding=child_binding,
            publication_binding={
                "output_child_path": str(output_root),
                "output_child_identity": output_guard.identity,
                "output_child_binding_sha256": child_binding["content_sha256"],
                "revision": f"revisions/sha256-{'b' * 64}",
                "content_root_sha256": "sha256:" + "b" * 64,
                "prior_current_identity": None,
            },
            output_operation_admission_binding={
                "admission_identity": operation_admission.admission_identity,
                "admission_sha256": operation_sha256,
            },
            pending_transition=None,
            to_value=lambda: {},
        )
        monkeypatch.setattr(
            output_publisher,
            "_require_active_output_bootstrap_lease",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            output_publisher,
            "_validate_output_publication_guard",
            lambda *_args, **_kwargs: output_guard,
        )
        monkeypatch.setattr(
            output_publisher,
            "observe_output_operation_admission_under_lease",
            lambda *_args, **_kwargs: operation_admission,
        )
        monkeypatch.setattr(
            output_publisher,
            "_load_exact_owning_session",
            lambda **_kwargs: current,
        )
        monkeypatch.setattr(
            output_publisher.operator_profile_state,
            "_require_active_lease",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            output_publisher,
            "_admission_raw_sha256",
            lambda *_args, **_kwargs: operation_sha256,
        )
        monkeypatch.setattr(
            output_publisher.live_session,
            "_seal_session_value",
            lambda *_args, **_kwargs: SimpleNamespace(
                content_sha256="sha256:" + "c" * 64
            ),
        )
        monkeypatch.setattr(
            output_publisher,
            "_validate_existing_layout",
            observe_replacement_layout,
        )
        monkeypatch.setattr(
            output_publisher,
            "ExclusiveFileLock",
            ObservedExclusiveFileLock,
        )

        with pytest.raises(ValueError, match="identity|guard"):
            output_publisher._finalize_committed_live_start_publication_under_guard(
                output_guard=output_guard,
                operation_lease=object(),  # type: ignore[arg-type]
                bootstrap_lease=object(),  # type: ignore[arg-type]
                operation_admission=operation_admission,  # type: ignore[arg-type]
                session_lease=object(),  # type: ignore[arg-type]
                expected_session=SimpleNamespace(  # type: ignore[arg-type]
                    content_sha256="expected-session-sha256"
                ),
                profile_lease=profile_lease,  # type: ignore[arg-type]
            )

    assert entered_locks == []
    assert _tree_snapshot(replacement_root) == replacement_before


def test_legacy_path_publisher_delegates_and_preserves_existing_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from hsconfig.output_operation_admission import (
        observe_output_operation_admission_under_lease,
    )

    local = tmp_path / "local-app-data"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    output_root = tmp_path / "outputs" / "ShadowPriest"
    real_under_guard = getattr(
        output_publisher,
        "publish_configure_run_under_guard",
        None,
    )
    delegations: list[tuple[object, object, object, object]] = []

    @contextmanager
    def observe_under_guard(rendered: RenderedConfigureRun, **kwargs: object):
        assert real_under_guard is not None
        output_guard = kwargs["output_guard"]
        operation_lease = kwargs["operation_lease"]
        bootstrap_lease = kwargs["bootstrap_lease"]
        publication_authorization = kwargs["publication_authorization"]
        assert type(output_guard).__name__ == "PlainDirectoryMutationGuard"
        assert type(bootstrap_lease).__name__ == "OutputChildBootstrapLease"
        assert type(publication_authorization).__name__ == (
            "OutputPublicationAuthorization"
        )
        output_guard.validate()
        assert observe_output_operation_admission_under_lease(operation_lease) is None
        assert kwargs["fault_hook"] is output_publisher.no_fault
        delegations.append(
            (
                output_guard,
                operation_lease,
                bootstrap_lease,
                publication_authorization,
            )
        )
        with real_under_guard(rendered, **kwargs) as published:
            yield published

    monkeypatch.setattr(
        output_publisher,
        "publish_configure_run_under_guard",
        observe_under_guard,
        raising=False,
    )
    first = publish_configure_run(rendered_runs[0], output_root)
    assert len(delegations) == 1
    delegations.clear()
    second = publish_configure_run(rendered_runs[0], output_root)
    assert len(delegations) == 1
    assert first.content_root_sha256 == second.content_root_sha256
    assert second.reused_existing_revision is True


def test_neutral_lock_bootstrap_supports_first_legacy_publish_without_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    local = tmp_path / "local-app-data"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    published = publish_configure_run(
        rendered_runs[0],
        tmp_path / "outputs" / "ShadowPriest",
    )
    state = local / "HSConfig"
    assert published.package_root.is_dir()
    neutral = _tree_snapshot(state)
    assert "." in neutral and neutral["."][0] == "directory"
    assert "locks" in neutral and neutral["locks"][0] == "directory"
    lock_files = {
        name: row
        for name, row in neutral.items()
        if row[0] == "file"
    }
    assert "locks/output-operation.lock" in lock_files
    child_locks = [
        name
        for name in lock_files
        if name.startswith("locks/output-child-") and name.endswith(".lock")
    ]
    assert len(child_locks) == 1
    assert set(neutral) == {
        ".",
        "locks",
        "locks/output-operation.lock",
        child_locks[0],
    }
    assert all(row[2] == b"" for row in lock_files.values())


def test_neutral_lock_bootstrap_supports_first_legacy_runtime_writer_without_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig.runtime_apply import apply_package
    from tests.test_package_immutability_after_apply import _published_output

    source_local = tmp_path / "source-local-app-data"
    source_local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(source_local))
    output_root, _revision = _published_output(tmp_path / "published-source")
    local = tmp_path / "local-app-data"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    runtime_root = tmp_path / "runtime"
    result = apply_package(
        package_root=output_root,
        runtime_root=runtime_root,
    )
    state = local / "HSConfig"
    assert result["runtime_write_performed"] is True
    assert (runtime_root / ".hsconfig" / "apply.lock").is_file()
    neutral = _tree_snapshot(state)
    assert set(neutral) == {
        ".",
        "locks",
        "locks/output-operation.lock",
    }
    assert neutral["."][0] == neutral["locks"][0] == "directory"
    assert neutral["locks/output-operation.lock"][0] == "file"
    assert neutral["locks/output-operation.lock"][2] == b""


def test_live_preview_and_legacy_publishers_share_output_child_bootstrap_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from queue import Empty

    from tests.test_configure_prepublication_apply import (
        _physical_tree,
        _prepare_pipeline,
    )

    real_lease = output_publisher.lease_output_child_bootstrap

    def assert_route_observes_claim_only_after_lock(
        *,
        output_root: Path,
        route_kind: str,
        payload_pickle_path: Path,
        session_root: Path | None,
        local_app_data: Path,
        expected_error: str,
    ) -> None:
        output_publisher._bootstrap_neutral_output_locks(
            output_root=output_root
        )
        context = multiprocessing.get_context("spawn")
        status_queue = context.Queue()
        process = context.Process(
            target=_output_child_bootstrap_route_worker,
            args=(
                route_kind,
                str(payload_pickle_path),
                None if session_root is None else str(session_root),
                str(local_app_data),
                str(output_root),
                status_queue,
            ),
        )
        process_started = False
        try:
            with real_lease(output_root=output_root):
                try:
                    process.start()
                finally:
                    process_started = process.pid is not None
                try:
                    attempted = status_queue.get(timeout=60)
                except Empty:
                    pytest.fail(
                        "publisher route did not reach the output-child "
                        "bootstrap lease within 60 seconds"
                    )
                assert attempted == ("attempted", "", "")
                process.join(0.1)
                assert process.is_alive()
                claim = output_publisher.output_child_claim_path(output_root)
                claim.write_bytes(b"{}")
                after_claim = _physical_tree(output_root.parent)
            process.join(60)
            if process.is_alive():
                pytest.fail(
                    "publisher route did not finish after bootstrap lease release"
                )
            assert process.exitcode == 0
            try:
                disposition, error_type, detail = status_queue.get(timeout=10)
            except Empty:
                pytest.fail("publisher route did not report its result")
            assert disposition == "error"
            assert error_type == "ValueError"
            assert detail == expected_error
            assert _physical_tree(output_root.parent) == after_claim
        finally:
            process_still_alive = False
            if process_started:
                if process.is_alive():
                    process.terminate()
                    process.join(10)
                    if process.is_alive():
                        process.kill()
                        process.join(10)
                process_still_alive = process.is_alive()
                if not process_still_alive:
                    process.close()
            status_queue.close()
            status_queue.join_thread()
            if process_still_alive:
                pytest.fail("publisher route worker could not be stopped")

    prepared = _prepare_pipeline(
        tmp_path / "preview",
        monkeypatch,
        preview=True,
    )
    preview_payload = tmp_path / "preview-route.pickle"
    preview_payload.write_bytes(pickle.dumps(prepared.request))
    assert_route_observes_claim_only_after_lock(
        output_root=prepared.output_child_root,
        route_kind="live-preview",
        payload_pickle_path=preview_payload,
        session_root=prepared.session_root,
        local_app_data=prepared.local_app_data,
        expected_error="live_start_output_claim_direct_final_invalid",
    )

    legacy_local = tmp_path / "legacy" / "local-app-data"
    legacy_local.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(legacy_local))
    legacy_output_root = tmp_path / "legacy" / "outputs" / "ShadowPriest"
    legacy_output_root.parent.mkdir(parents=True)
    legacy_payload = tmp_path / "legacy-route.pickle"
    legacy_payload.write_bytes(
        pickle.dumps((str(tmp_path / "legacy-route-source"), 1))
    )
    assert_route_observes_claim_only_after_lock(
        output_root=legacy_output_root,
        route_kind="legacy",
        payload_pickle_path=legacy_payload,
        session_root=None,
        local_app_data=legacy_local,
        expected_error="output_child_claim_present",
    )


def test_every_publisher_checks_output_child_claim_under_output_base_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    local = tmp_path / "local-app-data"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    output_root = tmp_path / "outputs" / "ShadowPriest"
    output_root.parent.mkdir(parents=True)
    output_root.mkdir()
    output_publisher._bootstrap_neutral_output_locks(output_root=output_root)
    claim = output_publisher.output_child_claim_path(output_root)
    claim.write_bytes(b"{}")
    with pytest.raises(ValueError, match="claim"):
        publish_configure_run(rendered_runs[0], output_root)
    assert not (output_root / "current.json").exists()


def test_foreign_or_malformed_output_child_claim_blocks_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from tests.test_configure_prepublication_apply import (
        _interrupt_pipeline,
        _physical_tree,
        _prepare_pipeline,
    )

    malformed_root = tmp_path / "malformed"
    local = malformed_root / "local-app-data"
    local.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    output_root = malformed_root / "outputs" / "ShadowPriest"
    output_root.mkdir(parents=True)
    output_publisher._bootstrap_neutral_output_locks(output_root=output_root)
    claim = output_publisher.output_child_claim_path(output_root)
    claim.write_bytes(b"{}")
    before = _physical_tree(malformed_root / "outputs")
    with pytest.raises(ValueError, match="claim"):
        publish_configure_run(rendered_runs[0], output_root)
    assert _physical_tree(malformed_root / "outputs") == before

    prepared = _prepare_pipeline(tmp_path / "foreign", monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_OUTPUT_CHILD_CLAIM_BOUND",
    )
    admission_path = Path(
        interrupted.output_operation_admission_binding["admission_path"]
    )
    admission_path.unlink()
    before = _physical_tree(prepared.output_base_root)
    with pytest.raises(ValueError, match="claim"):
        publish_configure_run(rendered_runs[0], prepared.output_child_root)
    assert _physical_tree(prepared.output_base_root) == before


def test_all_publishers_reject_active_malformed_or_replaced_output_operation_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from hsconfig.output_operation_admission import output_operation_admission_path
    from hsconfig.runtime_apply import apply_package
    from tests.test_configure_prepublication_apply import (
        _interrupt_pipeline,
        _physical_tree,
        _prepare_pipeline,
    )
    from tests.test_package_immutability_after_apply import _published_output

    for state in ("active", "malformed", "replaced"):
        for route in ("publisher", "runtime"):
            case = tmp_path / state / route
            if state == "malformed":
                local = case / "local-app-data"
                local.mkdir(parents=True)
                monkeypatch.setenv("LOCALAPPDATA", str(local))
                output_root = case / "outputs" / "ShadowPriest"
                output_root.mkdir(parents=True)
                output_publisher._bootstrap_neutral_output_locks(
                    output_root=output_root
                )
                output_operation_admission_path().write_bytes(b"{}")
                observed_root = case
            else:
                prepared = _prepare_pipeline(case, monkeypatch)
                interrupted = _interrupt_pipeline(
                    prepared,
                    "AFTER_OUTPUT_OPERATION_ADMISSION_BOUND",
                )
                output_root = prepared.output_child_root
                local = prepared.local_app_data
                observed_root = case
                admission = Path(
                    interrupted.output_operation_admission_binding[
                        "admission_path"
                    ]
                )
                if state == "replaced":
                    raw = admission.read_bytes()
                    identity = path_identity(admission)
                    admission.unlink()
                    admission.write_bytes(raw)
                    assert path_identity(admission) != identity
            before = _physical_tree(observed_root)
            runtime_root = case / "runtime-writer-target"
            if route == "publisher":
                with pytest.raises(ValueError, match="admission"):
                    publish_configure_run(rendered_runs[0], output_root)
            else:
                published_root, _revision = _published_output(case / "source")
                source_after_setup = _physical_tree(observed_root)
                with pytest.raises(ValueError, match="admission"):
                    apply_package(
                        package_root=published_root,
                        runtime_root=runtime_root,
                    )
                assert not runtime_root.exists()
                before = source_after_setup
            assert _physical_tree(observed_root) == before


def test_ordinary_publisher_rejects_foreign_admission_before_output_parent_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from tests.test_configure_prepublication_apply import (
        _interrupt_pipeline,
        _prepare_pipeline,
    )

    prepared = _prepare_pipeline(tmp_path / "active-owner", monkeypatch)
    _interrupt_pipeline(
        prepared,
        "AFTER_OUTPUT_OPERATION_ADMISSION_BOUND",
    )
    unrelated_parent = tmp_path / "unrelated-output-base"
    unrelated_output = unrelated_parent / "ShadowPriest"
    assert not unrelated_parent.exists()

    with pytest.raises(ValueError, match="admission"):
        publish_configure_run(rendered_runs[0], unrelated_output)

    assert not unrelated_parent.exists()


def test_runtime_apply_acquires_operation_lease_before_package_publication_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig import runtime_apply
    from tests.test_package_immutability_after_apply import _published_output

    published_root, _revision = _published_output(tmp_path / "source")
    order: list[str] = []
    real_operation_lease = runtime_apply.lease_output_operation_admission
    real_package_lease = runtime_apply._lease_real_apply_input

    @contextmanager
    def observed_operation_lease() -> object:
        order.append("operation")
        with real_operation_lease() as lease:
            yield lease

    @contextmanager
    def observed_package_lease(package_input: Path) -> object:
        order.append("package")
        with real_package_lease(package_input) as lease:
            yield lease

    monkeypatch.setattr(
        runtime_apply,
        "lease_output_operation_admission",
        observed_operation_lease,
    )
    monkeypatch.setattr(
        runtime_apply,
        "_lease_real_apply_input",
        observed_package_lease,
    )

    runtime_apply.apply_package(
        package_root=published_root,
        runtime_root=tmp_path / "runtime",
    )

    assert order[:2] == ["operation", "package"]


def test_all_publishers_reject_output_operation_staging_or_reserved_temp_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from hsconfig.output_operation_admission import (
        output_operation_admission_reserved_temp_path,
        output_operation_admission_staging_path,
    )
    from hsconfig.runtime_apply import apply_package
    from tests.test_configure_prepublication_apply import _physical_tree
    from tests.test_package_immutability_after_apply import _published_output

    for residue_name, residue_path_factory in (
        ("staging", output_operation_admission_staging_path),
        ("reserved-temp", output_operation_admission_reserved_temp_path),
    ):
        for route in ("publisher", "runtime"):
            case = tmp_path / residue_name / route
            local = case / "local-app-data"
            local.mkdir(parents=True)
            monkeypatch.setenv("LOCALAPPDATA", str(local))
            output_root = case / "outputs" / "ShadowPriest"
            output_root.mkdir(parents=True)
            output_publisher._bootstrap_neutral_output_locks(
                output_root=output_root
            )
            residue_path_factory().write_bytes(b"residue")
            runtime_root = case / "runtime-writer-target"
            before = _physical_tree(case)
            if route == "publisher":
                with pytest.raises(ValueError, match="residue"):
                    publish_configure_run(rendered_runs[0], output_root)
            else:
                published_root, _revision = _published_output(case / "source")
                before = _physical_tree(case)
                with pytest.raises(ValueError, match="residue"):
                    apply_package(
                        package_root=published_root,
                        runtime_root=runtime_root,
                    )
                assert not runtime_root.exists()
            assert _physical_tree(case) == before


def test_public_reconcile_fences_legacy_v1_temp_before_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _task8_live_output_context(
        tmp_path,
        monkeypatch,
        existing_legacy_current=True,
    ) as live:
        journals = output_publisher._load_valid_transactions(
            live.prepared.output_child_root
        )
        assert len(journals) == 1
        _journal_path, legacy = journals[0]
        assert legacy.schema_version == 1
        assert legacy.phase == "finalized"
        transactions = (
            live.prepared.output_child_root / ".publisher" / "transactions"
        )
        legacy_temp = transactions / (
            f".{legacy.transaction_id}.journal.tmp"
        )
        legacy_temp.write_bytes(output_publisher._transaction_bytes(legacy))
        assert output_publisher.output_child_claim_path(
            live.prepared.output_child_root
        ).is_file()
        assert live.operation_admission is not None
        output_root = live.prepared.output_child_root
        output_tree_root = live.prepared.output_base_root
        admission_path = live.operation_admission.admission_path
        before = (
            _tree_snapshot(output_tree_root),
            path_identity(admission_path),
            admission_path.read_bytes(),
        )

    with pytest.raises(
        ValueError,
        match="^publisher_live_start_authority_active$",
    ):
        reconcile_output(output_root)

    assert (
        _tree_snapshot(output_tree_root),
        path_identity(admission_path),
        admission_path.read_bytes(),
    ) == before


def test_owned_atomic_replace_preserves_target_binding_through_secure_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "journal.json"
    temp_path = tmp_path / ".journal.tmp"
    original = b"original-journal"
    replacement = b"replacement-journal"
    target.write_bytes(original)
    original_identity = path_identity(target)
    replacement_identity: tuple[int, int, int] | None = None
    real_secure_replace = output_publisher.secure_replace

    def swap_target_before_secure_replace(
        source: Path,
        delegated_target: Path,
        **kwargs: object,
    ) -> None:
        nonlocal replacement_identity
        assert source == temp_path
        assert delegated_target == target
        same_bytes_replacement = tmp_path / "same-bytes-replacement"
        same_bytes_replacement.write_bytes(original)
        replacement_identity = path_identity(same_bytes_replacement)
        assert replacement_identity != original_identity
        target.unlink()
        same_bytes_replacement.rename(target)
        real_secure_replace(  # type: ignore[arg-type]
            source,
            delegated_target,
            **kwargs,
        )

    monkeypatch.setattr(
        output_publisher,
        "secure_replace",
        swap_target_before_secure_replace,
    )

    with pytest.raises(
        ValueError,
        match="^filesystem_path_identity_changed$",
    ):
        output_publisher._owned_atomic_replace(
            target,
            replacement,
            temp_path=temp_path,
            expected_target_identity=original_identity,
            expected_target_content=original,
            temp_stage="after_test_temp_write",
        )

    assert replacement_identity is not None
    assert path_identity(target) == replacement_identity
    assert target.read_bytes() == original
    assert temp_path.read_bytes() == replacement


def test_receiptless_foreign_v2_temp_is_rejected_before_any_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _task8_live_output_context(
        tmp_path,
        monkeypatch,
        existing_legacy_current=True,
    ) as live:
        transaction = output_publisher._new_transaction(
            live.rendered,
            None,
            schema_version=2,
        )
        assert transaction.phase == "prepared"
        assert transaction.live_start_commit_receipt is None
        transactions = (
            live.prepared.output_child_root / ".publisher" / "transactions"
        )
        temp_path = transactions / (
            f".{transaction.transaction_id}.journal.tmp"
        )
        final_path = transactions / f"{transaction.transaction_id}.json"
        temp_path.write_bytes(output_publisher._transaction_bytes(transaction))
        parsed = output_publisher._parse_transaction(temp_path.read_bytes())
        assert parsed == transaction
        assert parsed.schema_version == 2
        assert not final_path.exists()

        authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            output_guard=live.guard,
            operation_admission=live.operation_admission,
            session_lease=live.session_lease,
            expected_session=live.current,
            profile_lease=live.profile_lease,
        )
        assert live.operation_admission is not None
        output_tree_root = live.prepared.output_base_root
        admission_path = live.operation_admission.admission_path
        temp_identity = path_identity(temp_path)
        temp_bytes = temp_path.read_bytes()
        before = (
            _tree_snapshot(output_tree_root),
            path_identity(admission_path),
            admission_path.read_bytes(),
        )
        secure_replace_calls: list[tuple[Path, Path]] = []
        real_secure_replace = output_publisher.secure_replace

        def observed_secure_replace(
            source: Path,
            target: Path,
            **kwargs: object,
        ) -> None:
            secure_replace_calls.append((source, target))
            real_secure_replace(  # type: ignore[arg-type]
                source,
                target,
                **kwargs,
            )

        monkeypatch.setattr(
            output_publisher,
            "secure_replace",
            observed_secure_replace,
        )

        with pytest.raises(
            ValueError,
            match="^publisher_transaction_temp_conflict$",
        ):
            with output_publisher.publish_configure_run_under_guard(
                live.rendered,
                output_guard=live.guard,
                operation_lease=live.operation_lease,
                bootstrap_lease=live.bootstrap_lease,
                publication_authorization=authorization,
            ):
                raise AssertionError("receiptless foreign v2 temp was resumed")

        assert secure_replace_calls == []
        assert not final_path.exists()
        assert path_identity(temp_path) == temp_identity
        assert temp_path.read_bytes() == temp_bytes
        assert (
            _tree_snapshot(output_tree_root),
            path_identity(admission_path),
            admission_path.read_bytes(),
        ) == before


@pytest.mark.skipif(os.name != "nt", reason="NTFS ADS is Windows-specific")
@pytest.mark.parametrize(
    "surface",
    (
        "claim",
        "unbound-staging",
        "final-journal",
        "journal-temp",
        "current-temp",
        "current-json",
    ),
)
def test_publisher_authority_files_reject_ntfs_ads_before_observation_or_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    case = tmp_path / surface
    transactions = case / ".publisher" / "transactions"
    transactions.mkdir(parents=True)
    transaction = _unit_transaction()
    publication = output_publisher.OutputPublication(
        schema_version=output_publisher.CURRENT_SCHEMA_VERSION,
        deck_name=transaction.deck_name,
        deck_fingerprint=transaction.deck_fingerprint,
        revision=transaction.revision,
        content_root_sha256=transaction.content_root_sha256,
    )
    if surface == "claim":
        target = output_publisher.output_child_claim_path(case)
        target.write_bytes(b"claim-bytes")

        def invoke() -> object:
            return output_publisher._claim_fingerprint(case)

    elif surface == "unbound-staging":
        target = output_publisher.output_child_claim_staging_path(case)
        target.write_bytes(b"unbound-staging")

        def invoke() -> object:
            return output_publisher._remove_unbound_plain_file(
                target,
                expected_parent_identity=path_identity(case),
                maximum_size=1024,
            )

    elif surface == "final-journal":
        target = transactions / f"{transaction.transaction_id}.json"
        target.write_bytes(output_publisher._transaction_bytes(transaction))

        def invoke() -> object:
            return output_publisher._recover_owned_atomic_temps(
                case,
                current_revision=None,
            )

    elif surface == "journal-temp":
        target = transactions / f".{transaction.transaction_id}.journal.tmp"
        target.write_bytes(output_publisher._transaction_bytes(transaction))

        def invoke() -> object:
            return output_publisher._recover_owned_atomic_temps(
                case,
                current_revision=None,
            )

    elif surface == "current-temp":
        final = transactions / f"{transaction.transaction_id}.json"
        final.write_bytes(output_publisher._transaction_bytes(transaction))
        target = transactions / f".{transaction.transaction_id}.current.tmp"
        target.write_bytes(output_publisher.output_publication_bytes(publication))

        def invoke() -> object:
            return output_publisher._recover_owned_atomic_temps(
                case,
                current_revision=None,
            )

    else:
        target = case / "current.json"
        target.write_bytes(output_publisher.output_publication_bytes(publication))

        def invoke() -> object:
            return output_publisher._snapshot_pointer(case)

    stream = Path(f"{target}:unbound")
    stream_bytes = b"unbound authority bytes\n"
    try:
        stream.write_bytes(stream_bytes)
    except OSError as error:
        pytest.skip(f"NTFS ADS unavailable: {error}")
    monkeypatch.setattr(
        output_publisher,
        "_validate_publisher_residue",
        lambda *_args, **_kwargs: None,
    )
    before = _tree_snapshot(case)
    observed_error: ValueError | None = None
    try:
        invoke()
    except ValueError as error:
        observed_error = error
    after = _tree_snapshot(case)
    stream_after = stream.read_bytes() if stream.exists() else None

    assert (
        None if observed_error is None else str(observed_error),
        after,
        stream_after,
    ) == (
        "filesystem_alternate_data_stream_forbidden",
        before,
        stream_bytes,
    )


def _pointer_receipt_for_ads_test(
    *,
    identity: tuple[int, int, int],
    content: bytes,
) -> output_publisher._LiveStartCommitReceipt:
    digest = "sha256:" + output_publisher.sha256(content).hexdigest()
    unsigned: dict[str, object] = {
        "schema_version": 1,
        "receipt_kind": "live_start_current_pointer_commit",
        "disposition": "pointer_staged",
        "expected_session_sha256": "sha256:" + "a" * 64,
        "operation_admission_identity": [1, 2, 3],
        "operation_admission_sha256": "sha256:" + "b" * 64,
        "claim_identity": [4, 5, 6],
        "claim_sha256": "sha256:" + "c" * 64,
        "output_child_identity": [7, 8, 9],
        "pointer_predecessor_identity": list(identity),
        "pointer_predecessor_size": len(content),
        "pointer_predecessor_sha256": digest,
        "pointer_staging_identity": list(identity),
        "planned_pointer_size": len(content),
        "planned_pointer_sha256": digest,
        "owner_journal_predecessor_identity": None,
        "owner_journal_identity": None,
    }
    payload = {
        **unsigned,
        "content_sha256": "sha256:"
        + output_publisher.sha256(
            output_publisher._canonical_json_bytes(unsigned)
        ).hexdigest(),
    }
    return output_publisher._parse_live_start_commit_receipt(payload)


@pytest.mark.skipif(os.name != "nt", reason="NTFS ADS is Windows-specific")
@pytest.mark.parametrize("surface", ("current", "predecessor"))
def test_pointer_receipt_ads_is_rejected_before_authority_bytes_are_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    pointer = tmp_path / "current.json"
    content = b"pointer-authority\n"
    pointer.write_bytes(content)
    receipt = _pointer_receipt_for_ads_test(
        identity=path_identity(pointer),
        content=content,
    )
    stream = Path(f"{pointer}:unbound")
    stream.write_bytes(b"foreign-stream")
    before = _tree_snapshot(tmp_path)
    reads: list[Path] = []
    real_read = output_publisher.read_file_no_follow

    def observed_read(path: Path, **kwargs: object) -> bytes:
        reads.append(path)
        return real_read(path, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(output_publisher, "read_file_no_follow", observed_read)
    with pytest.raises(
        ValueError,
        match="^filesystem_alternate_data_stream_forbidden$",
    ):
        if surface == "current":
            output_publisher._require_current_pointer_receipt_exact(
                tmp_path,
                receipt,
                content,
            )
        else:
            output_publisher._require_pointer_predecessor_exact(
                tmp_path,
                receipt,
            )

    assert reads == []
    assert _tree_snapshot(tmp_path) == before
    assert stream.read_bytes() == b"foreign-stream"


@pytest.mark.skipif(os.name != "nt", reason="NTFS ADS is Windows-specific")
@pytest.mark.parametrize(
    "surface",
    ("existing-journal-fallback", "owned-temp-verification", "target-content"),
)
def test_atomic_replace_ads_is_rejected_before_authority_read_or_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    reads: list[Path] = []
    replacements: list[tuple[Path, Path]] = []
    injected_before: dict[
        str,
        tuple[str, tuple[int, int, int], bytes | None],
    ] | None = None
    real_read = output_publisher.read_file_no_follow
    real_replace = output_publisher.secure_replace

    def observed_read(path: Path, **kwargs: object) -> bytes:
        reads.append(path)
        return real_read(path, **kwargs)  # type: ignore[arg-type]

    def observed_replace(source: Path, target: Path, **kwargs: object) -> None:
        replacements.append((source, target))
        real_replace(source, target, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(output_publisher, "read_file_no_follow", observed_read)
    monkeypatch.setattr(output_publisher, "secure_replace", observed_replace)
    transaction = _unit_transaction()
    if surface == "existing-journal-fallback":
        target = tmp_path / f"{transaction.transaction_id}.json"
        target.write_bytes(output_publisher._transaction_bytes(transaction))
        stream_owner = target

        def invoke() -> object:
            return output_publisher._write_transaction(target, transaction)

    elif surface == "owned-temp-verification":
        target = tmp_path / "target"
        temp_path = tmp_path / ".target.tmp"
        stream_owner = temp_path
        real_status = output_publisher.plain_file_status

        def status_with_ads(path: Path) -> os.stat_result:
            nonlocal injected_before
            status = real_status(path)
            if path == temp_path and injected_before is None:
                Path(f"{path}:unbound").write_bytes(b"foreign-stream")
                injected_before = _tree_snapshot(tmp_path)
            return status

        monkeypatch.setattr(
            output_publisher,
            "plain_file_status",
            status_with_ads,
        )

        def invoke() -> object:
            return output_publisher._owned_atomic_replace(
                target,
                b"replacement",
                temp_path=temp_path,
                temp_stage="after_test_temp_write",
            )

    else:
        target = tmp_path / "target"
        content = b"target-content"
        target.write_bytes(content)
        stream_owner = target

        def invoke() -> object:
            return output_publisher._validate_owned_replace_target(
                target,
                expected_identity=path_identity(target),
                expected_content=content,
            )

    if surface != "owned-temp-verification":
        Path(f"{stream_owner}:unbound").write_bytes(b"foreign-stream")
    before = _tree_snapshot(tmp_path)
    with pytest.raises(
        ValueError,
        match="^filesystem_alternate_data_stream_forbidden$",
    ):
        invoke()

    assert reads == []
    assert replacements == []
    assert _tree_snapshot(tmp_path) == (
        injected_before
        if surface == "owned-temp-verification"
        else before
    )
    assert Path(f"{stream_owner}:unbound").read_bytes() == b"foreign-stream"


@pytest.mark.skipif(os.name != "nt", reason="NTFS ADS is Windows-specific")
def test_bound_output_admission_ads_is_rejected_before_publisher_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig.live_start_faults import LiveStartFaultPoint
    from hsconfig.output_operation_admission import output_operation_admission_path
    from tests.test_configure_prepublication_apply import (
        _drive_pipeline,
        _prepare_pipeline,
    )

    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    final_path = output_operation_admission_path()
    reads: list[Path] = []
    injected_tree: dict[
        str,
        tuple[str, tuple[int, int, int], bytes | None],
    ] | None = None
    injected_final: tuple[tuple[int, int, int], bytes] | None = None
    stream = Path(f"{final_path}:unbound")
    real_read = output_publisher.read_file_no_follow

    def observed_read(path: Path, **kwargs: object) -> bytes:
        if path == final_path:
            reads.append(path)
        return real_read(path, **kwargs)  # type: ignore[arg-type]

    def inject_after_bound_commit(point: LiveStartFaultPoint) -> None:
        nonlocal injected_tree, injected_final
        if (
            point
            is LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_BOUND_COMMIT_BEFORE_CAS
        ):
            stream.write_bytes(b"foreign-stream")
            injected_tree = _tree_snapshot(prepared.output_base_root)
            injected_final = (path_identity(final_path), final_path.read_bytes())

    monkeypatch.setattr(output_publisher, "read_file_no_follow", observed_read)
    with pytest.raises(
        ValueError,
        match="^filesystem_alternate_data_stream_forbidden$",
    ):
        _drive_pipeline(prepared, fault_hook=inject_after_bound_commit)

    assert injected_tree is not None
    assert injected_final is not None
    assert reads == []
    assert _tree_snapshot(prepared.output_base_root) == injected_tree
    assert (path_identity(final_path), final_path.read_bytes()) == injected_final
    assert stream.read_bytes() == b"foreign-stream"
    assert not (prepared.output_child_root / "current.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="NTFS ADS is Windows-specific")
def test_publication_staging_ads_is_rejected_before_read_or_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "outputs" / "ShadowPriest"
    revisions = output_root / "revisions"
    destination = revisions / ".staging-ads-test"
    destination.mkdir(parents=True)
    reads: list[Path] = []
    replacements: list[tuple[Path, Path]] = []
    injected_tree: dict[
        str,
        tuple[str, tuple[int, int, int], bytes | None],
    ] | None = None
    injected_target: Path | None = None
    real_status = output_publisher.plain_file_status
    real_read = output_publisher.read_file_no_follow
    real_replace = output_publisher.secure_replace

    def status_with_ads(path: Path) -> os.stat_result:
        nonlocal injected_tree, injected_target
        status = real_status(path)
        if (
            path.is_relative_to(destination)
            and stat.S_ISREG(status.st_mode)
            and injected_target is None
        ):
            injected_target = path
            Path(f"{path}:unbound").write_bytes(b"foreign-stream")
            injected_tree = _tree_snapshot(output_root)
        return status

    def observed_read(path: Path, **kwargs: object) -> bytes:
        if path.is_relative_to(destination):
            reads.append(path)
        return real_read(path, **kwargs)  # type: ignore[arg-type]

    def observed_replace(source: Path, target: Path, **kwargs: object) -> None:
        replacements.append((source, target))
        real_replace(source, target, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(output_publisher, "plain_file_status", status_with_ads)
    monkeypatch.setattr(output_publisher, "read_file_no_follow", observed_read)
    monkeypatch.setattr(output_publisher, "secure_replace", observed_replace)
    with pytest.raises(
        ValueError,
        match="^filesystem_alternate_data_stream_forbidden$",
    ):
        output_publisher._write_rendered_run(rendered_runs[0], destination)

    assert injected_tree is not None
    assert injected_target is not None
    assert reads == []
    assert replacements == []
    assert _tree_snapshot(output_root) == injected_tree
    assert Path(f"{injected_target}:unbound").read_bytes() == b"foreign-stream"
    assert not (output_root / "current.json").exists()
    assert not any(path.name.startswith("rev-") for path in revisions.iterdir())


def test_receiptless_v2_final_with_pointer_temp_is_rejected_before_unlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    output_publisher._ensure_layout(output_root)
    transaction = output_publisher._new_transaction(
        rendered_runs[0],
        None,
        schema_version=2,
    )
    assert transaction.phase == "prepared"
    assert transaction.live_start_commit_receipt is None
    transactions = output_root / ".publisher" / "transactions"
    final_path = transactions / f"{transaction.transaction_id}.json"
    pointer_temp = transactions / f".{transaction.transaction_id}.current.tmp"
    final_path.write_bytes(output_publisher._transaction_bytes(transaction))
    publication = output_publisher.OutputPublication(
        schema_version=output_publisher.CURRENT_SCHEMA_VERSION,
        deck_name=transaction.deck_name,
        deck_fingerprint=transaction.deck_fingerprint,
        revision=transaction.revision,
        content_root_sha256=transaction.content_root_sha256,
    )
    pointer_temp.write_bytes(output_publisher.output_publication_bytes(publication))
    authority = output_publisher._LiveStartTempRecoveryAuthority(
        expected_session_sha256="sha256:" + "a" * 64,
        operation_admission_identity=(1, 2, 3),
        operation_admission_sha256="sha256:" + "b" * 64,
        claim_identity=(4, 5, 6),
        claim_sha256="sha256:" + "c" * 64,
        output_child_identity=path_identity(output_root),
    )
    before = _tree_snapshot(output_root)
    unlink_calls: list[Path] = []
    real_secure_unlink = output_publisher.secure_unlink

    def observed_secure_unlink(path: Path, **kwargs: object) -> None:
        unlink_calls.append(path)
        real_secure_unlink(path, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        output_publisher,
        "secure_unlink",
        observed_secure_unlink,
    )
    monkeypatch.setattr(
        output_publisher,
        "_validate_publisher_residue",
        lambda *_args, **_kwargs: None,
    )
    observed_error: ValueError | None = None
    try:
        output_publisher._recover_owned_atomic_temps(
            output_root,
            current_revision=None,
            preserve_bound_live_pointer_temps=True,
            live_start_authority=authority,
        )
    except ValueError as error:
        observed_error = error

    assert (
        None if observed_error is None else str(observed_error)
    ) == "publisher_transaction_temp_conflict"
    assert unlink_calls == []
    assert _tree_snapshot(output_root) == before


@pytest.mark.parametrize(
    "authority_field",
    ("session", "operation", "claim", "output-child"),
)
def test_v2_transaction_temp_requires_matching_live_authority_before_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority_field: str,
) -> None:
    class PointerCommittedJournalTempCrash(BaseException):
        pass

    with _task8_live_output_context(tmp_path, monkeypatch) as live:
        _leave_live_pointer_staging_bound(live, monkeypatch)
        first_authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            output_guard=live.guard,
            operation_admission=live.operation_admission,
            session_lease=live.session_lease,
            expected_session=live.current,
            profile_lease=live.profile_lease,
        )

        def crash_after_pointer_committed_temp_flush(stage: str) -> None:
            if stage == "after_journal_pointer_committed_temp_write":
                raise PointerCommittedJournalTempCrash

        with pytest.raises(PointerCommittedJournalTempCrash):
            with output_publisher.publish_configure_run_under_guard(
                live.rendered,
                output_guard=live.guard,
                operation_lease=live.operation_lease,
                bootstrap_lease=live.bootstrap_lease,
                publication_authorization=first_authorization,
                fault_hook=crash_after_pointer_committed_temp_flush,
            ):
                raise AssertionError(
                    "pointer-committed journal temp crash was not reached"
                )

        transactions = (
            live.prepared.output_child_root / ".publisher" / "transactions"
        )
        final_paths = list(transactions.glob("[0-9a-f]*.json"))
        temp_paths = list(transactions.glob(".*.journal.tmp"))
        assert len(final_paths) == 1
        assert len(temp_paths) == 1
        final_transaction = output_publisher._parse_transaction(
            final_paths[0].read_bytes()
        )
        temp_path = temp_paths[0]
        temp_identity = path_identity(temp_path)
        temp_transaction = output_publisher._parse_transaction(
            temp_path.read_bytes()
        )
        assert final_transaction.phase == "pointer_staging_bound"
        assert temp_transaction.phase == "pointer_committed"
        receipt = temp_transaction.live_start_commit_receipt
        assert receipt is not None
        assert receipt.owner_journal_identity == temp_identity

        def changed_identity(
            identity: tuple[int, int, int],
        ) -> tuple[int, int, int]:
            return (identity[0], identity[1] + 1, identity[2])

        receipt_payload = (
            output_publisher._live_start_commit_receipt_unsigned_payload(
                receipt
            )
        )
        if authority_field == "session":
            receipt_payload["expected_session_sha256"] = (
                "sha256:" + "0" * 64
            )
        elif authority_field == "operation":
            receipt_payload["operation_admission_identity"] = list(
                changed_identity(receipt.operation_admission_identity)
            )
        elif authority_field == "claim":
            receipt_payload["claim_identity"] = list(
                changed_identity(receipt.claim_identity)
            )
        else:
            receipt_payload["output_child_identity"] = list(
                changed_identity(receipt.output_child_identity)
            )
        receipt_payload["content_sha256"] = "sha256:" + output_publisher.sha256(
            output_publisher._canonical_json_bytes(receipt_payload)
        ).hexdigest()
        tampered_receipt = output_publisher._parse_live_start_commit_receipt(
            receipt_payload
        )
        assert tampered_receipt.owner_journal_identity == temp_identity
        temp_path.write_bytes(
            output_publisher._transaction_bytes(
                replace(
                    temp_transaction,
                    live_start_commit_receipt=tampered_receipt,
                )
            )
        )
        assert path_identity(temp_path) == temp_identity

        second_authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            output_guard=live.guard,
            operation_admission=live.operation_admission,
            session_lease=live.session_lease,
            expected_session=live.current,
            profile_lease=live.profile_lease,
        )
        output_tree_root = live.prepared.output_base_root
        admission_path = live.operation_admission.admission_path
        before = (
            _tree_snapshot(output_tree_root),
            path_identity(admission_path),
            admission_path.read_bytes(),
        )

        with pytest.raises(
            ValueError,
            match="^output_publication_authorization_expired$",
        ):
            with output_publisher.publish_configure_run_under_guard(
                live.rendered,
                output_guard=live.guard,
                operation_lease=live.operation_lease,
                bootstrap_lease=live.bootstrap_lease,
                publication_authorization=second_authorization,
            ):
                raise AssertionError("tampered v2 temp was resumed")

        assert (
            _tree_snapshot(output_tree_root),
            path_identity(admission_path),
            admission_path.read_bytes(),
        ) == before


def test_legacy_v1_owner_identity_replacement_blocks_v2_upgrade_temp_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _task8_live_output_context(
        tmp_path,
        monkeypatch,
        existing_legacy_current=True,
    ) as live:
        _transactions, final_path, temp_path = (
            _leave_legacy_finalized_owner_v2_upgrade_temp(
                live,
                monkeypatch,
            )
        )
        legacy_bytes = final_path.read_bytes()
        legacy_identity = path_identity(final_path)
        same_bytes_replacement = final_path.with_name("legacy-replacement")
        same_bytes_replacement.write_bytes(legacy_bytes)
        replacement_identity = path_identity(same_bytes_replacement)
        assert replacement_identity != legacy_identity
        final_path.unlink()
        same_bytes_replacement.rename(final_path)
        assert path_identity(final_path) == replacement_identity
        assert temp_path.is_file()
        authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
            operation_lease=live.operation_lease,
            bootstrap_lease=live.bootstrap_lease,
            output_guard=live.guard,
            operation_admission=live.operation_admission,
            session_lease=live.session_lease,
            expected_session=live.current,
            profile_lease=live.profile_lease,
        )
        output_tree_root = live.prepared.output_base_root
        admission_path = live.operation_admission.admission_path
        before = (
            _tree_snapshot(output_tree_root),
            path_identity(admission_path),
            admission_path.read_bytes(),
        )

        with pytest.raises(
            ValueError,
            match="identity|authority|conflict|changed",
        ):
            with output_publisher.publish_configure_run_under_guard(
                live.rendered,
                output_guard=live.guard,
                operation_lease=live.operation_lease,
                bootstrap_lease=live.bootstrap_lease,
                publication_authorization=authorization,
            ):
                raise AssertionError("replaced legacy owner was upgraded")

        assert (
            _tree_snapshot(output_tree_root),
            path_identity(admission_path),
            admission_path.read_bytes(),
        ) == before
@pytest.mark.parametrize(
    "entrypoint",
    ("controller", "unwrapped", "shared", "reconcile"),
)
def test_controller_legacy_and_preview_publishers_reject_matching_admission_before_pointer_or_revision_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
) -> None:
    from tests.test_runtime_live_admission import _build_admission

    case = tmp_path / entrypoint
    admission_path, _raw = _build_admission(case, monkeypatch)
    operation_path = admission_path.with_name("output-operation-admission.json")
    operation_path.unlink()
    output_root = case / "output" / "ShadowPriest"
    first = build_rendered_run(case / "rendered-first", 1)
    rendered = build_rendered_run(case / "rendered-second", 2)
    output_publisher.publish_configure_run(first, output_root)
    before = _tree_snapshot(output_root)
    publish_lock_held = Event()
    release_publish = Event()
    result: Queue[object] = Queue()
    real_lock = output_publisher.ExclusiveFileLock
    paused = False

    @contextmanager
    def pause_under_publish_lock(
        path: Path,
        *args: object,
        **kwargs: object,
    ):
        nonlocal paused
        with real_lock(path, *args, **kwargs) as lock:
            if Path(path).name == ".publish.lock" and not paused:
                paused = True
                publish_lock_held.set()
                assert release_publish.wait(timeout=15)
            yield lock

    def invoke() -> None:
        try:
            if entrypoint == "controller":
                result.put(
                    output_publisher.publish_configure_run(rendered, output_root)
                )
            elif entrypoint == "unwrapped":
                result.put(
                    output_publisher._publish_configure_run_unwrapped(
                        rendered,
                        output_root,
                    )
                )
            elif entrypoint == "reconcile":
                result.put(output_publisher.reconcile_output(output_root))
            else:
                from hsconfig.output_operation_admission import (
                    lease_output_operation_admission,
                )
                from hsconfig.package_io import hold_plain_directory

                with lease_output_operation_admission() as operation_lease:
                    with output_publisher.lease_output_child_bootstrap(
                        output_root=output_root
                    ) as bootstrap_lease:
                        with hold_plain_directory(output_root) as output_guard:
                            authorization = output_publisher.authorize_output_publication_under_bootstrap_lease(
                                operation_lease=operation_lease,
                                bootstrap_lease=bootstrap_lease,
                                output_guard=output_guard,
                                operation_admission=None,
                                session_lease=None,
                                expected_session=None,
                                profile_lease=None,
                            )
                            with output_publisher.publish_configure_run_under_guard(
                                rendered,
                                output_guard=output_guard,
                                operation_lease=operation_lease,
                                bootstrap_lease=bootstrap_lease,
                                publication_authorization=authorization,
                            ) as published:
                                result.put(published)
        except BaseException as error:
            result.put(error)

    monkeypatch.setattr(
        output_publisher,
        "ExclusiveFileLock",
        pause_under_publish_lock,
    )
    worker = Thread(target=invoke)
    worker.start()
    assert publish_lock_held.wait(timeout=15)
    admission_path, raw = _build_admission(case, monkeypatch)
    atomic_io.atomic_publish_bytes_no_replace(
        path=admission_path,
        staging_path=admission_path.with_name(f"{admission_path.name}.staged"),
        payload=raw,
        expected_parent_identity=path_identity(admission_path.parent),
        maximum_size=64 * 1024,
    )
    release_publish.set()
    worker.join(timeout=20)

    assert not worker.is_alive()
    error = result.get_nowait()
    assert isinstance(error, ValueError)
    assert str(error).startswith("runtime_live_admission")
    assert _tree_snapshot(output_root) == before


@pytest.mark.parametrize("entrypoint", ("controller", "unwrapped"))
def test_matching_admission_blocks_missing_output_root_before_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
) -> None:
    from tests.test_runtime_live_admission import _build_admission

    case = tmp_path / entrypoint
    admission_path, raw = _build_admission(case, monkeypatch)
    output_root = case / "output" / "ShadowPriest"
    output_root.rmdir()
    atomic_io.atomic_publish_bytes_no_replace(
        path=admission_path,
        staging_path=admission_path.with_name(f"{admission_path.name}.staged"),
        payload=raw,
        expected_parent_identity=path_identity(admission_path.parent),
        maximum_size=64 * 1024,
    )
    rendered = build_rendered_run(case / "rendered", 1)

    with pytest.raises(ValueError, match="runtime_live_admission"):
        if entrypoint == "controller":
            output_publisher.publish_configure_run(rendered, output_root)
        else:
            output_publisher._publish_configure_run_unwrapped(
                rendered,
                output_root,
            )

    assert not output_root.exists()


def test_unrelated_output_root_remains_publishable_under_runtime_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_runtime_live_admission import _build_admission

    admission_path, raw = _build_admission(tmp_path, monkeypatch)
    atomic_io.atomic_publish_bytes_no_replace(
        path=admission_path,
        staging_path=admission_path.with_name(f"{admission_path.name}.staged"),
        payload=raw,
        expected_parent_identity=path_identity(admission_path.parent),
        maximum_size=64 * 1024,
    )
    unrelated = tmp_path / "unrelated-output" / "OtherDeck"
    rendered = build_rendered_run(tmp_path / "unrelated-rendered", 1)

    published = output_publisher._publish_configure_run_unwrapped(
        rendered,
        unrelated,
    )

    assert published.output_root == unrelated
    assert (unrelated / "current.json").is_file()


@pytest.mark.parametrize("entrypoint", ("publish", "reconcile"))
def test_windows_runtime_admission_blocks_same_identity_short_alias_before_output_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
    entrypoint: str,
) -> None:
    from hsconfig.runtime_live_admission import (
        load_runtime_live_attempt_admission,
    )
    from tests.test_runtime_live_admission import _build_admission

    long_parent = tmp_path / "Long Runtime Admission Output Ancestor"
    long_parent.mkdir()
    alias_parent = _require_windows_short_path_alias(long_parent)
    admission_path, _raw = _build_admission(long_parent, monkeypatch)
    operation_path = admission_path.with_name("output-operation-admission.json")
    operation_path.unlink()
    long_output_root = long_parent / "output" / "ShadowPriest"
    publish_configure_run(rendered_runs[0], long_output_root)
    admission_path, raw = _build_admission(long_parent, monkeypatch)
    operation_path.unlink()
    atomic_io.atomic_publish_bytes_no_replace(
        path=admission_path,
        staging_path=admission_path.with_name(f"{admission_path.name}.staged"),
        payload=raw,
        expected_parent_identity=path_identity(admission_path.parent),
        maximum_size=64 * 1024,
    )
    observed = load_runtime_live_attempt_admission()
    assert observed is not None
    assert observed.output_root == long_output_root
    alias_output_root = alias_parent / "output" / "ShadowPriest"
    assert alias_output_root != long_output_root
    assert path_identity(alias_output_root) == observed.output_root_identity
    before = _tree_snapshot(long_output_root)

    with pytest.raises(
        ValueError,
        match=r"^runtime_live_admission_blocks_publication$",
    ):
        if entrypoint == "publish":
            publish_configure_run(rendered_runs[1], alias_output_root)
        else:
            reconcile_output(alias_output_root)

    assert _tree_snapshot(long_output_root) == before
