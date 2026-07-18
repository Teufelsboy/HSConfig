# HSConfig Live Source Closure Priority Queue v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the next real online-source opportunity into an honest runtime-facing source closure without weakening any gate: no default-only runtime surface, no apply-time block, no false `SOURCE_BACKED_STRONG`, and no dirty worktree at handoff.

**Architecture:** Keep the existing HSConfig source contract as the single authority. The source candidate registry proposes evidence, the online-source fetch/extractor creates typed claims, the contract layer classifies runtime readiness, and operator docs report the first missing source action. The implementation must add only narrowly verified candidates or extractor support. It must not add manual overrides, default promotions, or wording-based status shortcuts.

**Tech Stack:** Python, pytest, HSConfig CLI, PowerShell, Git, existing online-source fetch/extract pipeline.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Refresh remotes before implementation and before final verification.
- Do not run runtime apply/write commands. `configure --online-source` must write only package output folders.
- Do not commit generated package output, caches, logs, runtime evidence, or temporary research artifacts.
- Do not relax `SOURCE_BACKED_STRONG`; a deck becomes strong only when typed source claims close the runtime contract.
- Do not introduce default-only behavior. `default_only_runtime_surfaces` must remain empty for generated packages.
- Preserve the ShadowPriest Darkbishop boundary: keep the `hero_power_transform` effect contract, but do not create or reintroduce an opening-hand keep for Darkbishop Benedictus.
- Use exact, traceable source URLs. Decklist-only pages can support identity and recency, but only pages with explicit strategy/mulligan text can support runtime claims.
- End with `git status --short --branch` clean.

## Current Source Anchors

- ShadowPriest strong canary: `https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest`
  - Current deck guide dated May 3, 2026.
  - Provides archetype, gameplan, hero-power usage, explicit keep list, and explicit discard rule for 4+ cost cards.
- BigShaman priority candidate: `https://hearthstone-decks.net/big-shaman-202-legend-abadon-score-98-64/`
  - Current Wild Legend Big Shaman page dated December 31, 2025 with visible related Wild context in July 2026.
  - Provides the Big Shaman archetype, Y'Shaarj variant context, score/rank context, and explicit initial mulligan card names.
- Wild meta discovery surface: `https://hearthstone-decks.net/wild-deck/`
  - Use only as an index and freshness surface, not as a standalone runtime claim source.
- Existing BigShaman support seed: `https://www.hearthpwn.com/decks/1186371-big-shaman-in-depth-guide`
  - Keep as old support context unless the current source closes all typed claims.

## File Structure

Files expected to change:

- `src/hsconfig/source_candidate_registry.py`
- `docs/operator/source-candidate-proof-decks.json`
- `tests/test_source_candidate_registry_matrix.py`

Files that may change only if tests prove an extractor gap:

- `src/hsconfig/source_text_claim_extractor.py`
- `tests/test_source_text_claim_extractor.py`
- `tests/test_configure_online_source.py`

Files expected to be read-only verification targets:

- `src/hsconfig/source_document_model.py`
- `src/hsconfig/contract.py`
- `src/hsconfig/source_closure_optimizer.py`
- `tests/test_claim_kind_runtime_contract.py`
- `tests/test_source_closure_optimizer.py`
- `tests/test_universal_wild_no_block_matrix.py`
- `tests/test_shadowpriest_e2e.py`
- `.agents/skills/hsconfig/SKILL.md`

Generated artifacts must stay ignored or untracked:

- `outputs/2026-07-18-live-source-closure-priority-v3/`
- `tmp/2026-07-18-live-source-closure-priority-v3/`

---

## Task 1: Refresh Baseline And Capture Starting Contract State

**Files:** read-only repo state and tests.

**Purpose:** Prove the branch is current enough for implementation, the starting worktree is clean, and the existing source contract tests are not already failing.

**Steps:**

- [ ] Run:

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git fetch --all --prune --tags
  git rev-list --left-right --count HEAD...origin/main
  git status --short --branch
  python -m pytest tests/test_source_candidate_registry_matrix.py tests/test_claim_kind_runtime_contract.py tests/test_source_closure_optimizer.py -q
  ```

- [ ] Confirm `git status --short --branch` contains no tracked or untracked file changes before edits.
- [ ] Record the ahead/behind tuple from `git rev-list --left-right --count HEAD...origin/main` in the implementation notes.
- [ ] If baseline tests fail, stop edits and diagnose the failing test before changing source behavior.

**Expected output:**

- `git status --short --branch` shows a clean branch line only.
- Pytest exits with code `0`.

---

## Task 2: Add BigShaman Current Source Candidate With Registry Matrix Coverage

**Files:**

- `src/hsconfig/source_candidate_registry.py`
- `docs/operator/source-candidate-proof-decks.json`
- `tests/test_source_candidate_registry_matrix.py`

**Purpose:** Register the current BigShaman page as the first candidate source because it has explicit initial mulligan card names and current Wild context. Keep the old HearthPwn guide as support context.

**Interfaces:**

- Add a `SourceCandidate` for BigShaman with:
  - `url="https://hearthstone-decks.net/big-shaman-202-legend-abadon-score-98-64/"`
  - `source_family="decklist_with_strategy"`
  - `deck_name="BigShaman"`
  - `archetype="wild_big_shaman"`
  - `priority=10`
  - `expected_strength="current_legend_mulligan_source"`
  - `format_scope="wild"`
  - `publication_year=2025`
  - `source_visibility="full_text"`
  - `strength_ceiling="runtime_claims_possible"`
  - `expected_claim_kinds=("archetype", "gameplan_posture", "mulligan_keep")`
  - `first_missing_source_action="none"`
- Keep `https://www.hearthpwn.com/decks/1186371-big-shaman-in-depth-guide` as a second BigShaman candidate or support seed with `strength_ceiling="candidate_partial"`.
- Update `docs/operator/source-candidate-proof-decks.json` so the generated proof row matches registry order and fields.
- Update `tests/test_source_candidate_registry_matrix.py` so BigShaman expected strength and strong-promotion status reflect runtime-claim possibility, not automatic strength.

**Steps:**

- [ ] Add a failing matrix test named `test_live_source_priority_queue_registers_current_bigshaman_mulligan_source`.
- [ ] Assert the first BigShaman candidate URL is the Hearthstone-Decks Big Shaman page.
- [ ] Assert the first BigShaman candidate has `strength_ceiling == "runtime_claims_possible"`.
- [ ] Assert the old HearthPwn Big Shaman guide remains present as lower-priority support.
- [ ] Implement the registry and proof-doc changes.
- [ ] Run:

  ```powershell
  python -m pytest tests/test_source_candidate_registry_matrix.py -q
  ```

**Expected output:**

- The new test fails before registry edits.
- The matrix test passes after registry and proof-doc edits.
- The proof JSON exactly mirrors the registry; no hand-written divergence remains.

---

## Task 3: Generate BigShaman Online-Source Package Without Runtime Apply

**Files:** generated output only, plus read-only inspection of package summaries.

**Purpose:** Determine whether the new source naturally closes BigShaman to `SOURCE_BACKED_STRONG` or exposes a precise extractor/claim gap.

**Command:**

```powershell
cd C:\Users\darbo\Documents\HSConfig
$out = "outputs/2026-07-18-live-source-closure-priority-v3/BigShaman"
$runtime = "tmp/2026-07-18-live-source-closure-priority-v3/runtime/BigShaman"
Remove-Item -Recurse -Force $out,$runtime -ErrorAction SilentlyContinue
python -m hsconfig configure `
  --deck-name BigShaman `
  --deck-code "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==" `
  --out $out `
  --runtime-root $runtime `
  --online-source `
  --source-fetch-timeout-seconds 10 `
  --current-date 2026-07-18 `
  --json
```

**Steps:**

- [ ] Inspect the JSON result and `operator_summary.json`.
- [ ] Confirm `technical_status == "VALID_PACKAGE"`.
- [ ] Confirm `source_status_apply_blocking == false`.
- [ ] Confirm `default_only_runtime_surfaces == []`.
- [ ] Record `source_backed_status`.
- [ ] Record `first_missing_source_action`.
- [ ] Record the first missing claim chain if `source_backed_status` is not `SOURCE_BACKED_STRONG`.

**Expected output:**

- Package generation succeeds.
- No runtime apply/write occurs.
- If BigShaman is strong, the evidence is typed claim closure from fetched source text.
- If BigShaman is partial, the next action names the exact missing claim type or extractor miss.

---

## Task 4: Patch Extractor Only If The Current BigShaman Text Is Missed

**Files:**

- `src/hsconfig/source_text_claim_extractor.py`
- `tests/test_source_text_claim_extractor.py`
- `tests/test_configure_online_source.py`

**Purpose:** Fix only a real extraction miss. Do not add deck-specific hardcoded claims or status overrides.

**Entry condition:** Execute this task only when Task 3 proves that the source page text contains explicit BigShaman mulligan names but the extractor does not emit corresponding typed `mulligan_keep` claims.

**Test case:**

- Use a small fixture text containing the BigShaman page concepts:
  - archetype: Big Shaman
  - explicit initial mulligan names: Ancestor's Call, Scalding Geyser, Fairy Tale Forest, Auctionhouse Gavel
  - Y'Shaarj version context

**Steps:**

- [ ] Add a failing extractor test named `test_extracts_initial_mulligan_sentence_from_submitted_deck_source`.
- [ ] Assert typed `mulligan_keep` claims exist for the four named cards.
- [ ] Assert the claim source URL is preserved.
- [ ] Implement the narrowest parser change for "initial mulligan" phrasing.
- [ ] Run:

  ```powershell
  python -m pytest tests/test_source_text_claim_extractor.py tests/test_configure_online_source.py -q
  ```

**Expected output:**

- The new extractor test fails before the extractor patch.
- The test passes after a source-text parsing change.
- No BigShaman-specific hardcoded runtime output is added.

---

## Task 5: Re-Generate BigShaman And Run Closure Diagnostics

**Files:** generated output only, read-only diagnostics.

**Purpose:** Re-run the source closure after registry or extractor changes and preserve honesty if strong closure is not reached.

**Commands:**

```powershell
python -m hsconfig configure `
  --deck-name BigShaman `
  --deck-code "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==" `
  --out "outputs/2026-07-18-live-source-closure-priority-v3/BigShaman" `
  --runtime-root "tmp/2026-07-18-live-source-closure-priority-v3/runtime/BigShaman" `
  --online-source `
  --source-fetch-timeout-seconds 10 `
  --current-date 2026-07-18 `
  --json

python -m hsconfig source-closure-optimizer `
  --package-dir "outputs/2026-07-18-live-source-closure-priority-v3/BigShaman" `
  --json
```

**Steps:**

- [ ] Confirm the generated package remains `VALID_PACKAGE`.
- [ ] Confirm no default-only runtime surface appears.
- [ ] Confirm no apply block appears.
- [ ] If `SOURCE_BACKED_STRONG` is reached, record the exact typed claim kinds that closed the contract.
- [ ] If not strong, record the exact first missing source action and do not promote the deck.

**Expected output:**

- Either BigShaman reaches `SOURCE_BACKED_STRONG` from typed online claims, or it remains honestly partial with a precise next missing source action.

---

## Task 6: Rebuild All Requested Wild Deck Packages As No-Apply Matrix

**Files:** generated output only, read-only result matrix.

**Purpose:** Prove the plan does not regress the universal Wild no-block contract and does not turn unsupported decks into default-only packages.

**Deck matrix:**

- ShadowPriest: `AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=`
- CtAPaladin: `AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=`
- PirateRogue: `AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==`
- BigShaman: `AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==`
- Discolock: `AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA`
- TreantDruid: `AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==`
- ImbueMage: `AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=`
- MechPala: `AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==`
- Kingslayer: `AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=`
- Boarlock: `AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA`
- PirateDH: `AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==`
- CuteWarrior: `AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=`

**Steps:**

- [ ] Generate each package with `python -m hsconfig configure --online-source --source-fetch-timeout-seconds 10 --current-date 2026-07-18 --json`.
- [ ] Use output folders under `outputs/2026-07-18-live-source-closure-priority-v3/<DeckName>`.
- [ ] Use runtime roots under `tmp/2026-07-18-live-source-closure-priority-v3/runtime/<DeckName>`.
- [ ] Build a compact matrix with columns:
  - deck_name
  - technical_status
  - source_backed_status
  - source_status_apply_blocking
  - default_only_runtime_surfaces
  - first_missing_source_action
- [ ] Confirm ShadowPriest remains strong and keeps Darkbishop as effect-only.
- [ ] Confirm decks without enough source evidence remain partial with explicit source actions.

**Expected output:**

- All twelve packages generate with `VALID_PACKAGE`.
- All twelve have `source_status_apply_blocking == false`.
- All twelve have `default_only_runtime_surfaces == []`.
- No deck is promoted to `SOURCE_BACKED_STRONG` without typed source closure.

---

## Task 7: Focused Test Suite, Diff Review, And Clean Handoff

**Files:** all changed files and test surfaces.

**Purpose:** Prove the tracked code/doc changes are consistent, no generated files are staged, and the final worktree is clean.

**Commands:**

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_candidate_registry_matrix.py tests/test_configure_online_source.py tests/test_source_text_claim_extractor.py tests/test_claim_kind_runtime_contract.py tests/test_source_closure_optimizer.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_e2e.py -q
python -m pytest tests/test_operator_docs_contract_policy.py tests/test_skill_files.py -q
git diff --check
git status --short --branch
```

**Steps:**

- [ ] Review `git diff -- src/hsconfig/source_candidate_registry.py docs/operator/source-candidate-proof-decks.json tests/test_source_candidate_registry_matrix.py`.
- [ ] Review extractor diffs only if Task 4 changed extractor code.
- [ ] Confirm generated output and temp folders are not staged.
- [ ] Commit only intentional tracked source, proof, test, and plan changes.
- [ ] Run:

  ```powershell
  git status --short --branch
  git log -1 --oneline
  ```

**Expected output:**

- All focused pytest commands pass.
- `git diff --check` exits with code `0`.
- Final `git status --short --branch` is clean.
- The final commit contains no generated package output, cache, log, or runtime evidence.

---

## Subagent-Driven Execution Strategy

Use `superpowers:subagent-driven-development` for the implementation phase.

- **Source Candidate Auditor:** Read-only. Inspect registry, proof JSON, and current online source anchors. Report exact registry/proof/test edits required.
- **BigShaman Package Inspector:** Read-only. Run or inspect generated BigShaman package output and report source status, missing claims, and default-only surfaces.
- **ShadowPriest Canary Reviewer:** Read-only. Verify Darkbishop Benedictus remains effect-only and ShadowPriest does not regain a mistaken mulligan keep.
- **Final Reviewer:** Read-only. Review final diff, generated-artifact hygiene, and verification output before commit.
- **Main Agent:** Performs all edits and the final commit. No subagent writes to tracked files.

## Acceptance Criteria

- Repository state was refreshed with `git fetch --all --prune --tags`.
- No runtime apply/write command was run.
- No generated output, logs, cache, runtime evidence, or temp package artifacts are committed.
- BigShaman has the current Hearthstone-Decks source registered before stale support sources.
- BigShaman reaches `SOURCE_BACKED_STRONG` only if typed claims close the runtime contract.
- ShadowPriest remains the strong canary and preserves Darkbishop Benedictus as effect-only, not mulligan-keep.
- Every generated deck package remains non-blocking and non-default-only.
- Final worktree is clean.

## Implementation Notes Template

Record these values during execution:

```text
start_ahead_behind=
baseline_tests=
bigshaman_source_backed_status=
bigshaman_first_missing_source_action=
bigshaman_default_only_runtime_surfaces=
shadowpriest_darkbishop_runtime_claim=
all_decks_valid_package_count=
all_decks_default_only_count=
all_decks_apply_block_count=
focused_tests=
final_commit=
final_status=
```

## Self-Review Checklist

- [ ] The plan starts from current repo state and does not assume remote state.
- [ ] The plan contains exact source URLs and exact deck codes.
- [ ] The plan keeps `SOURCE_BACKED_STRONG` strict.
- [ ] The plan includes tests before implementation changes.
- [ ] The plan has a no-apply package verification path.
- [ ] The plan includes a full twelve-deck no-block matrix.
- [ ] The plan protects the clean-worktree requirement.
