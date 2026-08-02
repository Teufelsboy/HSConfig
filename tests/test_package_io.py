from __future__ import annotations

import json
import os
from pathlib import Path
import stat

import pytest

from hsconfig import package_io


def _one_file_tree(tmp_path: Path) -> Path:
    root = tmp_path / "package"
    root.mkdir()
    (root / "payload.json").write_text('{"ok":true}', encoding="utf-8")
    return root


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
