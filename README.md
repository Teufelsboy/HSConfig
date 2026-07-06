# HSConfig

HSConfig builds HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

This repository is a direct config authoring tool. Codex performs live guide research, writes structured guide-source claims, and HSConfig compiles those claims deterministically into validated VisionAI runtime files.

HSConfig does not parse replays, evaluate winrate, inspect post-game evidence, or tune from runtime logs. Those are HSTuner concerns.

`GlobalValues.json` is built baseline-first. When `--runtime-root` contains `CustomConfig/default/GlobalValues.json` or `CustomConfig/Default/GlobalValues.json`, HSConfig copies and profiles that full runtime baseline before applying deck-specific overlays. If no runtime default is available, it uses a bundled fallback baseline and records that fallback in the package reports.

## Commands

Prepare a complete validated package from deck input. This is the normal path.
`hsconfig prepare` decodes the Hearthstone deck code through HearthSim deckstrings,
writes exact CardIDs, enriches static card semantics, consumes optional
`--guide-sources-json`, writes guide-depth reports and the research contract under
`reports/research/`, compiles runtime config, and validates the package.

```powershell
hsconfig prepare --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\shadowpriest" --json
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

Key reports:

- `reports/guide_claim_bundle.json`
- `reports/claim_coverage_report.json`
- `reports/mulligan_plan_report.json`
- `reports/card_behavior_plan_report.json`
- `reports/combo_plan_report.json`
- `reports/global_values_authority_matrix.json`

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

`--cards-json` accepts either a list of card objects or an object with a `cards` list. `--claims-json` accepts either a legacy list of source-backed guide claims or an object with a `claims` list. `--guide-sources-json` accepts a list of source documents or an object with a `sources` list. `--plan-reports-dir` lets `build` consume inspected plan reports such as `mulligan_plan_report.json` and `card_behavior_plan_report.json`. `--allow-placeholder` is only for fixture/test previews when a real deckstring is intentionally unavailable.

See `docs/operator/guide-research-policy.md` for the structured guide-source format.
