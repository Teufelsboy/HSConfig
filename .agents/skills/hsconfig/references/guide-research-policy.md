# Guide Research Policy

Use current deck guides and data sources as strategic priors when live research is part of the request.

Every claim must record source, URL or source name, affected cards, claim type, and confidence. Runtime config intent artifacts cross-reference claims through `source_claim_ids`.

Confidence lanes:

- `guide_backed`: current deck guide or explicit supplied claim supports the card expectation.
- `source_backed_static_semantics`: card text or HearthstoneJSON semantics prove the behavior without a deck guide.
- `archetype_inferred`: mechanics imply a reasonable deck-plan role, but no direct guide claim exists.
- `generic_low_confidence`: HSConfig can only cover the card generically.

The research contract lives under `reports/research/` and includes archetype, claims, card roles, mulligan anchors, usage expectations, known bad patterns, and GlobalValues intent.

Do not infer replay performance, winrate, or postgame tuning from HSConfig outputs.
