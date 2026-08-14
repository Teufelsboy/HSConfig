from __future__ import annotations

import hashlib
import ctypes
import errno
import os
import stat
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

import hsconfig.deck_config_ini as deck_config_ini
from hsconfig.deck_config_ini import (
    read_deck_config,
    render_deck_config,
    replace_deck_config_if_unchanged,
)
from hsconfig.package_io import hold_plain_directory, path_identity_from_status


FAULT_STAGES = (
    "before_temp_write",
    "after_temp_write",
    "after_temp_flush",
    "before_replace",
    "after_replace",
    "after_parent_flush",
)
PRE_COMMIT_STAGES = frozenset(FAULT_STAGES[:4])


class InjectedFault(RuntimeError):
    pass


class InjectedBaseFault(BaseException):
    pass


def _fault_at(
    target: str,
    exception_type: type[BaseException] = InjectedFault,
) -> Callable[[str], None]:
    def inject(stage: str) -> None:
        if stage == target:
            raise exception_type(stage)

    return inject


def _temp_residue(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f".{path.name}.*.tmp"))


def _make_junction(link: Path, target: Path) -> None:
    if os.name != "nt":
        pytest.skip("Windows junction coverage")
    completed = subprocess.run(
        [
            "cmd.exe",
            "/d",
            "/c",
            "mklink",
            "/J",
            str(link),
            str(target),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip(f"directory junctions unavailable: {completed.stderr}")


class _StatusWithLinkCount:
    def __init__(self, status: os.stat_result, count: int) -> None:
        self._status = status
        self.st_nlink = count

    def __getattr__(self, name: str) -> object:
        return getattr(self._status, name)


def test_read_deck_config_represents_first_install_without_placeholder(
    tmp_path: Path,
) -> None:
    path = tmp_path / "CustomConfig" / "deck_config.ini"
    path.parent.mkdir()

    snapshot = read_deck_config(path, deck_name="Shadow Priest")

    assert snapshot.path == path
    assert snapshot.existed is False
    assert snapshot.content is None
    assert snapshot.sha256 is None
    assert snapshot.selected_config_dir is None
    assert not path.exists()


def test_read_deck_config_matches_only_configs_case_insensitively_and_keeps_inline_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    raw = (
        b"\xef\xbb\xbf[Other]\r\nshadow priest = ignored\r\n"
        b"[cOnFiGs]\r\n  SHADOW PRIEST =  Config Name ; inline text\r\n"
    )
    path.write_bytes(raw)

    snapshot = read_deck_config(path, deck_name="shadow priest")

    assert snapshot.content == raw
    assert snapshot.sha256 == hashlib.sha256(raw).hexdigest()
    assert snapshot.selected_config_dir == "Config Name ; inline text"


def test_read_deck_config_rejects_ambiguous_casefolded_mappings(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    path.write_text(
        "[CONFIGS]\nDeck = One\ndEcK=Two\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="^deck_config_ini_ambiguous_mapping$"):
        read_deck_config(path, deck_name="DECK")


def test_render_deck_config_preserves_bom_mixed_newlines_unicode_and_untouched_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    old = (
        b"\xef\xbb\xbf; Gr\xc3\xbc\xc3\x9fe\r\n"
        b"[CONFIGS]\n"
        b"  ShAdOw PrIeSt\t=   Old Config  \r\n"
        b"Other = Unchanged\n"
        b"[Unicode]\rvalue = \xe2\x98\x83"
    )
    path.write_bytes(old)
    snapshot = read_deck_config(path, deck_name="shadow priest")

    rendered = render_deck_config(
        snapshot,
        deck_name="SHADOW PRIEST",
        config_dir="Shadow--sha256-" + "a" * 64,
    )

    expected = old.replace(
        b"  ShAdOw PrIeSt\t=   Old Config  \r\n",
        b"  ShAdOw PrIeSt\t=   Shadow--sha256-" + b"a" * 64 + b"  \r\n",
    )
    assert rendered == expected
    assert rendered.startswith(b"\xef\xbb\xbf")
    assert not rendered.endswith((b"\n", b"\r"))


def test_render_deck_config_inserts_into_configs_with_first_newline_convention(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    old = b"; header\r\n[CONFIGS]\nOther=One\n[Else]\rvalue=two\r"
    path.write_bytes(old)
    snapshot = read_deck_config(path, deck_name="New Deck")

    rendered = render_deck_config(
        snapshot,
        deck_name="New Deck",
        config_dir="NewConfig",
    )

    assert rendered == (
        b"; header\r\n[CONFIGS]\nOther=One\n"
        b"New Deck = NewConfig\r\n[Else]\rvalue=two\r"
    )


@pytest.mark.parametrize(
    ("old", "expected"),
    [
        (
            b"[Other]\r\nvalue=one\r\n",
            b"[Other]\r\nvalue=one\r\n[CONFIGS]\r\nDeck = Config\r\n",
        ),
        (
            b"[Other]\nvalue=one",
            b"[Other]\nvalue=one\n[CONFIGS]\nDeck = Config",
        ),
        (b"", b"[CONFIGS]\nDeck = Config"),
    ],
)
def test_render_deck_config_appends_configs_and_preserves_final_newline_state(
    tmp_path: Path,
    old: bytes,
    expected: bytes,
) -> None:
    path = tmp_path / "deck_config.ini"
    path.write_bytes(old)
    snapshot = read_deck_config(path, deck_name="Deck")

    assert (
        render_deck_config(snapshot, deck_name="Deck", config_dir="Config")
        == expected
    )


def test_render_deck_config_for_missing_file_is_complete_and_has_no_side_effect(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name="Deck")

    rendered = render_deck_config(
        snapshot,
        deck_name="Deck",
        config_dir="Config",
    )

    assert rendered == b"[CONFIGS]\nDeck = Config"
    assert not path.exists()


def test_render_same_mapping_is_a_byte_exact_noop(tmp_path: Path) -> None:
    path = tmp_path / "deck_config.ini"
    raw = b"\xef\xbb\xbf[CONFIGS]\r\n  Deck = Same  \r\n"
    path.write_bytes(raw)
    snapshot = read_deck_config(path, deck_name="Deck")

    assert (
        render_deck_config(snapshot, deck_name="deck", config_dir="Same")
        == raw
    )


@pytest.mark.parametrize(
    "value",
    ["", " Deck", "Deck ", "A=B", "A\nB", ";Deck", "#Deck"],
)
def test_deck_name_validation_fails_closed(tmp_path: Path, value: str) -> None:
    path = tmp_path / "deck_config.ini"
    with pytest.raises(ValueError, match="^deck_config_ini_unsafe_deck_name$"):
        read_deck_config(path, deck_name=value)


@pytest.mark.parametrize("deck_name", ["Deck", "Däck #1", "Semi;Inside"])
def test_every_accepted_deck_name_survives_render_write_and_reread(
    tmp_path: Path,
    deck_name: str,
) -> None:
    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name=deck_name)
    rendered = render_deck_config(
        snapshot,
        deck_name=deck_name,
        config_dir="Config",
    )

    replace_deck_config_if_unchanged(snapshot, rendered)

    assert (
        read_deck_config(path, deck_name=deck_name).selected_config_dir
        == "Config"
    )


@pytest.mark.parametrize(
    "value",
    ["", " Config", "Config ", ".", "..", "../Config", "A/B", "A\\B", "CON"],
)
def test_config_directory_validation_fails_closed(
    tmp_path: Path,
    value: str,
) -> None:
    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name="Deck")

    with pytest.raises(ValueError, match="^deck_config_ini_unsafe_config_dir$"):
        render_deck_config(snapshot, deck_name="Deck", config_dir=value)


def test_read_deck_config_rejects_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "deck_config.ini"
    path.write_bytes(b"[CONFIGS]\nDeck=\xff")

    with pytest.raises(ValueError, match="^deck_config_ini_invalid_encoding$"):
        read_deck_config(path, deck_name="Deck")


def test_read_deck_config_rejects_oversized_input(tmp_path: Path) -> None:
    path = tmp_path / "deck_config.ini"
    path.write_bytes(b"x" * (1024 * 1024 + 1))

    with pytest.raises(ValueError, match="^deck_config_ini_too_large$"):
        read_deck_config(path, deck_name="Deck")


def test_create_if_absent_rejects_oversized_content_before_publication(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name="Deck")
    oversized = b"x" * (1024 * 1024 + 1)

    with pytest.raises(ValueError, match="^deck_config_ini_too_large$"):
        replace_deck_config_if_unchanged(snapshot, oversized)

    assert not path.exists()
    assert _temp_residue(path) == []


def test_read_deck_config_rejects_link_count_change_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "deck_config.ini"
    path.write_bytes(b"[CONFIGS]\nDeck = Config")
    real_fstat = os.fstat
    regular_calls = 0

    def mutate_final_regular_status(descriptor: int) -> os.stat_result:
        nonlocal regular_calls
        status = real_fstat(descriptor)
        if stat.S_ISREG(status.st_mode):
            regular_calls += 1
            if regular_calls >= 3:
                return _StatusWithLinkCount(status, 2)  # type: ignore[return-value]
        return status

    monkeypatch.setattr(deck_config_ini.os, "fstat", mutate_final_regular_status)

    with pytest.raises(ValueError, match="^deck_config_ini_unsafe_path$"):
        read_deck_config(path, deck_name="Deck")


@pytest.mark.skipif(os.name != "nt", reason="NTFS junction coverage")
@pytest.mark.parametrize("position", ["direct", "parent", "ancestor"])
def test_read_deck_config_rejects_ntfs_junctions_at_every_path_level(
    tmp_path: Path,
    position: str,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    junction: Path
    if position == "direct":
        actual = external / "target-directory"
        actual.mkdir()
        path = tmp_path / "deck_config.ini"
        junction = path
        _make_junction(junction, actual)
    elif position == "parent":
        actual = external / "CustomConfig"
        actual.mkdir()
        (actual / "deck_config.ini").write_bytes(
            b"[CONFIGS]\nDeck = Config"
        )
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        junction = runtime / "CustomConfig"
        _make_junction(junction, actual)
        path = junction / "deck_config.ini"
    else:
        actual = external / "root"
        path_under_actual = actual / "runtime" / "CustomConfig"
        path_under_actual.mkdir(parents=True)
        (path_under_actual / "deck_config.ini").write_bytes(
            b"[CONFIGS]\nDeck = Config"
        )
        junction = tmp_path / "alias"
        _make_junction(junction, actual)
        path = junction / "runtime" / "CustomConfig" / "deck_config.ini"
    try:
        with pytest.raises(ValueError, match="^deck_config_ini_unsafe_path$"):
            read_deck_config(path, deck_name="Deck")
    finally:
        junction.rmdir()


def test_read_deck_config_rejects_hardlinked_file(tmp_path: Path) -> None:
    source = tmp_path / "source.ini"
    source.write_text("[CONFIGS]\nDeck=One", encoding="utf-8")
    path = tmp_path / "deck_config.ini"
    try:
        os.link(source, path)
    except OSError as exc:
        pytest.skip(f"hardlinks unavailable: {exc}")

    with pytest.raises(ValueError, match="^deck_config_ini_unsafe_path$"):
        read_deck_config(path, deck_name="Deck")


def test_existing_file_cas_rejects_concurrent_edit_without_overwrite(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    path.write_bytes(b"[CONFIGS]\nDeck = Old")
    snapshot = read_deck_config(path, deck_name="Deck")
    rendered = render_deck_config(
        snapshot,
        deck_name="Deck",
        config_dir="New",
    )
    concurrent = b"[CONFIGS]\nDeck = Concurrent"
    path.write_bytes(concurrent)

    with pytest.raises(RuntimeError, match="^deck_config_ini_concurrent_change$"):
        replace_deck_config_if_unchanged(snapshot, rendered)

    assert path.read_bytes() == concurrent
    assert _temp_residue(path) == []


def test_existing_file_cas_rechecks_snapshot_immediately_before_replace(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    old = b"[CONFIGS]\nDeck = Old"
    path.write_bytes(old)
    snapshot = read_deck_config(path, deck_name="Deck")
    rendered = render_deck_config(
        snapshot,
        deck_name="Deck",
        config_dir="New",
    )
    concurrent = b"[CONFIGS]\nDeck = Concurrent"

    def edit_after_temp_flush(stage: str) -> None:
        if stage == "after_temp_flush":
            path.write_bytes(concurrent)

    with pytest.raises(RuntimeError, match="^deck_config_ini_concurrent_change$"):
        replace_deck_config_if_unchanged(
            snapshot,
            rendered,
            fault_hook=edit_after_temp_flush,
        )

    assert path.read_bytes() == concurrent
    assert _temp_residue(path) == []


def test_same_content_cas_revalidates_without_rewriting(tmp_path: Path) -> None:
    path = tmp_path / "deck_config.ini"
    raw = b"[CONFIGS]\nDeck = Current"
    path.write_bytes(raw)
    snapshot = read_deck_config(path, deck_name="Deck")
    before = path.stat()

    digest = replace_deck_config_if_unchanged(snapshot, raw)

    after = path.stat()
    assert digest == hashlib.sha256(raw).hexdigest()
    assert (after.st_dev, after.st_ino, after.st_mtime_ns) == (
        before.st_dev,
        before.st_ino,
        before.st_mtime_ns,
    )


@pytest.mark.parametrize("exception_type", [InjectedFault, InjectedBaseFault])
@pytest.mark.parametrize("fault_stage", FAULT_STAGES)
def test_existing_file_cas_faults_leave_one_complete_version_and_no_temp(
    tmp_path: Path,
    fault_stage: str,
    exception_type: type[BaseException],
) -> None:
    path = tmp_path / "deck_config.ini"
    old = b"[CONFIGS]\nDeck = Old"
    path.write_bytes(old)
    snapshot = read_deck_config(path, deck_name="Deck")
    new = render_deck_config(snapshot, deck_name="Deck", config_dir="New")

    with pytest.raises(exception_type, match=fault_stage):
        replace_deck_config_if_unchanged(
            snapshot,
            new,
            fault_hook=_fault_at(fault_stage, exception_type),
        )

    assert path.read_bytes() == (old if fault_stage in PRE_COMMIT_STAGES else new)
    assert _temp_residue(path) == []


@pytest.mark.parametrize("exception_type", [InjectedFault, InjectedBaseFault])
@pytest.mark.parametrize("fault_stage", FAULT_STAGES)
def test_create_if_absent_faults_never_expose_partial_bytes_or_temp_residue(
    tmp_path: Path,
    fault_stage: str,
    exception_type: type[BaseException],
) -> None:
    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name="Deck")
    new = render_deck_config(snapshot, deck_name="Deck", config_dir="New")

    with pytest.raises(exception_type, match=fault_stage):
        replace_deck_config_if_unchanged(
            snapshot,
            new,
            fault_hook=_fault_at(fault_stage, exception_type),
        )

    if fault_stage in PRE_COMMIT_STAGES:
        assert not path.exists()
    else:
        assert path.read_bytes() == new
    assert _temp_residue(path) == []


def test_create_if_absent_rejects_target_that_appears_before_commit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name="Deck")
    new = render_deck_config(snapshot, deck_name="Deck", config_dir="New")
    concurrent = b"[CONFIGS]\nDeck = Concurrent"

    def create_concurrent(stage: str) -> None:
        if stage == "before_replace":
            path.write_bytes(concurrent)

    with pytest.raises(RuntimeError, match="^deck_config_ini_concurrent_change$"):
        replace_deck_config_if_unchanged(
            snapshot,
            new,
            fault_hook=create_concurrent,
        )

    assert path.read_bytes() == concurrent
    assert _temp_residue(path) == []


def test_posix_mode_rejects_substituted_owned_temp_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name="Deck")
    new = render_deck_config(snapshot, deck_name="Deck", config_dir="New")
    attacker = b"[CONFIGS]\nDeck = ATTACKER"
    rename_calls: list[tuple[int, str, str]] = []
    monkeypatch.setattr(deck_config_ini, "_PLATFORM_NAME", "posix", raising=False)
    monkeypatch.setattr(
        deck_config_ini,
        "_rename_noreplace_posix",
        lambda descriptor, source, target: rename_calls.append(
            (descriptor, source, target)
        ),
        raising=False,
    )

    def substitute_temp(stage: str) -> None:
        if stage != "before_replace":
            return
        [temp] = _temp_residue(path)
        temp.unlink()
        temp.write_bytes(attacker)

    with pytest.raises(
        RuntimeError,
        match="^deck_config_ini_temp_identity_changed$",
    ):
        replace_deck_config_if_unchanged(
            snapshot,
            new,
            fault_hook=substitute_temp,
        )

    assert not path.exists()
    assert rename_calls == []
    residue = _temp_residue(path)
    assert len(residue) == 1
    assert residue[0].read_bytes() == attacker


def test_posix_no_replace_commit_is_one_parent_descriptor_bound_move(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temp = tmp_path / ".deck_config.ini.owned.tmp"
    target = tmp_path / "deck_config.ini"
    content = b"[CONFIGS]\nDeck = New"
    temp.write_bytes(content)
    identity = path_identity_from_status(temp.lstat())
    calls: list[tuple[int, str, str]] = []

    def atomic_move(descriptor: int, source: str, destination: str) -> bool:
        calls.append((descriptor, source, destination))
        temp.rename(target)
        return True

    monkeypatch.setattr(
        deck_config_ini,
        "_rename_noreplace_posix",
        atomic_move,
        raising=False,
    )
    with hold_plain_directory(tmp_path) as parent:
        deck_config_ini._commit_owned_temp_no_replace(
            parent,
            temp_name=temp.name,
            target_name=target.name,
            expected_identity=identity,
            expected_content=content,
            platform_name="posix",
        )
        assert calls == [(parent.descriptor, temp.name, target.name)]

    assert not temp.exists()
    assert target.read_bytes() == content
    assert target.stat().st_nlink == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX hard-link fallback")
def test_posix_no_replace_uses_hard_link_when_native_rename_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deck_config_ini,
        "_load_renameat2",
        lambda: None,
        raising=False,
    )

    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name="Deck")
    content = render_deck_config(
        snapshot,
        deck_name="Deck",
        config_dir="Portable",
    )

    replace_deck_config_if_unchanged(snapshot, content)

    assert path.read_bytes() == b"[CONFIGS]\nDeck = Portable"
    assert path.stat().st_nlink == 1
    assert _temp_residue(path) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX hard-link fallback")
@pytest.mark.parametrize("error_number", (errno.ENOSYS, errno.EINVAL))
def test_posix_no_replace_falls_back_when_renameat2_syscall_is_unsupported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    def unsupported(*_args: object) -> int:
        ctypes.set_errno(error_number)
        return -1

    monkeypatch.setattr(
        deck_config_ini,
        "_load_renameat2",
        lambda: unsupported,
        raising=False,
    )
    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name="Deck")
    content = render_deck_config(
        snapshot,
        deck_name="Deck",
        config_dir="Portable",
    )

    replace_deck_config_if_unchanged(snapshot, content)

    assert path.read_bytes() == b"[CONFIGS]\nDeck = Portable"
    assert path.stat().st_nlink == 1
    assert _temp_residue(path) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX hard-link fallback")
def test_posix_hard_link_fallback_is_exclusive_under_concurrent_first_create(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    barrier = tmp_path / "start"
    worker = tmp_path / "fallback-worker.py"
    worker.write_text(
        """
import sys
import time
from pathlib import Path
import hsconfig.deck_config_ini as deck_config_ini
from hsconfig.deck_config_ini import (
    read_deck_config,
    render_deck_config,
    replace_deck_config_if_unchanged,
)
deck_config_ini._load_renameat2 = lambda: None
path = Path(sys.argv[1])
barrier = Path(sys.argv[2])
value = sys.argv[3]
snapshot = read_deck_config(path, deck_name="Deck")
content = render_deck_config(snapshot, deck_name="Deck", config_dir=value)
while not barrier.exists():
    time.sleep(0.01)
try:
    replace_deck_config_if_unchanged(snapshot, content)
except RuntimeError as exc:
    print(str(exc))
    raise SystemExit(2)
print("committed")
""".lstrip(),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONPATH"] = source_root + os.pathsep + environment.get(
        "PYTHONPATH", ""
    )
    processes = [
        subprocess.Popen(
            [sys.executable, str(worker), str(path), str(barrier), value],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        for value in ("First", "Second")
    ]
    barrier.write_text("go", encoding="ascii")
    results = [process.communicate(timeout=20) for process in processes]

    assert sorted(process.returncode for process in processes) == [0, 2]
    assert sum("committed" in stdout for stdout, _ in results) == 1
    assert sum(
        "deck_config_ini_concurrent_change" in stdout
        for stdout, _ in results
    ) == 1
    assert path.read_bytes() in {
        b"[CONFIGS]\nDeck = First",
        b"[CONFIGS]\nDeck = Second",
    }
    assert path.stat().st_nlink == 1
    assert _temp_residue(path) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX hard-termination coverage")
def test_posix_native_commit_survives_hard_termination_without_temp_residue(
    tmp_path: Path,
) -> None:
    if deck_config_ini._load_renameat2() is None:
        pytest.skip("native renameat2 unavailable")
    path = tmp_path / "deck_config.ini"
    worker = tmp_path / "worker.py"
    worker.write_text(
        """
import os
import sys
from pathlib import Path
from hsconfig.deck_config_ini import (
    read_deck_config,
    render_deck_config,
    replace_deck_config_if_unchanged,
)
path = Path(sys.argv[1])
snapshot = read_deck_config(path, deck_name="Deck")
content = render_deck_config(snapshot, deck_name="Deck", config_dir="New")
def terminate(stage: str) -> None:
    if stage == "after_replace":
        os._exit(77)
replace_deck_config_if_unchanged(snapshot, content, fault_hook=terminate)
""".lstrip(),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONPATH"] = source_root + os.pathsep + environment.get(
        "PYTHONPATH", ""
    )

    completed = subprocess.run(
        [sys.executable, str(worker), str(path)],
        check=False,
        env=environment,
    )

    assert completed.returncode == 77
    assert path.read_bytes() == b"[CONFIGS]\nDeck = New"
    assert path.stat().st_nlink == 1
    assert _temp_residue(path) == []
    assert read_deck_config(path, deck_name="Deck").selected_config_dir == "New"


def test_two_processes_create_if_absent_and_exactly_one_commits(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    barrier = tmp_path / "start"
    worker = tmp_path / "worker.py"
    worker.write_text(
        """
import sys
import time
from pathlib import Path
from hsconfig.deck_config_ini import (
    read_deck_config,
    render_deck_config,
    replace_deck_config_if_unchanged,
)
path = Path(sys.argv[1])
barrier = Path(sys.argv[2])
value = sys.argv[3]
snapshot = read_deck_config(path, deck_name="Deck")
content = render_deck_config(snapshot, deck_name="Deck", config_dir=value)
while not barrier.exists():
    time.sleep(0.01)
try:
    replace_deck_config_if_unchanged(snapshot, content)
except RuntimeError as exc:
    print(str(exc))
    raise SystemExit(2)
print("committed")
""".lstrip(),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONPATH"] = source_root + os.pathsep + environment.get(
        "PYTHONPATH", ""
    )
    processes = [
        subprocess.Popen(
            [sys.executable, str(worker), str(path), str(barrier), value],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        for value in ("First", "Second")
    ]
    barrier.write_text("go", encoding="ascii")
    results = [process.communicate(timeout=20) for process in processes]

    assert sorted(process.returncode for process in processes) == [0, 2]
    assert sum("committed" in stdout for stdout, _ in results) == 1
    assert sum(
        "deck_config_ini_concurrent_change" in stdout
        for stdout, _ in results
    ) == 1
    assert path.read_bytes() in {
        b"[CONFIGS]\nDeck = First",
        b"[CONFIGS]\nDeck = Second",
    }
    assert _temp_residue(path) == []


def test_replace_rejects_snapshot_path_that_becomes_hardlinked(
    tmp_path: Path,
) -> None:
    path = tmp_path / "deck_config.ini"
    path.write_bytes(b"[CONFIGS]\nDeck = Old")
    snapshot = read_deck_config(path, deck_name="Deck")
    new = render_deck_config(snapshot, deck_name="Deck", config_dir="New")
    alias = tmp_path / "alias.ini"
    try:
        os.link(path, alias)
    except OSError as exc:
        pytest.skip(f"hardlinks unavailable: {exc}")

    with pytest.raises(ValueError, match="^deck_config_ini_unsafe_path$"):
        replace_deck_config_if_unchanged(snapshot, new)

    assert path.read_bytes() == b"[CONFIGS]\nDeck = Old"


def test_read_wraps_oserror_as_unsafe_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deck_config_ini,
        "capture_plain_ancestor_guard",
        lambda _path: (_ for _ in ()).throw(OSError("ancestor")),
    )
    with pytest.raises(ValueError, match="^deck_config_ini_unsafe_path$"):
        read_deck_config(tmp_path / "deck_config.ini", deck_name="Deck")


@pytest.mark.parametrize(
    "snapshot",
    (
        deck_config_ini.DeckConfigSnapshot(Path("x"), True, None, None, None),
        deck_config_ini.DeckConfigSnapshot(Path("x"), False, b"", None, None),
    ),
)
def test_render_rejects_internally_inconsistent_snapshot(
    snapshot: deck_config_ini.DeckConfigSnapshot,
) -> None:
    with pytest.raises(ValueError, match="deck_config_ini_invalid_snapshot"):
        render_deck_config(snapshot, deck_name="Deck", config_dir="Config")


def test_render_rejects_ambiguous_existing_mapping() -> None:
    content = b"[CONFIGS]\nDeck=A\ndeck=B\n"
    snapshot = deck_config_ini.DeckConfigSnapshot(
        Path("deck_config.ini"),
        True,
        content,
        hashlib.sha256(content).hexdigest(),
        None,
    )
    with pytest.raises(ValueError, match="deck_config_ini_ambiguous_mapping"):
        render_deck_config(snapshot, deck_name="Deck", config_dir="Config")


@pytest.mark.parametrize(
    ("lines", "final_newline", "expected"),
    (
        ([], False, [("value", "")]),
        ([("last", "\n")], True, [("last", "\n"), ("value", "\n")]),
        ([("last", "")], False, [("last", "\n"), ("value", "")]),
    ),
)
def test_insert_line_handles_empty_and_append_layouts(
    lines: list[tuple[str, str]],
    final_newline: bool,
    expected: list[tuple[str, str]],
) -> None:
    deck_config_ini._insert_line(lines, len(lines), "value", "\n", final_newline)
    assert lines == expected


class _ReadParent:
    def __init__(
        self,
        path: Path,
        *,
        first_error: BaseException | None = None,
        open_error: BaseException | None = None,
        final_error: BaseException | None = None,
        final_identity_change: bool = False,
    ) -> None:
        self.path = path.parent
        self.first_error = first_error
        self.open_error = open_error
        self.final_error = final_error
        self.final_identity_change = final_identity_change
        self.status_calls = 0

    def child_status(self, name: str) -> os.stat_result:
        self.status_calls += 1
        if self.status_calls == 1 and self.first_error is not None:
            raise self.first_error
        if self.status_calls > 1 and self.final_error is not None:
            raise self.final_error
        status = (self.path / name).stat()
        if self.status_calls > 1 and self.final_identity_change:
            values = list(status)
            values[1] += 1
            return os.stat_result(values)
        return status

    def open_file(self, name: str, **_kwargs: object) -> int:
        if self.open_error is not None:
            raise self.open_error
        return os.open(self.path / name, os.O_RDONLY)

    def validate(self) -> None:
        pass


@pytest.mark.parametrize(
    ("slot", "error"),
    (
        ("first_error", OSError("status")),
        ("open_error", OSError("open")),
        ("final_error", OSError("final")),
    ),
)
def test_read_plain_file_wraps_parent_operation_errors(
    tmp_path: Path,
    slot: str,
    error: BaseException,
) -> None:
    path = tmp_path / "deck_config.ini"
    path.write_bytes(b"[CONFIGS]\nDeck=A")
    parent = _ReadParent(path, **{slot: error})
    with pytest.raises(ValueError, match="deck_config_ini_unsafe_path"):
        deck_config_ini._read_plain_file(path, parent=parent)  # type: ignore[arg-type]


def test_read_plain_file_closes_descriptor_when_fstat_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "deck_config.ini"
    path.write_bytes(b"[CONFIGS]\nDeck=A")
    parent = _ReadParent(path)
    closes: list[int] = []
    real_close = os.close
    monkeypatch.setattr(
        deck_config_ini.os,
        "fstat",
        lambda _descriptor: (_ for _ in ()).throw(OSError("fstat")),
    )
    monkeypatch.setattr(deck_config_ini.os, "close", closes.append)
    with pytest.raises(OSError, match="fstat"):
        deck_config_ini._read_plain_file(path, parent=parent)  # type: ignore[arg-type]
    assert len(closes) == 1
    real_close(closes[0])


def test_read_plain_file_rejects_opened_and_final_identity_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "deck_config.ini"
    path.write_bytes(b"[CONFIGS]\nDeck=A")
    real_fstat = os.fstat
    calls = 0

    def changed_opened(descriptor: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        status = real_fstat(descriptor)
        if calls == 1:
            values = list(status)
            values[1] += 1
            return os.stat_result(values)
        return status

    monkeypatch.setattr(deck_config_ini.os, "fstat", changed_opened)
    with pytest.raises(ValueError, match="deck_config_ini_unsafe_path"):
        deck_config_ini._read_plain_file(path, parent=_ReadParent(path))  # type: ignore[arg-type]
    monkeypatch.setattr(deck_config_ini.os, "fstat", real_fstat)
    with pytest.raises(ValueError, match="deck_config_ini_unsafe_path"):
        deck_config_ini._read_plain_file(
            path,
            parent=_ReadParent(path, final_identity_change=True),  # type: ignore[arg-type]
        )


def test_replace_rejects_invalid_missing_snapshot_metadata(tmp_path: Path) -> None:
    snapshot = deck_config_ini.DeckConfigSnapshot(
        tmp_path / "deck_config.ini",
        False,
        b"stale",
        "0" * 64,
        None,
    )
    with pytest.raises(ValueError, match="deck_config_ini_invalid_snapshot"):
        replace_deck_config_if_unchanged(snapshot, b"new")


def test_replace_missing_snapshot_rejects_concurrent_file(tmp_path: Path) -> None:
    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name="Deck")
    path.write_bytes(b"concurrent")
    with pytest.raises(RuntimeError, match="deck_config_ini_concurrent_change"):
        replace_deck_config_if_unchanged(snapshot, b"new")


def test_replace_detects_failed_commit_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "deck_config.ini"
    snapshot = read_deck_config(path, deck_name="Deck")
    values = iter((None, b"wrong"))
    monkeypatch.setattr(
        deck_config_ini,
        "_current_bytes_or_none",
        lambda *_args, **_kwargs: next(values),
    )
    monkeypatch.setattr(deck_config_ini, "_atomic_create_if_absent", lambda *_args, **_kwargs: None)
    with pytest.raises(RuntimeError, match="commit_verification_failed"):
        replace_deck_config_if_unchanged(snapshot, b"new")


@pytest.mark.parametrize(
    ("error", "error_type", "message"),
    (
        (ValueError("generic"), ValueError, "deck_config_ini_unsafe_path"),
        (OSError(errno.EEXIST, "exists"), RuntimeError, "deck_config_ini_concurrent_change"),
        (OSError(errno.EIO, "io"), ValueError, "deck_config_ini_unsafe_path"),
    ),
)
def test_replace_normalizes_guard_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    error_type: type[BaseException],
    message: str,
) -> None:
    snapshot = deck_config_ini.DeckConfigSnapshot(
        tmp_path / "deck_config.ini",
        False,
        None,
        None,
        None,
    )
    monkeypatch.setattr(
        deck_config_ini,
        "capture_plain_ancestor_guard",
        lambda _path: (_ for _ in ()).throw(error),
    )
    with pytest.raises(error_type, match=message):
        replace_deck_config_if_unchanged(snapshot, b"new")


class _AtomicParent:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.identity = path_identity_from_status(path.stat())
        self.descriptor = -1

    def close(self) -> None:
        pass

    def validate(self) -> None:
        pass

    def open_file(self, name: str, *, create: bool, write: bool) -> int:
        flags = os.O_RDWR if write else os.O_RDONLY
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        return os.open(self.path / name, flags)

    def child_status(self, name: str) -> os.stat_result:
        return (self.path / name).stat()


def test_atomic_create_exhausts_temp_name_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _AtomicParent(tmp_path)
    try:
        monkeypatch.setattr(
            parent,
            "open_file",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(FileExistsError()),
        )
        with pytest.raises(FileExistsError, match="temp_creation_failed"):
            deck_config_ini._atomic_create_if_absent(
                tmp_path / "deck_config.ini",
                b"content",
                parent=parent,  # type: ignore[arg-type]
                fault_hook=deck_config_ini.no_fault,
            )
    finally:
        parent.close()


def test_atomic_create_propagates_non_collision_commit_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _AtomicParent(tmp_path)
    monkeypatch.setattr(
        deck_config_ini,
        "_commit_owned_temp_no_replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(errno.EIO, "commit")),
    )
    try:
        with pytest.raises(OSError, match="commit"):
            deck_config_ini._atomic_create_if_absent(
                tmp_path / "deck_config.ini",
                b"content",
                parent=parent,  # type: ignore[arg-type]
                fault_hook=deck_config_ini.no_fault,
            )
    finally:
        parent.close()


def test_atomic_create_records_cleanup_failures_without_masking_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _AtomicParent(tmp_path)
    primary = InjectedBaseFault("write")

    class BrokenHandle:
        def write(self, _content: bytes) -> int:
            raise primary

        def close(self) -> None:
            raise RuntimeError("close")

        def fileno(self) -> int:
            return 0

    monkeypatch.setattr(parent, "open_file", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(deck_config_ini.os, "fdopen", lambda *_args, **_kwargs: BrokenHandle())
    monkeypatch.setattr(deck_config_ini.os, "fstat", lambda _fd: tmp_path.stat())
    monkeypatch.setattr(
        parent,
        "child_status",
        lambda _name: (_ for _ in ()).throw(OSError("cleanup")),
    )
    try:
        with pytest.raises(InjectedBaseFault, match="write") as caught:
            deck_config_ini._atomic_create_if_absent(
                tmp_path / "deck_config.ini",
                b"content",
                parent=parent,  # type: ignore[arg-type]
                fault_hook=deck_config_ini.no_fault,
            )
    finally:
        parent.close()
    assert any("temp handle close failed" in note for note in caught.value.__notes__)
    assert any("owned temp cleanup failed" in note for note in caught.value.__notes__)


def test_atomic_create_ignores_missing_temp_during_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _AtomicParent(tmp_path)
    descriptors: list[int] = []
    original_open_file = parent.open_file

    def tracked_open_file(name: str, *, create: bool, write: bool) -> int:
        descriptor = original_open_file(name, create=create, write=write)
        descriptors.append(descriptor)
        return descriptor

    monkeypatch.setattr(parent, "open_file", tracked_open_file)
    monkeypatch.setattr(
        deck_config_ini.os,
        "fdopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(InjectedBaseFault("fdopen")),
    )
    monkeypatch.setattr(
        parent,
        "child_status",
        lambda _name: (_ for _ in ()).throw(FileNotFoundError()),
    )
    with pytest.raises(InjectedBaseFault, match="fdopen"):
        deck_config_ini._atomic_create_if_absent(
            tmp_path / "deck_config.ini",
            b"content",
            parent=parent,  # type: ignore[arg-type]
            fault_hook=deck_config_ini.no_fault,
        )
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])


def test_atomic_create_records_raw_descriptor_close_failure_without_masking_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _AtomicParent(tmp_path)
    descriptors: list[int] = []
    close_calls: list[int] = []
    original_open_file = parent.open_file
    original_close = os.close

    def tracked_open_file(name: str, *, create: bool, write: bool) -> int:
        descriptor = original_open_file(name, create=create, write=write)
        descriptors.append(descriptor)
        return descriptor

    def failing_close(descriptor: int) -> None:
        close_calls.append(descriptor)
        original_close(descriptor)
        raise RuntimeError("descriptor close")

    monkeypatch.setattr(parent, "open_file", tracked_open_file)
    monkeypatch.setattr(
        deck_config_ini.os,
        "fdopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(InjectedBaseFault("fdopen")),
    )
    monkeypatch.setattr(deck_config_ini.os, "close", failing_close)
    monkeypatch.setattr(
        parent,
        "child_status",
        lambda _name: (_ for _ in ()).throw(FileNotFoundError()),
    )

    with pytest.raises(InjectedBaseFault, match="fdopen") as caught:
        deck_config_ini._atomic_create_if_absent(
            tmp_path / "deck_config.ini",
            b"content",
            parent=parent,  # type: ignore[arg-type]
            fault_hook=deck_config_ini.no_fault,
        )

    assert len(descriptors) == 1
    assert close_calls == descriptors
    assert any(
        "temp descriptor close failed" in note
        for note in getattr(caught.value, "__notes__", ())
    )
    with pytest.raises(OSError):
        os.fstat(descriptors[0])


def test_atomic_create_ignores_temp_that_disappears_after_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _AtomicParent(tmp_path)
    monkeypatch.setattr(
        parent,
        "child_status",
        lambda _name: (_ for _ in ()).throw(FileNotFoundError()),
    )
    with pytest.raises(InjectedBaseFault, match="after_temp_write"):
        deck_config_ini._atomic_create_if_absent(
            tmp_path / "deck_config.ini",
            b"content",
            parent=parent,  # type: ignore[arg-type]
            fault_hook=_fault_at("after_temp_write", InjectedBaseFault),
        )
    for residue in tmp_path.glob("*.tmp"):
        residue.unlink()


def test_commit_owned_temp_rejects_unknown_platform(tmp_path: Path) -> None:
    parent = _AtomicParent(tmp_path)
    temp = tmp_path / "temp"
    temp.write_bytes(b"content")
    identity = path_identity_from_status(temp.stat())
    with pytest.raises(RuntimeError, match="atomic_create_unsupported"):
        deck_config_ini._commit_owned_temp_no_replace(
            parent,  # type: ignore[arg-type]
            temp_name="temp",
            target_name="target",
            expected_identity=identity,
            expected_content=b"content",
            platform_name="unknown",
        )


def test_posix_commit_uses_link_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _AtomicParent(tmp_path)
    temp = tmp_path / "temp"
    temp.write_bytes(b"content")
    identity = path_identity_from_status(temp.stat())
    calls: list[str] = []
    monkeypatch.setattr(deck_config_ini, "_rename_noreplace_posix", lambda *_args: False)
    monkeypatch.setattr(
        deck_config_ini,
        "_link_noreplace_posix",
        lambda *_args, **_kwargs: calls.append("link"),
    )
    monkeypatch.setattr(deck_config_ini, "_validate_owned_child", lambda *_args, **_kwargs: None)
    deck_config_ini._commit_owned_temp_no_replace(
        parent,  # type: ignore[arg-type]
        temp_name="temp",
        target_name="target",
        expected_identity=identity,
        expected_content=b"content",
        platform_name="posix",
    )
    assert calls == ["link"]


@pytest.mark.parametrize("mode", ("initial", "final", "wrapped"))
def test_validate_owned_child_rejects_invalid_or_unreadable_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    parent = _AtomicParent(tmp_path)
    target = tmp_path / "target"
    target.write_bytes(b"content")
    identity = path_identity_from_status(target.stat())
    expected_identity = identity
    if mode == "initial":
        expected_identity = (identity[0], identity[1] + 1, identity[2])
    elif mode == "final":
        real_identity = deck_config_ini.path_identity_from_status
        identity_calls = 0

        def changed_final(status: os.stat_result) -> tuple[int, int, int]:
            nonlocal identity_calls
            identity_calls += 1
            result = real_identity(status)
            if identity_calls == 2:
                return (result[0], result[1] + 1, result[2])
            return result

        monkeypatch.setattr(
            deck_config_ini,
            "path_identity_from_status",
            changed_final,
        )
        monkeypatch.setattr(
            deck_config_ini,
            "_read_plain_file",
            lambda *_args, **_kwargs: b"content",
        )
    else:
        monkeypatch.setattr(
            parent,
            "child_status",
            lambda _name: (_ for _ in ()).throw(OSError("status")),
        )
    with pytest.raises(RuntimeError, match="verification_failed"):
        deck_config_ini._validate_owned_child(
            parent,  # type: ignore[arg-type]
            name="target",
            expected_identity=expected_identity,
            expected_content=b"content",
            error_code="verification_failed",
        )


class _FakeRename:
    def __init__(self, result: int, error_number: int = 0) -> None:
        self.result = result
        self.error_number = error_number

    def __call__(self, *_args: object) -> int:
        ctypes.set_errno(self.error_number)
        return self.result


@pytest.mark.parametrize(
    ("function", "expected"),
    ((None, False), (_FakeRename(0), True), (_FakeRename(-1, errno.ENOSYS), False)),
)
def test_rename_noreplace_posix_reports_outcome(
    monkeypatch: pytest.MonkeyPatch,
    function: _FakeRename | None,
    expected: bool,
) -> None:
    monkeypatch.setattr(deck_config_ini, "_load_renameat2", lambda: function)
    assert deck_config_ini._rename_noreplace_posix(1, "source", "target") is expected


@pytest.mark.parametrize("error_number", (errno.EEXIST, errno.EIO))
def test_rename_noreplace_posix_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    monkeypatch.setattr(
        deck_config_ini,
        "_load_renameat2",
        lambda: _FakeRename(-1, error_number),
    )
    expected = FileExistsError if error_number == errno.EEXIST else OSError
    with pytest.raises(expected):
        deck_config_ini._rename_noreplace_posix(1, "source", "target")


def test_link_noreplace_wraps_unsupported_platform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _AtomicParent(tmp_path)
    monkeypatch.setattr(
        deck_config_ini.os,
        "link",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(NotImplementedError()),
    )
    with pytest.raises(RuntimeError, match="atomic_create_unsupported"):
        deck_config_ini._link_noreplace_posix(
            parent,  # type: ignore[arg-type]
            temp_name="temp",
            target_name="target",
            expected_identity=(1, 2, 3),
        )


@pytest.mark.parametrize("valid", (False, True))
def test_link_noreplace_validates_and_unlinks_owned_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    valid: bool,
) -> None:
    parent = _AtomicParent(tmp_path)
    temp = tmp_path / "temp"
    target = tmp_path / "target"
    temp.write_bytes(b"content")
    identity = path_identity_from_status(temp.stat())
    real_link = os.link
    real_unlink = os.unlink

    def fake_link(source: str, destination: str, **_kwargs: object) -> None:
        real_link(tmp_path / source, tmp_path / destination)

    def fake_unlink(name: str, **_kwargs: object) -> None:
        real_unlink(tmp_path / name)

    monkeypatch.setattr(deck_config_ini.os, "link", fake_link)
    monkeypatch.setattr(deck_config_ini.os, "unlink", fake_unlink)
    expected_identity = identity if valid else (identity[0], identity[1] + 1, identity[2])
    if valid:
        deck_config_ini._link_noreplace_posix(
            parent,  # type: ignore[arg-type]
            temp_name="temp",
            target_name="target",
            expected_identity=expected_identity,
        )
        assert not temp.exists()
        assert target.read_bytes() == b"content"
    else:
        with pytest.raises(RuntimeError, match="commit_verification_failed"):
            deck_config_ini._link_noreplace_posix(
                parent,  # type: ignore[arg-type]
                temp_name="temp",
                target_name="target",
                expected_identity=expected_identity,
            )


def test_load_renameat2_handles_missing_symbol_and_configures_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deck_config_ini.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("missing")),
    )
    assert deck_config_ini._load_renameat2() is None

    class FakeFunction:
        argtypes: object = None
        restype: object = None

    function = FakeFunction()
    library = type("Library", (), {"renameat2": function})()
    monkeypatch.setattr(deck_config_ini.ctypes, "CDLL", lambda *_args, **_kwargs: library)
    assert deck_config_ini._load_renameat2() is function
    assert function.argtypes is not None
    assert function.restype is ctypes.c_int


class _HostilePrimary(BaseException):
    def add_note(self, _note: str) -> None:
        raise RuntimeError("hostile")


def test_add_note_never_masks_hostile_primary() -> None:
    deck_config_ini._add_note(_HostilePrimary(), "cleanup", RuntimeError("secondary"))
