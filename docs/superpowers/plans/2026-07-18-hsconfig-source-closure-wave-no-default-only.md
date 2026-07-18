# HSConfig Source Closure Wave No Default Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use read-only subagents for source audit, package matrix audit, ShadowPriest contract audit, and final review. The main agent owns all tracked writes and all commits.

**Goal:** Execute the next HSConfig source-closure wave for the supplied Wild decks so every generated CustomConfig is load-safe, no deck succeeds through hidden default-only runtime surfaces, ShadowPriest remains honestly `SOURCE_BACKED_STRONG`, and every other deck is promoted only when current full-text source claims truly close the contract.

**Architecture:** Keep the existing canonical resolver and apply boundary intact. Use `src/hsconfig/source_candidate_registry.py` and `docs/operator/source-candidate-proof-decks.json` as acquisition-seed surfaces, then use the existing `hsconfig configure --online-source`, `research-status-sync`, `strong-closure-dossier`, and `source-closure-optimizer` commands to prove package status. Do not create a new apply gate, do not make candidate URLs promotion authority, and do not force `SOURCE_BACKED_STRONG` when the fetched source chain is incomplete.

**Tech Stack:** Python, pytest, existing HSConfig CLI, existing source acquisition/autopilot pipeline, existing operator reports, PowerShell on Windows, current public web source checks.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Start with `git fetch --all --prune --tags`, `git remote prune origin`, branch divergence check, matching-branch check, and a clean worktree check.
- End with `git status --short --branch` showing no uncommitted tracked changes.
- Do not run destructive git commands. Do not delete local-only branches.
- Do not push unless the user explicitly asks to push.
- Do not apply generated packages to HearthRanger runtime in this plan.
- Generated packages must stay under ignored `outputs/2026-07-18-source-closure-wave-no-default-only/`.
- Generated diagnostics must stay under ignored `tmp/2026-07-18-source-closure-wave-no-default-only/`.
- `reports/operator_summary.json` remains the only normal apply authority.
- `source_evidence_closure.json`, `strong_closure_dossier`, `source_closure_optimizer`, decklist pages, and source-candidate URLs remain diagnostic or acquisition artifacts only.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation gate and not an apply gate.
- `source_status_apply_blocking` must remain `false` for source-depth gaps.
- `default_only_runtime_surfaces` must be visible, must prevent `SOURCE_BACKED_STRONG`, and must not by itself block valid load-safe package generation.
- Context-only sources, decklist-only sources, category pages, and snippets must not promote a deck to `SOURCE_BACKED_STRONG`.
- ShadowPriest must preserve Darkbishop Benedictus / `SW_448` start-of-game hero-power-transform semantics while keeping `SW_448` out of opening-hand `Mulligan.json` unless an explicit opening-hand mulligan source says to keep the card.
- Keep `Presume.json` and `Concede.json` outside normal generated HSConfig packages.

---

## File Structure

- Read: `AGENTS.md`
  - Repo-local authority for workspace, freshness, and no-HSTuner boundary.
- Read: `src/hsconfig/source_candidate_registry.py`
  - Current source acquisition seed registry and source strength ceilings.
- Read or modify if live audit proves a better candidate: `docs/operator/source-candidate-proof-decks.json`
  - Human-visible proof manifest that must match the registry.
- Modify if registry/proof changes: `tests/test_source_candidate_registry_matrix.py`
  - Locks candidate URLs, strength ceilings, first missing actions, and context-only behavior.
- Read or modify only for a proven parser/contract defect: `src/hsconfig/source_text_claim_extractor.py`
  - Full-text source claim extraction.
- Read or modify only for a proven contract modeling defect: `src/hsconfig/source_document_model.py`
  - Source document and claim-kind normalization boundary.
- Read or modify only for a proven runtime lowering defect: `src/hsconfig/card_behavior_router.py`, `src/hsconfig/compile_mulligan.py`
  - Runtime lowering and mulligan emission boundaries.
- Verify: `tests/test_claim_kind_runtime_contract.py`
  - Claim-kind to runtime-surface contract, including start-of-game/effect semantics.
- Verify: `tests/test_configure_online_source.py`, `tests/test_configure_auto_source.py`
  - Online-source and auto-source package paths.
- Verify: `tests/test_universal_wild_no_block_matrix.py`
  - 12-deck no-block/default-only matrix.
- Verify: `tests/test_shadowpriest_e2e.py`
  - ShadowPriest package, Darkbishop effect, and no false mulligan keep.
- Generated ignored packages:
  - `outputs/2026-07-18-source-closure-wave-no-default-only/ShadowPriest/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/CtAPaladin/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/PirateRogue/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/BigShaman/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/Discolock/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/TreantDruid/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/ImbueMage/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/MechPala/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/Kingslayer/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/Boarlock/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/PirateDH/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/CuteWarrior/`
- Generated ignored diagnostics: `tmp/2026-07-18-source-closure-wave-no-default-only/`

---

### Task 1: Refresh Repository State And Prove Safe Baseline

**Files:**
- Read-only: git metadata
- Read-only: `AGENTS.md`
- Read-only: `docs/operator/source-candidate-proof-decks.json`
- Read-only: `src/hsconfig/source_candidate_registry.py`

**Interfaces:**
- Consumes: current branch, origin refs, current worktree.
- Produces: current, non-destructive baseline before any source or package work.

- [ ] **Step 1: Refresh remotes and prune stale remote refs**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git fetch --all --prune --tags
git remote prune origin
```

Expected: both commands exit `0`.

- [ ] **Step 2: Verify the tracked worktree starts clean**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
```

Expected: only the branch header, for example:

```text
## codex/hsconfig-canonical-source-status-sync
```

If any tracked file appears, run `git diff --stat` and stop before changing files unless the file is explicitly owned by this plan.

- [ ] **Step 3: Verify branch is not behind `origin/main`**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git rev-list --left-right --count HEAD...origin/main
```

Expected: the second number is `0`. The first number may be greater than `0` because the current plan branch can be ahead of `origin/main`.

- [ ] **Step 4: Inspect local branches with matching remote refs**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git for-each-ref --format='%(refname:short) %(upstream:short) %(objectname:short) %(upstream:track)' refs/heads
```

Expected: no branch with a matching upstream is behind. If a matching branch is behind and clean, fast-forward it only when this can be done without checking out over dirty files. Do not delete local-only branches.

- [ ] **Step 5: Confirm current source registry/proof tests pass before changes**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_candidate_registry_matrix.py -q
```

Expected:

```text
7 passed
```

---

### Task 2: Run Read-Only Current Source Audit Before Editing

**Files:**
- Read: `src/hsconfig/source_candidate_registry.py`
- Read: `docs/operator/source-candidate-proof-decks.json`
- Read: `tests/test_source_candidate_registry_matrix.py`

**Interfaces:**
- Consumes: current public web pages and existing source candidates.
- Produces: source-audit verdict with exact update actions, or a no-change verdict.

- [ ] **Step 1: Dispatch a read-only source audit subagent**

Dispatch one read-only subagent with this exact brief:

```text
Work in C:\Users\darbo\Documents\HSConfig. Read src/hsconfig/source_candidate_registry.py, docs/operator/source-candidate-proof-decks.json, and tests/test_source_candidate_registry_matrix.py. Use current public web checks for the 12 supplied Wild decks. Do not write files. Report only:
1. Dead or unusable registered candidate URLs.
2. Better current full-text guide URLs that should replace or supplement existing candidates.
3. Candidates that must remain context_only or candidate_partial.
4. Decks where runtime_claims_possible is plausible only after fetched full-text claims close the chain.
Respect: candidate URLs are acquisition seeds only; decklist/category pages cannot promote SOURCE_BACKED_STRONG.
```

Expected: compact deck-by-deck source verdict. No files changed by the subagent.

- [ ] **Step 2: Verify the known current high-value source candidates**

The audit must explicitly classify these URLs:

```text
ShadowPriest:
https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest

CtAPaladin:
https://www.reddit.com/r/wildhearthstone/comments/1u0kd33/any_help_with_cta_paladin_mulligan/
https://www.reddit.com/r/wildhearthstone/comments/1jydz4q/i_dont_understand_how_cta_paladin_is_any_good/

Discolock:
https://www.reddit.com/r/CompetitiveHS/comments/1s7nr67/easy_wild_legend_discolock/
https://www.reddit.com/r/wildhearthstone/comments/1nhpuu1/how_to_play_discolock/

TreantDruid:
https://www.reddit.com/r/wildhearthstone/comments/1mjge7n/treant_druid_to_early_legend/
https://www.reddit.com/r/CompetitiveHS/comments/1oty3l8/treant_druid_wild_legend_deck/

ImbueMage:
https://www.hearthpwn.com/decks/1462266-wild-imbue-mage

PirateDH:
https://hs.cardsrealm.com/en-bz/articles/hearthstone-wild-deck-guide-pirate-demon-hunter-become-a-legend

BigShaman:
https://www.hearthpwn.com/decks/1186371-big-shaman-in-depth-guide
```

Expected: keep these candidates unless current web evidence shows the URL is unusable or the strength ceiling is overstated.

- [ ] **Step 3: Preserve strict source strength ceilings**

Use this classification table for any source change:

```text
runtime_claims_possible:
  Source is full text or guide-like enough that fetched claims may close mulligan_keep, mulligan_discard, gameplan_posture, card_role, combo_sequence, mechanic_usage, targeting_rule, or hero_power_transform.

candidate_partial:
  Source supports context or some claim kinds, but a named first_missing_source_action remains.

context_only:
  Decklist, meta index, category page, or low-prose page. expected_claim_kinds must be empty and first_missing_source_action must not be none.
```

Expected: no context-only URL has `expected_claim_kinds` and no context-only URL uses `first_missing_source_action="none"`.

---

### Task 3: Update Candidate Registry Only For Proven Current Source Changes

**Files:**
- Modify if needed: `src/hsconfig/source_candidate_registry.py`
- Modify if needed: `docs/operator/source-candidate-proof-decks.json`
- Modify if needed: `tests/test_source_candidate_registry_matrix.py`

**Interfaces:**
- Consumes: source audit verdict from Task 2.
- Produces: registry/proof/test updates that stay aligned.

- [ ] **Step 1: If the audit reports no candidate changes, skip this task**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff -- src/hsconfig/source_candidate_registry.py docs/operator/source-candidate-proof-decks.json tests/test_source_candidate_registry_matrix.py
```

Expected if no candidate changes are needed: no output.

- [ ] **Step 2: If a candidate is added, write the failing registry test first**

For every new candidate URL, add or update a test in `tests/test_source_candidate_registry_matrix.py` using exact URL, deck, strength, and action strings from the completed source-audit verdict. Do not use templated values in the committed test.

For a CtAPaladin support-seed refresh, the test body must look like this:

```python
def test_source_closure_wave_cta_support_seed_is_registered():
    candidates = {
        candidate.url: candidate
        for candidate in source_candidates_for_deck("CtAPaladin")
    }
    url = (
        "https://www.reddit.com/r/wildhearthstone/comments/1qdrc06/"
        "the_xl_cta_paladin_experience/"
    )
    assert url in candidates
    assert candidates[url].strength_ceiling == "candidate_partial"
    assert candidates[url].first_missing_source_action == (
        "add_current_cta_paladin_mulligan_keep_source"
    )
```

Expected before implementation: the new assertion fails because the candidate is not registered or the strength/action is wrong.

- [ ] **Step 3: Run the failing candidate test**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_candidate_registry_matrix.py::test_source_closure_wave_cta_support_seed_is_registered -q
```

Expected before registry update: fail on the missing or misclassified URL.

- [ ] **Step 4: Update the registry and proof doc together**

In `src/hsconfig/source_candidate_registry.py`, add a `SourceCandidate` row with all fields populated. For the CtAPaladin support-seed example above, the row must be:

```python
SourceCandidate(
    url="https://www.reddit.com/r/wildhearthstone/comments/1qdrc06/the_xl_cta_paladin_experience/",
    source_family="community_guide",
    deck_name="CtAPaladin",
    archetype="wild_cta_paladin",
    reason=(
        "current Wild CtA Paladin posture support without enough "
        "card-specific mulligan closure to promote by itself"
    ),
    priority=7,
    expected_strength="guide_current_archetype_partial",
    publication_year=2026,
    strength_ceiling="candidate_partial",
    expected_claim_kinds=("gameplan_posture", "card_role"),
    first_missing_source_action="add_current_cta_paladin_mulligan_keep_source",
)
```

In `docs/operator/source-candidate-proof-decks.json`, put the same URL in exactly one of:

```json
"candidate_urls": []
"support_seed_urls": []
"context_seed_urls": []
```

Expected: proof doc order matches the registry order returned by `source_candidates_for_deck(...)`.

- [ ] **Step 5: Run registry/proof tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_candidate_registry_matrix.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit candidate-only changes if this task changed tracked files**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src/hsconfig/source_candidate_registry.py docs/operator/source-candidate-proof-decks.json tests/test_source_candidate_registry_matrix.py
git commit -m "chore: refresh source closure candidates"
```

Expected: commit succeeds if files changed. If no candidate files changed, skip the commit.

---

### Task 4: Generate Fresh Online-Source Packages For The 12 Decks

**Files:**
- Generated ignored packages: one folder per deck under `outputs/2026-07-18-source-closure-wave-no-default-only/`, using the exact deck names in Step 2.
- Generated ignored logs: one JSON log per deck under `tmp/2026-07-18-source-closure-wave-no-default-only/logs/`, using the exact deck names in Step 2.
- Generated ignored runtime scratch roots: one scratch root per deck under `tmp/2026-07-18-source-closure-wave-no-default-only/runtime/`, using the exact deck names in Step 2.

**Interfaces:**
- Consumes: deck names, deck codes, source candidate registry, online-source fetches.
- Produces: fresh no-apply package per supplied deck.

- [ ] **Step 1: Create ignored output folders**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
New-Item -ItemType Directory -Force outputs\2026-07-18-source-closure-wave-no-default-only | Out-Null
New-Item -ItemType Directory -Force tmp\2026-07-18-source-closure-wave-no-default-only\logs | Out-Null
New-Item -ItemType Directory -Force tmp\2026-07-18-source-closure-wave-no-default-only\runtime | Out-Null
```

Expected: command exits `0`; `git status --short -- outputs tmp` prints no tracked changes.

- [ ] **Step 2: Run `configure --online-source` for every deck without apply**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$decks = @(
  @{Name="ShadowPriest"; Code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="},
  @{Name="CtAPaladin"; Code="AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA="},
  @{Name="PirateRogue"; Code="AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA=="},
  @{Name="BigShaman"; Code="AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA=="},
  @{Name="Discolock"; Code="AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA"},
  @{Name="TreantDruid"; Code="AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA=="},
  @{Name="ImbueMage"; Code="AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA="},
  @{Name="MechPala"; Code="AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="},
  @{Name="Kingslayer"; Code="AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA="},
  @{Name="Boarlock"; Code="AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA"},
  @{Name="PirateDH"; Code="AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA=="},
  @{Name="CuteWarrior"; Code="AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA="}
)

foreach ($deck in $decks) {
  $out = "outputs\2026-07-18-source-closure-wave-no-default-only\$($deck.Name)"
  $runtime = "tmp\2026-07-18-source-closure-wave-no-default-only\runtime\$($deck.Name)"
  $log = "tmp\2026-07-18-source-closure-wave-no-default-only\logs\$($deck.Name).json"
  python -m hsconfig configure `
    --deck-name $deck.Name `
    --deck-code $deck.Code `
    --out $out `
    --runtime-root $runtime `
    --online-source `
    --source-fetch-timeout-seconds 10 `
    --current-date 2026-07-18 `
    --json | Tee-Object -FilePath $log
  if ($LASTEXITCODE -ne 0) { throw "configure failed for $($deck.Name)" }
}
```

Expected: all 12 commands exit `0`. No `--apply` flag is used.

- [ ] **Step 3: Confirm generated outputs are ignored**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short -- outputs tmp
```

Expected: no output.

---

### Task 5: Build And Guard The Source Closure Matrix

**Files:**
- Generated ignored: `tmp/2026-07-18-source-closure-wave-no-default-only/source_closure_matrix.json`
- Generated ignored: `tmp/2026-07-18-source-closure-wave-no-default-only/source_closure_matrix.md`

**Interfaces:**
- Consumes: fresh package reports.
- Produces: strict deck-by-deck classification and fail-fast guard.

- [ ] **Step 1: Generate matrix JSON and Markdown**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

root = Path("outputs/2026-07-18-source-closure-wave-no-default-only")
out = Path("tmp/2026-07-18-source-closure-wave-no-default-only")
rows = []

for deck_dir in sorted(path for path in root.iterdir() if path.is_dir()):
    package = deck_dir / "04_package"
    reports = package / "reports"
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    closure = json.loads((reports / "source_evidence_closure.json").read_text(encoding="utf-8"))
    source_to_runtime = json.loads((reports / "source_to_runtime_explainability.json").read_text(encoding="utf-8"))
    rows.append({
        "deck_name": deck_dir.name,
        "technical_status": operator.get("technical_status"),
        "semantic_status": operator.get("semantic_status"),
        "source_backed_status": operator.get("source_backed_status"),
        "source_strong_ready": operator.get("source_strong_ready"),
        "first_missing_source_action": operator.get("first_missing_source_action"),
        "source_status_reasons": operator.get("source_status_reasons"),
        "source_status_apply_blocking": operator.get("source_status_apply_blocking"),
        "default_only_runtime_surfaces": operator.get("default_only_runtime_surfaces"),
        "runtime_apply_mode": operator.get("runtime_apply_mode"),
        "runtime_apply_allowed": operator.get("runtime_apply_allowed"),
        "closure_apply_blocking": closure.get("apply_blocking"),
        "source_to_runtime_apply_blocking": source_to_runtime.get("apply_blocking"),
    })

out.mkdir(parents=True, exist_ok=True)
(out / "source_closure_matrix.json").write_text(
    json.dumps(rows, indent=2, sort_keys=True),
    encoding="utf-8",
)

lines = [
    "| Deck | Technical | Semantic | Source | Strong | First missing | Default-only | Source apply blocking |",
    "| --- | --- | --- | --- | --- | --- | --- | --- |",
]
for row in rows:
    lines.append(
        "| {deck_name} | {technical_status} | {semantic_status} | {source_backed_status} | {source_strong_ready} | {first_missing_source_action} | {default_only_runtime_surfaces} | {source_status_apply_blocking} |".format(**row)
    )
(out / "source_closure_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
'@
$script | python -
```

Expected: 12 matrix rows, one for each supplied deck.

- [ ] **Step 2: Fail on technical, default-only, or apply-blocking regressions**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

rows = json.loads(Path("tmp/2026-07-18-source-closure-wave-no-default-only/source_closure_matrix.json").read_text(encoding="utf-8"))
bad = []
for row in rows:
    if row["technical_status"] != "VALID_PACKAGE":
        bad.append((row["deck_name"], "technical_status", row["technical_status"]))
    if row["runtime_apply_mode"] != "load_safe_apply":
        bad.append((row["deck_name"], "runtime_apply_mode", row["runtime_apply_mode"]))
    if row["runtime_apply_allowed"] is not True:
        bad.append((row["deck_name"], "runtime_apply_allowed", row["runtime_apply_allowed"]))
    if row["default_only_runtime_surfaces"] != []:
        bad.append((row["deck_name"], "default_only_runtime_surfaces", row["default_only_runtime_surfaces"]))
    if row["source_status_apply_blocking"] is not False:
        bad.append((row["deck_name"], "source_status_apply_blocking", row["source_status_apply_blocking"]))
    if row["closure_apply_blocking"] is not False:
        bad.append((row["deck_name"], "closure_apply_blocking", row["closure_apply_blocking"]))
    if row["source_to_runtime_apply_blocking"] is not False:
        bad.append((row["deck_name"], "source_to_runtime_apply_blocking", row["source_to_runtime_apply_blocking"]))

if bad:
    raise SystemExit(json.dumps(bad, indent=2))
print("source closure matrix no-block/default-only guard passed")
'@
$script | python -
```

Expected:

```text
source closure matrix no-block/default-only guard passed
```

- [ ] **Step 3: Classify source status honestly**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

rows = json.loads(Path("tmp/2026-07-18-source-closure-wave-no-default-only/source_closure_matrix.json").read_text(encoding="utf-8"))
classification = {}
for row in rows:
    if (
        row["technical_status"] == "VALID_PACKAGE"
        and row["source_backed_status"] == "SOURCE_BACKED_STRONG"
        and row["source_strong_ready"] is True
        and row["first_missing_source_action"] == "none"
        and row["default_only_runtime_surfaces"] == []
    ):
        classification[row["deck_name"]] = "strong"
    elif row["technical_status"] == "VALID_PACKAGE" and row["source_status_apply_blocking"] is False:
        classification[row["deck_name"]] = "partial_source_action_needed"
    else:
        classification[row["deck_name"]] = "investigate"

Path("tmp/2026-07-18-source-closure-wave-no-default-only/deck_classification.json").write_text(
    json.dumps(classification, indent=2, sort_keys=True),
    encoding="utf-8",
)
for deck_name, status in sorted(classification.items()):
    print(f"{deck_name}: {status}")
'@
$script | python -
```

Expected: ShadowPriest is `strong`. Other decks may be `strong` only if the package reports `source_strong_ready=true`; otherwise they remain `partial_source_action_needed`.

---

### Task 6: Fix Only Concrete Source-Closure Defects

**Files:**
- Modify only if a concrete failing guard identifies the defect:
  - `src/hsconfig/source_text_claim_extractor.py`
  - `src/hsconfig/source_document_model.py`
  - `src/hsconfig/card_behavior_router.py`
  - `src/hsconfig/compile_mulligan.py`
  - `tests/test_claim_kind_runtime_contract.py`
  - `tests/test_configure_online_source.py`
  - `tests/test_shadowpriest_e2e.py`

**Interfaces:**
- Consumes: source closure matrix, operator summary, source claim gap report, source-to-runtime explainability.
- Produces: focused code/test fix only when current source evidence proves HSConfig is losing valid claims or lowering them incorrectly.

- [ ] **Step 1: Dispatch a read-only package matrix audit subagent**

Dispatch one read-only subagent with this exact brief:

```text
Work in C:\Users\darbo\Documents\HSConfig. Read outputs/2026-07-18-source-closure-wave-no-default-only/*/04_package/reports/operator_summary.json, source_claim_gap_report.json, source_to_runtime_explainability.json, and source_evidence_closure.json. Do not write files. Report:
1. Decks that are VALID_PACKAGE but SOURCE_BACKED_PARTIAL.
2. For each partial deck, the first_missing_source_action and the first concrete missing link if present.
3. Whether the missing link is source-unavailable, extractor-loss, model-loss, runtime-lowering-loss, or correct diagnostic-only behavior.
4. Any default_only_runtime_surfaces or source_status_apply_blocking=true regression.
```

Expected: no writes; exact deck/action report.

- [ ] **Step 2: Apply the source-closure decision table**

Use this table and fix only the first proven defect:

```text
source-unavailable:
  Do not change runtime logic. Keep SOURCE_BACKED_PARTIAL and preserve first_missing_source_action.

extractor-loss:
  Add a failing test in tests/test_configure_online_source.py showing the fetched guide text has a specific claim kind that HSConfig missed. Fix src/hsconfig/source_text_claim_extractor.py.

model-loss:
  Add a failing test in tests/test_claim_kind_runtime_contract.py showing the claim exists but is normalized to the wrong claim_kind or cards. Fix src/hsconfig/source_document_model.py.

runtime-lowering-loss:
  Add a failing test in tests/test_claim_kind_runtime_contract.py or tests/test_shadowpriest_e2e.py showing a source-backed runtime-lowerable claim is suppressed incorrectly. Fix src/hsconfig/card_behavior_router.py or src/hsconfig/compile_mulligan.py.

correct diagnostic-only behavior:
  Do not change code. Preserve SOURCE_BACKED_PARTIAL and exact first_missing_source_action.
```

Expected: no broad refactor, no new fallback authority, and no promotion by source candidate alone.

- [ ] **Step 3: If fixing extractor-loss, write the failing online-source regression**

Add a deck-specific test to `tests/test_configure_online_source.py`. For a ShadowPriest extractor regression, use this exact test name and structure:

```python
def test_online_source_extracts_current_shadowpriest_mulligan_and_hero_power_claims(
    tmp_path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    source_url = "https://example.test/current-shadowpriest-guide"
    fixture_map = tmp_path / "fixture_map.json"
    _write_fixture_map(
        fixture_map,
        source_url,
        "shadowpriest_current_guide.html",
    )
    out = tmp_path / "shadowpriest"
    code = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--online-source",
            "--auto-source",
            "--source-url",
            source_url,
            "--source-fixture-url-map-json",
            str(fixture_map),
            "--current-date",
            "2026-07-18",
            "--json",
        ]
    )
    assert code == 0
    source_documents = _read_json(
        out / "03_source_autopilot" / "source_documents.json"
    )
    flat_claims = [
        claim
        for document in source_documents["source_documents"]
        for claim in document.get("claims", [])
    ]
    assert {
        card_id
        for claim in flat_claims
        if claim.get("claim_kind") == "mulligan_keep"
        for card_id in claim.get("cards", [])
    } == {"SW_446", "TOY_381", "SW_444", "SCH_514", "GVG_009"}
    assert any(
        claim.get("claim_kind") == "hero_power_transform"
        and claim.get("cards") == ["SW_448"]
        for claim in flat_claims
    )
```

Expected before implementation: fails because the concrete claim kind is absent from generated source documents or guide claim bundle.

- [ ] **Step 4: If fixing model-loss or runtime-lowering-loss, write the failing contract regression**

Add or extend a deck-specific test in `tests/test_configure_online_source.py`. For the Darkbishop boundary, extend the ShadowPriest online-source test from Step 3 with this exact runtime assertion block:

```python
    deck_dir = next((out / "04_package" / "CustomConfig").iterdir())
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    darkbishop = json.loads((deck_dir / "SW_448.json").read_text(encoding="utf-8"))
    assert_darkbishop_effect_semantics_without_mulligan_keep(darkbishop, mulligan)
```

Expected before implementation: fails on the precise missing or wrong runtime surface. This uses the existing helper `assert_darkbishop_effect_semantics_without_mulligan_keep(...)` in `tests/test_configure_online_source.py`; do not create a second weaker helper.

- [ ] **Step 5: Run the targeted failing test before implementation**

Run the exact new test, for example:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_configure_online_source.py::test_online_source_extracts_current_shadowpriest_mulligan_and_hero_power_claims -q
```

Expected: fails before the code fix.

- [ ] **Step 6: Implement the minimal fix and rerun the targeted test**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_claim_kind_runtime_contract.py::test_darkbishop_hero_power_transform_does_not_emit_mulligan_keep -q
```

Expected: targeted test passes.

---

### Task 7: Preserve And Prove ShadowPriest Strong Boundary

**Files:**
- Read:
  - `outputs/2026-07-18-source-closure-wave-no-default-only/ShadowPriest/04_package/reports/operator_summary.json`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/ShadowPriest/04_package/reports/source_to_runtime_explainability.json`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/ShadowPriest/04_package/CustomConfig/*/Mulligan.json`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/ShadowPriest/04_package/CustomConfig/*/SW_448.json`
- Modify only if a regression appears:
  - `tests/test_shadowpriest_e2e.py`
  - `tests/test_claim_kind_runtime_contract.py`
  - source/runtime code identified by failure

**Interfaces:**
- Consumes: fresh ShadowPriest package.
- Produces: proof that ShadowPriest is strong, load-safe, no-default-only, and Darkbishop effect-only.

- [ ] **Step 1: Run ShadowPriest source-strong guard**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

base = Path("outputs/2026-07-18-source-closure-wave-no-default-only/ShadowPriest/04_package")
operator = json.loads((base / "reports/operator_summary.json").read_text(encoding="utf-8"))
assert operator["technical_status"] == "VALID_PACKAGE", operator["technical_status"]
assert operator["runtime_apply_mode"] == "load_safe_apply", operator["runtime_apply_mode"]
assert operator["source_status_apply_blocking"] is False
assert operator["default_only_runtime_surfaces"] == []
assert operator["semantic_status"] == "SOURCE_BACKED_STRONG", operator["semantic_status"]
assert operator["source_backed_status"] == "SOURCE_BACKED_STRONG", operator["source_backed_status"]
assert operator["source_strong_ready"] is True
assert operator["first_missing_source_action"] == "none", operator["first_missing_source_action"]
print("ShadowPriest SOURCE_BACKED_STRONG guard passed")
'@
$script | python -
```

Expected:

```text
ShadowPriest SOURCE_BACKED_STRONG guard passed
```

- [ ] **Step 2: Run Darkbishop effect-not-mulligan guard**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

package = Path("outputs/2026-07-18-source-closure-wave-no-default-only/ShadowPriest/04_package")
deck_dirs = [path for path in (package / "CustomConfig").iterdir() if path.is_dir()]
assert len(deck_dirs) == 1
deck_dir = deck_dirs[0]
mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
darkbishop = json.loads((deck_dir / "SW_448.json").read_text(encoding="utf-8"))
mulligan_text = json.dumps(mulligan, sort_keys=True)
darkbishop_text = json.dumps(darkbishop, sort_keys=True).lower()
assert "SW_448" not in mulligan_text, mulligan_text
assert "beforeuseheropowerbonus" in darkbishop_text, darkbishop_text
assert "hero_power" in darkbishop_text or "shadow" in darkbishop_text, darkbishop_text
print("Darkbishop effect-not-mulligan guard passed")
'@
$script | python -
```

Expected:

```text
Darkbishop effect-not-mulligan guard passed
```

- [ ] **Step 3: If either guard fails, fix only the named regression**

Use this decision table:

```text
SW_448 appears in Mulligan.json:
  Add or tighten tests/test_shadowpriest_e2e.py and tests/test_claim_kind_runtime_contract.py.
  Fix claim_kind/runtime lowering so hero_power_transform does not imply mulligan_keep.

SW_448.json lacks BeforeUseHeroPowerBonus:
  Add a claim-kind runtime test for hero_power_transform.
  Fix card behavior routing or source document modeling.

ShadowPriest package is SOURCE_BACKED_PARTIAL:
  Inspect source_claim_gap_report.json and source_autopilot_report.json.
  Fix only extractor/model/status propagation if current full-text source really contains the missing claim.
  Do not force Strong through a default or candidate-only override.
```

Expected: after the fix, repeat Steps 1 and 2 successfully.

---

### Task 8: Generate Research Status Sync, Closure Dossiers, And Optimizer Output

**Files:**
- Read:
  - `outputs/2026-07-18-source-closure-wave-no-default-only/ShadowPriest/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/CtAPaladin/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/PirateRogue/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/BigShaman/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/Discolock/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/TreantDruid/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/ImbueMage/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/MechPala/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/Kingslayer/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/Boarlock/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/PirateDH/04_package/`
  - `outputs/2026-07-18-source-closure-wave-no-default-only/CuteWarrior/04_package/`
  - `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/`
- Generated ignored:
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/ShadowPriest.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/CtAPaladin.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/PirateRogue.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/BigShaman.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/Discolock.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/TreantDruid.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/ImbueMage.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/MechPala.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/Kingslayer.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/Boarlock.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/PirateDH.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/status-sync/CuteWarrior.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/ShadowPriest.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/CtAPaladin.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/PirateRogue.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/BigShaman.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/Discolock.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/TreantDruid.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/ImbueMage.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/MechPala.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/Kingslayer.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/Boarlock.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/PirateDH.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier/CuteWarrior.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/source-closure-optimizer.json`
  - `tmp/2026-07-18-source-closure-wave-no-default-only/source-closure-optimizer.md`

**Interfaces:**
- Consumes: fresh package reports and historical research snapshots.
- Produces: diagnostic-only closure evidence, not apply authority.

- [ ] **Step 1: Run `research-status-sync` and `strong-closure-dossier` for every deck**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
New-Item -ItemType Directory -Force tmp\2026-07-18-source-closure-wave-no-default-only\status-sync | Out-Null
New-Item -ItemType Directory -Force tmp\2026-07-18-source-closure-wave-no-default-only\closure-dossier | Out-Null
$research = "docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop\results"
$names = @(
  "ShadowPriest",
  "CtAPaladin",
  "PirateRogue",
  "BigShaman",
  "Discolock",
  "TreantDruid",
  "ImbueMage",
  "MechPala",
  "Kingslayer",
  "Boarlock",
  "PirateDH",
  "CuteWarrior"
)
foreach ($name in $names) {
  $package = "outputs\2026-07-18-source-closure-wave-no-default-only\$name\04_package"
  python -m hsconfig research-status-sync `
    --package $package `
    --research-results-dir $research `
    --out "tmp\2026-07-18-source-closure-wave-no-default-only\status-sync\$name.json" `
    --json
  if ($LASTEXITCODE -ne 0) { throw "research-status-sync failed for $name" }

  python -m hsconfig strong-closure-dossier `
    --package $package `
    --research-results-dir $research `
    --source-autopilot-report-json "outputs\2026-07-18-source-closure-wave-no-default-only\$name\03_source_autopilot\source_autopilot_report.json" `
    --out "tmp\2026-07-18-source-closure-wave-no-default-only\closure-dossier\$name.json" `
    --json
  if ($LASTEXITCODE -ne 0) { throw "strong-closure-dossier failed for $name" }
}
```

Expected: every command exits `0`.

- [ ] **Step 2: Run source closure optimizer for all packages**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m hsconfig source-closure-optimizer `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\ShadowPriest\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\CtAPaladin\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\PirateRogue\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\BigShaman\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\Discolock\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\TreantDruid\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\ImbueMage\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\MechPala\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\Kingslayer\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\Boarlock\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\PirateDH\04_package `
  --package outputs\2026-07-18-source-closure-wave-no-default-only\CuteWarrior\04_package `
  --candidate-proof-json docs\operator\source-candidate-proof-decks.json `
  --out tmp\2026-07-18-source-closure-wave-no-default-only\source-closure-optimizer.json `
  --markdown-out tmp\2026-07-18-source-closure-wave-no-default-only\source-closure-optimizer.md
```

Expected: command exits `0`; output files stay under ignored `tmp/`.

- [ ] **Step 3: Summarize closure dossier statuses**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

root = Path("tmp/2026-07-18-source-closure-wave-no-default-only/closure-dossier")
for path in sorted(root.glob("*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    print(path.stem, json.dumps({
        "status": data.get("status"),
        "source_backed_status": data.get("source_backed_status"),
        "source_strong_ready": data.get("source_strong_ready"),
        "first_missing_source_action": data.get("first_missing_source_action"),
        "source_status_apply_blocking": data.get("source_status_apply_blocking"),
    }, sort_keys=True))
'@
$script | python -
```

Expected: all decks show `source_status_apply_blocking=false`. ShadowPriest shows strong-ready true. Partial decks show exact next action.

---

### Task 9: Run Focused Regression Suite

**Files:**
- Verify:
  - `tests/test_claim_kind_runtime_contract.py`
  - `tests/test_configure_online_source.py`
  - `tests/test_configure_auto_source.py`
  - `tests/test_source_candidate_registry_matrix.py`
  - `tests/test_real_deck_usage_loop.py`
  - `tests/test_universal_wild_no_block_matrix.py`
  - `tests/test_shadowpriest_e2e.py`
  - `tests/test_operator_docs_contract_policy.py`
  - `tests/test_skill_files.py`

**Interfaces:**
- Consumes: full code/docs/test diff.
- Produces: proof that the current source contract remains load-safe, no-default-only, and ShadowPriest-correct.

- [ ] **Step 1: Run source candidate tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_candidate_registry_matrix.py -q
```

Expected: pass.

- [ ] **Step 2: Run core contract/no-block suite**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest `
  tests/test_claim_kind_runtime_contract.py `
  tests/test_configure_online_source.py `
  tests/test_configure_auto_source.py `
  tests/test_source_candidate_registry_matrix.py `
  tests/test_real_deck_usage_loop.py `
  tests/test_universal_wild_no_block_matrix.py `
  tests/test_shadowpriest_e2e.py `
  -q
```

Expected: pass.

- [ ] **Step 3: Run docs and skill tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_docs_contract_policy.py tests/test_skill_files.py -q
```

Expected: pass.

- [ ] **Step 4: Run diff hygiene**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --check
```

Expected: exit code `0`. Windows line-ending warnings are acceptable only if there are no whitespace errors.

---

### Task 10: Final Review, Commit, And Clean Worktree

**Files:**
- Commit only intentional tracked files from this plan.
- Do not commit generated `outputs/`, `tmp/`, runtime logs, replay files, HDT exports, or private runtime evidence.

**Interfaces:**
- Consumes: final diff, test outputs, subagent reviews.
- Produces: committed tracked changes and clean worktree.

- [ ] **Step 1: Dispatch final read-only reviewer subagent**

Dispatch one read-only subagent with this exact brief:

```text
Work in C:\Users\darbo\Documents\HSConfig. Review the final tracked diff, the source closure matrix, the ShadowPriest guards, and the pytest outputs. Do not write files. Report only blocking issues:
1. False SOURCE_BACKED_STRONG promotion.
2. Hidden default-only runtime success.
3. source_status_apply_blocking true for a valid source-quality gap.
4. ShadowPriest SW_448 emitted as mulligan keep or missing effect semantics.
5. Generated outputs or runtime evidence staged for commit.
```

Expected: no blocking issues, or a concrete issue to fix before commit.

- [ ] **Step 2: Inspect final tracked diff**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --stat
git status --short --branch
```

Expected: tracked changes, if any, are limited to:

```text
src/hsconfig/source_candidate_registry.py
docs/operator/source-candidate-proof-decks.json
tests/test_source_candidate_registry_matrix.py
src/hsconfig/source_text_claim_extractor.py
src/hsconfig/source_document_model.py
src/hsconfig/card_behavior_router.py
src/hsconfig/compile_mulligan.py
tests/test_claim_kind_runtime_contract.py
tests/test_configure_online_source.py
tests/test_shadowpriest_e2e.py
```

Plan-only execution may have no tracked changes beyond this plan document.

- [ ] **Step 3: Commit intentional tracked changes**

If only source candidate/proof/test changes exist, run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src/hsconfig/source_candidate_registry.py docs/operator/source-candidate-proof-decks.json tests/test_source_candidate_registry_matrix.py
git commit -m "chore: refresh source closure candidates"
```

If a concrete source extraction or runtime contract fix exists, run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git add src/hsconfig/source_text_claim_extractor.py src/hsconfig/source_document_model.py src/hsconfig/card_behavior_router.py src/hsconfig/compile_mulligan.py tests/test_claim_kind_runtime_contract.py tests/test_configure_online_source.py tests/test_shadowpriest_e2e.py
git commit -m "fix: close source contract gap"
```

If both categories exist, prefer two separate commits in the order above.

Expected: each commit succeeds. Do not stage generated ignored outputs.

- [ ] **Step 4: Prove final clean state**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
git rev-list --left-right --count HEAD...origin/main
```

Expected:

```text
## codex/hsconfig-canonical-source-status-sync
40 0
```

There must be no uncommitted tracked changes.

---

## Acceptance Criteria

- [ ] Repository state was refreshed before implementation.
- [ ] Worktree started clean or only plan-owned tracked files existed.
- [ ] Existing registry/proof tests passed before candidate changes.
- [ ] Source audit verified current public candidate status.
- [ ] Candidate registry, proof doc, and tests changed only when current source evidence required it.
- [ ] All 12 supplied decks generated fresh `configure --online-source` packages.
- [ ] Generated packages and diagnostics stayed ignored under `outputs/` and `tmp/`.
- [ ] Every generated deck has `technical_status=VALID_PACKAGE`.
- [ ] Every generated deck has `runtime_apply_mode=load_safe_apply`.
- [ ] Every generated deck has `runtime_apply_allowed=true`.
- [ ] Every generated deck has `source_status_apply_blocking=false`.
- [ ] Every generated deck has `default_only_runtime_surfaces=[]`.
- [ ] No context-only or decklist-only source promoted a deck to `SOURCE_BACKED_STRONG`.
- [ ] ShadowPriest has `semantic_status=SOURCE_BACKED_STRONG`.
- [ ] ShadowPriest has `source_backed_status=SOURCE_BACKED_STRONG`.
- [ ] ShadowPriest has `source_strong_ready=true`.
- [ ] ShadowPriest has `first_missing_source_action=none`.
- [ ] ShadowPriest `Mulligan.json` does not keep `SW_448`.
- [ ] ShadowPriest `SW_448.json` preserves hero-power-transform semantics.
- [ ] Partial decks expose exact `first_missing_source_action`.
- [ ] Kingslayer Quick Pick and Boarlock Fracking are not invented from generic prose.
- [ ] Focused source candidate, online-source, no-block, claim-kind, and ShadowPriest tests pass.
- [ ] Docs/skill tests pass if docs or skill files changed.
- [ ] `git diff --check` passes.
- [ ] Final tracked worktree is clean.

## Subagent-Driven Execution Strategy

- **Source Audit subagent, read-only:** current web/source candidate verification for all 12 decks.
- **Package Matrix subagent, read-only:** generated package report audit for status, default-only, and apply-blocking regressions.
- **ShadowPriest Contract subagent, read-only:** `SW_448`, `Mulligan.json`, claim-kind rows, and strong closure proof.
- **Final Reviewer subagent, read-only:** final diff, test evidence, generated-output staging, and worktree status.
- **Main writer:** all tracked file edits, all commits, all final decisions on whether a deck remains partial or can be honestly promoted.

## Execution Handoff

Plan complete. Execute with:

```text
Setze den Plan SubAgent Driven um
```
