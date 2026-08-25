from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsconfig.cli import _build_parser, main
from hsconfig.operator_profile import operator_profile_path


def _roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    local_app_data = tmp_path / "local-app-data"
    runtime_root = tmp_path / "runtime"
    output_base_root = tmp_path / "outputs"
    local_app_data.mkdir()
    runtime_root.mkdir()
    output_base_root.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    return runtime_root, output_base_root


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
