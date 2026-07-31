from __future__ import annotations

import json
import multiprocessing
import os
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from hsconfig.configure_run_model import (
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
)
from hsconfig.output_publisher import publish_configure_run, reconcile_output
from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
from tests.helpers.audited_package_request import audited_request


def build_rendered_run(
    root: Path,
    revision: int,
) -> RenderedConfigureRun:
    package = assemble_package(
        compile_package(audited_request(root, "ShadowPriest"))
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
    rendered = build_rendered_run(Path(source_root), 1)
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


def test_two_first_publishers_share_creation_and_one_reuses(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "shared-source"
    output_root = tmp_path / "ShadowPriest"
    expected = build_rendered_run(source_root, 1).content_root_sha256
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
        for _ in range(2)
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

    def swap_then_create(
        parent: package_io.PlainDirectoryMutationGuard,
        name: str,
    ) -> int:
        nonlocal staging_name
        if (
            staging_name is None
            and name.startswith(".staging-")
            and parent.path.name == "revisions"
        ):
            staging_name = name
            parent.path.rename(
                parent.path.with_name("revisions-owned-moved")
            )
            os.symlink(
                external,
                parent.path,
                target_is_directory=True,
            )
        return original_create(parent, name)

    monkeypatch.setattr(
        package_io,
        "_create_windows_child_directory_descriptor",
        swap_then_create,
    )

    with pytest.raises((OSError, ValueError)):
        publish_configure_run(rendered_runs[0], output_root)

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

    def swap_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal temp_name
        target = Path(path)
        if temp_name is None and target.name.endswith(".journal.tmp"):
            temp_name = target.name
            target.parent.rename(
                target.parent.with_name("transactions-owned-moved")
            )
            os.symlink(
                external,
                target.parent,
                target_is_directory=True,
            )
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
        nonlocal temp_name
        if temp_name is None and target.name.endswith(".journal.tmp"):
            temp_name = target.name
            target.parent.rename(
                target.parent.with_name("transactions-owned-moved")
            )
            os.symlink(
                external,
                target.parent,
                target_is_directory=True,
            )
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
        try:
            os.symlink(
                external,
                staging / "01_manifest",
                target_is_directory=True,
            )
        except OSError:
            pytest.skip("directory symlinks unavailable")
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

    def swap_parent(target: Path) -> None:
        nonlocal swapped
        if swapped:
            return
        swapped = True
        moved = target.parent.with_name("01_manifest-owned-moved")
        target.parent.rename(moved)
        os.symlink(external, target.parent, target_is_directory=True)

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

    def swap_then_child_open(
        target: Path,
        *,
        create: bool,
        write: bool,
    ) -> int:
        nonlocal attempted
        if (
            not attempted
            and target.name == "input.json"
            and target.parent.name == "01_manifest"
            and ".staging-" in str(target)
        ):
            attempted = True
            revisions = target.parents[2]
            revisions.rename(
                revisions.with_name("revisions-owned-moved")
            )
            os.symlink(
                external,
                revisions,
                target_is_directory=True,
            )
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

    assert attempted
    assert tuple(external.iterdir()) == ()


def test_symlinked_existing_ancestor_is_rejected_before_mutation(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    alias = tmp_path / "outputs-alias"
    try:
        os.symlink(external, alias, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")

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
    try:
        os.symlink(external, output_root / ".publish.lock")
    except OSError:
        pytest.skip("file symlinks unavailable")

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
