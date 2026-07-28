from pathlib import Path

import pytest

from hsconfig.package_domain import (
    DispositionLedger,
    GlobalValueDecision,
    GlobalValueDecisionKind,
    GlobalValuesDecisionLedger,
    LayeredEvidenceContract,
    MulliganPlanModel,
)
from hsconfig.package_model import (
    PackageArtifact,
    PackageModel,
    build_runtime_surface_plan,
    content_root_sha256,
    load_package_model,
    load_package_model_from_view,
)
from hsconfig.package_renderer import render_package_model, write_rendered_package


def test_renderer_derives_runtime_and_reports_from_one_typed_model() -> None:
    model = _model()

    rendered = render_package_model(model)

    assert rendered == render_package_model(model)
    names = {artifact.relative_path for artifact in rendered.artifacts}
    runtime_names = names - {"reports/package_manifest.json", "reports/package_model.json", "reports/mulligan_plan_report.json"}
    assert runtime_names == set(model.runtime_surface_plan.expected_files)
    assert rendered.content_root_sha256


def test_renderer_refuses_nonempty_destination_and_verifies_written_tree(tmp_path: Path) -> None:
    rendered = render_package_model(_model())
    destination = tmp_path / "package"

    write_rendered_package(rendered, destination)

    assert (destination / "GlobalValues.json").is_file()
    with pytest.raises(ValueError, match="destination_must_be_empty"):
        write_rendered_package(rendered, destination)


def test_loader_rejects_a_package_with_a_manifest_digest_mismatch(tmp_path: Path) -> None:
    destination = tmp_path / "package"
    write_rendered_package(render_package_model(_model()), destination)
    target = destination / "GlobalValues.json"
    target.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="typed_package_manifest_mismatch"):
        load_package_model(destination)


def test_loader_reads_canonical_json_through_a_package_view() -> None:
    rendered = render_package_model(_model())
    view = _MemoryPackageView(
        {artifact.relative_path: artifact.content for artifact in rendered.artifacts}
    )

    assert load_package_model_from_view(view) == _model()


def test_loader_rejects_a_persisted_typed_report_parity_mismatch() -> None:
    rendered = render_package_model(_model())
    files = {artifact.relative_path: artifact.content for artifact in rendered.artifacts}
    files["reports/mulligan_plan_report.json"] = b"{}\n"
    non_manifest = tuple(
        PackageArtifact(relative_path=path, content=content)
        for path, content in sorted(files.items())
        if path != "reports/package_manifest.json"
    )
    import json

    files["reports/package_manifest.json"] = (
        json.dumps(
            {
                "schema_version": 1,
                "content_root_sha256": content_root_sha256(non_manifest),
                "artifacts": [
                    {
                        "relative_path": artifact.relative_path,
                        "size": artifact.size,
                        "sha256": artifact.sha256,
                    }
                    for artifact in non_manifest
                ],
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )

    with pytest.raises(ValueError, match="typed_package_report_parity_mismatch"):
        load_package_model_from_view(_MemoryPackageView(files))


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


class _MemoryPackageView:
    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    def file_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._files))

    def read_bytes(self, relative_path: str) -> bytes:
        return self._files[relative_path]

    def read_json(self, relative_path: str) -> object:
        import json

        return json.loads(self.read_bytes(relative_path))

    def exists(self, relative_path: str) -> bool:
        return relative_path in self._files
