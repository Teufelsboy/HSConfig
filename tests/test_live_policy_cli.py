from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import hsconfig.operator_profile as operator_profile
from hsconfig.commands import live_policy
from hsconfig.cli import _build_parser, main
from hsconfig.operator_profile import (
    disable_operator_profile,
    enable_operator_profile,
    operator_profile_path,
)
from hsconfig.package_io import path_identity


def _roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    local_app_data = tmp_path / "local-app-data"
    runtime_root = tmp_path / "runtime"
    output_base_root = tmp_path / "outputs"
    local_app_data.mkdir()
    runtime_root.mkdir()
    output_base_root.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    return runtime_root, output_base_root


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


def test_enable_and_disable_round_trip_through_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    runtime_root, output_base_root = _roots(tmp_path, monkeypatch)

    enable_code = main(
        [
            "live-policy",
            "enable",
            "--runtime-root",
            str(runtime_root),
            "--output-base-root",
            str(output_base_root),
            "--expected-absent",
            "--json",
        ]
    )
    enabled = json.loads(capsys.readouterr().out)

    assert enable_code == 0
    assert enabled["status"] == "enabled"
    assert enabled["content_sha256"].startswith("sha256:")
    assert enabled["runtime_root"] == str(runtime_root.resolve())
    assert enabled["output_base_root"] == str(output_base_root.resolve())
    assert len(enabled["runtime_root_identity"]) == 3
    assert len(enabled["output_base_root_identity"]) == 3
    before_status = _inventory(tmp_path)
    assert main(["live-policy", "status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        **enabled, "diagnostic_only": True, "runtime_write_performed": False,
    }
    assert _inventory(tmp_path) == before_status

    disable_code = main(
        [
            "live-policy",
            "disable",
            "--expected-predecessor-sha256",
            enabled["content_sha256"],
            "--json",
        ]
    )
    disabled = json.loads(capsys.readouterr().out)

    assert disable_code == 0
    assert disabled["status"] == "disabled"
    assert disabled["content_sha256"] != enabled["content_sha256"]
    assert disabled["runtime_root"] == enabled["runtime_root"]
    assert disabled["output_base_root"] == enabled["output_base_root"]
    assert len(disabled["runtime_root_identity"]) == 3
    assert len(disabled["output_base_root_identity"]) == 3
    before_status = _inventory(tmp_path)
    assert main(["live-policy", "status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        **disabled, "diagnostic_only": True, "runtime_write_performed": False,
    }
    assert _inventory(tmp_path) == before_status


def test_disable_never_creates_a_missing_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    _runtime_root, _output_base_root = _roots(tmp_path, monkeypatch)

    code = main(
        [
            "live-policy",
            "disable",
            "--expected-predecessor-sha256",
            "sha256:" + ("0" * 64),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "failed"
    assert not operator_profile_path().exists()
    assert not operator_profile_path().parent.exists()


def test_cli_enable_rejects_over_limit_prospective_state_root_without_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    depth_base = tmp_path / "cli-local-depth"
    runtime_root = tmp_path / "cli-runtime"
    output_base_root = tmp_path / "cli-outputs"
    depth_base.mkdir()
    runtime_root.mkdir()
    output_base_root.mkdir()
    local_app_data = _existing_directory_at_identity_row_depth(depth_base, 256)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    state_root = local_app_data / "HSConfig"
    parent_before = (
        tuple(local_app_data.iterdir()),
        path_identity(local_app_data),
        local_app_data.stat().st_mtime_ns,
    )

    code = main(
        [
            "live-policy",
            "enable",
            "--runtime-root",
            str(runtime_root),
            "--output-base-root",
            str(output_base_root),
            "--expected-absent",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "failed"
    assert not state_root.exists()
    assert (
        tuple(local_app_data.iterdir()),
        path_identity(local_app_data),
        local_app_data.stat().st_mtime_ns,
    ) == parent_before


def test_profile_mutations_require_exact_predecessor_option():
    parser = _build_parser()

    with pytest.raises(SystemExit) as missing_enable:
        parser.parse_args(
            [
                "live-policy",
                "enable",
                "--runtime-root",
                "C:\\runtime",
                "--output-base-root",
                "C:\\outputs",
            ]
        )
    assert missing_enable.value.code == 2

    with pytest.raises(SystemExit) as ambiguous_enable:
        parser.parse_args(
            [
                "live-policy",
                "enable",
                "--runtime-root",
                "C:\\runtime",
                "--output-base-root",
                "C:\\outputs",
                "--expected-absent",
                "--expected-predecessor-sha256",
                "sha256:" + ("0" * 64),
            ]
        )
    assert ambiguous_enable.value.code == 2

    with pytest.raises(SystemExit) as missing_disable:
        parser.parse_args(["live-policy", "disable"])
    assert missing_disable.value.code == 2


def _inventory(root: Path) -> dict[str, tuple[int, bytes | None]]:
    return {
        str(path.relative_to(root)): (
            path.lstat().st_mtime_ns,
            path.read_bytes() if path.is_file() else None,
        )
        for path in [root, *root.rglob("*")]
    }


@pytest.mark.parametrize("state_exists", [False, True])
@pytest.mark.parametrize("as_json", [False, True])
def test_status_absent_is_read_only(
    tmp_path, monkeypatch, capsys, state_exists, as_json
):
    _roots(tmp_path, monkeypatch)
    if state_exists:
        operator_profile_path().parent.mkdir()
    before = _inventory(tmp_path)

    code = main(["live-policy", "status", *(["--json"] if as_json else [])])

    assert code == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "absent",
        "diagnostic_only": True,
        "runtime_write_performed": False,
    }
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("as_json", [False, True])
def test_status_validates_fixture_profile_without_mutation(
    tmp_path, monkeypatch, capsys, enabled, as_json
):
    runtime_root, output_base_root = _roots(tmp_path, monkeypatch)
    profile = enable_operator_profile(
        runtime_root=runtime_root,
        output_base_root=output_base_root,
        expected_predecessor_sha256=None,
    )
    if not enabled:
        profile = disable_operator_profile(
            expected_predecessor_sha256=profile.content_sha256
        )
    document = json.loads(operator_profile_path().read_bytes())
    before = _inventory(tmp_path)

    def forbidden_mutation_admission(*args, **kwargs):
        raise AssertionError("status must not acquire a profile lock or live admission")

    monkeypatch.setattr(operator_profile, "ExclusiveFileLock", forbidden_mutation_admission)
    monkeypatch.setattr(
        operator_profile, "require_live_admission_allows_profile_mutation",
        forbidden_mutation_admission,
    )

    code = main(["live-policy", "status", *(["--json"] if as_json else [])])

    assert code == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "enabled" if enabled else "disabled",
        "diagnostic_only": True,
        "runtime_write_performed": False,
        **{key: document[key] for key in (
            "content_sha256", "runtime_root", "output_base_root",
            "runtime_root_identity", "output_base_root_identity",
        )},
    }
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("defect", [
    "json", "hash", "runtime_missing", "output_missing", "profile_directory",
    "hardlink", "state_file", "state_symlink", "profile_symlink",
])
@pytest.mark.parametrize("as_json", [False, True])
def test_status_invalid_profile_is_closed_and_read_only(
    tmp_path, monkeypatch, capsys, defect, as_json
):
    runtime_root, output_base_root = _roots(tmp_path, monkeypatch)
    path = operator_profile_path()
    if defect.startswith("state_"):
        if defect == "state_file":
            path.parent.write_bytes(b"not a directory")
        else:
            try:
                path.parent.symlink_to(runtime_root, target_is_directory=True)
            except OSError:
                pytest.skip("directory symlinks unavailable")
    else:
        enable_operator_profile(
            runtime_root=runtime_root, output_base_root=output_base_root,
            expected_predecessor_sha256=None,
        )
        if defect == "json":
            path.write_bytes(b"not JSON: private details")
        elif defect == "hash":
            raw = path.read_bytes()
            digest = json.loads(raw)["content_sha256"].encode()
            path.write_bytes(raw.replace(digest, b"sha256:" + b"0" * 64))
        elif defect == "runtime_missing":
            runtime_root.rmdir()
        elif defect == "output_missing":
            output_base_root.rmdir()
        elif defect == "profile_directory":
            path.unlink()
            path.mkdir()
        elif defect == "hardlink":
            try:
                os.link(path, tmp_path / "profile-alias.json")
            except OSError:
                pytest.skip("hardlinks unavailable")
        elif defect == "profile_symlink":
            target = tmp_path / "profile-target.json"
            path.rename(target)
            try:
                path.symlink_to(target)
            except OSError:
                pytest.skip("file symlinks unavailable")
    before = _inventory(tmp_path)

    code = main(["live-policy", "status", *(["--json"] if as_json else [])])

    assert code == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "invalid",
        "diagnostic_only": True,
        "runtime_write_performed": False,
        "error_code": "operator_profile_invalid",
    }
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("environment", ["missing", "relative", "nonexistent", "file"])
def test_status_environment_error_is_distinct_and_sanitized(
    tmp_path, monkeypatch, capsys, environment
):
    if environment == "missing":
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
    else:
        value = "private-relative-root" if environment == "relative" else str(tmp_path / "private-root")
        if environment == "file":
            Path(value).write_bytes(b"not a directory")
        monkeypatch.setenv("LOCALAPPDATA", value)
    before = _inventory(tmp_path)

    assert main(["live-policy", "status", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "invalid",
        "diagnostic_only": True,
        "runtime_write_performed": False,
        "error_code": "operator_profile_environment_invalid",
    }
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("option", [
    ["--runtime-root", "runtime"], ["--output-base-root", "output"],
    ["--expected-absent"], ["--expected-predecessor-sha256", "sha256:" + "0" * 64],
])
def test_status_rejects_mutation_operands(option):
    with pytest.raises(SystemExit) as error:
        _build_parser().parse_args(["live-policy", "status", *option])
    assert error.value.code == 2


@pytest.mark.parametrize("failure", [
    FileNotFoundError("private-path disappeared after probe"),
    PermissionError("private-path access denied"),
    RuntimeError("private-path resolution failed"),
    ValueError("private-path binding invalid"),
])
def test_status_sanitizes_expected_late_failures(monkeypatch, capsys, failure):
    def failed_read():
        raise failure

    monkeypatch.setattr(live_policy, "load_operator_profile_if_present", failed_read)
    assert main(["live-policy", "status", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "invalid",
        "diagnostic_only": True,
        "runtime_write_performed": False,
        "error_code": "operator_profile_invalid",
    }
