# HSConfig Operator Guide

HSConfig creates pre-game HearthRanger VisionAI `CustomConfig` packages from a deck name, deck code, and source-backed guide evidence.

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner.

Research artifacts are evidence, not operator instructions. Use `docs/research/README.md` when auditing why a source-depth or fixture decision exists; return to this guide for the normal command path.

Repository history is indexed in [`docs/history/README.md`](../history/README.md).
Ignored local output maintenance follows the
[`output retention policy`](output-retention-policy.md). Maintenance and
inventory are never apply authority.

## Quick Start

- Run `hsconfig configure` for normal operation.
- Before source refresh, package generation, or runtime-facing apply review, run `git fetch --all --prune --tags`, `python scripts/check_hsconfig_currentness.py --cwd . --json`, and `git status --short --branch`. Runtime-facing work must start from a clean worktree and not be behind `origin/main`; feature branches may be ahead.
- Use `--online-source --auto-source --source-url ...` for public guide URLs, or `--auto-source --source-search-results-json ...` for captured source records.
- After `configure`, resolve `<out>/current.json` and read `<current-revision>/configure_summary.json.acceptance_summary` first, then `<current-revision>/configure_summary.json.handoff_contract`, then `<current-revision>/configure_summary.json.source_closure_receipt` when source depth is the question. Use `<current-package>/reports/operator_summary.json` as the apply authority. `source_closure_receipt` is a compact diagnostic-only source-closure receipt. It does not replace `reports/operator_summary.json`, cannot promote, block, apply, or write runtime files, and keeps source_status_apply_blocking=false.
- `technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` means runtime apply is allowed. This is the human-facing verdict only when read from `reports/operator_summary.json`; the apply command recomputes every technical authority boundary before writing.
- A captured or diagnostic-source package can instead be
  `technical_status=VALID_PACKAGE`, `runtime_load_safe=true`,
  `fixture_classification=load_safe_fixture`, and
  `runtime_apply_reason=diagnostic_source_not_apply_eligible` while
  `runtime_apply_mode=blocked` and `runtime_apply_allowed=false`. This package
  is valid and load-safe for inspection, but apply-ineligible until rebuilt
  from live-verified source.
- Warnings are follow-up work, not a second apply path. HSTuner owns post-run evaluation and tuning.

### Canonical local release gate

Release preparation uses one local orchestration entry point:

```powershell
python scripts/check_release_gate.py --repo . --outputs outputs --tree-mode working-pre-cutover --json
```

The command must start from a clean committed OID. It runs all behavioral,
coverage, contract, dependency, distribution, determinism, output, hygiene,
version, publishability, and near-100 scorecard checks in a fixed order. It
prints only short progress lines to stderr and exactly one JSON document to
stdout. The provisional `working-pre-cutover` mode permits only the enumerated
historical plan, research, and history directories during the publishability
scan; it never marks `final_release_ready=true`. Candidate mode requires a
detached candidate tree and an explicitly verified outputs root. Final mode is
the default and permits no historical exception.

This command is the local Clean-OID producer/verifier, not the current legacy CI
producer. The legacy `full-test-suite` workflow does not invoke it and does not
depend on the ignored local `outputs/` tree; that workflow still installs the
development package, runs Ruff, runs the full pytest suite, and audits
dependencies. Task 8 owns the later locked-CI consolidation. The command's
stdlib-only parent selects the current Python-minor lock. Only Python 3.11 and
3.12 are canonical because those are the committed release locks; Python 3.13
or newer produces exactly one failure JSON document with exit code 2. The
parent upgrades the fresh
environment from the exact locked
pip wheel by URL and SHA-256, installs the exact 43-package graph, and builds the
local package from `git archive HEAD` in external disposable storage. The child
starts only after the manifest binds the interpreter, repository, commit, tree,
lock, selected wheel inventories, and installed RECORD payloads. No ambient
environment, plugin, cached bytecode, or pre-existing virtual environment is an
authority input.

The release gate is the only canonical producer/verifier. It requires
`outputs/` to contain exactly the twelve catalog deck directories, binds the
complete output tree by entry type, name, size, and digest, and derives semantic
dispositions from the current package disposition ledgers and source-contract
audits. Open P0/P1 counts are derived from the completed checks; operators do not
prepare authority JSON by hand. Working-pre-cutover omits GitHub checks, keeps
GitHub polish pending, and can never set `final_release_ready=true`. Candidate
mode requires detached HEAD and the same exact twelve-directory output inventory.

Final mode performs one fresh live GitHub API transaction. Repository settings,
the concrete active ruleset, version tag, release, and empty asset inventory must all
bind to the current repository, OID, tree, version, observation time, and
transaction identity. Scorecard evidence and receipts are assembled only in memory and
sent to the Near-100 subprocess as one closed JSON stdin envelope. Embedded receipt
schema v2 binds repository identity, commit OID, tree OID, tree state, dirty-tree
fingerprint, and generation mode; final GitHub receipts additionally bind the validated
transaction identity and observation time. The gate creates no evidence files and owns
no named evidence workspace. The legacy schema-v1 `--evidence <file>` scorecard mode is
diagnostic compatibility only and cannot replace canonical gate-produced stdin evidence.
The canonical outputs root never contains release-evidence sidecars.

All gate subprocesses run with a controlled Python/pip/Git environment and bounded
capture. The in-memory envelope rejects duplicate JSON keys, schema drift, receipt
swaps, and repository/tree/mode binding drift; inspected files and archives reject
links, reparse points, hardlinks, unsafe members, and repository/output changes during
the run. No evidence-file cleanup phase exists because the gate never writes evidence.

## Preferred Normal Path

Preferred normal path: `hsconfig configure`.

## Normal Operator Path

1. Run `hsconfig configure`.
2. Resolve `outputs/<DeckName>/current.json` to its `revisions/sha256-<digest>` directory. Read `<current-revision>/configure_summary.json.acceptance_summary`, then `<current-revision>/configure_summary.json.handoff_contract` as the pre-run config contract receipt: compact diagnostic-only handoff proof for use_config_now, single authority, no-default-only status, forbidden-surface status, source-to-runtime trace status, Darkbishop boundary, mechanic discipline, and the next report; it does not replace `reports/operator_summary.json`, cannot apply runtime files, cannot turn source gaps into blockers, and operator_summary.json remains the only normal apply authority. Then read `<current-revision>/configure_summary.json.source_closure_receipt` when source depth is the question; it is a compact diagnostic-only source-closure receipt that does not replace `reports/operator_summary.json`, cannot promote, block, apply, or write runtime files, and keeps source_status_apply_blocking=false.
3. Use `<current-revision>/04_package/reports/operator_summary.json` as the apply authority.
4. Apply only through `hsconfig apply` or `hsconfig configure --apply`.

reports/operator_summary.json remains the only normal apply authority.
Other reports are diagnostic. They explain source quality, mechanic coverage,
ownership, and missing links; they do not grant apply permission.

Normal HSConfig output is limited to `GlobalValues.json`, `Mulligan.json`,
per-card `<CARDID>.json`, and `Combo.json` when exact ordered combo evidence and a matching live-verified strategic receipt exist.
`Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are known
VisionAI surfaces, but they are outside the normal output path.

### Optional Contract Preflight

Use `hsconfig contract-preflight --json` for a read-only repo and skill contract
check before source refresh, package generation, or runtime-facing apply review.
It checks currentness, installed-skill sync, skill reference routing,
source-status non-blocking policy, source-candidate plan visibility,
no-default-only visibility, supported runtime surfaces, negative-scope
boundaries, and the research-context lock around `docs/research/current-truth.md`.
The `source_candidate_plan.json` check is diagnostic-only and does not replace `reports/operator_summary.json`.
The historical research outline files remain
diagnostic-only evidence and do not replace `reports/operator_summary.json`.
When a package already exists, use
`hsconfig contract-preflight --package <04_package> --json` for a single
read-only readiness view. It combines the repo/skill preflight with package
runtime validation and compact config-quality signals. If
`package_contract.status=attention`, inspect `reports/operator_summary.json`
first and then run `hsconfig contract-doctor --package <04_package> --json` for
details. Package-mode preflight is diagnostic-only; it does not write files,
does not replace `reports/operator_summary.json`, and does not block a
technically load-safe package.
Package mode also mirrors compact generated `surface_intent` diagnostics, including status, surface count, fallback rows, legacy-policy surfaces, and first attention, without changing apply authority.
Use `--skill-install-root <path>` only when testing or checking a non-default
Codex skill root. This preflight is diagnostic-only and does not replace
`reports/operator_summary.json`.

Use `hsconfig configure` for normal operation:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --json
```

This command runs the lower-level pre-run chain, writes a validated package, atomically updates `outputs/<DeckName>/current.json`, and leaves the final decision in the resolved `revisions/sha256-<digest>/04_package/reports/operator_summary.json`.

When public guide URLs are available for a fresh config, use the online source path:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --source-url "<public-guide-url>" --json
```

This writes `02_source_acquisition`, `03_source_autopilot`, and the normal `04_package`. Strategic Strong claims require exact deck-matching guide claims acquired as `live_http` with `live_verified` provenance and bound to matching strategic receipts. Static semantics may support only deterministic identity, role, and mechanical effect claim families. If sources are thin, unavailable, stale, captured, fixture-backed, manual, legacy, only decklist evidence, or static records without supported effect semantics, HSConfig still builds a technically valid diagnostic package and reports the first missing source link. A package that consumed captured, fixture, manual, or legacy provenance remains available for build, validation, and preflight, but runtime apply is blocked with `diagnostic_source_not_apply_eligible`.

When `--online-source` is used, HSConfig also checks its source candidate
registry for the deck name. These candidate URLs are acquisition seeds only.
They reduce manual source entry, but they do not promote a package to
`SOURCE_BACKED_STRONG` unless fetched full-text evidence passes source evidence
policy, claim-kind normalization, surface gates, and closure profile checks.

When current guide/search records are already captured, use the source-autopilot bridge:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --auto-source --source-search-results-json "source_search_results.json" --json
```

This writes `02_source_autopilot/source_autopilot_report.json`, `02_source_autopilot/source_evidence_rows.json`, and `02_source_autopilot/source_documents.json`, then feeds the generated source documents into the existing `research-deck` and `prepare` stages. `source-autopilot` is source-strength preflight, not runtime apply authority. Captured search records, `decklist_only`, snippets, `policy_fallback`, `default_runtime`, and `evergreen_wild_archetype` context cannot mint strategic receipts; static records without explicit supported effect semantics do not promote `SOURCE_BACKED_STRONG`. Supported deterministic static effect claims remain eligible only for their non-strategic claim families. `reports/operator_summary.json` remains the only normal apply authority.

Source freshness fields remain diagnostic, while normalized acquisition
provenance is an authorization input for strategic receipts and runtime apply.
Only `live_http` plus `live_verified` is apply-eligible. Captured, fixture,
manual, and legacy inputs remain diagnostic-only even when their package is
technically valid. `operator_summary.json` exposes this separately as
`source_apply_eligible=false` and
`source_apply_eligibility_reasons=["diagnostic_source_not_apply_eligible"]`;
`source_status_apply_blocking` remains reserved for source-closure status.
The apply gate recomputes this authority from receipt-bound package inputs
before any runtime write.
For a technically valid diagnostic or captured package,
`fixture_classification=load_safe_fixture` is a descriptive classification
only. It is separate from `runtime_load_safe`, is not read by `apply_gate`, and
cannot authorize a write.

For staged inspection, use the Lower-Level Inspected Path below.
Per-card runtime files use `per-card <CARDID>.json` naming when the guide-backed surface is documented.
Choice surface lowering follows the card behavior policy: `discover_choice` and `choose_one_choice` only lower when option identity is source-backed, and unresolved identities stay in the `suppressed` rows of `card_behavior_plan_report.json`.

Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.

### Runtime package match

After `apply` or `configure --apply`, HSConfig verifies that the active
`CustomConfig/<config_dir>` folder semantically matches the validated package
that was copied. This is a technical install-integrity check. Before the INI
commit point, failure leaves the previous complete config selected. After the
INI commit point, the new verified config remains selected and recovery
completes advisory state or receipt work; HSConfig does not roll the committed
INI selection back to the old config.

For read-only audits, run:

```powershell
python -m hsconfig.cli runtime-match --package <package> --runtime-root <HearthRangerRoot> --json
```

`runtime-match` does not grant apply permission and never writes runtime files.
Apply permission still comes only from `reports/operator_summary.json`.

## Real-Deck Usage Loop

Use this loop to run `hsconfig configure`, then inspect source-contract and no-default-only diagnostics without treating them as extra gates.

1. Run `hsconfig configure` with the deck name, deck code, runtime root, and output directory.
2. Resolve `<out>/current.json`, then read `<current-revision>/configure_summary.json.acceptance_summary` first; `use_config_now` and `next_report_to_open` are compact operator projection fields, not an apply authority.
3. Read `<current-revision>/configure_summary.json.handoff_contract` next for the pre-run config contract receipt; it is diagnostic-only and not an apply authority.
4. When source-contract or no-default-only diagnostics are the question, read `<current-revision>/configure_summary.json.source_closure_receipt` after acceptance and handoff; it is diagnostic-only and not an apply gate.
5. Treat `technical_status=VALID_PACKAGE` plus
   `runtime_apply_mode=load_safe_apply` and `runtime_apply_allowed=true` as the
   apply signal. A valid diagnostic package may still have
   `runtime_load_safe=true` while its apply mode is blocked.
6. Inspect `mulligan_policy_status` to see whether Mulligan is source-backed or policy-backed.
7. `default_only_runtime_surfaces` must be inspected when non-empty.
8. `source_to_runtime_explainability.json` is diagnostic.
9. `source_evidence_closure.json` is diagnostic.
10. `source_contract_audit.json` is diagnostic.
11. Do not add another runtime-write authority for real-deck usage.
12. Concrete defects get targeted fixes; warnings do not become blockers.

The loop is intentionally narrow. It proves that a real deck can move through the existing normal path without turning source-depth warnings, closure freshness, default-only diagnostics, or mechanic visibility into runtime-write permission.

## Lower-Level Inspected Path

Lower-level inspected path: `source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply`.

Use this path when each source and research stage must be inspected before package preparation.

1. Run `hsconfig source-manifest` to get aliases, card targets, and research questions.
2. If compact public source-search records already exist, run `hsconfig source-autopilot`; otherwise write short source evidence rows from current guide, archetype, mulligan, card-text, and metadata sources.
3. Run `hsconfig draft-source-documents` only when you are manually turning evidence rows into strict `source_documents.json`.
4. Run `hsconfig research-deck --source-documents-json ...` to normalize guide sources.
5. Run `hsconfig prepare --guide-sources-json ...` to compile the pre-run package and reports.
6. Run `hsconfig validate --package <package> --json` before handoff or runtime apply.
7. Open `reports/operator_summary.json` first.
8. Run `hsconfig apply` only when the operator summary allows it.

## Source Claim vs Runtime Surface

Runtime Mulligan writes require explicit `claim_kind` values such as
`mulligan_keep` or `mulligan_discard`. Card importance, start-of-game effects,
deckbuilding effects, hero-power-transform text, and guide gameplan text remain
contract evidence unless they are separately backed by explicit hand-required
Mulligan guidance.

Effect semantics are not opening-hand mulligan keeps: start-of-game and
deckbuilding cards can stay visible in card behavior or diagnostics while
remaining absent from `Mulligan.json`.

`claim_kind` describes what the source says. It does not by itself authorize a
runtime write. Runtime output is decided by surface-specific gates:

- `Mulligan.json`: only explicit `mulligan_keep` or `mulligan_discard` claims.
- `GlobalValues.json`: curated `gameplan_posture` overlays plus full baseline keys.
- `Combo.json`: exact `combo_sequence` claims with valid CardID sequences and a matching live-verified strategic receipt; static semantics never authorize strategic Combo order.
- `<CARDID>.json`: documented CardID behavior claims such as targeting,
  mechanic usage, hero-power transform, discover, choose-one, and known bad
  patterns. A curated linked runtime entity may own the physical file.

Wrong-surface or low-confidence claims do not block deck generation. They are
reported as suppressed/report-only rows with explicit reasons.
`reports/source_contract_audit.json` explains those source-to-runtime decisions
per claim and per card; it does not replace `reports/operator_summary.json`.
source_contract_audit.json is diagnostic. Its `claim_lifecycle_rows` explain
source -> policy -> surface gate -> builder/router -> emitted/suppressed.
Runtime readiness still comes from `operator_summary.json`.

Source-contract invariant: effect semantics are preserved on supported effect
and CardID surfaces, but only exact runtime-surface claims lower into matching
runtime JSON. Start-of-game, deckbuilding, deck-state, and hero-power-transform
facts do not become Mulligan keeps unless there is separate exact hand-keep
authority. `source_contract_audit.json` is diagnostic; `operator_summary.json`
remains the normal apply authority.

### Linked Runtime Ownership

Card semantics and physical runtime ownership are separate:

- Source card: `SW_448` (Darkbishop Benedictus)
- Link: `hero_power_transform`
- Runtime owner: `EX1_625t` (Mind Spike)
- Physical row: `CardID/EX1_625t.json`

`SW_448` causes the transform and stays traceable in diagnostics;
`EX1_625t` owns the physical `BeforeUseHeroPowerBonus / * / 10` row.
The numeric bonus is a configuration policy value, not proof of optimal play.
Unknown or uncurated linked entities are suppressed rather than written to an
arbitrary non-deck CardID.

### Audited Semantic Closure

Use the [source-contract spine](source-contract-spine.md) for the compact
claim-to-runtime contract and the [guide research policy](guide-research-policy.md)
for exact source identity and Mulligan eligibility.

- `exact_deck_matched` requires a decoded canonical deck fingerprint match.
- Guide-backed Mulligan claims require `exact_deck_matched`.
- `hero_power_transform` does not authorize aggressive GlobalValues by itself.
- A metadata-only CardID file is not `runtime_emitted`.
- Offline tests prove neither in-client behavior nor gameplay optimality.
- `configuration_assurance` is diagnostic and has `runtime_gate_impact=none`.

The six `configuration_assurance` fields keep independent truths separate:

| Field | Meaning |
| --- | --- |
| `load_safety` | `validated` only when the technical package is valid; otherwise `not_validated`. |
| `source_authority` | `exact`, `archetype_only`, `partial`, or `unknown`. |
| `semantic_closure` | The current diagnostic `semantic_handoff_status`. |
| `in_client_behavior` | Always `not_proven_by_pre_run_contract`. |
| `optimality_claim_allowed` | Always `false` for this pre-run contract. |
| `runtime_gate_impact` | Always `none`; assurance cannot grant or deny apply. |

## Load Safety vs. Config Richness

Open `reports/operator_summary.json` first.

- `technical_status` and `runtime_load_safe` describe structural load safety.
  `runtime_apply_mode`, `runtime_apply_allowed`, `apply_policy`, and
  `runtime_apply_reason` describe the current package's apply decision.
- `mulligan_policy_status` tells whether Mulligan used source-backed or policy-backed keeps. `default_only_runtime_surfaces` must normally be empty for a generated deck package; if it is not empty, open `default_only_runtime_surface_details` and `reports/source_to_runtime_explainability.json` for the per-card closure rows before improving source claims.
- `surface_status_ledger` is the compact per-surface health view. It lists `mulligan`, `globalvalues`, `cardid_behavior`, and `combo` with one status each: `source_backed`, `policy_backed`, `static_semantics_backed`, `warning_only`, `suppressed_with_reason`, or `default_only`. This ledger is diagnostic-only. Runtime apply still depends on `operator_summary.json` technical validity and the guarded apply gate, not source strength. A `default_only` row means visible quality debt, not a hidden success and not an apply blocker by itself.
- Minimal load-safe apply requires `GlobalValues.json` and `Mulligan.json`. Normal `prepare` packages should still emit per-card `<CARDID>.json` files when deck-card identity is known, but those rich CardID files are not the minimal runtime-apply gate.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are legacy/diagnostic VisionAI surfaces outside the normal HSConfig output path. Their absence never blocks a valid load-safe package, and their presence in a normal package is treated as drift.
- `load_safe_apply` is an HSConfig operator policy, not a HearthRanger public-doc term. per-card-every-card coverage is HSConfig rich output for stronger control and matrix proof, not a minimal runtime-write requirement.
- `config_usefulness` is non-blocking. It explains whether the load-safe package is guide-aligned, usable with targeted gaps, or load-safe but thin.

No-silent-default-only policy: default-only or thin runtime surfaces are visible quality debt, not an apply blocker. `operator_summary.json` remains the only normal apply authority. When `default_only_runtime_surfaces` is non-empty, open `default_only_runtime_surface_details` and `reports/source_to_runtime_explainability.json` to see the first missing source-to-runtime link before improving guide claims or policy-backed defaults.

Contract invariant closure means: single apply authority, no silent default-only success, claim-kind surface discipline, and effect-not-mulligan canary coverage. It is diagnostic proof, not another runtime apply gate. `operator_summary.json remains the only normal apply authority`.

Semantic handoff safety:

- `SOURCE_BACKED_STRONG` proves source closure only. It is necessary but not sufficient for semantic handoff.
- Read `semantic_handoff_status` and `semantic_handoff_reasons` before describing a package as semantically closed.
- Never lower generic gameplay “keep” prose into `Mulligan.json`; explicit opening-hand or Mulligan context is required.
- Reject the whole runtime row when any structured condition atom is unsupported.
- Targeting claims count as closed only when target scope and a compatible target surface are both encoded.
- Do not emit generic `InHandPlayPriority` or `BeforePlayCardBonus` rows solely to make every-card coverage appear complete.
- `reports/operator_summary.json` remains the only normal apply authority.
- `semantic_handoff_status` is diagnostic and never creates a second apply gate.

- `config_usefulness.surfaces.mulligan` separates runtime load safety from Mulligan richness. A present `Mulligan.json` can satisfy the load-safe gate while `status=thin`, `first_gap_reason`, or `next_source_need=source_backed_or_policy_backed_mulligan_keeps` tells the operator that more exact keep/discard evidence or an explicit versioned policy claim would improve the package.
- A thin package may still be applied. Thin means the operator should inspect the named `next_report_to_open`, not that HSConfig should stop.
- A thin Mulligan means no physical row has exact Lane-B guide authority or explicit Lane-D `versioned_internal_policy` authority. It is a source-quality signal, not a HearthRanger load error. HSConfig never invents a low-curve keep set: Lane E records `bot_delegated` dispositions and leaves those decisions to HearthRanger's native pre-run bot with zero generated runtime rows. Non-hand start-of-game enablers such as Darkbishop Benedictus still require explicit opening-hand authority.
- The frozen twelve-package release projection groups all 426 report occurrences into exactly 316 canonical claim identities: `A:267`, `B:0`, `C:49`, `D:0`, `E:0`. The 49 guide-context claims include deck-matched and low-confidence source rows that lack live-verified, same-fingerprint Lane-B authority. Suppression and low confidence never mint Lane E; only an explicit `bot_delegated` disposition plus a matching zero-emission lifecycle row can do so.
- HSConfig stays pre-run only. Post-game evidence review and post-game tuning belong in HSTuner, outside this skill.

## Runtime Apply Authority

`reports/operator_summary.json` is the sole human-facing verdict; never infer apply readiness from individual diagnostic reports.
The CLI and direct Python entry points both run strict complete-package validation before the shared apply gate.
CLI prevalidation failures return `validation_report` and `errors`; they may stop before a stable apply-gate reason code exists.
Direct `plan_apply_package()` / `apply_package()` prevalidation raises before the shared gate.

After prevalidation, `evaluate_apply_gate()` independently rechecks the package
instead of trusting the human-facing verdict as a self-assertion. These are simplified fail-closed phases, not a promise that every entry point emits the same intermediate result or reason code:

1. Require a readable object at `reports/operator_summary.json`.
2. Validate required package structure, forbidden surfaces, runtime JSON, and strict package semantics.
3. Recompute deck-input verification and require runtime apply eligibility.
4. Verify strategic source authority.
5. Require the derivation receipt and summary derivation metadata.
6. Verify the receipt schema and recompute its summary-bound digest.
7. Recompute receipt content from authoritative inputs and runtime JSON.
8. Verify exact summary derivation consistency and generated-file parity.
9. Authorize the runtime write only for a recomputed valid package.

Only `decoded_from_deck_code` and `cards_json_matches_deck_code` inputs are
apply-eligible. Unverified deck input blocks apply even when a diagnostic package can still be built.

When the shared gate is reached, stable coded failures include:

- `strict_package_validation_failed`
- `deck_input_not_verified`
- `source_authority_receipt_invalid`
- `package_derivation_receipt_missing`
- `package_derivation_receipt_schema_unsupported`
- `package_derivation_receipt_digest_mismatch`
- `package_derivation_mismatch`
- `operator_summary_derivation_inconsistent`

These codes belong to the shared gate; CLI prevalidation can instead return `validation_report` and `errors` before that gate is reached.

`package_derivation_mismatch` is the recomputation failure: authoritative deck
identity, source receipts, GlobalValues authority inputs, ownership manifest,
or runtime JSON no longer matches the canonical receipt.

`no_block_failure_mode_summary` is the fastest way to read why a package did
or did not stop. `technical_hard_block` is the only technical hard-stop
category. A valid `load_safe_fixture` can still have
`overall=runtime_apply_not_allowed`, `hard_block=false`,
`runtime_apply_reason=diagnostic_source_not_apply_eligible`,
`apply_policy=BLOCKED`, and
`next_action=ACQUIRE_LIVE_VERIFIED_SOURCE_BEFORE_APPLY`. The
other categories, `source_depth_warning`, `warning_only_mechanic`,
`future_mechanic_drift`, `guide_strength_gap`, `combo_uncertainty`, and
`runtime_evidence_only_tuning`, explain source or semantic limits while
`load_safe_apply` can proceed only when the current package gate also allows it.
It does not create a second apply path.

`hsconfig apply --fake --json` creates a receipt-bound preview without runtime mutation.
Normal `hsconfig apply --json` remains autonomous when the gate allows it: it creates
and verifies the fake receipt in the same invocation, then writes the runtime package.
`--from-fake-receipt` can be used when an operator wants to apply a previously generated
matching fake receipt.

For the durable no-block contract across valid Wild decks, see
`docs/operator/universal-wild-no-block-contract.md`.

- `technical_status=VALID_PACKAGE` means the runtime JSON shape is structurally valid and load-safe.
- `runtime_load_safe=true` means the package passed the normal pre-run load-safety contract.
- `fixture_classification=load_safe_fixture` classifies a technically valid
  diagnostic/captured fixture. It is output-only and never an apply-gate input.
- `runtime_apply_mode=load_safe_apply` means normal `hsconfig apply --json` is allowed.
- `runtime_apply_mode=blocked` means no runtime write should happen. The package
  may be invalid/load-unsafe, or it may be valid/load-safe but apply-ineligible
  because its source provenance is diagnostic.
- `runtime_apply_allowed=true` is descriptive; the CLI and `apply_package()` still re-evaluate the gate before writing.
- `semantic_status=SOURCE_BACKED_STRONG` means source coverage and per-card closure support source-backed confidence and handoff. It is not a runtime apply permission; use `technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` for normal guarded apply.
- `semantic_status=VALID_BUT_NOT_GUIDE_STRONG` means the package is valid and load-safe, but source depth, runtime surfaces, combo detail, conditions, mechanics, or conflicts still need work before it can be called source-backed strong.
- `apply_policy=ALLOWED` marks the no-warning source-strong path; it is not the only normal apply permission.
- `next_action=READY_TO_APPLY_WITH_WARNINGS` plus `apply_policy=ALLOWED_WITH_WARNINGS` means the package is still allowed to write at runtime when `technical_status=VALID_PACKAGE`, while semantic warnings remain visible in the reports.
- `runtime_apply_reason=diagnostic_source_not_apply_eligible` pairs with
  `apply_policy=BLOCKED` and
  `next_action=ACQUIRE_LIVE_VERIFIED_SOURCE_BEFORE_APPLY`; READY/ALLOWED values
  are not valid for that package.
- `source_informed_apply_readiness.status=ready` is diagnostic only. It documents that the remaining semantic blockers are limited to allowed source-depth gaps such as `cards_need_guide_claims` or `cards_need_mulligan_claims`.
- `cards_need_runtime_surface`, combo, condition, mechanic, conflict, unsupported-condition, uncovered-card, and generic-low-confidence blockers keep source-informed apply blocked.
- `ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE`; warnings describe semantic/source confidence debt, not a write blocker.

Lower-level reports explain the gate. They do not grant independent apply permission.

For the active claim-kind-to-runtime boundary, see `docs/operator/source-contract-spine.md`; it is a diagnostic reference, not a command path.

Direct Python runtime writes use the same gate. `hsconfig.runtime_apply.apply_package()` resolves `reports/operator_summary.json` through `evaluate_apply_gate()` before any runtime mutation and rejects forged or missing gate dictionaries. Use the CLI for normal operation; direct imports are test and integration surfaces, not a second permission model.

## Report Ownership

Open `reports/operator_summary.json` first. Other reports explain source quality, mechanic coverage, ownership, and missing links. They do not grant apply permission.

`source_depth_lane` is a readable alias for the first missing source/runtime link:
`closed`, `source_claim_gap`, `mulligan_claim_gap`, `runtime_surface_gap`,
`combo_sequence_gap`, `condition_lowering_gap`, or `mechanic_lowering_gap`.
It does not grant apply permission. Use `reports/operator_summary.json` as the gate.

| File | Authority | Answers |
| --- | --- | --- |
| `reports/operator_summary.json` | normal operator gate | what to do next |
| `reports/source_to_runtime_explainability.json` | diagnostic source-to-runtime projection | which exact source-to-runtime link is missing before a card can be stronger |
| `reports/source_evidence_closure.json` | diagnostic source evidence closure | compact package-quality closure summary without apply authority |
| `reports/source_contract_audit.json` | diagnostic source-to-runtime explanation | why each source claim did or did not lower to runtime config |
| `reports/source_claim_gap_report.json` | secondary diagnostic evidence for card/source gap history | which card link is missing first |
| `reports/strong_promotion_report.json` | promotion confirmation | whether the package can be called source-backed strong |
| `reports/per_card_config_readiness_report.json` | card lane diagnostics | which lane each card occupies |
| `reports/guide_source_depth_report.json` | source-depth diagnostics | how strong the guide and source coverage is |
| `reports/global_values_authority_matrix.json` | GlobalValues diagnostics | which GlobalValues keys are source-backed or archetype-inferred |
| `reports/mechanic_drift_report.json` | non-blocking mechanic drift visibility | which unknown, text-only, or current-card-type mechanics should be inspected next |
| `reports/semantic_enrichment_report.json` | semantic mechanic diagnostics | which static mechanics, linked entities, deckwide effects, and warning-only flags were inferred |

## Diagnostic Detail

`reports/source_to_runtime_explainability.json` is the card-readable projection
of the source-contract audit: it names emitted runtime files, missing runtime
files, the first missing link, the per-card closure lane, and the next source action per claim/card. Its
compact `source_to_runtime_explainability_summary` in `operator_summary.json` is
non-blocking and does not grant apply permission.

source_to_runtime_explainability.json is the primary card-readable repair map for source-to-runtime closure. It names emitted runtime files, missing runtime files, first missing links, closure lanes, and next source actions. source_claim_gap_report.json is secondary diagnostic evidence for older source-depth workflows; it must not become the first operator report and does not grant or deny apply permission.

`reports/source_evidence_closure.json` is the compact diagnostic closure summary
for package quality. It mirrors the operator/source-to-runtime summaries,
default-only risk, next report, and first missing source-action counts without
becoming an apply authority.

Fresh package proof should show `reports/operator_summary.json.source_to_runtime_explainability_summary.closure_schema_current=true` and `cards_missing_closure=0`. If closure rows are missing, treat the package as stale or diagnostically incomplete and regenerate it; this is not a runtime apply gate. Default-only surfaces must not be silent: open `default_only_runtime_surface_details` and `reports/source_to_runtime_explainability.json` before reading a package as qualitatively complete.

`mechanic_visibility_summary` is descriptive and non-blocking. It shows
`direct`, `identity_gated_direct`, `partial`, and `warning_only` mechanic
buckets so a valid package can be applied while still making Dredge, Tradeable,
unresolved generation, or partial targeting limits visible.

The mechanic lowering registry is the executable authority behind
`needs_mechanic_lowering`. `cards_needing_mechanic_lowering` only increments
when a registered mechanic has a documented default CardID lowering target and
no meaningful CardID row was emitted. Dredge, Tradeable, and unknown future
mechanics stay report-only/warning-only; they do not increment
`cards_needing_mechanic_lowering`.

`first_warning_boundary` names the first next-inspection item.
`warning_boundaries` is the complete alphabetical list of report-only mechanics
the operator may inspect next. `choose_one` is identity-gated direct, while
`board_position`, `generic_spell_target`, `location_activation`,
`secret_timing`, and `generated_entity_random_pool` are warning-only. These
warnings are explanatory; warning-only mechanics do not block load-safe apply
for a valid package.

`reports/mechanic_drift_report.json` is the non-blocking current-card-data drift
surface. `mechanic_drift_summary` in `reports/operator_summary.json` lists
unknown mechanics, text-only mechanics, and unknown card types detected from
HearthstoneJSON-style metadata. Unknown mechanics are warning-only and do not
block load-safe apply. Mechanic drift is not a runtime apply gate; it tells the
operator which future Wild mechanic should be mapped next.

Modern mechanic visibility is non-blocking. HSConfig names current mechanics
such as `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`,
`quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue` when card
metadata or text exposes them. Mechanics without a documented normal-path
VisionAI runtime surface stay visible as `warning_only` or `partial`; they must
not block `load_safe_apply` for a technically valid package. `rewind`, `herald`,
and `shatter` are warning-only report-only visibility labels; HSConfig names
them in reports and does not map them to runtime surfaces.

Open `reports/semantic_enrichment_report.json` when the summary points to
static or warning-only mechanic coverage. It explains inferred card semantics,
static evidence, linked entities, deckwide effects, and warning-only flags.
Lowerability buckets live in `reports/operator_summary.json` and
`reports/per_card_config_readiness_report.json`.

## Optional Acceptance Matrix

Use `hsconfig acceptance-matrix` after one or more packages have already been
prepared when you want a compact read-only proof view.

```powershell
hsconfig acceptance-matrix --package outputs/ShadowPriest --package outputs/BigShaman --json
```

The matrix summarizes `technical_status`, `runtime_apply_mode`, runtime file
coverage, CardID file count, `config_usefulness`, and warning boundaries across
packages. It is diagnostic only. It does not write runtime files, and it does not replace `reports/operator_summary.json`
as the single operator gate.

A technically valid, load-safe diagnostic-source package remains a failed
matrix row because apply is ineligible, but it is classified as
`apply_eligibility_classification=diagnostic_source_apply_ineligible` with
`technical_hard_block_count=0`. Its blocked mode, false apply permission, and
`diagnostic_source_not_apply_eligible` reason remain visible. Invalid,
load-unsafe, inconsistent, or otherwise technically blocked packages retain a
technical hard block.

Read `status` first. The matrix-level `status` is authoritative for the
matrix diagnostic. Row fields such as `apply_gate_allowed`,
`runtime_apply_mode`, and `validation_status` explain why a package passed or
failed, but they do not override `status` or `matrix_row_status`.

Developer drift check: `hsconfig contract-spine-sentinel --json` verifies that source-contract diagnostics have not become a second apply path. Normal deck configuration still starts with `hsconfig configure`, and `reports/operator_summary.json` remains the apply authority.

## Optional Source Closure Optimizer

Use `hsconfig source-closure-optimizer` after packages have already been
prepared when you want a compact source-depth and research freshness diagnostic.

```powershell
python -m hsconfig.cli source-closure-optimizer `
  --package outputs\latest\ShadowPriest\04_package `
  --research-results-dir docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop\results `
  --out outputs\diagnostics\source_closure_optimizer.json `
  --markdown-out outputs\diagnostics\source_closure_optimizer.md
```

Use the research relation fields to refresh stale research snapshots; do not
use them to override `operator_summary.json` or to block a valid load-safe
package.

## Developer Guardrail

Run this after changing source-contract, skill, apply, report ownership, or
mechanic-lowering code:

```powershell
python scripts\check_contract_guardrails.py
```

The command checks installed-skill sync, `hsconfig contract-spine-sentinel
--json`, and the focused boundary tests. It is diagnostic only. Normal deck
configuration still starts with `hsconfig configure`, and
`reports/operator_summary.json` remains the only normal apply authority.
The lower-level `hsconfig contract-preflight --json` exposes the same
installed-skill sync class in its JSON payload for quick operator checks.

## Optional Contract Doctor

Use `hsconfig contract-doctor --package <package> --json` when a prepared package
is valid but you want a compact explanation of source -> claim_kind -> surface
gate -> builder/router -> runtime effect diagnostics. It does not write runtime
files; `--out` only writes the requested Markdown diagnostic.
operator_summary.json remains the only normal apply authority.

`hsconfig contract-doctor --package <04_package> --json` includes a diagnostic-only
`config_quality` section. It checks no-default-only visibility, CardID semantic
score coverage, runtime JSON leanness, forbidden legacy surfaces, the Darkbishop
effect-not-mulligan boundary, source-to-runtime trace completeness, closure
freshness, stray CardID runtime files, and report-only mechanic runtime drift. It
does not replace `reports/operator_summary.json`, does not apply runtime files,
and does not block a technically valid package.

`config_quality.checks.semantic_intent_coverage` is a diagnostic-only rollup: it shows traced per-card intent, missing semantic scores, semantic-default rows, report-only mechanic runtime leaks, and warning-only mechanics, but it does not change `reports/operator_summary.json` apply authority.

`<current-revision>/configure_summary.json.acceptance_summary` is the first post-`configure` read after resolving `<out>/current.json`. It is a compact operator projection with `use_config_now`, `technical_status`, `runtime_apply_allowed`, `source_strength`, `default_only_clean`, and `next_report_to_open`; it does not replace `reports/operator_summary.json`, which remains the normal apply authority.

`configure_summary.json.handoff_contract` is a diagnostic-only handoff proof for normal generated packages. It compresses the already-generated acceptance, config-proof, and config-quality facts into one small object: single authority, no-default-only status, forbidden normal surfaces, source-to-runtime trace status, Darkbishop boundary status, mechanic discipline, and the next report to open. It does not replace reports/operator_summary.json and it cannot grant or deny runtime writes.

`<current-revision>/configure_summary.json.source_closure_receipt` is the compact diagnostic-only source-closure receipt for normal generated packages, read after acceptance and handoff when source depth is the question. It mirrors the canonical source status, no-default-only status, source acquisition counts, source document counts, runtime-lowerable claim counts, and the first missing source action. It does not replace `reports/operator_summary.json`, cannot promote, block, apply, or write runtime files, and default-only runtime surfaces remain visible quality debt rather than hidden success.

`contract-preflight.research_context.latest_research_result_contract_*` exposes whether the latest research-deep result batch has HSConfig-valid fields and result payloads. This research-result sentinel is source-quality visibility only; it cannot promote, downgrade, block, or apply a package.
`latest_research_result_contract_first_non_promoting_*` names the first source action needed for Strong closure; it is diagnostic-only, cannot block or promote a package, and operator_summary.json remains the only normal apply authority.

Then read `<current-revision>/configure_summary.json.config_proof_summary` only as a diagnostic-only config proof. `source_to_runtime_status` reports trace health (`clean`, `attention`, or `missing`), while `currentness_status`, `closure_schema_current`, and `cards_missing_closure` report closure freshness. `forbidden_normal_surfaces_status=unknown` means legacy-surface evidence was unavailable, not clean. `runtime_surface_boundary_details` lists `GlobalValues.json`, `Mulligan.json`, and per-card `<CARDID>.json` as unconditional; `Combo.json` is conditional on a complete source-backed combo with a matching live-verified strategic receipt. This proof is not another apply gate and does not replace `reports/operator_summary.json`.

`<current-revision>/configure_summary.json.config_quality_summary` remains a compact diagnostic-only, non-blocking mirror of the existing config-quality contract. It is for quick quality visibility after `hsconfig configure` or when `acceptance_summary.next_report_to_open` points to `reports/contract_doctor.json`. If `status` is `attention`, run `hsconfig contract-doctor --package <current-package>` for details. The normal apply authority remains `<current-package>/reports/operator_summary.json`.

`config_intent_self_audit` is a diagnostic-only proof that generated runtime files are intentionally explained by `operator_summary.json`, source-to-runtime explainability, deck identity, or explicit non-blocking default/suppression visibility. If its status is `attention`, the package can still be technically usable through `reports/operator_summary.json`, but inspect `reports/contract_doctor.json` or run `hsconfig contract-doctor --package <04_package> --json` before calling the config qualitatively complete.

## Expert Paths

Use `hsconfig build`, `hsconfig research-contract`, `--claims-json`, `--plan-reports-dir`, and `--allow-placeholder` only for fixtures, diagnostics, or inspected expert inputs. `--cards-json` is apply-eligible only when its normalized roster exactly matches the decoded deck code; otherwise it remains diagnostic and apply is blocked.

`--allow-source-informed` is a backward-compatible legacy no-op. It does not create a second apply path. Runtime apply decisions come from `reports/operator_summary.json`.

```powershell
hsconfig apply --package <package> --runtime-root <runtime-root> --json
```

Source-informed apply is still not `SOURCE_BACKED_STRONG`; close the remaining `source_claim_gap_report.json` links before promoting the fixture or calling the package strong.

## Fixture Matrix

`docs/operator/audited-deck-catalog.json` is the single identity source for the
twelve audited user decks. It owns each exact `deck_name`, `deck_code`, `hs_id`,
and `hdt_deck_id`: eleven rows have the `representative` role and CuteWarrior
has the `supplemental` role. The role manifests below reference this catalog by
`deck_name`; do not copy audited identity fields into them.

`docs/operator/archetype-fixture-matrix.json` is the representative 11-deck HSConfig proof set.

Source-depth closure means every representative deck either proves `SOURCE_BACKED_STRONG` or exposes the first missing source-to-runtime link. Close existing matrix gaps before adding more representative decks.

When a source-informed row cannot be promoted honestly, keep it visible with an explicit stop condition instead of widening the matrix or forcing a weak source claim.

Do not add a new representative deck when an existing row can exercise the same source-depth or runtime-surface family.

Boarlock remains the first closure-truth row because it is the representative
`Combo.json` control. Its current Fracking row is durably preserved as
source-informed until exact Boarlock-relevant Fracking mulligan evidence exists.

Boarlock and Kingslayer are both durable source-informed controls with explicit
stop conditions. Do not widen the representative matrix to a twelfth deck to
avoid these rows. Add or promote only when exact source evidence closes a
preserved stop condition.

After durable Boarlock and Kingslayer preservation, the current actionable source-informed closure targets are the four partial representative rows: CtAPaladin, Discolock, TreantDruid, and PirateDH.

The representative fixture matrix proves source-depth breadth. The universal
no-block matrix proves the separate runtime promise: every valid listed deck
still creates a load-safe initial package even when source confidence remains
warning-only.

### Twelve-deck read-only acceptance

`tests/test_audited_deck_set_acceptance.py` combines the eleven representative
manifest rows with the supplemental CuteWarrior row without copying deck codes
or promoting CuteWarrior into the representative matrix. A catalog guard
requires exactly eleven representative rows, exactly one supplemental
CuteWarrior row, exactly twelve audited rows, and unique deck names, deck
codes, Hearthstone IDs, and HDT deck IDs. Every exact deck code must decode to
30 main-deck cards with no unresolved DBF IDs. MechPala additionally preserves
its three decoded Zilliax sideboard modules under `TOY_330`; every other audited
deck has no sideboard cards. It prepares packages only under pytest temporary
directories. The test
uses a frozen local DBF snapshot for the twelve audited deckstrings. The
snapshot pins HearthstoneJSON build `247416`, its immutable `CardDefs.xml` URL,
capture timestamp, upstream raw digest, and a canonical snapshot digest. Its
loader derives the required DBF set independently from the raw deckstrings and
requires exactly 192 unique DBF IDs and 192 unique CardIDs with no missing or
extra row. The test denies external Cardfeed/DNS/socket access, including the
directly imported source-acquisition resolver and connection aliases, stubs the
runtime writer entry, keeps the temporary runtime root absent, and requires
that no runtime apply receipt is created.

The twelve captured/fixture-backed cases are expected to be technically valid
and load-safe but apply-ineligible with
`runtime_apply_reason=diagnostic_source_not_apply_eligible`. This is a
provenance result from the current package's `reports/operator_summary.json`;
the fixture manifests describe test scope and do not participate in runtime
apply authority. A
separate exact-deck fixture acquired through the real source-acquisition path
shows the positive boundary: only `live_http` plus `live_verified` provenance
and a passing current strict package validation can produce a technically
eligible gate.

The acceptance set enforces these semantic boundaries across physical output
and reports:

- semantic-enrichment card types prove that neither the source card nor a
  linked physical runtime owner is a spell for `OnBoardBonus` or
  `BeforeBattlecryTargetBonus`;
- physical CardID `values` rows and meaningful report rows have exact
  duplicate-preserving, typed parity in both directions before every report row
  is checked for source-claim and source-ref provenance; unsupported conditions
  remain suppressed rather than becoming unconditional rows;
- ShadowPriest keeps the Mind Spike linked owner, report-only reciprocal burn,
  and one board row for each audited summon engine;
- MechPala keeps all three `TOY_330` sideboard modules report-visible and keeps
  `TOY_330` out of policy Mulligan holds;
- Kingslayer and Boarlock keep the unresolved `DEEP_014` and `WW_092` policy
  holds suppressed; Kingslayer wrong-owner attack rows, a static Boarlock
  `Combo.json`, and unauthorized hero-power overlays remain absent;
- Discolock has no coverage-only `InHandPlayPriority` or unauthorized
  GlobalValues overlay, and ImbueMage physical Mulligan identities match its
  readiness ledger.

This matrix proves a read-only pre-run package contract. It does not prove
in-client execution, gameplay improvement, matchup quality, or optimality.

## Supplemental Proof Decks

`docs/operator/source-candidate-proof-decks.json` is the separate 12-deck
source-candidate proof set. It proves that each user-supplied Wild deck has
either a registry candidate or an explicit first missing source action.
Candidate registry lookup is keyed only by `deck_name`; callers must not pass
or silently discard a deck code.
This proof set does not widen the representative fixture matrix and does not change runtime apply authority.

`docs/operator/supplemental-proof-decks.json` lists decks that prove narrow command,
syntax, or acceptance behavior without widening the representative matrix.

CuteWarrior is supplemental. It must not be counted as a twelfth representative
row unless a future matrix review proves a real missing family that none of the
current eleven representative rows can exercise.

SecretMage and HighlanderPriest are supplemental visibility-only decks. They
prove that current Wild secret/highlander/location control surfaces still
produce load-safe packages, but they do not widen the representative matrix and
do not close Boarlock or Kingslayer source-depth stop conditions. Their
manifest-local deck codes are intentionally outside the audited twelve-deck
identity catalog.
