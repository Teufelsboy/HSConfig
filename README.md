# HSConfig

HSConfig builds HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

This repository is a direct config authoring tool. Codex performs live guide research, writes structured guide-source claims, and HSConfig compiles those claims deterministically into validated VisionAI runtime files.

HSConfig does not parse replays, evaluate winrate, inspect post-game evidence, or tune from runtime logs. Those are HSTuner concerns.

`GlobalValues.json` is built baseline-first. When `--runtime-root` contains `CustomConfig/default/GlobalValues.json` or `CustomConfig/Default/GlobalValues.json`, HSConfig copies and profiles that full runtime baseline before applying deck-specific overlays. If no runtime default is available, it uses a bundled fallback baseline and records that fallback in the package reports.

## Commands

Normalize researched guide inputs first. This is the normal pre-build path.
It writes `deck_fingerprint.json`, `candidate_archetypes.json`,
`guide_sources.json`, `guide_builder_receipt.json`, and identity reports without
writing `CustomConfig` runtime files.

```powershell
hsconfig research-deck --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --out ".\outputs\shadowpriest\research" --json
```

Prepare a complete validated package from normalized guide input.
`hsconfig prepare` decodes the Hearthstone deck code through HearthSim deckstrings,
writes exact CardIDs, enriches static card semantics, consumes
`--guide-sources-json` or `--source-documents-json`, writes guide-depth reports
and the research contract under `reports/research/`, compiles runtime config,
validates the package, and writes `reports/operator_summary.json`.

```powershell
hsconfig prepare --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\shadowpriest" --guide-sources-json ".\outputs\shadowpriest\research\guide_sources.json" --json
```

Diagnostic research-only output:

```powershell
hsconfig research-contract --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --out ".\outputs\shadowpriest\reports\research" --json
```

Lower-level package build remains available when a caller already controls the
research inputs:

```powershell
hsconfig build --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\shadowpriest" --json
```

Rebuild from inspected plan reports:

```powershell
hsconfig build --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\shadowpriest" --plan-reports-dir ".\outputs\shadowpriest\reports" --json
```

Expert override: build from explicit card rows instead of deckstring decode.

```powershell
hsconfig build --deck-name "Fixture Deck" --deck-code "fixture-code" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\fixture_deck" --cards-json ".\cards.json" --json
```

Expert override: add source-backed guide claims.

```powershell
hsconfig build --deck-name "Fixture Deck" --deck-code "fixture-code" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\fixture_deck" --cards-json ".\cards.json" --claims-json ".\claims.json" --json
```

Preferred guide-depth input: pass structured guide sources created by Codex after
online guide/archetype research.

```powershell
hsconfig prepare --deck-name "Fixture Deck" --deck-code "fixture-code" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\fixture_deck" --guide-sources-json ".\guide_sources.json" --json
```

Convenience input: pass researched source documents directly and let `prepare`
write generated guide-builder artifacts into `reports/`.

```powershell
hsconfig prepare --deck-name "Fixture Deck" --deck-code "fixture-code" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\fixture_deck" --source-documents-json ".\source_documents.json" --json
```

Key reports:

- `reports/guide_claim_bundle.json`
- `reports/operator_summary.json`
- `reports/guide_builder_receipt.json`
- `reports/candidate_archetypes.json`
- `reports/deck_fingerprint.json`
- `reports/identity_graph_report.json`
- `reports/claim_coverage_report.json`
- `reports/mulligan_plan_report.json`
- `reports/card_behavior_plan_report.json`
- `reports/combo_plan_report.json`
- `reports/global_values_authority_matrix.json`
- `reports/per_card_config_readiness_report.json`
- `reports/guide_source_depth_report.json`

`operator_summary.json` is the operator-facing readiness file. It separates
technical package validity from semantic source strength through
`technical_status`, `semantic_status`, `next_action`, and `apply_policy`.
Status meanings:

- VALID_PACKAGE means the JSON package loads structurally.
- SOURCE_BACKED_STRONG means HSConfig has enough current guide-backed coverage for strong initial config.
- STATIC_SEMANTICS_USABLE means the package is safe but not guide-depth.
- VALID_BUT_NOT_GUIDE_STRONG means Codex should improve source documents before calling the package optimized.

The readiness and depth reports are quality checks for guide-backed config
generation, not postgame proof. A valid package may still contain
`archetype_inferred` or `generic_low_confidence` cards, but those lanes tell
Codex to improve the structured guide source before treating the package as
deeply configured.

Validate a package:

```powershell
hsconfig validate --package ".\outputs\fixture_deck" --json
```

Apply a validated package to a HearthRanger runtime only when requested:

```powershell
hsconfig apply --package ".\outputs\shadowpriest" --runtime-root "C:\Users\darbo\Desktop\HS" --json
```

`apply` copies the validated deck folder into `CustomConfig/<deck_slug>` and updates
`CustomConfig/deck_config.ini` so HearthRanger maps the visible deck name to that folder.

`--cards-json` accepts either a list of card objects or an object with a `cards` list. `--claims-json` accepts either a legacy list of source-backed guide claims or an object with a `claims` list. `--source-documents-json` accepts a list of researched source documents or an object with a `source_documents` list. `--guide-sources-json` accepts normalized guide sources from `research-deck` or an object with a `sources` list. `--plan-reports-dir` lets `build` consume inspected plan reports such as `mulligan_plan_report.json` and `card_behavior_plan_report.json`. `--allow-placeholder` is only for fixture/test previews when a real deckstring is intentionally unavailable.

See `docs/operator/guide-research-policy.md` for the structured guide-source format.
