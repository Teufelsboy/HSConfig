from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import hsconfig.strict_package_validation as strict_package_validation
from hsconfig.cli import main
from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.configure_run_model import (
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
)
from hsconfig.contract_preflight import build_package_contract_preflight
from hsconfig.io import read_json, write_json
from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.package_render_authority import AuthorityArtifact
from hsconfig.run_manifest import (
    build_tree_manifest_from_artifacts,
    write_tree_manifest,
)
from hsconfig.runtime_surface_ledger import rederive_runtime_surface_ledger_from_package
from hsconfig.strict_package_validation import (
    validate_complete_configure_run_from_view,
    validate_complete_package,
)
from tests.helpers.audited_package_request import audited_request
from tests.helpers.verified_deck_input import VERIFIED_TEST_DECK_CODE


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ({"status": "passed", "errors": []}, True),
        ({"status": "passed", "errors": ["contradictory error"]}, False),
        ({"status": "failed", "errors": []}, False),
        ({}, False),
    ],
)
def test_strict_validation_passed_requires_clean_passed_report(
    report: dict[str, Any],
    expected: bool,
) -> None:
    from hsconfig.strict_package_validation import strict_validation_passed

    assert strict_validation_passed(report) is expected


class _OneReadPackageView:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = dict(files)
        self.read_counts: dict[str, int] = {}
        self.enumerations = 0

    def file_names(self) -> tuple[str, ...]:
        self.enumerations += 1
        if self.enumerations > 1:
            raise AssertionError("live view enumerated more than once")
        return tuple(reversed(sorted(self.files)))

    def read_bytes(self, relative_path: str) -> bytes:
        count = self.read_counts.get(relative_path, 0) + 1
        self.read_counts[relative_path] = count
        if count > 1:
            raise AssertionError(f"live file read more than once: {relative_path}")
        try:
            return self.files[relative_path]
        except KeyError as error:
            raise FileNotFoundError(relative_path) from error

    def read_json(self, relative_path: str) -> Any:
        raise AssertionError(f"live JSON read bypassed snapshot: {relative_path}")

    def exists(self, relative_path: str) -> bool:
        raise AssertionError(f"live existence check bypassed snapshot: {relative_path}")


@pytest.fixture(scope="module")
def strict_run(
    tmp_path_factory: pytest.TempPathFactory,
) -> RenderedConfigureRun:
    root = tmp_path_factory.mktemp("strict-run")
    package = assemble_package(
        compile_package(audited_request(root, "ShadowPriest"))
    )
    return render_configure_run_model(
        create_configure_run_model(
            package=package,
            stage_artifacts={
                "01_manifest/input.json": b"{}\n",
                "02_source_documents/source.json": b"{}\n",
                "03_research/research.json": b"{}\n",
            },
        )
    )


def _run_files(rendered: RenderedConfigureRun) -> dict[str, bytes]:
    return {
        artifact.relative_path: artifact.content
        for artifact in rendered.artifacts
    }


def _remanifest_run_files(
    rendered: RenderedConfigureRun,
    files: dict[str, bytes],
) -> dict[str, bytes]:
    changed = dict(files)
    artifacts = tuple(
        AuthorityArtifact.from_content(
            relative_path=path,
            content=content,
        )
        for path, content in sorted(changed.items())
        if path != "package_manifest.json"
    )
    changed["package_manifest.json"] = write_tree_manifest(
        build_tree_manifest_from_artifacts(
            deck_name=rendered.model.deck_name,
            deck_fingerprint=rendered.model.deck_fingerprint,
            artifacts=artifacts,
        )
    )
    return changed


def test_strict_run_validation_snapshots_once_then_validates_package(
    strict_run: RenderedConfigureRun,
) -> None:
    source = _OneReadPackageView(_run_files(strict_run))

    report = validate_complete_configure_run_from_view(source)

    assert report["status"] == "passed"
    assert report["errors"] == []
    assert source.enumerations == 1
    assert set(source.read_counts) == set(source.files)
    assert set(source.read_counts.values()) == {1}


def test_strict_run_validation_rejects_manifest_before_package_semantics(
    strict_run: RenderedConfigureRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _run_files(strict_run)
    files["01_manifest/input.json"] = b'{"tampered":true}\n'
    source = _OneReadPackageView(files)
    monkeypatch.setattr(
        strict_package_validation,
        "validate_complete_package_from_view",
        lambda _package: pytest.fail(
            "package semantics ran before manifest verification"
        ),
    )

    report = validate_complete_configure_run_from_view(source)

    assert report == {
        "status": "failed",
        "errors": ["run_manifest_invalid"],
        "checked_files": 0,
    }


def test_strict_run_validation_rejects_remanifested_forged_summary(
    strict_run: RenderedConfigureRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _run_files(strict_run)
    summary = json.loads(files["configure_summary.json"])
    summary["deck_fingerprint"] = "0" * 64
    files["configure_summary.json"] = (
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    files = _remanifest_run_files(strict_run, files)
    monkeypatch.setattr(
        strict_package_validation,
        "validate_complete_package_from_view",
        lambda _package: pytest.fail(
            "package semantics ran after forged configure summary"
        ),
    )

    report = validate_complete_configure_run_from_view(
        _OneReadPackageView(files)
    )

    assert report == {
        "status": "failed",
        "errors": ["run_manifest_invalid"],
        "checked_files": 0,
    }


@pytest.mark.parametrize(
    "mutation",
    ("missing_required_stages", "forged_unavailable_stages"),
)
def test_strict_run_rejects_self_consistent_invalid_stage_tree(
    strict_run: RenderedConfigureRun,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    files = _run_files(strict_run)
    if mutation == "missing_required_stages":
        files = {
            path: content
            for path, content in files.items()
            if not path.startswith(("01_", "02_", "03_"))
        }
    else:
        summary = json.loads(files["configure_summary.json"])
        summary["unavailable_stages"] = {}
        files["configure_summary.json"] = (
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    files = _remanifest_run_files(strict_run, files)
    monkeypatch.setattr(
        strict_package_validation,
        "validate_complete_package_from_view",
        lambda _package: pytest.fail(
            "package semantics ran after invalid stage tree"
        ),
    )

    report = validate_complete_configure_run_from_view(
        _OneReadPackageView(files)
    )

    assert report == {
        "status": "failed",
        "errors": ["run_manifest_invalid"],
        "checked_files": 0,
    }


@pytest.mark.parametrize(
    "alias_path",
    ("04_PACKAGE/evil.json", "04_Package/evil.json"),
)
def test_strict_run_rejects_remanifested_package_root_alias(
    strict_run: RenderedConfigureRun,
    monkeypatch: pytest.MonkeyPatch,
    alias_path: str,
) -> None:
    files = _run_files(strict_run)
    content = b"hostile\n"
    files[alias_path] = content
    payload = json.loads(files["package_manifest.json"])
    payload["entries"].append(
        {
            "relative_path": alias_path,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    )
    payload["entries"].sort(key=lambda row: row["relative_path"])
    records = b"".join(
        (
            f"{row['relative_path']}\0{row['size']}\0"
            f"{row['sha256']}\n"
        ).encode("utf-8")
        for row in payload["entries"]
    )
    payload["content_root_sha256"] = hashlib.sha256(
        records
    ).hexdigest()
    files["package_manifest.json"] = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    monkeypatch.setattr(
        strict_package_validation,
        "validate_complete_package_from_view",
        lambda _package: pytest.fail(
            "package semantics ran after package-root alias"
        ),
    )

    report = validate_complete_configure_run_from_view(
        _OneReadPackageView(files)
    )

    assert report == {
        "status": "failed",
        "errors": ["run_manifest_invalid"],
        "checked_files": 0,
    }


@pytest.mark.parametrize("mutation", ("missing", "malformed"))
def test_strict_run_maps_verified_package_structure_errors_to_failed_report(
    strict_run: RenderedConfigureRun,
    mutation: str,
) -> None:
    files = _run_files(strict_run)
    baseline_path = (
        "04_package/reports/globalvalues_baseline.json"
    )
    if mutation == "missing":
        del files[baseline_path]
    else:
        files[baseline_path] = b"{"
    files = _remanifest_run_files(strict_run, files)

    report = validate_complete_configure_run_from_view(
        _OneReadPackageView(files)
    )

    assert report == {
        "status": "failed",
        "errors": ["package_validation_invalid"],
        "checked_files": 0,
    }


def test_strict_run_validation_propagates_base_exception(
    strict_run: RenderedConfigureRun,
) -> None:
    class InjectedBaseFault(BaseException):
        pass

    class InterruptedView(_OneReadPackageView):
        def read_bytes(self, relative_path: str) -> bytes:
            if relative_path == "package_manifest.json":
                raise InjectedBaseFault("interrupt")
            return super().read_bytes(relative_path)

    with pytest.raises(InjectedBaseFault, match="interrupt"):
        validate_complete_configure_run_from_view(
            InterruptedView(_run_files(strict_run))
        )


def test_strict_run_validation_propagates_package_semantic_base_exception(
    strict_run: RenderedConfigureRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InjectedBaseFault(BaseException):
        pass

    monkeypatch.setattr(
        strict_package_validation,
        "validate_complete_package_from_view",
        lambda _package: (_ for _ in ()).throw(
            InjectedBaseFault("semantic interrupt")
        ),
    )

    with pytest.raises(InjectedBaseFault, match="semantic interrupt"):
        validate_complete_configure_run_from_view(
            _OneReadPackageView(_run_files(strict_run))
        )


def test_strict_run_validation_uses_verified_package_snapshot_for_semantics(
    strict_run: RenderedConfigureRun,
) -> None:
    files = _run_files(strict_run)
    globalvalues_path = next(
        path
        for path in files
        if path.startswith("04_package/CustomConfig/")
        and path.endswith("/GlobalValues.json")
    )
    files[globalvalues_path] = b"{}\n"
    artifacts = tuple(
        AuthorityArtifact.from_content(
            relative_path=path,
            content=content,
        )
        for path, content in sorted(files.items())
        if path != "package_manifest.json"
    )
    files["package_manifest.json"] = write_tree_manifest(
        build_tree_manifest_from_artifacts(
            deck_name=strict_run.model.deck_name,
            deck_fingerprint=strict_run.model.deck_fingerprint,
            artifacts=artifacts,
        )
    )

    report = validate_complete_configure_run_from_view(
        _OneReadPackageView(files)
    )

    assert report["status"] == "failed"
    assert "run_manifest_invalid" not in report["errors"]


def test_strict_validation_rejects_unexpected_physical_sideboard_emission(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    reports = package / "reports"
    deck_dir = next((package / "CustomConfig").iterdir())
    deck_identity_path = reports / "deck_identity.json"
    deck_identity = json.loads(deck_identity_path.read_text(encoding="utf-8"))
    deck_identity["sideboards"] = [
        {
            "owner_card_id": deck_identity["cards"][0]["card_id"],
            "cards": [{"card_id": "SIDE_001", "count": 1}],
        }
    ]
    write_json(deck_identity_path, deck_identity)
    write_json(
        deck_dir / "SIDE_001.json",
        {
            "GameCardId": "SIDE_001",
            "BeforePlayCardBonus": {
                "values": [{"condition": "*", "value": "1"}]
            },
        },
    )
    ledger = rederive_runtime_surface_ledger_from_package(package)
    assert ledger["schema_version"] == 2
    assert ledger["unexpected_runtime_emissions"] == [
        {"card_id": "SIDE_001", "reason": "ineligible_card_runtime_emitted"}
    ]
    write_json(reports / "runtime_surface_ledger.json", ledger)

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert (
        "runtime_surface_ledger_unexpected_emission:"
        "SIDE_001:ineligible_card_runtime_emitted"
    ) in report["errors"]


@pytest.mark.parametrize("schema_version", [True, 2.0])
def test_strict_validation_rejects_non_integer_ledger_schema_version(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    schema_version: object,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    ledger_path = package / "reports" / "runtime_surface_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["schema_version"] = schema_version
    write_json(ledger_path, ledger)

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert "runtime_surface_ledger_schema_invalid" in report["errors"]


def test_strict_validation_compares_nested_canonical_types(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    ledger_path = package / "reports" / "runtime_surface_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert type(ledger["globalvalues_emitted"]) is bool
    ledger["globalvalues_emitted"] = int(ledger["globalvalues_emitted"])
    write_json(ledger_path, ledger)

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert "runtime_surface_ledger_content_mismatch" in report["errors"]


@pytest.mark.parametrize("mutation", ["missing", "tampered", "stale"])
def test_strict_validation_requires_current_canonical_runtime_surface_ledger(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    ledger_path = package / "reports" / "runtime_surface_ledger.json"
    if mutation == "missing":
        ledger_path.unlink()
    elif mutation == "tampered":
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger["cards"] = {}
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    else:
        deck_dir = next((package / "CustomConfig").iterdir())
        mulligan_path = deck_dir / "Mulligan.json"
        mulligan = json.loads(mulligan_path.read_text(encoding="utf-8"))
        mulligan["Mulligan"]["values"] = [
            {
                "comment": "stale ledger mutation",
                "mulligan": "STALE_CARD",
                "condition": "*",
                "value": "hold",
            }
        ]
        mulligan_path.write_text(json.dumps(mulligan), encoding="utf-8")

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(error.startswith("runtime_surface_ledger_") for error in report["errors"])


def _run_cli(capsys: pytest.CaptureFixture[str], args: list[str]) -> tuple[dict[str, Any], int]:
    code = main([*args, "--json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out), code


def _clean_quality_report(_package: Path) -> dict[str, Any]:
    return {
        "status": "clean",
        "checks": {
            "operator_summary": {
                "present": True,
                "source_status_apply_blocking": False,
                "default_only_runtime_surfaces": [],
            },
            "closure_freshness": {
                "closure_schema_current": True,
                "cards_missing_closure": 0,
            },
            "config_intent_self_audit": {"status": "clean"},
            "surface_intent_projection": {
                "status": "clean",
                "present": True,
                "surface_count": 3,
                "fallback_intent_rows": [],
                "legacy_policy_surface_rows": [],
                "first_attention": None,
            },
        },
        "problems": [],
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
    }


def _mutate_published_globalvalues_report(
    package: Path,
    mutation: str,
) -> None:
    reports = package / "reports"
    if mutation == "missing_baseline":
        (reports / "globalvalues_baseline.json").unlink()
    elif mutation == "missing_profile":
        (reports / "globalvalues_profile.json").unlink()
    elif mutation == "missing_authority_matrix":
        (reports / "global_values_authority_matrix.json").unlink()
    else:
        path = reports / "globalvalues_profile.json"
        mutated_profile = deepcopy(read_json(path))
        mutated_profile["missing_overlay_keys"] = ["GlobalMinionAttack"]
        write_json(path, mutated_profile)


def _build_fixture(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[dict[str, Any], int]:
    return _run_cli(
        capsys,
        [
            "build",
            "--deck-name",
            "Strict Fixture",
            "--deck-code",
            VERIFIED_TEST_DECK_CODE,
            "--runtime-root",
            str(tmp_path / "build-runtime"),
            "--out",
            str(tmp_path / "build-package"),
        ],
    )


@pytest.mark.parametrize(
    "forgery",
    ["generated_overlay", "baseline_overlay"],
)
def test_strict_validation_binds_globalvalues_to_canonical_authority_matrix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    forgery: str,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    reports = package / "reports"
    deck_dir = next((package / "CustomConfig").iterdir())
    config_path = deck_dir / "GlobalValues.json"
    profile_path = reports / "globalvalues_profile.json"
    authority = json.loads(
        (reports / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert {
        row["key"] for row in authority["allowed_step1_overlays"]
    } == {"baseline"}

    if forgery == "generated_overlay":
        key = "MyHeroPowerValue"
        config[key] = {"values": [{"condition": "*", "value": "1.15"}]}
        profile["generated_overlay_keys"] = [key]
        profile["expected_overlay_keys"] = [key]
        profile["authority_parity"] = {
            "authorized_overlay_keys": [key],
            "emitted_overlay_keys": [key],
            "status": "matched",
        }
        profile["keys"][key] = {
            "decision": "overlay_changed",
            "status": "overlay_changed",
            "reason": "forged generated overlay",
        }
        profile["key_count"] = len(config)
    else:
        key = "GlobalMinionAttack"
        config[key]["values"][0]["value"] = "999"
        profile["baseline_overlay_parity"] = {
            "authorized_overlay_keys": [key],
            "emitted_overlay_keys": [key],
            "status": "matched",
        }
        profile["keys"][key].update(
            {
                "decision": "overlay_changed",
                "status": "overlay_changed",
                "new_value": "999",
                "reason": "forged baseline overlay",
            }
        )
        profile["changed_keys"] = [key]
        profile["unchanged_keys"] = [
            existing
            for existing in profile["unchanged_keys"]
            if existing != key
        ]

    profile["summary"].update(
        {
            "authority_parity": profile["authority_parity"],
            "baseline_overlay_parity": profile["baseline_overlay_parity"],
            "changed_key_count": len(profile["changed_keys"]),
            "unchanged_key_count": len(profile["unchanged_keys"]),
            "expected_overlay_key_count": len(profile["expected_overlay_keys"]),
            "generated_overlay_key_count": len(profile["generated_overlay_keys"]),
            "key_count": profile["key_count"],
        }
    )
    write_json(config_path, config)
    write_json(profile_path, profile)

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        "GlobalValues config does not match canonical authority matrix" in error
        or "GlobalValues profile does not match canonical authority matrix" in error
        for error in report["errors"]
    )


def test_strict_validation_rejects_internally_consistent_authorized_key39(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    reports = package / "reports"
    deck_dir = next((package / "CustomConfig").iterdir())
    baseline = json.loads(
        (reports / "globalvalues_baseline.json").read_text(encoding="utf-8")
    )
    authority = {
        "aggression_profile": "hero_power_pressure",
        "posture": "hero_power_pressure",
        "allowed_step1_overlays": [
            {
                "key": "MyHeroPowerValue",
                "overlay": "increase",
                "operation": "increase",
                "value": None,
                "authority": "step1_source_backed_posture",
                "claim_id": "forged-key39",
                "claim_refs": ["forged-key39"],
                "reason": "forged authorized key39",
            }
        ],
        "blocked_until_runtime_evidence": [],
    }
    forged = compile_globalvalues(
        baseline,
        {"global_values_authority_matrix": authority},
    )
    write_json(deck_dir / "GlobalValues.json", forged["config"])
    write_json(reports / "globalvalues_profile.json", forged["profile"])
    write_json(reports / "global_values_authority_matrix.json", authority)
    write_json(
        reports / "runtime_surface_ledger.json",
        rederive_runtime_surface_ledger_from_package(package),
    )

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        "globalvalues_authority_overlay_key_not_baseline:MyHeroPowerValue"
        in error
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    "expression",
    ["True", "False", "-True", "True + 1"],
)
def test_strict_validation_rejects_boolean_authority_expression(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    expression: str,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    authority = {
        "aggression_profile": "turn_weight",
        "posture": "turn_weight",
        "allowed_step1_overlays": [
            {
                "key": "FirstTurnValueWeight",
                "overlay": f"set:{expression}",
                "operation": "set",
                "value": expression,
                "authority": "step1_source_backed_posture",
                "claim_id": "boolean-expression",
                "claim_refs": ["boolean-expression"],
                "reason": "boolean expression must not be numeric",
            }
        ],
        "blocked_until_runtime_evidence": [],
    }
    write_json(
        package / "reports" / "global_values_authority_matrix.json",
        authority,
    )

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        "globalvalues_authority_overlay_value_invalid:FirstTurnValueWeight"
        in error
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            "string_schema",
            "GlobalValues profile schema_version must be a non-bool integer",
        ),
        (
            "schema_downgrade",
            "GlobalValues authority matrix requires profile schema_version 2",
        ),
        (
            "duplicate_ledgers",
            "GlobalValues profile generated_overlay_keys contains duplicate key "
            "MyHeroPowerValue",
        ),
    ],
)
def test_strict_validation_rejects_schema_downgrade_and_duplicate_ledgers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
    expected_error: str,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    reports = package / "reports"
    deck_dir = next((package / "CustomConfig").iterdir())
    config_path = deck_dir / "GlobalValues.json"
    profile_path = reports / "globalvalues_profile.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    if mutation == "string_schema":
        profile["schema_version"] = "2"
    elif mutation == "schema_downgrade":
        profile["schema_version"] = 1
        profile.pop("authority_parity")
        profile.pop("baseline_overlay_parity")
        profile["summary"].pop("authority_parity")
        profile["summary"].pop("baseline_overlay_parity")
    else:
        key = "MyHeroPowerValue"
        profile["schema_version"] = 1
        profile.pop("authority_parity")
        profile.pop("baseline_overlay_parity")
        profile["summary"].pop("authority_parity")
        profile["summary"].pop("baseline_overlay_parity")
        config[key] = {"values": [{"condition": "*", "value": "1.15"}]}
        profile["generated_overlay_keys"] = [key, key]
        profile["expected_overlay_keys"] = [key, key]
        profile["keys"][key] = {
            "decision": "overlay_changed",
            "status": "overlay_changed",
            "reason": "forged duplicate ledger",
        }
        profile["key_count"] = len(config)

    write_json(config_path, config)
    write_json(profile_path, profile)

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(expected_error in error for error in report["errors"])


@pytest.mark.parametrize("remove_ownership_marker", [False, True])
def test_strict_validation_rejects_deleted_matrix_self_downgrade(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    remove_ownership_marker: bool,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    reports = package / "reports"
    deck_dir = next((package / "CustomConfig").iterdir())
    config_path = deck_dir / "GlobalValues.json"
    profile_path = reports / "globalvalues_profile.json"
    matrix_path = reports / "global_values_authority_matrix.json"
    ownership = json.loads(
        (reports / "output_ownership_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(
        row.get("file") == "reports/global_values_authority_matrix.json"
        for row in ownership["files"]
    )

    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    key = "GlobalMinionAttack"
    config[key]["values"][0]["value"] = "999"
    profile["schema_version"] = 1
    profile.pop("authority_parity")
    profile.pop("baseline_overlay_parity")
    profile["summary"].pop("authority_parity")
    profile["summary"].pop("baseline_overlay_parity")
    profile["keys"][key].update(
        {
            "decision": "overlay_changed",
            "status": "overlay_changed",
            "new_value": "999",
            "reason": "forged after deleting canonical matrix",
        }
    )
    profile["changed_keys"] = [key]
    profile["unchanged_keys"] = [
        existing
        for existing in profile["unchanged_keys"]
        if existing != key
    ]
    matrix_path.unlink()
    if remove_ownership_marker:
        ownership["files"] = [
            row
            for row in ownership["files"]
            if row.get("file")
            != "reports/global_values_authority_matrix.json"
        ]
        write_json(reports / "output_ownership_manifest.json", ownership)
    write_json(config_path, config)
    write_json(profile_path, profile)

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        "GlobalValues current contract requires authority matrix"
        in error
        for error in report["errors"]
    )


def test_legacy_globalvalues_validation_requires_explicit_opt_in(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    reports = package / "reports"
    profile_path = reports / "globalvalues_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["schema_version"] = 1
    profile.pop("authority_parity")
    profile.pop("baseline_overlay_parity")
    profile["summary"].pop("authority_parity")
    profile["summary"].pop("baseline_overlay_parity")
    (reports / "global_values_authority_matrix.json").unlink()
    write_json(profile_path, profile)

    default_report = validate_complete_package(package)
    legacy_report = validate_complete_package(
        package,
        allow_legacy_globalvalues=True,
    )

    assert default_report["status"] == "failed"
    assert legacy_report["status"] == "passed"


def test_current_pre_run_reports_are_required_and_legacy_is_version_bound(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    reports = package / "reports"
    for name in (
        "layered_evidence_contract.json",
        "source_acquisition_closure.json",
        "disposition_ledger.json",
        "globalvalues_decision_ledger.json",
        "pre_run_closure.json",
    ):
        (reports / name).unlink()

    current = validate_complete_package(package)
    assert current["status"] == "failed"
    assert any(
        "pre_run_current_reports_missing" in error
        for error in current["errors"]
    )

    manifest_path = reports / "input_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("pre_run_contract_schema_version")
    manifest.pop("source_acquisition_input_binding")
    write_json(manifest_path, manifest)

    unversioned = validate_complete_package(package)
    explicit_legacy = validate_complete_package(
        package,
        legacy_pre_run_contract_version=0,
    )
    wrong_legacy_version = validate_complete_package(
        package,
        legacy_pre_run_contract_version=1,
    )

    assert unversioned["status"] == "failed"
    assert wrong_legacy_version["status"] == "failed"
    assert explicit_legacy["status"] == "passed"


@pytest.fixture
def linked_owner_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    deck_dir = next((package / "CustomConfig").iterdir())
    deck_identity_path = package / "reports" / "deck_identity.json"
    deck_identity = json.loads(deck_identity_path.read_text(encoding="utf-8"))
    deck_identity["cards"].append({"card_id": "SW_448", "count": 1})
    write_json(deck_identity_path, deck_identity)
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "claim_id": "claim_darkbishop",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "meaningful_runtime_surface": True,
                }
            ]
        },
    )
    write_json(
        deck_dir / "EX1_625t.json",
        {
            "GameCardId": "EX1_625t",
            "ConfigComment": "curated linked runtime owner",
            "BeforeUseHeroPowerBonus": {
                "values": [{"condition": "*", "value": "10"}]
            },
        },
    )
    return package


@pytest.mark.parametrize(
    "mutation",
    [
        "remove",
        "invalid_json",
        "non_object",
        "empty_rows",
        "invalid_rows_container",
    ],
)
def test_linked_owner_package_fails_closed_without_valid_plan_report(
    linked_owner_package: Path,
    mutation: str,
) -> None:
    path = linked_owner_package / "reports" / "card_behavior_plan_report.json"
    if mutation == "remove":
        path.unlink()
    elif mutation == "invalid_json":
        path.write_text("{", encoding="utf-8")
    elif mutation == "non_object":
        path.write_text("[]", encoding="utf-8")
    elif mutation == "empty_rows":
        write_json(path, {"rows": []})
    else:
        write_json(path, {"rows": {}})

    report = validate_complete_package(linked_owner_package)

    assert report["status"] == "failed"
    assert any(
        code in report["errors"]
        for code in {
            "linked_runtime_owner_evidence_missing",
            "linked_runtime_owner_evidence_invalid",
        }
    )


def test_linked_runtime_owner_projection_has_exact_authority_fields() -> None:
    projection = strict_package_validation.linked_runtime_owner_projection(
        {
            "rows": [
                {
                    "claim_id": "claim_darkbishop",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "meaningful_runtime_surface": True,
                    "diagnostic_prose": "must not enter authority",
                }
            ]
        }
    )

    assert projection == [
        {
            "source_card_id": "SW_448",
            "runtime_card_id": "EX1_625t",
            "link_kind": "hero_power_transform",
            "semantic_surface": "hero_power_before_use",
            "behavior_block": "BeforeUseHeroPowerBonus",
        }
    ]


@pytest.mark.parametrize(
    "rows",
    [{}, None, "corrupt", [None]],
    ids=["object", "null", "string", "non_object_row"],
)
def test_ownerless_package_rejects_invalid_behavior_plan_rows(
    linked_owner_package: Path,
    rows: object,
) -> None:
    for owner_path in (linked_owner_package / "CustomConfig").glob(
        "*/EX1_625t.json"
    ):
        owner_path.unlink()
    write_json(
        linked_owner_package
        / "reports"
        / "card_behavior_plan_report.json",
        {"rows": rows},
    )

    report = validate_complete_package(linked_owner_package)

    assert report["status"] == "failed"
    assert "linked_runtime_owner_evidence_invalid" in report["errors"]


@pytest.mark.parametrize(
    "rows",
    [{}, None, "corrupt", [None]],
    ids=["object", "null", "string", "non_object_row"],
)
def test_linked_runtime_owner_projection_rejects_invalid_rows(
    rows: object,
) -> None:
    with pytest.raises(
        ValueError,
        match="^linked_runtime_owner_evidence_invalid$",
    ):
        strict_package_validation.linked_runtime_owner_projection(
            {"rows": rows}
        )


def test_valid_package_passes_build_validate_apply_and_preflight(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    package = Path(build_result["package"])
    runtime = tmp_path / "runtime"

    validate_result, validate_code = _run_cli(
        capsys,
        ["validate", "--package", str(package)],
    )
    apply_result, apply_code = _run_cli(
        capsys,
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--fake",
        ],
    )
    monkeypatch.setattr(
        "hsconfig.config_quality_contract.build_config_quality_report",
        _clean_quality_report,
    )
    preflight = build_package_contract_preflight(package)

    assert build_code == 0
    assert build_result["status"] == "passed"
    assert validate_code == 0
    assert validate_result["status"] == "passed"
    assert apply_code == 0
    assert apply_result["status"] == "fake_apply_ready"
    assert not runtime.exists()
    assert preflight is not None
    assert preflight["validation_status"] == "passed"
    assert preflight["package_contract_current"] is True
    assert preflight["authority"] == "diagnostic_only"
    assert preflight["apply_blocking"] is False
    assert preflight["runtime_write_performed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_baseline",
        "missing_profile",
        "missing_authority_matrix",
        "missing_overlay_keys",
    ],
)
def test_invalid_globalvalues_reports_fail_all_strict_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)

    package = tmp_path / "build-package"
    _mutate_published_globalvalues_report(package, mutation)
    runtime = tmp_path / "runtime"

    validate_result, validate_code = _run_cli(
        capsys,
        ["validate", "--package", str(package)],
    )
    apply_result, apply_code = _run_cli(
        capsys,
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--fake",
        ],
    )
    monkeypatch.setattr(
        "hsconfig.config_quality_contract.build_config_quality_report",
        _clean_quality_report,
    )
    preflight = build_package_contract_preflight(package)

    assert preflight is not None
    assert preflight["validation_status"] == "failed"
    assert preflight["package_contract_current"] is False
    assert preflight["authority"] == "diagnostic_only"
    assert preflight["apply_blocking"] is False
    assert preflight["runtime_write_performed"] is False
    assert build_code == 0
    assert build_result["status"] == "passed"
    assert validate_code == 1
    assert validate_result["status"] == "failed"
    assert apply_code == 1
    assert apply_result["status"] in {"failed", "blocked"}
    assert not runtime.exists()


def test_strict_validation_rejects_linked_runtime_filename_gamecardid_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    deck_dir = next((package / "CustomConfig").iterdir())
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "claim_id": "claim_darkbishop",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "semantic_score": {
                        "semantic_reason": "hero_power_transform",
                    },
                    "meaningful_runtime_surface": True,
                }
            ]
        },
    )
    write_json(
        deck_dir / "EX1_625t.json",
        {
            "GameCardId": "SW_448",
            "ConfigComment": "wrong linked runtime owner",
            "BeforeUseHeroPowerBonus": {
                "values": [{"condition": "*", "value": "10"}]
            },
        },
    )
    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        "linked runtime entity filename/GameCardId mismatch: "
        "EX1_625t.json owns EX1_625t, got SW_448"
        in error
        for error in report["errors"]
    )


def test_strict_validation_rejects_post_build_linked_runtime_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    deck_dir = next((package / "CustomConfig").iterdir())
    deck_identity_path = package / "reports" / "deck_identity.json"
    deck_identity = json.loads(deck_identity_path.read_text(encoding="utf-8"))
    deck_identity["cards"].append({"card_id": "SW_448", "count": 1})
    write_json(deck_identity_path, deck_identity)
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "claim_id": "claim_darkbishop",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "semantic_score": {
                        "semantic_reason": "hero_power_transform",
                    },
                    "meaningful_runtime_surface": True,
                }
            ]
        },
    )
    write_json(
        deck_dir / "EX1_625t.json",
        {
            "GameCardId": "EX1_625t",
            "ConfigComment": "curated linked runtime owner",
            "BeforeUseHeroPowerBonus": {
                "values": [{"condition": "*", "value": "10"}]
            },
        },
    )
    write_json(
        package / "reports" / "runtime_surface_ledger.json",
        rederive_runtime_surface_ledger_from_package(package),
    )

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        "verified_emission_package_view_mismatch" in error
        for error in report["errors"]
    )


def test_strict_validation_rejects_linked_relation_masked_as_not_meaningful(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    deck_dir = next((package / "CustomConfig").iterdir())
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "claim_id": "masked_linked_owner",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "semantic_score": {
                        "semantic_reason": "hero_power_before_use",
                    },
                    "meaningful_runtime_surface": False,
                }
            ]
        },
    )
    write_json(
        deck_dir / "EX1_625t.json",
        {
            "GameCardId": "EX1_625t",
            "ConfigComment": "curated linked runtime owner",
            "BeforeUseHeroPowerBonus": {
                "values": [{"condition": "*", "value": "10"}]
            },
        },
    )

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        error.startswith("linked_runtime_entity_relation_invalid:")
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    (
        "source_card_id",
        "runtime_card_id",
        "link_kind",
        "behavior_block",
        "semantic_reason",
    ),
    [
        (
            "SW_448",
            "SW_448",
            "hero_power_transform",
            "BeforeUseHeroPowerBonus",
            "hero_power_transform",
        ),
        (
            "SW_448",
            "WRONG_TARGET",
            "hero_power_transform",
            "BeforeUseHeroPowerBonus",
            "hero_power_transform",
        ),
        (
            "SW_448",
            "EX1_625t",
            "wrong_link",
            "BeforeUseHeroPowerBonus",
            "hero_power_before_use",
        ),
        (
            "SW_448",
            "EX1_625t",
            "hero_power_transform",
            "OnBoardBonus",
            "hero_power_before_use",
        ),
        (
            "SW_448",
            "EX1_625t",
            "hero_power_transform",
            "BeforePlayCardBonus",
            "hero_power_before_use",
        ),
    ],
)
def test_strict_validation_rejects_non_curated_linked_runtime_relation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    source_card_id: str,
    runtime_card_id: str,
    link_kind: str,
    behavior_block: str,
    semantic_reason: str,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "claim_id": "invalid_linked_owner",
                    "card_id": source_card_id,
                    "source_card_id": source_card_id,
                    "runtime_card_id": runtime_card_id,
                    "link_kind": link_kind,
                    "behavior_block": behavior_block,
                    "semantic_score": {
                        "semantic_reason": semantic_reason,
                    },
                    "meaningful_runtime_surface": True,
                }
            ]
        },
    )

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        error.startswith("linked_runtime_entity_relation_invalid:")
        for error in report["errors"]
    )
