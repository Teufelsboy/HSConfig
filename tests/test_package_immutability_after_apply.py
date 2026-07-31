from __future__ import annotations

from argparse import Namespace
import hashlib
from pathlib import Path

import pytest

from hsconfig.configure_run_stage_contract import configure_summary_bytes
from hsconfig.commands.apply import apply_payload
from hsconfig.current_output import OutputPublication, output_publication_bytes
from hsconfig.io import write_json
from hsconfig.io import read_json
from hsconfig.package_render_authority import AuthorityArtifact
from hsconfig.runtime_apply import apply_package, plan_apply_package
from hsconfig.run_manifest import (
    MANIFEST_PATH,
    build_tree_manifest_from_artifacts,
    write_tree_manifest,
)
from tests.test_runtime_apply import _complete_package


def _inventory(root: Path) -> tuple[tuple[str, int, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def _backup_names(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if (
            "backup" in path.name.casefold()
            or path.name.casefold().endswith(".bak")
            or "rollback_snapshot" in path.name.casefold()
        )
    )


def _published_output(tmp_path: Path) -> tuple[Path, Path]:
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    identity = read_json(package / "reports" / "deck_identity.json")
    output_root = tmp_path / "published"
    staging = tmp_path / "revision-staging"
    staging.mkdir()
    package.rename(staging / "04_package")
    stage_files = {
        "01_manifest/input.json": b"{}\n",
        "02_source_documents/source.json": b"{}\n",
        "03_research/research.json": b"{}\n",
    }
    stage_files["configure_summary.json"] = configure_summary_bytes(
        deck_name=identity["deck_name"],
        deck_fingerprint=identity["deck_fingerprint"],
        paths=tuple(sorted(stage_files)),
    )
    for relative_path, content in stage_files.items():
        target = staging / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    artifacts = tuple(
        AuthorityArtifact.from_content(
            relative_path=path.relative_to(staging).as_posix(),
            content=path.read_bytes(),
        )
        for path in sorted(staging.rglob("*"))
        if path.is_file()
    )
    manifest = build_tree_manifest_from_artifacts(
        deck_name=identity["deck_name"],
        deck_fingerprint=identity["deck_fingerprint"],
        artifacts=artifacts,
    )
    (staging / MANIFEST_PATH).write_bytes(write_tree_manifest(manifest))
    revision = (
        output_root
        / "revisions"
        / f"sha256-{manifest.content_root_sha256}"
    )
    revision.parent.mkdir(parents=True)
    staging.rename(revision)
    (output_root / ".publish.lock").write_bytes(b"")
    publication = OutputPublication(
        schema_version=1,
        deck_name=identity["deck_name"],
        deck_fingerprint=identity["deck_fingerprint"],
        revision=f"revisions/{revision.name}",
        content_root_sha256=manifest.content_root_sha256,
    )
    (output_root / "current.json").write_bytes(
        output_publication_bytes(publication)
    )
    return output_root, revision


def _apply_args(
    package: Path,
    runtime: Path,
    *,
    fake: bool = False,
    from_fake_receipt: Path | None = None,
) -> Namespace:
    return Namespace(
        package=str(package),
        runtime_root=str(runtime),
        fake=fake,
        from_fake_receipt=(
            str(from_fake_receipt)
            if from_fake_receipt is not None
            else None
        ),
        immutable_package=True,
        json=True,
    )


def test_fake_plan_is_pure_and_does_not_mutate_loose_package(
    tmp_path: Path,
) -> None:
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    before = _inventory(package)

    receipt = plan_apply_package(
        package_root=package,
        runtime_root=tmp_path / "runtime",
    )

    assert receipt["status"] == "fake_apply_ready"
    assert receipt["runtime_write_performed"] is False
    assert _inventory(package) == before


def test_loose_real_apply_fails_closed_without_runtime_or_backup_mutation(
    tmp_path: Path,
) -> None:
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    runtime = tmp_path / "runtime"
    write_json(runtime / "CustomConfig" / "deck" / "old.json", {"old": True})
    before_package = _inventory(package)
    before_runtime = _inventory(runtime)

    with pytest.raises(TypeError, match="published_output_required"):
        apply_package(package_root=package, runtime_root=runtime)

    assert _inventory(package) == before_package
    assert _inventory(runtime) == before_runtime
    assert _backup_names(tmp_path) == []


def test_inactive_revision_shaped_direct_path_fails_with_stable_error(
    tmp_path: Path,
) -> None:
    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    inactive = (
        tmp_path
        / "not-published"
        / "revisions"
        / f"sha256-{'d' * 64}"
        / "04_package"
    )
    inactive.parent.mkdir(parents=True)
    package.rename(inactive)
    before = _inventory(inactive)

    with pytest.raises(TypeError, match="published_output_required"):
        apply_package(
            package_root=inactive,
            runtime_root=tmp_path / "runtime",
        )

    assert _inventory(inactive) == before
    assert not (tmp_path / "runtime").exists()
    assert _backup_names(tmp_path) == []


def test_published_plan_apply_from_fake_and_idempotency_preserve_revision(
    tmp_path: Path,
) -> None:
    output_root, revision = _published_output(tmp_path)
    package = revision / "04_package"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    before_package = _inventory(package)
    before_revision = _inventory(revision)

    fake = plan_apply_package(
        package_root=output_root,
        runtime_root=runtime,
    )
    assert _inventory(package) == before_package
    assert _inventory(revision) == before_revision

    first = apply_package(
        package_root=output_root,
        runtime_root=runtime,
        fake_receipt=fake,
    )
    assert first["status"] == "applied"
    assert first["runtime_write_performed"] is True
    assert first["logical_config_dir"] == "deck"
    assert first["versioned_config_dir"].startswith("deck--sha256-")
    assert _inventory(package) == before_package
    assert _inventory(revision) == before_revision
    assert _backup_names(tmp_path) == []

    second = apply_package(
        package_root=package,
        runtime_root=runtime,
    )
    assert second["status"] == "already_current"
    assert second["runtime_write_performed"] is False
    assert _inventory(package) == before_package
    assert _inventory(revision) == before_revision
    assert _backup_names(tmp_path) == []


def test_injected_installer_failure_preserves_full_published_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig import runtime_apply

    output_root, revision = _published_output(tmp_path)
    package = revision / "04_package"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    before_package = _inventory(package)
    before_revision = _inventory(revision)

    def fail_install(_plan):
        raise RuntimeError("injected installer failure")

    monkeypatch.setattr(runtime_apply, "install_runtime_package", fail_install)
    with pytest.raises(RuntimeError, match="injected installer failure"):
        apply_package(package_root=output_root, runtime_root=runtime)

    assert _inventory(package) == before_package
    assert _inventory(revision) == before_revision
    assert _backup_names(tmp_path) == []


def test_real_apply_payload_covers_output_root_direct_active_fake_and_from_fake(
    tmp_path: Path,
) -> None:
    output_root, revision = _published_output(tmp_path)
    package = revision / "04_package"
    runtime = tmp_path / "runtime-real"

    fake_payload, fake_code = apply_payload(
        _apply_args(output_root, runtime, fake=True)
    )
    assert fake_code == 0
    assert fake_payload["status"] == "fake_apply_ready"

    fake_path = tmp_path / "fake-receipt.json"
    write_json(fake_path, fake_payload["receipt"])
    first, first_code = apply_payload(
        _apply_args(
            output_root,
            runtime,
            from_fake_receipt=fake_path,
        )
    )
    assert first_code == 0
    assert first["status"] == "applied"

    second, second_code = apply_payload(_apply_args(package, runtime))
    assert second_code == 0
    assert second["status"] == "already_current"


@pytest.mark.parametrize(
    "status",
    [
        "applied",
        "already_current",
        "recovered",
        "committed_receipt_pending",
    ],
)
def test_apply_payload_preserves_all_typed_installer_statuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    output_root, _ = _published_output(tmp_path)

    monkeypatch.setattr(
        "hsconfig.commands.apply.apply_package",
        lambda **_kwargs: {"status": status},
    )
    payload, code = apply_payload(
        _apply_args(output_root, tmp_path / "runtime")
    )

    assert code == 0
    assert payload["status"] == status
    assert payload["receipt"]["status"] == status


def test_apply_payload_converts_installer_exception_to_failed_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, _ = _published_output(tmp_path)

    def fail_apply(**_kwargs):
        raise RuntimeError("injected installer exception")

    monkeypatch.setattr("hsconfig.commands.apply.apply_package", fail_apply)
    payload, code = apply_payload(
        _apply_args(output_root, tmp_path / "runtime")
    )

    assert code == 1
    assert payload == {
        "status": "failed",
        "errors": ["injected installer exception"],
    }


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit(7)])
def test_apply_payload_does_not_swallow_base_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    output_root, _ = _published_output(tmp_path)

    def fail_apply(**_kwargs):
        raise failure

    monkeypatch.setattr("hsconfig.commands.apply.apply_package", fail_apply)
    with pytest.raises(type(failure)):
        apply_payload(_apply_args(output_root, tmp_path / "runtime"))
