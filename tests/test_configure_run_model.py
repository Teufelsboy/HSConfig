from hsconfig.configure_run_model import create_configure_run_model, render_configure_run_model
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
