# HSConfig Operator Guide

HSConfig creates pre-game HearthRanger VisionAI `CustomConfig` packages from a deck name, deck code, and source-backed guide evidence.

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner.

Research artifacts are evidence, not operator instructions. Use `docs/research/README.md` when auditing why a source-depth or fixture decision exists; return to this guide for the normal command path.
The normal path is: source-manifest -> draft-source-documents -> research-deck -> prepare -> apply.

## Normal Operator Path

1. Run `hsconfig source-manifest` to get aliases, card targets, and research questions.
2. Write short source evidence rows from current guide, archetype, mulligan, card-text, and metadata sources.
3. Run `hsconfig draft-source-documents` to turn evidence rows into strict `source_documents.json`.
4. Run `hsconfig research-deck --source-documents-json ...` to normalize guide sources.
5. Run `hsconfig prepare --guide-sources-json ...` to compile and validate the package.
6. Open `reports/operator_summary.json` first.
7. Run `hsconfig apply` only when the operator summary allows it.

## Single Gate

Use `reports/operator_summary.json` as the normal operator gate.

- `technical_status=VALID_PACKAGE` means the runtime JSON shape is load-safe.
- `semantic_status=SOURCE_BACKED_STRONG` means source coverage and per-card closure are strong enough for normal apply or handoff.
- `semantic_status=VALID_BUT_NOT_GUIDE_STRONG` means the package is valid but source depth, runtime surfaces, combo detail, conditions, mechanics, or conflicts still need work.
- `apply_policy=ALLOWED` is required for normal apply.
- `next_action=SOURCE_INFORMED_APPLY_READY` plus `apply_policy=ALLOWED_SOURCE_INFORMED` means the only remaining blockers are source-depth gaps for `cards_need_guide_claims` or `cards_need_mulligan_claims`. `source_informed_apply_readiness.status=ready` documents that state.
- `cards_need_runtime_surface`, combo, condition, mechanic, conflict, unsupported-condition, uncovered-card, and generic-low-confidence blockers keep source-informed apply blocked.

Lower-level reports explain the gate. They do not grant independent apply permission.

## Report Ownership

Open `reports/operator_summary.json` first. Lower-level reports explain the gate. They do not grant independent apply permission.

| File | Authority | Answers |
| --- | --- | --- |
| `reports/operator_summary.json` | normal operator gate | what to do next |
| `reports/source_claim_gap_report.json` | repair contract | which card link is missing first |
| `reports/strong_promotion_report.json` | promotion confirmation | whether the package can be called source-backed strong |
| `reports/per_card_config_readiness_report.json` | card lane diagnostics | which lane each card occupies |
| `reports/guide_source_depth_report.json` | source-depth diagnostics | how strong the guide and source coverage is |
| `reports/global_values_authority_matrix.json` | GlobalValues diagnostics | which GlobalValues keys are source-backed or archetype-inferred |

## Expert Paths

Use `hsconfig build`, `hsconfig research-contract`, `--cards-json`, `--claims-json`, `--plan-reports-dir`, and `--allow-placeholder` only for fixtures, diagnostics, or inspected expert inputs.

Use `--allow-source-informed` only when `operator_summary.json` says `SOURCE_INFORMED_APPLY_READY`, `ALLOWED_SOURCE_INFORMED`, and `source_informed_apply_readiness.status=ready`. The normal command is:

```powershell
hsconfig apply --package <package> --runtime-root <runtime-root> --allow-source-informed --json
```

Source-informed apply is still not `SOURCE_BACKED_STRONG`; close the remaining `source_claim_gap_report.json` links before promoting the fixture or calling the package strong.

## Fixture Matrix

`docs/operator/archetype-fixture-matrix.json` is the representative 11-deck HSConfig proof set.

Source-depth closure means every representative deck either proves `SOURCE_BACKED_STRONG` or exposes the first missing source-to-runtime link. Close existing matrix gaps before adding more representative decks.

When a source-informed row cannot be promoted honestly, keep it visible with an explicit stop condition instead of widening the matrix or forcing a weak source claim.

Do not add a new representative deck when an existing row can exercise the same source-depth or runtime-surface family. Close the current Kingslayer and Boarlock `source_informed_valid_fixture` rows before widening the matrix.
