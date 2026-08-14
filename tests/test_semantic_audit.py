from hsconfig.semantic_audit import render_semantic_audit_markdown


def test_render_semantic_audit_markdown_lists_deckwide_effects_and_warnings():
    report = {
        "semantic_enrichment_status": "partial",
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "semantic_families": ["hero_power_transform", "hero_power_pressure"],
                "linked_entities": [{"card_id": "EX1_625t", "name": "Mind Spike"}],
            }
        ],
        "deckwide_effects": [
            {
                "source_card_id": "SW_448",
                "source_card_name": "Darkbishop Benedictus",
                "effect": "replace_starting_hero_power",
                "target_card_id": "EX1_625t",
                "target_name": "Mind Spike",
                "reason": "Darkbishop Benedictus enters Shadowform at Start of Game.",
            }
        ],
        "semantic_enrichment_warnings": [
            {"card_id": "SW_448", "warning": "mind_spike_resolved_from_builtin_fallback"}
        ],
    }

    markdown = render_semantic_audit_markdown(report)

    assert "# Card Semantic Audit" in markdown
    assert "Status: `partial`" in markdown
    assert "SW_448 Darkbishop Benedictus" in markdown
    assert "EX1_625t Mind Spike" in markdown
    assert "hero_power_transform" in markdown
    assert "Darkbishop Benedictus enters Shadowform at Start of Game." in markdown
    assert "mind_spike_resolved_from_builtin_fallback" in markdown


def test_render_semantic_audit_markdown_includes_configuration_assurance():
    markdown = render_semantic_audit_markdown(
        {
            "configuration_assurance": {
                "load_safety": "validated",
                "source_authority": "exact",
                "semantic_closure": "closed",
                "in_client_behavior": "not_proven_by_pre_run_contract",
                "optimality_claim_allowed": False,
                "runtime_gate_impact": "none",
            }
        }
    )

    assert (
        "## Configuration Assurance\n\n"
        "- Load safety: `validated`\n"
        "- Source authority: `exact`\n"
        "- Semantic closure: `closed`\n"
        "- In-client behavior: `not_proven_by_pre_run_contract`\n"
        "- Optimality claim allowed: `false`\n"
        "- Runtime gate impact: `none`"
    ) in markdown
