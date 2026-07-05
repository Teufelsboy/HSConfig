# HSConfig

HSConfig builds HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

This repository is a direct config authoring tool. The pipeline is deck identity, card metadata, guide research, aggressive gameplan contracts, VisionAI compilers, strict validation, and optional runtime apply.

HSConfig does not parse replays, evaluate winrate, inspect post-game evidence, or tune from runtime logs. Those are HSTuner concerns.

`GlobalValues.json` is built baseline-first. When `--runtime-root` contains `CustomConfig/default/GlobalValues.json` or `CustomConfig/Default/GlobalValues.json`, HSConfig copies and profiles that full runtime baseline before applying deck-specific overlays. If no runtime default is available, it uses a bundled fallback baseline and records that fallback in the package reports.

## Commands

Prepare a complete validated package from deck input. This is the normal path.
`hsconfig prepare` decodes the Hearthstone deck code through HearthSim deckstrings,
writes exact CardIDs, enriches static card semantics, writes the research contract
under `reports/research/`, compiles runtime config, and validates the package.

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

Expert override: build from explicit card rows instead of deckstring decode.

```powershell
hsconfig build --deck-name "Fixture Deck" --deck-code "fixture-code" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\fixture_deck" --cards-json ".\cards.json" --json
```

Expert override: add source-backed guide claims.

```powershell
hsconfig build --deck-name "Fixture Deck" --deck-code "fixture-code" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\fixture_deck" --cards-json ".\cards.json" --claims-json ".\claims.json" --json
```

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

`--cards-json` accepts either a list of card objects or an object with a `cards` list. `--claims-json` accepts either a list of source-backed guide claims or an object with a `claims` list. `--allow-placeholder` is only for fixture/test previews when a real deckstring is intentionally unavailable.
