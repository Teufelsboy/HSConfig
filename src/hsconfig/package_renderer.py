"""Strict deterministic rendering for the immutable package model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hsconfig.package_model import (
    PackageArtifact,
    PackageModel,
    RenderedPackage,
    content_root_sha256,
    package_model_document,
)


_MANIFEST_PATH = "reports/package_manifest.json"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True
    ).encode("utf-8") + b"\n"


def render_package_model(model: PackageModel) -> RenderedPackage:
    runtime_payloads = _runtime_payloads(model)
    artifacts = [
        PackageArtifact.from_content(relative_path=path, content=_json_bytes(payload))
        for path, payload in runtime_payloads.items()
    ]
    artifacts.extend(
        (
            PackageArtifact.from_content(
                relative_path="reports/mulligan_plan_report.json",
                content=_json_bytes(model.mulligan_plan.to_report()),
            ),
            PackageArtifact.from_content(
                relative_path="reports/package_model.json",
                content=_json_bytes(package_model_document(model)),
            ),
        )
    )
    content_root = content_root_sha256(tuple(artifacts))
    artifacts.append(
        PackageArtifact.from_content(
            relative_path=_MANIFEST_PATH,
            content=_json_bytes(
                {
                    "schema_version": 1,
                    "content_root_sha256": content_root,
                    "artifacts": [
                        {
                            "relative_path": artifact.relative_path,
                            "size": artifact.size,
                            "sha256": artifact.sha256,
                        }
                        for artifact in sorted(
                            artifacts, key=lambda artifact: artifact.relative_path
                        )
                    ],
                }
            ),
        )
    )
    rendered = RenderedPackage(
        model=model,
        artifacts=tuple(sorted(artifacts, key=lambda artifact: artifact.relative_path)),
        content_root_sha256=content_root,
    )
    _verify_rendered_package(rendered)
    return rendered


def _runtime_payloads(model: PackageModel) -> dict[str, Any]:
    payloads: dict[str, Any] = {}
    cards_by_path = {
        path: json.loads(row.official_semantics_canonical_json)
        for row in model.disposition_ledger.cards
        for path in row.runtime_paths
    }
    for surface in model.runtime_surface_plan.surfaces:
        if surface.family == "GlobalValues":
            payloads[surface.relative_path] = {
                row.key: json.loads(row.emitted_canonical_json)
                for row in model.globalvalues_ledger.decisions
            }
        elif surface.family == "Mulligan":
            payloads[surface.relative_path] = {
                "GameCardId": "Mulligan",
                "ConfigComment": f"{model.deck_name} generated mulligan rules",
                "Mulligan": {
                    "values": [
                        {
                            "comment": f"{model.deck_name}: {rule.card_id}_mulligan_{index}",
                            "mulligan": json.loads(rule.selector_canonical_json),
                            "condition": json.loads(rule.condition_canonical_json),
                            "value": rule.action,
                        }
                        for index, rule in enumerate(model.mulligan_plan.rules, start=1)
                    ]
                },
            }
        elif surface.family == "CardID":
            try:
                payloads[surface.relative_path] = cards_by_path[surface.relative_path]
            except KeyError as error:
                raise ValueError("runtime_surface_cardid_payload_missing") from error
        elif surface.family == "Combo":
            payloads[surface.relative_path] = {
                "GameCardId": "Combo",
                "ConfigComment": f"{model.deck_name} generated combos",
                "ComboList": {"values": []},
            }
    if tuple(sorted(payloads)) != model.runtime_surface_plan.expected_files:
        raise ValueError("runtime_surface_render_parity_mismatch")
    return payloads


def write_rendered_package(rendered: RenderedPackage, destination: Path) -> None:
    if render_package_model(rendered.model) != rendered:
        raise ValueError("rendered_package_invalid")
    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise ValueError("destination_must_be_empty")
    destination.mkdir(parents=True, exist_ok=True)
    for artifact in rendered.artifacts:
        target = destination / artifact.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.content)
        if target.stat().st_size != artifact.size or _sha256(target.read_bytes()) != artifact.sha256:
            raise ValueError("written_artifact_verification_failed")
    view_artifacts = tuple(
        artifact
        for artifact in rendered.artifacts
        if artifact.relative_path != _MANIFEST_PATH
    )
    if content_root_sha256(view_artifacts) != rendered.content_root_sha256:
        raise ValueError("written_content_root_verification_failed")


def _verify_rendered_package(rendered: RenderedPackage) -> None:
    paths = tuple(artifact.relative_path for artifact in rendered.artifacts)
    if tuple(sorted(paths)) != paths or len(set(paths)) != len(paths):
        raise ValueError("rendered_package_artifacts_not_unique_sorted")
    for artifact in rendered.artifacts:
        if artifact.size != len(artifact.content) or artifact.sha256 != _sha256(artifact.content):
            raise ValueError("rendered_package_artifact_digest_mismatch")
    manifest = next(
        artifact for artifact in rendered.artifacts if artifact.relative_path == _MANIFEST_PATH
    )
    manifest_payload = json.loads(manifest.content)
    if manifest_payload.get("content_root_sha256") != rendered.content_root_sha256:
        raise ValueError("rendered_package_manifest_root_mismatch")
    content_artifacts = tuple(
        artifact for artifact in rendered.artifacts if artifact.relative_path != _MANIFEST_PATH
    )
    if content_root_sha256(content_artifacts) != rendered.content_root_sha256:
        raise ValueError("rendered_package_content_root_mismatch")


def _sha256(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()
