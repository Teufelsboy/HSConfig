"""Bounded, offline verification of frozen audited deck builds."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from tempfile import gettempdir

from hsconfig.audited_build_request import _render_selected_run
from hsconfig.build_input_catalog import (
    AuditedBuildInputSet,
    FrozenBuildResourceStore,
)
from hsconfig.build_inputs import CanonicalBuildInputs
from hsconfig.configure_run_model import (
    RenderedConfigureRun,
    render_configure_run_model,
    write_rendered_configure_run,
)
from hsconfig.deck_config_ini import read_deck_config
from hsconfig.output_publisher import PublishedOutput, publish_configure_run
from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.package_io import path_identity
from hsconfig.package_model import DirectoryPackageView
from hsconfig.package_request import PackageResolutionSnapshot
from hsconfig.runtime_installer import (
    _receipt_bytes,
    _receipt_path,
    _receipt_payload_for_plan,
    _state_key,
    RuntimeInstallPlan,
    install_runtime_package,
    plan_runtime_install,
    recover_runtime_state,
)
from hsconfig.runtime_state import RuntimeState
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
)
from hsconfig.strict_package_validation import (
    strict_validation_passed,
    validate_complete_configure_run_from_view,
)


_AUDITED_DECK_ORDER = (
    "ShadowPriest",
    "CtAPaladin",
    "PirateRogue",
    "BigShaman",
    "Discolock",
    "TreantDruid",
    "ImbueMage",
    "MechPala",
    "Kingslayer",
    "Boarlock",
    "PirateDH",
    "CuteWarrior",
)


@dataclass(frozen=True, slots=True)
class DeckVerification:
    deck_name: str
    first_content_root_sha256: str
    second_content_root_sha256: str
    configure_run_bytes_equal: bool
    runtime_old_or_new_safe: bool


@dataclass(frozen=True, slots=True)
class _PriorRuntimeState:
    config_dir: str
    target_tree: dict[str, bytes]
    ini_bytes: bytes
    state: RuntimeState
    receipt_path: Path
    receipt_bytes: bytes
    journal_path: Path
    journal_bytes: bytes


def verify_audited_decks(
    *,
    build_inputs: AuditedBuildInputSet,
    resource_store: FrozenBuildResourceStore,
    deck_codes: Mapping[str, str],
    work_root_a: Path,
    work_root_b: Path,
) -> tuple[DeckVerification, ...]:
    """Verify the exact explicit audited set below caller-owned temp roots."""
    if not isinstance(build_inputs, AuditedBuildInputSet):
        raise TypeError("audited_build_inputs_required")
    if not isinstance(resource_store, FrozenBuildResourceStore):
        raise TypeError("frozen_build_resource_store_required")
    _validate_exact_audited_inputs(build_inputs)
    codes = _validate_deck_codes(build_inputs, deck_codes)
    root_a = _prepare_fresh_temporary_root(work_root_a)
    root_b = _prepare_fresh_temporary_root(work_root_b)
    if root_a == root_b:
        raise ValueError("verification_roots_must_differ")
    rows: list[DeckVerification] = []
    for inputs in build_inputs.builds:
        first_root = root_a / inputs.deck_name
        second_root = root_b / inputs.deck_name
        first_root.mkdir()
        second_root.mkdir()
        rows.append(
            _verify_one_audited_deck(
                inputs=inputs,
                resource_store=resource_store,
                deck_code=codes[inputs.deck_name],
                work_root_a=first_root,
                work_root_b=second_root,
            )
        )
    return tuple(rows)


def _verify_one_audited_deck(
    *,
    inputs: CanonicalBuildInputs,
    resource_store: FrozenBuildResourceStore,
    deck_code: str,
    work_root_a: Path,
    work_root_b: Path,
) -> DeckVerification:
    """Private one-deck primitive for narrow cold-build coverage."""
    if not isinstance(inputs, CanonicalBuildInputs):
        raise TypeError("audited_build_input_required")
    _validate_private_work_roots(work_root_a, work_root_b)
    if sha256(deck_code.encode("utf-8")).hexdigest() != inputs.deck_code_sha256:
        raise ValueError("audited_build_deck_code_mismatch")
    first = _render_selected_run(
        inputs=inputs,
        resources=resource_store,
        deck_code=deck_code,
    )
    second = _render_selected_run(
        inputs=inputs,
        resources=resource_store,
        deck_code=deck_code,
    )
    first_root = Path(work_root_a) / inputs.deck_name
    second_root = Path(work_root_b) / inputs.deck_name
    first_run_root = first_root / "configure-run"
    second_run_root = second_root / "configure-run"
    write_rendered_configure_run(first, first_run_root)
    write_rendered_configure_run(second, second_run_root)

    first_tree = _tree_bytes(first_run_root)
    second_tree = _tree_bytes(second_run_root)
    configure_run_bytes_equal = first_tree == second_tree
    if not configure_run_bytes_equal:
        raise ValueError("audited_build_tree_bytes_mismatch")
    _assert_no_serialized_root(first_tree, Path(work_root_a), Path(work_root_b))
    _assert_semantic_closure(first_run_root)
    _assert_semantic_closure(second_run_root)

    runtime_safe = _verify_exception_recovery(
        rendered=first,
        inputs=inputs,
        resource_store=resource_store,
        deck_code=deck_code,
        publication_root=first_root / "publication",
        runtime_root=first_root / "runtime-pre-commit",
        checkpoint="before_ini_compare_and_swap",
        expect_new=False,
    ) and _verify_exception_recovery(
        rendered=second,
        inputs=inputs,
        resource_store=resource_store,
        deck_code=deck_code,
        publication_root=second_root / "publication",
        runtime_root=second_root / "runtime-post-commit",
        checkpoint="after_state_write",
        expect_new=True,
    )
    if not runtime_safe:
        raise ValueError("runtime_exception_recovery_unsafe")
    return DeckVerification(
        deck_name=inputs.deck_name,
        first_content_root_sha256=first.content_root_sha256,
        second_content_root_sha256=second.content_root_sha256,
        configure_run_bytes_equal=configure_run_bytes_equal,
        runtime_old_or_new_safe=runtime_safe,
    )


def _validate_private_work_roots(left: Path, right: Path) -> None:
    roots = (Path(left), Path(right))
    temp_root = Path(gettempdir()).resolve()
    resolved = tuple(root.resolve() for root in roots)
    same_root = resolved[0] == resolved[1]
    if all(root.exists() for root in roots):
        same_root = same_root or roots[0].samefile(roots[1])
    if (
        same_root
        or any(
            not root.is_absolute()
            or not root.is_dir()
            or any(root.iterdir())
            for root in roots
        )
        or any(not _is_within(root, temp_root) for root in resolved)
    ):
        raise ValueError("verification_private_roots_invalid")


def _validate_exact_audited_inputs(build_inputs: AuditedBuildInputSet) -> None:
    if tuple(build.deck_name for build in build_inputs.builds) != _AUDITED_DECK_ORDER:
        raise ValueError("audited_build_input_set_invalid")


def _validate_deck_codes(
    build_inputs: AuditedBuildInputSet,
    deck_codes: Mapping[str, str],
) -> dict[str, str]:
    if not isinstance(deck_codes, Mapping) or set(deck_codes) != set(_AUDITED_DECK_ORDER):
        raise ValueError("audited_build_deck_codes_invalid")
    codes = {str(name): value for name, value in deck_codes.items()}
    if any(not isinstance(code, str) or not code for code in codes.values()):
        raise ValueError("audited_build_deck_codes_invalid")
    if any(
        sha256(codes[inputs.deck_name].encode("utf-8")).hexdigest()
        != inputs.deck_code_sha256
        for inputs in build_inputs.builds
    ):
        raise ValueError("audited_build_deck_code_mismatch")
    return codes


def _prepare_fresh_temporary_root(path: Path) -> Path:
    root = Path(path)
    resolved = root.resolve()
    temp_root = Path(gettempdir()).resolve()
    if not root.is_absolute():
        raise ValueError("verification_root_must_be_absolute")
    if not _is_within(resolved, temp_root):
        raise ValueError("verification_root_not_temporary")
    if root.exists():
        raise ValueError("verification_root_must_be_fresh")
    root.mkdir(parents=True)
    return root.resolve()


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return str(candidate).casefold().startswith(
            str(parent).casefold().rstrip("\\/") + "\\"
        ) or str(candidate).casefold().startswith(
            str(parent).casefold().rstrip("\\/") + "/"
        )
    return True


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _assert_no_serialized_root(
    tree: dict[str, bytes],
    root_a: Path,
    root_b: Path,
) -> None:
    markers = {
        variant.casefold()
        for root in (root_a, root_b)
        for variant in _root_spellings(root)
    }
    if any(
        marker.encode("utf-8") in content.decode("utf-8", "ignore").casefold().encode("utf-8")
        for content in tree.values()
        for marker in markers
    ):
        raise ValueError("audited_build_absolute_root_serialized")


def _root_spellings(root: Path) -> tuple[str, ...]:
    resolved = Path(root).resolve()
    values = (str(root), str(resolved), root.as_posix(), resolved.as_posix())
    return tuple(
        sorted(
            {
                value
                for item in values
                for value in (
                    item,
                    item.replace("/", "\\"),
                    item.replace("\\", "/"),
                )
            }
        )
    )


def _assert_semantic_closure(run_root: Path) -> None:
    report = validate_complete_configure_run_from_view(
        DirectoryPackageView(run_root)
    )
    if not strict_validation_passed(report):
        raise ValueError("audited_build_semantic_closure_invalid")


def _verify_exception_recovery(
    *,
    rendered: RenderedConfigureRun,
    inputs: CanonicalBuildInputs,
    resource_store: FrozenBuildResourceStore,
    deck_code: str,
    publication_root: Path,
    runtime_root: Path,
    checkpoint: str,
    expect_new: bool,
) -> bool:
    prior_rendered = _render_canonical_prior(
        rendered=rendered,
        inputs=inputs,
        resource_store=resource_store,
        deck_code=deck_code,
    )
    prior_published = publish_configure_run(prior_rendered, publication_root)
    runtime_root.mkdir()
    prior_plan = plan_runtime_install(
        published_output=prior_published,
        runtime_root=runtime_root,
    )
    install_runtime_package(prior_plan)
    prior = _capture_prior_runtime(prior_plan)
    published = publish_configure_run(rendered, publication_root)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )

    def inject(stage: str) -> None:
        if stage == checkpoint:
            raise RuntimeError(f"release-verification:{checkpoint}")

    try:
        install_runtime_package(plan, fault_hook=inject)
    except RuntimeError as error:
        if str(error) != f"release-verification:{checkpoint}":
            raise
    else:
        return False

    state = recover_runtime_state(runtime_root)
    ini = read_deck_config(
        runtime_root / "CustomConfig" / "deck_config.ini",
        deck_name=plan.deck_name,
    )
    if expect_new:
        return _new_runtime_state_is_exact(
            plan=plan,
            published=published,
            prior=prior,
            state=state,
            ini_sha256=ini.sha256,
            selected_config_dir=ini.selected_config_dir,
        )
    return _prior_runtime_state_is_exact(
        runtime_root=runtime_root,
        plan=plan,
        prior=prior,
        state=state,
    )


def _render_canonical_prior(
    *, rendered: RenderedConfigureRun, inputs: CanonicalBuildInputs,
    resource_store: FrozenBuildResourceStore, deck_code: str,
) -> RenderedConfigureRun:
    from hsconfig.audited_build_request import resolve_frozen_audited_package_request

    request = resolve_frozen_audited_package_request(
        inputs=inputs, resources=resource_store, deck_code=deck_code
    )
    prior_preconfig = deepcopy(request.snapshot.general_preconfig.to_value())
    prior_preconfig["globalvalues_baseline"]["ConfigComment"] = "task-4-prior"
    prior_preconfig["globalvalues_baseline_receipt"]["baseline"]["ConfigComment"] = "task-4-prior"
    snapshot = PackageResolutionSnapshot.from_strict(
        request.snapshot.strict_build_context, prior_preconfig
    )
    prior_package = assemble_package(compile_package(replace(request, snapshot=snapshot)))
    return render_configure_run_model(replace(rendered.model, package=prior_package))


def _capture_prior_runtime(plan: RuntimeInstallPlan) -> _PriorRuntimeState:
    state = recover_runtime_state(plan.runtime_root)
    if state is None:
        raise RuntimeError("prior_runtime_state_missing")
    ini_path = plan.runtime_root / "CustomConfig" / "deck_config.ini"
    receipt_path = _receipt_path(plan.runtime_root, _state_key(plan.deck_name))
    journals = load_runtime_transaction_journals(plan.runtime_root)
    if len(journals) != 1 or journals[0].phase != RuntimeTransactionPhase.FINALIZED or not journals[0].owns_target:
        raise RuntimeError("prior_runtime_journal_invalid")
    journal_path = plan.runtime_root / ".hsconfig" / "transactions" / f"{journals[0].transaction_id}.json"
    return _PriorRuntimeState(
        config_dir=plan.versioned_config_dir,
        target_tree=_tree_bytes(plan.runtime_root / "CustomConfig" / plan.versioned_config_dir),
        ini_bytes=ini_path.read_bytes(),
        state=state,
        receipt_path=receipt_path,
        receipt_bytes=receipt_path.read_bytes(),
        journal_path=journal_path,
        journal_bytes=journal_path.read_bytes(),
    )


def _prior_runtime_state_is_exact(
    *,
    runtime_root: Path,
    plan: RuntimeInstallPlan,
    prior: _PriorRuntimeState,
    state: RuntimeState | None,
) -> bool:
    return (
        (runtime_root / "CustomConfig" / "deck_config.ini").read_bytes()
        == prior.ini_bytes
        and _tree_bytes(runtime_root / "CustomConfig" / prior.config_dir)
        == prior.target_tree
        and state == prior.state
        and prior.receipt_path.read_bytes() == prior.receipt_bytes
        and prior.journal_path.read_bytes() == prior.journal_bytes
        and not (runtime_root / "CustomConfig" / plan.versioned_config_dir).exists()
        and list((runtime_root / ".hsconfig" / "receipts").rglob("*.json"))
        == [prior.receipt_path]
    )


def _new_runtime_state_is_exact(
    *,
    plan: RuntimeInstallPlan,
    published: PublishedOutput,
    prior: _PriorRuntimeState,
    state: RuntimeState | None,
    ini_sha256: str | None,
    selected_config_dir: str | None,
) -> bool:
    if ini_sha256 is None or state is None:
        return False
    matching = [
        deck
        for deck in state.decks
        if deck.deck_name.casefold() == plan.deck_name.casefold()
    ]
    receipt = _receipt_path(plan.runtime_root, _state_key(plan.deck_name))
    expected_receipt = _receipt_bytes(
        _receipt_payload_for_plan(plan, ini_sha256, _state_key(plan.deck_name))
    )
    expected_tree = _tree_bytes(
        published.package_root / "CustomConfig" / plan.logical_config_dir
    )
    target = plan.runtime_root / "CustomConfig" / plan.versioned_config_dir
    journals = load_runtime_transaction_journals(plan.runtime_root)
    return (
        prior.config_dir != plan.versioned_config_dir
        and not (plan.runtime_root / "CustomConfig" / prior.config_dir).exists()
        and not prior.journal_path.exists()
        and len(journals) == 1
        and journals[0].phase == RuntimeTransactionPhase.FINALIZED
        and journals[0].owns_target
        and journals[0].deck_name == plan.deck_name
        and journals[0].state_key == _state_key(plan.deck_name)
        and journals[0].logical_config_dir == plan.logical_config_dir
        and journals[0].package_root_sha256 == plan.package_root_sha256
        and journals[0].source_manifest_sha256
        == plan.source_revision_root.name.removeprefix("sha256-")
        and journals[0].target_path
        == f"CustomConfig/{plan.versioned_config_dir}"
        and journals[0].target_identity == path_identity(target)
        and selected_config_dir == plan.versioned_config_dir
        and len(state.decks) == 1
        and len(matching) == 1
        and matching[0].config_dir == plan.versioned_config_dir
        and matching[0].package_root_sha256 == plan.package_root_sha256
        and matching[0].ini_sha256 == ini_sha256
        and _tree_bytes(
            target
        )
        == expected_tree
        and receipt.read_bytes() == expected_receipt
        and list((plan.runtime_root / ".hsconfig" / "receipts").rglob("*.json"))
        == [receipt]
    )


__all__ = ("DeckVerification", "verify_audited_decks")
