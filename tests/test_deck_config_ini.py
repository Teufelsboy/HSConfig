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
