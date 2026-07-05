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
            source = _id_name(
                effect.get("source_card_id"),
                effect.get("source_card_name"),
            )
            target = _id_name(effect.get("target_card_id"), effect.get("target_name"))
            lines.append(
                "- "
                f"{source}: "
                f"`{effect.get('effect', 'unknown')}` -> "
                f"{target}"
            )
            if effect.get("reason"):
                lines.append(f"  - Reason: {effect['reason']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Cards", ""])
    for card in report.get("cards", []):
        families = ", ".join(card.get("semantic_families", [])) or "none"
        linked = ", ".join(
            _id_name(entity.get("card_id"), entity.get("name"))
            for entity in card.get("linked_entities", [])
        )
        lines.append(f"- {_id_name(card.get('card_id'), card.get('name'))}: {families}")
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


def _id_name(card_id: Any, name: Any) -> str:
    card_id_text = str(card_id or "UNKNOWN")
    name_text = str(name or card_id_text)
    if name_text == card_id_text:
        return card_id_text
    return f"{card_id_text} {name_text}"
