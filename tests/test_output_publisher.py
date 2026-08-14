from __future__ import annotations

import errno
import json
import multiprocessing
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import hsconfig.output_publisher as output_publisher

from hsconfig.configure_run_model import (
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
)
from hsconfig.output_publisher import publish_configure_run, reconcile_output
from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
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
    if os.name != "nt":
        pytest.skip("Windows 8.3 path alias regression")
    import ctypes
    from ctypes import wintypes

    import hsconfig.package_io as package_io

    long_parent = tmp_path / "Long Ancestor Directory For Short Path Alias"
    long_parent.mkdir()
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
    required = get_short_path(str(long_parent), None, 0)
    if required == 0:
        pytest.skip("Windows short paths unavailable")
    buffer = ctypes.create_unicode_buffer(required)
    written = get_short_path(str(long_parent), buffer, len(buffer))
    if written == 0 or written >= len(buffer):
        pytest.skip("Windows short path could not be obtained")
    alias_parent = Path(buffer.value)
    if alias_parent.resolve(strict=True) == alias_parent.absolute():
        pytest.skip("Windows volume did not provide an alternate spelling")

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
    monkeypatch.setattr(output_publisher, "_ensure_layout", lambda _root: None)
    monkeypatch.setattr(output_publisher, "_capture_layout_guards", lambda _root: ())
    monkeypatch.setattr(output_publisher, "_validate_layout_guards", lambda _guards: None)
    monkeypatch.setattr(output_publisher, "ExclusiveFileLock", _NoopLock)
    monkeypatch.setattr(output_publisher, "_reconcile_locked", lambda _root: None)
    monkeypatch.setattr(output_publisher, "_snapshot_pointer", lambda _root: object())
    monkeypatch.setattr(output_publisher, "_new_transaction", lambda *_args: transaction)
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

    monkeypatch.setattr(output_publisher, "resolve_current_publication_unlocked", resolve)
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
            publish_configure_run(rendered, root)
    else:
        result = publish_configure_run(rendered, root)
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
    monkeypatch.setattr(output_publisher, "resolve_current_publication_unlocked", lambda _root: (publication, object()))
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
            if mode == "final_root" and root_calls == 4:
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
                mode == "owned" and nested_calls >= 3
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
