from dataclasses import replace
import json
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


def test_renderer_uses_the_linked_physical_owner_payload_for_cardid() -> None:
    rendered = render_package_model(_model_with_cardid())

    payload = json.loads(
        next(
            artifact.content
            for artifact in rendered.artifacts
            if artifact.relative_path == "CARD_A.json"
        )
    )

    assert payload == {
        "ConfigComment": "linked physical owner",
        "GameCardId": "CARD_A",
    }


def test_globalvalues_runtime_and_report_have_one_row_per_ledger_key() -> None:
    model = _model_with_ordered_globalvalues()
    rendered = render_package_model(model)
    artifacts = {
        artifact.relative_path: json.loads(artifact.content)
        for artifact in rendered.artifacts
        if artifact.relative_path in {
            "GlobalValues.json",
            "reports/package_model.json",
        }
    }
    runtime = artifacts["GlobalValues.json"]
    report_rows = artifacts["reports/package_model.json"][
        "globalvalues_ledger"
    ]["decisions"]
    globalvalues_surface = next(
        surface
        for surface in model.runtime_surface_plan.surfaces
        if surface.family == "GlobalValues"
    )

    assert len(runtime) == 3
    assert set(runtime) == {
        "ConfigComment",
        "FirstTurnValueWeight",
        "GameCardId",
    }
    assert [row["key"] for row in report_rows] == [
        "GameCardId",
        "ConfigComment",
        "FirstTurnValueWeight",
    ]
    assert globalvalues_surface.decision_ids == (
        "globalvalues:ConfigComment",
        "globalvalues:FirstTurnValueWeight",
        "globalvalues:GameCardId",
    )


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
        PackageArtifact.from_content(relative_path=path, content=content)
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


def test_loader_rejects_unverified_manifest_size_and_digest_records() -> None:
    rendered = render_package_model(_model())
    files = {artifact.relative_path: artifact.content for artifact in rendered.artifacts}
    manifest = json.loads(files["reports/package_manifest.json"])
    manifest["artifacts"][0]["size"] = 0
    manifest["artifacts"][0]["sha256"] = ""
    files["reports/package_manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )

    with pytest.raises(ValueError, match="typed_package_manifest_mismatch"):
        load_package_model_from_view(_MemoryPackageView(files))


def test_loader_accepts_a_verified_zero_size_manifest_record() -> None:
    rendered = render_package_model(_model())
    files = {artifact.relative_path: artifact.content for artifact in rendered.artifacts}
    files["empty.bin"] = b""
    non_manifest = tuple(
        PackageArtifact.from_content(relative_path=path, content=content)
        for path, content in sorted(files.items())
        if path != "reports/package_manifest.json"
    )
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

    assert load_package_model_from_view(_MemoryPackageView(files)) == _model()


def test_package_writer_rejects_a_forged_render_before_writing(
    tmp_path: Path,
) -> None:
    rendered = render_package_model(_model())
    destination = tmp_path / "package"

    with pytest.raises(ValueError, match="rendered_package_invalid"):
        write_rendered_package(
            replace(rendered, content_root_sha256="0" * 64),
            destination,
        )

    assert not destination.exists()


def test_package_writer_rejects_an_existing_file_destination(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "package"
    destination.write_bytes(b"occupied")

    with pytest.raises(ValueError, match="destination_must_be_empty"):
        write_rendered_package(render_package_model(_model()), destination)


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


def _model_with_cardid() -> PackageModel:
    from hsconfig.package_domain import (
        CardDisposition,
        CardDispositionRow,
        EvidenceLane,
    )

    model = _model()
    dispositions = DispositionLedger(
        "fingerprint",
        (
            CardDispositionRow(
                "fingerprint",
                "CARD_A",
                "main_deck",
                b'{"ConfigComment":"linked physical owner","GameCardId":"CARD_A"}',
                EvidenceLane.OFFICIAL_CARD_DATA,
                ("evidence-card",),
                (),
                "CARD_A",
                CardDisposition.RUNTIME_EMITTED,
                ("CARD_A.json",),
                "fixture",
            ),
        ),
        (),
        "dispositions",
    )
    return PackageModel(
        model.deck_name,
        model.deck_fingerprint,
        model.mulligan_plan,
        model.globalvalues_ledger,
        dispositions,
        model.evidence_contract,
        build_runtime_surface_plan(
            mulligan_plan=model.mulligan_plan,
            globalvalues_ledger=model.globalvalues_ledger,
            disposition_ledger=dispositions,
            combo_decision_ids=(),
        ),
    )


def _model_with_ordered_globalvalues() -> PackageModel:
    model = _model()
    decisions = tuple(
        GlobalValueDecision(
            "fingerprint",
            key,
            GlobalValueDecisionKind.COPY_BASELINE,
            b'"baseline"',
            b'"baseline"',
            "baseline",
            (),
            "fixture",
        )
        for key in (
            "GameCardId",
            "ConfigComment",
            "FirstTurnValueWeight",
        )
    )
    ledger = GlobalValuesDecisionLedger(
        "fingerprint",
        "baseline",
        decisions,
        "globalvalues",
    )
    return PackageModel(
        model.deck_name,
        model.deck_fingerprint,
        model.mulligan_plan,
        ledger,
        model.disposition_ledger,
        model.evidence_contract,
        build_runtime_surface_plan(
            mulligan_plan=model.mulligan_plan,
            globalvalues_ledger=ledger,
            disposition_ledger=model.disposition_ledger,
            combo_decision_ids=(),
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
