from __future__ import annotations

from typing import Any


def render_semantic_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Card Semantic Audit",
        "",
        f"Status: `{report.get('semantic_enrichment_status', 'unknown')}`",
        "",
        "## Deckwide Effects",
        "",
    ]
    deckwide_effects = report.get("deckwide_effects", [])
    if deckwide_effects:
        for effect in deckwide_effects:
            lines.append(
                "- "
                f"{effect.get('source_card_name', effect.get('source_card_id', 'Unknown'))}: "
                f"`{effect.get('effect', 'unknown')}` -> "
                f"{effect.get('target_name', effect.get('target_card_id', 'Unknown'))}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Cards", ""])
    for card in report.get("cards", []):
        families = ", ".join(card.get("semantic_families", [])) or "none"
        linked = ", ".join(
            f"{entity.get('name', entity.get('card_id'))} ({entity.get('card_id')})"
            for entity in card.get("linked_entities", [])
        )
        lines.append(f"- {card.get('name', card.get('card_id'))} (`{card.get('card_id')}`): {families}")
        if linked:
            lines.append(f"  - Linked: {linked}")

    lines.extend(["", "## Warnings", ""])
    warnings = report.get("semantic_enrichment_warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning.get('card_id')}`: {warning.get('warning')}")
    else:
        lines.append("- None")

    lines.append("")
    return "\n".join(lines)
