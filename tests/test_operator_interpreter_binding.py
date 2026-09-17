"""Interpreter diagnostics never adopt or rewrite a mismatched profile."""

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from hsconfig.cli import main
from hsconfig import live_start_controller as controller
from hsconfig import operator_profile
from hsconfig.operator_profile import (
    disable_operator_profile,
    enable_operator_profile,
    load_operator_profile,
    operator_profile_path,
)
from tests.test_live_policy_cli import _inventory, _roots


@pytest.mark.parametrize("stored,current,expected", [
    ((17, 12, 16895), ((1 << 48) + 17, 12, 16895), True),
    (((1 << 48) + 17, 12, 16895), (17, 12, 16895), True),
    ((17, 12, 16895), (17, 12, 16895), False),
    ((17, 12, 16895), (18, 12, 16895), False),
    ((17, 12, 16895), ((1 << 48) + 18, 12, 16895), False),
    ((17, 12, 16895), ((1 << 48) + 17, 13, 16895), False),
    ((17, 12, 16895), ((1 << 48) + 17, 12, 16894), False),
    (((1 << 40) + 17, 12, 16895), ((1 << 48) + 17, 12, 16895), False),
])
def test_device_width_diagnostic_pattern_is_exact_on_every_platform(stored, current, expected):
    assert operator_profile._has_device_encoding_difference(stored, current) is expected


def _profile(tmp_path, monkeypatch, state="enabled"):
    runtime, output = _roots(tmp_path, monkeypatch)
    if state == "absent":
        return None
    profile = enable_operator_profile(
        runtime_root=runtime, output_base_root=output,
        expected_predecessor_sha256=None,
    )
    if state == "disabled":
        profile = disable_operator_profile(
            expected_predecessor_sha256=profile.content_sha256,
        )
    return profile


def _change_stored_identity(*, changed_roots, other_drift=None):
    path = operator_profile_path()
    document = json.loads(path.read_bytes())
    for field in changed_roots:
        identity = document[field]
        device = identity[0]
        identity[0] = device & 0xFFFFFFFF if device > 0xFFFFFFFF else device | (1 << 48)
    if other_drift:
        field, component = other_drift
        document[field][component] += 1
    del document["content_sha256"]

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

    document["content_sha256"] = "sha256:" + sha256(canonical(document)).hexdigest()
    path.write_bytes(canonical(document))


@pytest.mark.parametrize("state", ["enabled", "disabled", "absent"])
def test_runtime_info_reports_the_executing_python_without_mutating_profile(
    tmp_path, monkeypatch, capsys, state,
):
    _profile(tmp_path, monkeypatch, state)
    before = _inventory(tmp_path)
    assert main(["live-policy", "status", "--runtime-info", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == state
    assert result["runtime_info"] == {
        "python_executable": sys.executable,
        "python_version": list(sys.version_info[:3]),
        "package_root": str(Path(controller.__file__).resolve().parent),
    }
    assert result["runtime_write_performed"] is False
    assert _inventory(tmp_path) == before


def test_reported_python_can_revalidate_the_same_profile_in_a_fresh_process(
    tmp_path, monkeypatch, capsys,
):
    profile = _profile(tmp_path, monkeypatch)
    assert main(["live-policy", "status", "--runtime-info", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    before = _inventory(tmp_path)
    completed = subprocess.run(
        [result["runtime_info"]["python_executable"], "-B", "-m", "hsconfig",
         "live-policy", "status", "--json"],
        text=True, capture_output=True, check=False, timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    assert observed["status"] == "enabled"
    assert observed["content_sha256"] == profile.content_sha256
    assert "runtime_info" not in observed
    assert _inventory(tmp_path) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows 3.11/3.12 device encoding")
@pytest.mark.parametrize("changed_roots", [
    ("runtime_root_identity",),
    ("output_base_root_identity",),
    ("runtime_root_identity", "output_base_root_identity"),
])
def test_device_encoding_conflict_is_specific_but_still_rejected(
    tmp_path, monkeypatch, capsys, changed_roots,
):
    _profile(tmp_path, monkeypatch)
    _change_stored_identity(changed_roots=changed_roots)
    before = _inventory(tmp_path)
    with pytest.raises(ValueError, match="operator_profile_identity_encoding_mismatch"):
        load_operator_profile()
    assert main(["live-policy", "status", "--runtime-info", "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "invalid"
    assert result["error_code"] == "operator_profile_identity_encoding_mismatch"
    assert result["runtime_write_performed"] is False
    assert result["runtime_info"]["python_executable"] == sys.executable
    assert main(["live-policy", "status", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "operator_profile_invalid"
    assert _inventory(tmp_path) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows 3.11/3.12 device encoding")
@pytest.mark.parametrize("other_drift", [
    ("runtime_root_identity", 1), ("runtime_root_identity", 2),
    ("output_base_root_identity", 1), ("output_base_root_identity", 2),
    ("output_base_root_identity", 0),
])
def test_real_identity_drift_is_not_relabelled_as_interpreter_conflict(
    tmp_path, monkeypatch, capsys, other_drift,
):
    _profile(tmp_path, monkeypatch)
    _change_stored_identity(
        changed_roots=("runtime_root_identity",), other_drift=other_drift,
    )
    before = _inventory(tmp_path)
    assert main(["live-policy", "status", "--runtime-info", "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "invalid"
    assert result["error_code"] == "operator_profile_invalid"
    assert _inventory(tmp_path) == before


@pytest.mark.skipif(os.name != "nt", reason="Windows 3.11/3.12 device encoding")
@pytest.mark.parametrize("preview", [False, True])
def test_quality_prepare_reports_encoding_conflict_before_network_or_session(
    tmp_path, monkeypatch, preview,
):
    _profile(tmp_path, monkeypatch)
    _change_stored_identity(changed_roots=("runtime_root_identity",))
    before = _inventory(tmp_path)

    def no_network(**kwargs):
        raise AssertionError("profile conflict must stop before acquisition")

    monkeypatch.setattr(controller, "fetch_card_snapshot", no_network)
    result = controller.prepare_quality_live_start(controller.LiveStartRequest(
        "ShadowPriest",
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        preview,
    ))
    assert result.status == "PROFILE_REQUIRED"
    assert result.summary.to_value()["error_code"] == "operator_profile_identity_encoding_mismatch"
    assert result.run_root is None
    assert _inventory(tmp_path) == before
