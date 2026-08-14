from __future__ import annotations

import errno
from hashlib import sha256
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import hsconfig.package_io as package_io
from hsconfig.operator_summary import build_operator_summary_from_inputs
from hsconfig.operator_summary_inputs import load_operator_summary_inputs
from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.package_derivation_receipt import (
    verify_package_derivation_receipt_from_view,
)
from hsconfig.package_model import DirectoryPackageView
import hsconfig.package_publication as package_publication
from hsconfig.package_publication import (
    PublicationFaultPoint,
    publish_rendered_package,
)
from hsconfig.package_render_authority import render_package_authority
from tests.helpers.package_byte_contract import (
    artifact_rows_for_tree,
    content_root_sha256,
    load_fixture,
)
from tests.helpers.audited_package_request import audited_request


FIXTURE_PATH = Path("tests/fixtures/package-byte-contract-v1.json")
_DIRECTORY_SYMLINK_UNAVAILABLE_ERRNOS = {
    errno.EPERM,
    errno.ENOSYS,
    errno.ENOTSUP,
    errno.EOPNOTSUPP,
}
_WINDOWS_PRIVILEGE_NOT_HELD = 1314


@pytest.mark.parametrize(
    ("platform_name", "changed_field", "states_are_equal"),
    (
        ("nt", "st_ctime_ns", True),
        ("nt", "st_mtime_ns", False),
        ("nt", "st_size", False),
        ("nt", "st_ino", False),
        ("posix", "st_ctime_ns", False),
    ),
)
def test_cross_stat_file_state_compares_only_portable_windows_fields(
    platform_name: str,
    changed_field: str,
    states_are_equal: bool,
) -> None:
    fields = {
        "st_dev": 1,
        "st_ino": 2,
        "st_mode": 3,
        "st_size": 4,
        "st_mtime_ns": 5,
        "st_ctime_ns": 6,
        "st_nlink": 1,
        "st_file_attributes": 0,
    }
    changed_fields = {**fields, changed_field: fields[changed_field] + 1}

    before = package_io._file_state(
        SimpleNamespace(**fields),
        platform_name=platform_name,
    )
    after = package_io._file_state(
        SimpleNamespace(**changed_fields),
        platform_name=platform_name,
    )

    assert (before == after) is states_are_equal


def _rendered(tmp_path: Path, deck_name: str = "ShadowPriest"):
    request = audited_request(
        tmp_path,
        deck_name,
        fixture_paths=True,
    )
    return render_package_authority(
        assemble_package(compile_package(request))
    )


def _make_directory_symlink(target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError as error:
        if (
            getattr(error, "winerror", None)
            == _WINDOWS_PRIVILEGE_NOT_HELD
            or error.errno in _DIRECTORY_SYMLINK_UNAVAILABLE_ERRNOS
        ):
            pytest.skip(f"directory symlinks unavailable: {error}")
        raise


@pytest.mark.parametrize(
    ("error_number", "winerror"),
    (
        (errno.EPERM, None),
        (errno.ENOTSUP, None),
        (errno.EINVAL, 1314),
    ),
)
def test_directory_symlink_helper_skips_only_unavailable_platform_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
    winerror: int | None,
) -> None:
    unavailable = OSError(error_number, "directory symlink unavailable")
    if winerror is not None:
        unavailable.winerror = winerror

    def fail_symlink(*_args: object, **_kwargs: object) -> None:
        raise unavailable

    monkeypatch.setattr(os, "symlink", fail_symlink)

    with pytest.raises(
        pytest.skip.Exception,
        match="directory symlinks unavailable",
    ):
        _make_directory_symlink(
            tmp_path / "target",
            tmp_path / "link",
        )


def test_directory_symlink_helper_reraises_other_os_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unexpected = OSError(errno.ENOENT, "unexpected symlink failure")

    def fail_symlink(*_args: object, **_kwargs: object) -> None:
        raise unexpected

    monkeypatch.setattr(os, "symlink", fail_symlink)

    with pytest.raises(OSError) as raised:
        _make_directory_symlink(
            tmp_path / "target",
            tmp_path / "link",
        )

    assert raised.value is unexpected


def test_publication_writes_exact_bytes_then_reloads_all_authorities(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"

    published = publish_rendered_package(rendered, destination)

    assert published.destination == destination
    assert published.content_root_sha256 == rendered.content_root_sha256
    view = DirectoryPackageView(destination)
    assert view.file_names() == rendered.artifacts.file_names()
    for artifact in rendered.artifacts.artifacts:
        actual = view.read_bytes(artifact.relative_path)
        assert actual == artifact.content
        assert len(actual) == artifact.size
        assert sha256(actual).hexdigest() == artifact.sha256

    receipt = view.read_json("package_derivation_receipt.json")
    verified, reasons = verify_package_derivation_receipt_from_view(
        view,
        receipt,
    )
    assert verified is True
    assert reasons == []
    replay_inputs = load_operator_summary_inputs(view)
    assert replay_inputs.authority.package_summary_parity is True
    assert build_operator_summary_from_inputs(
        replay_inputs
    ) == view.read_json("reports/operator_summary.json")

    rows = artifact_rows_for_tree(destination)
    fixture = load_fixture(FIXTURE_PATH)["decks"]["ShadowPriest"]
    assert rows == fixture["artifacts"]
    assert content_root_sha256(rows) == fixture["content_root_sha256"]


@pytest.mark.parametrize("fault_point", tuple(PublicationFaultPoint))
@pytest.mark.parametrize("preexisting_empty", (False, True))
def test_every_publication_fault_rolls_back_without_partial_output_or_residue(
    tmp_path: Path,
    fault_point: PublicationFaultPoint,
    preexisting_empty: bool,
) -> None:
    rendered = _rendered(tmp_path / "inputs", "CuteWarrior")
    destination = tmp_path / "published"
    if preexisting_empty:
        destination.mkdir()

    def fail_at(point: PublicationFaultPoint, _active: Path) -> None:
        if point is fault_point:
            raise RuntimeError(f"fault:{point.value}")

    with pytest.raises(RuntimeError, match=f"fault:{fault_point.value}"):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=fail_at,
        )

    if preexisting_empty:
        assert destination.is_dir()
        assert list(destination.iterdir()) == []
    else:
        assert not destination.exists()
    assert not tuple(
        destination.parent.glob(f".{destination.name}.staging-*")
    )


def test_publication_hooks_are_ordered_unique_and_switch_path_after_commit(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    trace: list[tuple[PublicationFaultPoint, Path]] = []

    def observe(point: PublicationFaultPoint, active: Path) -> None:
        trace.append((point, active))

    publish_rendered_package(
        rendered,
        destination,
        fault_hook=observe,
    )

    expected_order = tuple(PublicationFaultPoint)
    assert tuple(point for point, _active in trace) == expected_order
    assert len(trace) == len({point for point, _active in trace})
    staging_paths = tuple(
        active
        for point, active in trace
        if point is not PublicationFaultPoint.AFTER_COMMIT
    )
    assert len(set(staging_paths)) == 1
    assert staging_paths[0] != destination
    assert trace[-1] == (
        PublicationFaultPoint.AFTER_COMMIT,
        destination,
    )


def test_before_commit_rejects_preexisting_destination_identity_swap(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    renamed_original = tmp_path / "published-original"
    destination.mkdir()
    original_stat = destination.lstat()
    replacement_identity: tuple[int, int] | None = None

    def replace_empty_destination(
        point: PublicationFaultPoint,
        _active: Path,
    ) -> None:
        nonlocal replacement_identity
        if point is PublicationFaultPoint.BEFORE_COMMIT:
            destination.rename(renamed_original)
            destination.mkdir()
            replacement_stat = destination.lstat()
            replacement_identity = (
                int(replacement_stat.st_dev),
                int(replacement_stat.st_ino),
            )

    with pytest.raises(
        ValueError,
        match="publication_destination_identity_mismatch",
    ):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=replace_empty_destination,
        )

    assert replacement_identity is not None
    replacement_stat = destination.lstat()
    assert (
        int(replacement_stat.st_dev),
        int(replacement_stat.st_ino),
    ) == replacement_identity
    assert list(destination.iterdir()) == []
    renamed_stat = renamed_original.lstat()
    assert (
        int(renamed_stat.st_dev),
        int(renamed_stat.st_ino),
    ) == (
        int(original_stat.st_dev),
        int(original_stat.st_ino),
    )
    assert list(renamed_original.iterdir()) == []
    assert not tuple(
        destination.parent.glob(f".{destination.name}.staging-*")
    )


@pytest.mark.parametrize("tamper_point", tuple(PublicationFaultPoint))
def test_every_publication_hook_is_followed_by_exact_reload_verification(
    tmp_path: Path,
    tamper_point: PublicationFaultPoint,
) -> None:
    rendered = _rendered(tmp_path / "inputs", "CuteWarrior")
    destination = tmp_path / "published"

    def tamper(point: PublicationFaultPoint, active: Path) -> None:
        if point is not tamper_point:
            return
        if point is PublicationFaultPoint.STAGING_CREATED:
            (active / "unexpected.txt").write_bytes(b"unexpected")
            return
        receipt = active / "package_derivation_receipt.json"
        receipt.write_bytes(receipt.read_bytes() + b" ")

    with pytest.raises(
        ValueError,
        match=(
            "published_package_(tree_shape|file_set|artifact|"
            "receipt_verification)_"
        ),
    ):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=tamper,
        )

    if tamper_point is PublicationFaultPoint.AFTER_COMMIT:
        preserved = destination / "package_derivation_receipt.json"
        assert preserved.read_bytes().endswith(b" ")
        assert set(DirectoryPackageView(destination).file_names()) == {
            "package_derivation_receipt.json"
        }
        assert not tuple(
            destination.parent.glob(f".{destination.name}.staging-*")
        )
    else:
        assert not destination.exists()
        residue = tuple(
            destination.parent.glob(f".{destination.name}.staging-*")
        )
        assert len(residue) == 1
        if tamper_point is PublicationFaultPoint.STAGING_CREATED:
            assert (residue[0] / "unexpected.txt").read_bytes() == (
                b"unexpected"
            )
            assert DirectoryPackageView(residue[0]).file_names() == (
                "unexpected.txt",
            )
        else:
            preserved = residue[0] / "package_derivation_receipt.json"
            assert preserved.read_bytes().endswith(b" ")
            assert DirectoryPackageView(residue[0]).file_names() == (
                "package_derivation_receipt.json",
            )


def test_after_commit_rollback_preserves_unexpected_concurrent_files(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    foreign = destination / "concurrent-owner.txt"

    def add_foreign_then_fail(
        point: PublicationFaultPoint,
        active: Path,
    ) -> None:
        if point is PublicationFaultPoint.AFTER_COMMIT:
            assert active == destination
            foreign.write_bytes(b"preserve-concurrent-data")
            raise RuntimeError("fault:foreign-after-commit")

    with pytest.raises(
        RuntimeError,
        match="fault:foreign-after-commit",
    ):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=add_foreign_then_fail,
        )

    assert foreign.read_bytes() == b"preserve-concurrent-data"
    assert set(DirectoryPackageView(destination).file_names()) == {
        "concurrent-owner.txt"
    }
    assert not tuple(
        destination.parent.glob(f".{destination.name}.staging-*")
    )


def test_after_commit_rollback_preserves_foreign_bytes_at_a_planned_name(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    replacement = destination / "reports" / "operator_summary.json"

    def replace_then_fail(
        point: PublicationFaultPoint,
        _active: Path,
    ) -> None:
        if point is PublicationFaultPoint.AFTER_COMMIT:
            replacement.write_bytes(b"foreign-concurrent-replacement")
            raise RuntimeError("fault:planned-name-replaced")

    with pytest.raises(RuntimeError, match="fault:planned-name-replaced"):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=replace_then_fail,
        )

    assert replacement.read_bytes() == b"foreign-concurrent-replacement"
    assert not tuple(
        destination.parent.glob(f".{destination.name}.staging-*")
    )


def test_after_commit_rollback_preserves_byte_identical_replacement_inode(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    replacement = destination / "reports" / "operator_summary.json"
    identities: dict[str, tuple[int, int]] = {}

    def replace_identically_then_fail(
        point: PublicationFaultPoint,
        _active: Path,
    ) -> None:
        if point is PublicationFaultPoint.AFTER_COMMIT:
            before = replacement.lstat()
            content = replacement.read_bytes()
            replacement.unlink()
            replacement.write_bytes(content)
            after = replacement.lstat()
            identities["before"] = (before.st_dev, before.st_ino)
            identities["after"] = (after.st_dev, after.st_ino)
            raise RuntimeError("fault:byte-identical-replacement")

    with pytest.raises(
        RuntimeError,
        match="fault:byte-identical-replacement",
    ):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=replace_identically_then_fail,
        )

    assert identities["before"] != identities["after"]
    assert replacement.read_bytes() == rendered.artifacts.read_bytes(
        "reports/operator_summary.json"
    )
    assert not tuple(
        destination.parent.glob(f".{destination.name}.staging-*")
    )


def test_after_commit_rollback_never_follows_a_directory_symlink_parent(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    external = tmp_path / "external"
    external.mkdir()
    victim = external / "operator_summary.json"
    victim.write_bytes(b"external-victim")

    def replace_reports_then_fail(
        point: PublicationFaultPoint,
        _active: Path,
    ) -> None:
        if point is PublicationFaultPoint.AFTER_COMMIT:
            reports = destination / "reports"
            reports.rename(destination / "reports-publisher-original")
            _make_directory_symlink(
                external,
                reports,
            )
            raise RuntimeError("fault:reports-parent-reparse")

    with pytest.raises(RuntimeError, match="fault:reports-parent-reparse"):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=replace_reports_then_fail,
    )

    assert victim.read_bytes() == b"external-victim"
    assert not destination.exists()
    assert not tuple(
        destination.parent.glob(f".{destination.name}.staging-*")
    )


def test_after_commit_root_symlink_to_the_exact_tree_is_rejected_without_following(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    moved = tmp_path / "publisher-tree-moved"

    def replace_root_with_symlink(
        point: PublicationFaultPoint,
        _active: Path,
    ) -> None:
        if point is PublicationFaultPoint.AFTER_COMMIT:
            destination.rename(moved)
            _make_directory_symlink(
                moved,
                destination,
            )

    with pytest.raises(
        ValueError,
        match="published_package_root_identity_mismatch",
    ):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=replace_root_with_symlink,
        )

    assert destination.is_symlink()
    assert (moved / "package_derivation_receipt.json").is_file()
    assert not tuple(
        destination.parent.glob(f".{destination.name}.staging-*")
    )


def test_staging_created_root_symlink_is_rejected_before_external_writes(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    external = tmp_path / "external-empty"
    external.mkdir()

    def replace_staging_root(
        point: PublicationFaultPoint,
        active: Path,
    ) -> None:
        if point is PublicationFaultPoint.STAGING_CREATED:
            active.rmdir()
            _make_directory_symlink(
                external,
                active,
            )

    with pytest.raises(
        ValueError,
        match="published_package_root_identity_mismatch",
    ):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=replace_staging_root,
        )

    assert tuple(external.iterdir()) == ()
    assert not destination.exists()
    assert not tuple(
        destination.parent.glob(f".{destination.name}.staging-*")
    )


def test_staging_created_nested_symlink_is_rejected_before_external_writes(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    external = tmp_path / "external-empty"
    external.mkdir()

    def inject_reports_symlink(
        point: PublicationFaultPoint,
        active: Path,
    ) -> None:
        if point is PublicationFaultPoint.STAGING_CREATED:
            _make_directory_symlink(
                external,
                active / "reports",
            )

    with pytest.raises(
        ValueError,
        match="published_package_tree_shape_mismatch",
    ):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=inject_reports_symlink,
        )

    assert tuple(external.iterdir()) == ()
    assert not destination.exists()


def test_before_commit_nested_directory_swap_never_traverses_external_target(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    external = tmp_path / "external"
    external.mkdir()
    victim = external / "operator_summary.json"
    victim.write_bytes(b"external-victim")
    captured: dict[str, Path] = {}

    def replace_reports_then_fail(
        point: PublicationFaultPoint,
        active: Path,
    ) -> None:
        if point is PublicationFaultPoint.BEFORE_COMMIT:
            original = active / "reports-publisher-original"
            (active / "reports").rename(original)
            _make_directory_symlink(
                external,
                active / "reports",
            )
            captured["staging"] = active
            captured["original"] = original
            raise RuntimeError("fault:nested-dir-swap")

    with pytest.raises(RuntimeError, match="fault:nested-dir-swap"):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=replace_reports_then_fail,
    )

    assert victim.read_bytes() == b"external-victim"
    assert not captured["staging"].exists()
    assert not captured["original"].exists()
    assert not destination.exists()


def test_staging_creation_failure_removes_only_new_nested_parents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    preexisting = tmp_path / "preexisting"
    preexisting.mkdir()
    destination = preexisting / "new" / "nested" / "published"

    def fail_staging(*args: object, **kwargs: object) -> str:
        del args, kwargs
        raise OSError("injected_mkdtemp_failure")

    monkeypatch.setattr(
        package_publication.tempfile,
        "mkdtemp",
        fail_staging,
    )

    with pytest.raises(OSError, match="injected_mkdtemp_failure"):
        publish_rendered_package(rendered, destination)

    assert preexisting.is_dir()
    assert tuple(preexisting.iterdir()) == ()
    assert not destination.exists()


def test_mkdtemp_parent_symlink_swap_is_rejected_before_external_package_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    parent = tmp_path / "publication-parent"
    parent.mkdir()
    moved = tmp_path / "publication-parent-original"
    external = tmp_path / "external-parent-target"
    external.mkdir()
    victim = external / "victim.txt"
    victim.write_bytes(b"preserve")
    destination = parent / "published"
    real_mkdtemp = package_publication.tempfile.mkdtemp

    def swap_parent_then_create(*args: object, **kwargs: object) -> str:
        parent.rename(moved)
        _make_directory_symlink(external, parent)
        return real_mkdtemp(*args, **kwargs)

    monkeypatch.setattr(
        package_publication.tempfile,
        "mkdtemp",
        swap_parent_then_create,
    )

    with pytest.raises(
        ValueError,
        match="published_package_parent_identity_mismatch",
    ):
        publish_rendered_package(rendered, destination)

    assert parent.is_symlink()
    assert victim.read_bytes() == b"preserve"
    assert not tuple(external.rglob("package_derivation_receipt.json"))
    assert moved.is_dir()


@pytest.mark.skipif(
    os.name != "nt",
    reason="NTFS junction regression is Windows-specific",
)
def test_mkdtemp_parent_junction_swap_is_rejected_before_external_package_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    parent = tmp_path / "publication-parent"
    parent.mkdir()
    moved = tmp_path / "publication-parent-original"
    external = tmp_path / "external-parent-target"
    external.mkdir()
    victim = external / "victim.txt"
    victim.write_bytes(b"preserve")
    probe = tmp_path / "junction-probe"
    probe_result = subprocess.run(
        [
            "cmd.exe",
            "/d",
            "/c",
            "mklink",
            "/J",
            str(probe),
            str(external),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe_result.returncode != 0:
        pytest.skip(
            f"junction creation unavailable: {probe_result.stderr}"
        )
    probe.rmdir()
    destination = parent / "published"
    real_mkdtemp = package_publication.tempfile.mkdtemp

    def swap_parent_then_create(*args: object, **kwargs: object) -> str:
        parent.rename(moved)
        created = subprocess.run(
            [
                "cmd.exe",
                "/d",
                "/c",
                "mklink",
                "/J",
                str(parent),
                str(external),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if created.returncode != 0:
            raise OSError(created.stderr)
        return real_mkdtemp(*args, **kwargs)

    monkeypatch.setattr(
        package_publication.tempfile,
        "mkdtemp",
        swap_parent_then_create,
    )

    with pytest.raises(
        ValueError,
        match="published_package_parent_identity_mismatch",
    ):
        publish_rendered_package(rendered, destination)

    assert (
        getattr(parent.lstat(), "st_file_attributes", 0)
        & 0x400
    )
    assert victim.read_bytes() == b"preserve"
    assert not tuple(external.rglob("package_derivation_receipt.json"))
    assert moved.is_dir()


@pytest.mark.skipif(
    os.name != "nt",
    reason="NTFS junction regression is Windows-specific",
)
def test_destination_preflight_preserves_an_empty_ntfs_junction(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    external = tmp_path / "junction-target"
    external.mkdir()
    destination = tmp_path / "published"
    created = subprocess.run(
        [
            "cmd.exe",
            "/d",
            "/c",
            "mklink",
            "/J",
            str(destination),
            str(external),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        pytest.skip(f"junction creation unavailable: {created.stderr}")

    with pytest.raises(ValueError, match="destination_must_be_empty"):
        publish_rendered_package(rendered, destination)

    assert destination.is_dir()
    assert (
        getattr(destination.lstat(), "st_file_attributes", 0)
        & 0x400
    )
    assert tuple(external.iterdir()) == ()


def test_destination_preflight_rejects_a_directory_symlink_ancestor(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    external = tmp_path / "symlink-target"
    external.mkdir()
    ancestor = tmp_path / "parent-reparse"
    _make_directory_symlink(external, ancestor)
    destination = ancestor / "nested" / "published"

    with pytest.raises(ValueError, match="publication_parent_invalid"):
        publish_rendered_package(rendered, destination)

    assert ancestor.is_symlink()
    assert tuple(external.iterdir()) == ()
    assert not destination.exists()


@pytest.mark.skipif(
    os.name != "nt",
    reason="NTFS junction regression is Windows-specific",
)
def test_destination_preflight_rejects_an_ntfs_junction_ancestor(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    external = tmp_path / "junction-parent-target"
    external.mkdir()
    ancestor = tmp_path / "parent-junction"
    created = subprocess.run(
        [
            "cmd.exe",
            "/d",
            "/c",
            "mklink",
            "/J",
            str(ancestor),
            str(external),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        pytest.skip(f"junction creation unavailable: {created.stderr}")
    destination = ancestor / "nested" / "published"

    with pytest.raises(ValueError, match="publication_parent_invalid"):
        publish_rendered_package(rendered, destination)

    assert (
        getattr(ancestor.lstat(), "st_file_attributes", 0)
        & 0x400
    )
    assert tuple(external.iterdir()) == ()
    assert not destination.exists()


@pytest.mark.parametrize("injection_point", tuple(PublicationFaultPoint))
def test_full_tree_verification_rejects_empty_directory_injection_at_every_hook(
    tmp_path: Path,
    injection_point: PublicationFaultPoint,
) -> None:
    rendered = _rendered(tmp_path / "inputs", "CuteWarrior")
    destination = tmp_path / "published"

    def inject_empty_directory(
        point: PublicationFaultPoint,
        active: Path,
    ) -> None:
        if point is injection_point:
            (active / "unexpected-empty-dir").mkdir()

    with pytest.raises(
        ValueError,
        match="published_package_tree_shape_mismatch",
    ):
        publish_rendered_package(
            rendered,
            destination,
            fault_hook=inject_empty_directory,
        )

    assert not destination.exists()
    assert not tuple(
        destination.parent.glob(f".{destination.name}.staging-*")
    )


def test_publication_refuses_a_nonempty_destination_without_mutation(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    destination.mkdir()
    existing = destination / "operator-owned.txt"
    existing.write_bytes(b"preserve-me")

    with pytest.raises(ValueError, match="destination_must_be_empty"):
        publish_rendered_package(rendered, destination)

    assert existing.read_bytes() == b"preserve-me"
    assert tuple(destination.iterdir()) == (existing,)


def test_successful_publication_accepts_a_preexisting_empty_destination(
    tmp_path: Path,
) -> None:
    rendered = _rendered(tmp_path / "inputs")
    destination = tmp_path / "published"
    destination.mkdir()

    publish_rendered_package(rendered, destination)

    assert DirectoryPackageView(destination).file_names() == (
        rendered.artifacts.file_names()
    )
