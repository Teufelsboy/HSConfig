from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
import json
from pathlib import Path

import pytest

from hsconfig.package_assembler import (
    ArtifactPhase,
    ArtifactPlan,
    PackageModel,
    PlannedArtifact,
    assemble_package,
)
from hsconfig.package_compiler import compile_package
from hsconfig.package_render_authority import render_package_authority
from hsconfig.package_request import FrozenJsonDocument
from tests.helpers.audited_package_request import audited_request


def test_assembler_builds_the_complete_sorted_shadowpriest_plan(
    tmp_path: Path,
) -> None:
    model = assemble_package(
        compile_package(audited_request(tmp_path, "ShadowPriest"))
    )
    paths = tuple(row.relative_path for row in model.artifact_plan.artifacts)

    assert isinstance(model, PackageModel)
    assert paths == tuple(sorted(paths))
    fixture = json.loads(
        Path("tests/fixtures/package-byte-contract-v1.json").read_text(
            encoding="utf-8"
        )
    )
    expected = tuple(
        sorted(
            row["relative_path"]
            for row in fixture["decks"]["ShadowPriest"]["artifacts"]
        )
    )
    assert paths == expected
    assert "reports/package_model.json" not in paths
    assert "reports/package_manifest.json" not in paths
    assert not any(path.endswith("/Combo.json") for path in paths)
    assert {
        "reports/runtime_surface_ledger.json",
        "reports/validation_report.json",
        "reports/output_ownership_manifest.json",
        "reports/operator_summary.json",
        "reports/card_semantic_audit.md",
        "reports/strong_promotion_report.json",
        "reports/source_evidence_closure.json",
        "package_derivation_receipt.json",
    }.issubset(paths)
    with pytest.raises(FrozenInstanceError):
        model.artifact_plan = ArtifactPlan(())  # type: ignore[misc]


def test_all_audited_artifact_plans_equal_the_frozen_fixture(
    tmp_path: Path,
) -> None:
    fixture = json.loads(
        Path("tests/fixtures/package-byte-contract-v1.json").read_text(
            encoding="utf-8"
        )
    )
    total = 0
    for deck_name, expected_deck in fixture["decks"].items():
        model = assemble_package(
            compile_package(audited_request(tmp_path, deck_name))
        )
        actual = tuple(
            row.relative_path for row in model.artifact_plan.artifacts
        )
        expected = tuple(
            sorted(
                row["relative_path"]
                for row in expected_deck["artifacts"]
            )
        )
        assert actual == expected, deck_name
        assert 72 <= len(actual) <= 74
        assert not any(path.endswith("/Combo.json") for path in actual)
        total += len(actual)
    assert total == 878


def test_compiled_and_model_authority_graph_rejects_low_level_rebinding(
    tmp_path: Path,
) -> None:
    request = audited_request(tmp_path, "ShadowPriest")
    compiled = compile_package(request)
    model = assemble_package(compiled)
    pending: list[object] = [request, compiled, model]
    seen: set[int] = set()
    authority_nodes: list[object] = []

    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if is_dataclass(value) and not isinstance(value, type):
            authority_nodes.append(value)
            pending.extend(
                getattr(value, field.name) for field in fields(value)
            )
        elif isinstance(value, tuple):
            pending.extend(value)

    assert authority_nodes
    for node in authority_nodes:
        assert not hasattr(node, "__dict__")
        for field in fields(node):
            current = getattr(node, field.name)
            with pytest.raises((AttributeError, TypeError)):
                setattr(node, field.name, current)
            with pytest.raises((AttributeError, TypeError)):
                object.__setattr__(node, field.name, current)


def test_request_deck_code_cannot_be_forged_before_compile_and_render(
    tmp_path: Path,
) -> None:
    request = audited_request(
        tmp_path,
        "ShadowPriest",
        fixture_paths=True,
    )
    original_deck_code = request.invocation.deck_code
    expected_hash = request.snapshot.strict_build_context
    assert expected_hash is not None
    expected_deck_code_sha256 = expected_hash.inputs.deck_code_sha256
    mutation_rejected = False

    try:
        object.__setattr__(
            request.invocation,
            "deck_code",
            "FORGED-DECK-CODE",
        )
    except (AttributeError, TypeError):
        mutation_rejected = True

    compiled = compile_package(request)
    rendered = render_package_authority(assemble_package(compiled))
    input_manifest = rendered.artifacts.read_json(
        "reports/input_manifest.json"
    )

    assert mutation_rejected is True
    assert request.invocation.deck_code == original_deck_code
    assert compiled.deck_code_sha256 == expected_deck_code_sha256
    assert input_manifest["deck_code"] == original_deck_code


def test_compiled_projection_document_cannot_be_forged_before_render(
    tmp_path: Path,
) -> None:
    compiled = compile_package(
        audited_request(tmp_path, "ShadowPriest")
    )
    projection = next(
        row
        for row in compiled.json_projections
        if row.relative_path
        == "reports/research/card_usage_expectations.json"
    )
    original = projection.document.canonical_json
    forged = FrozenJsonDocument.from_value(
        {"forged_post_compile_evidence": True}
    )
    mutation_rejected = False

    try:
        object.__setattr__(projection, "document", forged)
    except (AttributeError, TypeError):
        mutation_rejected = True

    rendered = render_package_authority(assemble_package(compiled))

    assert mutation_rejected is True
    rendered_value = rendered.artifacts.read_json(
        projection.relative_path
    )
    assert rendered_value == json.loads(original)
    assert rendered_value != forged.to_value()


@pytest.mark.parametrize(
    ("paths", "error"),
    [
        (("reports/a.json", "reports/a.json"), "artifact_path_duplicate"),
        (("reports/A.json", "reports/a.json"), "artifact_path_casefold_collision"),
        (("reports/a", "reports/a/b.json"), "artifact_path_prefix_collision"),
        (("../escape.json",), "artifact_path_invalid"),
        (("reports\\bad.json",), "artifact_path_invalid"),
        (("/absolute.json",), "artifact_path_invalid"),
        (("./reports/a.json",), "artifact_path_invalid"),
        (("C:/escape.json",), "artifact_path_invalid"),
        (("reports/C:/escape.json",), "artifact_path_invalid"),
        (("reports/bad\u0000.json",), "artifact_path_invalid"),
        (("reports/bad.json.",), "artifact_path_invalid"),
        (("reports/bad.json ",), "artifact_path_invalid"),
        (
            ("reports/A", "reports/a/b.json"),
            "artifact_path_casefold_prefix_collision",
        ),
    ],
)
def test_artifact_plan_rejects_unsafe_or_colliding_paths(
    paths: tuple[str, ...],
    error: str,
) -> None:
    rows = tuple(
        PlannedArtifact(
            relative_path=path,
            owner="package_compiler",
            phase=ArtifactPhase.PRE_AUTHORITY,
        )
        for path in paths
    )

    with pytest.raises(ValueError, match=error):
        ArtifactPlan(rows)


def test_planned_artifact_rejects_unknown_owner_and_phase() -> None:
    with pytest.raises(ValueError, match="artifact_owner_invalid"):
        PlannedArtifact(
            relative_path="reports/a.json",
            owner="unknown",
            phase=ArtifactPhase.PRE_AUTHORITY,
        )
    with pytest.raises(ValueError, match="artifact_phase_invalid"):
        PlannedArtifact(
            relative_path="reports/a.json",
            owner="package_compiler",
            phase="unknown",  # type: ignore[arg-type]
        )


def test_artifact_plan_rejects_unknown_or_misphased_pre_authority_path() -> None:
    with pytest.raises(
        ValueError,
        match="artifact_projection_authority_invalid",
    ):
        ArtifactPlan(
            (
                PlannedArtifact(
                    "reports/unknown.json",
                    "package_compiler",
                    ArtifactPhase.PRE_AUTHORITY,
                ),
            )
        )
    with pytest.raises(
        ValueError,
        match="artifact_projection_authority_invalid",
    ):
        ArtifactPlan(
            (
                PlannedArtifact(
                    "reports/deck_identity.json",
                    "resolution",
                    ArtifactPhase.VALIDATION,
                ),
            )
        )


@pytest.mark.parametrize(
    "artifact",
    (
        PlannedArtifact(
            "reports/x.json",
            "globalvalues",
            ArtifactPhase.CORE_RUNTIME,
        ),
        PlannedArtifact(
            "CustomConfig/x/a.json",
            "strict_package_validation",
            ArtifactPhase.VALIDATION,
        ),
        PlannedArtifact(
            "reports/wrong.json",
            "package_derivation_receipt",
            ArtifactPhase.RECEIPT,
        ),
    ),
)
def test_artifact_plan_rejects_owner_phase_root_mismatch(
    artifact: PlannedArtifact,
) -> None:
    with pytest.raises(ValueError, match="artifact_authority_invalid"):
        ArtifactPlan((artifact,))


def test_package_model_rejects_an_empty_artifact_plan(tmp_path: Path) -> None:
    compiled = compile_package(audited_request(tmp_path, "ShadowPriest"))

    with pytest.raises(ValueError, match="package_model_artifact_plan_empty"):
        PackageModel(compiled, ArtifactPlan(()))
    with pytest.raises(
        ValueError,
        match="package_model_artifact_plan_incomplete",
    ):
        PackageModel(
            compiled,
            ArtifactPlan(
                (
                    PlannedArtifact(
                        "reports/deck_identity.json",
                        "resolution",
                        ArtifactPhase.PRE_AUTHORITY,
                    ),
                )
            ),
        )
