from __future__ import annotations

from contextlib import contextmanager
from inspect import signature
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from typing import Callable, Iterator

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
from hsconfig.output_operation_admission import OutputOperationAdmissionLease
from hsconfig.package_io import path_identity
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
) -> tuple[Path, SimpleNamespace]:
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
    return output_root, SimpleNamespace(
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
    lease: SimpleNamespace,
    runtime: Path,
    *,
    statuses: list[str | tuple[str, bool]],
) -> list[str]:
    from hsconfig import runtime_apply

    events: list[str] = []
    # This helper exercises result/status compatibility, not the separate
    # Task-10 absent-root bootstrap boundary covered below.
    runtime.mkdir(parents=True, exist_ok=True)

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
        assert events[-1] == "plan"
        active_context = runtime_apply._ACTIVE_OUTPUT_OPERATION_INSTALL.get()
        assert active_context is not None
        assert active_context.package_lease is lease
        assert active_context.expected_root_identity == path_identity(runtime)
        events.append("install")
        selected = statuses.pop(0)
        status, runtime_write_performed = (
            selected
            if isinstance(selected, tuple)
            else (selected, selected != "already_current")
        )
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
            runtime_write_performed=runtime_write_performed,
        )

    monkeypatch.setattr(runtime_apply, "lease_package_input", fake_lease)
    monkeypatch.setattr(
        runtime_apply,
        "revalidate_package_input_lease",
        lambda _lease: None,
    )
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


def test_runtime_apply_preserves_installer_public_signature() -> None:
    from hsconfig import runtime_apply, runtime_installer

    assert signature(runtime_apply.install_runtime_package) == signature(
        runtime_installer.install_runtime_package
    )


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
        ("already_current", True),
        ("recovered", True),
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
        statuses=[(status, write_performed)],
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
    assert events == ["lease_enter", "plan", "install", "lease_exit"]


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


# Task 10 keeps the compatibility-only missing-runtime-root route deliberately
# narrow.  These tests use the public writer with its surrounding capability
# leases stubbed only at the outer boundary: the assertions describe the order
# and data that the private legacy-root bearer must preserve before the normal
# installer is allowed to see a root.
def _patch_absent_root_apply_boundary(
    monkeypatch: pytest.MonkeyPatch,
    *,
    package: Path,
    runtime: Path,
    authorize: Callable[..., object],
    bootstrap: Callable[..., object],
    output_gate: Callable[..., None] | None = None,
    after_plan: Callable[[], None] | None = None,
) -> tuple[list[str], list[object]]:
    from hsconfig import runtime_apply

    events: list[str] = []
    install_plans: list[object] = []
    operation_lease = object()
    package_lease = SimpleNamespace(
        package_root=package,
        publication=object(),
        content_root_sha256="c" * 64,
        output_root=package.parent / "published",
        snapshot=object(),
    )
    plan = _install_plan(package, runtime)

    @contextmanager
    def fake_operation_lease() -> Iterator[object]:
        events.append("output_operation_enter")
        try:
            yield operation_lease
        finally:
            events.append("output_operation_exit")

    @contextmanager
    def fake_package_lease(_package_input: Path) -> Iterator[SimpleNamespace]:
        events.append("package_enter")
        try:
            yield package_lease
        finally:
            events.append("package_exit")

    def fake_output_gate(*, lease: object) -> None:
        assert lease is operation_lease
        events.append("output_operation_gate")
        if output_gate is not None:
            output_gate(lease=lease)

    def fake_authorize(**kwargs: object) -> object:
        events.append("legacy_root_authorize")
        assert kwargs["output_operation_lease"] is operation_lease
        assert kwargs["package_lease"] is package_lease
        assert kwargs["runtime_root"] == runtime
        return authorize(**kwargs)

    def fake_bootstrap(**kwargs: object) -> object:
        events.append("legacy_root_bootstrap")
        return bootstrap(**kwargs)

    def fake_plan(*, published_output: object, runtime_root: Path) -> object:
        assert runtime_root == runtime
        assert published_output is not None
        assert runtime.exists()
        events.append("runtime_plan")
        if after_plan is not None:
            after_plan()
        return plan

    def fake_install(received: object) -> RuntimeInstallResult:
        assert received is plan
        active_context = runtime_apply._ACTIVE_OUTPUT_OPERATION_INSTALL.get()
        assert active_context is not None
        assert active_context.operation_lease is operation_lease
        assert active_context.package_lease is package_lease
        if active_context.expected_root_identity != path_identity(runtime):
            raise ValueError("runtime_apply_root_identity_changed")
        install_plans.append(received)
        events.append("runtime_install")
        return RuntimeInstallResult(
            status="applied",
            config_dir=plan.versioned_config_dir,
            package_root_sha256=plan.package_root_sha256,
            previous_config_dir=None,
            receipt_path=None,
            runtime_write_performed=True,
        )

    monkeypatch.setattr(runtime_apply, "_bootstrap_neutral_output_locks", lambda: None)
    monkeypatch.setattr(
        runtime_apply,
        "lease_output_operation_admission",
        fake_operation_lease,
    )
    monkeypatch.setattr(
        runtime_apply,
        "require_output_operation_allows_runtime_mutation",
        fake_output_gate,
    )
    monkeypatch.setattr(runtime_apply, "_lease_real_apply_input", fake_package_lease)
    monkeypatch.setattr(
        runtime_apply,
        "revalidate_package_input_lease",
        lambda _lease: None,
    )
    monkeypatch.setattr(runtime_apply, "_validate_runtime_apply_package", lambda _package: None)
    monkeypatch.setattr(
        runtime_apply,
        "_resolve_allowed_apply_gate",
        lambda **_kwargs: {"allowed": True, "mode": "load_safe_apply"},
    )
    monkeypatch.setattr(runtime_apply, "_logical_config_dir", lambda *_args: "deck")
    monkeypatch.setattr(
        runtime_apply,
        "build_fake_apply_receipt",
        lambda **_kwargs: {"fake": "receipt"},
    )
    monkeypatch.setattr(runtime_apply, "verify_fake_apply_receipt", lambda **_kwargs: None)
    monkeypatch.setattr(
        runtime_apply,
        "_authorize_legacy_runtime_root_bootstrap_from_context",
        fake_authorize,
    )
    monkeypatch.setattr(
        runtime_apply,
        "_bootstrap_legacy_runtime_root_from_context",
        fake_bootstrap,
    )
    monkeypatch.setattr(runtime_apply, "plan_runtime_install", fake_plan)
    monkeypatch.setattr(runtime_apply, "install_runtime_package", fake_install)
    return events, install_plans


def _production_legacy_root_bootstrap_context(
    *,
    tmp_path: Path,
    package: Path,
) -> tuple[OutputOperationAdmissionLease, PackageInputLease]:
    state_root = tmp_path / "output-operation-state"
    locks_root = state_root / "locks"
    locks_root.mkdir(parents=True)
    lock_path = locks_root / "output-operation.lock"
    lock_path.write_bytes(b"")
    operation_lease = OutputOperationAdmissionLease(
        state_root=state_root,
        state_root_identity=path_identity(state_root),
        locks_root_identity=path_identity(locks_root),
        lock_path=lock_path,
        lock_identity=path_identity(lock_path),
        lock_token=object(),  # type: ignore[arg-type]
    )
    package_lease = PackageInputLease(
        package_root=package,
        publication=None,
        content_root_sha256=None,
        output_root=None,
        snapshot=None,
        lock_token=object(),  # type: ignore[arg-type]
    )
    return operation_lease, package_lease


def test_public_apply_preserves_absent_runtime_root_contract_after_output_operation_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _allowed_package(tmp_path)
    runtime = tmp_path / "fresh-runtime"
    created: list[Path] = []

    def authorize(**kwargs: object) -> object:
        assert kwargs["expected_predecessor_identity"] is None
        assert kwargs["config_dir"] == "deck"
        return object()

    def bootstrap(*, authorization: object, **_kwargs: object) -> object:
        assert authorization is not None
        runtime.mkdir()
        created.append(runtime)
        return SimpleNamespace(
            runtime_root=runtime,
            successor_identity=path_identity(runtime),
        )

    events, installed = _patch_absent_root_apply_boundary(
        monkeypatch,
        package=package,
        runtime=runtime,
        authorize=authorize,
        bootstrap=bootstrap,
    )

    result = apply_package(package_root=package.parent / "published", runtime_root=runtime)

    assert result["status"] == "applied"
    assert created == [runtime]
    assert installed
    assert events == [
        "output_operation_enter",
        "output_operation_gate",
        "package_enter",
        "legacy_root_authorize",
        "legacy_root_bootstrap",
        "runtime_plan",
        "runtime_install",
        "package_exit",
        "output_operation_exit",
    ]


def test_public_installer_creates_absent_runtime_root_only_after_output_operation_and_package_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _allowed_package(tmp_path)
    runtime = tmp_path / "fresh-runtime"
    observed_before_create: list[tuple[bool, bool]] = []

    def authorize(**_kwargs: object) -> object:
        assert not runtime.exists()
        return object()

    def bootstrap(**_kwargs: object) -> object:
        observed_before_create.append(
            ("output_operation_gate" in events, "package_enter" in events)
        )
        runtime.mkdir()
        return SimpleNamespace(
            runtime_root=runtime,
            successor_identity=path_identity(runtime),
        )

    events, _installed = _patch_absent_root_apply_boundary(
        monkeypatch,
        package=package,
        runtime=runtime,
        authorize=authorize,
        bootstrap=bootstrap,
    )

    apply_package(package_root=package.parent / "published", runtime_root=runtime)

    assert observed_before_create == [(True, True)]
    assert events.index("output_operation_gate") < events.index("package_enter")
    assert events.index("package_enter") < events.index("legacy_root_authorize")
    assert events.index("legacy_root_authorize") < events.index("legacy_root_bootstrap")


def test_public_installer_fresh_root_hard_kill_resumes_before_any_semantic_runtime_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _allowed_package(tmp_path)
    runtime = tmp_path / "fresh-runtime"

    def authorize(**_kwargs: object) -> object:
        return object()

    def hard_kill_before_root_mutation(**_kwargs: object) -> object:
        raise KeyboardInterrupt("legacy_root_bootstrap_before_mkdir")

    _events, installed = _patch_absent_root_apply_boundary(
        monkeypatch,
        package=package,
        runtime=runtime,
        authorize=authorize,
        bootstrap=hard_kill_before_root_mutation,
    )

    with pytest.raises(KeyboardInterrupt, match="legacy_root_bootstrap_before_mkdir"):
        apply_package(package_root=package.parent / "published", runtime_root=runtime)

    assert not runtime.exists()
    assert not (runtime / ".hsconfig").exists()
    assert not (runtime / "apply.lock").exists()
    assert installed == []


def test_active_output_or_runtime_admission_keeps_absent_runtime_root_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _allowed_package(tmp_path)
    runtime = tmp_path / "fresh-runtime"

    def blocked_by_active_runtime_admission(**_kwargs: object) -> object:
        raise ValueError("runtime_live_admission_blocks_legacy_root_bootstrap")

    def unreachable_bootstrap(**_kwargs: object) -> object:
        raise AssertionError("legacy bootstrap must not run behind an admission")

    _events, installed = _patch_absent_root_apply_boundary(
        monkeypatch,
        package=package,
        runtime=runtime,
        authorize=blocked_by_active_runtime_admission,
        bootstrap=unreachable_bootstrap,
    )

    with pytest.raises(
        ValueError,
        match="runtime_live_admission_blocks_legacy_root_bootstrap",
    ):
        apply_package(package_root=package.parent / "published", runtime_root=runtime)

    assert not runtime.exists()
    assert installed == []


def test_fresh_runtime_root_parent_or_root_substitution_fails_before_hsconfig_or_runtime_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _allowed_package(tmp_path)
    runtime = tmp_path / "fresh-runtime"
    displaced = tmp_path / "displaced-authorized-runtime"

    def authorize(**_kwargs: object) -> object:
        return object()

    def bootstrap(**_kwargs: object) -> object:
        runtime.mkdir()
        return SimpleNamespace(
            runtime_root=runtime,
            successor_identity=path_identity(runtime),
        )

    def substitute_root_after_plan() -> None:
        runtime.rename(displaced)
        runtime.mkdir()

    _events, installed = _patch_absent_root_apply_boundary(
        monkeypatch,
        package=package,
        runtime=runtime,
        authorize=authorize,
        bootstrap=bootstrap,
        after_plan=substitute_root_after_plan,
    )

    with pytest.raises(ValueError, match="runtime_apply_root_identity_changed"):
        apply_package(package_root=package.parent / "published", runtime_root=runtime)

    assert runtime.exists()
    assert displaced.exists()
    assert not (runtime / ".hsconfig").exists()
    assert not (runtime / "apply.lock").exists()
    assert installed == []


def test_direct_legacy_root_bootstrap_cannot_bypass_active_runtime_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig import runtime_apply

    package = _allowed_package(tmp_path)
    runtime = tmp_path / "fresh-runtime"
    operation_lease, package_lease = (
        _production_legacy_root_bootstrap_context(
            tmp_path=tmp_path,
            package=package,
        )
    )
    apply_gate = {"allowed": True, "mode": "load_safe_apply"}
    fake_receipt = {"fake": "receipt"}
    admission_checks: list[Path] = []

    monkeypatch.setattr(
        runtime_apply,
        "require_output_operation_allows_runtime_mutation",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        runtime_apply,
        "revalidate_package_input_lease",
        lambda _lease: None,
    )
    monkeypatch.setattr(
        runtime_apply,
        "_resolve_allowed_apply_gate",
        lambda **_kwargs: dict(apply_gate),
    )
    monkeypatch.setattr(
        runtime_apply,
        "verify_fake_apply_receipt",
        lambda **_kwargs: None,
    )

    def active_admission(*, runtime_root: Path) -> None:
        admission_checks.append(runtime_root)
        raise ValueError("runtime_live_admission_blocks_legacy_root_bootstrap")

    monkeypatch.setattr(
        runtime_apply,
        "require_live_admission_allows_legacy_root_bootstrap",
        active_admission,
    )

    with pytest.raises(
        ValueError,
        match="runtime_live_admission_blocks_legacy_root_bootstrap",
    ):
        runtime_apply._authorize_legacy_runtime_root_bootstrap_from_context(
            output_operation_lease=operation_lease,
            package_lease=package_lease,
            runtime_root=runtime,
            expected_predecessor_identity=None,
            bound_ancestor_path=tmp_path,
            bound_ancestor_identity=path_identity(tmp_path),
            config_dir="deck",
            apply_gate=apply_gate,
            fake_apply_receipt=fake_receipt,
        )

    assert admission_checks == [runtime]
    assert not runtime.exists()


def test_legacy_root_bootstrap_rechecks_runtime_admission_immediately_before_first_mkdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig import runtime_apply

    package = _allowed_package(tmp_path)
    runtime = tmp_path / "fresh-runtime"
    operation_lease, package_lease = (
        _production_legacy_root_bootstrap_context(
            tmp_path=tmp_path,
            package=package,
        )
    )
    apply_gate = {"allowed": True, "mode": "load_safe_apply"}
    fake_receipt = {"fake": "receipt"}
    admission_checks: list[bool] = []
    created: list[Path] = []
    blocked = False

    monkeypatch.setattr(
        runtime_apply,
        "require_output_operation_allows_runtime_mutation",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        runtime_apply,
        "revalidate_package_input_lease",
        lambda _lease: None,
    )
    monkeypatch.setattr(
        runtime_apply,
        "_resolve_allowed_apply_gate",
        lambda **_kwargs: dict(apply_gate),
    )
    monkeypatch.setattr(
        runtime_apply,
        "verify_fake_apply_receipt",
        lambda **_kwargs: None,
    )

    def admission_gate(*, runtime_root: Path) -> None:
        assert runtime_root == runtime
        admission_checks.append(blocked)
        if blocked:
            raise ValueError(
                "runtime_live_admission_blocks_legacy_root_bootstrap"
            )

    real_create = runtime_apply.secure_create_directory

    def tracked_create(
        path: Path,
        *,
        expected_parent_identity: tuple[int, int, int],
    ) -> tuple[int, int, int]:
        created.append(path)
        return real_create(
            path,
            expected_parent_identity=expected_parent_identity,
        )

    monkeypatch.setattr(
        runtime_apply,
        "require_live_admission_allows_legacy_root_bootstrap",
        admission_gate,
    )
    monkeypatch.setattr(
        runtime_apply,
        "secure_create_directory",
        tracked_create,
    )
    authorization = (
        runtime_apply._authorize_legacy_runtime_root_bootstrap_from_context(
            output_operation_lease=operation_lease,
            package_lease=package_lease,
            runtime_root=runtime,
            expected_predecessor_identity=None,
            bound_ancestor_path=tmp_path,
            bound_ancestor_identity=path_identity(tmp_path),
            config_dir="deck",
            apply_gate=apply_gate,
            fake_apply_receipt=fake_receipt,
        )
    )

    def activate_admission(_point: object) -> None:
        nonlocal blocked
        blocked = True

    with pytest.raises(
        ValueError,
        match="runtime_live_admission_blocks_legacy_root_bootstrap",
    ):
        runtime_apply._bootstrap_legacy_runtime_root_from_context(
            authorization=authorization,
            fault_hook=activate_admission,
        )

    assert admission_checks == [False, True]
    assert created == []
    assert not runtime.exists()


@pytest.mark.parametrize("surface", ["staging", "reserved_temp", "malformed"])
def test_legacy_root_bootstrap_authorization_rejects_output_operation_staging_temp_or_malformed_surfaces_before_mkdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    package = _allowed_package(tmp_path)
    runtime = tmp_path / "fresh-runtime"

    def reject_surface(**_kwargs: object) -> object:
        raise ValueError(f"output_operation_admission_{surface}_invalid")

    _events, installed = _patch_absent_root_apply_boundary(
        monkeypatch,
        package=package,
        runtime=runtime,
        authorize=reject_surface,
        bootstrap=lambda **_kwargs: pytest.fail("bootstrap must be unreachable"),
    )

    with pytest.raises(ValueError, match=f"output_operation_admission_{surface}_invalid"):
        apply_package(package_root=package.parent / "published", runtime_root=runtime)

    assert not runtime.exists()
    assert installed == []


@pytest.mark.parametrize(
    "invalid_authorization",
    ["forged", "stale", "reused", "cross_thread", "wrong_root", "wrong_gate"],
)
def test_legacy_root_bootstrap_authorization_rejects_forged_stale_reused_cross_thread_wrong_root_or_unvalidated_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_authorization: str,
) -> None:
    from hsconfig import runtime_apply

    package = _allowed_package(tmp_path)
    runtime = tmp_path / "fresh-runtime"
    operation_lease, package_lease = (
        _production_legacy_root_bootstrap_context(
            tmp_path=tmp_path,
            package=package,
        )
    )
    apply_gate = evaluate_apply_gate(package)
    fake_receipt = runtime_apply.build_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime,
        config_dir="deck",
        apply_gate=apply_gate,
    )
    issued_authorizations: list[object] = []

    monkeypatch.setattr(
        runtime_apply,
        "require_output_operation_allows_runtime_mutation",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        runtime_apply,
        "revalidate_package_input_lease",
        lambda _lease: None,
    )
    monkeypatch.setattr(
        runtime_apply,
        "require_live_admission_allows_legacy_root_bootstrap",
        lambda **_kwargs: None,
    )

    def authorize() -> object:
        authorization = (
            runtime_apply._authorize_legacy_runtime_root_bootstrap_from_context(
                output_operation_lease=operation_lease,
                package_lease=package_lease,
                runtime_root=runtime,
                expected_predecessor_identity=None,
                bound_ancestor_path=tmp_path,
                bound_ancestor_identity=path_identity(tmp_path),
                config_dir="deck",
                apply_gate=apply_gate,
                fake_apply_receipt=fake_receipt,
            )
        )
        issued_authorizations.append(authorization)
        return authorization

    def assert_authorization_consumed(authorization: object) -> None:
        with pytest.raises(
            ValueError,
            match=(
                "legacy_runtime_root_bootstrap_authorization_"
                "inactive_or_forged"
            ),
        ):
            runtime_apply._bootstrap_legacy_runtime_root_from_context(
                authorization=authorization,
            )

    try:
        authorization = authorize()

        if invalid_authorization == "forged":
            forged = object.__new__(type(authorization))
            object.__setattr__(
                forged,
                "_nonce",
                authorization._nonce,
            )
            object.__setattr__(
                forged,
                "_thread_id",
                authorization._thread_id,
            )

            with pytest.raises(
                ValueError,
                match=(
                    "legacy_runtime_root_bootstrap_authorization_"
                    "inactive_or_forged"
                ),
            ):
                runtime_apply._bootstrap_legacy_runtime_root_from_context(
                    authorization=forged,
                )

            assert not runtime.exists()
            evidence = runtime_apply._bootstrap_legacy_runtime_root_from_context(
                authorization=authorization,
            )
            assert evidence.runtime_root == runtime
            assert len(evidence.created_directory_identities) == 1
            assert runtime.is_dir()
        elif invalid_authorization == "stale":
            runtime_apply._consume_legacy_runtime_root_bootstrap_authorization(
                authorization
            )

            assert_authorization_consumed(authorization)
            assert not runtime.exists()
        elif invalid_authorization == "reused":
            evidence = runtime_apply._bootstrap_legacy_runtime_root_from_context(
                authorization=authorization,
            )
            successor_identity = path_identity(runtime)

            assert evidence.successor_identity == successor_identity
            assert len(evidence.created_directory_identities) == 1
            assert_authorization_consumed(authorization)
            assert path_identity(runtime) == successor_identity
            assert list(runtime.iterdir()) == []
        elif invalid_authorization == "cross_thread":
            thread_errors: list[BaseException] = []

            def bootstrap_on_other_thread() -> None:
                try:
                    runtime_apply._bootstrap_legacy_runtime_root_from_context(
                        authorization=authorization,
                    )
                except BaseException as error:
                    thread_errors.append(error)

            thread = Thread(target=bootstrap_on_other_thread)
            thread.start()
            thread.join(timeout=10)

            assert not thread.is_alive()
            assert len(thread_errors) == 1
            assert isinstance(thread_errors[0], ValueError)
            assert str(thread_errors[0]) == (
                "legacy_runtime_root_bootstrap_authorization_"
                "inactive_or_forged"
            )
            assert not runtime.exists()
            evidence = runtime_apply._bootstrap_legacy_runtime_root_from_context(
                authorization=authorization,
            )
            assert evidence.runtime_root == runtime
            assert len(evidence.created_directory_identities) == 1
            assert runtime.is_dir()
        elif invalid_authorization == "wrong_root":
            runtime.mkdir()

            with pytest.raises(
                ValueError,
                match="legacy_runtime_root_predecessor_changed",
            ):
                runtime_apply._bootstrap_legacy_runtime_root_from_context(
                    authorization=authorization,
                )

            assert runtime.is_dir()
            assert list(runtime.iterdir()) == []
            assert_authorization_consumed(authorization)
        elif invalid_authorization == "wrong_gate":
            apply_gate["policy"] = "BLOCKED"

            with pytest.raises(
                ValueError,
                match="legacy_runtime_root_bootstrap_authority_changed",
            ):
                runtime_apply._bootstrap_legacy_runtime_root_from_context(
                    authorization=authorization,
                )

            assert not runtime.exists()
            assert_authorization_consumed(authorization)
        else:
            raise AssertionError(invalid_authorization)
    finally:
        with runtime_apply._active_legacy_root_bootstraps_lock:
            for authorization in issued_authorizations:
                runtime_apply._active_legacy_root_bootstraps.pop(
                    id(authorization),
                    None,
                )


def test_runtime_apply_creates_no_runtime_surface_before_output_operation_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig import runtime_apply

    package = _allowed_package(tmp_path)
    runtime = tmp_path / "fresh-runtime"

    @contextmanager
    def blocked_operation_lease() -> Iterator[object]:
        yield object()

    def reject_runtime_mutation(*, lease: object) -> None:
        del lease
        raise ValueError("output_operation_admission_blocks_runtime_mutation")

    monkeypatch.setattr(runtime_apply, "_bootstrap_neutral_output_locks", lambda: None)
    monkeypatch.setattr(
        runtime_apply,
        "lease_output_operation_admission",
        blocked_operation_lease,
    )
    monkeypatch.setattr(
        runtime_apply,
        "require_output_operation_allows_runtime_mutation",
        reject_runtime_mutation,
    )

    with pytest.raises(
        ValueError,
        match="output_operation_admission_blocks_runtime_mutation",
    ):
        apply_package(package_root=package, runtime_root=runtime)

    assert not runtime.exists()
    assert not (runtime / ".hsconfig").exists()
    assert not (runtime / "apply.lock").exists()
