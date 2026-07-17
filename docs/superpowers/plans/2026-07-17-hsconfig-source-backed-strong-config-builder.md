# HSConfig Source-Backed Strong Config Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `hsconfig configure` path produce the best available load-safe CustomConfig package for every valid Wild deck, while promoting a deck to `SOURCE_BACKED_STRONG` only when full-text source claims, claim-kind contracts, closure profiles, and no-default-only runtime surfaces all agree.

**Architecture:** Keep the existing source pipeline as the single chain of authority: `source_acquisition.collect_public_source_records` fetches public source records, `source_claim_compiler.compile_source_search_records` normalizes acquired records, `source_autopilot.build_source_autopilot_bundle` extracts evidence rows and drafts `source_documents.json`, `source_document_builder.build_source_document_bundle` qualifies source claims, `source_status_resolver.resolve_source_status` resolves the canonical package source status, and `operator_summary.json` remains the only normal apply-facing authority. Do not add a second status model or an alternate apply gate.

**Tech Stack:** Python stdlib, pytest, existing `hsconfig` modules, existing source fixtures, existing CLI command surface, no new runtime dependencies.

## Global Constraints

- Always refresh repository state before implementation:
  - Run `git fetch --all --prune`.
  - Run `git rev-list --left-right --count HEAD...origin/main`.
  - Expected output before code work: `0 0`, or stop and record the divergence before editing.
- Preserve existing dirty worktree changes. Do not revert user or previous-agent work unless explicitly requested.
- Keep the solution narrow:
  - Extend the current acquisition/autopilot/document/closure path.
  - Do not introduce a new scoring framework, new config generator, new branch policy, or new dependency.
- `SOURCE_BACKED_STRONG` is an evidence-quality status only. It must never be required for package generation or apply eligibility.
- Every valid Wild deck must still produce a load-safe, validated package. Missing public sources must surface as `SOURCE_BACKED_PARTIAL` or equivalent diagnostics, not as a deck block.
- No default-only surface may silently count as complete:
  - Generated default or placeholder runtime values must be visible in reports.
  - Default-only data must prevent `SOURCE_BACKED_STRONG`.
  - Default-only data must not prevent a load-safe package when the deck is otherwise valid.
- Candidate URLs, decklists, stats pages, and registry entries are source seeds. They are not strong evidence unless full-text extracted claims pass source policy, claim-kind normalization, and closure profile requirements.
- Darkbishop Benedictus must remain effect-only for ShadowPriest:
  - Keep `hero_power_transform` / Shadowform / Mind Spike semantics in `CardID` runtime config.
  - Do not keep `SW_448` in opening hand unless an explicit full-text mulligan source says to keep it.
- Strong promotion must be reproducible offline through fixtures and deterministic tests.

## Deck Matrix Under Test

Use these deck identities for the universal no-block and source-status matrix. The implementation may reuse existing fixtures where present, but the acceptance tests must cover these exact deck names.

| Deck | Deckcode | HSid | HDT-DeckId |
| --- | --- | --- | --- |
| ShadowPriest | `AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=` | `2737726722` | `c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602` |
| CtAPaladin | `AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=` | `2737744316` | `f9b54950-ca24-48cf-805e-bf620eab47a0` |
| PirateRogue | `AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==` | `2740734095` | `c1e87d43-5802-460b-b955-31ae458eb41a` |
| BigShaman | `AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==` | `2737735409` | `6b26f907-6f1e-44c8-a4e4-d14e9d51f819` |
| Discolock | `AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA` | `2740357533` | `55241397-ac74-4d46-a662-089e5858839c` |
| TreantDruid | `AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==` | `2740360895` | `a120a28b-1840-4032-a3c9-2da4c51338ed` |
| ImbueMage | `AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=` | `2740361888` | `49c05560-8b30-4d06-b3a2-a8b0ff36d005` |
| MechPala | `AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==` | `2740734214` | `8f011f55-8ae2-436c-b53a-315f280e8833` |
| Kingslayer | `AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=` | `2740733989` | `1292ff02-8ebe-47a5-90b1-9a1899acd6aa` |
| Boarlock | `AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA` | `2740361505` | `7727c718-c93c-47ca-a766-5612c3806f0f` |
| PirateDH | `AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==` | `2737737281` | `2bc184ed-b59a-4420-900d-b0ed3d153979` |
| CuteWarrior | `AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=` | `2750150375` | `a753f091-b770-4a06-8da8-59f1d5269f6b` |

## Implementation Tasks

### 1. Baseline Refresh And Worktree Ownership

- [ ] Run:
  - `git fetch --all --prune`
  - `git rev-list --left-right --count HEAD...origin/main`
  - `git status --short --branch`
- [ ] Expected upstream sync result: `0 0`.
- [ ] Record the current dirty files in `.superpowers/sdd/progress.md` before new edits so prior completed work is not mistaken for new changes.
- [ ] Confirm these existing files are the intended integration points:
  - `src/hsconfig/source_acquisition.py`
  - `src/hsconfig/source_claim_compiler.py`
  - `src/hsconfig/source_autopilot.py`
  - `src/hsconfig/source_document_builder.py`
  - `src/hsconfig/source_status_resolver.py`
  - `src/hsconfig/operator_summary.py`
  - `src/hsconfig/package_builder.py`
  - `src/hsconfig/commands/configure.py`
- [ ] Do not create a parallel status module, parallel package builder, or parallel command.

### 2. Lock The Source Acquisition Contract With Tests

- [ ] Add or extend tests in `tests/test_source_backed_strong_harvester_closure.py` and `tests/test_configure_online_source.py`.
- [ ] Test current full-text guide behavior:
  - Use a ShadowPriest fixture mapped through `--source-fixture-url-map-json`.
  - Assert `source_acquisition_report.json` has:
    - `source_record_count > 0`
    - a guide record with `source_visibility == "full_text"`
    - `deck_match_scope in {"deck_matched", "deck_or_archetype_matched"}`
    - `promotion_eligible is True`
    - `strong_promotion_eligible is True`
    - `first_missing_source_action == "none"`
- [ ] Test non-strong seeds:
  - A decklist-only source must produce `promotion_eligible is False`, `strong_promotion_eligible is False`, and `first_missing_source_action != "none"`.
  - A stats-only source must produce `promotion_eligible is False`, `strong_promotion_eligible is False`, and `first_missing_source_action != "none"`.
  - A static card-text source may support effect semantics, but must not by itself promote deck strategy or mulligan strategy to strong.
- [ ] Expected command:
  - `python -m pytest tests/test_source_backed_strong_harvester_closure.py tests/test_configure_online_source.py tests/test_source_evidence_policy.py -q`
- [ ] Expected result after implementation: all selected tests pass.

### 3. Make Evidence Rows Explicit And Atomic

- [ ] Update `src/hsconfig/source_acquisition.py` only if a field is missing from acquired records. Required acquired record fields:
  - `source_url`
  - `source_title`
  - `source_family`
  - `source_visibility`
  - `source_category`
  - `source_document_kind`
  - `publication_year`
  - `retrieved_at`
  - `deck_match`
  - `deck_match_scope`
  - `normalized_text`
  - `promotion_eligible`
  - `strong_promotion_eligible`
  - `promotion_blockers`
  - `first_missing_source_action`
- [ ] Update `src/hsconfig/source_autopilot.py` so `extract_source_evidence_rows` keeps policy fields on every extracted row:
  - `source_lane`
  - `source_freshness_lane`
  - `source_rank_lane`
  - `deck_match_scope`
  - `trust_ceiling`
  - `promotion_eligible`
  - `strong_promotion_eligible`
  - `first_missing_source_action`
- [ ] Ensure `extract_text_claims` output cannot convert an inherited non-promoting source into a promoting claim.
- [ ] Ensure `_mulligan_rows`, `_explicit_claim_rows`, and text-extracted rows all use one normalization path for:
  - `claim_kind`
  - `cards`
  - `scope`
  - `evidence_text_short`
  - `source_type`
- [ ] Add regression tests in `tests/test_source_autopilot.py`:
  - A non-promoting source record yields only non-promoting evidence rows.
  - A strong guide source can yield promoting evidence rows only for claim kinds accepted by `source_document_model.SUPPORTED_ATOMIC_CLAIM_KINDS`.
  - A default/runtime-generated source type never yields strong evidence rows.

### 4. Preserve Canonical Source Status Resolution

- [ ] Keep `src/hsconfig/source_status_resolver.py` as the single source-status resolver.
- [ ] Add tests in `tests/test_source_status_resolver.py` if missing for:
  - `technical_status == "VALID_PACKAGE"` plus all closure profiles strong plus no default-only surfaces yields `SOURCE_BACKED_STRONG`.
  - Any `default_only_surface_count > 0` yields `SOURCE_BACKED_PARTIAL` or the existing non-strong status, with `first_missing_source_action == "replace_default_only_runtime_surface_with_source_claim"`.
  - Any `source_claim_gap_report` missing claim chain yields non-strong and forwards the first exact action.
  - Diagnostic-only evidence cannot make `apply_blocking` true.
- [ ] Ensure `src/hsconfig/operator_summary.py`, `src/hsconfig/strong_promotion_report.py`, and `src/hsconfig/source_evidence_closure.py` consume `SourceStatusResolution.to_dict()` rather than reimplementing status strings.
- [ ] Expected command:
  - `python -m pytest tests/test_source_status_resolver.py tests/test_operator_summary.py tests/test_strong_promotion_report.py tests/test_source_evidence_closure.py -q`
- [ ] Expected result after implementation: all selected tests pass.

### 5. Enforce No Default-Only Runtime Surfaces Without Blocking Decks

- [ ] Audit `src/hsconfig/package_builder.py` for every fallback/default/runtime surface emitted into package files.
- [ ] Make every default-only surface visible in reports through existing summary structures:
  - `operator_summary.json`
  - `source_to_runtime_explainability.json`
  - `source_claim_gap_report.json`
  - `source_evidence_closure.json`
  - `strong_promotion_report.json`
- [ ] Add or extend `tests/test_universal_wild_no_block_matrix.py`:
  - All twelve deck names in the deck matrix generate a package.
  - Every generated package validates.
  - No deck is blocked solely because source status is partial.
  - No package can report `SOURCE_BACKED_STRONG` when it has default-only runtime surfaces.
  - Every non-strong deck has a non-empty `first_missing_source_action`.
- [ ] Expected command:
  - `python -m pytest tests/test_universal_wild_no_block_matrix.py -q`
- [ ] Expected result after implementation: all selected tests pass and all matrix rows are load-safe.

### 6. ShadowPriest Fresh Strong Closure

- [ ] Add a focused ShadowPriest end-to-end test in `tests/test_shadowpriest_fresh_closure_proof.py`.
- [ ] Fixture requirements:
  - Use the provided ShadowPriest deck code.
  - Use at least one current full-text public guide fixture that contains explicit mulligan text.
  - Use static card semantics for Darkbishop Benedictus.
- [ ] Assertions:
  - `operator_summary["source_backed_status"] == "SOURCE_BACKED_STRONG"`.
  - `operator_summary["first_missing_source_action"] == "none"`.
  - `operator_summary` reports zero default-only runtime surfaces.
  - `SW_448` is present only through effect semantics in the `CardID` runtime surface.
  - `SW_448` is not emitted as a `mulligan_keep` claim unless the source text explicitly says to keep it.
  - The configured opening-hand keeps come from guide-backed mulligan claims, not from static card text.
- [ ] Expected command:
  - `python -m pytest tests/test_shadowpriest_fresh_closure_proof.py tests/test_source_evidence_policy.py tests/test_source_autopilot.py -q`
- [ ] Expected result after implementation: ShadowPriest closes strong and Darkbishop remains effect-only.

### 7. Configure Command Wiring

- [ ] Keep the command sequence in `src/hsconfig/commands/configure.py`:
  1. `source-manifest`
  2. optional `source-acquire`
  3. optional `source-autopilot`
  4. `research-deck`
  5. `prepare`
  6. `validate`
  7. optional `apply`
- [ ] Ensure `--online-source` always writes:
  - `02_source_acquisition/source_acquisition_report.json`
  - `02_source_acquisition/source_claim_compiler_report.json`
  - `02_source_acquisition/source_search_results.json`
  - `03_source_autopilot/ranked_sources.json`
  - `03_source_autopilot/source_evidence_rows.json`
  - `03_source_autopilot/source_documents.json`
  - `03_source_autopilot/source_autopilot_report.json`
  - `04_package/reports/operator_summary.json`
  - `04_package/reports/source_bundle.json`
  - `04_package/reports/source_evidence_closure.json`
- [ ] Ensure `--apply` still calls `apply_payload` only after package validation succeeds.
- [ ] Ensure `--apply` does not require `SOURCE_BACKED_STRONG`.
- [ ] Add one CLI regression in `tests/test_configure_online_source.py`:
  - A partial-source deck with a valid package validates and can run configure without failure.
  - The same package reports non-strong status and a concrete first missing source action.

### 8. Candidate Registry And Online Deck Cross-Check

- [ ] Audit `src/hsconfig/source_candidate_registry.py` against current online source categories.
- [ ] Keep registry entries as seeds, not proof:
  - ShadowPriest may include a current full-text guide URL.
  - Hearthstone-decks category pages may be retained as decklist or archetype discovery seeds.
  - HSGuru or stats pages may be retained only as statistical context.
- [ ] Add or extend `tests/test_source_candidate_registry.py` and `tests/test_source_candidate_registry_matrix.py`:
  - Every matrix deck has at least one candidate URL or a documented static-semantics-only fallback action.
  - Any decklist/stat-only candidate has `first_missing_source_action != "none"`.
  - A `none` action is allowed only when the registry entry points to a current or evergreen full-text guide that can produce claim evidence.
- [ ] Do not hard-code live network success in tests. Use fixtures for deterministic CI.

### 9. Documentation And Skill Contract

- [ ] Update `docs/operator/source-backed-strong-closure.md`:
  - Define `SOURCE_BACKED_STRONG`.
  - State that it is not an apply gate.
  - State that default-only surfaces prevent strong.
  - State that decklists/stats/context pages are non-strong unless converted into full-text source claims.
- [ ] Update `docs/operator/universal-wild-no-block-contract.md`:
  - Every valid Wild deck must generate a load-safe package.
  - Partial source status must be diagnostic, not blocking.
  - `first_missing_source_action` is the operator next action.
- [ ] Update `.agents/skills/hsconfig/SKILL.md`:
  - Normal operator command remains `hsconfig configure`.
  - `--online-source` is the preferred source-backed builder path.
  - Strong promotion requires closure; source acquisition alone is insufficient.
  - Darkbishop Benedictus is an effect-only ShadowPriest runtime card unless explicit mulligan text says otherwise.
- [ ] Sync installed skill:
  - `python scripts/sync_installed_skill.py`
  - `python scripts/sync_installed_skill.py --check`
- [ ] Expected check output:
  - `HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig`

### 10. Final Verification

- [ ] Run focused verification:
  - `python -m pytest tests/test_source_backed_strong_harvester_closure.py tests/test_configure_online_source.py tests/test_source_autopilot.py tests/test_source_status_resolver.py tests/test_operator_summary.py tests/test_strong_promotion_report.py tests/test_source_evidence_closure.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_fresh_closure_proof.py tests/test_operator_docs_contract_policy.py -q`
- [ ] Run formatting/check hygiene:
  - `git diff --check`
  - `python scripts/sync_installed_skill.py --check`
- [ ] If the focused test set passes, run the repository default test command if documented in `README.md` or `pyproject.toml`.
- [ ] Final expected focused result:
  - All selected tests pass.
  - `git diff --check` exits 0.
  - Skill sync check exits 0.
  - `operator_summary.json` remains the canonical status surface.
  - No default-only package can claim `SOURCE_BACKED_STRONG`.
  - Every matrix deck remains no-block and load-safe.

## Subagent Execution Split

- [ ] Explorer agent, read-only:
  - Map current source pipeline and identify exact default-only counters already present in reports.
  - Files: `src/hsconfig/source_acquisition.py`, `src/hsconfig/source_autopilot.py`, `src/hsconfig/package_builder.py`, `src/hsconfig/operator_summary.py`.
- [ ] Test agent, write-limited to tests:
  - Add failing tests for source acquisition, no default-only strong, ShadowPriest effect-only Darkbishop, and universal deck no-block.
- [ ] Worker agent, write-limited to source modules:
  - Implement the smallest changes needed to satisfy tests.
  - Do not touch docs or skill files.
- [ ] Docs agent, write-limited to docs and skill:
  - Update operator docs and `.agents/skills/hsconfig/SKILL.md`.
  - Run skill sync after main implementation lands.
- [ ] Reviewer agent, read-only:
  - Review final diff for duplicate status logic, hidden default-only promotion, accidental apply blocking, and ShadowPriest Darkbishop mulligan regression.

## Acceptance Criteria

- [ ] `SOURCE_BACKED_STRONG` is reachable for ShadowPriest from full-text source claims plus static effect semantics.
- [ ] `SOURCE_BACKED_STRONG` is impossible when any runtime surface is default-only.
- [ ] `SOURCE_BACKED_STRONG` is impossible from decklist-only, stats-only, snippet-only, or static-semantics-only strategy evidence.
- [ ] `SW_448` is not held in mulligan by default.
- [ ] `SW_448` effect semantics remain present in runtime config.
- [ ] All twelve provided Wild decks produce validated load-safe packages.
- [ ] Non-strong decks report an actionable `first_missing_source_action`.
- [ ] `operator_summary.json`, `strong_promotion_report.json`, `source_evidence_closure.json`, and `source_bundle.json` agree on source status and first missing action.
- [ ] No new dependency is added.
- [ ] The installed `hsconfig` skill is synced and verified.
