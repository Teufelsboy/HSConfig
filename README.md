# HSConfig

HSConfig builds guide-aligned HearthRanger VisionAI `CustomConfig` packages from a Hearthstone deck name and deck code.

HSConfig is a direct pre-game config authoring tool. Codex researches current guide and card sources, `research-deck` normalizes them, and `prepare` compiles a validated initial package.

HSConfig does not parse replays, evaluate winrate, inspect post-game evidence, or tune from runtime logs. Those are HSTuner concerns. `Presume.json` and `Concede.json` are not emitted in the normal path.

## Normal Operator Path

Normal command path: write `source_documents.json` -> `hsconfig research-deck --source-documents-json ...` -> `hsconfig prepare --guide-sources-json ...` -> inspect `reports/operator_summary.json` -> `hsconfig apply ...` only when requested.

Maintainer sync: after changing `.agents/skills/hsconfig`, run `python scripts/sync_installed_skill.py --check`; if drift is expected, run `python scripts/sync_installed_skill.py`.

```powershell
hsconfig research-deck --source-documents-json ".\source_documents.json" --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --out ".\outputs\shadowpriest\research" --json
```

```powershell
hsconfig prepare --guide-sources-json ".\outputs\shadowpriest\research\guide_sources.json" --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\shadowpriest" --json
```

```powershell
hsconfig validate --package ".\outputs\shadowpriest" --json
hsconfig apply --package ".\outputs\shadowpriest" --runtime-root "C:\Users\darbo\Desktop\HS" --json
```

Run `apply` only when the user or task requests runtime writes and `operator_summary.json` allows it through `next_action` and `apply_policy`.

## Status Model

`operator_summary.json` is the operator-facing readiness file. It separates technical package validity from source depth through `technical_status`, `semantic_status`, `next_action`, `apply_policy`, `guide_strength_summary`, and `semantic_blockers`.
`reports/operator_summary.json` is the single operator gate. Use the detail reports to explain the gate, but do not make apply or handoff decisions from a lower-level report alone.

| Status | Meaning | Normal action |
| --- | --- | --- |
| `VALID_PACKAGE` | Runtime JSON is structurally valid and load-safe. | Handoff or continue source work according to `operator_summary.json`. |
| `SOURCE_BACKED_STRONG` | Current guide-backed per-card coverage supports a strong initial config. | Preferred apply or handoff state. |
| `STATIC_SEMANTICS_USABLE` | Static card semantics produced a valid package without enough live guide depth. | Safe baseline only; improve sources before calling it guide-strong. |
| `VALID_BUT_NOT_GUIDE_STRONG` | Package is valid, but guide claims, runtime surfaces, combo details, or conflicts still need work. | Read `guide_strength_summary` and `semantic_blockers`. |

## Key Reports

- `reports/operator_summary.json`
- `reports/guide_builder_receipt.json`
- `reports/candidate_archetypes.json`
- `reports/deck_fingerprint.json`
- `reports/identity_graph_report.json`
- `reports/guide_claim_bundle.json`
- `reports/claim_coverage_report.json`
- `reports/mulligan_plan_report.json`
- `reports/card_behavior_plan_report.json`
- `reports/combo_plan_report.json`
- `reports/global_values_authority_matrix.json`
- `reports/per_card_config_readiness_report.json`
- `reports/guide_source_depth_report.json`
- `reports/research/*`

## Expert Paths

Use lower-level `hsconfig build` only when the caller already controls explicit `--cards-json`, legacy `--claims-json`, structured `--guide-sources-json`, or inspected `--plan-reports-dir` inputs. Use `--allow-placeholder` only for deterministic fixture or preview tests.

`GlobalValues.json` is built baseline-first. When `--runtime-root` contains `CustomConfig/default/GlobalValues.json` or `CustomConfig/Default/GlobalValues.json`, HSConfig copies and profiles that full runtime baseline before applying deck-specific overlays. If no runtime default is available, it uses a bundled fallback baseline and records that fallback in the package reports.

See `docs/operator/guide-research-policy.md` for the structured guide-source format and source-depth expectations.
