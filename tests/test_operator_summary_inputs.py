from __future__ import annotations

import contextlib
import hashlib
import io
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

import hsconfig.package_builder as package_builder
from hsconfig.operator_summary import build_operator_summary_from_inputs
from hsconfig.operator_summary_inputs import (
    OperatorAuthorityInputs,
    OperatorDiagnosticInputs,
    OperatorSummaryInputs,
    freeze_operator_summary_inputs,
    load_operator_summary_inputs,
)
from hsconfig.package_model import DirectoryPackageView
from tests.helpers import fixture_prepare as fixture_prepare_helper
from tests.helpers.fixture_prepare import (
    fixture_path_for,
    load_archetype_matrix,
    prepare_fixture_deck,
)


_SHADOWPRIEST_BASE_OID_SHA256 = (
    "sha256:028ce659ae0ad214fc77d5efbd310d00"
    "d566d191f55920789aeeb913a453a53f"
)
_OPERATOR_MODULES = (
    "hsconfig.operator_integrity",
    "hsconfig.operator_summary_evaluator",
    "hsconfig.operator_summary_inputs",
    "hsconfig.operator_status",
    "hsconfig.operator_diagnostics",
    "hsconfig.operator_summary",
)
_EMPTY_VALID_SUMMARY_SHA256 = (
    "sha256:b33278befd0aac8678539e4c6c5f5ef"
    "c2bb242df4354f9845c40b908f9405cf1"
)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("first_module", _OPERATOR_MODULES)
def test_operator_modules_support_every_isolated_import_order(
    first_module: str,
) -> None:
    imports = "; ".join(
        f"import {module}"
        for module in _OPERATOR_MODULES
    )
    script = (
        "import hashlib, json; "
        f"import {first_module}; {imports}; "
        "from hsconfig.operator_summary_inputs import "
        "freeze_operator_summary_inputs; "
        "from hsconfig.operator_status import build_operator_status; "
        "from hsconfig.operator_summary import "
        "build_operator_summary_from_inputs; "
        "inputs=freeze_operator_summary_inputs("
        "technical_validation={'status':'passed','errors':[]}); "
        "assert build_operator_status(inputs).technical_status "
        "== 'VALID_PACKAGE'; "
        "summary=build_operator_summary_from_inputs(inputs); "
        "payload=json.dumps(summary,ensure_ascii=False,"
        "separators=(',',':'),sort_keys=True).encode('utf-8'); "
        "assert 'sha256:'+hashlib.sha256(payload).hexdigest() "
        f"== {_EMPTY_VALID_SUMMARY_SHA256!r}"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, (
        completed.stdout + completed.stderr
    )


class _PoisonablePackageView:
    def __init__(self, files: Mapping[str, bytes]) -> None:
        self.files = dict(files)
        self.file_names_calls = 0
        self.read_counts: dict[str, int] = {}
        self.poisoned = False

    def file_names(self) -> tuple[str, ...]:
        if self.poisoned:
            raise AssertionError("original view reused")
        self.file_names_calls += 1
        return tuple(self.files)

    def read_bytes(self, relative_path: str) -> bytes:
        if self.poisoned:
            raise AssertionError("original view reused")
        self.read_counts[relative_path] = (
            self.read_counts.get(relative_path, 0) + 1
        )
        return self.files[relative_path]

    def read_json(self, relative_path: str) -> Any:
        raise AssertionError("loader must snapshot bytes, not live JSON")

    def exists(self, relative_path: str) -> bool:
        raise AssertionError("loader must use its one file-name snapshot")


def test_in_memory_freezer_owns_deeply_immutable_inputs() -> None:
    technical = {"status": "passed", "errors": []}
    guide = {"depth_status": "source_informed", "nested": [{"value": 1}]}
    generated = ["reports/validation_report.json"]

    inputs = freeze_operator_summary_inputs(
        deck_name="Frozen",
        deck_code="AAE=",
        technical_validation=technical,
        guide_source_depth=guide,
        generated_files=generated,
    )

    assert isinstance(inputs, OperatorSummaryInputs)
    assert isinstance(inputs.authority, OperatorAuthorityInputs)
    assert isinstance(inputs.diagnostics, OperatorDiagnosticInputs)
    technical["status"] = "failed"
    guide["nested"][0]["value"] = 2
    generated.append("poisoned.json")
    assert inputs.authority.technical_validation["status"] == "passed"
    assert inputs.diagnostics.guide_source_depth["nested"] == (
        {"value": 1},
    )
    assert inputs.diagnostics.generated_files == (
        "reports/validation_report.json",
    )
    with pytest.raises(TypeError):
        inputs.authority.technical_validation["status"] = "failed"  # type: ignore[index]
    with pytest.raises(TypeError):
        inputs.diagnostics.guide_source_depth["nested"][0]["value"] = 9  # type: ignore[index]


def test_direct_public_authority_construction_owns_nested_values() -> None:
    technical = {"status": "passed", "nested": [{"value": 1}]}
    authority = OperatorAuthorityInputs(
        technical_validation=technical,
        package_derivation=None,
        package_authority=None,
        deck_input_verification_report=None,
        strict_package_validation=True,
        actual_runtime_surface_inventory=True,
        deck_input_verification=True,
        source_receipt_validity=True,
        source_acquisition_eligibility=True,
        derivation_receipt_validity=True,
        package_summary_parity=True,
    )

    technical["status"] = "failed"
    technical["nested"][0]["value"] = 2

    assert authority.technical_validation["status"] == "passed"
    assert authority.technical_validation["nested"] == ({"value": 1},)
    with pytest.raises(TypeError):
        authority.technical_validation["status"] = "failed"  # type: ignore[index]


def test_direct_public_diagnostic_and_summary_construction_owns_values() -> None:
    base = freeze_operator_summary_inputs(
        technical_validation={"status": "passed", "errors": []},
    )
    guide = {"nested": [{"value": 1}]}
    legacy = {"technical_validation": {"status": "passed"}}
    diagnostics = replace(
        base.diagnostics,
        guide_source_depth=guide,
    )
    inputs = OperatorSummaryInputs(
        deck_name="Direct",
        deck_code="AAE=",
        package_label="memory://direct",
        authority=base.authority,
        diagnostics=diagnostics,
        legacy_kwargs=legacy,
    )

    guide["nested"][0]["value"] = 2
    legacy["technical_validation"]["status"] = "failed"

    assert diagnostics.guide_source_depth["nested"] == ({"value": 1},)
    assert inputs.legacy_kwargs["technical_validation"]["status"] == (
        "passed"
    )


def test_freezer_owns_siblings_before_one_mulligan_projection() -> None:
    technical = {"status": "passed", "errors": []}

    class _SideEffectingMulligan:
        calls = 0

        def to_report(self) -> dict[str, Any]:
            self.calls += 1
            technical["status"] = "failed"
            return {
                "rules": [],
                "suppressed_rules": [],
                "bot_delegated": [],
            }

    mulligan = _SideEffectingMulligan()
    inputs = freeze_operator_summary_inputs(
        technical_validation=technical,
        mulligan_plan_report=mulligan,
    )

    assert mulligan.calls == 1
    assert inputs.authority.technical_validation["status"] == "passed"
    assert inputs.diagnostics.mulligan_plan_report["rules"] == ()


def test_freezer_rejects_unsupported_custom_values() -> None:
    with pytest.raises(
        TypeError,
        match="^operator_summary_input_value_unsupported$",
    ):
        freeze_operator_summary_inputs(
            technical_validation={"status": "passed", "errors": []},
            gameplan_contract={"unsupported": object()},
        )


def test_freezer_preserves_legacy_aliases_and_noop_keyword() -> None:
    inputs = freeze_operator_summary_inputs(
        deck_name="Aliases",
        deck_code="AAE=",
        validation_report={"status": "passed", "errors": []},
        guide_source_depth_report={"depth_status": "source_informed"},
        config_readiness_report={
            "summary": {"cards_needing_guide_claims": 1}
        },
        strong_promotion_report={"promotion_ready": False},
    )

    summary = build_operator_summary_from_inputs(inputs)

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert "strong_promotion_report" not in summary


def test_package_loader_snapshots_each_file_once_and_never_reuses_view() -> None:
    stored_poison = {
        "schema_version": 1,
        "technical_status": "POISONED",
        "semantic_status": "POISONED",
        "next_action": "POISONED",
        "apply_policy": "POISONED",
        "runtime_apply_allowed": "POISONED",
        "runtime_apply_mode": "POISONED",
        "runtime_apply_reason": "POISONED",
        "runtime_load_safe": "POISONED",
        "runtime_apply_requires_flag": "POISONED",
        "load_safe_to_install": "POISONED",
        "use_config_now": "POISONED",
        "use_config_now_scope": "POISONED",
    }
    source = _PoisonablePackageView(
        {
            "reports/operator_summary.json": (
                b"\xef\xbb\xbf"
                + json.dumps(stored_poison).encode("utf-8")
            ),
            "reports/validation_report.json": json.dumps(
                {"status": "passed", "errors": []}
            ).encode("utf-8"),
        }
    )

    inputs = load_operator_summary_inputs(source)
    source.files.clear()
    source.poisoned = True

    assert source.file_names_calls == 1
    assert source.read_counts == {
        "reports/operator_summary.json": 1,
        "reports/validation_report.json": 1,
    }
    actual = build_operator_summary_from_inputs(inputs)
    assert actual["technical_status"] == "INVALID_PACKAGE"
    assert actual["runtime_apply_allowed"] is False
    assert actual["runtime_apply_reason"] == (
        "technical_validation_failed"
    )
    assert "POISONED" not in json.dumps(actual, sort_keys=True)


@pytest.mark.parametrize(
    ("receipt_payload", "expected_reason"),
    [
        (None, "package_derivation_receipt_missing"),
        (b"null", "package_derivation_receipt_invalid"),
        (b"[]", "package_derivation_receipt_invalid"),
        (b"{", "package_derivation_receipt_invalid"),
    ],
)
def test_package_replay_invalid_derivation_receipt_fails_closed(
    receipt_payload: bytes | None,
    expected_reason: str,
) -> None:
    stored_allowed = {
        "technical_status": "VALID_PACKAGE",
        "semantic_status": "NEEDS_MORE_RESEARCH",
        "next_action": "READY_TO_APPLY_WITH_WARNINGS",
        "apply_policy": "ALLOWED_WITH_WARNINGS",
        "runtime_load_safe": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_allowed": True,
        "runtime_apply_reason": "runtime_load_safe_package",
        "runtime_apply_requires_flag": None,
        "load_safe_to_install": True,
        "use_config_now": True,
        "use_config_now_scope": "load_safety_only",
    }
    files = {
        "reports/operator_summary.json": json.dumps(
            stored_allowed
        ).encode("utf-8"),
        "reports/validation_report.json": json.dumps(
            {"status": "passed", "errors": []}
        ).encode("utf-8"),
    }
    if receipt_payload is not None:
        files["package_derivation_receipt.json"] = receipt_payload
    source = _PoisonablePackageView(files)

    inputs = load_operator_summary_inputs(source)
    actual = build_operator_summary_from_inputs(inputs)

    assert inputs.authority.package_derivation is not None
    assert inputs.authority.package_authority is not None
    assert inputs.authority.package_authority[
        "source_apply_eligibility_reasons"
    ] == (expected_reason,)
    assert actual["technical_status"] == "INVALID_PACKAGE"
    assert actual["runtime_apply_allowed"] is False
    assert actual["runtime_apply_mode"] == "blocked"
    assert actual["runtime_apply_reason"] == (
        "technical_validation_failed"
    )


@pytest.mark.parametrize(
    ("file_names", "message"),
    [
        (
            (
                "reports/operator_summary.json",
                "reports/operator_summary.json",
            ),
            "operator_summary_package_path_duplicate",
        ),
        (
            ("reports/../operator_summary.json",),
            "operator_summary_package_path_invalid",
        ),
        (
            ("reports\\operator_summary.json",),
            "operator_summary_package_path_invalid",
        ),
    ],
)
def test_package_loader_rejects_noncanonical_or_duplicate_paths(
    file_names: tuple[str, ...],
    message: str,
) -> None:
    class _PathView(_PoisonablePackageView):
        def file_names(self) -> tuple[str, ...]:
            self.file_names_calls += 1
            return file_names

    source = _PathView(
        {"reports/operator_summary.json": b"{}"}
    )

    with pytest.raises(ValueError, match=f"^{message}$"):
        load_operator_summary_inputs(source)


def test_physical_shadowpriest_replay_matches_complete_base_oid_oracle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        package_builder,
        "fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    shadow = next(
        row
        for row in load_archetype_matrix()
        if row["deck_name"] == "ShadowPriest"
    )
    source_fixture = fixture_path_for(shadow)
    canonical_source_fixture = tmp_path / "shadowpriest-source.json"
    canonical_source_fixture.write_bytes(
        source_fixture.read_text(encoding="utf-8")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .encode("utf-8")
    )
    monkeypatch.setattr(
        fixture_prepare_helper,
        "fixture_path_for",
        lambda _deck: canonical_source_fixture,
    )
    with contextlib.redirect_stdout(io.StringIO()):
        prepared = prepare_fixture_deck(tmp_path, shadow)
    assert prepared["exit_code"] == 0
    inputs = load_operator_summary_inputs(
        DirectoryPackageView(prepared["out"])
    )

    actual = build_operator_summary_from_inputs(inputs)

    assert _canonical_sha256(actual) == _SHADOWPRIEST_BASE_OID_SHA256
