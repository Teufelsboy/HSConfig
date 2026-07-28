from dataclasses import replace
import json
from pathlib import Path

import pytest

from hsconfig.configure_run_model import (
    ConfigureRunModel,
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
    write_rendered_configure_run,
)
from hsconfig.package_domain import (
    DispositionLedger,
    GlobalValueDecision,
    GlobalValueDecisionKind,
    GlobalValuesDecisionLedger,
    LayeredEvidenceContract,
    MulliganPlanModel,
)
from hsconfig.package_model import PackageModel, build_runtime_surface_plan


def test_configure_run_is_immutable_complete_and_deterministic() -> None:
    run = create_configure_run_model(
        package=_model(),
        stage_artifacts={
            "01_manifest/input.json": b"{}",
            "02_source_documents/source.json": b"{}",
            "03_research/research.json": b"{}",
        },
    )

    rendered = render_configure_run_model(run)

    assert rendered == render_configure_run_model(run)
    assert tuple(item.relative_path for item in rendered.artifacts) == tuple(
        sorted(item.relative_path for item in rendered.artifacts)
    )
    assert "04_package/CustomConfig/fixture_deck/GlobalValues.json" in {
        item.relative_path for item in rendered.artifacts
    }
    assert "configure_summary.json" in {
        item.relative_path for item in rendered.artifacts
    }


@pytest.mark.parametrize(
    ("source_stage", "autopilot_stage", "expected_unavailable"),
    [
        (
            "02_source_documents",
            None,
            {
                "02_source_acquisition": "02_source_documents_selected",
                "02_source_autopilot": "not_requested",
                "03_source_autopilot": "not_requested",
            },
        ),
        (
            "02_source_documents",
            "02_source_autopilot",
            {
                "02_source_acquisition": "02_source_documents_selected",
                "03_source_autopilot": "02_source_autopilot_selected",
            },
        ),
        (
            "02_source_acquisition",
            None,
            {
                "02_source_autopilot": "not_requested",
                "02_source_documents": "02_source_acquisition_selected",
                "03_source_autopilot": "not_requested",
            },
        ),
        (
            "02_source_acquisition",
            "03_source_autopilot",
            {
                "02_source_autopilot": "03_source_autopilot_selected",
                "02_source_documents": "02_source_acquisition_selected",
            },
        ),
    ],
)
def test_configure_run_accepts_the_full_legal_source_autopilot_matrix(
    source_stage: str,
    autopilot_stage: str | None,
    expected_unavailable: dict[str, str],
) -> None:
    stage_artifacts = {
        "01_manifest/input.json": b"{}",
        f"{source_stage}/source.json": b"{}",
        "03_research/research.json": b"{}",
    }
    if autopilot_stage is not None:
        stage_artifacts[f"{autopilot_stage}/autopilot.json"] = b"{}"

    rendered = render_configure_run_model(
        create_configure_run_model(
            package=_model(),
            stage_artifacts=stage_artifacts,
        )
    )
    summary = json.loads(
        next(
            artifact.content
            for artifact in rendered.artifacts
            if artifact.relative_path == "configure_summary.json"
        )
    )

    assert summary["unavailable_stages"] == expected_unavailable


@pytest.mark.parametrize(
    ("source_stage", "autopilot_stages"),
    [
        ("02_source_documents", ("03_source_autopilot",)),
        ("02_source_acquisition", ("02_source_autopilot",)),
        (
            "02_source_documents",
            ("02_source_autopilot", "03_source_autopilot"),
        ),
    ],
)
def test_configure_run_rejects_illegal_source_autopilot_combinations(
    source_stage: str, autopilot_stages: tuple[str, ...]
) -> None:
    stage_artifacts = {
        "01_manifest/input.json": b"{}",
        f"{source_stage}/source.json": b"{}",
        "03_research/research.json": b"{}",
        **{
            f"{stage}/autopilot.json": b"{}"
            for stage in autopilot_stages
        },
    }

    with pytest.raises(ValueError, match="configure_run_autopilot_stage_invalid"):
        create_configure_run_model(
            package=_model(),
            stage_artifacts=stage_artifacts,
        )


@pytest.mark.parametrize(
    "source_paths",
    [
        (),
        (
            "02_source_documents/source.json",
            "02_source_acquisition/source.json",
        ),
    ],
)
def test_configure_run_requires_exactly_one_source_alternative(
    source_paths: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="configure_run_source_stage_invalid"):
        create_configure_run_model(
            package=_model(),
            stage_artifacts={
                "01_manifest/input.json": b"{}",
                "03_research/research.json": b"{}",
                **{path: b"{}" for path in source_paths},
            },
        )


@pytest.mark.parametrize(
    "reserved_path",
    [
        "configure_summary.json",
        "04_package",
        "04_package/reports/caller.json",
        "04_package/CustomConfig/caller.json",
    ],
)
def test_configure_run_rejects_reserved_paths(reserved_path: str) -> None:
    with pytest.raises(ValueError, match="configure_run_reserved_path"):
        create_configure_run_model(
            package=_model(),
            stage_artifacts={
                "01_manifest/input.json": b"{}",
                "02_source_documents/source.json": b"{}",
                "03_research/research.json": b"{}",
                reserved_path: b"{}",
            },
        )


def test_configure_tuple_fields_copy_caller_lists() -> None:
    canonical = create_configure_run_model(
        package=_model(),
        stage_artifacts={
            "01_manifest/input.json": b"{}",
            "02_source_documents/source.json": b"{}",
            "03_research/research.json": b"{}",
        },
    )
    caller_stage_artifacts = list(canonical.stage_artifacts)
    run = ConfigureRunModel(
        canonical.deck_name,
        canonical.deck_fingerprint,
        canonical.package,
        caller_stage_artifacts,
    )
    canonical_rendered = render_configure_run_model(run)
    caller_rendered_artifacts = list(canonical_rendered.artifacts)
    rendered = RenderedConfigureRun(
        run,
        caller_rendered_artifacts,
        canonical_rendered.content_root_sha256,
    )

    caller_stage_artifacts.clear()
    caller_rendered_artifacts.clear()

    assert len(run.stage_artifacts) == 3
    assert rendered.artifacts == canonical_rendered.artifacts


def test_configure_writer_rejects_a_forged_revision_before_writing(
    tmp_path: Path,
) -> None:
    rendered = render_configure_run_model(
        create_configure_run_model(
            package=_model(),
            stage_artifacts={
                "01_manifest/input.json": b"{}",
                "02_source_documents/source.json": b"{}",
                "03_research/research.json": b"{}",
            },
        )
    )
    destination = tmp_path / "configure"

    with pytest.raises(ValueError, match="rendered_configure_run_invalid"):
        write_rendered_configure_run(
            replace(rendered, content_root_sha256="0" * 64),
            destination,
        )

    assert not destination.exists()


def _model() -> PackageModel:
    mulligan = MulliganPlanModel("Fixture Deck", (), (), (), 0)
    globalvalues = GlobalValuesDecisionLedger(
        "fingerprint",
        "baseline",
        (
            GlobalValueDecision(
                "fingerprint", "HeroValue", GlobalValueDecisionKind.COPY_BASELINE,
                b'{"values":[]}', b'{"values":[]}', "baseline", (), "fixture",
            ),
        ),
        "globalvalues",
    )
    dispositions = DispositionLedger("fingerprint", (), (), "dispositions")
    evidence = LayeredEvidenceContract("fingerprint", (), False, 0, 0, "evidence")
    return PackageModel(
        "Fixture Deck", "fingerprint", mulligan, globalvalues, dispositions, evidence,
        build_runtime_surface_plan(
            mulligan_plan=mulligan, globalvalues_ledger=globalvalues,
            disposition_ledger=dispositions, combo_decision_ids=(),
        ),
    )
