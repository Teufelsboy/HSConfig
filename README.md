# HSConfig

HSConfig builds HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

This repository is a direct config authoring tool. The pipeline is deck identity, card metadata, guide research, aggressive gameplan contracts, VisionAI compilers, strict validation, and optional runtime apply.

HSConfig does not parse replays, evaluate winrate, inspect post-game evidence, or tune from runtime logs. Those are HSTuner concerns.

`GlobalValues.json` is built baseline-first. When `--runtime-root` contains `CustomConfig/default/GlobalValues.json` or `CustomConfig/Default/GlobalValues.json`, HSConfig copies and profiles that full runtime baseline before applying deck-specific overlays. If no runtime default is available, it uses a bundled fallback baseline and records that fallback in the package reports.

## Commands

Build a deterministic preview package:

```powershell
hsconfig build --deck-name "Fixture Deck" --deck-code "fixture-code" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\fixture_deck" --json
```

Build from explicit card rows:

```powershell
hsconfig build --deck-name "Fixture Deck" --deck-code "fixture-code" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\fixture_deck" --cards-json ".\cards.json" --json
```

Build from explicit card rows plus guide-backed claims:

```powershell
hsconfig build --deck-name "Fixture Deck" --deck-code "fixture-code" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\fixture_deck" --cards-json ".\cards.json" --claims-json ".\claims.json" --json
```

Validate a package:

```powershell
hsconfig validate --package ".\outputs\fixture_deck" --json
```

Apply a validated package to a HearthRanger runtime only when requested:

```powershell
hsconfig apply --package ".\outputs\fixture_deck" --runtime-root "C:\Users\darbo\Desktop\HS" --json
```

`--cards-json` accepts either a list of card objects or an object with a `cards` list. `--claims-json` accepts either a list of source-backed guide claims or an object with a `claims` list. Without explicit cards, `build` creates a tiny deterministic placeholder deck identity from the deck name and deck code so the package can still be previewed and validated.
