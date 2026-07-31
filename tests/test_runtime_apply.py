from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.current_output import (
    OutputPublication,
    PackageInputLease,
)
from hsconfig.io import read_json, write_json
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    DERIVATION_RECEIPT_SCHEMA_VERSION,
    build_package_derivation_receipt,
    write_package_derivation_receipt,
)
from hsconfig.runtime_apply import apply_package, plan_apply_package
from hsconfig.runtime_installer import RuntimeInstallResult
from tests.helpers.current_apply_eligible_package import (
    write_current_pre_run_contract,
)
from tests.helpers.current_globalvalues_contract import (
    GLOBALVALUES_AUTHORITY_MATRIX_PATH,
    write_current_globalvalues_contract,
)
from tests.helpers.current_runtime_surface_ledger_contract import (
    write_current_runtime_surface_ledger,
)
from tests.helpers.verified_deck_input import install_verified_deck_input


def _write_operator_summary_with_derivation(
    package: Path,
    summary: dict,
) -> None:
    reports = package / "reports"
    summary = {
        **summary,
        "apply_policy": "ALLOWED_WITH_WARNINGS",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_reason": "runtime_load_safe_package",
    }
    manifest = read_json(reports / "input_manifest.json")
    deck_name = str(manifest.get("deck_name", "deck"))
    deck_input_verification = install_verified_deck_input(
        package,
        deck_name=deck_name,
    )
    write_json(reports / "guide_claim_bundle.json", {"canonical_source_receipts": []})
    write_json(reports / "card_behavior_plan_report.json", {"rows": []})
    write_current_runtime_surface_ledger(package)
    write_current_pre_run_contract(package)
    generated = summary.get("generated_files", [])
    ownership = build_output_ownership_manifest(
        [
            *generated,
            GLOBALVALUES_AUTHORITY_MATRIX_PATH,
            DERIVATION_RECEIPT_PATH,
            "reports/operator_summary.json",
            "reports/output_ownership_manifest.json",
        ]
    )
    write_json(reports / "output_ownership_manifest.json", ownership)
    receipt = build_package_derivation_receipt(package)
    digest = write_package_derivation_receipt(
        package / DERIVATION_RECEIPT_PATH,
        receipt,
    )
    write_json(
        reports / "operator_summary.json",
        {
            **summary,
            "deck_input_verification": deck_input_verification,
            "package_derivation": {
                "schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION,
                "receipt_path": DERIVATION_RECEIPT_PATH,
                "receipt_sha256": digest,
                "verified": True,
            },
        },
    )


def _complete_package(
    tmp_path: Path,
    *,
    semantic_status: str,
    next_action: str,
    apply_policy: str,
    source_informed_apply_readiness: dict | None = None,
) -> Path:
    package = tmp_path / "package"
    deck = package / "CustomConfig" / "deck"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "new"}
    write_json(deck / "GlobalValues.json", globalvalues)
    write_json(
        deck / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "new",
            "Mulligan": {"values": []},
        },
    )
    write_json(
        deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "fixture"},
    )
    write_current_globalvalues_contract(package, globalvalues)
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Gate Deck", "runtime_root": "unused"},
    )
    summary = {
        "technical_status": "VALID_PACKAGE",
        "semantic_status": semantic_status,
        "next_action": next_action,
        "apply_policy": apply_policy,
        "semantic_blockers": [],
        "generated_files": [
            "CustomConfig/deck/GlobalValues.json",
            "CustomConfig/deck/Mulligan.json",
            "CustomConfig/deck/EX1_001.json",
        ],
    }
    if source_informed_apply_readiness is not None:
        summary["source_informed_apply_readiness"] = source_informed_apply_readiness
    _write_operator_summary_with_derivation(package, summary)
    return package


def _allowed_package(tmp_path: Path) -> Path:
    return _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )


def _published_lease(
    package: Path,
) -> tuple[Path, PackageInputLease]:
    digest = "a" * 64
    output_root = package.parent / "published"
    revision = output_root / "revisions" / f"sha256-{digest}"
    published_package = revision / "04_package"
    revision.mkdir(parents=True)
    package.rename(published_package)
    publication = OutputPublication(
        schema_version=1,
        deck_name="Gate Deck",
        deck_fingerprint="b" * 64,
        revision=f"revisions/sha256-{digest}",
        content_root_sha256=digest,
    )
    return output_root, PackageInputLease(
        package_root=published_package,
        publication=publication,
        content_root_sha256=digest,
        output_root=output_root,
        snapshot=None,
    )


def _install_plan(package: Path, runtime: Path) -> SimpleNamespace:
    return SimpleNamespace(
        deck_name="Gate Deck",
        logical_config_dir="deck",
        versioned_config_dir="deck--sha256-" + "c" * 64,
        package_root_sha256="c" * 64,
        source_package_root=package,
        runtime_root=runtime,
    )


def _patch_published_apply(
    monkeypatch: pytest.MonkeyPatch,
    lease: PackageInputLease,
    runtime: Path,
    *,
    statuses: list[str],
) -> list[str]:
    from hsconfig import runtime_apply

    events: list[str] = []

    @contextmanager
    def fake_lease(_input: Path):
        events.append("lease_enter")
        try:
            yield lease
        finally:
            events.append("lease_exit")

    plan = _install_plan(lease.package_root, runtime)

    def fake_plan(*, published_output, runtime_root):
        assert published_output.package_root == lease.package_root
        assert runtime_root == runtime
        events.append("plan")
        return plan

    def fake_install(received):
        assert received is plan
        assert events[-1] == "lease_exit"
        events.append("install")
        status = statuses.pop(0)
        return RuntimeInstallResult(
            status=status,
            config_dir=plan.versioned_config_dir,
            package_root_sha256=plan.package_root_sha256,
            previous_config_dir=None,
            receipt_path=(
                runtime / ".hsconfig" / "receipts" / "deck" / "last_apply_receipt.json"
                if status != "committed_receipt_pending"
                else None
            ),
        )

    monkeypatch.setattr(runtime_apply, "lease_package_input", fake_lease)
    monkeypatch.setattr(runtime_apply, "plan_runtime_install", fake_plan)
    monkeypatch.setattr(runtime_apply, "install_runtime_package", fake_install)
    return events


def test_plan_is_pure_and_fake_loose_package_is_supported(tmp_path: Path) -> None:
    package = _allowed_package(tmp_path)

    receipt = plan_apply_package(
        package_root=package,
        runtime_root=tmp_path / "runtime",
    )

    assert receipt["status"] == "fake_apply_ready"
    assert receipt["config_dir"] == "deck"
    assert not (package / "reports" / "runtime_apply_fake_receipt.json").exists()


def test_plan_config_dir_is_an_assertion_not_override(tmp_path: Path) -> None:
    package = _allowed_package(tmp_path)

    with pytest.raises(ValueError, match="config_dir_mismatch"):
        plan_apply_package(
            package_root=package,
            runtime_root=tmp_path / "runtime",
            config_dir="another-deck",
        )


def test_caller_gate_cannot_bypass_operator_summary(tmp_path: Path) -> None:
    package = _allowed_package(tmp_path)
    supplied = evaluate_apply_gate(package)
    supplied = {**supplied, "policy": "ALLOWED"}

    with pytest.raises(ValueError, match="apply_gate_mismatch"):
        plan_apply_package(
            package_root=package,
            runtime_root=tmp_path / "runtime",
            apply_gate=supplied,
        )


def test_loose_real_apply_requires_published_output(tmp_path: Path) -> None:
    package = _allowed_package(tmp_path)
    runtime = tmp_path / "runtime"

    with pytest.raises(TypeError, match="published_output_required"):
        apply_package(package_root=package, runtime_root=runtime)

    assert not runtime.exists()


@pytest.mark.parametrize(
    ("status", "write_performed"),
    [
        ("applied", True),
        ("already_current", False),
        ("recovered", False),
        ("committed_receipt_pending", True),
    ],
)
def test_published_apply_preserves_installer_status_and_honest_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    write_performed: bool,
) -> None:
    package = _allowed_package(tmp_path)
    output_root, lease = _published_lease(package)
    runtime = tmp_path / "runtime"
    events = _patch_published_apply(
        monkeypatch,
        lease,
        runtime,
        statuses=[status],
    )

    result = apply_package(package_root=output_root, runtime_root=runtime)

    assert result["status"] == status
    assert result["runtime_write_performed"] is write_performed
    assert result["mapped_deck_name"] == "Gate Deck"
    assert result["logical_config_dir"] == "deck"
    assert result["versioned_config_dir"].startswith("deck--sha256-")
    assert result["package_root_sha256"] == "c" * 64
    assert set(result) == {
        "status",
        "runtime_write_performed",
        "mapped_deck_name",
        "logical_config_dir",
        "versioned_config_dir",
        "package_root_sha256",
        "previous_config_dir",
        "receipt_path",
        "apply_gate",
    }
    assert events == ["lease_enter", "plan", "lease_exit", "install"]


def test_direct_active_published_package_is_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _allowed_package(tmp_path)
    _, lease = _published_lease(package)
    runtime = tmp_path / "runtime"
    _patch_published_apply(monkeypatch, lease, runtime, statuses=["applied"])

    result = apply_package(
        package_root=lease.package_root,
        runtime_root=runtime,
    )

    assert result["status"] == "applied"


def test_from_fake_receipt_is_verified_before_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _allowed_package(tmp_path)
    output_root, lease = _published_lease(package)
    runtime = tmp_path / "runtime"
    fake = plan_apply_package(
        package_root=lease.package_root,
        runtime_root=runtime,
    )
    _patch_published_apply(monkeypatch, lease, runtime, statuses=["applied"])

    result = apply_package(
        package_root=output_root,
        runtime_root=runtime,
        fake_receipt=fake,
    )

    assert result["status"] == "applied"


def test_compatibility_flags_do_not_reactivate_legacy_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _allowed_package(tmp_path)
    output_root, lease = _published_lease(package)
    runtime = tmp_path / "runtime"
    _patch_published_apply(monkeypatch, lease, runtime, statuses=["already_current"])

    result = apply_package(
        package_root=output_root,
        runtime_root=runtime,
        replace=False,
        allow_source_informed=True,
        write_history=True,
    )

    assert result["status"] == "already_current"
    assert not (runtime / "CustomConfig" / "hsconfig_write_history.jsonl").exists()
