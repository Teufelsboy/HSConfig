# HSConfig Live Source Refresh Optimal Config Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh live source evidence and generate optimal load-safe CustomConfig packages for the supplied Wild decks, with ShadowPriest held to `SOURCE_BACKED_STRONG`, no hidden default-only success, and no dirty worktree at handoff.

**Architecture:** Do not add a new apply gate or weaken `SOURCE_BACKED_STRONG`. Use the existing `hsconfig configure --online-source` pipeline, source candidate registry, `operator_summary.json`, research-status sync, and strong-closure dossier to prove the current package state. Only change tracked source registry, docs, fixtures, or tests when a concrete live-source defect is found; generated packages and diagnostics stay under ignored `outputs/` or `tmp/` paths.

**Tech Stack:** Python, pytest, existing HSConfig CLI, existing source acquisition/autopilot pipeline, existing operator reports, PowerShell on Windows.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Start every execution with `git fetch --all --prune --tags`.
- End every execution with `git status --short --branch` showing no uncommitted tracked changes.
- Do not use destructive git cleanup.
- Do not write or apply HearthRanger runtime config unless a later user request explicitly asks for apply.
- Generated live packages must go under ignored paths: `outputs/2026-07-18-live-source-refresh/` and `tmp/2026-07-18-live-source-refresh/`.
- `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a runtime apply gate.
- `source_status_apply_blocking` must stay `false` for source-quality gaps.
- `default_only_runtime_surfaces` must be visible and must prevent `SOURCE_BACKED_STRONG`.
- Candidate URLs, decklists, snippets, and meta pages are acquisition seeds only until fetched full text produces deck-matched, claim-kind-normalized, surface-gated runtime claims.
- ShadowPriest must preserve Darkbishop Benedictus / `SW_448` start-of-game hero-power-transform semantics, but must not keep `SW_448` in `Mulligan.json` without explicit opening-hand source evidence.
- Keep `CuteWarrior` as supplemental/load-safe proof unless a separate future review proves it should widen the representative fixture matrix.

---

## File Structure

- Read: `src/hsconfig/commands/configure.py`
  - Confirms the normal one-command pipeline and output folder shape.
- Read: `src/hsconfig/source_candidate_registry.py`
  - Source candidate truth for online acquisition seeds.
- Read or modify only if live evidence changes: `docs/operator/source-candidate-proof-decks.json`
  - Human-visible source candidate proof set.
- Read or modify only if source candidate registry changes: `tests/test_source_candidate_registry_matrix.py`
  - Locks registry/proof expectations.
- Read: `docs/operator/archetype-fixture-matrix.json`
  - Representative fixture truth and expected strong/partial status.
- Read: `tests/test_universal_wild_no_block_matrix.py`
  - No-block and no-default-only regression coverage for the 12 deck inputs.
- Read: `tests/test_claim_kind_runtime_contract.py`
  - Claim-kind and Darkbishop effect-not-mulligan boundary.
- Generated ignored output: `outputs/2026-07-18-live-source-refresh/<DeckName>/`
  - Fresh `configure --online-source` packages.
- Generated ignored diagnostics: `tmp/2026-07-18-live-source-refresh/`
  - Matrix summaries, status-sync reports, closure dossiers, and command logs.

---

### Task 1: Refresh Baseline And Prove Clean Starting State

**Files:**
- Read-only: git metadata
- Read-only: `docs/operator/source-candidate-proof-decks.json`
- Read-only: `src/hsconfig/source_candidate_registry.py`

**Interfaces:**
- Consumes: current branch, remote state, current source candidate registry.
- Produces: a current clean baseline before any source or package work.

- [ ] **Step 1: Refresh remotes**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git fetch --all --prune --tags
```

Expected: exit code `0`.

- [ ] **Step 2: Confirm the starting worktree is clean**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
```

Expected: only the branch header, for example:

```text
## codex/hsconfig-canonical-source-status-sync
```

If tracked files are dirty, inspect them with `git diff --stat` and stop before changing files unless they are owned by this plan.

- [ ] **Step 3: Record current branch divergence**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git rev-list --left-right --count HEAD...origin/main
```

Expected: record the two numbers in the execution notes. Do not merge or rebase inside this plan unless the current branch is behind and the user explicitly asks to integrate.

- [ ] **Step 4: Verify the candidate registry and proof doc still agree**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_candidate_registry_matrix.py -q
```

Expected: pass.

---

### Task 2: Verify Live Source Candidates Before Changing Anything

**Files:**
- Read: `src/hsconfig/source_candidate_registry.py`
- Read: `docs/operator/source-candidate-proof-decks.json`
- Modify only if a real source candidate update is needed:
  - `src/hsconfig/source_candidate_registry.py`
  - `docs/operator/source-candidate-proof-decks.json`
  - `tests/test_source_candidate_registry_matrix.py`

**Interfaces:**
- Consumes: current online source candidates and existing candidate registry.
- Produces: a verified candidate list that is either unchanged or updated with exact tests.

- [ ] **Step 1: Use a read-only source audit subagent**

Dispatch a read-only subagent with this exact brief:

```text
Audit HSConfig live source candidates for the 12 supplied Wild decks. Read src/hsconfig/source_candidate_registry.py, docs/operator/source-candidate-proof-decks.json, and tests/test_source_candidate_registry_matrix.py. Use current public web checks for each candidate URL. Report only:
1. URLs that are dead or no longer usable as source candidates.
2. Better current full-text guide URLs that should replace or supplement existing candidates.
3. Candidates that must remain context_only or candidate_partial.
Do not write files.
```

Expected: subagent returns a compact deck-by-deck source candidate verdict.

- [ ] **Step 2: Preserve known high-value candidates**

The following candidates must stay unless the source audit proves the URL is unusable:

```text
ShadowPriest: https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest
PirateDH: https://hs.cardsrealm.com/en-bz/articles/hearthstone-wild-deck-guide-pirate-demon-hunter-become-a-legend
BigShaman: https://www.hearthpwn.com/decks/1186371-big-shaman-in-depth-guide
ImbueMage: https://www.hearthpwn.com/decks/1462266-wild-imbue-mage
```

Expected: no change for these rows unless audit evidence shows a stronger live replacement.

- [ ] **Step 3: If the audit finds a better candidate, update registry and proof doc together**

For every changed candidate in `src/hsconfig/source_candidate_registry.py`, make the matching update in `docs/operator/source-candidate-proof-decks.json`.

Use these strength rules exactly:

```text
runtime_claims_possible: fetched full-text source may contain runtime-lowerable claims.
candidate_partial: source can support context or some claims, but a known first_missing_source_action remains.
context_only: decklist/meta/category source, no runtime claim kinds.
```

For `context_only`, keep:

```python
expected_claim_kinds=()
first_missing_source_action!="none"
```

- [ ] **Step 4: Run candidate registry tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_candidate_registry_matrix.py tests/test_docs_active_path.py::test_operator_docs_define_source_candidate_proof_set_without_new_authority -q
```

Expected: pass.

- [ ] **Step 5: If files changed, commit only candidate/proof updates**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff -- src/hsconfig/source_candidate_registry.py docs/operator/source-candidate-proof-decks.json tests/test_source_candidate_registry_matrix.py
git add src/hsconfig/source_candidate_registry.py docs/operator/source-candidate-proof-decks.json tests/test_source_candidate_registry_matrix.py
git commit -m "chore: refresh HSConfig live source candidates"
```

Expected: commit succeeds only if those files changed. If no files changed, skip this step.

---

### Task 3: Generate Fresh Online-Source Packages For All Supplied Decks

**Files:**
- Generated ignored output:
  - `outputs/2026-07-18-live-source-refresh/<DeckName>/`
  - `tmp/2026-07-18-live-source-refresh/logs/<DeckName>.json`

**Interfaces:**
- Consumes: source candidate registry, current deck list, public source fetches.
- Produces: fresh no-apply packages for all 12 decks.

- [ ] **Step 1: Create ignored output folders**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
New-Item -ItemType Directory -Force outputs\2026-07-18-live-source-refresh | Out-Null
New-Item -ItemType Directory -Force tmp\2026-07-18-live-source-refresh\logs | Out-Null
New-Item -ItemType Directory -Force tmp\2026-07-18-live-source-refresh\runtime | Out-Null
```

Expected: exit code `0`; no tracked files created.

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
  $out = "outputs\2026-07-18-live-source-refresh\$($deck.Name)"
  $runtime = "tmp\2026-07-18-live-source-refresh\runtime\$($deck.Name)"
  $log = "tmp\2026-07-18-live-source-refresh\logs\$($deck.Name).json"
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

Expected: every command exits `0`, each log has `"status": "OK"`, and no runtime apply is performed.

- [ ] **Step 3: Confirm generated outputs are ignored**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short -- outputs tmp
```

Expected: no output.

---

### Task 4: Build The Live Source Status Matrix

**Files:**
- Generated ignored output:
  - `tmp/2026-07-18-live-source-refresh/live_source_matrix.json`
  - `tmp/2026-07-18-live-source-refresh/live_source_matrix.md`

**Interfaces:**
- Consumes: fresh package reports.
- Produces: a compact deck-by-deck decision table for implementation and final handoff.

- [ ] **Step 1: Generate JSON and Markdown matrix summaries**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

root = Path("outputs/2026-07-18-live-source-refresh")
out = Path("tmp/2026-07-18-live-source-refresh")
rows = []

for deck_dir in sorted(root.iterdir()):
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
        "source_status_apply_blocking": operator.get("source_status_apply_blocking"),
        "default_only_runtime_surfaces": operator.get("default_only_runtime_surfaces"),
        "runtime_apply_mode": operator.get("runtime_apply_mode"),
        "runtime_apply_allowed": operator.get("runtime_apply_allowed"),
        "closure_apply_blocking": closure.get("apply_blocking"),
        "source_to_runtime_apply_blocking": source_to_runtime.get("apply_blocking"),
    })

out.mkdir(parents=True, exist_ok=True)
(out / "live_source_matrix.json").write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")

lines = [
    "| Deck | Technical | Semantic | Source | Strong ready | Missing action | Default-only | Apply-blocking |",
    "| --- | --- | --- | --- | --- | --- | --- | --- |",
]
for row in rows:
    apply_blocking = row["source_status_apply_blocking"] or row["closure_apply_blocking"] or row["source_to_runtime_apply_blocking"]
    lines.append(
        "| {deck_name} | {technical_status} | {semantic_status} | {source_backed_status} | {source_strong_ready} | {first_missing_source_action} | {default_only_runtime_surfaces} | {apply_blocking} |".format(
            apply_blocking=apply_blocking,
            **row,
        )
    )
(out / "live_source_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
'@
$script | python -
```

Expected:

```text
ShadowPriest has technical_status VALID_PACKAGE.
Every deck has source_status_apply_blocking False.
Every deck has default_only_runtime_surfaces [].
No deck has closure_apply_blocking True.
No deck has source_to_runtime_apply_blocking True.
```

- [ ] **Step 2: Fail fast on no-block or default-only violations**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

rows = json.loads(Path("tmp/2026-07-18-live-source-refresh/live_source_matrix.json").read_text(encoding="utf-8"))
bad = []
for row in rows:
    if row["technical_status"] != "VALID_PACKAGE":
        bad.append((row["deck_name"], "technical_status", row["technical_status"]))
    if row["source_status_apply_blocking"] is not False:
        bad.append((row["deck_name"], "source_status_apply_blocking", row["source_status_apply_blocking"]))
    if row["default_only_runtime_surfaces"] != []:
        bad.append((row["deck_name"], "default_only_runtime_surfaces", row["default_only_runtime_surfaces"]))
    if row["closure_apply_blocking"] is not False:
        bad.append((row["deck_name"], "closure_apply_blocking", row["closure_apply_blocking"]))
    if row["source_to_runtime_apply_blocking"] is not False:
        bad.append((row["deck_name"], "source_to_runtime_apply_blocking", row["source_to_runtime_apply_blocking"]))

if bad:
    raise SystemExit(json.dumps(bad, indent=2))
print("live matrix no-block/default-only guard passed")
'@
$script | python -
```

Expected:

```text
live matrix no-block/default-only guard passed
```

---

### Task 5: Force ShadowPriest To Strong Or Fix The Concrete Source Defect

**Files:**
- Read:
  - `outputs/2026-07-18-live-source-refresh/ShadowPriest/04_package/reports/operator_summary.json`
  - `outputs/2026-07-18-live-source-refresh/ShadowPriest/04_package/reports/source_claim_gap_report.json`
  - `outputs/2026-07-18-live-source-refresh/ShadowPriest/04_package/reports/source_to_runtime_explainability.json`
  - `outputs/2026-07-18-live-source-refresh/ShadowPriest/03_source_autopilot/source_documents.json`
- Modify only if concrete defect is proven:
  - `src/hsconfig/source_text_claim_extractor.py`
  - `src/hsconfig/source_document_model.py`
  - `src/hsconfig/source_candidate_registry.py`
  - `tests/test_claim_kind_runtime_contract.py`
  - `tests/test_configure_online_source.py`
  - `tests/test_shadowpriest_e2e.py`

**Interfaces:**
- Consumes: live ShadowPriest package.
- Produces: ShadowPriest package with `SOURCE_BACKED_STRONG` and correct Darkbishop runtime boundary.

- [ ] **Step 1: Assert ShadowPriest package is technically valid and source-strong**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

base = Path("outputs/2026-07-18-live-source-refresh/ShadowPriest/04_package")
operator = json.loads((base / "reports/operator_summary.json").read_text(encoding="utf-8"))
assert operator["technical_status"] == "VALID_PACKAGE", operator["technical_status"]
assert operator["runtime_apply_mode"] == "load_safe_apply", operator["runtime_apply_mode"]
assert operator["source_status_apply_blocking"] is False
assert operator["default_only_runtime_surfaces"] == []
assert operator["semantic_status"] == "SOURCE_BACKED_STRONG", operator["semantic_status"]
assert operator["source_backed_status"] == "SOURCE_BACKED_STRONG", operator["source_backed_status"]
assert operator["source_strong_ready"] is True
assert operator["first_missing_source_action"] == "none", operator["first_missing_source_action"]
print("ShadowPriest strong package guard passed")
'@
$script | python -
```

Expected:

```text
ShadowPriest strong package guard passed
```

If this fails, do not weaken the strong gate. Continue to Step 2.

- [ ] **Step 2: Diagnose only the first ShadowPriest missing source link**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

base = Path("outputs/2026-07-18-live-source-refresh/ShadowPriest/04_package/reports")
for name in [
    "operator_summary.json",
    "source_claim_gap_report.json",
    "source_to_runtime_explainability.json",
    "guide_claim_bundle.json",
]:
    data = json.loads((base / name).read_text(encoding="utf-8"))
    print("\n==", name, "==")
    if name == "operator_summary.json":
        keys = [
            "semantic_status",
            "source_backed_status",
            "source_status_reasons",
            "first_missing_source_action",
            "semantic_blockers",
            "default_only_runtime_surfaces",
        ]
        print(json.dumps({key: data.get(key) for key in keys}, indent=2, sort_keys=True))
    elif name == "source_claim_gap_report.json":
        print(json.dumps(data.get("summary", data), indent=2, sort_keys=True))
    elif name == "source_to_runtime_explainability.json":
        print(json.dumps(data.get("operator_attention", []), indent=2, sort_keys=True))
    else:
        print(json.dumps({
            "claim_count": len(data.get("claims", [])),
            "claim_kinds": sorted({claim.get("claim_kind") for claim in data.get("claims", [])}),
        }, indent=2, sort_keys=True))
'@
$script | python -
```

Expected: output names exactly one concrete missing chain or extraction gap.

- [ ] **Step 3: Fix only the proven ShadowPriest defect**

Use this decision table:

```text
No source documents were fetched:
  Fix candidate URL/fetch handling in src/hsconfig/source_candidate_registry.py or source acquisition only.

Guide source fetched but no mulligan/gameplan/targeting claims extracted:
  Add a focused parser/extractor regression in tests/test_configure_online_source.py and fix src/hsconfig/source_text_claim_extractor.py.

Hero-power-transform claim exists but SW_448 card behavior missing:
  Add a focused regression in tests/test_claim_kind_runtime_contract.py and fix src/hsconfig/source_document_model.py.

SW_448 appears in Mulligan.json:
  Add a failing regression in tests/test_claim_kind_runtime_contract.py and tests/test_shadowpriest_e2e.py, then fix start-of-game non-hand suppression.

All claims exist but strong still false due stale status:
  Add focused regression in tests/test_configure_online_source.py and fix status propagation only.
```

Expected: one focused code/test change. Do not modify unrelated decks while fixing ShadowPriest.

- [ ] **Step 4: Re-run ShadowPriest only**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m hsconfig configure `
  --deck-name ShadowPriest `
  --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
  --out outputs\2026-07-18-live-source-refresh\ShadowPriest `
  --runtime-root tmp\2026-07-18-live-source-refresh\runtime\ShadowPriest `
  --online-source `
  --source-fetch-timeout-seconds 10 `
  --current-date 2026-07-18 `
  --json
```

Expected: `"status": "OK"` and Step 1 passes.

- [ ] **Step 5: Verify Darkbishop effect-not-mulligan boundary**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

package = Path("outputs/2026-07-18-live-source-refresh/ShadowPriest/04_package")
deck_dirs = [path for path in (package / "CustomConfig").iterdir() if path.is_dir()]
assert len(deck_dirs) == 1
deck_dir = deck_dirs[0]
mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
darkbishop = json.loads((deck_dir / "SW_448.json").read_text(encoding="utf-8"))

mulligan_text = json.dumps(mulligan, sort_keys=True)
assert "SW_448" not in mulligan_text, mulligan_text
darkbishop_text = json.dumps(darkbishop, sort_keys=True).lower()
assert "hero_power" in darkbishop_text or "shadow" in darkbishop_text, darkbishop_text
assert "beforeuseheropowerbonus" in darkbishop_text, darkbishop_text
print("Darkbishop effect-not-mulligan guard passed")
'@
$script | python -
```

Expected:

```text
Darkbishop effect-not-mulligan guard passed
```

---

### Task 6: Produce Research Status Sync And Strong Closure Dossiers

**Files:**
- Read:
  - `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/*.json`
  - `outputs/2026-07-18-live-source-refresh/<DeckName>/04_package/`
- Generated ignored output:
  - `tmp/2026-07-18-live-source-refresh/status-sync/<DeckName>.json`
  - `tmp/2026-07-18-live-source-refresh/closure-dossier/<DeckName>.json`

**Interfaces:**
- Consumes: fresh packages and existing research-deep snapshots.
- Produces: diagnostic proof that stale seed-only snapshots do not override canonical package status.

- [ ] **Step 1: Run research-status-sync and strong-closure-dossier for every deck**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
New-Item -ItemType Directory -Force tmp\2026-07-18-live-source-refresh\status-sync | Out-Null
New-Item -ItemType Directory -Force tmp\2026-07-18-live-source-refresh\closure-dossier | Out-Null
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
  $package = "outputs\2026-07-18-live-source-refresh\$name\04_package"
  python -m hsconfig research-status-sync `
    --package $package `
    --research-results-dir $research `
    --out "tmp\2026-07-18-live-source-refresh\status-sync\$name.json" `
    --json
  if ($LASTEXITCODE -ne 0) { throw "research-status-sync failed for $name" }

  python -m hsconfig strong-closure-dossier `
    --package $package `
    --research-results-dir $research `
    --source-autopilot-report-json "outputs\2026-07-18-live-source-refresh\$name\03_source_autopilot\source_autopilot_report.json" `
    --out "tmp\2026-07-18-live-source-refresh\closure-dossier\$name.json" `
    --json
  if ($LASTEXITCODE -ne 0) { throw "strong-closure-dossier failed for $name" }
}
```

Expected: all commands exit `0`; all outputs stay under ignored `tmp/`.

- [ ] **Step 2: Summarize dossier status**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$script = @'
from pathlib import Path
import json

root = Path("tmp/2026-07-18-live-source-refresh/closure-dossier")
for path in sorted(root.glob("*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    keys = {
        "status": data.get("status"),
        "source_backed_status": data.get("source_backed_status"),
        "source_strong_ready": data.get("source_strong_ready"),
        "first_missing_source_action": data.get("first_missing_source_action"),
        "source_status_apply_blocking": data.get("source_status_apply_blocking"),
    }
    print(path.stem, json.dumps(keys, sort_keys=True))
'@
$script | python -
```

Expected:

```text
ShadowPriest source_strong_ready true and first_missing_source_action none.
Partial decks show exact first_missing_source_action.
Every deck shows source_status_apply_blocking false.
```

---

### Task 7: Classify Strong, Partial, And Known Stop Conditions

**Files:**
- Read:
  - `tmp/2026-07-18-live-source-refresh/live_source_matrix.json`
  - `tmp/2026-07-18-live-source-refresh/closure-dossier/*.json`
  - `docs/operator/source-backed-strong-closure.md`
  - `docs/operator/source-candidate-proof-decks.json`

**Interfaces:**
- Consumes: matrix and dossier outputs.
- Produces: final deck-state classification for handoff.

- [ ] **Step 1: Classify each deck using the strict table**

Use this classification rule:

```text
strong:
  technical_status == VALID_PACKAGE
  source_backed_status == SOURCE_BACKED_STRONG
  source_strong_ready == true
  first_missing_source_action == none
  default_only_runtime_surfaces == []

partial_source_action_needed:
  technical_status == VALID_PACKAGE
  source_status_apply_blocking == false
  first_missing_source_action != none
  known stop condition absent

preserved_partial_stop_condition:
  Kingslayer with Quick Pick exact mulligan source still unavailable
  Boarlock with Fracking exact mulligan source still unavailable

context_only_load_safe:
  candidate is decklist/meta/category context only and still builds load-safe
```

- [ ] **Step 2: Do not promote false Strong**

If a deck has only decklist/meta/current-index support, keep or set:

```text
source_backed_status: SOURCE_BACKED_PARTIAL
source_strong_ready: false
first_missing_source_action: add_current_full_text_mulligan_or_gameplan_source
source_status_apply_blocking: false
```

Expected: no deck becomes Strong from Hearthstone-Decks.net category pages or decklist-only source records alone.

- [ ] **Step 3: Preserve Kingslayer and Boarlock stop conditions**

Expected:

```text
Kingslayer remains partial until exact Quick Pick mulligan keep/discard source exists.
Boarlock remains partial until exact Fracking mulligan keep/discard source exists.
Both remain load-safe and source_status_apply_blocking=false.
```

Do not invent mulligan keeps for Quick Pick or Fracking from generic draw/weapon/combo prose.

---

### Task 8: Run Focused Contract And Matrix Verification

**Files:**
- Verify:
  - `tests/test_claim_kind_runtime_contract.py`
  - `tests/test_configure_online_source.py`
  - `tests/test_configure_auto_source.py`
  - `tests/test_universal_wild_no_block_matrix.py`
  - `tests/test_source_candidate_registry_matrix.py`
  - `tests/test_real_deck_usage_loop.py`
  - `tests/test_shadowpriest_e2e.py`

**Interfaces:**
- Consumes: code, docs, registry, and package builder behavior.
- Produces: regression proof for source contract, online-source path, no-block matrix, and ShadowPriest boundary.

- [ ] **Step 1: Run focused tests**

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

Expected: all selected tests pass.

- [ ] **Step 2: Run docs/skill contract tests if tracked docs or skill files changed**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_docs_contract_policy.py tests/test_skill_files.py -q
```

Expected: pass.

- [ ] **Step 3: Run `git diff --check`**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --check
```

Expected: exit code `0`. Windows line-ending warnings without whitespace errors are acceptable.

---

### Task 9: Commit Any Intentional Tracked Changes And Leave The Worktree Clean

**Files:**
- Commit only intentional tracked changes from this plan.
- Do not commit generated `outputs/`, `tmp/`, logs, runtime exports, replay files, or private runtime evidence.

**Interfaces:**
- Consumes: final diff.
- Produces: a clean git state.

- [ ] **Step 1: Inspect tracked diff**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --stat
git status --short --branch
```

Expected: tracked changes, if any, are limited to source candidate registry/proof docs/tests or a concrete source extraction/contract fix from Task 5.

- [ ] **Step 2: Commit if tracked changes exist**

If tracked changes exist, run one of these commit commands depending on scope:

```powershell
git add src/hsconfig/source_candidate_registry.py docs/operator/source-candidate-proof-decks.json tests/test_source_candidate_registry_matrix.py
git commit -m "chore: refresh HSConfig source candidate proof"
```

or:

```powershell
git add src/hsconfig/source_text_claim_extractor.py src/hsconfig/source_document_model.py tests/test_claim_kind_runtime_contract.py tests/test_configure_online_source.py tests/test_shadowpriest_e2e.py
git commit -m "fix: close ShadowPriest live source contract"
```

Expected: commit succeeds. Do not stage ignored package outputs.

- [ ] **Step 3: Prove final clean state**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
```

Expected: only the branch header. If ignored outputs exist, they must not appear in this command.

---

## Acceptance Criteria

- [ ] Repository was refreshed before execution.
- [ ] Starting worktree was clean or only plan-owned tracked changes existed.
- [ ] All 12 supplied decks produced fresh `configure --online-source` packages under `outputs/2026-07-18-live-source-refresh/`.
- [ ] No generated live package was committed.
- [ ] Every package has `technical_status=VALID_PACKAGE`.
- [ ] Every package has `runtime_apply_mode=load_safe_apply`.
- [ ] Every package has `source_status_apply_blocking=false`.
- [ ] Every package has `default_only_runtime_surfaces=[]`.
- [ ] ShadowPriest has `semantic_status=SOURCE_BACKED_STRONG`.
- [ ] ShadowPriest has `source_backed_status=SOURCE_BACKED_STRONG`.
- [ ] ShadowPriest has `source_strong_ready=true`.
- [ ] ShadowPriest has `first_missing_source_action=none`.
- [ ] ShadowPriest `Mulligan.json` does not keep `SW_448`.
- [ ] ShadowPriest `SW_448.json` preserves hero-power-transform semantics.
- [ ] Kingslayer and Boarlock are not falsely promoted if exact missing mulligan sources remain unavailable.
- [ ] Context-only or decklist-only sources do not promote Strong.
- [ ] Focused contract, online-source, source candidate, no-block matrix, and ShadowPriest tests pass.
- [ ] `git diff --check` passes.
- [ ] Final `git status --short --branch` is clean.

## Subagent-Driven Execution Strategy

- **Source Audit subagent, read-only:** verify online candidate usability and source strength class for all 12 decks.
- **Package Matrix subagent, read-only:** inspect generated package reports and summarize technical/source/default-only status.
- **ShadowPriest Contract subagent, read-only:** inspect `SW_448`, Mulligan, claim bundle, and source gaps.
- **Final Reviewer subagent, read-only:** review final diff, test evidence, and worktree status before handoff.
- **Main writer:** only the main agent writes files, updates tests, commits intentional tracked changes, and decides whether a source issue is data, parser, or contract logic.

## Execution Handoff

Plan complete. Execute with:

```text
Setze den Plan SubAgent Driven um
```
