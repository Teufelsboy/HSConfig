from __future__ import annotations

import copy
import json
import os
import pickle
from hashlib import sha256
from pathlib import Path
from queue import Queue
from threading import Thread

import pytest

import hsconfig.output_operation_admission as admission
from hsconfig import package_io
from hsconfig.operator_profile import (
    enable_operator_profile,
    operator_profile_path,
)
from hsconfig.output_operation_admission import (
    OUTPUT_OPERATION_ADMISSION_FIELDS,
    OUTPUT_OPERATION_ADMISSION_KIND,
    OUTPUT_OPERATION_ADMISSION_NAME,
    OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME,
    OUTPUT_OPERATION_ADMISSION_SCHEMA_VERSION,
    OUTPUT_OPERATION_ADMISSION_STAGING_NAME,
    OutputOperationAdmissionLockToken,
    lease_output_operation_admission,
    observe_output_operation_admission_under_lease,
    output_operation_admission_path,
    require_output_operation_allows_profile_mutation,
    require_output_operation_allows_publication,
    require_output_operation_allows_runtime_mutation,
)
from hsconfig.package_io import path_identity


STANDARD_DIGEST = "sha256:" + ("2" * 64)
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


def _canonical(document: dict[str, object]) -> bytes:
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


def _existing_directory_at_identity_row_depth(
    parent: Path,
    target_rows: int,
) -> Path:
    current = parent
    current_rows = 1
    ancestor = current
    while ancestor.parent != ancestor:
        current_rows += 1
        ancestor = ancestor.parent
    if current_rows > target_rows:
        raise AssertionError("temporary root already exceeds requested identity depth")
    for _ in range(target_rows - current_rows):
        current /= "d"
        current.mkdir()
    return current


def _enabled_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path, object]:
    local_app_data = tmp_path / "local-app-data"
    runtime_root = tmp_path / "runtime"
    output_base_root = tmp_path / "outputs"
    local_app_data.mkdir(parents=True)
    runtime_root.mkdir()
    output_base_root.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    profile = enable_operator_profile(
        runtime_root=runtime_root,
        output_base_root=output_base_root,
        expected_predecessor_sha256=None,
    )
    return local_app_data, runtime_root, output_base_root, profile


def _admission_document(
    *, local_app_data: Path, output_base_root: Path, profile: object
) -> tuple[dict[str, object], bytes]:
    state_root = local_app_data / "HSConfig"
    session_root = local_app_data.parent / "session"
    session_root.mkdir(exist_ok=True)
    output_child = output_base_root / "deck"
    bootstrap_lock = state_root / "locks" / "output-child-test.lock"
    bootstrap_lock.touch(exist_ok=True)
    unsigned: dict[str, object] = {
        "schema_version": OUTPUT_OPERATION_ADMISSION_SCHEMA_VERSION,
        "record_kind": OUTPUT_OPERATION_ADMISSION_KIND,
        "state": "ACTIVE",
        "run_id": "b" * 32,
        "session_root": str(session_root.resolve()),
        "session_root_identity": list(path_identity(session_root)),
        "expected_session_sha256": STANDARD_DIGEST,
        "operator_profile_path": str(operator_profile_path().resolve()),
        "operator_profile_parent_identity": list(path_identity(state_root)),
        "operator_profile_identity": list(path_identity(operator_profile_path())),
        "operator_profile_sha256": profile.content_sha256,
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
    digest = "sha256:" + sha256(_canonical(unsigned)).hexdigest()
    document = {**unsigned, "content_sha256": digest}
    return document, _canonical(document)


def test_output_operation_admission_fixed_path_schema_and_observation_are_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_app_data, _runtime_root, output_base_root, profile = _enabled_layout(
        tmp_path, monkeypatch
    )
    state_root = local_app_data / "HSConfig"
    document, raw = _admission_document(
        local_app_data=local_app_data,
        output_base_root=output_base_root,
        profile=profile,
    )
    path = output_operation_admission_path()
    path.write_bytes(raw)

    assert path == state_root / OUTPUT_OPERATION_ADMISSION_NAME
    assert set(document) == OUTPUT_OPERATION_ADMISSION_FIELDS
    with lease_output_operation_admission() as lease:
        observed = observe_output_operation_admission_under_lease(lease)
        assert observed is not None
        assert observed.admission_path == path
        assert observed.admission_sha256 == document["content_sha256"]
        assert observed.run_id == "b" * 32
        assert observed.state == "ACTIVE"
        assert observed.output_base_root == output_base_root.resolve()

    document["extra"] = True
    unsigned = dict(document)
    unsigned.pop("content_sha256")
    document["content_sha256"] = "sha256:" + sha256(_canonical(unsigned)).hexdigest()
    path.write_bytes(_canonical(document))
    with lease_output_operation_admission() as lease:
        with pytest.raises(ValueError, match="fields"):
            observe_output_operation_admission_under_lease(lease)


def test_admission_ads_is_rejected_before_authority_bytes_are_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data, _runtime_root, output_base_root, profile = _enabled_layout(
        tmp_path,
        monkeypatch,
    )
    _document, raw = _admission_document(
        local_app_data=local_app_data,
        output_base_root=output_base_root,
        profile=profile,
    )
    path = output_operation_admission_path()
    path.write_bytes(raw)
    stream_path = _create_ntfs_stream_or_skip(path)
    before = (path_identity(path), path.read_bytes(), stream_path.read_bytes())
    read_calls: list[Path] = []
    real_read = admission.read_file_no_follow

    def observed_read(candidate: Path, **kwargs: object) -> bytes:
        read_calls.append(Path(candidate))
        return real_read(candidate, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(admission, "read_file_no_follow", observed_read)
    with lease_output_operation_admission() as lease:
        with pytest.raises(
            ValueError,
            match="^filesystem_alternate_data_stream_forbidden$",
        ):
            observe_output_operation_admission_under_lease(lease)

    assert read_calls == []
    assert (path_identity(path), path.read_bytes(), stream_path.read_bytes()) == before


def test_output_operation_admission_observation_is_read_only_and_never_bootstraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    state_root = local_app_data / "HSConfig"

    with pytest.raises(FileNotFoundError):
        with lease_output_operation_admission():
            pass
    assert not state_root.exists()

    local_app_data, _runtime_root, _output_base_root, _profile = _enabled_layout(
        tmp_path / "enabled", monkeypatch
    )
    state_root = local_app_data / "HSConfig"
    lock_path = state_root / "locks" / "output-operation.lock"
    initial = (
        lock_path.read_bytes(),
        path_identity(lock_path),
        lock_path.stat().st_mtime_ns,
        state_root.stat().st_mtime_ns,
    )
    with lease_output_operation_admission() as lease:
        assert observe_output_operation_admission_under_lease(lease) is None
        assert observe_output_operation_admission_under_lease(lease) is None
    assert (
        lock_path.read_bytes(),
        path_identity(lock_path),
        lock_path.stat().st_mtime_ns,
        state_root.stat().st_mtime_ns,
    ) == initial
    assert not output_operation_admission_path().exists()
    assert not (state_root / OUTPUT_OPERATION_ADMISSION_STAGING_NAME).exists()
    assert not (state_root / OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME).exists()


def test_neutral_lease_entries_reject_over_limit_state_root_before_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    depth_base = tmp_path / "over-limit-neutral-state"
    depth_base.mkdir()
    local_app_data = _existing_directory_at_identity_row_depth(depth_base, 256)
    state_root = local_app_data / "HSConfig"
    state_root.mkdir()
    state_root_identity = path_identity(state_root)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    boundary_events: list[tuple[str, Path]] = []
    real_require_no_streams = admission.require_no_alternate_data_streams
    real_open_directory = package_io._open_plain_directory_descriptor

    def record_ads_traversal(path: Path, **kwargs: object) -> None:
        candidate = Path(path)
        if candidate == state_root:
            boundary_events.append(("ads", candidate))
        real_require_no_streams(path, **kwargs)

    def record_held_chain(path: Path, *args: object, **kwargs: object) -> int:
        candidate = Path(path)
        if candidate == local_app_data:
            boundary_events.append(("held_chain", candidate))
        return real_open_directory(path, *args, **kwargs)

    monkeypatch.setattr(
        admission,
        "require_no_alternate_data_streams",
        record_ads_traversal,
    )
    monkeypatch.setattr(
        package_io,
        "_open_plain_directory_descriptor",
        record_held_chain,
    )

    def public_lease() -> None:
        with lease_output_operation_admission():
            pass

    def bound_lease() -> None:
        with admission._lease_output_operation_admission_for_state_root(
            state_root=state_root,
            state_root_identity=state_root_identity,
        ):
            pass

    for entry_name, entry in (("public", public_lease), ("bound", bound_lease)):
        boundary_events.clear()
        outcome: BaseException | None = None
        try:
            entry()
        except BaseException as error:
            outcome = error
        assert boundary_events == [], entry_name
        assert isinstance(outcome, ValueError), entry_name
        assert "bound" in str(outcome), entry_name


def test_output_operation_admission_lease_is_thread_bound_and_expires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _enabled_layout(tmp_path, monkeypatch)
    cross_thread: Queue[BaseException | None] = Queue()

    with lease_output_operation_admission() as lease:
        require_output_operation_allows_runtime_mutation(lease=lease)
        with pytest.raises(TypeError):
            OutputOperationAdmissionLockToken()
        with pytest.raises(TypeError):
            copy.copy(lease.lock_token)
        with pytest.raises(TypeError):
            pickle.dumps(lease.lock_token)

        def use_cross_thread() -> None:
            try:
                require_output_operation_allows_runtime_mutation(lease=lease)
            except BaseException as error:
                cross_thread.put(error)
            else:
                cross_thread.put(None)

        thread = Thread(target=use_cross_thread)
        thread.start()
        thread.join(timeout=5)
        assert isinstance(cross_thread.get_nowait(), ValueError)

    with pytest.raises(ValueError, match="inactive"):
        require_output_operation_allows_runtime_mutation(lease=lease)


def test_runtime_mutation_gate_allows_only_absent_fixed_output_operation_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_app_data, _runtime_root, _output_base_root, _profile = _enabled_layout(
        tmp_path, monkeypatch
    )
    state_root = local_app_data / "HSConfig"

    with lease_output_operation_admission() as lease:
        assert require_output_operation_allows_runtime_mutation(lease=lease) is None
        assert require_output_operation_allows_runtime_mutation(lease=lease) is None

    assert not (state_root / OUTPUT_OPERATION_ADMISSION_NAME).exists()
    assert not (state_root / OUTPUT_OPERATION_ADMISSION_STAGING_NAME).exists()
    assert not (state_root / OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME).exists()


def test_runtime_mutation_gate_rejects_final_staging_temp_malformed_or_replaced_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    local_app_data, _runtime_root, output_base_root, profile = _enabled_layout(
        tmp_path, monkeypatch
    )
    state_root = local_app_data / "HSConfig"
    final_path = state_root / OUTPUT_OPERATION_ADMISSION_NAME
    _document, valid = _admission_document(
        local_app_data=local_app_data,
        output_base_root=output_base_root,
        profile=profile,
    )

    final_path.write_bytes(valid)
    with lease_output_operation_admission() as lease:
        with pytest.raises(ValueError, match="output_operation"):
            require_output_operation_allows_runtime_mutation(lease=lease)
    final_path.unlink()

    final_path.write_bytes(b"{}")
    with lease_output_operation_admission() as lease:
        with pytest.raises(ValueError):
            require_output_operation_allows_runtime_mutation(lease=lease)
    final_path.unlink()

    for name in (
        OUTPUT_OPERATION_ADMISSION_STAGING_NAME,
        OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME,
    ):
        residue = state_root / name
        residue.write_bytes(b"residue")
        with lease_output_operation_admission() as lease:
            with pytest.raises(ValueError, match="output_operation"):
                require_output_operation_allows_runtime_mutation(lease=lease)
        residue.unlink()

    final_path.write_bytes(valid)
    real_read = admission.read_file_no_follow

    def replace_before_read(
        path: Path, *, expected_status: os.stat_result, maximum_size: int
    ) -> bytes:
        replacement = path.with_name("replacement.json")
        replacement.write_bytes(valid)
        os.replace(replacement, path)
        return real_read(
            path,
            expected_status=expected_status,
            maximum_size=maximum_size,
        )

    monkeypatch.setattr(admission, "read_file_no_follow", replace_before_read)
    with lease_output_operation_admission() as lease:
        with pytest.raises(ValueError, match="identity"):
            require_output_operation_allows_runtime_mutation(lease=lease)


def test_public_output_operation_observation_never_creates_reserved_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    local_app_data = tmp_path / "local-app-data"
    state_root = local_app_data / "HSConfig"
    locks_root = state_root / "locks"
    locks_root.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    lock_path = locks_root / "output-operation.lock"
    before = (
        path_identity(state_root),
        path_identity(locks_root),
        state_root.stat().st_mtime_ns,
        locks_root.stat().st_mtime_ns,
        tuple(state_root.iterdir()),
        tuple(locks_root.iterdir()),
    )

    with pytest.raises(TypeError):
        with lease_output_operation_admission(create_if_missing=True):
            pass
    with pytest.raises(FileNotFoundError):
        with lease_output_operation_admission():
            pass
    for operation in (
        lambda: observe_output_operation_admission_under_lease(None),
        lambda: require_output_operation_allows_profile_mutation(None),
        lambda: require_output_operation_allows_runtime_mutation(lease=None),
        lambda: require_output_operation_allows_publication(
            lease=None,
            output_root=tmp_path / "output",
            output_root_identity=None,
        ),
    ):
        with pytest.raises(ValueError):
            operation()

    assert not lock_path.exists()
    assert (
        path_identity(state_root),
        path_identity(locks_root),
        state_root.stat().st_mtime_ns,
        locks_root.stat().st_mtime_ns,
        tuple(state_root.iterdir()),
        tuple(locks_root.iterdir()),
    ) == before


@pytest.mark.parametrize(
    "path_field",
    (
        "session_root",
        "operator_profile_path",
        "output_base_root",
        "output_child_path",
        "output_bootstrap_lock_path",
        "output_claim_path",
    ),
)
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
def test_output_operation_admission_rejects_unsafe_windows_namespace_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_field: str,
    unsafe_component: str,
):
    local_app_data, _runtime_root, output_base_root, profile = _enabled_layout(
        tmp_path, monkeypatch
    )
    document, _raw = _admission_document(
        local_app_data=local_app_data,
        output_base_root=output_base_root,
        profile=profile,
    )
    document[path_field] = str(tmp_path / unsafe_component)
    unsigned = dict(document)
    unsigned.pop("content_sha256")
    document["content_sha256"] = "sha256:" + sha256(_canonical(unsigned)).hexdigest()
    output_operation_admission_path().write_bytes(_canonical(document))

    with lease_output_operation_admission() as lease:
        with pytest.raises(ValueError, match="namespace"):
            observe_output_operation_admission_under_lease(lease)


@pytest.mark.parametrize("unsafe_component", SUPERSCRIPT_DOS_DEVICE_COMPONENTS)
def test_windows_namespace_validator_rejects_superscript_dos_devices(
    tmp_path: Path,
    unsafe_component: str,
):
    if os.name != "nt":
        pytest.skip("Win32 device aliases are Windows-specific")
    with pytest.raises(ValueError, match="namespace"):
        admission._require_windows_safe_absolute_path(
            tmp_path / unsafe_component,
            error="windows_namespace_invalid",
        )


@pytest.mark.parametrize("unsafe_path", UNC_IPC_NAMESPACE_PATHS)
def test_windows_namespace_validator_rejects_unc_ipc_shares(
    unsafe_path: str,
):
    if os.name != "nt":
        pytest.skip("UNC IPC namespaces are Windows-specific")
    with pytest.raises(ValueError, match="namespace"):
        admission._require_windows_safe_absolute_path(
            Path(unsafe_path),
            error="windows_namespace_invalid",
        )


@pytest.mark.parametrize(
    "ordinary_path",
    (
        "\\\\server\\ordinary-share\\authority",
        "\\\\server\\C$\\authority",
        "\\\\server\\ADMIN$\\authority",
        "\\\\server\\ordinary-share",
        "\\\\server\\C$",
        "\\\\server\\ADMIN$",
    ),
)
def test_windows_namespace_validator_preserves_ordinary_unc_shares(
    ordinary_path: str,
):
    if os.name != "nt":
        pytest.skip("UNC namespaces are Windows-specific")
    candidate = Path(ordinary_path)
    assert (
        admission._require_windows_safe_absolute_path(
            candidate,
            error="windows_namespace_invalid",
        )
        == candidate
    )


@pytest.mark.parametrize(
    ("candidate_path", "accepted"),
    (
        ("\\\\COM1\\ordinary-share\\authority", True),
        ("\\\\server\\CON\\authority", True),
        ("\\\\NUL\\COM1.txt\\ordinary", True),
        ("\\\\COM1\\CON", True),
        ("\\\\NUL\\COM1.txt", True),
        ("\\\\COM1\\ordinary-share\\CON", False),
        ("\\\\server\\CON\\COM1.txt", False),
        ("\\\\server\\ordinary-share\\LPT¹", False),
        ("\\\\COM1\\PiPe\\authority", False),
    ),
)
def test_windows_namespace_validator_applies_device_rules_only_after_unc_share(
    candidate_path: str,
    accepted: bool,
):
    if os.name != "nt":
        pytest.skip("UNC namespaces are Windows-specific")
    candidate = Path(candidate_path)
    if accepted:
        assert (
            admission._require_windows_safe_absolute_path(
                candidate,
                error="windows_namespace_invalid",
            )
            == candidate
        )
    else:
        with pytest.raises(ValueError, match="namespace"):
            admission._require_windows_safe_absolute_path(
                candidate,
                error="windows_namespace_invalid",
            )


@pytest.mark.parametrize(
    "surface",
    ("admission", "staging", "reserved_temp"),
)
def test_output_operation_admission_rejects_ntfs_alternate_data_streams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
):
    local_app_data, _runtime_root, output_base_root, profile = _enabled_layout(
        tmp_path, monkeypatch
    )
    _document, raw = _admission_document(
        local_app_data=local_app_data,
        output_base_root=output_base_root,
        profile=profile,
    )
    state_root = local_app_data / "HSConfig"
    surfaces = {
        "admission": output_operation_admission_path(),
        "staging": state_root / OUTPUT_OPERATION_ADMISSION_STAGING_NAME,
        "reserved_temp": state_root / OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME,
    }
    authority_path = surfaces[surface]
    if surface == "admission":
        authority_path.write_bytes(raw)
    else:
        authority_path.touch()
    stream_path = _create_ntfs_stream_or_skip(authority_path)
    try:
        with lease_output_operation_admission() as lease:
            with pytest.raises(ValueError, match="alternate_data_stream"):
                observe_output_operation_admission_under_lease(lease)
    finally:
        stream_path.unlink(missing_ok=True)


def test_output_operation_admission_is_fixed_absent_cas_and_profile_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threading import Event

    from hsconfig.operator_profile import lease_operator_profile, load_operator_profile
    from tests.test_configure_prepublication_apply import (
        _drive_pipeline,
        _physical_tree,
        _prepare_pipeline,
    )

    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    profile = load_operator_profile()
    contender_started = Event()
    contender_acquired = Event()
    contender: Thread | None = None
    observations: list[str] = []

    def compete_for_profile() -> None:
        contender_started.set()
        with lease_operator_profile(expected_profile=profile):
            contender_acquired.set()

    def observe(event: str, _payload: object | None = None) -> None:
        nonlocal contender
        if event == "output_operation_admission_prepared_cas":
            persisted = json.loads(
                (prepared.session_root / "session.json").read_bytes()
            )
            assert persisted["pending_transition"]["operation"] == (
                "install_output_operation_admission"
            )
            assert not output_operation_admission_path().exists()
            contender = Thread(target=compete_for_profile)
            contender.start()
            assert contender_started.wait(5)
            assert not contender_acquired.wait(0.1)
            observations.append("prepared-before-final")
        elif event == "output_operation_admission_bound_cas":
            assert output_operation_admission_path().is_file()
            observations.append("bound-after-final")

    monkeypatch.setattr(
        __import__("hsconfig.live_start_controller", fromlist=["*"]),
        "_emit_pipeline_event",
        observe,
    )
    before_runtime = _physical_tree(prepared.runtime_root)
    completed = _drive_pipeline(prepared)
    assert observations == ["prepared-before-final", "bound-after-final"]
    binding = completed.output_operation_admission_binding
    raw = output_operation_admission_path().read_bytes()
    document = json.loads(raw)
    assert set(document) == OUTPUT_OPERATION_ADMISSION_FIELDS
    assert document["operator_profile_sha256"] == profile.content_sha256
    assert binding["admission_identity"] == path_identity(
        output_operation_admission_path()
    )
    assert binding["admission_sha256"] == "sha256:" + sha256(raw).hexdigest()
    assert _physical_tree(prepared.runtime_root) == before_runtime
    assert contender is not None
    contender.join(5)
    assert contender_acquired.is_set()


def test_unbound_staging_and_direct_final_are_delete_only_or_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_configure_prepublication_apply import (
        _drive_pipeline,
        _interrupt_pipeline,
        _prepare_pipeline,
    )

    unbound = _prepare_pipeline(tmp_path / "unbound", monkeypatch)
    interrupted = _interrupt_pipeline(
        unbound,
        "AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS",
    )
    pending = interrupted.pending_transition
    final = Path(pending["external_file_action"]["final_path"])
    staging = Path(pending["external_file_action"]["staging_path"])
    assert staging.is_file()
    assert not final.exists()
    completed = _drive_pipeline(unbound, expected=interrupted)
    assert completed.output_operation_admission_binding["state"] == "ACTIVE"
    assert final.is_file()
    assert not staging.exists()

    direct = _prepare_pipeline(tmp_path / "direct-final", monkeypatch)
    interrupted = _interrupt_pipeline(
        direct,
        "AFTER_OUTPUT_OPERATION_ADMISSION_PREPARED",
    )
    final = Path(interrupted.pending_transition["external_file_action"]["final_path"])
    final.write_bytes(b"foreign-direct-final")
    with pytest.raises(ValueError, match="final|tamper|admission"):
        _drive_pipeline(direct, expected=interrupted)
    assert final.read_bytes() == b"foreign-direct-final"
