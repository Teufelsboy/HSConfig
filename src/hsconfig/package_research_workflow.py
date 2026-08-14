from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from hsconfig.package_io import prepare_research_output_dir
from hsconfig.preconfig_context import build_preconfig_context
from hsconfig.research_contract import write_research_contract_bundle_to_dir


@dataclass(frozen=True)
class ResearchWorkflowDependencies:
    fetch_latest_cards: Callable[..., Any]
    research_required_guide_sources: Callable[..., dict[str, Any]]


def research_contract_payload(
    args: argparse.Namespace,
    *,
    current_date: date,
    dependencies: ResearchWorkflowDependencies,
) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)

    context = build_preconfig_context(
        args,
        current_date=current_date,
        fetch_latest_cards_fn=dependencies.fetch_latest_cards,
        fetch_latest_collectible_cards_fn=None,
        research_required_guide_sources_fn=(
            dependencies.research_required_guide_sources
        ),
    )
    deck_identity = context["deck_identity"]
    bundle = context["research_bundle"]
    write_research_contract_bundle_to_dir(bundle, out)

    return (
        {
            "status": "passed",
            "research_dir": str(out),
            "deck_slug": deck_identity["deck_slug"],
            "confidence": bundle["archetype_research"]["confidence"],
        },
        0,
    )
