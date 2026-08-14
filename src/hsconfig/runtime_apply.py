from __future__ import annotations

import re
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.current_output import PackageInputLease, lease_package_input
from hsconfig.output_publisher import PublishedOutput
from hsconfig.runtime_apply_receipts import (
    build_fake_apply_receipt,
    verify_fake_apply_receipt,
)
from hsconfig.runtime_installer import (
    RuntimeInstallPlan,
    RuntimeInstallResult,
    install_runtime_package,
    plan_runtime_install,
)
from hsconfig.strict_package_validation import (
    LINKED_RUNTIME_OWNER_EVIDENCE_INVALID,
    LINKED_RUNTIME_OWNER_EVIDENCE_MISSING,
    strict_validation_passed,
    validate_complete_package,
)


_REVISION_NAME = re.compile(r"sha256-[0-9a-f]{64}")

# Read-only authority-boundary tests still monkeypatch this removed private
# boundary to prove validation fails before any legacy destination work.  The
# sentinel is intentionally non-callable; no backup implementation remains.
_snapshot_existing_runtime_target: None = None


def plan_apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    apply_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with lease_package_input(Path(package_root)) as lease:
        package = lease.package_root
        _validate_runtime_apply_package(package)
        resolved_gate = _resolve_allowed_apply_gate(
            package=package,
            apply_gate=apply_gate,
            allow_source_informed=False,
        )
        logical_config_dir = _logical_config_dir(package, config_dir)
        return build_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime_root,
            config_dir=logical_config_dir,
            apply_gate=resolved_gate,
        )


def apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    replace: bool = True,
    fake_receipt: dict[str, Any] | None = None,
    apply_gate: dict[str, Any] | None = None,
    allow_source_informed: bool = False,
    write_history: bool = True,
) -> dict[str, Any]:
    del replace, write_history
    runtime = Path(runtime_root)
    with _lease_real_apply_input(Path(package_root)) as lease:
        package = lease.package_root
        _validate_runtime_apply_package(package)
        resolved_gate = _resolve_allowed_apply_gate(
            package=package,
            apply_gate=apply_gate,
            allow_source_informed=allow_source_informed,
        )
        logical_config_dir = _logical_config_dir(package, config_dir)
        receipt = fake_receipt
        if receipt is None:
            receipt = build_fake_apply_receipt(
                package_root=package,
                runtime_root=runtime,
                config_dir=logical_config_dir,
                apply_gate=resolved_gate,
            )
        verify_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime,
            config_dir=logical_config_dir,
            receipt=receipt,
        )
        if lease.publication is None:
            raise TypeError("published_output_required")
        published = _published_output(lease)
        runtime.mkdir(parents=True, exist_ok=True)
        plan = plan_runtime_install(
            published_output=published,
            runtime_root=runtime,
        )
        if plan.logical_config_dir != logical_config_dir:
            raise ValueError("config_dir_mismatch")

    result = install_runtime_package(plan)
    return _apply_result(plan, result, resolved_gate)


@contextmanager
def _lease_real_apply_input(
    package_input: Path,
) -> Iterator[PackageInputLease]:
    output_root = _direct_published_output_root(package_input)
    lease_target = output_root if output_root is not None else package_input
    with ExitStack() as stack:
        try:
            lease = stack.enter_context(lease_package_input(lease_target))
        except ValueError as error:
            if output_root is not None:
                raise TypeError("published_output_required") from error
            raise
        if output_root is not None:
            if (
                lease.publication is None
                or _resolved(lease.package_root) != _resolved(package_input)
                or package_input.parent.name
                != f"sha256-{lease.content_root_sha256}"
            ):
                raise TypeError("published_output_required")
        yield lease


def _direct_published_output_root(package_input: Path) -> Path | None:
    if (
        package_input.name != "04_package"
        or not _REVISION_NAME.fullmatch(package_input.parent.name)
        or package_input.parent.parent.name != "revisions"
    ):
        return None
    return package_input.parent.parent.parent


def _published_output(lease: PackageInputLease) -> PublishedOutput:
    if (
        lease.publication is None
        or lease.output_root is None
        or lease.content_root_sha256 is None
    ):
        raise TypeError("published_output_required")
    return PublishedOutput(
        output_root=lease.output_root,
        revision_root=lease.package_root.parent,
        package_root=lease.package_root,
        content_root_sha256=lease.content_root_sha256,
        reused_existing_revision=True,
    )


def _apply_result(
    plan: RuntimeInstallPlan,
    result: RuntimeInstallResult,
    apply_gate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": result.status,
        "runtime_write_performed": result.status
        in {"applied", "committed_receipt_pending"},
        "mapped_deck_name": plan.deck_name,
        "logical_config_dir": plan.logical_config_dir,
        "versioned_config_dir": result.config_dir,
        "package_root_sha256": result.package_root_sha256,
        "previous_config_dir": result.previous_config_dir,
        "receipt_path": (
            str(result.receipt_path)
            if result.receipt_path is not None
            else None
        ),
        "apply_gate": apply_gate,
    }


def _validate_runtime_apply_package(package: Path) -> None:
    try:
        report = validate_complete_package(package)
    except ValueError as exc:
        raise ValueError(
            "Runtime apply requires a valid complete package before fake/apply "
            f"receipt or runtime writes: {exc}"
        ) from exc

    if strict_validation_passed(report):
        return
    errors = report.get("errors") or ["unknown package validation failure"]
    first_error = next(
        (
            code
            for code in (
                LINKED_RUNTIME_OWNER_EVIDENCE_MISSING,
                LINKED_RUNTIME_OWNER_EVIDENCE_INVALID,
            )
            if code in errors
        ),
        str(errors[0]),
    )
    extra_count = max(len(errors) - 1, 0)
    suffix = f" (and {extra_count} more)" if extra_count else ""
    raise ValueError(
        "Runtime apply requires a valid complete package before fake/apply "
        f"receipt or runtime writes: {first_error}{suffix}"
    )


def _resolve_allowed_apply_gate(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
    allow_source_informed: bool,
) -> dict[str, Any]:
    del allow_source_informed
    evaluated = evaluate_apply_gate(package)
    if apply_gate is not None and apply_gate != evaluated:
        reason = _first_gate_reason(evaluated)
        raise ValueError(
            "Runtime apply requires an allowed apply gate from "
            f"reports/operator_summary.json; got apply_gate_mismatch:{reason}"
        )
    if not _is_allowed_gate_for_package(
        package=package,
        apply_gate=evaluated,
    ):
        reason = _first_gate_reason(evaluated)
        raise ValueError(
            "Runtime apply requires an allowed apply gate from "
            f"reports/operator_summary.json; got {reason}"
        )
    return evaluated


def _is_allowed_gate_for_package(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
) -> bool:
    if not isinstance(apply_gate, dict):
        return False
    if apply_gate.get("allowed") is not True:
        return False
    if apply_gate.get("mode") != "load_safe_apply":
        return False
    if apply_gate.get("policy") not in {"ALLOWED", "ALLOWED_WITH_WARNINGS"}:
        return False
    operator_summary_path = apply_gate.get("operator_summary_path")
    if not operator_summary_path:
        return False
    expected = package / "reports" / "operator_summary.json"
    try:
        return Path(str(operator_summary_path)).resolve() == expected.resolve()
    except OSError:
        return False


def _first_gate_reason(apply_gate: dict[str, Any] | None) -> str:
    if not isinstance(apply_gate, dict):
        return "missing_apply_gate"
    reasons = apply_gate.get("reasons")
    if isinstance(reasons, list) and reasons:
        first = reasons[0]
        if isinstance(first, dict):
            return str(first.get("reason", "blocked"))
        return str(first)
    status = apply_gate.get("status", "missing_apply_gate")
    mode = apply_gate.get("mode", "")
    return f"{status}:{mode}" if mode else str(status)


def _logical_config_dir(package: Path, requested: str | None) -> str:
    logical = _single_config_dir(package)
    if requested is not None:
        _validate_config_dir(requested)
        if requested != logical:
            raise ValueError("config_dir_mismatch")
    source = package / "CustomConfig" / logical
    _validate_complete_source_dir(source)
    return logical


def _single_config_dir(package_root: Path) -> str:
    custom_config = package_root / "CustomConfig"
    if not custom_config.is_dir():
        raise FileNotFoundError(
            f"Package CustomConfig directory not found: {custom_config}"
        )
    deck_dirs = sorted(
        path.name for path in custom_config.iterdir() if path.is_dir()
    )
    if len(deck_dirs) != 1:
        raise ValueError("Expected exactly one CustomConfig deck directory.")
    return deck_dirs[0]


def _validate_config_dir(config_dir: str) -> None:
    path = Path(config_dir)
    if (
        not config_dir
        or path.name != config_dir
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"Invalid config directory name: {config_dir!r}")


def _validate_complete_source_dir(source_dir: Path) -> None:
    missing = [
        filename
        for filename in ("GlobalValues.json", "Mulligan.json")
        if not (source_dir / filename).is_file()
    ]
    if missing:
        raise ValueError(
            f"Incomplete package deck config {source_dir}: "
            f"missing {', '.join(missing)}"
        )


def _resolved(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError:
        return path.resolve()
