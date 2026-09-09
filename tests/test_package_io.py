from __future__ import annotations

import errno
import json
import multiprocessing
import os
from pathlib import Path
import signal
import stat
import sys
from types import SimpleNamespace
from hashlib import sha256
from typing import Any

import pytest

from hsconfig import package_io


def _one_file_tree(tmp_path: Path) -> Path:
    root = tmp_path / "package"
    root.mkdir()
    (root / "payload.json").write_text('{"ok":true}', encoding="utf-8")
    return root


def _complete_physical_tree(
    root: Path,
) -> dict[str, tuple[str, tuple[int, int, int], bytes | None]]:
    if not root.exists():
        return {}
    result = {".": ("directory", package_io.path_identity(root), None)}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result[relative] = (
                "directory",
                package_io.path_identity(path),
                None,
            )
        elif path.is_file():
            result[relative] = (
                "file",
                package_io.path_identity(path),
                path.read_bytes(),
            )
        else:
            result[relative] = (
                "unsafe",
                package_io.path_identity(path),
                None,
            )
    return result


def _windows_drive_root_or_skip(tmp_path: Path) -> Path:
    if os.name != "nt":
        pytest.skip("drive-root ADS validation is Windows-specific")
    root = Path(tmp_path.anchor)
    assert root.is_absolute()
    assert root.parent == root
    assert root.name == ""
    return root


def _windows_admin_share_root_or_skip() -> Path:
    if os.name != "nt":
        pytest.skip("UNC-root ADS validation is Windows-specific")
    root = Path("\\" * 2 + "\\".join(("localhost", "ADMIN$")))
    try:
        status = root.lstat()
    except OSError as error:
        pytest.skip(f"local ADMIN$ share is unavailable: {error}")
    if not stat.S_ISDIR(status.st_mode):
        pytest.fail("available local ADMIN$ authority is not a directory")
    if package_io.status_is_reparse(status):
        pytest.fail("available local ADMIN$ authority is a reparse point")
    assert root.parent == root
    assert root.name == ""
    return root


def _create_ntfs_stream_or_skip(path: Path) -> Path:
    if os.name != "nt":
        pytest.skip("NTFS alternate data streams are Windows-specific")
    probe_path = path.parent / ".hsconfig-package-io-ads-probe"
    probe_stream_path = Path(f"{probe_path}:probe")
    probe_path.write_bytes(b"")
    try:
        probe_stream_path.write_bytes(b"probe")
    except OSError as error:
        pytest.skip(f"test volume does not support NTFS ADS: {error}")
    finally:
        probe_stream_path.unlink(missing_ok=True)
        probe_path.unlink(missing_ok=True)
    stream_path = Path(f"{path}:review-fix")
    stream_path.write_bytes(b"foreign-stream")
    return stream_path


def test_bounded_package_snapshot_returns_stable_sorted_content(tmp_path: Path) -> None:
    root = tmp_path / "package"
    (root / "reports").mkdir(parents=True)
    (root / "z.json").write_text("{}", encoding="utf-8")
    (root / "reports" / "a.json").write_text('{"value":1}', encoding="utf-8")

    view = package_io.snapshot_bounded_filesystem_package(root)

    assert view.file_names() == ("reports/a.json", "z.json")
    assert view.directory_names == ("reports",)
    assert view.read_bytes("z.json") == b"{}"
    assert view.read_json("reports/a.json") == {"value": 1}
    assert view.exists("reports/a.json")
    assert not view.exists("../escape.json")
    with pytest.raises(FileNotFoundError, match="missing.json"):
        view.read_bytes("missing.json")


def test_no_replace_commit_is_parent_identity_bound_on_windows_and_posix(
    tmp_path: Path,
) -> None:
    rejected_source = tmp_path / "rejected.json.staged"
    rejected_target = tmp_path / "rejected.json"
    rejected_source.write_bytes(b"rejected")
    parent_identity = package_io.path_identity(tmp_path)
    wrong_parent_identity = (
        parent_identity[0],
        parent_identity[1] + 1,
        parent_identity[2],
    )

    with pytest.raises(ValueError, match="identity"):
        package_io.secure_commit_sibling_no_replace(
            source_path=rejected_source,
            target_path=rejected_target,
            expected_source_identity=package_io.path_identity(
                rejected_source
            ),
            expected_parent_identity=wrong_parent_identity,
        )

    assert rejected_source.read_bytes() == b"rejected"
    assert not rejected_target.exists()

    source = tmp_path / "authority.json.staged"
    target = tmp_path / "authority.json"
    source.write_bytes(b"authority")
    expected = package_io.path_identity(source)
    result = package_io.secure_commit_sibling_no_replace(
        source_path=source,
        target_path=target,
        expected_source_identity=expected,
        expected_parent_identity=parent_identity,
    )
    assert result == expected == package_io.path_identity(target)
    assert not source.exists()


def test_no_replace_rejects_foreign_source_hardlink_before_target_creation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "authority.json.staged"
    foreign = tmp_path / "foreign-hardlink.json"
    target = tmp_path / "authority.json"
    source.write_bytes(b"authority")
    os.link(source, foreign)
    expected = package_io.path_identity(source)
    parent_identity = package_io.path_identity(tmp_path)

    with pytest.raises(ValueError, match="identity|link"):
        package_io.secure_commit_sibling_no_replace(
            source_path=source,
            target_path=target,
            expected_source_identity=expected,
            expected_parent_identity=parent_identity,
        )

    assert not target.exists()
    assert package_io.path_identity(source) == expected
    assert package_io.path_identity(foreign) == expected
    assert source.stat().st_nlink == foreign.stat().st_nlink == 2
    assert source.read_bytes() == foreign.read_bytes() == b"authority"


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX hard-link publication")
def test_no_replace_posix_hook_fires_after_exact_link_before_source_unlink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "authority.json.staged"
    target = tmp_path / "authority.json"
    source.write_bytes(b"authority")
    expected = package_io.path_identity(source)
    events: list[str] = []

    def observe_link_boundary(point: str) -> None:
        events.append(point)
        assert point == "after_posix_link_before_source_unlink"
        assert package_io.path_identity(source) == expected
        assert package_io.path_identity(target) == expected
        assert source.stat().st_nlink == target.stat().st_nlink == 2
        assert source.read_bytes() == target.read_bytes() == b"authority"

    result = package_io.secure_commit_sibling_no_replace(
        source_path=source,
        target_path=target,
        expected_source_identity=expected,
        expected_parent_identity=package_io.path_identity(tmp_path),
        fault_hook=observe_link_boundary,
    )
    assert events == ["after_posix_link_before_source_unlink"]
    assert result == expected == package_io.path_identity(target)
    assert target.stat().st_nlink == 1
    assert not source.exists()


def _posix_commit_until_link_boundary(
    root_text: str,
    expected_source: tuple[int, int, int],
    expected_parent: tuple[int, int, int],
    ready: Any,
) -> None:
    root = Path(root_text)
    source = root / "authority.json.staged"
    target = root / "authority.json"

    def wait_for_parent_kill(point: str) -> None:
        ready.send(
            (
                point,
                package_io.path_identity(source),
                package_io.path_identity(target),
                source.stat().st_nlink,
                target.stat().st_nlink,
            )
        )
        signal.pause()
        raise AssertionError("linked child must be killed before source unlink")

    package_io.secure_commit_sibling_no_replace(
        source_path=source,
        target_path=target,
        expected_source_identity=expected_source,
        expected_parent_identity=expected_parent,
        fault_hook=wait_for_parent_kill,
    )


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX SIGKILL and hard links")
def test_no_replace_posix_hard_kill_after_link_resumes_bound_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "authority.json.staged"
    target = tmp_path / "authority.json"
    source.write_bytes(b"authority")
    expected = package_io.path_identity(source)
    parent_identity = package_io.path_identity(tmp_path)
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(
        target=_posix_commit_until_link_boundary,
        args=(str(tmp_path), expected, parent_identity, sender),
    )
    child.start()
    sender.close()
    try:
        assert receiver.poll(15), (
            f"real link boundary not reached; child exit code: {child.exitcode}"
        )
        assert receiver.recv() == (
            "after_posix_link_before_source_unlink",
            expected,
            expected,
            2,
            2,
        )
        child.kill()
        child.join(10)
        assert child.exitcode == -signal.SIGKILL
    finally:
        if child.is_alive():
            child.kill()
            child.join(10)
        receiver.close()
        child.close()

    assert package_io.path_identity(source) == expected
    assert package_io.path_identity(target) == expected
    assert source.stat().st_nlink == target.stat().st_nlink == 2
    assert source.read_bytes() == target.read_bytes() == b"authority"
    resume_events: list[str] = []
    result = package_io.secure_commit_sibling_no_replace(
        source_path=source,
        target_path=target,
        expected_source_identity=expected,
        expected_parent_identity=parent_identity,
        fault_hook=resume_events.append,
    )
    assert resume_events == ["after_posix_link_before_source_unlink"]
    assert result == expected == package_io.path_identity(target)
    assert target.read_bytes() == b"authority"
    assert target.stat().st_nlink == 1
    assert not source.exists()


@pytest.mark.parametrize(
    ("constant", "value", "with_directory", "reason"),
    [
        ("MAX_FILESYSTEM_DEPTH", -1, False, "filesystem_tree_depth_limit"),
        (
            "MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY",
            0,
            False,
            "filesystem_directory_entry_limit",
        ),
        ("MAX_FILESYSTEM_NODES", 0, False, "filesystem_node_limit"),
        ("MAX_FILESYSTEM_DIRECTORIES", 0, True, "filesystem_directory_limit"),
        ("MAX_RUN_FILES", 0, False, "filesystem_file_limit"),
        ("MAX_RUN_TOTAL_BYTES", 0, False, "filesystem_total_size_limit"),
        ("MAX_RUN_PATH_BYTES", 0, False, "filesystem_path_length_limit"),
    ],
)
def test_bounded_package_snapshot_enforces_each_physical_resource_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    constant: str,
    value: int,
    with_directory: bool,
    reason: str,
) -> None:
    root = _one_file_tree(tmp_path)
    if with_directory:
        (root / "subdir").mkdir()
    monkeypatch.setattr(package_io, constant, value)

    with pytest.raises(ValueError, match=reason):
        package_io.snapshot_bounded_filesystem_package(root)


def test_bounded_package_snapshot_rejects_reparse_and_noncanonical_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _one_file_tree(tmp_path)
    monkeypatch.setattr(
        package_io,
        "status_is_reparse",
        lambda status: stat.S_ISREG(status.st_mode),
    )
    with pytest.raises(ValueError, match="filesystem_tree_reparse_forbidden"):
        package_io.snapshot_bounded_filesystem_package(root)

    monkeypatch.undo()
    monkeypatch.setattr(package_io, "canonical_relative_path", lambda _value: "other")
    with pytest.raises(ValueError, match="filesystem_path_invalid"):
        package_io.snapshot_bounded_filesystem_package(root)


def test_bounded_package_snapshot_detects_membership_and_identity_races(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _one_file_tree(tmp_path)
    monkeypatch.setattr(package_io, "_bounded_inventory", lambda _root: ((), ()))
    with pytest.raises(ValueError, match="filesystem_tree_membership_changed"):
        package_io.snapshot_bounded_filesystem_package(root)

    monkeypatch.undo()
    real_identity = package_io.path_identity
    calls = 0

    def changing_identity(path: Path) -> package_io.PathIdentity:
        nonlocal calls
        calls += 1
        identity = real_identity(path)
        if calls > 1:
            return identity[0], identity[1], identity[2] ^ 1
        return identity

    monkeypatch.setattr(package_io, "path_identity", changing_identity)
    with pytest.raises(ValueError, match="filesystem_tree_identity_changed"):
        package_io.snapshot_bounded_filesystem_package(root)


def test_bounded_inventory_enforces_limits_and_entry_kinds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _one_file_tree(tmp_path)
    assert package_io._bounded_inventory(root) == (("payload.json",), ())

    monkeypatch.setattr(package_io, "MAX_FILESYSTEM_NODES", 0)
    with pytest.raises(ValueError, match="filesystem_tree_inventory_limit"):
        package_io._bounded_inventory(root)

    monkeypatch.undo()
    monkeypatch.setattr(package_io, "MAX_RUN_PATH_BYTES", 0)
    with pytest.raises(ValueError, match="filesystem_path_length_limit"):
        package_io._bounded_inventory(root)

    monkeypatch.undo()
    monkeypatch.setattr(
        package_io,
        "status_is_reparse",
        lambda status: stat.S_ISREG(status.st_mode),
    )
    with pytest.raises(ValueError, match="filesystem_tree_reparse_forbidden"):
        package_io._bounded_inventory(root)


@pytest.mark.parametrize(
    "name",
    [None, "", ".", "..", "a/b", "a\\b", "a\x00b"],
)
def test_secure_child_name_rejects_ambiguous_or_nested_names(name: object) -> None:
    with pytest.raises(ValueError, match="filesystem_child_name_invalid"):
        package_io._require_child_name(name)  # type: ignore[arg-type]


def test_require_no_alternate_data_streams_accepts_local_drive_root(
    tmp_path: Path,
) -> None:
    root = _windows_drive_root_or_skip(tmp_path)
    identity = package_io.path_identity(root)

    package_io.require_no_alternate_data_streams(
        root,
        expected_identity=identity,
        expected_parent_identity=identity,
        directory=True,
    )


def test_require_no_alternate_data_streams_accepts_authority_only_unc_root() -> None:
    root = _windows_admin_share_root_or_skip()
    identity = package_io.path_identity(root)

    package_io.require_no_alternate_data_streams(
        root,
        expected_identity=identity,
        expected_parent_identity=identity,
        directory=True,
    )


def test_require_no_alternate_data_streams_root_rejects_late_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _windows_drive_root_or_skip(tmp_path)
    identity = package_io.path_identity(root)
    stream_name = f"hsconfig-package-io-late-{os.urandom(16).hex()}"
    stream_path = Path(f"{root}:{stream_name}")
    stream_payload = b"late-root-stream"
    expected_stream = (f":{stream_name}:$DATA", len(stream_payload))
    opened_descriptors: list[int] = []
    initial_inventories: list[tuple[tuple[str, int], ...]] = []
    final_inventories: list[tuple[tuple[str, int], ...]] = []
    real_open = package_io._open_plain_directory_descriptor
    real_streams = package_io._windows_native_handle_streams

    def recording_open(path: Path, **kwargs: object) -> int:
        descriptor = real_open(path, **kwargs)
        opened_descriptors.append(descriptor)
        return descriptor

    def create_late_stream(
        native_handle: int,
    ) -> tuple[tuple[str, int], ...]:
        initial = real_streams(native_handle)
        initial_inventories.append(initial)
        assert initial == ()
        try:
            with stream_path.open("xb") as stream:
                assert stream.write(stream_payload) == len(stream_payload)
        except OSError as error:
            pytest.skip(f"local root cannot create an NTFS ADS: {error}")
        final = real_streams(native_handle)
        final_inventories.append(final)
        assert expected_stream in final
        return initial

    monkeypatch.setattr(
        package_io,
        "_open_plain_directory_descriptor",
        recording_open,
    )
    monkeypatch.setattr(
        package_io,
        "_windows_native_handle_streams",
        create_late_stream,
    )

    try:
        with pytest.raises(ValueError, match="alternate_data_stream"):
            package_io.require_no_alternate_data_streams(
                root,
                expected_identity=identity,
                expected_parent_identity=identity,
                directory=True,
            )

        assert initial_inventories == [()]
        assert final_inventories == [(expected_stream,)]
        assert stream_path.read_bytes() == stream_payload
        assert opened_descriptors
        for descriptor in opened_descriptors:
            with pytest.raises(OSError):
                os.fstat(descriptor)
    finally:
        stream_path.unlink(missing_ok=True)


def test_require_no_alternate_data_streams_root_contract_fails_closed(
    tmp_path: Path,
) -> None:
    root = _windows_drive_root_or_skip(tmp_path)
    identity = package_io.path_identity(root)
    wrong_identity = identity[0], identity[1] ^ 1, identity[2]

    with pytest.raises(ValueError, match="root_stream_validation_invalid"):
        package_io.require_no_alternate_data_streams(
            root,
            expected_identity=identity,
            expected_parent_identity=identity,
            directory=False,
            expected_size=0,
        )
    with pytest.raises(ValueError, match="root_stream_validation_invalid"):
        package_io.require_no_alternate_data_streams(
            root,
            expected_identity=identity,
            expected_parent_identity=identity,
            directory=True,
            expected_size=0,
        )
    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        package_io.require_no_alternate_data_streams(
            root,
            expected_identity=identity,
            expected_parent_identity=wrong_identity,
            directory=True,
        )
    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        package_io.require_no_alternate_data_streams(
            root,
            expected_identity=wrong_identity,
            expected_parent_identity=wrong_identity,
            directory=True,
        )


@pytest.mark.parametrize("failure_point", ("handle_state", "stream_inventory"))
def test_require_no_alternate_data_streams_root_failure_closes_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    root = _windows_drive_root_or_skip(tmp_path)
    identity = package_io.path_identity(root)
    opened_descriptors: list[int] = []
    strict_share_requests: list[bool] = []
    real_open = package_io._open_plain_directory_descriptor

    def recording_open(path: Path, **kwargs: object) -> int:
        strict_share_requests.append(bool(kwargs.get("deny_write_share", False)))
        descriptor = real_open(path, **kwargs) if kwargs else real_open(path)
        opened_descriptors.append(descriptor)
        return descriptor

    monkeypatch.setattr(
        package_io,
        "_open_plain_directory_descriptor",
        recording_open,
    )

    def fail_probe(_native_handle: int) -> object:
        raise OSError(5, "root ADS probe failed")

    if failure_point == "handle_state":
        monkeypatch.setattr(package_io, "_windows_native_handle_state", fail_probe)
    else:
        monkeypatch.setattr(package_io, "_windows_native_handle_streams", fail_probe)

    with pytest.raises(OSError, match="root ADS probe failed"):
        package_io.require_no_alternate_data_streams(
            root,
            expected_identity=identity,
            expected_parent_identity=identity,
            directory=True,
        )

    assert strict_share_requests == [True]
    assert opened_descriptors
    for descriptor in opened_descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    assert package_io.path_identity(root) == identity


@pytest.mark.parametrize("directory", (False, True))
def test_require_no_alternate_data_streams_preserves_child_behavior(
    tmp_path: Path,
    directory: bool,
) -> None:
    if os.name != "nt":
        pytest.skip("NTFS alternate data streams are Windows-specific")
    parent = tmp_path / "ads-child-parent"
    parent.mkdir()
    child = parent / ("directory" if directory else "file.bin")
    if directory:
        child.mkdir()
        expected_size = None
    else:
        child.write_bytes(b"content")
        expected_size = len(b"content")
    identity = package_io.path_identity(child)
    parent_identity = package_io.path_identity(parent)

    package_io.require_no_alternate_data_streams(
        child,
        expected_identity=identity,
        expected_parent_identity=parent_identity,
        directory=directory,
        expected_size=expected_size,
    )
    stream_path = _create_ntfs_stream_or_skip(child)
    try:
        with pytest.raises(ValueError, match="alternate_data_stream"):
            package_io.require_no_alternate_data_streams(
                child,
                expected_identity=identity,
                expected_parent_identity=parent_identity,
                directory=directory,
                expected_size=expected_size,
            )
    finally:
        stream_path.unlink(missing_ok=True)


def test_report_readers_require_mapping_documents(tmp_path: Path) -> None:
    package = tmp_path / "package"
    reports = package / "reports"
    reports.mkdir(parents=True)

    assert package_io.read_optional_profile(package) is None
    with pytest.raises(ValueError, match="Missing GlobalValues baseline report"):
        package_io.read_required_baseline(package)
    with pytest.raises(ValueError, match="Missing GlobalValues authority matrix report"):
        package_io.read_required_globalvalues_authority_matrix(package)

    documents = {
        "globalvalues_profile.json": package_io.read_optional_profile,
        "globalvalues_baseline.json": package_io.read_required_baseline,
        "global_values_authority_matrix.json": (
            package_io.read_required_globalvalues_authority_matrix
        ),
    }
    for name, reader in documents.items():
        (reports / name).write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError, match="must be an object"):
            reader(package)
        (reports / name).write_text(json.dumps({"name": name}), encoding="utf-8")
        assert reader(package) == {"name": name}


def test_research_output_directory_must_be_empty_or_absent(tmp_path: Path) -> None:
    absent = tmp_path / "absent"
    package_io.prepare_research_output_dir(absent)

    file_path = tmp_path / "file"
    file_path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="exists and is not a directory"):
        package_io.prepare_research_output_dir(file_path)

    empty = tmp_path / "empty"
    empty.mkdir()
    package_io.prepare_research_output_dir(empty)
    (empty / "owned.txt").write_text("occupied", encoding="utf-8")
    with pytest.raises(ValueError, match="Refusing to overwrite non-empty"):
        package_io.prepare_research_output_dir(empty)


def test_file_state_omits_ctime_only_for_windows_semantics(tmp_path: Path) -> None:
    path = tmp_path / "file.bin"
    path.write_bytes(b"content")
    status = path.stat()

    assert package_io._file_state(status, platform_name="nt")[-1] is None
    assert package_io._file_state(status, platform_name="posix")[-1] == status.st_ctime_ns


def test_secure_file_lifecycle_binds_parent_and_child_identity(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    parent_identity = package_io.path_identity(parent)
    path = parent / "payload.bin"

    descriptor = package_io.secure_open_file_descriptor(
        path,
        create=True,
        write=True,
        expected_parent_identity=parent_identity,
    )
    try:
        assert os.write(descriptor, b"payload") == 7
    finally:
        os.close(descriptor)

    file_identity = package_io.path_identity(path)
    descriptor = package_io.secure_open_file_descriptor(
        path,
        create=False,
        write=False,
        expected_parent_identity=parent_identity,
    )
    try:
        assert os.read(descriptor, 7) == b"payload"
    finally:
        os.close(descriptor)

    with pytest.raises(FileExistsError):
        descriptor = package_io.secure_open_file_descriptor(
            path,
            create=True,
            write=True,
            expected_parent_identity=parent_identity,
        )
        os.close(descriptor)
    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        package_io.secure_unlink(path, expected_identity=(0, 0, 0))

    assert package_io.secure_unlink(
        path,
        expected_identity=file_identity,
        expected_parent_identity=parent_identity,
    )
    assert not path.exists()
    assert not package_io.secure_unlink(path, missing_ok=True)
    with pytest.raises(FileNotFoundError):
        package_io.secure_unlink(path)


def test_secure_directory_lifecycle_rejects_wrong_node_kinds(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    parent_identity = package_io.path_identity(parent)
    child = parent / "child"

    child_identity = package_io.secure_create_directory(
        child,
        expected_parent_identity=parent_identity,
    )
    assert package_io.path_identity(child) == child_identity
    with pytest.raises(FileNotFoundError):
        package_io.secure_rmdir(parent / "missing-file", missing_ok=False)

    file_path = parent / "file"
    file_path.write_bytes(b"content")
    with pytest.raises(ValueError, match="filesystem_directory_invalid"):
        package_io.secure_rmdir(file_path)
    with pytest.raises(ValueError, match="filesystem_file_invalid"):
        package_io.secure_unlink(child)
    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        package_io.secure_rmdir(child, expected_identity=(0, 0, 0))

    assert package_io.secure_rmdir(
        child,
        expected_identity=child_identity,
        expected_parent_identity=parent_identity,
    )
    assert not package_io.secure_rmdir(child, missing_ok=True)


def test_secure_replace_supports_same_and_cross_parent_moves(tmp_path: Path) -> None:
    source_parent = tmp_path / "source"
    target_parent = tmp_path / "target"
    source_parent.mkdir()
    target_parent.mkdir()
    source = source_parent / "source.txt"
    source.write_text("first", encoding="utf-8")
    source_identity = package_io.path_identity(source)

    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        package_io.secure_replace(
            source,
            source_parent / "wrong-source.txt",
            expected_source_identity=(0, 0, 0),
        )
    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        package_io.secure_replace(
            source,
            source_parent / "wrong-parent.txt",
            expected_target_parent_identity=(0, 0, 0),
        )

    same_parent_target = source_parent / "same.txt"
    package_io.secure_replace(
        source,
        same_parent_target,
        expected_source_identity=source_identity,
        expected_source_parent_identity=package_io.path_identity(source_parent),
        expected_target_parent_identity=package_io.path_identity(source_parent),
        expected_target_absent=True,
    )
    assert same_parent_target.read_text(encoding="utf-8") == "first"

    cross_parent_target = target_parent / "final.txt"
    package_io.secure_replace(
        same_parent_target,
        cross_parent_target,
        expected_source_identity=source_identity,
        expected_source_parent_identity=package_io.path_identity(source_parent),
        expected_target_parent_identity=package_io.path_identity(target_parent),
        expected_target_absent=True,
    )
    assert cross_parent_target.read_text(encoding="utf-8") == "first"

    replacement = source_parent / "replacement.txt"
    replacement.write_text("second", encoding="utf-8")
    with pytest.raises(FileExistsError):
        package_io.secure_replace(
            replacement,
            cross_parent_target,
            expected_target_absent=True,
        )
    package_io.secure_replace(replacement, cross_parent_target)
    assert cross_parent_target.read_text(encoding="utf-8") == "second"


def test_identity_and_no_follow_guards_reject_wrong_filesystem_objects(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    file_path = directory / "file.bin"
    file_path.write_bytes(b"content")
    file_status = package_io.plain_file_status(file_path)

    package_io.require_plain_directory(directory)
    package_io.require_same_identity_resolution(
        file_path,
        expected_status=file_status,
    )
    assert package_io.read_file_no_follow(
        file_path,
        expected_status=file_status,
        maximum_size=7,
    ) == b"content"

    with pytest.raises(ValueError, match="filesystem_directory_invalid"):
        package_io.require_plain_directory(file_path)
    with pytest.raises(ValueError, match="filesystem_file_invalid"):
        package_io.plain_file_status(directory)
    with pytest.raises(ValueError, match="filesystem_file_invalid"):
        package_io.read_file_no_follow(
            file_path,
            expected_status=file_status,
            maximum_size=6,
        )

    other = directory / "other.bin"
    other.write_bytes(b"other")
    with pytest.raises(ValueError, match="filesystem_path_resolution_changed"):
        package_io.require_same_identity_resolution(
            file_path,
            expected_status=other.lstat(),
        )


def test_ancestor_guard_detects_replacement_after_capture(tmp_path: Path) -> None:
    directory = tmp_path / "guarded"
    directory.mkdir()
    guarded = directory / "payload.bin"
    guarded.write_bytes(b"before")
    guard = package_io.capture_plain_ancestor_guard(guarded)
    guard.validate()

    replacement = directory / "replacement.bin"
    replacement.write_bytes(b"after")
    replacement.replace(guarded)

    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        guard.validate()


def test_hardlinked_files_are_rejected_as_ambiguous_package_members(
    tmp_path: Path,
) -> None:
    root = _one_file_tree(tmp_path)
    payload = root / "payload.json"
    alias = root / "alias.json"
    os.link(payload, alias)

    with pytest.raises(ValueError, match="filesystem_file_invalid"):
        package_io.plain_file_status(payload)
    with pytest.raises(ValueError, match="filesystem_tree_entry_invalid"):
        package_io.snapshot_bounded_filesystem_package(root)


def test_child_directory_guard_opens_relative_to_held_parent(
    tmp_path: Path,
) -> None:
    parent_path = tmp_path / "parent"
    child_path = parent_path / "child"
    parent_path.mkdir()
    child_path.mkdir()

    with package_io.hold_plain_directory(parent_path) as parent:
        with parent.hold_child_directory("child") as child:
            descriptor = child.open_file("probe.bin", create=True, write=True)
            try:
                os.write(descriptor, b"bound")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            child.validate()
            assert child.path == child_path
            assert (child_path / "probe.bin").read_bytes() == b"bound"


def test_child_directory_guard_fails_closed_after_visible_parent_swap(
    tmp_path: Path,
) -> None:
    parent_path = tmp_path / "parent"
    moved_path = tmp_path / "moved"
    parent_path.mkdir()
    (parent_path / "child").mkdir()
    with package_io.hold_plain_directory(parent_path) as parent:
        with parent.hold_child_directory("child") as child:
            try:
                parent_path.rename(moved_path)
            except PermissionError:
                pytest.skip("platform prevents a visible rename of the held directory")
            parent_path.mkdir()
            (parent_path / "child").mkdir()
            moved_before = _complete_physical_tree(moved_path)
            visible_before = _complete_physical_tree(parent_path)

            with pytest.raises(ValueError, match="identity|guard|inactive"):
                descriptor = child.open_file(
                    "must-not-exist.bin",
                    create=True,
                    write=True,
                )
                os.close(descriptor)

            assert _complete_physical_tree(moved_path) == moved_before
            assert _complete_physical_tree(parent_path) == visible_before


def test_cleanup_parent_bootstrap_is_atomic_idempotent_and_identity_bound(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "HSConfig"
    state_root.mkdir()
    with package_io.hold_plain_directory(state_root) as state:
        first = package_io.bootstrap_plain_child_directory_under_guard(
            parent_guard=state,
            child_name="cleanup",
        )
        second = package_io.bootstrap_plain_child_directory_under_guard(
            parent_guard=state,
            child_name="cleanup",
        )
        assert first == second == package_io.path_identity(state_root / "cleanup")


def test_secure_unlink_verified_dispatches_all_authority_to_posix_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "bound.bin"
    expected_identity = (11, 12, 0o100600)
    expected_parent_identity = (21, 22, 0o40700)
    expected_size = 37
    expected_sha256 = "a" * 64
    delegated: list[
        tuple[Path, package_io.PathIdentity, package_io.PathIdentity, int, str]
    ] = []

    def fake_posix_verified_unlink(
        delegated_path: Path,
        *,
        expected_identity: package_io.PathIdentity,
        expected_parent_identity: package_io.PathIdentity,
        expected_size: int,
        expected_sha256: str,
    ) -> None:
        delegated.append(
            (
                delegated_path,
                expected_identity,
                expected_parent_identity,
                expected_size,
                expected_sha256,
            )
        )

    error: BaseException | None = None
    with monkeypatch.context() as platform_patch:
        platform_patch.setattr(
            package_io,
            "_secure_unlink_verified_posix",
            fake_posix_verified_unlink,
            raising=False,
        )
        platform_patch.setattr(package_io.os, "name", "posix")
        try:
            package_io.secure_unlink_verified(
                path,
                expected_identity=expected_identity,
                expected_parent_identity=expected_parent_identity,
                expected_size=expected_size,
                expected_sha256=expected_sha256,
            )
        except BaseException as caught:
            error = caught
    if error is not None:
        raise error

    assert delegated == [
        (
            path,
            expected_identity,
            expected_parent_identity,
            expected_size,
            expected_sha256,
        )
    ]


def test_secure_rmdir_verified_dispatches_all_authority_to_posix_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "bound-directory"
    expected_identity = (31, 32, 0o40700)
    expected_parent_identity = (41, 42, 0o40700)
    delegated: list[
        tuple[Path, package_io.PathIdentity, package_io.PathIdentity]
    ] = []

    def fake_posix_verified_rmdir(
        delegated_path: Path,
        *,
        expected_identity: package_io.PathIdentity,
        expected_parent_identity: package_io.PathIdentity,
    ) -> None:
        delegated.append(
            (
                delegated_path,
                expected_identity,
                expected_parent_identity,
            )
        )

    error: BaseException | None = None
    with monkeypatch.context() as platform_patch:
        platform_patch.setattr(
            package_io,
            "_secure_rmdir_verified_posix",
            fake_posix_verified_rmdir,
            raising=False,
        )
        platform_patch.setattr(package_io.os, "name", "posix")
        try:
            package_io.secure_rmdir_verified(
                path,
                expected_identity=expected_identity,
                expected_parent_identity=expected_parent_identity,
            )
        except BaseException as caught:
            error = caught
    if error is not None:
        raise error

    assert delegated == [
        (path, expected_identity, expected_parent_identity)
    ]


@pytest.mark.skipif(os.name != "nt", reason="Windows verified rmdir semantics")
def test_secure_rmdir_verified_deletes_exact_windows_directory(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    path = parent / "bound-directory"
    path.mkdir()
    expected_parent_identity = package_io.path_identity(parent)

    package_io.secure_rmdir_verified(
        path,
        expected_identity=package_io.path_identity(path),
        expected_parent_identity=expected_parent_identity,
    )

    assert not package_io.path_lexists(path)
    assert package_io.path_identity(parent) == expected_parent_identity


@pytest.mark.parametrize("operation", ("unlink", "rmdir"))
def test_posix_advisory_unlock_error_after_successful_delete_is_best_effort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    calls: list[int] = []
    lock_ex = 1
    lock_nb = 2
    lock_un = 4

    def fake_flock(_descriptor: int, mode: int) -> None:
        calls.append(mode)
        if mode == lock_un:
            raise OSError(errno.EIO, "advisory unlock failed after commit")

    fake_fcntl = SimpleNamespace(
        LOCK_EX=lock_ex,
        LOCK_NB=lock_nb,
        LOCK_UN=lock_un,
        flock=fake_flock,
    )
    monkeypatch.setitem(sys.modules, "fcntl", fake_fcntl)
    target = tmp_path / "committed-target"
    if operation == "unlink":
        target.write_bytes(b"committed-file")
    else:
        target.mkdir()

    with package_io._hold_posix_advisory_exclusive_lock(73):
        if operation == "unlink":
            target.unlink()
        else:
            target.rmdir()

    assert not package_io.path_lexists(target)
    assert calls == [lock_ex | lock_nb, lock_un]


@pytest.mark.skipif(os.name == "nt", reason="POSIX verified unlink semantics")
def test_posix_verified_unlink_exact_file_is_descriptor_relative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    path = parent / "bound.bin"
    payload = b"exact verified payload"
    path.write_bytes(payload)
    expected_identity = package_io.path_identity(path)
    expected_parent_identity = package_io.path_identity(parent)
    observed: list[tuple[str, package_io.PathIdentity]] = []
    real_unlink = os.unlink

    def observe_unlink(
        name: str,
        *,
        dir_fd: int | None = None,
    ) -> None:
        assert dir_fd is not None
        observed.append(
            (
                name,
                package_io.path_identity_from_status(os.fstat(dir_fd)),
            )
        )
        real_unlink(name, dir_fd=dir_fd)

    monkeypatch.setattr(package_io.os, "unlink", observe_unlink)

    package_io.secure_unlink_verified(
        path,
        expected_identity=expected_identity,
        expected_parent_identity=expected_parent_identity,
        expected_size=len(payload),
        expected_sha256=sha256(payload).hexdigest(),
    )

    assert observed == [(path.name, expected_parent_identity)]
    assert not path.exists()
    assert package_io.path_identity(parent) == expected_parent_identity


@pytest.mark.skipif(os.name == "nt", reason="POSIX verified unlink semantics")
@pytest.mark.parametrize(
    "mutated_raw",
    (b"dxact verified payload", b"different-size"),
    ids=("same-size-content", "changed-size"),
)
def test_posix_verified_unlink_preserves_same_identity_content_or_size_change(
    tmp_path: Path,
    mutated_raw: bytes,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    path = parent / "bound.bin"
    original_raw = b"exact verified payload"
    path.write_bytes(original_raw)
    expected_identity = package_io.path_identity(path)
    expected_parent_identity = package_io.path_identity(parent)

    with path.open("r+b") as stream:
        assert stream.write(mutated_raw) == len(mutated_raw)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())
    assert package_io.path_identity(path) == expected_identity

    with pytest.raises(
        ValueError,
        match="^filesystem_verified_unlink_content_changed$",
    ):
        package_io.secure_unlink_verified(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
            expected_size=len(original_raw),
            expected_sha256=sha256(original_raw).hexdigest(),
        )

    assert package_io.path_identity(path) == expected_identity
    assert path.read_bytes() == mutated_raw


@pytest.mark.skipif(os.name == "nt", reason="POSIX verified unlink semantics")
def test_posix_verified_unlink_preserves_mutation_after_digest_before_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    path = parent / "bound.bin"
    original_raw = b"exact verified payload"
    mutated_raw = bytes((original_raw[0] ^ 1,)) + original_raw[1:]
    path.write_bytes(original_raw)
    expected_identity = package_io.path_identity(path)
    expected_parent_identity = package_io.path_identity(parent)
    real_descriptor_sha256 = package_io._posix_descriptor_sha256
    mutated = False

    def mutate_after_digest(
        descriptor: int,
        *,
        expected_size: int,
    ) -> str:
        nonlocal mutated
        digest = real_descriptor_sha256(
            descriptor,
            expected_size=expected_size,
        )
        if not mutated:
            with path.open("r+b") as stream:
                assert stream.write(mutated_raw) == len(mutated_raw)
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            assert package_io.path_identity(path) == expected_identity
            mutated = True
        return digest

    monkeypatch.setattr(
        package_io,
        "_posix_descriptor_sha256",
        mutate_after_digest,
    )

    with pytest.raises(
        ValueError,
        match="^filesystem_verified_unlink_content_changed$",
    ):
        package_io.secure_unlink_verified(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
            expected_size=len(original_raw),
            expected_sha256=sha256(original_raw).hexdigest(),
        )

    assert mutated
    assert package_io.path_identity(path) == expected_identity
    assert path.read_bytes() == mutated_raw


@pytest.mark.skipif(os.name == "nt", reason="POSIX verified unlink semantics")
@pytest.mark.parametrize("entry_kind", ("hardlink", "symlink"))
def test_posix_verified_unlink_rejects_hardlink_or_symlink_without_following(
    tmp_path: Path,
    entry_kind: str,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    path = parent / "bound.bin"
    payload = b"must be preserved"
    companion = parent / "companion.bin"
    if entry_kind == "hardlink":
        path.write_bytes(payload)
        expected_identity = package_io.path_identity(path)
        expected_size = len(payload)
        expected_sha256 = sha256(payload).hexdigest()
        os.link(path, companion)
        assert path.stat().st_nlink == companion.stat().st_nlink == 2
    else:
        companion.write_bytes(payload)
        path.symlink_to(companion.name)
        expected_identity = package_io.path_identity(path)
        expected_size = path.lstat().st_size
        expected_sha256 = "0" * 64
        assert path.is_symlink()
    expected_parent_identity = package_io.path_identity(parent)

    with pytest.raises(
        ValueError,
        match="^filesystem_verified_unlink_content_changed$",
    ):
        package_io.secure_unlink_verified(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        )

    assert package_io.path_identity(path) == expected_identity
    if entry_kind == "hardlink":
        assert path.read_bytes() == companion.read_bytes() == payload
        assert path.stat().st_nlink == companion.stat().st_nlink == 2
    else:
        assert path.is_symlink()
        assert companion.read_bytes() == payload


@pytest.mark.skipif(os.name == "nt", reason="POSIX verified rmdir semantics")
def test_posix_verified_rmdir_exact_empty_directory_is_descriptor_relative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    path = parent / "bound-directory"
    path.mkdir()
    expected_identity = package_io.path_identity(path)
    expected_parent_identity = package_io.path_identity(parent)
    observed: list[tuple[str, package_io.PathIdentity]] = []
    real_rmdir = os.rmdir

    def observe_rmdir(
        name: str,
        *,
        dir_fd: int | None = None,
    ) -> None:
        assert dir_fd is not None
        observed.append(
            (
                name,
                package_io.path_identity_from_status(os.fstat(dir_fd)),
            )
        )
        real_rmdir(name, dir_fd=dir_fd)

    monkeypatch.setattr(package_io.os, "rmdir", observe_rmdir)

    package_io.secure_rmdir_verified(
        path,
        expected_identity=expected_identity,
        expected_parent_identity=expected_parent_identity,
    )

    assert observed == [(path.name, expected_parent_identity)]
    assert not path.exists()
    assert package_io.path_identity(parent) == expected_parent_identity


@pytest.mark.skipif(os.name == "nt", reason="POSIX verified rmdir semantics")
@pytest.mark.parametrize("mutation", ("nonempty", "substituted"))
def test_posix_verified_rmdir_preserves_nonempty_or_substituted_directory(
    tmp_path: Path,
    mutation: str,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    path = parent / "bound-directory"
    path.mkdir()
    expected_identity = package_io.path_identity(path)
    expected_parent_identity = package_io.path_identity(parent)
    retired = parent / "retired-directory"
    if mutation == "nonempty":
        foreign = path / "foreign.bin"
        foreign.write_bytes(b"foreign-directory-content")
    else:
        path.rename(retired)
        path.mkdir()
        foreign = path / "foreign.bin"
        foreign.write_bytes(b"foreign-substitute")
        assert package_io.path_identity(retired) == expected_identity
        assert package_io.path_identity(path) != expected_identity

    with pytest.raises(
        ValueError,
        match="^filesystem_verified_rmdir_content_changed$",
    ):
        package_io.secure_rmdir_verified(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
        )

    assert foreign.is_file()
    if mutation == "nonempty":
        assert package_io.path_identity(path) == expected_identity
        assert foreign.read_bytes() == b"foreign-directory-content"
    else:
        assert package_io.path_identity(retired) == expected_identity
        assert package_io.path_identity(path) != expected_identity
        assert foreign.read_bytes() == b"foreign-substitute"


@pytest.mark.skipif(os.name == "nt", reason="POSIX verified rmdir semantics")
def test_posix_verified_rmdir_preserves_transient_entry_metadata_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    path = parent / "bound-directory"
    path.mkdir()
    expected_identity = package_io.path_identity(path)
    expected_parent_identity = package_io.path_identity(parent)
    opened = path.stat()
    real_listdir = os.listdir
    mutated = False

    def mutate_after_first_empty_observation(
        descriptor: int,
    ) -> list[str]:
        nonlocal mutated
        entries = real_listdir(descriptor)
        if not mutated:
            assert entries == []
            transient = path / "transient.bin"
            transient.write_bytes(b"transient")
            transient.unlink()
            os.utime(
                path,
                ns=(opened.st_atime_ns, opened.st_mtime_ns + 1_000_000_000),
                follow_symlinks=False,
            )
            assert package_io.path_identity(path) == expected_identity
            assert real_listdir(descriptor) == []
            mutated = True
        return entries

    monkeypatch.setattr(
        package_io.os,
        "listdir",
        mutate_after_first_empty_observation,
    )

    with pytest.raises(
        ValueError,
        match="^filesystem_verified_rmdir_content_changed$",
    ):
        package_io.secure_rmdir_verified(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
        )

    assert mutated
    assert package_io.path_identity(path) == expected_identity
    assert path.is_dir()
    assert real_listdir(path) == []
