# Source Builder Workflow

HSConfig builds pre-game HearthRanger VisionAI CustomConfig packages. It does not parse replays, inspect winrate, or tune from post-game logs.

For the normal operator entry point, start at `docs/operator/README.md`.

Identity fields such as `hs_id` keep deck rows and examples unambiguous before games are played. hdt_deck_id is identity-only metadata, not replay evidence, not HDT parsing input, and not a post-run tuning source.

Normal path:

1. Run `hsconfig source-manifest`; it writes deck aliases, card targets, research questions, `source_research_manifest.json`, and diagnostic `source_candidate_plan.json`.
2. Prefer `hsconfig configure --online-source --auto-source --source-url ...` for a fresh public-guide-backed package when URLs are available. It uses `source_candidate_plan.json` to order explicit `--source-url` values first, then registry candidate URLs, with duplicates removed. If no URL is known, use Codex/operator research with the plan's query suggestions to find current public guide URLs and repeat `--source-url` for each useful source.
3. Prefer `hsconfig source-autopilot` when compact public source-search records already exist; it writes ranked sources, evidence rows, and `source_documents.json`.
4. Use Codex research plus `hsconfig draft-source-documents` only when you are manually collecting short evidence rows from current guide, mulligan, card-text, and metadata sources.
5. Run `hsconfig research-deck --source-documents-json ...` to normalize guide sources.
6. Run `hsconfig prepare --guide-sources-json ...` to compile the package.
7. Read `reports/operator_summary.json` first.
8. Run `hsconfig apply` only after `reports/operator_summary.json` shows the package is runtime-load-safe. `READY_TO_APPLY_WITH_WARNINGS` / `ALLOWED_WITH_WARNINGS` is the normal load-safe lane. `--allow-source-informed` is a backward-compatible legacy no-op. It does not create a second apply path. Runtime apply decisions come from `reports/operator_summary.json`.

Recommended fresh deck command:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --online-source --auto-source --apply
```

If public sources are thin, the command still writes a valid package and reports the first missing source action. Do not manually relabel `SOURCE_BACKED_PARTIAL` as `SOURCE_BACKED_STRONG`.

Guide strength is not the write gate. When `technical_status=VALID_PACKAGE` and
`runtime_apply_mode=load_safe_apply`, HSConfig may apply the initial package
even if `semantic_status=VALID_BUT_NOT_GUIDE_STRONG`. Use the warnings to
improve future source depth; do not treat them as load-safety blockers.
For any valid deck code, HSConfig still attempts to generate a load-safe valid
package. `SOURCE_BACKED_STRONG` is an evidence label, not a generation/apply
gate.

Evidence rows should be short and atomic. Long guide prose belongs outside runtime config.

`source-autopilot` is source-strength preflight, not runtime apply authority. `decklist_only`, decklist-only pages, statistical enrichment, policy fallback, snippets, default/runtime examples, and static records without explicit supported effect semantics do not promote `SOURCE_BACKED_STRONG`; current guide-backed or qualifying `evergreen_wild_archetype` card-specific runtime-lowerable claims, or supported official static effect semantics, are still required.

Autonomous source path:

```powershell
hsconfig source-acquire --deck-name "<DeckName>" --deck-code "<DeckCode>" --source-url "<public-guide-url>" --out "outputs/<DeckName>/02_source_acquisition" --json
hsconfig source-autopilot --deck-name "<DeckName>" --deck-code "<DeckCode>" --source-search-results-json "outputs/<DeckName>/02_source_acquisition/source_search_results.json" --out "outputs/<DeckName>/03_source_autopilot" --json
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --source-url "<public-guide-url>" --json
```

`source-acquire` fetches bounded public pages and writes compact source records. Fetch failures, thin pages, decklist-only records, and static metadata without explicit supported effect semantics remain visible diagnostics; they do not block a technically valid package and do not promote `SOURCE_BACKED_STRONG`.

`source_candidate_plan.json` is deterministic pre-acquisition guidance. It lists candidate and explicit URL order, query suggestions, card-level claim targets, and the first missing source action. Queries are for Codex/operator research only; HSConfig core does not scrape search result pages or pass query text to source acquisition. The plan cannot promote, block apply, write runtime config, or replace `reports/operator_summary.json`.

`reports/02_source_acquisition/source_closure_intake_receipt.json` is the bounded intake receipt for candidate source rows and fetched source metadata. It is diagnostic-only: it can explain source readiness, first missing source actions, and which URLs entered configure, but it cannot promote `SOURCE_BACKED_STRONG`, block load-safe generation, write runtime config, or replace `reports/operator_summary.json` as the apply authority.

Every card should reach one visible lane: `guide_backed`, `source_backed_static_semantics`, `archetype_inferred`, `explicit_low_confidence`, `generic_low_confidence`, or `contract_gap`.
Every expected runtime surface must be emitted, explicitly suppressed, or
reported as a gap or source action. Thin or weak source is non-blocking, but it
must stay visible instead of becoming hidden default-only runtime.
`operator_summary.json.source_backed_strong_closure` and `operator_summary.json.no_default_only_runtime_status` are compact diagnostic-only summaries. They expose whether Strong closure is honest and whether default-only runtime stayed visible, but they do not create apply gates and do not replace `reports/operator_summary.json` authority.

For Mulligan evidence, prefer exact, source-backed claims over broad archetype guesses. The source document builder accepts both canonical and convenience fields, but each claim should still preserve the source family, source confidence, selector, condition, and short evidence text so `Mulligan.json` can be rich without becoming a load-safety gate.

```json
{
  "source_url": "https://example.invalid/guide",
  "source_title": "Example Deck Guide",
  "source_family": "mulligan_guide",
  "claims": [
    {
      "kind": "mulligan_keep",
      "card_id": "CARD_001",
      "selector": "CARD_001",
      "condition": {"coin": true},
      "source_confidence": "high",
      "evidence_text_short": "Keep CARD_001 with The Coin as the early pressure anchor."
    }
  ]
}
```

Use separate claims for always-keep, with-Coin, no-Coin, matchup-speed, hand-partner, and throw/discard-away rules when the guide supports them. Unsupported conditions stay visible as `unsupported_mulligan_condition` in `mulligan_plan_report.json`; they do not block `load_safe_apply`.
