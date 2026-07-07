# Source Builder Workflow

HSConfig builds pre-game HearthRanger VisionAI CustomConfig packages. It does not parse replays, inspect winrate, or tune from post-game logs.

For the normal operator entry point, start at `docs/operator/README.md`.

Identity fields such as `hs_id` keep deck rows and examples unambiguous before games are played. hdt_deck_id is identity-only metadata, not replay evidence, not HDT parsing input, and not a post-run tuning source.

Normal path:

1. Run `hsconfig source-manifest` to get deck aliases, card targets, and research questions.
2. Use Codex research to collect short evidence rows from current guide, mulligan, card-text, and metadata sources.
3. Run `hsconfig draft-source-documents` to convert evidence rows into `source_documents.json`.
4. Run `hsconfig research-deck --source-documents-json ...` to normalize guide sources.
5. Run `hsconfig prepare --guide-sources-json ...` to compile the package.
6. Read `reports/operator_summary.json` first.
7. Run `hsconfig apply` only when the apply gate allows it or the operator intentionally uses `--allow-source-informed`.

Evidence rows should be short and atomic. Long guide prose belongs outside runtime config.

Every card should reach one visible lane: `guide_backed`, `source_backed_static_semantics`, `archetype_inferred`, `explicit_low_confidence`, `generic_low_confidence`, or `contract_gap`.
