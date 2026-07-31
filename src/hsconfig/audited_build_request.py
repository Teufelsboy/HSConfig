"""Frozen-only request and configure-run bridge for audited deck builds."""

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from hsconfig.audited_deck_catalog import (
    AUDITED_DECK_CATALOG_PATH,
    load_audited_deck_catalog,
)
from hsconfig.build_context import resolve_build_context
from hsconfig.build_input_catalog import (
    AuditedBuildInputSet,
    FrozenBuildResourceStore,
    load_packaged_audited_build_inputs,
    load_packaged_audited_build_resource_store,
)
from hsconfig.build_inputs import CanonicalBuildInputs
from hsconfig.configure_run_model import (
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
)
from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.package_request import (
    PackageInvocation,
    PackageResolutionSnapshot,
    ResolvedPackageRequest,
)


class _BuildResourceReader(Protocol):
    def read_by_sha256(self, content_sha256: str) -> bytes: ...


def resolve_frozen_audited_package_request(
    *,
    inputs: CanonicalBuildInputs,
    resources: _BuildResourceReader,
    deck_code: str,
) -> ResolvedPackageRequest:
    """Resolve without filesystem, network, clock, runtime, or local card DB."""

    if (
        not isinstance(deck_code, str)
        or sha256(deck_code.encode("utf-8")).hexdigest()
        != inputs.deck_code_sha256
    ):
        raise ValueError("frozen_audited_deck_code_mismatch")
    context = resolve_build_context(inputs, resources=resources)
    preconfig = _json_document(context.general_preconfig_canonical_json)
    closure = _json_document(context.acquisition_closure_canonical_json)
    return ResolvedPackageRequest.from_values(
        snapshot=PackageResolutionSnapshot.from_strict(context, preconfig),
        invocation=PackageInvocation(
            deck_code=deck_code,
            runtime_root="runtime-write-fence",
            cards_json=None,
            claims_json=None,
            guide_sources_json=None,
            plan_reports_dir=None,
            target_config_mode="preview",
            include_disposition_diagnostics=False,
        ),
        plan_overrides={},
        acquisition_closure_input=closure,
        mulligan_gap_input=[],
    )


def resolve_audited_package_request(
    *,
    deck_name: str,
    catalog_path: Path = AUDITED_DECK_CATALOG_PATH,
) -> ResolvedPackageRequest:
    """Select one catalog identity and delegate to the frozen-only core."""

    _audited, resources, row, inputs = _audited_authority(
        deck_name=deck_name,
        catalog_path=catalog_path,
    )
    return resolve_frozen_audited_package_request(
        inputs=inputs,
        resources=resources,
        deck_code=str(row["deck_code"]),
    )


def render_audited_configure_run(
    *,
    deck_name: str,
    catalog_path: Path = AUDITED_DECK_CATALOG_PATH,
) -> RenderedConfigureRun:
    """Compile and render one frozen audited request through core authorities."""

    _audited, resources, row, inputs = _audited_authority(
        deck_name=deck_name,
        catalog_path=catalog_path,
    )
    return _render_selected_run(
        inputs=inputs,
        resources=resources,
        deck_code=str(row["deck_code"]),
    )


def render_all_audited_configure_runs(
    catalog_path: Path = AUDITED_DECK_CATALOG_PATH,
) -> tuple[tuple[str, RenderedConfigureRun], ...]:
    """Return the exact catalog-ordered immutable twelve-run rebuild set."""

    rows = load_audited_deck_catalog(catalog_path)
    audited = load_packaged_audited_build_inputs()
    resources = load_packaged_audited_build_resource_store(
        audited_inputs=audited
    )
    by_name = {inputs.deck_name: inputs for inputs in audited.builds}
    result = tuple(
        (
            str(row["deck_name"]),
            _render_selected_run(
                inputs=by_name[str(row["deck_name"])],
                resources=resources,
                deck_code=str(row["deck_code"]),
            ),
        )
        for row in rows
    )
    if len(result) != 12 or len({name for name, _run in result}) != 12:
        raise ValueError("audited_build_rendered_set_invalid")
    return result


def _render_selected_run(
    *,
    inputs: CanonicalBuildInputs,
    resources: FrozenBuildResourceStore,
    deck_code: str,
) -> RenderedConfigureRun:
    request = resolve_frozen_audited_package_request(
        inputs=inputs,
        resources=resources,
        deck_code=deck_code,
    )
    package = assemble_package(compile_package(request))
    source_payloads = tuple(
        resources.read_by_sha256(digest)
        for digest in inputs.source_bundle_resource_sha256s
    )
    return render_configure_run_model(
        create_configure_run_model(
            package=package,
            stage_artifacts={
                "01_manifest/audited_build_input.json": inputs.canonical_payload,
                **{
                    "02_source_documents/"
                    f"frozen_source_authority_{index}.json": value
                    for index, value in enumerate(source_payloads, start=1)
                },
                "03_research/frozen_build_receipt.json": _canonical_json_bytes(
                    {
                        "deck_name": inputs.deck_name,
                        "input_sha256": inputs.input_sha256,
                        "source_resource_sha256s": list(
                            inputs.source_bundle_resource_sha256s
                        ),
                    }
                ),
            },
        )
    )


def _audited_authority(
    *,
    deck_name: str,
    catalog_path: Path,
) -> tuple[AuditedBuildInputSet, FrozenBuildResourceStore, Mapping[str, Any], CanonicalBuildInputs]:
    rows = load_audited_deck_catalog(catalog_path)
    audited = load_packaged_audited_build_inputs()
    resources = load_packaged_audited_build_resource_store(
        audited_inputs=audited
    )
    matching_rows = [row for row in rows if row["deck_name"] == deck_name]
    matching_inputs = [
        inputs for inputs in audited.builds if inputs.deck_name == deck_name
    ]
    if len(matching_rows) != 1 or len(matching_inputs) != 1:
        raise ValueError("audited_build_request_deck_invalid")
    return audited, resources, matching_rows[0], matching_inputs[0]


def _json_document(value: bytes) -> Any:
    try:
        return json.loads(value.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("frozen_audited_resource_json_invalid") from error


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = (
    "render_all_audited_configure_runs",
    "render_audited_configure_run",
    "resolve_audited_package_request",
    "resolve_frozen_audited_package_request",
)
