from __future__ import annotations

import json
import os
import threading
import time
import hashlib
from pathlib import Path

import pytest

from hsconfig.configure_run_model import (
    RenderedConfigureRun,
)
from hsconfig.current_output import resolve_current_package
from hsconfig.output_publisher import publish_configure_run
from tests.test_output_publisher import (
    rendered_runs_fixture as _rendered_runs_fixture,  # noqa: F401
)


def _publish(
    tmp_path: Path,
    rendered: RenderedConfigureRun,
) -> tuple[Path, Path]:
    output_root = tmp_path / "ShadowPriest"
    published = publish_configure_run(rendered, output_root)
    return output_root, published.package_root


def test_resolver_returns_only_verified_current_package(
    tmp_path: Path,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    output_root, package_root = _publish(tmp_path, rendered_runs[0])
    assert resolve_current_package(output_root) == package_root


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
        os.symlink(real_root, revision_root, target_is_directory=True)
    except OSError:
        real_root.rename(revision_root)
        pytest.skip("directory symlinks unavailable")
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
    try:
        os.symlink(tmp_path / "missing-pointer", pointer)
    except OSError:
        pytest.skip("file symlinks unavailable")
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
