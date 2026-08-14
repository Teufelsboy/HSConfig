from pathlib import Path

import pytest

import hsconfig.configure_stage_snapshot as snapshot
from hsconfig.configure_stage_snapshot import (
    collect_configure_stage_artifacts,
)


def test_stage_artifacts_exclude_unowned_output_root_content(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "configure"
    (output_root / "01_manifest").mkdir(parents=True)
    (output_root / "01_manifest" / "manifest.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (output_root / "rogue.json").write_text("rogue", encoding="utf-8")
    (output_root / "unknown" / "nested").mkdir(parents=True)
    (output_root / "unknown" / "nested" / "foreign.json").write_text(
        "foreign",
        encoding="utf-8",
    )
    (output_root / "configure_summary.json").write_text(
        '{"status":"OK"}',
        encoding="utf-8",
    )

    artifacts = collect_configure_stage_artifacts(output_root)

    assert artifacts == {
        "01_manifest/manifest.json": b"{}",
        "02_source_documents/stage_status.json": (
            b'{"reason":"not_requested","status":"unavailable"}\n'
        ),
        "configure_summary.json": b'{"status":"OK"}',
    }


def test_stage_artifacts_reject_owned_file_symlink_without_reading_target(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "configure"
    manifest_root = output_root / "01_manifest"
    manifest_root.mkdir(parents=True)
    external = tmp_path / "external-secret.json"
    external.write_text('{"secret":true}', encoding="utf-8")
    linked = manifest_root / "linked.json"
    try:
        linked.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"file symlink unavailable: {exc}")

    with pytest.raises(ValueError, match="configure_stage_node_unsafe"):
        collect_configure_stage_artifacts(output_root)


def test_stage_artifacts_reject_output_root_reparse_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root, _manifest = _stage_snapshot_fixture(tmp_path)
    real_lstat = snapshot._stage_lstat
    root = output_root.absolute()

    def reparse_root(path: Path):
        result = real_lstat(path)
        if path == root:
            return _StatOverlay(result, reparse=True)
        return result

    monkeypatch.setattr(snapshot, "_stage_lstat", reparse_root)

    with pytest.raises(ValueError, match="configure_stage_root_unsafe"):
        collect_configure_stage_artifacts(output_root)


def test_stage_artifacts_reject_persistent_ancestor_reparse_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root, _manifest = _stage_snapshot_fixture(tmp_path)
    real_lstat = snapshot._stage_lstat
    ancestor = output_root.absolute().parent

    def reparse_ancestor(path: Path):
        result = real_lstat(path)
        if path == ancestor:
            return _StatOverlay(result, reparse=True)
        return result

    monkeypatch.setattr(snapshot, "_stage_lstat", reparse_ancestor)

    with pytest.raises(ValueError, match="configure_stage_root_unsafe"):
        collect_configure_stage_artifacts(output_root)


def test_stage_artifacts_reject_file_swap_before_open_without_reading(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root, manifest = _stage_snapshot_fixture(tmp_path)
    real_open = snapshot._stage_open
    read_called = False

    def swap_before_open(path: Path, flags: int) -> int:
        if path == manifest:
            original = path.with_suffix(".original")
            path.replace(original)
            path.write_bytes(b"replacement")
        return real_open(path, flags)

    def reject_read(_descriptor: int, _size: int) -> bytes:
        nonlocal read_called
        read_called = True
        raise AssertionError("swapped file must fail before read")

    monkeypatch.setattr(snapshot, "_stage_open", swap_before_open)
    monkeypatch.setattr(snapshot, "_stage_read", reject_read)

    with pytest.raises(ValueError, match="configure_stage_file_changed"):
        collect_configure_stage_artifacts(output_root)
    assert read_called is False


@pytest.mark.parametrize("swap_timing", ["before_scan", "after_scan"])
def test_stage_artifacts_reject_directory_identity_swap_around_scan(
    tmp_path: Path,
    monkeypatch,
    swap_timing: str,
) -> None:
    output_root, _manifest = _stage_snapshot_fixture(tmp_path)
    manifest_root = output_root / "01_manifest"
    real_scan = snapshot._stage_scandir_rows
    swapped = False

    def swap_directory(path: Path):
        nonlocal swapped
        if path != manifest_root or swapped:
            return real_scan(path)
        swapped = True
        if swap_timing == "before_scan":
            manifest_root.rename(output_root / "original-manifest")
            manifest_root.mkdir()
            return real_scan(path)
        rows = real_scan(path)
        manifest_root.rename(output_root / "original-manifest")
        manifest_root.mkdir()
        return rows

    monkeypatch.setattr(snapshot, "_stage_scandir_rows", swap_directory)

    with pytest.raises(
        ValueError,
        match="configure_stage_directory_changed",
    ):
        collect_configure_stage_artifacts(output_root)


@pytest.mark.parametrize("mutation", ["torn_read", "concurrent_write"])
def test_stage_artifacts_reject_torn_or_concurrently_mutated_file(
    tmp_path: Path,
    monkeypatch,
    mutation: str,
) -> None:
    output_root, manifest = _stage_snapshot_fixture(tmp_path)
    real_read = snapshot._stage_read
    calls = 0

    def mutate_during_read(descriptor: int, size: int) -> bytes:
        nonlocal calls
        calls += 1
        if calls == 1:
            chunk = real_read(descriptor, 1)
            if mutation == "concurrent_write":
                manifest.write_bytes(b"changed-content")
            return chunk
        if mutation == "torn_read":
            return b""
        return real_read(descriptor, size)

    monkeypatch.setattr(snapshot, "_stage_read", mutate_during_read)

    with pytest.raises(ValueError, match="configure_stage_file_changed"):
        collect_configure_stage_artifacts(output_root)


@pytest.mark.parametrize(
    (
        "platform_name",
        "path_ctime_ns",
        "handle_ctime_ns",
        "path_birthtime_ns",
        "handle_birthtime_ns",
        "expected_match",
    ),
    [
        pytest.param(
            "nt", 10, 20, 30, 30, True, id="windows_matching_birthtime"
        ),
        pytest.param(
            "nt",
            10,
            20,
            None,
            None,
            False,
            id="windows_missing_birthtime_uses_ctime",
        ),
        pytest.param(
            "posix", 10, 20, 30, 30, False, id="posix_uses_ctime"
        ),
        pytest.param(
            "nt", 10, 10, 30, 40, False, id="windows_birthtime_mismatch"
        ),
    ],
)
def test_stage_file_time_token_uses_platform_specific_timestamp(
    platform_name: str,
    path_ctime_ns: int,
    handle_ctime_ns: int,
    path_birthtime_ns: int | None,
    handle_birthtime_ns: int | None,
    expected_match: bool,
) -> None:
    path_stat = _TimestampOverlay(
        ctime_ns=path_ctime_ns,
        birthtime_ns=path_birthtime_ns,
    )
    handle_stat = _TimestampOverlay(
        ctime_ns=handle_ctime_ns,
        birthtime_ns=handle_birthtime_ns,
    )

    path_token = snapshot._stage_file_time_token(
        path_stat,
        platform_name=platform_name,
    )
    handle_token = snapshot._stage_file_time_token(
        handle_stat,
        platform_name=platform_name,
    )

    assert (path_token == handle_token) is expected_match


def _stage_snapshot_fixture(tmp_path: Path) -> tuple[Path, Path]:
    output_root = tmp_path / "configure"
    manifest_root = output_root / "01_manifest"
    manifest_root.mkdir(parents=True)
    manifest = manifest_root / "manifest.json"
    manifest.write_bytes(b"manifest-content")
    (output_root / "configure_summary.json").write_bytes(
        b'{"status":"OK"}'
    )
    return output_root, manifest


class _StatOverlay:
    def __init__(self, base, *, reparse: bool) -> None:
        self._base = base
        self.st_file_attributes = (
            getattr(base, "st_file_attributes", 0)
            | (0x400 if reparse else 0)
        )

    def __getattr__(self, name: str):
        return getattr(self._base, name)


class _TimestampOverlay:
    def __init__(
        self,
        *,
        ctime_ns: int,
        birthtime_ns: int | None,
    ) -> None:
        self.st_ctime_ns = ctime_ns
        if birthtime_ns is not None:
            self.st_birthtime_ns = birthtime_ns

    def __getattr__(self, name: str):
        raise AttributeError(name)
