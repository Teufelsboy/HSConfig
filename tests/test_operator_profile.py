from __future__ import annotations

import copy
import gc
import json
import os
import pickle
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from queue import Queue
from threading import Event, Thread

import pytest

import hsconfig.operator_profile as operator_profile
import hsconfig.output_operation_admission as output_operation_admission
from hsconfig.operator_profile import (
    OperatorProfileLockToken,
    derive_deck_output_binding,
    disable_operator_profile,
    enable_operator_profile,
    lease_operator_profile,
    load_operator_profile,
    operator_profile_path,
    revalidate_operator_profile,
    revalidate_operator_profile_lease,
)
from hsconfig.package_io import path_identity


STANDARD_DIGEST = "sha256:" + ("1" * 64)
SUPERSCRIPT_DOS_DEVICE_COMPONENTS = (
    "COM¹",
    "COM²",
    "COM³",
    "LPT¹",
    "LPT²",
    "LPT³",
    "COM¹.txt",
    "COM².txt",
    "COM³.txt",
    "LPT¹.txt",
    "LPT².txt",
    "LPT³.txt",
)
UNC_IPC_NAMESPACE_PATHS = (
    "\\\\server\\PiPe\\authority",
    "\\\\server\\MaIlSlOt\\authority",
    "\\\\server\\iPc$\\authority",
)


def _layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    local_app_data = tmp_path / "local-app-data"
    runtime_root = tmp_path / "runtime"
    output_base_root = tmp_path / "outputs"
    local_app_data.mkdir()
    runtime_root.mkdir()
    output_base_root.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    return local_app_data, runtime_root, output_base_root


def _enable(runtime_root: Path, output_base_root: Path):
    return enable_operator_profile(
        runtime_root=runtime_root,
        output_base_root=output_base_root,
        expected_predecessor_sha256=None,
    )


def _canonical_document(document: dict[str, object]) -> bytes:
    return json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _create_ntfs_stream_or_skip(path: Path) -> Path:
    if os.name != "nt":
        pytest.skip("NTFS alternate data streams are Windows-specific")
    probe_path = path.parent / ".hsconfig-review-fix-ads-probe"
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


def _administrative_share_alias_or_skip(path: Path) -> Path:
    if os.name != "nt":
        pytest.skip("drive and administrative-share aliases are Windows-specific")
    drive = path.drive
    if len(drive) != 2 or drive[1] != ":":
        pytest.skip("test path is not on a drive-backed Windows volume")
    alias = Path(f"\\\\localhost\\{drive[0]}$").joinpath(*path.parts[1:])
    try:
        available = alias.is_dir() and path_identity(alias) == path_identity(path)
    except OSError:
        available = False
    if not available:
        pytest.skip("local administrative share is unavailable")
    return alias


def _long_windows_profile_root(parent: Path) -> Path:
    if os.name != "nt":
        pytest.skip("the real UTF-8/UTF-16 long-path reproducer is Windows-specific")
    parent.mkdir()
    current = parent
    for index in range(110):
        current /= f"{index:03d}-" + ("界" * 235)
        current.mkdir()
    return current


def _active_admission_document(
    *,
    local_app_data: Path,
    profile_sha256: str,
    output_base_root: Path,
) -> tuple[dict[str, object], bytes]:
    state_root = local_app_data / "HSConfig"
    profile_path = state_root / "operator-profile.json"
    session_root = local_app_data.parent / "session"
    session_root.mkdir(exist_ok=True)
    output_child = output_base_root / "deck"
    bootstrap_lock = state_root / "locks" / "output-child-test.lock"
    bootstrap_lock.touch(exist_ok=True)
    unsigned: dict[str, object] = {
        "schema_version": 1,
        "record_kind": "live_start_output_operation_admission",
        "state": "ACTIVE",
        "run_id": "a" * 32,
        "session_root": str(session_root.resolve()),
        "session_root_identity": list(path_identity(session_root)),
        "expected_session_sha256": STANDARD_DIGEST,
        "operator_profile_path": str(profile_path.resolve()),
        "operator_profile_parent_identity": list(path_identity(state_root)),
        "operator_profile_identity": list(path_identity(profile_path)),
        "operator_profile_sha256": profile_sha256,
        "state_root_identity": list(path_identity(state_root)),
        "output_base_root": str(output_base_root.resolve()),
        "output_base_root_identity": list(path_identity(output_base_root)),
        "output_child_path": str(output_child.resolve()),
        "output_child_predecessor_state": "absent",
        "output_child_predecessor_identity": None,
        "output_bootstrap_lock_path": str(bootstrap_lock.resolve()),
        "output_bootstrap_lock_identity": list(path_identity(bootstrap_lock)),
        "output_claim_path": str(
            (output_base_root / ".hsconfig-live-start-output-child-test.claim.json").resolve()
        ),
    }
    digest = "sha256:" + sha256(_canonical_document(unsigned)).hexdigest()
    document = {**unsigned, "content_sha256": digest}
    return document, _canonical_document(document)


def test_enable_writes_closed_canonical_profile_and_reloads_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)

    profile = _enable(runtime_root, output_base_root)
    profile_path = operator_profile_path()
    raw = profile_path.read_bytes()
    document = json.loads(raw)

    assert set(document) == {
        "schema_version",
        "live_by_default",
        "runtime_root",
        "runtime_root_identity",
        "output_base_root",
        "output_base_root_identity",
        "content_sha256",
    }
    assert document["schema_version"] == 1
    assert document["live_by_default"] is True
    assert raw == _canonical_document(document)
    assert profile == load_operator_profile()
    assert profile.runtime_root == runtime_root.resolve()
    assert profile.output_base_root == output_base_root.resolve()
    assert profile.content_sha256 == document["content_sha256"]


def test_disable_preserves_bound_roots_and_only_changes_live_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    enabled = _enable(runtime_root, output_base_root)
    enabled_document = json.loads(operator_profile_path().read_bytes())

    disabled = disable_operator_profile(
        expected_predecessor_sha256=enabled.content_sha256
    )
    disabled_document = json.loads(operator_profile_path().read_bytes())

    assert disabled.live_by_default is False
    assert disabled.runtime_root == enabled.runtime_root
    assert disabled.runtime_root_identity == enabled.runtime_root_identity
    assert disabled.output_base_root == enabled.output_base_root
    assert disabled.output_base_root_identity == enabled.output_base_root_identity
    assert {
        key: value
        for key, value in enabled_document.items()
        if key not in {"live_by_default", "content_sha256"}
    } == {
        key: value
        for key, value in disabled_document.items()
        if key not in {"live_by_default", "content_sha256"}
    }
    assert disabled.content_sha256 != enabled.content_sha256
    assert load_operator_profile() == disabled


def test_normal_load_is_read_only_and_detects_self_digest_or_identity_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    expected = _enable(runtime_root, output_base_root)
    profile_path = operator_profile_path()
    original_bytes = profile_path.read_bytes()
    initial = (original_bytes, path_identity(profile_path), profile_path.stat().st_mtime_ns)

    loaded = load_operator_profile()
    observations = [initial]
    for _ in range(2):
        assert revalidate_operator_profile(loaded) == loaded
        observations.append(
            (
                profile_path.read_bytes(),
                path_identity(profile_path),
                profile_path.stat().st_mtime_ns,
            )
        )
    assert load_operator_profile() == expected
    assert observations == [initial, initial, initial]

    tampered = json.loads(original_bytes)
    tampered["content_sha256"] = "sha256:" + ("0" * 64)
    profile_path.write_bytes(_canonical_document(tampered))
    with pytest.raises(ValueError):
        revalidate_operator_profile(loaded)

    profile_path.write_bytes(original_bytes)
    replacement = profile_path.with_name("replacement.json")
    replacement.write_bytes(original_bytes)
    os.replace(replacement, profile_path)
    with pytest.raises(ValueError, match="identity"):
        revalidate_operator_profile(loaded)


def test_profile_rejects_missing_overlapping_reparse_or_unsafe_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    missing = tmp_path / "missing"
    with pytest.raises((FileNotFoundError, ValueError)):
        _enable(missing, output_base_root)

    unsafe_file = tmp_path / "not-a-directory"
    unsafe_file.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        _enable(unsafe_file, output_base_root)

    with pytest.raises(ValueError, match="overlap"):
        _enable(runtime_root, runtime_root)

    nested_output = runtime_root / "nested"
    nested_output.mkdir()
    with pytest.raises(ValueError, match="overlap"):
        _enable(runtime_root, nested_output)

    target = tmp_path / "reparse-target"
    alias = tmp_path / "reparse-alias"
    target.mkdir()
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError:
        return
    with pytest.raises(ValueError):
        _enable(alias, output_base_root)


def test_profile_roots_are_disjoint_from_the_hsconfig_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    state_root = local_app_data / "HSConfig"
    state_root.mkdir()

    with pytest.raises(ValueError, match="state_root_overlap"):
        _enable(state_root, output_base_root)
    with pytest.raises(ValueError, match="state_root_overlap"):
        _enable(runtime_root, local_app_data)


def test_enable_safely_creates_state_root_but_load_and_disable_never_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    state_root = local_app_data / "HSConfig"

    with pytest.raises(FileNotFoundError):
        load_operator_profile()
    assert not state_root.exists()
    with pytest.raises(FileNotFoundError):
        disable_operator_profile(expected_predecessor_sha256=STANDARD_DIGEST)
    assert not state_root.exists()

    _enable(runtime_root, output_base_root)
    assert state_root.is_dir()
    assert (state_root / "operator-profile.lock").is_file()
    assert (state_root / "locks").is_dir()
    operation_lock = state_root / "locks" / "output-operation.lock"
    assert operation_lock.is_file()
    assert operation_lock.read_bytes() == b""


def test_deck_output_binding_is_safe_stable_and_identity_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)

    absent = derive_deck_output_binding(profile, "Shadow Priest!")
    assert absent.output_name == "shadow_priest"
    assert absent.output_root == output_base_root.resolve() / "shadow_priest"
    assert absent.precondition_state == "absent"
    assert absent.precondition_identity is None
    assert not absent.output_root.exists()
    assert derive_deck_output_binding(profile, "Shadow Priest!") == absent

    absent.output_root.mkdir()
    existing = derive_deck_output_binding(load_operator_profile(), "Shadow Priest!")
    assert existing.precondition_state == "existing"
    assert existing.precondition_identity == path_identity(absent.output_root)

    with pytest.raises(ValueError, match="reserved"):
        derive_deck_output_binding(profile, "CON")
    with pytest.raises(ValueError, match="length"):
        derive_deck_output_binding(profile, "x" * 129)
    unsafe_child = output_base_root / "unsafe"
    unsafe_child.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError):
        derive_deck_output_binding(load_operator_profile(), "unsafe")


def test_enable_and_disable_require_absent_or_exact_predecessor_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    first = _enable(runtime_root, output_base_root)
    profile_path = operator_profile_path()
    first_state = (
        profile_path.read_bytes(),
        path_identity(profile_path),
        profile_path.stat().st_mtime_ns,
    )

    with pytest.raises(ValueError, match="predecessor"):
        _enable(runtime_root, output_base_root)
    with pytest.raises(ValueError, match="predecessor"):
        enable_operator_profile(
            runtime_root=runtime_root,
            output_base_root=output_base_root,
            expected_predecessor_sha256=STANDARD_DIGEST,
        )
    assert (
        profile_path.read_bytes(),
        path_identity(profile_path),
        profile_path.stat().st_mtime_ns,
    ) == first_state

    idempotent = enable_operator_profile(
        runtime_root=runtime_root,
        output_base_root=output_base_root,
        expected_predecessor_sha256=first.content_sha256,
    )
    assert idempotent == first
    assert (
        profile_path.read_bytes(),
        path_identity(profile_path),
        profile_path.stat().st_mtime_ns,
    ) == first_state

    rebound_root = tmp_path / "rebound-output"
    rebound_root.mkdir()
    rebound = enable_operator_profile(
        runtime_root=runtime_root,
        output_base_root=rebound_root,
        expected_predecessor_sha256=first.content_sha256,
    )
    with pytest.raises(ValueError, match="predecessor"):
        disable_operator_profile(expected_predecessor_sha256=first.content_sha256)
    disabled = disable_operator_profile(
        expected_predecessor_sha256=rebound.content_sha256
    )
    assert disabled.live_by_default is False

    before_race = profile_path.read_bytes()
    race_output = tmp_path / "race-output"
    race_output.mkdir()
    real_atomic_write = operator_profile.atomic_write_bytes

    def replace_root_before_write(
        path: Path, content: bytes, **kwargs: object
    ) -> None:
        race_output.rmdir()
        race_output.mkdir()
        real_atomic_write(path, content, **kwargs)

    monkeypatch.setattr(
        operator_profile,
        "atomic_write_bytes",
        replace_root_before_write,
    )
    with pytest.raises(ValueError, match="identity"):
        enable_operator_profile(
            runtime_root=runtime_root,
            output_base_root=race_output,
            expected_predecessor_sha256=disabled.content_sha256,
        )
    assert profile_path.read_bytes() == before_race


@pytest.mark.parametrize(
    "invalid_canonical",
    (b"", b"x" * (operator_profile.OPERATOR_PROFILE_MAX_BYTES + 1)),
    ids=("empty", "oversized"),
)
def test_expected_absent_enable_rejects_invalid_canonical_size_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_canonical: bytes,
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)

    def invalid_seal(**_kwargs: object) -> bytes:
        return invalid_canonical

    monkeypatch.setattr(operator_profile, "_seal_profile", invalid_seal)
    with pytest.raises(ValueError):
        _enable(runtime_root, output_base_root)

    assert not operator_profile_path().exists()


def test_real_long_path_profile_is_rejected_before_expected_absent_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    local_app_data, _runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    long_runtime_root = _long_windows_profile_root(tmp_path / "long-runtime")

    with pytest.raises(ValueError):
        _enable(long_runtime_root, output_base_root)

    assert not (local_app_data / "HSConfig" / "operator-profile.json").exists()


@pytest.mark.parametrize("mutation", ("rebind", "disable"))
def test_oversized_profile_mutation_preserves_exact_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)
    profile_path = operator_profile_path()
    predecessor = (
        profile_path.read_bytes(),
        path_identity(profile_path),
        profile_path.stat().st_mtime_ns,
    )

    def oversized_seal(**_kwargs: object) -> bytes:
        return b"x" * (operator_profile.OPERATOR_PROFILE_MAX_BYTES + 1)

    monkeypatch.setattr(operator_profile, "_seal_profile", oversized_seal)
    with pytest.raises(ValueError):
        if mutation == "rebind":
            rebound_output = tmp_path / "rebound-oversized"
            rebound_output.mkdir()
            enable_operator_profile(
                runtime_root=runtime_root,
                output_base_root=rebound_output,
                expected_predecessor_sha256=profile.content_sha256,
            )
        else:
            disable_operator_profile(
                expected_predecessor_sha256=profile.content_sha256
            )

    assert (
        profile_path.read_bytes(),
        path_identity(profile_path),
        profile_path.stat().st_mtime_ns,
    ) == predecessor


def test_operator_profile_lease_is_active_nonforgeable_and_expires_on_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)
    cross_thread: Queue[BaseException | None] = Queue()

    with lease_operator_profile(expected_profile=profile) as lease:
        assert revalidate_operator_profile_lease(lease) == profile
        with pytest.raises(TypeError):
            OperatorProfileLockToken()
        with pytest.raises(TypeError):
            copy.copy(lease.lock_token)
        with pytest.raises(TypeError):
            pickle.dumps(lease.lock_token)

        def use_cross_thread() -> None:
            try:
                revalidate_operator_profile_lease(lease)
            except BaseException as error:
                cross_thread.put(error)
            else:
                cross_thread.put(None)

        thread = Thread(target=use_cross_thread)
        thread.start()
        thread.join(timeout=5)
        assert isinstance(cross_thread.get_nowait(), ValueError)

    with pytest.raises(ValueError, match="inactive"):
        revalidate_operator_profile_lease(lease)


def test_profile_mutation_waits_for_active_live_authority_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)
    started = Event()
    finished = Event()
    result: Queue[object] = Queue()

    def disable() -> None:
        started.set()
        try:
            result.put(
                disable_operator_profile(
                    expected_predecessor_sha256=profile.content_sha256
                )
            )
        except BaseException as error:
            result.put(error)
        finally:
            finished.set()

    with lease_operator_profile(expected_profile=profile):
        thread = Thread(target=disable)
        thread.start()
        assert started.wait(timeout=2)
        assert not finished.wait(timeout=0.2)

    thread.join(timeout=5)
    assert not thread.is_alive()
    outcome = result.get_nowait()
    assert not isinstance(outcome, BaseException)
    assert outcome.live_by_default is False


def test_operator_profile_lease_missing_lock_is_read_only_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)
    lock_path = operator_profile_path().with_name("operator-profile.lock")
    lock_path.unlink()
    profile_bytes = operator_profile_path().read_bytes()

    assert load_operator_profile() == profile
    with pytest.raises(FileNotFoundError):
        with lease_operator_profile(expected_profile=profile):
            pass
    assert not lock_path.exists()
    assert operator_profile_path().read_bytes() == profile_bytes


def test_operator_profile_lease_revalidation_detects_byte_identity_or_root_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)
    profile_path = operator_profile_path()
    original_bytes = profile_path.read_bytes()

    with lease_operator_profile(expected_profile=profile) as lease:
        profile_path.write_bytes(original_bytes + b" ")
        with pytest.raises(ValueError):
            revalidate_operator_profile_lease(lease)
    profile_path.write_bytes(original_bytes)
    loaded = load_operator_profile()

    with lease_operator_profile(expected_profile=loaded) as lease:
        replacement = profile_path.with_name("same-bytes.json")
        replacement.write_bytes(original_bytes)
        os.replace(replacement, profile_path)
        with pytest.raises(ValueError, match="identity"):
            revalidate_operator_profile_lease(lease)
    loaded = load_operator_profile()

    with lease_operator_profile(expected_profile=loaded) as lease:
        output_base_root.rmdir()
        output_base_root.mkdir()
        with pytest.raises(ValueError, match="identity"):
            revalidate_operator_profile_lease(lease)


def test_profile_enable_bootstraps_fixed_operation_lock_before_profile_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    real_atomic_write = operator_profile.atomic_write_bytes
    observed: list[str] = []

    def checked_atomic_write(path: Path, content: bytes, **kwargs: object) -> None:
        operation_lock = local_app_data / "HSConfig" / "locks" / "output-operation.lock"
        assert operation_lock.is_file()
        assert operation_lock.stat().st_size == 0
        observed.append("profile_cas")
        real_atomic_write(path, content, **kwargs)

    monkeypatch.setattr(operator_profile, "atomic_write_bytes", checked_atomic_write)
    _enable(runtime_root, output_base_root)

    assert observed == ["profile_cas"]


def test_profile_mutations_reject_present_malformed_or_replaced_output_operation_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)
    profile_path = operator_profile_path()
    original = profile_path.read_bytes()
    admission_path = local_app_data / "HSConfig" / "output-operation-admission.json"

    admission_path.write_bytes(b"{}")
    with pytest.raises(ValueError):
        disable_operator_profile(expected_predecessor_sha256=profile.content_sha256)
    assert profile_path.read_bytes() == original
    admission_path.unlink()

    _document, canonical = _active_admission_document(
        local_app_data=local_app_data,
        profile_sha256=profile.content_sha256,
        output_base_root=output_base_root,
    )
    admission_path.write_bytes(canonical)
    replacement = admission_path.with_name("replacement.json")
    replacement.write_bytes(canonical)
    os.replace(replacement, admission_path)
    with pytest.raises(ValueError, match="output_operation"):
        enable_operator_profile(
            runtime_root=runtime_root,
            output_base_root=output_base_root,
            expected_predecessor_sha256=profile.content_sha256,
        )
    assert profile_path.read_bytes() == original


def test_profile_mutations_reject_output_operation_staging_or_reserved_temp_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)
    state_root = local_app_data / "HSConfig"
    profile_bytes = operator_profile_path().read_bytes()

    for name in (
        "output-operation-admission.staged",
        ".output-operation-admission.staged.live-start-atomic.tmp",
    ):
        residue = state_root / name
        residue.write_bytes(b"residue")
        with pytest.raises(ValueError, match="output_operation"):
            disable_operator_profile(
                expected_predecessor_sha256=profile.content_sha256
            )
        assert operator_profile_path().read_bytes() == profile_bytes
        residue.unlink()


def test_profile_mutation_lock_order_is_profile_then_output_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)
    events: list[str] = []
    real_profile_lock = operator_profile.ExclusiveFileLock
    real_operation_lock = output_operation_admission.ExclusiveFileLock

    @contextmanager
    def traced_profile_lock(*args: object, **kwargs: object):
        with real_profile_lock(*args, **kwargs) as lock:
            events.append("profile_enter")
            try:
                yield lock
            finally:
                events.append("profile_exit")

    @contextmanager
    def traced_operation_lock(*args: object, **kwargs: object):
        with real_operation_lock(*args, **kwargs) as lock:
            events.append("operation_enter")
            try:
                yield lock
            finally:
                events.append("operation_exit")

    monkeypatch.setattr(operator_profile, "ExclusiveFileLock", traced_profile_lock)
    monkeypatch.setattr(
        output_operation_admission, "ExclusiveFileLock", traced_operation_lock
    )

    enable_operator_profile(
        runtime_root=runtime_root,
        output_base_root=output_base_root,
        expected_predecessor_sha256=profile.content_sha256,
    )

    assert events == [
        "profile_enter",
        "operation_enter",
        "operation_exit",
        "profile_exit",
    ]


def test_absent_profile_enable_is_blocked_by_active_output_operation_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    state_root = local_app_data / "HSConfig"
    locks = state_root / "locks"
    locks.mkdir(parents=True)
    (locks / "output-operation.lock").touch()
    placeholder_profile = state_root / "operator-profile.json"
    placeholder_profile.touch()
    _document, canonical = _active_admission_document(
        local_app_data=local_app_data,
        profile_sha256=STANDARD_DIGEST,
        output_base_root=output_base_root,
    )
    placeholder_profile.unlink()
    (state_root / "output-operation-admission.json").write_bytes(canonical)

    with pytest.raises(ValueError, match="output_operation"):
        _enable(runtime_root, output_base_root)
    assert not placeholder_profile.exists()


def test_operator_profile_rejects_ntfs_alternate_data_streams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    _enable(runtime_root, output_base_root)
    profile_path = operator_profile_path()
    stream_path = _create_ntfs_stream_or_skip(profile_path)
    try:
        with pytest.raises(ValueError, match="alternate_data_stream"):
            load_operator_profile()
    finally:
        stream_path.unlink(missing_ok=True)


@pytest.mark.parametrize(
    "surface",
    ("state_root", "locks_root", "profile_lock", "output_operation_lock"),
)
def test_task1_state_and_lock_surfaces_reject_ntfs_alternate_data_streams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
):
    local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)
    state_root = local_app_data / "HSConfig"
    surfaces = {
        "state_root": state_root,
        "locks_root": state_root / "locks",
        "profile_lock": state_root / "operator-profile.lock",
        "output_operation_lock": state_root / "locks" / "output-operation.lock",
    }
    stream_path = _create_ntfs_stream_or_skip(surfaces[surface])
    try:
        with pytest.raises(ValueError, match="alternate_data_stream"):
            if surface in {"state_root", "profile_lock"}:
                with lease_operator_profile(expected_profile=profile):
                    pass
            else:
                with output_operation_admission.lease_output_operation_admission():
                    pass
    finally:
        stream_path.unlink(missing_ok=True)


@pytest.mark.parametrize("path_field", ("runtime_root", "output_base_root"))
@pytest.mark.parametrize(
    "unsafe_component",
    (
        "alias.",
        "alias ",
        "payload:stream",
        "NUL",
        "COM1.txt",
        *SUPERSCRIPT_DOS_DEVICE_COMPONENTS,
        *UNC_IPC_NAMESPACE_PATHS,
    ),
)
def test_operator_profile_rejects_unsafe_windows_namespace_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_field: str,
    unsafe_component: str,
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    _enable(runtime_root, output_base_root)
    profile_path = operator_profile_path()
    document = json.loads(profile_path.read_bytes())
    document[path_field] = str(tmp_path / unsafe_component)
    unsigned = dict(document)
    unsigned.pop("content_sha256")
    document["content_sha256"] = (
        "sha256:" + sha256(_canonical_document(unsigned)).hexdigest()
    )
    profile_path.write_bytes(_canonical_document(document))

    with pytest.raises(ValueError, match="namespace"):
        load_operator_profile()


@pytest.mark.parametrize(
    ("left_identities", "left_remaining", "right_identities", "right_remaining", "expected"),
    (
        (((1, 10, 1), (1, 1, 1)), (), ((1, 10, 1), (2, 1, 1)), (), True),
        (((1, 10, 1), (1, 1, 1)), (), ((1, 11, 1), (1, 10, 1), (1, 1, 1)), (), True),
        (((1, 11, 1), (1, 10, 1), (1, 1, 1)), (), ((1, 10, 1), (1, 1, 1)), (), True),
        (((1, 11, 1), (1, 10, 1), (1, 1, 1)), (), ((1, 12, 1), (1, 10, 1), (1, 1, 1)), (), False),
        (((1, 10, 1), (1, 1, 1)), (), ((1, 10, 1), (1, 1, 1)), ("HSConfig",), True),
        (((1, 11, 1), (1, 10, 1), (1, 1, 1)), (), ((1, 10, 1), (1, 1, 1)), ("HSConfig",), False),
    ),
)
def test_physical_identity_mapping_detects_only_equal_or_containing_roots(
    left_identities: tuple[tuple[int, int, int], ...],
    left_remaining: tuple[str, ...],
    right_identities: tuple[tuple[int, int, int], ...],
    right_remaining: tuple[str, ...],
    expected: bool,
):
    assert (
        operator_profile._identity_mappings_overlap(
            left_identities=left_identities,
            left_remaining=left_remaining,
            right_identities=right_identities,
            right_remaining=right_remaining,
        )
        is expected
    )


@pytest.mark.parametrize("alias_case", ("same", "parent_child", "state_parent"))
def test_windows_drive_unc_aliases_cannot_bypass_root_disjointness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alias_case: str,
):
    local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    if alias_case == "same":
        requested_runtime = runtime_root
        requested_output = _administrative_share_alias_or_skip(runtime_root)
    elif alias_case == "parent_child":
        physical_parent = tmp_path / "physical-parent"
        physical_child = physical_parent / "child"
        physical_child.mkdir(parents=True)
        requested_runtime = physical_parent
        requested_output = _administrative_share_alias_or_skip(physical_child)
    else:
        requested_runtime = _administrative_share_alias_or_skip(local_app_data)
        requested_output = output_base_root
    state_root = local_app_data / "HSConfig"
    assert tuple(local_app_data.iterdir()) == ()

    with pytest.raises(ValueError, match="overlap"):
        enable_operator_profile(
            runtime_root=requested_runtime,
            output_base_root=requested_output,
            expected_predecessor_sha256=None,
        )

    assert tuple(local_app_data.iterdir()) == ()
    assert not state_root.exists()


@pytest.mark.parametrize("authority", ("runtime_root", "output_base_root", "localappdata"))
@pytest.mark.parametrize("unsafe_path", UNC_IPC_NAMESPACE_PATHS)
def test_unc_ipc_authorities_reject_before_profile_state_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority: str,
    unsafe_path: str,
):
    if os.name != "nt":
        pytest.skip("UNC IPC namespaces are Windows-specific")
    local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    if authority == "runtime_root":
        runtime_root = Path(unsafe_path)
    elif authority == "output_base_root":
        output_base_root = Path(unsafe_path)
    else:
        monkeypatch.setenv("LOCALAPPDATA", unsafe_path)

    with pytest.raises(ValueError, match="namespace"):
        _enable(runtime_root, output_base_root)

    assert tuple(local_app_data.iterdir()) == ()


def test_physical_identity_mapping_bounds_missing_tail_traversal(
    tmp_path: Path,
):
    missing_at_limit = tmp_path.joinpath(*(["missing"] * 256))
    _identities, remaining = operator_profile._physical_identity_mapping(
        missing_at_limit
    )
    assert len(remaining) == 256
    with pytest.raises(ValueError, match="bound"):
        operator_profile._physical_identity_mapping(missing_at_limit / "overflow")


def test_physical_identity_mapping_bounds_existing_ancestor_traversal(
    tmp_path: Path,
):
    base_rows = 1
    base = tmp_path
    while base.parent != base:
        base_rows += 1
        base = base.parent
    existing_at_limit = tmp_path
    for _ in range(256 - base_rows):
        existing_at_limit /= "d"
        existing_at_limit.mkdir()
    identities, remaining = operator_profile._physical_identity_mapping(
        existing_at_limit
    )
    assert len(identities) == 256
    assert remaining == ()

    existing_over_limit = existing_at_limit / "d"
    existing_over_limit.mkdir()
    with pytest.raises(ValueError, match="bound"):
        operator_profile._physical_identity_mapping(existing_over_limit)


def test_profile_observation_registry_is_weak_identity_bound_and_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _local_app_data, runtime_root, output_base_root = _layout(tmp_path, monkeypatch)
    profile = _enable(runtime_root, output_base_root)
    with operator_profile._profile_observations_lock:
        baseline_size = len(operator_profile._profile_observations)

    for _ in range(25):
        assert revalidate_operator_profile(profile) is profile
    gc.collect()
    with operator_profile._profile_observations_lock:
        assert len(operator_profile._profile_observations) == baseline_size

    forged = operator_profile.OperatorProfile(
        schema_version=profile.schema_version,
        live_by_default=profile.live_by_default,
        runtime_root=profile.runtime_root,
        runtime_root_identity=profile.runtime_root_identity,
        output_base_root=profile.output_base_root,
        output_base_root_identity=profile.output_base_root_identity,
        content_sha256=profile.content_sha256,
    )
    assert forged == profile and forged is not profile
    for unbound in (forged, copy.copy(profile), pickle.loads(pickle.dumps(profile))):
        with pytest.raises(ValueError, match="unbound"):
            revalidate_operator_profile(unbound)

    transient = load_operator_profile()
    transient_id = id(transient)
    del transient
    gc.collect()
    with operator_profile._profile_observations_lock:
        assert transient_id not in operator_profile._profile_observations

    stale = load_operator_profile()
    disable_operator_profile(expected_predecessor_sha256=stale.content_sha256)
    with pytest.raises(ValueError):
        revalidate_operator_profile(stale)
