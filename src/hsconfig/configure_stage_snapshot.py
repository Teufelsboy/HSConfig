"""Identity-bound collection of configure-owned stage artifacts."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import NamedTuple

__all__ = ("collect_configure_stage_artifacts",)

_CONFIGURE_STAGE_ROOTS = (
    "01_manifest",
    "02_source_documents",
    "02_source_acquisition",
    "02_source_autopilot",
    "03_source_autopilot",
    "03_research",
)


class _StageScanRow(NamedTuple):
    name: str
    path: Path
    discovered_stat: os.stat_result


class _StageFileRecord(NamedTuple):
    path: Path
    relative_path: str
    discovered_stat: os.stat_result
    directory_chain: tuple[tuple[Path, tuple[int, int]], ...]


def collect_configure_stage_artifacts(
    output_root: Path,
) -> dict[str, bytes]:
    root = Path(os.path.abspath(output_root))
    root_chain = _capture_stage_root_chain(root)
    directory_bindings: dict[Path, tuple[int, int]] = {
        root: root_chain[-1][1]
    }
    discovered_files: list[_StageFileRecord] = []
    for root_name in _CONFIGURE_STAGE_ROOTS:
        stage_root = root / root_name
        if os.path.lexists(stage_root):
            _discover_owned_stage_tree(
                root,
                stage_root,
                root_chain=root_chain,
                directory_bindings=directory_bindings,
                discovered_files=discovered_files,
            )
    summary_path = root / "configure_summary.json"
    if not os.path.lexists(summary_path):
        raise ValueError("configure_stage_summary_missing")
    _require_stage_root_chain(root_chain)
    summary_stat = _stage_lstat(summary_path)
    _require_discovered_regular_file(summary_path, summary_stat)
    _require_stage_root_chain(root_chain)
    discovered_files.append(
        _StageFileRecord(
            path=summary_path,
            relative_path="configure_summary.json",
            discovered_stat=summary_stat,
            directory_chain=(),
        )
    )
    _require_stage_root_chain(root_chain)
    for path, identity in directory_bindings.items():
        if path != root:
            _require_stage_directory_identity(path, identity)
    artifacts = {
        record.relative_path: _read_discovered_stage_file(
            record,
            root_chain=root_chain,
        )
        for record in sorted(
            discovered_files,
            key=lambda value: value.relative_path,
        )
    }
    if not any(
        path.startswith(
            ("02_source_documents/", "02_source_acquisition/")
        )
        for path in artifacts
    ):
        artifacts["02_source_documents/stage_status.json"] = (
            b'{"reason":"not_requested","status":"unavailable"}\n'
        )
    folded = [path.casefold() for path in artifacts]
    if len(folded) != len(set(folded)):
        raise ValueError("configure_stage_path_casefold_collision")
    return dict(sorted(artifacts.items()))


def _capture_stage_root_chain(
    output_root: Path,
) -> tuple[tuple[Path, tuple[int, int]], ...]:
    chain: list[tuple[Path, tuple[int, int]]] = []
    for path in (*reversed(output_root.parents), output_root):
        try:
            node_stat = _stage_lstat(path)
        except OSError as exc:
            raise ValueError("configure_stage_root_unsafe") from exc
        if (
            not stat.S_ISDIR(node_stat.st_mode)
            or _stage_stat_is_reparse(node_stat)
        ):
            raise ValueError("configure_stage_root_unsafe")
        chain.append((path, _stage_identity(node_stat)))
    return tuple(chain)


def _require_stage_root_chain(
    chain: tuple[tuple[Path, tuple[int, int]], ...],
) -> None:
    for path, expected in chain:
        try:
            current = _stage_lstat(path)
        except OSError as exc:
            raise ValueError("configure_stage_root_changed") from exc
        if (
            not stat.S_ISDIR(current.st_mode)
            or _stage_stat_is_reparse(current)
            or _stage_identity(current) != expected
        ):
            raise ValueError("configure_stage_root_changed")


def _discover_owned_stage_tree(
    output_root: Path,
    stage_root: Path,
    *,
    root_chain: tuple[tuple[Path, tuple[int, int]], ...],
    directory_bindings: dict[Path, tuple[int, int]],
    discovered_files: list[_StageFileRecord],
) -> None:
    _require_stage_root_chain(root_chain)
    root_stat = _stage_lstat(stage_root)
    if _stage_stat_is_reparse(root_stat):
        raise ValueError("configure_stage_node_unsafe")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError("configure_stage_root_not_directory")
    root_identity = _stage_identity(root_stat)
    directory_bindings[stage_root] = root_identity
    pending = [(stage_root, ((stage_root, root_identity),))]
    while pending:
        directory, directory_chain = pending.pop()
        _require_stage_snapshot_context(root_chain, directory_chain)
        rows = _stage_scandir_rows(directory)
        _require_stage_snapshot_context(root_chain, directory_chain)
        for row in rows:
            expected_path = directory / row.name
            if (
                row.path != expected_path
                or not row.path.is_relative_to(output_root)
            ):
                raise ValueError("configure_stage_path_drift")
            node_stat = row.discovered_stat
            if _stage_stat_is_reparse(node_stat):
                raise ValueError("configure_stage_node_unsafe")
            if stat.S_ISDIR(node_stat.st_mode):
                identity = _stage_identity(node_stat)
                if row.path in directory_bindings:
                    raise ValueError("configure_stage_path_duplicate")
                directory_bindings[row.path] = identity
                pending.append(
                    (
                        row.path,
                        (*directory_chain, (row.path, identity)),
                    )
                )
            elif stat.S_ISREG(node_stat.st_mode):
                relative = row.path.relative_to(output_root).as_posix()
                if any(
                    record.relative_path == relative
                    for record in discovered_files
                ):
                    raise ValueError("configure_stage_path_duplicate")
                discovered_files.append(
                    _StageFileRecord(
                        path=row.path,
                        relative_path=relative,
                        discovered_stat=node_stat,
                        directory_chain=directory_chain,
                    )
                )
            else:
                raise ValueError("configure_stage_node_unsafe")


def _stage_scandir_rows(directory: Path) -> tuple[_StageScanRow, ...]:
    with os.scandir(directory) as entries:
        rows = tuple(
            _StageScanRow(
                name=entry.name,
                path=Path(entry.path),
                discovered_stat=_stage_lstat(Path(entry.path)),
            )
            for entry in entries
        )
    return tuple(sorted(rows, key=lambda row: row.name))


def _read_discovered_stage_file(
    record: _StageFileRecord,
    *,
    root_chain: tuple[tuple[Path, tuple[int, int]], ...],
) -> bytes:
    _require_stage_snapshot_context(root_chain, record.directory_chain)
    before = _stage_lstat(record.path)
    if not _same_stage_file_snapshot(before, record.discovered_stat):
        raise ValueError("configure_stage_file_changed")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = _stage_open(record.path, flags)
    try:
        opened = _stage_fstat(descriptor)
        if not _same_stage_file_snapshot(opened, record.discovered_stat):
            raise ValueError("configure_stage_file_changed")
        chunks: list[bytes] = []
        while chunk := _stage_read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        content = b"".join(chunks)
        after_handle = _stage_fstat(descriptor)
        after_path = _stage_lstat(record.path)
        _require_stage_snapshot_context(
            root_chain,
            record.directory_chain,
        )
        if (
            not _same_stage_file_snapshot(
                after_handle,
                record.discovered_stat,
            )
            or not _same_stage_file_snapshot(
                after_path,
                record.discovered_stat,
            )
            or len(content) != int(record.discovered_stat.st_size)
        ):
            raise ValueError("configure_stage_file_changed")
        return content
    finally:
        os.close(descriptor)


def _require_stage_snapshot_context(
    root_chain: tuple[tuple[Path, tuple[int, int]], ...],
    directory_chain: tuple[tuple[Path, tuple[int, int]], ...],
) -> None:
    _require_stage_root_chain(root_chain)
    for path, identity in directory_chain:
        _require_stage_directory_identity(path, identity)


def _require_stage_directory_identity(
    path: Path,
    expected: tuple[int, int],
) -> None:
    try:
        current = _stage_lstat(path)
    except OSError as exc:
        raise ValueError("configure_stage_directory_changed") from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or _stage_stat_is_reparse(current)
        or _stage_identity(current) != expected
    ):
        raise ValueError("configure_stage_directory_changed")


def _require_discovered_regular_file(
    path: Path,
    node_stat: os.stat_result,
) -> None:
    if (
        not stat.S_ISREG(node_stat.st_mode)
        or _stage_stat_is_reparse(node_stat)
    ):
        raise ValueError(f"configure_stage_node_unsafe:{path.name}")


def _same_stage_file_snapshot(
    actual: os.stat_result,
    expected: os.stat_result,
) -> bool:
    return (
        stat.S_ISREG(actual.st_mode)
        and not _stage_stat_is_reparse(actual)
        and _stage_file_signature(actual) == _stage_file_signature(expected)
    )


def _stage_file_signature(
    node_stat: os.stat_result,
) -> tuple[int, int, int, int, int]:
    return (
        *_stage_identity(node_stat),
        int(node_stat.st_size),
        int(node_stat.st_mtime_ns),
        int(node_stat.st_ctime_ns),
    )


def _stage_identity(node_stat: os.stat_result) -> tuple[int, int]:
    return (int(node_stat.st_dev), int(node_stat.st_ino))


def _stage_stat_is_reparse(node_stat: os.stat_result) -> bool:
    return bool(
        stat.S_ISLNK(node_stat.st_mode)
        or getattr(node_stat, "st_file_attributes", 0) & 0x400
    )


def _stage_lstat(path: Path) -> os.stat_result:
    return path.lstat()


def _stage_open(path: Path, flags: int) -> int:
    return os.open(path, flags)


def _stage_fstat(descriptor: int) -> os.stat_result:
    return os.fstat(descriptor)


def _stage_read(descriptor: int, size: int) -> bytes:
    return os.read(descriptor, size)
