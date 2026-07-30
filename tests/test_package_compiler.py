from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path
import importlib
import subprocess
import sys
from typing import Any

import pytest

from hsconfig.package_compiler import (
    CompiledPackage,
    CompiledRuntimeSurface,
    NamedJsonProjection,
    PRE_AUTHORITY_OWNER_BY_PATH,
    PackageDecisionSnapshot,
    ProjectionOwner,
    compile_package,
    compile_package_decisions,
)
from hsconfig.package_domain import (
    FrozenDefinitionList,
    FrozenDefinitionMapping,
)
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.package_request import (
    PackageResolutionSnapshot,
    ResolvedPackageRequest,
)
from tests.helpers.audited_package_request import audited_request


def test_shared_audited_request_runs_without_importing_test_modules() -> None:
    script = "\n".join(
        (
            "import sys",
            "import tempfile",
            "from pathlib import Path",
            (
                "from tests.helpers.audited_package_request "
                "import audited_request"
            ),
            "with tempfile.TemporaryDirectory() as root:",
            (
                "    request = audited_request("
                "Path(root), 'ShadowPriest')"
            ),
            "    assert request.invocation.deck_code",
            (
                "loaded = sorted(name for name in sys.modules "
                "if name.startswith('tests.test_'))"
            ),
            "assert loaded == [], loaded",
        )
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, (
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def test_c3_compiles_real_audited_decisions_without_post_request_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = audited_request(tmp_path, "ShadowPriest")

    def forbidden(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("post_request_io_forbidden")

    monkeypatch.setattr(
        "hsconfig.mulligan_plan.load_policy_profile",
        forbidden,
    )
    monkeypatch.setattr(
        "hsconfig.evidence_contract.load_policy_profile",
        forbidden,
    )
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "is_file", forbidden)
    monkeypatch.setattr(Path, "is_dir", forbidden)

    compiled = compile_package_decisions(request)

    assert isinstance(compiled, PackageDecisionSnapshot)
    assert compiled.deck_name == "ShadowPriest"
    assert compiled.deck_fingerprint == (
        "831b989cf8d076bff87848b4d0d6f382c9d306fddea7619017f0c361bfc92327"
    )
    assert compiled.combo_plan.decisions == ()
    assert compiled.mulligan_plan.deck_name == "ShadowPriest"
    assert {
        projection.relative_path
        for projection in compiled.decision_projections
    }.issuperset(
        {
            "reports/gameplan_contract.json",
            "reports/mulligan_plan_report.json",
            "reports/card_behavior_plan_report.json",
            "reports/combo_plan_report.json",
            "reports/global_values_authority_matrix.json",
        }
    )


def test_c3_identical_request_is_equal_and_caller_mutation_cannot_change_it(
    tmp_path: Path,
) -> None:
    request = audited_request(tmp_path, "Boarlock")

    first = compile_package_decisions(request)
    second = compile_package_decisions(request)
    mutable = first.compiler_state.to_value()
    mutable["deck_identity"]["deck_name"] = "changed"

    assert first == second
    assert first.compiler_state.to_value()["deck_identity"]["deck_name"] == (
        "Boarlock"
    )
    assert first.combo_plan.decisions == ()
    assert first.combo_plan.suppressions == ()


def test_c4_compiles_complete_immutable_runtime_and_report_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = audited_request(tmp_path, "ShadowPriest")

    def forbidden(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("c6_or_io_call_forbidden")

    for target in (
        "hsconfig.package_renderer.render_package_model",
        "hsconfig.strict_package_validation.validate_complete_package",
        "hsconfig.output_ownership_manifest.build_output_ownership_manifest",
        "hsconfig.package_derivation_receipt.refresh_package_derivation_authority",
        "hsconfig.operator_summary.build_operator_summary",
    ):
        monkeypatch.setattr(target, forbidden)
    monkeypatch.setattr(
        "hsconfig.source_contract_audit._packaged_policy_mapping",
        forbidden,
    )
    monkeypatch.setattr(
        "hsconfig.pre_run_metrics.load_policy_profile",
        forbidden,
    )

    compiled = compile_package(request)

    assert isinstance(compiled, CompiledPackage)
    assert compiled == compile_package(request)
    assert compiled.combo_plan.decisions == ()
    assert all(
        surface.family != "Combo"
        for surface in compiled.runtime_surfaces
    )
    assert {
        surface.file_name for surface in compiled.runtime_surfaces
    }.issuperset({"GlobalValues.json", "Mulligan.json"})
    assert {
        projection.relative_path
        for projection in compiled.json_projections
    }.issuperset(
        {
            "reports/input_manifest.json",
            "reports/source_contract_audit.json",
            "reports/disposition_ledger.json",
            "reports/pre_run_closure.json",
        }
    )
    ledger_bytes = compiled.semantic_runtime_ledger.canonical_json
    mutable = compiled.semantic_runtime_ledger.to_value()
    mutable.clear()
    assert compiled.semantic_runtime_ledger.canonical_json == ledger_bytes


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    (
        ("runtime_surfaces", ()),
        ("json_projections", ()),
        ("text_projections", ()),
    ),
)
def test_compiled_package_rejects_incomplete_projection_collections(
    tmp_path: Path,
    field_name: str,
    replacement: tuple[object, ...],
) -> None:
    compiled = compile_package(audited_request(tmp_path, "ShadowPriest"))

    with pytest.raises(ValueError, match="compiled_package_.*incomplete"):
        _recreate_compiled(compiled, **{field_name: replacement})


def test_compiled_package_rejects_duplicate_runtime_and_projection_paths(
    tmp_path: Path,
) -> None:
    compiled = compile_package(audited_request(tmp_path, "ShadowPriest"))

    with pytest.raises(ValueError, match="compiled_package_runtime_duplicate"):
        _recreate_compiled(
            compiled,
            runtime_surfaces=(
                compiled.runtime_surfaces[0],
                *compiled.runtime_surfaces,
            ),
        )
    with pytest.raises(ValueError, match="compiled_package_projection_duplicate"):
        _recreate_compiled(
            compiled,
            json_projections=(
                compiled.json_projections[0],
                *compiled.json_projections,
            ),
        )


def test_compiled_package_rejects_missing_optional_compiler_projection(
    tmp_path: Path,
) -> None:
    compiled = compile_package(audited_request(tmp_path, "ShadowPriest"))
    optional_paths = {
        "reports/card_id_map.json",
        "reports/deckstring_decode_receipt.json",
        "reports/guide_sources.json",
        "reports/plan_input_diagnostics.json",
    }
    optional = next(
        row
        for row in compiled.json_projections
        if row.relative_path in optional_paths
    )

    with pytest.raises(ValueError, match="compiled_package_projection_incomplete"):
        _recreate_compiled(
            compiled,
            json_projections=tuple(
                row
                for row in compiled.json_projections
                if row is not optional
            ),
        )


def test_compiled_package_rejects_coordinated_projection_contract_forgery(
    tmp_path: Path,
) -> None:
    compiled = compile_package(audited_request(tmp_path, "ShadowPriest"))
    optional = next(
        row
        for row in compiled.json_projections
        if row.relative_path == "reports/card_id_map.json"
    )
    json_projections = tuple(
        row
        for row in compiled.json_projections
        if row is not optional
    )
    reduced_contract = tuple(
        sorted(
            (
                *(row.relative_path for row in json_projections),
                *(
                    row.relative_path
                    for row in compiled.text_projections
                ),
            )
        )
    )

    with pytest.raises(
        TypeError,
        match="compiled_package_internal_construction_only",
    ):
        replace(
            compiled,
            json_projections=json_projections,
            _projection_path_contract=reduced_contract,
        )


def test_compiled_package_rejects_nested_snapshot_projection_forgery(
    tmp_path: Path,
) -> None:
    compiled = compile_package(audited_request(tmp_path, "ShadowPriest"))
    card_map = next(
        row
        for row in compiled.json_projections
        if row.relative_path == "reports/card_id_map.json"
    )
    reduced_json = tuple(
        row for row in compiled.json_projections if row is not card_map
    )
    state = compiled.decision_snapshot.compiler_state.to_value()
    state["cards_payload"]["card_id_map"] = None
    forged_snapshot = replace(
        compiled.decision_snapshot,
        compiler_state=FrozenJsonDocument.from_value(state),
    )

    with pytest.raises(
        TypeError,
        match="compiled_package_internal_construction_only",
    ):
        replace(
            compiled,
            decision_snapshot=forged_snapshot,
            json_projections=reduced_json,
        )


def _recreate_compiled(
    compiled: CompiledPackage,
    **changes: object,
) -> CompiledPackage:
    values = {
        field.name: getattr(compiled, field.name)
        for field in fields(compiled)
    }
    values.update(changes)
    return CompiledPackage._create(**values)  # type: ignore[arg-type]


_C3_C4_DEFINITION_CLOSURE_MODULES = (
    "pre_run_metrics",
    "compile_globalvalues",
    "globalvalues_authority",
    "globalvalues_key_authority",
    "card_behavior_surface_router",
    "semantic_runtime_gate",
    "condition_format",
    "mechanic_support",
    "compile_cardid",
    "runtime_surface_ledger",
    "visionai_registry",
    "disposition_ledger",
    "mechanic_drift",
    "config_readiness",
    "guide_source_depth",
    "source_claim_gap_report",
    "source_to_runtime_explainability",
    "configure_stages",
    "source_acquisition_provenance",
    "source_document_model",
    "source_contract_matrix",
    "source_semantic_qualifiers",
    "linked_entity_supplement",
)


def test_c3_c4_reachable_static_authority_definitions_are_frozen() -> None:
    violations: list[str] = []
    for module_name in _C3_C4_DEFINITION_CLOSURE_MODULES:
        module = importlib.import_module(f"hsconfig.{module_name}")
        for name, value in vars(module).items():
            if name.isupper() and type(value) in {dict, list, set}:
                violations.append(f"{module_name}.{name}")

    assert violations == []


def test_dynamic_registry_and_disposition_authorities_reject_mutation() -> None:
    from hsconfig import (
        disposition_ledger,
        mechanic_support,
        visionai_registry,
    )

    with pytest.raises(TypeError, match="frozen_definition"):
        visionai_registry.CARD_BEHAVIOR_BLOCK_REGISTRY[
            "BeforePlayCardBonus"
        ]["support"] = "mutated"
    with pytest.raises(TypeError, match="frozen_definition"):
        visionai_registry.CARD_BEHAVIOR_BLOCK_REGISTRY["new"] = {}
    with pytest.raises(TypeError, match="frozen_definition"):
        disposition_ledger._KNOWN_DISPOSITIONS["new"] = "mutated"
    authority = visionai_registry.CARD_BEHAVIOR_BLOCK_REGISTRY
    with pytest.raises(TypeError, match="frozen_definition"):
        authority |= {"new": {}}
    with pytest.raises(TypeError):
        dict.__setitem__(authority, "new", {})  # type: ignore[arg-type]
    frozen_rows = next(iter(mechanic_support.MECHANIC_SUPPORT.values()))[
        "normal_path_surfaces"
    ]
    with pytest.raises((AttributeError, TypeError)):
        list.append(frozen_rows, "mutated")  # type: ignore[arg-type]


def test_resolved_request_is_stable_after_frozen_backing_rebind_probes(
    tmp_path: Path,
) -> None:
    request = audited_request(tmp_path, "ShadowPriest")
    expected = compile_package(request)
    seen: set[int] = set()
    frozen_values: list[FrozenDefinitionMapping | FrozenDefinitionList] = []
    stack: list[object] = []
    for module_name in _C3_C4_DEFINITION_CLOSURE_MODULES:
        module = importlib.import_module(f"hsconfig.{module_name}")
        stack.extend(
            value
            for name, value in vars(module).items()
            if name.isupper()
        )
    while stack:
        value = stack.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, FrozenDefinitionMapping):
            frozen_values.append(value)
            stack.extend(value.values())
        elif isinstance(value, FrozenDefinitionList):
            frozen_values.append(value)
            stack.extend(value)
        elif isinstance(value, Mapping):
            stack.extend(value.values())
        elif isinstance(value, (tuple, list, set, frozenset)):
            stack.extend(value)

    assert frozen_values
    for value in frozen_values:
        with pytest.raises((AttributeError, TypeError)):
            value._values = {}  # type: ignore[attr-defined]
        backing_name = (
            "_FrozenDefinitionMapping__values"
            if isinstance(value, FrozenDefinitionMapping)
            else "_FrozenDefinitionList__values"
        )
        with pytest.raises((AttributeError, TypeError)):
            setattr(value, backing_name, ())
        with pytest.raises((AttributeError, TypeError)):
            object.__setattr__(value, "_values", {})
        with pytest.raises((AttributeError, TypeError)):
            object.__setattr__(value, backing_name, ())

    assert compile_package(request) == expected


def test_compiler_adopts_single_support_authority_without_legacy_import() -> None:
    compiler_tree = ast.parse(
        Path("src/hsconfig/package_compiler.py").read_text(
            encoding="utf-8"
        )
    )
    support_tree = ast.parse(
        Path("src/hsconfig/package_compiler_support.py").read_text(
            encoding="utf-8"
        )
    )
    compiler_imports = {
        node.module
        for node in ast.walk(compiler_tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "hsconfig.package_compiler_support" in compiler_imports
    assert "hsconfig.package_legacy_workflow" not in compiler_imports

    support_defs = {
        node.name
        for node in support_tree.body
        if isinstance(node, ast.FunctionDef)
    }
    assert "_build_package_disposition_ledger" in support_defs
    assert "_filter_runtime_rows_by_claim_ids" in support_defs
    assert not Path("src/hsconfig/package_legacy_workflow.py").exists()


def test_pre_authority_owner_mapping_is_exact_and_rejects_swaps() -> None:
    counts = {
        owner: tuple(PRE_AUTHORITY_OWNER_BY_PATH.values()).count(owner)
        for owner in ProjectionOwner
    }
    assert counts == {
        ProjectionOwner.RESOLUTION: 15,
        ProjectionOwner.RESEARCH: 9,
        ProjectionOwner.PACKAGE_COMPILER: 23,
    }
    with pytest.raises(ValueError, match="projection_owner_mismatch"):
        NamedJsonProjection(
            "reports/deck_identity.json",
            ProjectionOwner.RESEARCH,
            FrozenJsonDocument.from_value({}),
        )
    with pytest.raises(ValueError, match="projection_path_unknown"):
        NamedJsonProjection(
            "reports/unknown.json",
            ProjectionOwner.RESOLUTION,
            FrozenJsonDocument.from_value({}),
        )


def test_boarlock_keeps_rejected_static_combo_truth_only_in_audit(
    tmp_path: Path,
) -> None:
    compiled = compile_package(audited_request(tmp_path, "Boarlock"))
    assert compiled.combo_plan.decisions == ()
    assert compiled.combo_plan.suppressions == ()
    audit = next(
        row.document.to_value()
        for row in compiled.json_projections
        if row.relative_path == "reports/source_contract_audit.json"
    )
    combo_row = audit["claim_rows"]["claim_83be054c2c6e"]
    assert combo_row["surfaces"]["combo"]["reason"] == (
        "combo_requires_public_guide_source"
    )


def test_compile_is_stable_after_globalvalues_authority_rebinding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hsconfig.compile_globalvalues as compile_globalvalues

    request = audited_request(tmp_path, "ShadowPriest")
    expected = compile_package(request)

    monkeypatch.setattr(
        compile_globalvalues,
        "TOP_LEVEL_KEYS",
        frozenset(),
    )

    assert compile_package(request) == expected


def test_resolved_incomplete_baseline_is_closed_before_ambient_rebinding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hsconfig.globalvalues_baseline as globalvalues_baseline

    original = audited_request(tmp_path, "ShadowPriest")
    preconfig = original.snapshot.general_preconfig.to_value()
    preconfig["globalvalues_baseline"].pop("GlobalHeroAttack")
    preconfig["globalvalues_baseline_receipt"]["baseline"].pop(
        "GlobalHeroAttack"
    )
    request = ResolvedPackageRequest(
        snapshot=PackageResolutionSnapshot.from_strict(
            original.snapshot.strict_build_context,
            preconfig,
        ),
        invocation=original.invocation,
        plan_overrides=original.plan_overrides,
        acquisition_closure_input=original.acquisition_closure_input,
        mulligan_gap_input=original.mulligan_gap_input,
    )
    expected = compile_package(request)

    monkeypatch.setattr(
        globalvalues_baseline,
        "_FALLBACK_GLOBALVALUES_BASELINE",
        {},
    )
    monkeypatch.setattr(
        globalvalues_baseline,
        "FALLBACK_GLOBALVALUES_BASELINE",
        {},
        raising=False,
    )

    assert compile_package(request) == expected


def test_compile_is_stable_across_approved_definition_closure_rebinding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = audited_request(tmp_path, "ShadowPriest")
    expected = compile_package(request)
    rebound: list[str] = []
    mutation_probes = 0

    for module_name in _C3_C4_DEFINITION_CLOSURE_MODULES:
        module = importlib.import_module(f"hsconfig.{module_name}")
        for name, value in tuple(vars(module).items()):
            if not name.isupper():
                continue
            poison: object
            if isinstance(value, Mapping):
                mutation_probes += 1
                with pytest.raises((AttributeError, TypeError)):
                    value.clear()
                poison = {}
            elif isinstance(value, (set, frozenset)):
                mutation_probes += 1
                with pytest.raises((AttributeError, TypeError)):
                    value.clear()
                poison = frozenset()
            elif isinstance(value, (list, tuple)):
                if isinstance(value, list):
                    mutation_probes += 1
                    with pytest.raises((AttributeError, TypeError)):
                        value.clear()
                poison = ()
            elif isinstance(value, (str, int, float, bool)):
                poison = object()
            else:
                continue
            monkeypatch.setattr(module, name, poison)
            rebound.append(f"{module_name}.{name}")

    assert "compile_globalvalues.TOP_LEVEL_KEYS" in rebound
    assert mutation_probes > 0
    assert compile_package(request) == expected


@pytest.mark.parametrize(
    ("family", "owner"),
    (
        ("GlobalValues", "combo"),
        ("Mulligan", "cardid"),
        ("CardID", "mulligan"),
        ("Combo", "globalvalues"),
    ),
)
def test_compiled_runtime_surface_rejects_wrong_known_owner_swap(
    family: str,
    owner: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="compiled_runtime_owner_mismatch",
    ):
        CompiledRuntimeSurface(
            file_name=f"{family}.json",
            family=family,
            owner=owner,
            decision_ids=(),
            document=FrozenJsonDocument.from_value({}),
        )


@pytest.mark.parametrize(
    ("family", "file_name"),
    (
        ("GlobalValues", "Mulligan.json"),
        ("Mulligan", "GlobalValues.json"),
        ("Combo", "CARD_001.json"),
        ("CardID", "Combo.json"),
    ),
)
def test_compiled_runtime_surface_binds_family_to_file_name(
    family: str,
    file_name: str,
) -> None:
    owner = {
        "GlobalValues": "globalvalues",
        "Mulligan": "mulligan",
        "Combo": "combo",
        "CardID": "cardid",
    }[family]
    with pytest.raises(
        ValueError,
        match="compiled_runtime_file_family_mismatch",
    ):
        CompiledRuntimeSurface(
            file_name=file_name,
            family=family,
            owner=owner,
            decision_ids=(),
            document=FrozenJsonDocument.from_value({}),
        )


def test_all_audited_gameplan_projections_match_fresh_legacy_semantics(
    tmp_path: Path,
) -> None:
    from tests.helpers.package_byte_contract import prepare_audited_packages

    legacy = prepare_audited_packages(tmp_path / "legacy")
    for deck_name, package_root in legacy.items():
        compiled = compile_package(
            audited_request(tmp_path / "requests" / deck_name, deck_name)
        )
        actual = next(
            row.document
            for row in compiled.json_projections
            if row.relative_path == "reports/gameplan_contract.json"
        )
        expected = FrozenJsonDocument.from_json_bytes(
            (
                package_root
                / "reports"
                / "gameplan_contract.json"
            ).read_bytes()
        )
        assert actual.to_value() == expected.to_value(), deck_name
        assert sha256(actual.canonical_json).hexdigest() == sha256(
            expected.canonical_json
        ).hexdigest()
