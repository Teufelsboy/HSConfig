from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from hsconfig.atomic_io import atomic_write_bytes as real_atomic_write_bytes
from hsconfig.cli import main
from hsconfig.package_io import (
    secure_create_directory as real_secure_create_directory,
    status_is_reparse,
)
from tests.helpers.audited_package_request import audited_request


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="
)


def test_starter_context_cli_writes_one_canonical_artifact_without_runtime_mutation(
    tmp_path: Path,
    capsys,
) -> None:
    # Break caught: publishing package/runtime files or any sibling besides the
    # explicit canonical starter context.
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    sentinel = runtime_root / "sentinel.bin"
    sentinel.write_bytes(b"runtime must remain unchanged")
    before = _tree_receipt(runtime_root)
    out = tmp_path / "starter"

    code = main(
        [
            "starter-context",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--full-cards-json",
            "tests/fixtures/hearthstonejson_shadowpriest_cards.json",
            "--skip-semantic-fetch",
            "--current-date",
            "2026-07-29",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    artifact = out / "starter_context.json"
    raw = artifact.read_bytes()
    document = json.loads(raw)

    assert code == 0
    assert payload == {
        "content_sha256": document["content_sha256"],
        "deck_fingerprint": (
            "831b989cf8d076bff87848b4d0d6f382c9d306fddea7619017f0c361bfc92327"
        ),
        "output": str(artifact),
        "runtime_write_performed": False,
        "status": "passed",
    }
    assert sorted(path.name for path in out.iterdir()) == ["starter_context.json"]
    assert raw == json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert before == _tree_receipt(runtime_root)


def test_starter_context_rejects_resolver_time_output_ancestor_substitution(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: an output parent replaced by a runtime-root junction after
    # preflight made recursive mkdir create and publish inside runtime.
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    (runtime_root / "sentinel.bin").write_bytes(b"unchanged")
    before = _tree_receipt(runtime_root)
    output_parent = tmp_path / "output-parent"
    output_parent.mkdir()
    out = output_parent / "starter"
    snapshot = audited_request(tmp_path / "request", "ShadowPriest").snapshot

    def substitute_output_parent(*_args, **_kwargs):
        output_parent.rmdir()
        _make_directory_link(output_parent, runtime_root)
        return SimpleNamespace(snapshot=snapshot)

    monkeypatch.setattr(
        "hsconfig.commands.starter_context.resolve_package_request",
        substitute_output_parent,
    )
    after: dict[str, str]
    try:
        code = main(
            [
                "starter-context",
                "--deck-name",
                "ShadowPriest",
                "--deck-code",
                SHADOWPRIEST_CODE,
                "--runtime-root",
                str(runtime_root),
                "--out",
                str(out),
                "--json",
            ]
        )
        after = _tree_receipt(runtime_root)
    finally:
        if os.path.lexists(output_parent) and status_is_reparse(output_parent.lstat()):
            if os.name == "nt":
                os.rmdir(output_parent)
            else:
                output_parent.unlink()
        leaked = runtime_root / "starter"
        if leaked.exists():
            artifact = leaked / "starter_context.json"
            if artifact.exists():
                artifact.unlink()
            leaked.rmdir()

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "failed"
    assert before == after


def test_starter_context_rejects_post_create_output_directory_substitution(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: the newly created output directory was previously not
    # identity-bound to the atomic write, so a plain runtime directory could
    # replace it after secure creation and receive the artifact.
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    (runtime_root / "sentinel.bin").write_bytes(b"unchanged")
    before = _tree_receipt(runtime_root)
    out = tmp_path / "starter"
    retired_output = tmp_path / "retired-output"
    substitute_output = tmp_path / "substitute-output"
    substitute_output.mkdir()

    def substitute_created_output(path: Path, content: bytes, **kwargs) -> None:
        out.rename(retired_output)
        substitute_output.rename(out)
        try:
            real_atomic_write_bytes(path, content, **kwargs)
        finally:
            out.rename(substitute_output)
            retired_output.rename(out)

    monkeypatch.setattr(
        "hsconfig.commands.starter_context.atomic_write_bytes",
        substitute_created_output,
    )
    after: dict[str, str]
    try:
        code = main(
            [
                "starter-context",
                "--deck-name",
                "ShadowPriest",
                "--deck-code",
                SHADOWPRIEST_CODE,
                "--runtime-root",
                str(runtime_root),
                "--out",
                str(out),
                "--source-documents-json",
                "tests/fixtures/source_documents_shadowpriest_strong.json",
                "--full-cards-json",
                "tests/fixtures/hearthstonejson_shadowpriest_cards.json",
                "--skip-semantic-fetch",
                "--current-date",
                "2026-07-29",
                "--json",
            ]
        )
        after = _tree_receipt(runtime_root)
    finally:
        leaked = runtime_root / "starter_context.json"
        if leaked.exists():
            leaked.unlink()

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "failed"
    assert before == after
    assert list(out.iterdir()) == []


def test_starter_context_holds_runtime_root_through_output_commit(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: replacing runtime-root with a junction to the output parent
    # after final validation could make the new output child a runtime child.
    if os.name != "nt":
        pytest.skip("runtime-root junction substitution is Windows-specific")
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    (runtime_root / "sentinel.bin").write_bytes(b"unchanged")
    retired_runtime = tmp_path / "retired-runtime"
    output_parent = tmp_path / "output-parent"
    output_parent.mkdir()
    out = output_parent / "starter"
    before = _tree_receipt(tmp_path)

    def substitute_runtime_root(path: Path, **kwargs) -> tuple[int, int, int]:
        runtime_root.rename(retired_runtime)
        _make_directory_link(runtime_root, output_parent)
        return real_secure_create_directory(path, **kwargs)

    monkeypatch.setattr(
        "hsconfig.commands.starter_context.secure_create_directory",
        substitute_runtime_root,
    )
    after: dict[str, str]
    output_child_created: bool
    try:
        code = main(
            [
                "starter-context",
                "--deck-name",
                "ShadowPriest",
                "--deck-code",
                SHADOWPRIEST_CODE,
                "--runtime-root",
                str(runtime_root),
                "--out",
                str(out),
                "--source-documents-json",
                "tests/fixtures/source_documents_shadowpriest_strong.json",
                "--full-cards-json",
                "tests/fixtures/hearthstonejson_shadowpriest_cards.json",
                "--skip-semantic-fetch",
                "--current-date",
                "2026-07-29",
                "--json",
            ]
        )
        after = _tree_receipt(tmp_path)
        output_child_created = os.path.lexists(out)
    finally:
        artifact = out / "starter_context.json"
        if artifact.exists():
            artifact.unlink()
        if out.exists():
            out.rmdir()
        if os.path.lexists(runtime_root) and status_is_reparse(runtime_root.lstat()):
            if os.name == "nt":
                os.rmdir(runtime_root)
            else:
                runtime_root.unlink()
        if retired_runtime.exists():
            retired_runtime.rename(runtime_root)

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "failed"
    assert output_child_created is False
    assert before == after


def _tree_receipt(root: Path) -> dict[str, str]:
    receipt: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        status = path.lstat()
        if status_is_reparse(status):
            receipt[relative] = "reparse"
        elif path.is_dir():
            receipt[relative] = "directory"
        elif path.is_file():
            receipt[relative] = f"file:{sha256(path.read_bytes()).hexdigest()}"
        else:
            receipt[relative] = "other"
    return receipt


def _make_directory_link(link: Path, target: Path) -> None:
    if os.name != "nt":
        link.symlink_to(target, target_is_directory=True)
        return
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip("directory junction creation unavailable")
