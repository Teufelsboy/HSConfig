from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date
import json
import os
from pathlib import Path
from typing import Iterator

from hsconfig.build_context import resolve_build_context
from hsconfig.build_input_catalog import (
    load_packaged_audited_build_inputs,
    load_packaged_audited_build_resource_store,
)
from hsconfig.evidence_contract import load_policy_profile
from hsconfig.globalvalues_baseline import load_globalvalues_baseline
from hsconfig.globalvalues_decisions import (
    normalize_globalvalues_decision_baseline,
)
from hsconfig.package_request import (
    PackageInvocation,
    PackageResolutionSnapshot,
    ResolvedPackageRequest,
)
from hsconfig.pre_run_metrics import (
    build_source_acquisition_closure_report,
)
from hsconfig.preconfig_context import build_preconfig_context
from tests.helpers.package_byte_contract import (
    _load_audited_catalog,
    _materialize_source_documents,
    _offline_build_inputs,
    _offline_network_and_card_data,
)


def audited_request(
    tmp_path: Path,
    deck_name: str,
    *,
    fixture_paths: bool = False,
) -> ResolvedPackageRequest:
    deck = next(
        row
        for row in _load_audited_catalog()
        if row["deck_name"] == deck_name
    )
    deck_cards, offline_cards, card_database = _offline_build_inputs()
    del deck_cards
    source_documents = _materialize_source_documents(
        deck_name,
        root=tmp_path,
    )
    current_date = date(2026, 7, 29)
    args = argparse.Namespace(
        command="prepare",
        deck_name=deck_name,
        deck_code=str(deck["deck_code"]),
        out=(
            f"packages/{deck_name}"
            if fixture_paths
            else str(tmp_path / "unused")
        ),
        runtime_root=(
            "runtime-write-fence"
            if fixture_paths
            else str(tmp_path / "runtime-write-fence")
        ),
        guide_sources_json=None,
        source_documents_json=str(source_documents),
        auto_research_fallback=False,
        json=True,
        cards_json=None,
        claims_json=None,
        plan_reports_dir=None,
        allow_placeholder=False,
        current_date=current_date.isoformat(),
        collectible_cards_json=None,
        full_cards_json=None,
        skip_semantic_fetch=False,
        source_evidence_json=None,
    )
    with _working_directory(tmp_path), _offline_network_and_card_data(
        offline_cards,
        card_database,
    ):
        preconfig = build_preconfig_context(
            args,
            current_date=current_date,
            source_authority_consumer="prepare",
            fetch_latest_cards_fn=lambda timeout=10.0: [
                dict(card) for card in offline_cards
            ],
            fetch_latest_collectible_cards_fn=None,
        )
        policy = load_policy_profile()
        baseline_receipt = load_globalvalues_baseline(args.runtime_root)
        baseline = normalize_globalvalues_decision_baseline(
            baseline_receipt["baseline"]
        )
        acquisition = build_source_acquisition_closure_report(
            deck_fingerprint=str(
                preconfig["deck_identity"]["deck_fingerprint"]
            ),
            acquisition_closure=None,
        )["acquisition_closure"]
    policy_mapping = {
        "policy_id": policy.policy_id,
        "version": policy.version,
        "effective_date": policy.effective_date,
        "content_sha256": policy.content_sha256,
        "rules": json.loads(policy.rules_canonical_json),
    }
    preconfig = {
        **preconfig,
        "policy_profile": policy_mapping,
        "globalvalues_baseline": baseline,
        "globalvalues_baseline_receipt": baseline_receipt,
    }
    audited_inputs = load_packaged_audited_build_inputs()
    inputs = next(
        row
        for row in audited_inputs.builds
        if row.deck_name == deck_name
    )
    resources = load_packaged_audited_build_resource_store(
        audited_inputs=audited_inputs
    )
    strict_context = resolve_build_context(inputs, resources=resources)
    return ResolvedPackageRequest.from_values(
        snapshot=PackageResolutionSnapshot.from_strict(
            strict_context,
            preconfig,
        ),
        invocation=PackageInvocation(
            deck_code=str(deck["deck_code"]),
            runtime_root=args.runtime_root,
            cards_json=None,
            claims_json=None,
            guide_sources_json=None,
            plan_reports_dir=None,
            target_config_mode="preview",
            include_disposition_diagnostics=False,
        ),
        plan_overrides={},
        acquisition_closure_input=acquisition,
        mulligan_gap_input=[],
    )


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(previous)


__all__ = ("audited_request",)
