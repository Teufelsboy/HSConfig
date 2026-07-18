# HSConfig Source Contract Partial Closure Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining `SOURCE_BACKED_PARTIAL` Wild deck source gaps where exact full-text evidence exists, preserve explicit partial/stop-condition status where it does not, and produce an honest no-default-only CustomConfig verification matrix without creating a dirty final worktree.

**Architecture:** Keep the current source-contract implementation intact: `hsconfig configure` remains the package builder, `reports/operator_summary.json` remains the only normal apply authority, and `SOURCE_BACKED_STRONG` remains an evidence-quality label. This plan is an evidence and package-validation execution pass, not a broad code rewrite; source candidate pages are fetched and normalized into claims only when they provide deck-matched, claim-kind-specific full text.

**Tech Stack:** Python stdlib, existing HSConfig CLI, pytest, existing `research-deep` outline/results schema, existing `docs/operator` source contracts, Git. No new dependency is allowed.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Start by refreshing repository state:
  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git fetch --all --prune --tags
  git status --short --branch
  git log -1 --oneline
  ```
- Do not push unless the user explicitly asks.
- Do not run live runtime apply. Do not use `--apply`.
- Keep the final worktree clean. If implementation changes are required, commit them at the end after tests pass.
- Preserve `reports/operator_summary.json` as the only normal apply authority.
- Preserve `SOURCE_BACKED_STRONG` as an evidence-quality label, not a generation or apply gate.
- Preserve `source_status_apply_blocking=false` for strong, partial, seed-only, and context-only source states.
- Candidate URLs are acquisition seeds only until fetched, deck-matched, claim-kind-normalized, and surface-gated.
- No `default only` success is allowed: default-only runtime surfaces must be visible diagnostics and must prevent `SOURCE_BACKED_STRONG`.
- `Darkbishop Benedictus` must preserve start-of-game / shadow hero-power-transform effect semantics, but it must not become an opening-hand keep without explicit keep text.
- Use deterministic local fixtures or normalized source JSON for tests. Live online checks are operator verification, not CI requirements.
- Do not commit raw fetched pages, Hearthstone logs, HearthRanger runtime evidence, HDT exports, pytest cache, or private runtime data.

---

## File Structure

- Modify only if exact new source evidence or verified package status changes it: `docs/operator/source-candidate-proof-decks.json`
  - Responsibility: 12-deck candidate/source-gap seed inventory; not runtime authority.
- Modify: `docs/operator/source-backed-strong-closure.md`
  - Responsibility: canonical human-readable closure status, blocker snapshot, and current source actions.
- Modify only if research results are intentionally refreshed: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/*.json`
  - Responsibility: one normalized `research-deep` result per deck.
- Modify only if operator workflow wording is stale after verification: `docs/research/current-truth.md`
  - Responsibility: current research/diagnostic truth and `research-status-sync` boundary.
- Modify only if skill guidance is stale after verification: `.agents/skills/hsconfig/SKILL.md`
  - Responsibility: operator skill instructions for `hsconfig configure`, source strength, and Darkbishop boundary.
- Modify only if tests expose a missing assertion: `tests/test_source_candidate_registry.py`
  - Responsibility: candidate registry ceilings and non-promoting context-only URLs.
- Modify only if tests expose a missing assertion: `tests/test_research_result_contract.py`
  - Responsibility: seed-only, partial, strong, invalid, and downgrade-forbidden research result classification.
- Modify only if tests expose a missing assertion: `tests/test_research_status_sync.py`
  - Responsibility: canonical package status wins over stale or seed-only research snapshots.
- Modify only if tests expose a missing assertion: `tests/test_universal_wild_no_block_matrix.py`
  - Responsibility: every provided Wild deck remains load-safe, non-blocking, and no-default-only honest.
- Modify only if tests expose a missing assertion: `tests/test_shadowpriest_source_contract_acceptance.py`
  - Responsibility: ShadowPriest strong path plus Darkbishop effect-not-keep boundary.

---

### Task 1: Baseline Refresh And Contract Inventory

**Files:**
- Read: `docs/operator/source-backed-strong-closure.md`
- Read: `docs/operator/source-candidate-proof-decks.json`
- Read: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/outline.yaml`
- Read: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/fields.yaml`

**Interfaces:**
- Consumes: current branch, committed source-contract code, source candidate proof set.
- Produces: implementation note listing strong control decks and partial closure decks for Tasks 2-8.

- [ ] **Step 1: Refresh repository state**

  Run:
  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git fetch --all --prune --tags
  git status --short --branch
  git log -1 --oneline
  ```

  Expected:
  ```text
  ## codex/hsconfig-canonical-source-status-sync
  83cdf52 Complete source-backed strong config closure
  ```

  If the commit differs, record the actual commit in implementation notes and continue only after confirming the worktree is clean.

- [ ] **Step 2: Run focused contract baseline**

  Run:
  ```powershell
  python -m pytest tests\test_research_result_contract.py tests\test_research_status_sync.py tests\test_source_candidate_registry.py tests\test_source_candidate_registry_matrix.py tests\test_shadowpriest_source_contract_acceptance.py tests\test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
  ```

  Expected:
  ```text
  56 passed
  ```

  The exact elapsed time may differ. Any failure must be fixed before source evidence work starts.

- [ ] **Step 3: Freeze the execution inventory**

  Read:
  ```powershell
  Get-Content -Raw docs\operator\source-backed-strong-closure.md
  Get-Content -Raw docs\operator\source-candidate-proof-decks.json
  ```

  Expected inventory:
  ```text
  Strong controls: ShadowPriest, PirateRogue, BigShaman, ImbueMage, MechPala
  Closure targets: CtAPaladin, Discolock, TreantDruid, Kingslayer, Boarlock, PirateDH, CuteWarrior
  ```

  Do not change strong-control decks unless a test proves a regression.

- [ ] **Step 4: Confirm research-deep output boundary**

  Run:
  ```powershell
  Get-Content -Raw docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop\outline.yaml
  Get-Content -Raw docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop\fields.yaml
  ```

  Expected:
  - `execution.output_dir` is `./results`.
  - The outline contains exactly the 12 user decks.
  - Fields include `source_strength`, `lowerable_claim_kinds`, `non_promoting_support`, and `first_missing_source_action`.

---

### Task 2: Acquire Current Public Source Evidence Without Promotion

**Files:**
- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/CtAPaladin.json`
- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/Discolock.json`
- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/TreantDruid.json`
- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/Kingslayer.json`
- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/Boarlock.json`
- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/PirateDH.json`
- Modify: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/CuteWarrior.json`
- Read-only control: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/ShadowPriest.json`
- Read-only control: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/PirateRogue.json`
- Read-only control: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/BigShaman.json`
- Read-only control: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/ImbueMage.json`
- Read-only control: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/MechPala.json`

**Interfaces:**
- Consumes: `research-deep` fields schema and live public pages found by web search.
- Produces: refreshed per-deck research JSON records; these records remain diagnostic until `research-status-sync` compares them with package reports.

- [ ] **Step 1: Dispatch read-only source research subagents**

  Use `superpowers:subagent-driven-development` or a read-only research split. Assign one subagent per target group:
  ```text
  Agent A: CtAPaladin, Discolock
  Agent B: TreantDruid, PirateDH
  Agent C: Kingslayer, Boarlock
  Agent D: CuteWarrior
  Main agent: ShadowPriest, PirateRogue, BigShaman, ImbueMage, MechPala controls
  ```

  Each agent must return this exact structure for each deck:
  ```json
  {
    "deck_name": "CtAPaladin",
    "archetype": "Wild CtA Paladin",
    "current_deck_sources": [
      {
        "url": "https://hearthstone-decks.net/wild-decks/paladin-wild-decks/other-paladin-decks-paladin-wild-decks/cta-paladin/",
        "source_family": "current_deck_index",
        "promotes_strong": false
      }
    ],
    "guide_sources": [],
    "source_strength": "decklist_or_stats_only",
    "lowerable_claim_kinds": [],
    "non_promoting_support": [
      "current deck index confirms archetype presence but does not prove mulligan or runtime claims"
    ],
    "first_missing_source_action": "add_explicit_mulligan_source",
    "notes": "Do not promote without fetched full-text mulligan guidance."
  }
  ```

  Replace the deck-specific values with the actual findings. Do not write source results from subagents directly; the main agent writes after review.

- [ ] **Step 2: Verify source strength classification before writing**

  For each candidate page, classify it with this table:
  ```text
  exact_full_text_guide: deck/archetype matched page with explicit guide text and lowerable claims
  archetype_full_text_guide: archetype matched guide text with explicit lowerable claims
  decklist_or_stats_only: current list, rank, score, image, deck code, or stats only
  static_semantics_only: official/deterministic card text semantics only
  missing: no usable public source found
  ```

  Expected:
  - No decklist/stat/currentness page is marked `exact_full_text_guide`.
  - No Reddit or forum snippet is marked strong unless the fetched visible text contains the exact lowerable claim.
  - If a page only confirms currentness, it goes into `non_promoting_support`.

- [ ] **Step 3: Write refreshed research JSON for target decks**

  Update only the seven target result files. Each file must match the fields in `fields.yaml` and include no raw copied article text. Use concise source summaries and URLs.

  Example for a still-partial target:
  ```json
  {
    "deck_name": "Boarlock",
    "archetype": "Wild Elwynn Boar Warlock",
    "current_deck_sources": [
      {
        "url": "https://hearthstone-decks.net/wild-decks/warlock-wild-decks/other-warlock-decks-warlock-wild-decks/elwynn-boar-warlock/",
        "source_family": "current_deck_index",
        "promotes_strong": false
      }
    ],
    "guide_sources": [],
    "source_strength": "decklist_or_stats_only",
    "lowerable_claim_kinds": [],
    "non_promoting_support": [
      "current Boar Warlock list context exists but does not prove Fracking mulligan keep/discard"
    ],
    "first_missing_source_action": "add_mulligan_keep_or_discard_claim_for_WW_092_Fracking",
    "notes": "Preserve explicit stop condition unless exact Boarlock Fracking mulligan text is found."
  }
  ```

- [ ] **Step 4: Validate research result contract**

  Run:
  ```powershell
  python -m pytest tests\test_research_result_contract.py tests\test_research_status_sync.py -q -p no:cacheprovider
  ```

  Expected:
  - Strong-looking but non-lowerable research is non-promoting.
  - Seed-only/context-only snapshots cannot downgrade canonical strong packages.

---

### Task 3: Close Or Preserve Exact Mulligan Evidence Targets

**Files:**
- Modify if evidence changes: `docs/operator/source-backed-strong-closure.md`
- Modify if evidence changes: `docs/operator/source-candidate-proof-decks.json`
- Modify if evidence changes: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/CtAPaladin.json`
- Modify if evidence changes: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/Discolock.json`
- Modify if evidence changes: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/Kingslayer.json`
- Modify if evidence changes: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/Boarlock.json`

**Interfaces:**
- Consumes: Task 2 reviewed source evidence.
- Produces: exact mulligan closure decision for CtAPaladin, Discolock, Kingslayer, and Boarlock.

- [ ] **Step 1: Evaluate CtAPaladin mulligan evidence**

  Required promoting evidence:
  ```text
  Deck/archetype: CtA Paladin / Call to Arms Paladin
  Claim kind: mulligan_keep or mulligan_discard
  Minimum text: explicit keep/discard wording for the named card or exact mulligan policy
  ```

  If found, write:
  ```json
  {
    "source_strength": "exact_full_text_guide",
    "lowerable_claim_kinds": ["mulligan_keep"],
    "first_missing_source_action": "none"
  }
  ```

  If not found, preserve:
  ```json
  {
    "source_strength": "decklist_or_stats_only",
    "lowerable_claim_kinds": [],
    "first_missing_source_action": "add_explicit_mulligan_source"
  }
  ```

- [ ] **Step 2: Evaluate Discolock mulligan evidence**

  Required promoting evidence:
  ```text
  Deck/archetype: Discard Warlock / Discolock
  Claim kind: mulligan_keep or mulligan_discard
  Minimum text: explicit keep/discard wording for discard-engine cards or exact mulligan policy
  ```

  If exact evidence is not present, preserve `SOURCE_BACKED_PARTIAL` and keep the first missing action:
  ```text
  add_explicit_mulligan_source
  ```

- [ ] **Step 3: Evaluate Kingslayer Quick Pick evidence**

  Required promoting evidence:
  ```text
  Deck/archetype: Kingslayer or Kingsbane Rogue
  Card: Quick Pick
  Claim kind: mulligan_keep or mulligan_discard
  Minimum text: exact opening-hand/mulligan keep or discard instruction for Quick Pick
  ```

  If exact evidence is not present, preserve:
  ```text
  SOURCE_BACKED_PARTIAL
  first_missing_source_action=add_mulligan_keep_or_discard_claim
  stop condition=exact_kingslayer_quick_pick_mulligan_source_unavailable
  ```

- [ ] **Step 4: Evaluate Boarlock Fracking evidence**

  Required promoting evidence:
  ```text
  Deck/archetype: Boarlock or Elwynn Boar Warlock
  Card: Fracking
  Claim kind: mulligan_keep or mulligan_discard
  Minimum text: exact opening-hand/mulligan keep or discard instruction for Fracking
  ```

  If exact evidence is not present, preserve:
  ```text
  SOURCE_BACKED_PARTIAL
  first_missing_source_action=add_mulligan_keep_or_discard_claim
  stop condition=exact_boarlock_fracking_mulligan_source_unavailable
  ```

- [ ] **Step 5: Run target decision tests**

  Run:
  ```powershell
  python -m pytest tests\test_kingslayer_quick_pick_source_decision.py tests\test_boarlock_fracking_source_decision.py tests\test_source_candidate_registry.py -q -p no:cacheprovider
  ```

  Expected:
  - Preserved stop conditions remain explicit when exact source evidence is absent.
  - Registry rows remain acquisition seeds only.

---

### Task 4: Close Or Preserve Card-Specific Guide Claim Targets

**Files:**
- Modify if evidence changes: `docs/operator/source-backed-strong-closure.md`
- Modify if evidence changes: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/TreantDruid.json`
- Modify if evidence changes: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/PirateDH.json`
- Modify if evidence changes: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/CuteWarrior.json`

**Interfaces:**
- Consumes: Task 2 source evidence.
- Produces: card-specific closure decisions for TreantDruid, PirateDH, and CuteWarrior.

- [ ] **Step 1: Evaluate TreantDruid card-specific claims**

  Required promoting evidence:
  ```text
  Deck/archetype: Treant Druid
  Claim kind: mulligan_keep, board_flood_setup, gameplan_posture, or card_role
  Minimum text: explicit card-specific role/setup/mulligan wording, not just a decklist
  ```

  If only current list pages or old decklist entries are found, preserve:
  ```text
  SOURCE_BACKED_PARTIAL
  first_missing_source_action=add_card_specific_source_claim
  ```

- [ ] **Step 2: Evaluate PirateDH card-specific claims**

  Required promoting evidence:
  ```text
  Deck/archetype: Pirate Demon Hunter
  Claim kind: mulligan_keep, weapon_pressure, gameplan_posture, or card_role
  Minimum text: explicit role/setup/mulligan wording for the deck's runtime-relevant cards
  ```

  If only current list pages are found, preserve:
  ```text
  SOURCE_BACKED_PARTIAL
  first_missing_source_action=add_card_specific_source_claim
  ```

- [ ] **Step 3: Evaluate CuteWarrior full-text guide availability**

  Required promoting evidence:
  ```text
  Deck/archetype: Cute Warrior
  Claim kind: mulligan_keep, gameplan_posture, or card_role
  Minimum text: current full-text guide or guide-like source with explicit play-pattern claims
  ```

  If only currentness/rank/decklist sources are found, preserve:
  ```text
  SOURCE_BACKED_PARTIAL
  first_missing_source_action=add_current_full_text_mulligan_or_gameplan_source
  ```

- [ ] **Step 4: Run source depth and no-block tests**

  Run:
  ```powershell
  python -m pytest tests\test_guide_source_depth.py tests\test_source_claim_quality_autonomy.py tests\test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
  ```

  Expected:
  - Low-confidence or context-only source remains visible.
  - It does not block config generation.
  - It does not become `SOURCE_BACKED_STRONG`.

---

### Task 5: Generate The 12-Deck Package Matrix Without Apply

**Files:**
- Read/write outside final committed docs only if needed: local package output directory selected during execution.
- Modify if summary changes: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**
- Consumes: updated research and candidate records from Tasks 2-4.
- Produces: package reports for all 12 decks and a closure matrix summary.

- [ ] **Step 1: Create a disposable package output root outside committed docs**

  Run:
  ```powershell
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $outRoot = Join-Path $env:TEMP "hsconfig-source-closure-$stamp"
  New-Item -ItemType Directory -Force -Path $outRoot | Out-Null
  Write-Host $outRoot
  ```

  Expected:
  - `$outRoot` is under the user temp directory.
  - Nothing is written into runtime HearthRanger folders.

- [ ] **Step 2: Run configure for each deck without apply**

  Use this exact deck table:
  ```powershell
  $decks = @(
    @{ Name = "ShadowPriest"; Code = "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" },
    @{ Name = "CtAPaladin"; Code = "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=" },
    @{ Name = "PirateRogue"; Code = "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==" },
    @{ Name = "BigShaman"; Code = "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==" },
    @{ Name = "Discolock"; Code = "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA" },
    @{ Name = "TreantDruid"; Code = "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==" },
    @{ Name = "ImbueMage"; Code = "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=" },
    @{ Name = "MechPala"; Code = "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==" },
    @{ Name = "Kingslayer"; Code = "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=" },
    @{ Name = "Boarlock"; Code = "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA" },
    @{ Name = "PirateDH"; Code = "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==" },
    @{ Name = "CuteWarrior"; Code = "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=" }
  )
  foreach ($deck in $decks) {
    $out = Join-Path $outRoot $deck.Name
    python -m hsconfig configure --deck-name $deck.Name --deck-code $deck.Code --online-source --auto-source --out $out --current-date 2026-07-18
    if ($LASTEXITCODE -ne 0) { throw "configure failed for $($deck.Name)" }
  }
  ```

  Expected:
  - Every deck exits `0`.
  - No command uses `--apply`.
  - Every deck writes `reports/operator_summary.json` under its package directory.

- [ ] **Step 3: Summarize package source status**

  Run:
  ```powershell
  $summary = foreach ($deck in $decks) {
    $operator = Get-Content -Raw (Join-Path $outRoot "$($deck.Name)\reports\operator_summary.json") | ConvertFrom-Json
    [pscustomobject]@{
      deck = $deck.Name
      technical_status = $operator.technical_status
      source_backed_status = $operator.source_backed_status
      first_missing_source_action = $operator.first_missing_source_action
      source_status_apply_blocking = $operator.source_status_apply_blocking
      default_only_runtime_surfaces = ($operator.default_only_runtime_surfaces -join ",")
      next_action = $operator.next_action
    }
  }
  $summary | Format-Table -AutoSize
  ```

  Expected:
  - `technical_status` is `VALID_PACKAGE` for every deck.
  - `source_status_apply_blocking` is `False` for every deck.
  - Strong control decks remain `SOURCE_BACKED_STRONG`.
  - Partial decks either become `SOURCE_BACKED_STRONG` only when exact evidence closed, or remain `SOURCE_BACKED_PARTIAL` with a concrete `first_missing_source_action`.
  - `default_only_runtime_surfaces` is empty for any deck claiming `SOURCE_BACKED_STRONG`.

---

### Task 6: Sync Canonical Closure Documentation

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify if needed: `docs/operator/source-candidate-proof-decks.json`
- Modify if needed: `docs/research/current-truth.md`
- Modify if needed: `.agents/skills/hsconfig/SKILL.md`

**Interfaces:**
- Consumes: Task 5 package summary.
- Produces: current human-readable closure status and operator instructions.

- [ ] **Step 1: Update Current Blocker Snapshot**

  In `docs/operator/source-backed-strong-closure.md`, update only the `## Current Blocker Snapshot` table. Use this exact status rule:
  ```text
  SOURCE_BACKED_STRONG only when operator_summary.json says SOURCE_BACKED_STRONG and default_only_runtime_surfaces is empty.
  SOURCE_BACKED_PARTIAL when any first missing source action remains.
  ```

  Preserve explicit stop-condition language for:
  ```text
  Kingslayer Quick Pick
  Boarlock Fracking
  ```

- [ ] **Step 2: Update source candidate proof set only for proven source changes**

  If Task 2 found new stable source candidates, add them to `docs/operator/source-candidate-proof-decks.json` with one of these ceilings:
  ```json
  {
    "expected_strength_ceiling": "runtime_claims_possible"
  }
  ```
  or:
  ```json
  {
    "expected_strength_ceiling": "candidate_partial"
  }
  ```
  or:
  ```json
  {
    "expected_strength_ceiling": "context_only"
  }
  ```

  Do not change `expected_strong_promotion_status` to strong unless a package report proved strong closure.

- [ ] **Step 3: Update operator current truth if wording changed**

  In `docs/research/current-truth.md`, ensure these statements remain present:
  ```text
  research-status-sync is diagnostic only.
  Seed-only snapshots do not promote or downgrade canonical package status.
  SOURCE_BACKED_STRONG is not an apply gate.
  ```

- [ ] **Step 4: Update skill guidance if operator path changed**

  In `.agents/skills/hsconfig/SKILL.md`, ensure these statements remain present:
  ```text
  Use hsconfig configure for normal package generation.
  Do not treat source candidate URLs as promotion authority.
  Darkbishop Benedictus effect matters, but the physical card is not a mulligan keep without explicit source text.
  ```

- [ ] **Step 5: Run docs and skill sync tests**

  Run:
  ```powershell
  python -m pytest tests\test_docs_active_path.py tests\test_research_current_truth.py tests\test_skill_sync.py tests\test_skill_files.py -q -p no:cacheprovider
  ```

  Expected:
  - Docs continue to name `operator_summary.json` as normal apply authority.
  - Skill docs continue to prefer `hsconfig configure`.

---

### Task 7: Run Acceptance Matrix And Contract Tests

**Files:**
- Test: `tests/test_research_result_contract.py`
- Test: `tests/test_research_status_sync.py`
- Test: `tests/test_source_candidate_registry.py`
- Test: `tests/test_source_candidate_registry_matrix.py`
- Test: `tests/test_shadowpriest_source_contract_acceptance.py`
- Test: `tests/test_universal_wild_no_block_matrix.py`
- Test: `tests/test_acceptance_matrix.py`
- Test: `tests/test_configure_online_source.py`

**Interfaces:**
- Consumes: documentation and source-result updates from Tasks 2-6.
- Produces: green focused test suite and acceptance proof.

- [ ] **Step 1: Run focused source-contract suite**

  Run:
  ```powershell
  python -m pytest tests\test_research_result_contract.py tests\test_research_status_sync.py tests\test_source_candidate_registry.py tests\test_source_candidate_registry_matrix.py tests\test_shadowpriest_source_contract_acceptance.py tests\test_universal_wild_no_block_matrix.py tests\test_acceptance_matrix.py tests\test_configure_online_source.py -q -p no:cacheprovider
  ```

  Expected:
  - All tests pass.
  - No live network is required.

- [ ] **Step 2: Run acceptance matrix CLI**

  Run:
  ```powershell
  python -m hsconfig acceptance-matrix --json
  ```

  Expected:
  - Command exits `0`.
  - Matrix reports the representative deck statuses without converting source partiality into apply blocking.

- [ ] **Step 3: Verify no default-only strong package**

  Run:
  ```powershell
  python -m pytest tests\test_universal_wild_no_block_matrix.py::test_universal_wild_matrix_has_no_default_only_strong_success -q -p no:cacheprovider
  ```

  Expected:
  - Test passes, or if this exact test name does not exist, add the narrow assertion to `tests/test_universal_wild_no_block_matrix.py` and rerun the file.

---

### Task 8: Full Verification, Cleanup, And Commit

**Files:**
- Review: all changed files from `git diff --name-only`

**Interfaces:**
- Consumes: all task outputs.
- Produces: passing test suite and clean committed branch.

- [ ] **Step 1: Run full test suite**

  Run:
  ```powershell
  python -m pytest -q -p no:cacheprovider
  ```

  Expected:
  ```text
  passed
  ```

  Skips are acceptable only if they are existing environment skips.

- [ ] **Step 2: Remove transient artifacts**

  Run:
  ```powershell
  git status --short
  Get-ChildItem -Recurse -Force -Directory -Filter ".pytest_cache" | ForEach-Object { Remove-Item -Recurse -Force -LiteralPath $_.FullName }
  Get-ChildItem -Recurse -Force -Directory -Filter "__pycache__" | ForEach-Object { Remove-Item -Recurse -Force -LiteralPath $_.FullName }
  git status --short
  ```

  Expected:
  - No cache directories remain as tracked/untracked changes.
  - Only intentional docs/research/test/source files are listed.

- [ ] **Step 3: Review diff**

  Run:
  ```powershell
  git diff -- docs src tests .agents
  ```

  Expected:
  - No raw fetched HTML pages.
  - No Hearthstone/HearthRanger/HDT runtime evidence.
  - No `--apply` output.
  - No broad architecture rewrite.
  - All remaining changes map to Tasks 2-7.

- [ ] **Step 4: Commit intentional changes**

  Run:
  ```powershell
  git add docs src tests .agents
  git commit -m "Close source contract partial deck matrix"
  git status --short --branch
  ```

  Expected:
  - Commit succeeds.
  - Final status is clean.

---

## Subagent Assignment

- **Subagent A - Mulligan Evidence Research:** Task 3 for CtAPaladin and Discolock.
- **Subagent B - Stop-Condition Evidence Research:** Task 3 for Kingslayer and Boarlock.
- **Subagent C - Card-Specific Evidence Research:** Task 4 for TreantDruid and PirateDH.
- **Subagent D - Currentness And CuteWarrior Research:** Task 4 for CuteWarrior and current Wild context pages.
- **Main Agent:** Tasks 1, 2 review/write, Task 5 package matrix, Task 6 docs sync, Task 7 tests, Task 8 cleanup/commit.

Only the main agent writes files. Subagents provide evidence summaries, URLs, claim-kind classification, and recommended `first_missing_source_action` values.

## Self-Review

- Spec coverage: The plan covers current repo refresh, no dirty final state, no live apply, no default-only strong promotion, source-candidate non-authority, research-deep result handling, 12-deck online source cross-check, package matrix validation, and commit cleanup.
- Placeholder scan: No forbidden placeholder markers or unspecified deferred-work step is present.
- Interface consistency: `operator_summary.json`, `source_backed_status`, `first_missing_source_action`, `source_status_apply_blocking`, and `default_only_runtime_surfaces` are used consistently across tasks.
