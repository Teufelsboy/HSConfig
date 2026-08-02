from __future__ import annotations

import errno
import json
import os
import stat
import threading
import time
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from hsconfig.configure_run_model import (
    RenderedConfigureRun,
)
import hsconfig.current_output as current_output_module
from hsconfig.current_output import resolve_current_package
from hsconfig.output_publisher import publish_configure_run
from tests.test_output_publisher import (
    rendered_runs_fixture as _rendered_runs_fixture,  # noqa: F401
)


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


def _publish(
    tmp_path: Path,
    rendered: RenderedConfigureRun,
) -> tuple[Path, Path]:
    output_root = tmp_path / "ShadowPriest"
    published = publish_configure_run(rendered, output_root)
    return output_root, published.package_root


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


def test_resolver_returns_only_verified_current_package(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root, package_root = _publish(tmp_path, rendered_runs[0])
    assert resolve_current_package(output_root) == package_root


def test_windows_resolver_accepts_same_identity_short_path_alias(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    if os.name != "nt":
        pytest.skip("Windows 8.3 path alias regression")
    import ctypes
    from ctypes import wintypes

    from hsconfig.package_io import path_identity

    long_parent = tmp_path / "Long Current Output Ancestor For Alias"
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

    output_root = alias_parent / "ShadowPriest"
    published = publish_configure_run(rendered_runs[0], output_root)

    resolved = resolve_current_package(output_root)

    assert path_identity(resolved) == path_identity(
        published.package_root
    )


def test_same_identity_resolution_rejects_expected_status_from_other_path(
    tmp_path: Path,
) -> None:
    from hsconfig.package_io import require_same_identity_resolution

    expected = tmp_path / "expected"
    candidate = tmp_path / "candidate"
    expected.mkdir()
    candidate.mkdir()

    with pytest.raises(
        ValueError,
        match="filesystem_path_resolution_changed",
    ):
        require_same_identity_resolution(
            candidate,
            expected_status=expected.lstat(),
        )


def test_same_identity_resolution_rejects_windows_reparse_attribute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig.package_io import require_same_identity_resolution

    candidate = tmp_path / "reparse-candidate"
    reparse_status = SimpleNamespace(
        st_mode=stat.S_IFDIR,
        st_dev=1,
        st_ino=2,
        st_file_attributes=getattr(
            stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x0400,
        ),
    )

    with monkeypatch.context() as patch:
        patch.setattr(
            Path,
            "lstat",
            lambda self: reparse_status,
        )
        patch.setattr(
            Path,
            "resolve",
            lambda self, strict=False: pytest.fail(
                "reparse point must be rejected before resolution"
            ),
        )
        with pytest.raises(
            ValueError,
            match="filesystem_path_resolution_changed",
        ):
            require_same_identity_resolution(candidate)


def test_same_identity_resolution_rejects_symlink(
    tmp_path: Path,
) -> None:
    from hsconfig.package_io import require_same_identity_resolution

    target = tmp_path / "target"
    alias = tmp_path / "alias"
    target.mkdir()
    _make_symlink(
        target,
        alias,
        target_is_directory=True,
    )

    with pytest.raises(
        ValueError,
        match="filesystem_path_resolution_changed",
    ):
        require_same_identity_resolution(alias)


@pytest.mark.parametrize(
    "revision",
    (
        "../outside",
        "revisions/../outside",
        "revisions/sha256-" + "0" * 64 + "/extra",
    ),
)
def test_resolver_rejects_pointer_traversal(
    tmp_path: Path,
    revision: str,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root, _ = _publish(tmp_path, rendered_runs[0])
    payload = json.loads((output_root / "current.json").read_bytes())
    payload["revision"] = revision
    (output_root / "current.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="current_output_invalid"):
        resolve_current_package(output_root)


def test_resolver_rejects_manifest_tampering(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root, package_root = _publish(tmp_path, rendered_runs[0])
    (package_root / "reports" / "deck_identity.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="current_output_invalid"):
        resolve_current_package(output_root)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda content: content.replace(b"\n", b"\r\n"),
        lambda content: content[:-1],
        lambda content: content.replace(
            b"{\n",
            b'{\n  "deck_name": "duplicate",\n',
            1,
        ),
        lambda content: content.replace(
            b"{\n",
            b'{\n  "unknown": 1,\n',
            1,
        ),
    ),
    ids=("crlf", "missing-final-lf", "duplicate-key", "unknown-key"),
)
def test_resolver_requires_exact_canonical_pointer_bytes(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
    mutate: object,
) -> None:
    output_root, _ = _publish(tmp_path, rendered_runs[0])
    pointer = output_root / "current.json"
    pointer.write_bytes(mutate(pointer.read_bytes()))  # type: ignore[operator]
    with pytest.raises(ValueError, match="current_output_invalid"):
        resolve_current_package(output_root)


def test_resolver_rejects_casefold_second_current_claim(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root, _ = _publish(tmp_path, rendered_runs[0])
    alias = output_root / "CURRENT.JSON"
    try:
        alias.write_bytes((output_root / "current.json").read_bytes())
    except OSError:
        pytest.skip("filesystem is case-insensitive")
    if alias.samefile(output_root / "current.json"):
        pytest.skip("filesystem is case-insensitive")
    with pytest.raises(ValueError, match="current_output_invalid"):
        resolve_current_package(output_root)


def test_resolver_rejects_extra_unmanifested_physical_file(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root, package_root = _publish(tmp_path, rendered_runs[0])
    (package_root.parent / "extra.bin").write_bytes(b"extra")
    with pytest.raises(ValueError, match="current_output_invalid"):
        resolve_current_package(output_root)


def test_resolver_rejects_hardlinked_revision_file(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root, package_root = _publish(tmp_path, rendered_runs[0])
    source = package_root / "reports" / "deck_identity.json"
    alias = tmp_path / "external-hardlink.json"
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("hard links unavailable")
    with pytest.raises(ValueError, match="current_output_invalid"):
        resolve_current_package(output_root)


def test_resolver_rejects_reparse_revision_root(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root, package_root = _publish(tmp_path, rendered_runs[0])
    revision_root = package_root.parent
    real_root = output_root / "revisions" / "moved-revision"
    revision_root.rename(real_root)
    try:
        _make_symlink(
            real_root,
            revision_root,
            target_is_directory=True,
        )
    except pytest.skip.Exception:
        real_root.rename(revision_root)
        raise
    with pytest.raises(ValueError, match="current_output_invalid"):
        resolve_current_package(output_root)


def test_resolver_rejects_empty_unmanifested_directory(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root, package_root = _publish(tmp_path, rendered_runs[0])
    (package_root.parent / "unmanifested-empty").mkdir()
    with pytest.raises(ValueError, match="current_output_invalid"):
        resolve_current_package(output_root)


def test_reconcile_dangling_current_symlink_mutates_nothing(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from hsconfig.output_publisher import reconcile_output

    output_root, package_root = _publish(tmp_path, rendered_runs[0])
    pointer = output_root / "current.json"
    pointer.unlink()
    _make_symlink(
        tmp_path / "missing-pointer",
        pointer,
        target_is_directory=False,
    )
    journals = tuple(
        (output_root / ".publisher" / "transactions").iterdir()
    )

    with pytest.raises(ValueError):
        reconcile_output(output_root)
    assert package_root.parent.is_dir()
    assert tuple(
        (output_root / ".publisher" / "transactions").iterdir()
    ) == journals


def test_resolver_runs_strict_package_semantics_after_manifest_verification(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from hsconfig.current_output import (
        OutputPublication,
        output_publication_bytes,
    )

    output_root, package_root = _publish(tmp_path, rendered_runs[0])
    revision = package_root.parent
    manifest_path = revision / "package_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    removed = "04_package/reports/globalvalues_baseline.json"
    (revision / removed).unlink()
    manifest["entries"] = [
        row
        for row in manifest["entries"]
        if row["relative_path"] != removed
    ]
    records = b"".join(
        (
            f"{row['relative_path']}\0{row['size']}\0"
            f"{row['sha256']}\n"
        ).encode("utf-8")
        for row in manifest["entries"]
    )
    root_sha256 = hashlib.sha256(records).hexdigest()
    manifest["content_root_sha256"] = root_sha256
    manifest_path.write_bytes(
        (
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    )
    renamed = revision.with_name(f"sha256-{root_sha256}")
    revision.rename(renamed)
    (output_root / "current.json").write_bytes(
        output_publication_bytes(
            OutputPublication(
                schema_version=1,
                deck_name=manifest["deck_name"],
                deck_fingerprint=manifest["deck_fingerprint"],
                revision=f"revisions/{renamed.name}",
                content_root_sha256=root_sha256,
            )
        )
    )

    with pytest.raises(ValueError, match="current_output_invalid"):
        resolve_current_package(output_root)


def test_resolver_holds_publish_lock_for_point_in_time_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    import hsconfig.current_output as current_output

    output_root, old_package = _publish(tmp_path, rendered_runs[0])
    entered = threading.Event()
    release = threading.Event()
    original = current_output.resolve_current_publication_unlocked

    def blocked(root: Path) -> object:
        entered.set()
        assert release.wait(10)
        return original(root)

    monkeypatch.setattr(
        current_output,
        "resolve_current_publication_unlocked",
        blocked,
    )
    resolved: list[Path] = []
    resolver = threading.Thread(
        target=lambda: resolved.append(resolve_current_package(output_root))
    )
    publisher_done = threading.Event()
    publisher = threading.Thread(
        target=lambda: (
            publish_configure_run(rendered_runs[1], output_root),
            publisher_done.set(),
        )
    )
    resolver.start()
    assert entered.wait(10)
    publisher.start()
    time.sleep(0.1)
    assert not publisher_done.is_set()
    assert old_package.is_dir()
    release.set()
    resolver.join(20)
    publisher.join(20)
    assert not resolver.is_alive()
    assert not publisher.is_alive()
    assert resolved == [old_package]


def test_package_input_lease_blocks_publisher_for_entire_consumer_lifetime(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    lease_package_input = getattr(
        current_output_module,
        "lease_package_input",
        None,
    )
    assert callable(lease_package_input)
    output_root, old_package = _publish(tmp_path, rendered_runs[0])
    publisher_done = threading.Event()
    published_packages: list[Path] = []

    with lease_package_input(output_root) as lease:
        publisher = threading.Thread(
            target=lambda: (
                published_packages.append(
                    publish_configure_run(
                        rendered_runs[1],
                        output_root,
                    ).package_root
                ),
                publisher_done.set(),
            )
        )
        publisher.start()
        time.sleep(0.1)

        assert lease.package_root == old_package
        assert lease.publication is not None
        assert (
            lease.content_root_sha256
            == lease.publication.content_root_sha256
        )
        assert not publisher_done.is_set()
        assert old_package.is_dir()

    publisher.join(20)
    assert not publisher.is_alive()
    assert publisher_done.is_set()
    assert len(published_packages) == 1


def test_package_input_lease_preserves_direct_package_compatibility(
    tmp_path: Path,
) -> None:
    lease_package_input = getattr(
        current_output_module,
        "lease_package_input",
        None,
    )
    assert callable(lease_package_input)
    package_root = tmp_path / "04_package"
    package_root.mkdir()

    with lease_package_input(package_root) as lease:
        assert lease.package_root == package_root
        assert lease.publication is None
        assert lease.content_root_sha256 is None
        assert lease.output_root is None


def test_package_input_lease_rejects_existing_non_plain_candidate(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "not-a-package-directory"
    candidate.write_bytes(b"not a directory")
    leased_as_direct = False

    with pytest.raises(ValueError, match="current_output_invalid"):
        with current_output_module.lease_package_input(candidate) as lease:
            leased_as_direct = lease.publication is None
            raise AssertionError(
                "existing non-plain candidate was leased as direct"
            )

    assert leased_as_direct is False


def test_package_input_lease_preserves_consumer_exception_when_exit_guard_fails(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, _package_root = _publish(tmp_path, rendered_runs[0])

    class FailingExitGuard:
        def __init__(self) -> None:
            self.calls = 0

        def validate(self) -> None:
            self.calls += 1
            if self.calls == 3:
                raise ValueError("lease_guard_changed")

    monkeypatch.setattr(
        current_output_module,
        "capture_plain_ancestor_guard",
        lambda _path: FailingExitGuard(),
    )

    with pytest.raises(RuntimeError, match="consumer_failure") as captured:
        with current_output_module.lease_package_input(output_root):
            raise RuntimeError("consumer_failure")

    assert "lease_guard_changed" in "\n".join(captured.value.__notes__)


def test_package_input_lease_rejects_corrupt_output_without_direct_fallback(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    lease_package_input = getattr(
        current_output_module,
        "lease_package_input",
        None,
    )
    assert callable(lease_package_input)
    output_root, _package_root = _publish(tmp_path, rendered_runs[0])
    direct_fallback = output_root / "04_package"
    direct_fallback.mkdir()
    (output_root / "current.json").write_bytes(b"{}\n")

    with pytest.raises(ValueError, match="current_output_invalid"):
        with lease_package_input(output_root):
            pytest.fail("corrupt output root must never be leased")


@pytest.mark.parametrize(
    "marker_kind",
    (
        ".publish.lock",
        ".PUBLISH.LOCK",
        ".publisher",
        ".PUBLISHER",
        "revisions",
        "REVISIONS",
        "CURRENT.JSON",
    ),
)
def test_package_input_lease_treats_any_publication_marker_as_output_root(
    tmp_path: Path,
    marker_kind: str,
) -> None:
    lease_package_input = getattr(
        current_output_module,
        "lease_package_input",
        None,
    )
    assert callable(lease_package_input)
    candidate = tmp_path / marker_kind.replace(".", "marker")
    (candidate / "04_package").mkdir(parents=True)
    marker = candidate / marker_kind
    if marker_kind.casefold() in {".publisher", "revisions"}:
        marker.mkdir()
    else:
        marker.write_bytes(b"{}\n")

    with pytest.raises(ValueError, match="current_output_invalid"):
        with lease_package_input(candidate):
            pytest.fail("publication marker must force output-root handling")


def test_lease_rejects_exit_guard_change_without_consumer_failure(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, _package_root = _publish(tmp_path, rendered_runs[0])

    class FailingExitGuard:
        def __init__(self) -> None:
            self.calls = 0

        def validate(self) -> None:
            self.calls += 1
            if self.calls == 3:
                raise ValueError("lease_guard_changed")

    monkeypatch.setattr(
        current_output_module,
        "capture_plain_ancestor_guard",
        lambda _path: FailingExitGuard(),
    )

    with pytest.raises(ValueError, match="lease_guard_changed"):
        with current_output_module.lease_package_input(output_root):
            pass


def test_resolve_current_package_rejects_direct_package_compatibility_path(
    tmp_path: Path,
) -> None:
    direct_package = tmp_path / "04_package"
    direct_package.mkdir()

    with pytest.raises(ValueError, match="current_output_invalid"):
        resolve_current_package(direct_package)


def test_resolver_rejects_pointer_identity_mismatch(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    from dataclasses import replace

    output_root, _package_root = _publish(tmp_path, rendered_runs[0])
    pointer = output_root / "current.json"
    publication = current_output_module.parse_output_publication(
        pointer.read_bytes()
    )
    pointer.write_bytes(
        current_output_module.output_publication_bytes(
            replace(publication, deck_name="WrongIdentity")
        )
    )

    with pytest.raises(ValueError, match="current_output_invalid") as captured:
        resolve_current_package(output_root)

    assert isinstance(captured.value.__cause__, ValueError)
    assert isinstance(captured.value.__cause__.__cause__, ValueError)
    assert (
        str(captured.value.__cause__.__cause__)
        == "current_identity_mismatch"
    )


def test_snapshot_rejects_package_that_fails_strict_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = SimpleNamespace(directory_names=())
    manifest = SimpleNamespace()
    package = object()
    monkeypatch.setattr(
        current_output_module,
        "snapshot_bounded_filesystem_package",
        lambda _root: snapshot,
    )
    monkeypatch.setattr(
        current_output_module,
        "_verify_exact_directory_set",
        lambda observed: assert_same(snapshot, observed),
    )
    monkeypatch.setattr(
        current_output_module,
        "verify_configure_run_package",
        lambda observed: (manifest, package),
    )
    monkeypatch.setattr(
        current_output_module,
        "validate_complete_package_from_view",
        lambda observed: {"status": "failed", "errors": ["broken"]},
    )
    monkeypatch.setattr(
        current_output_module,
        "strict_validation_passed",
        lambda report: report["status"] == "passed",
    )

    with pytest.raises(
        ValueError,
        match="published_package_semantics_invalid",
    ):
        current_output_module.snapshot_and_verify_revision(tmp_path)


def assert_same(expected: object, actual: object) -> None:
    assert actual is expected


def test_current_alias_scan_enforces_output_root_entry_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "current.json").write_bytes(b"{}\n")
    monkeypatch.setattr(current_output_module, "MAX_OUTPUT_ROOT_ENTRIES", 0)

    with pytest.raises(ValueError, match="output_root_entry_limit"):
        current_output_module._reject_current_aliases(tmp_path)


def test_output_layout_marker_is_false_for_missing_candidate(
    tmp_path: Path,
) -> None:
    assert not current_output_module._has_output_layout_marker(
        tmp_path / "missing"
    )


def test_output_layout_scan_enforces_entry_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "entry").write_bytes(b"x")
    monkeypatch.setattr(current_output_module, "MAX_OUTPUT_ROOT_ENTRIES", 0)

    with pytest.raises(ValueError, match="output_root_entry_limit"):
        current_output_module._has_output_layout_marker(tmp_path)


def test_output_layout_scan_wraps_scandir_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_scandir(_path: Path) -> object:
        raise OSError("scandir failed")

    monkeypatch.setattr(current_output_module.os, "scandir", fail_scandir)

    with pytest.raises(ValueError, match="current_output_invalid") as captured:
        current_output_module._has_output_layout_marker(tmp_path)

    assert isinstance(captured.value.__cause__, OSError)
