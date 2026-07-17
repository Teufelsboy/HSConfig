# HSConfig Source-Backed Strong Optimal Config Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and verify a fresh optimal ShadowPriest CustomConfig package through the current source-backed pipeline, while proving that the Source/Contract logic stays canonical, no hidden default-only path exists, and all listed Wild decks remain load-safe instead of blocked by source-depth gaps.

**Architecture:** Use the existing `hsconfig configure` path as the only package builder: source acquisition -> source autopilot -> source documents -> research/prepare -> validate -> reports. Keep `reports/operator_summary.json` as the only normal apply authority; `SOURCE_BACKED_STRONG` is a diagnostic evidence-quality label produced through the canonical source-status resolver, not a generation or apply gate. Do not add a new runtime surface, source-status model, apply gate, or post-game tuning loop.

**Tech Stack:** Python 3.11+, pytest, existing `hsconfig` CLI, existing `source_status_resolver`, existing source acquisition/autopilot modules, PowerShell for local command orchestration, no new dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Before execution, run `git fetch --all --prune` and confirm `git rev-list --left-right --count HEAD...origin/main` prints `0 0`.
- Preserve the existing dirty worktree. Do not reset, checkout, clean, delete, or overwrite previous changes.
- Do not apply to the live HearthRanger runtime in this plan. Generate and validate packages only. Runtime writes require a separate explicit apply request.
- Use `C:\Users\darbo\Desktop\HS` as `--runtime-root` only if it exists. If it does not exist, stop before configure and report the missing runtime root.
- `SOURCE_BACKED_STRONG` must be honest. Never promote from decklist-only, stats-only, snippet-only, policy-backed, default-runtime, or candidate-registry evidence alone.
- Candidate URLs and current online deck pages are acquisition seeds only. They become strong evidence only after fetched full text produces deck/archetype-matched, claim-kind-normalized, runtime-surface-lowerable claims.
- No default-only runtime surface may be hidden. Any default-only surface must appear in `operator_summary.json`, explainability/closure diagnostics, and must prevent `SOURCE_BACKED_STRONG`.
- Valid decks must not be blocked because source depth is partial. A technically valid deck must still produce a load-safe package with `source_status_apply_blocking=false`.
- Darkbishop Benedictus / `SW_448` must preserve start-of-game hero-power-transform runtime semantics, but must not be emitted as a Mulligan keep unless an explicit opening-hand keep source says so.
- Keep source and runtime truth separate: source documents explain confidence; `operator_summary.json` governs package readiness.

---

## File Structure

- Read: `docs/operator/README.md` for the normal configure path and report order.
- Read: `docs/operator/source-backed-strong-closure.md` for canonical source-status rules.
- Read: `docs/operator/universal-wild-no-block-contract.md` for no-block behavior.
- Read: `.agents/skills/hsconfig/SKILL.md` for operator workflow and Darkbishop boundary.
- Use generated output directory: `outputs/2026-07-17-source-backed-strong-optimal/`.
- Create or update during execution only if source capture is needed: `docs/operator/source-inputs/2026-07-17-shadowpriest-source-search-results.json`.
- Do not modify source code unless a failing acceptance test proves an implementation defect. If source code must change, first add the failing test that exposes the defect.
- Do not commit generated package output, runtime logs, replay files, HearthRanger logs, HDT exports, or private runtime evidence.

## Deck Matrix

Use this exact deck matrix for no-block and package verification.

```json
[
  {
    "deck_name": "ShadowPriest",
    "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    "hsid": "2737726722",
    "hdt_deck_id": "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602"
  },
  {
    "deck_name": "CtAPaladin",
    "deck_code": "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=",
    "hsid": "2737744316",
    "hdt_deck_id": "f9b54950-ca24-48cf-805e-bf620eab47a0"
  },
  {
    "deck_name": "PirateRogue",
    "deck_code": "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==",
    "hsid": "2740734095",
    "hdt_deck_id": "c1e87d43-5802-460b-b955-31ae458eb41a"
  },
  {
    "deck_name": "BigShaman",
    "deck_code": "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
    "hsid": "2737735409",
    "hdt_deck_id": "6b26f907-6f1e-44c8-a4e4-d14e9d51f819"
  },
  {
    "deck_name": "Discolock",
    "deck_code": "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA",
    "hsid": "2740357533",
    "hdt_deck_id": "55241397-ac74-4d46-a662-089e5858839c"
  },
  {
    "deck_name": "TreantDruid",
    "deck_code": "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==",
    "hsid": "2740360895",
    "hdt_deck_id": "a120a28b-1840-4032-a3c9-2da4c51338ed"
  },
  {
    "deck_name": "ImbueMage",
    "deck_code": "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=",
    "hsid": "2740361888",
    "hdt_deck_id": "49c05560-8b30-4d06-b3a2-a8b0ff36d005"
  },
  {
    "deck_name": "MechPala",
    "deck_code": "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
    "hsid": "2740734214",
    "hdt_deck_id": "8f011f55-8ae2-436c-b53a-315f280e8833"
  },
  {
    "deck_name": "Kingslayer",
    "deck_code": "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=",
    "hsid": "2740733989",
    "hdt_deck_id": "1292ff02-8ebe-47a5-90b1-9a1899acd6aa"
  },
  {
    "deck_name": "Boarlock",
    "deck_code": "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA",
    "hsid": "2740361505",
    "hdt_deck_id": "7727c718-c93c-47ca-a766-5612c3806f0f"
  },
  {
    "deck_name": "PirateDH",
    "deck_code": "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==",
    "hsid": "2737737281",
    "hdt_deck_id": "2bc184ed-b59a-4420-900d-b0ed3d153979"
  },
  {
    "deck_name": "CuteWarrior",
    "deck_code": "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=",
    "hsid": "2750150375",
    "hdt_deck_id": "a753f091-b770-4a06-8da8-59f1d5269f6b"
  }
]
```

## Source Seeds To Use During Execution

Use these current public URLs as source-acquisition seeds. They are not proof until fetched and normalized.

```text
https://hearthstone-decks.net/wild-decks/priest-wild-decks/shadow-priest-priest-wild-decks/
https://www.hsguru.com/deck/11156421
https://www.hearthpwn.com/decks/1395635-legend-shadowburst-priest
https://hearthstone-decks.net/wild-meta-report-team-wildside-september-2021/
https://outof.games/news/5444-shadowburst-priest-wild-hearthstone-full-deck-guide-on-the-wildest-of-thursdays/
https://hearthstone-decks.net/wild-decks/paladin-wild-decks/other-paladin-decks-paladin-wild-decks/cta-paladin/
https://hearthstone-decks.net/wild-decks/rogue-wild-decks/pirate-rogue-other-rogue-decks-rogue-wild-decks/
https://hearthstone-decks.net/wild-decks/shaman-wild-decks/big-shaman-wild/
https://hearthstone-decks.net/wild-decks/warlock-wild-decks/
https://hearthstone-decks.net/wild-decks/druid-wild-decks/other-druid-decks-druid-wild-decks/treant-druid-other-druid-decks-druid-wild-decks/
https://hearthstone-decks.net/wild-decks/mage-wild-decks/other-mage-decks-mage-wild-decks/imbue-mage-other-mage-decks-mage-wild-decks/
https://hearthstone-decks.net/wild-decks/paladin-wild-decks/wild-mech-paladin/
https://hearthstone-decks.net/wild-decks/warlock-wild-decks/other-warlock-decks-warlock-wild-decks/elwynn-boar-warlock/
https://hearthstone-decks.net/wild-decks/demon-hunter-wild-decks/
https://hearthstone-decks.net/wild-decks/warrior-wild-decks/
```

---

### Task 1: Refresh Repository And Establish Execution Baseline

**Files:**
- Read-only: repository metadata
- Read-only: `docs/operator/README.md`
- Read-only: `.agents/skills/hsconfig/SKILL.md`
- Read-only: `src/hsconfig/commands/configure.py`
- Read-only: `src/hsconfig/source_status_resolver.py`

**Interfaces:**
- Consumes: current branch, upstream state, existing dirty worktree.
- Produces: confirmed safe execution baseline with no destructive git operations.

- [ ] **Step 1: Refresh remotes**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git fetch --all --prune
```

Expected: exit code 0.

- [ ] **Step 2: Confirm upstream sync**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git rev-list --left-right --count HEAD...origin/main
```

Expected:

```text
0 0
```

If the output is not `0 0`, stop before source/config generation and inspect divergence with:

```powershell
git status --short --branch
git log --oneline --decorate --left-right --graph HEAD...origin/main -20
```

- [ ] **Step 3: Record worktree status**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git status --short --branch
```

Expected: any dirty files are existing source-contract work or this new plan file. Do not clean them.

- [ ] **Step 4: Confirm runtime root exists**

Run:

```powershell
$runtimeRoot = "C:\Users\darbo\Desktop\HS"
if (-not (Test-Path $runtimeRoot)) {
  throw "Missing runtime root: $runtimeRoot"
}
"runtime root ok: $runtimeRoot"
```

Expected:

```text
runtime root ok: C:\Users\darbo\Desktop\HS
```

- [ ] **Step 5: Run current focused contract tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py tests/test_source_bundle.py tests/test_strong_promotion_report.py tests/test_source_evidence_closure.py tests/test_shadowpriest_fresh_closure_proof.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all tests pass. If this fails, do not generate a final package before fixing the failing contract test.

---

### Task 2: Capture Source Seeds Without Promoting Them

**Files:**
- Create: `docs/operator/source-inputs/2026-07-17-shadowpriest-source-search-results.json`
- Read-only: `src/hsconfig/source_acquisition.py`
- Read-only: `src/hsconfig/source_candidate_registry.py`

**Interfaces:**
- Consumes: source seed URLs listed in this plan.
- Produces: a deterministic source-search JSON file that `hsconfig configure --auto-source --source-search-results-json ...` can consume.

- [ ] **Step 1: Create source-inputs directory**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
New-Item -ItemType Directory -Force .\docs\operator\source-inputs | Out-Null
```

Expected: exit code 0.

- [ ] **Step 2: Write deterministic ShadowPriest source search records**

Create `docs/operator/source-inputs/2026-07-17-shadowpriest-source-search-results.json` with this exact JSON shape:

```json
{
  "deck_name": "ShadowPriest",
  "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
  "retrieved_for": "2026-07-17-source-backed-strong-optimal-config-run",
  "records": [
    {
      "title": "Top Legend Hearthstone Shadow Priest Decks",
      "url": "https://hearthstone-decks.net/wild-decks/priest-wild-decks/shadow-priest-priest-wild-decks/",
      "source_type": "deck_category_seed",
      "source_family": "hearthstone-decks",
      "source_visibility": "decklist_or_category",
      "deck_match_scope": "archetype_matched",
      "expected_strength": "acquisition_seed_only"
    },
    {
      "title": "Shadow Priest Wild Deck - HSGuru",
      "url": "https://www.hsguru.com/deck/11156421",
      "source_type": "decklist_seed",
      "source_family": "hsguru",
      "source_visibility": "decklist_or_stats",
      "deck_match_scope": "archetype_matched",
      "expected_strength": "acquisition_seed_only"
    },
    {
      "title": "Legend Shadowburst Priest - HearthPwn",
      "url": "https://www.hearthpwn.com/decks/1395635-legend-shadowburst-priest",
      "source_type": "public_guide_candidate",
      "source_family": "hearthpwn",
      "source_visibility": "full_text_candidate",
      "deck_match_scope": "archetype_matched",
      "expected_strength": "claim_extraction_required"
    },
    {
      "title": "Team WildSide Wild Meta Report Shadow Priest",
      "url": "https://hearthstone-decks.net/wild-meta-report-team-wildside-september-2021/",
      "source_type": "evergreen_wild_archetype_candidate",
      "source_family": "hearthstone-decks",
      "source_visibility": "full_text_candidate",
      "deck_match_scope": "archetype_matched",
      "expected_strength": "claim_extraction_required"
    },
    {
      "title": "Shadowburst Priest Wild Hearthstone Full Deck Guide",
      "url": "https://outof.games/news/5444-shadowburst-priest-wild-hearthstone-full-deck-guide-on-the-wildest-of-thursdays/",
      "source_type": "evergreen_wild_archetype_candidate",
      "source_family": "outofgames",
      "source_visibility": "full_text_candidate",
      "deck_match_scope": "archetype_matched",
      "expected_strength": "claim_extraction_required"
    }
  ]
}
```

- [ ] **Step 3: Validate JSON syntax**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
path = Path("docs/operator/source-inputs/2026-07-17-shadowpriest-source-search-results.json")
data = json.loads(path.read_text(encoding="utf-8"))
assert data["deck_name"] == "ShadowPriest"
assert len(data["records"]) == 5
assert all(row["url"].startswith("https://") for row in data["records"])
print("source input ok")
'@ | python -
```

Expected:

```text
source input ok
```

- [ ] **Step 4: Confirm no record claims proof by itself**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
data = json.loads(Path("docs/operator/source-inputs/2026-07-17-shadowpriest-source-search-results.json").read_text(encoding="utf-8"))
for row in data["records"]:
    assert row["expected_strength"] in {"acquisition_seed_only", "claim_extraction_required"}
print("all records are seeds, not proof")
'@ | python -
```

Expected:

```text
all records are seeds, not proof
```

---

### Task 3: Generate Fresh ShadowPriest Package

**Files:**
- Generated: `outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/`
- Read: `docs/operator/source-inputs/2026-07-17-shadowpriest-source-search-results.json`

**Interfaces:**
- Consumes: ShadowPriest deck code, runtime root, current source-search JSON.
- Produces: validated generated package under `04_package`.

- [ ] **Step 1: Remove only the previous generated output for this run**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$out = "outputs\2026-07-17-source-backed-strong-optimal\ShadowPriest"
if (Test-Path $out) {
  Remove-Item -LiteralPath $out -Recurse -Force
}
New-Item -ItemType Directory -Force $out | Out-Null
```

Expected: exit code 0. This removes only the generated output directory for this plan.

- [ ] **Step 2: Run configure with source-autopilot input**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
hsconfig configure `
  --deck-name "ShadowPriest" `
  --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
  --runtime-root "C:\Users\darbo\Desktop\HS" `
  --out "outputs\2026-07-17-source-backed-strong-optimal\ShadowPriest" `
  --auto-source `
  --source-search-results-json "docs\operator\source-inputs\2026-07-17-shadowpriest-source-search-results.json" `
  --json
```

Expected: exit code 0 and a JSON payload with `status` not equal to `error`.

- [ ] **Step 3: Confirm generated package files exist**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$package = "outputs\2026-07-17-source-backed-strong-optimal\ShadowPriest\04_package"
@(
  "$package\CustomConfig\deck\GlobalValues.json",
  "$package\CustomConfig\deck\Mulligan.json",
  "$package\CustomConfig\deck\SW_448.json",
  "$package\reports\operator_summary.json",
  "$package\reports\source_evidence_closure.json",
  "$package\reports\source_to_runtime_explainability.json",
  "$package\reports\source_contract_audit.json",
  "$package\reports\strong_promotion_report.json",
  "$package\reports\source_bundle.json"
) | ForEach-Object {
  if (-not (Test-Path $_)) { throw "missing generated file: $_" }
}
"shadowpriest package files ok"
```

Expected:

```text
shadowpriest package files ok
```

- [ ] **Step 4: Validate the package**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
hsconfig validate --package "outputs\2026-07-17-source-backed-strong-optimal\ShadowPriest\04_package" --json
```

Expected: exit code 0 and validation status indicating a valid package.

---

### Task 4: Verify ShadowPriest Source/Contract Acceptance

**Files:**
- Read: `outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package/reports/operator_summary.json`
- Read: `outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package/reports/source_evidence_closure.json`
- Read: `outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package/reports/strong_promotion_report.json`
- Read: `outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package/CustomConfig/deck/SW_448.json`
- Read: `outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package/CustomConfig/deck/Mulligan.json`

**Interfaces:**
- Consumes: generated ShadowPriest package.
- Produces: pass/fail proof that the package is load-safe, not default-only, and Darkbishop is effect-only.

- [ ] **Step 1: Assert operator summary baseline**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
root = Path("outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package")
operator = json.loads((root / "reports/operator_summary.json").read_text(encoding="utf-8"))
assert operator["technical_status"] == "VALID_PACKAGE", operator["technical_status"]
assert operator["runtime_load_safe"] is True
assert operator["runtime_apply_allowed"] is True
assert operator["runtime_apply_contract"]["apply_authority"] == "reports/operator_summary.json"
assert operator["source_status_diagnostic_only"] is True
assert operator["source_status_apply_blocking"] is False
assert operator["default_only_runtime_surfaces"] == []
assert operator["default_only_runtime_surface_details"] == []
assert operator["no_default_only_runtime_status"] == "clean"
assert operator["source_backed_status"] in {"SOURCE_BACKED_STRONG", "SOURCE_BACKED_PARTIAL"}
print(operator["source_backed_status"])
print(operator["first_missing_source_action"])
'@ | python -
```

Expected:

```text
SOURCE_BACKED_STRONG
none
```

If the first line is `SOURCE_BACKED_PARTIAL`, do not relabel it. Continue to Task 6 and close the reported source gap with stronger public evidence.

- [ ] **Step 2: Assert no hidden default-only rows in explainability**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
root = Path("outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package")
explain = json.loads((root / "reports/source_to_runtime_explainability.json").read_text(encoding="utf-8"))
text = json.dumps(explain, sort_keys=True)
assert '"default_only": true' not in text.lower()
assert '"status": "default_only"' not in text.lower()
print("no hidden default-only explainability rows")
'@ | python -
```

Expected:

```text
no hidden default-only explainability rows
```

- [ ] **Step 3: Assert Darkbishop effect semantics exist**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
root = Path("outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package/CustomConfig/deck")
rows = json.loads((root / "SW_448.json").read_text(encoding="utf-8"))
blob = json.dumps(rows).lower()
assert "hero_power" in blob or "hero power" in blob or "shadow" in blob or "mind spike" in blob
print("SW_448 effect semantics present")
'@ | python -
```

Expected:

```text
SW_448 effect semantics present
```

- [ ] **Step 4: Assert Darkbishop is not a Mulligan keep**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
root = Path("outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package/CustomConfig/deck")
mulligan = json.loads((root / "Mulligan.json").read_text(encoding="utf-8"))
blob = json.dumps(mulligan)
assert "SW_448" not in blob
assert "Darkbishop Benedictus" not in blob
print("SW_448 absent from Mulligan")
'@ | python -
```

Expected:

```text
SW_448 absent from Mulligan
```

- [ ] **Step 5: Assert source reports agree**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
root = Path("outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package")
operator = json.loads((root / "reports/operator_summary.json").read_text(encoding="utf-8"))
closure = json.loads((root / "reports/source_evidence_closure.json").read_text(encoding="utf-8"))
promotion = json.loads((root / "reports/strong_promotion_report.json").read_text(encoding="utf-8"))
assert closure["source_backed_status"] == operator["source_backed_status"]
assert promotion["source_backed_status"] == operator["source_backed_status"]
assert closure["first_missing_source_action"] == operator["first_missing_source_action"]
assert promotion["first_missing_source_action"] == operator["first_missing_source_action"]
assert closure["source_status_apply_blocking"] is False
assert promotion["source_status_apply_blocking"] is False
print("source reports agree")
'@ | python -
```

Expected:

```text
source reports agree
```

---

### Task 5: Verify Universal Wild No-Block Matrix

**Files:**
- Read/verify: `tests/test_universal_wild_no_block_matrix.py`
- Generated: `outputs/2026-07-17-source-backed-strong-optimal/matrix/`

**Interfaces:**
- Consumes: the twelve-deck matrix.
- Produces: proof that all listed valid decks remain load-safe and no source-depth warning blocks generation.

- [ ] **Step 1: Run existing no-block matrix test**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Generate real package outputs for the twelve deck inputs**

Run this PowerShell script:

```powershell
cd C:\Users\darbo\Documents\HSConfig
$runtimeRoot = "C:\Users\darbo\Desktop\HS"
$baseOut = "outputs\2026-07-17-source-backed-strong-optimal\matrix"
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
if (Test-Path $baseOut) {
  Remove-Item -LiteralPath $baseOut -Recurse -Force
}
foreach ($deck in $decks) {
  $out = Join-Path $baseOut $deck.Name
  hsconfig configure --deck-name $deck.Name --deck-code $deck.Code --runtime-root $runtimeRoot --out $out --online-source --auto-source --json | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "configure failed for $($deck.Name)" }
}
"matrix configure complete"
```

Expected:

```text
matrix configure complete
```

- [ ] **Step 3: Assert matrix package invariants**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
base = Path("outputs/2026-07-17-source-backed-strong-optimal/matrix")
names = [
    "ShadowPriest", "CtAPaladin", "PirateRogue", "BigShaman",
    "Discolock", "TreantDruid", "ImbueMage", "MechPala",
    "Kingslayer", "Boarlock", "PirateDH", "CuteWarrior",
]
for name in names:
    package = base / name / "04_package"
    operator = json.loads((package / "reports/operator_summary.json").read_text(encoding="utf-8"))
    assert operator["technical_status"] == "VALID_PACKAGE", (name, operator["technical_status"])
    assert operator["runtime_load_safe"] is True, name
    assert operator["runtime_apply_allowed"] is True, name
    assert operator["source_status_diagnostic_only"] is True, name
    assert operator["source_status_apply_blocking"] is False, name
    assert operator["source_backed_status"] in {"SOURCE_BACKED_STRONG", "SOURCE_BACKED_PARTIAL"}, name
    assert isinstance(operator["first_missing_source_action"], str), name
    if operator["source_backed_status"] != "SOURCE_BACKED_STRONG":
        assert operator["first_missing_source_action"] != "none", name
    assert operator["default_only_runtime_surfaces"] == [], name
    assert operator["default_only_runtime_surface_details"] == [], name
print("matrix invariants ok")
'@ | python -
```

Expected:

```text
matrix invariants ok
```

---

### Task 6: Close Any ShadowPriest Source Gap Honestly

**Files:**
- Read: generated ShadowPriest reports
- Modify only if stronger source capture is needed: `docs/operator/source-inputs/2026-07-17-shadowpriest-source-search-results.json`

**Interfaces:**
- Consumes: `first_missing_source_action`, source reports, current public guide pages.
- Produces: either `SOURCE_BACKED_STRONG` or a precise blocker showing which exact source-to-runtime link is still missing.

- [ ] **Step 1: Read the first missing source action**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
root = Path("outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package/reports")
operator = json.loads((root / "operator_summary.json").read_text(encoding="utf-8"))
print("source_backed_status=", operator["source_backed_status"])
print("first_missing_source_action=", operator["first_missing_source_action"])
print("source_status_reasons=", operator["source_status_reasons"])
'@ | python -
```

Expected strong path:

```text
source_backed_status= SOURCE_BACKED_STRONG
first_missing_source_action= none
```

If strong path is reached, skip the remaining steps in this task.

- [ ] **Step 2: Inspect source-to-runtime explainability for the blocking card or surface**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
root = Path("outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package/reports")
explain = json.loads((root / "source_to_runtime_explainability.json").read_text(encoding="utf-8"))
rows = explain.get("rows", explain if isinstance(explain, list) else [])
for row in rows:
    text = json.dumps(row, sort_keys=True)
    if "missing" in text.lower() or "gap" in text.lower() or "default_only" in text.lower():
        print(text[:1000])
'@ | python -
```

Expected: printed rows identify exact missing card, claim kind, or runtime surface.

- [ ] **Step 3: Add only verified full-text source rows**

If Task 6 Step 2 identifies a missing `mulligan_keep`, `mulligan_discard`, `targeting_rule`, `gameplan_posture`, or `card_role`, update `docs/operator/source-inputs/2026-07-17-shadowpriest-source-search-results.json` by adding only rows that satisfy all of these facts:

```text
source_visibility = full_text_candidate
deck_match_scope = archetype_matched or deck_matched
expected_strength = claim_extraction_required
url starts with https://
the page contains explicit text for the missing claim family
```

Do not add a row for a decklist-only, stats-only, search-result-only, snippet-only, or card-database-only source as a strong proof source.

- [ ] **Step 4: Re-run ShadowPriest configure after source update**

Run Task 3 Step 1, Task 3 Step 2, Task 4 Step 1, Task 4 Step 2, Task 4 Step 3, Task 4 Step 4, and Task 4 Step 5 again.

Expected: either `SOURCE_BACKED_STRONG` with `first_missing_source_action=none`, or a precise remaining gap. Never manually edit generated reports to force strong.

---

### Task 7: Add Regression Test Only If Execution Exposes A Defect

**Files:**
- Modify conditionally: `tests/test_shadowpriest_fresh_closure_proof.py`
- Modify conditionally: `tests/test_configure_online_source.py`
- Modify conditionally: `tests/test_universal_wild_no_block_matrix.py`
- Modify conditionally: source module that failed the test

**Interfaces:**
- Consumes: any concrete failure from Tasks 3-6.
- Produces: one failing regression test and the smallest implementation fix.

- [ ] **Step 1: If all Tasks 3-6 pass, do not modify source code**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --name-only -- src tests
```

Expected if no implementation defect exists: no new source/test changes from this plan beyond pre-existing dirty work.

- [ ] **Step 2: If a defect exists, write the failing test first**

Use the narrowest matching file:

```text
tests/test_shadowpriest_fresh_closure_proof.py for ShadowPriest/Darkbishop regressions
tests/test_configure_online_source.py for configure/source-acquisition wiring regressions
tests/test_universal_wild_no_block_matrix.py for no-block/default-only regressions
tests/test_source_status_resolver.py for source-status resolution regressions
```

The test must assert the exact failed invariant from Tasks 3-6. Example for a hidden default-only defect:

```python
def test_shadowpriest_configure_does_not_hide_default_only_surface(tmp_path):
    result = run_shadowpriest_configure(tmp_path)
    operator = read_operator_summary(result)

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["source_status_apply_blocking"] is False
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["no_default_only_runtime_status"] == "clean"
```

- [ ] **Step 3: Run the failing test**

Run the exact test path. Example:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_shadowpriest_fresh_closure_proof.py::test_shadowpriest_configure_does_not_hide_default_only_surface -q
```

Expected before fix: the test fails for the observed invariant.

- [ ] **Step 4: Implement the smallest fix**

Change only the module responsible for the failing invariant:

```text
src/hsconfig/source_status_resolver.py for source status decisions
src/hsconfig/commands/configure.py for configure stage wiring
src/hsconfig/source_acquisition.py for acquired source records
src/hsconfig/source_autopilot.py for evidence row extraction
src/hsconfig/package_builder.py for package/report emission
src/hsconfig/operator_summary.py for operator fields
```

Do not add another status model or apply gate.

- [ ] **Step 5: Run the exact failing test again**

Run the same command from Step 3.

Expected after fix: pass.

---

### Task 8: Final Verification

**Files:**
- Verify all generated ShadowPriest and matrix outputs.
- Verify any modified source, tests, docs, and source-input JSON.

**Interfaces:**
- Consumes: final local worktree and generated packages.
- Produces: completion evidence suitable for handoff.

- [ ] **Step 1: Run focused source/contract suite**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py tests/test_source_bundle.py tests/test_strong_promotion_report.py tests/test_source_evidence_closure.py tests/test_shadowpriest_fresh_closure_proof.py tests/test_universal_wild_no_block_matrix.py tests/test_configure_online_source.py tests/test_operator_docs_contract_policy.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run skill sync check**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python scripts/sync_installed_skill.py --check
```

Expected: installed HSConfig skill is in sync.

- [ ] **Step 3: Run diff hygiene**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --check
```

Expected: exit code 0. Windows LF/CRLF conversion warnings are acceptable; whitespace errors are not.

- [ ] **Step 4: Confirm upstream status remains current**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git rev-list --left-right --count HEAD...origin/main
git status --short --branch
```

Expected: first command prints `0 0`. Status shows only intended dirty files and generated source-input/plan files, with no runtime logs or replay/private evidence.

- [ ] **Step 5: Summarize generated ShadowPriest status**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
@'
import json
from pathlib import Path
root = Path("outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest/04_package")
operator = json.loads((root / "reports/operator_summary.json").read_text(encoding="utf-8"))
print("technical_status:", operator["technical_status"])
print("runtime_apply_mode:", operator["runtime_apply_mode"])
print("source_backed_status:", operator["source_backed_status"])
print("first_missing_source_action:", operator["first_missing_source_action"])
print("default_only_runtime_surfaces:", operator["default_only_runtime_surfaces"])
'@ | python -
```

Expected ideal output:

```text
technical_status: VALID_PACKAGE
runtime_apply_mode: load_safe_apply
source_backed_status: SOURCE_BACKED_STRONG
first_missing_source_action: none
default_only_runtime_surfaces: []
```

If `source_backed_status` remains `SOURCE_BACKED_PARTIAL`, the plan is not complete for the user's requested Strong outcome; report the exact remaining source action and continue source acquisition rather than forcing status.

---

## Acceptance Criteria

- [ ] Repository was refreshed and upstream state was confirmed as `0 0` before execution.
- [ ] ShadowPriest package was regenerated under `outputs/2026-07-17-source-backed-strong-optimal/ShadowPriest`.
- [ ] ShadowPriest package validates.
- [ ] ShadowPriest `operator_summary.json` reports `technical_status=VALID_PACKAGE`.
- [ ] ShadowPriest `operator_summary.json` reports `runtime_apply_mode=load_safe_apply`.
- [ ] ShadowPriest `operator_summary.json` reports `source_status_apply_blocking=false`.
- [ ] ShadowPriest has no hidden or visible default-only runtime surfaces.
- [ ] ShadowPriest reaches `SOURCE_BACKED_STRONG` only if the fetched/normalized source evidence actually closes the source-to-runtime chain.
- [ ] `SW_448.json` preserves Darkbishop Benedictus hero-power-transform semantics.
- [ ] `Mulligan.json` does not keep `SW_448` unless an explicit opening-hand source supports that keep.
- [ ] All twelve listed Wild decks generate load-safe packages or pass the existing no-block matrix tests.
- [ ] Any non-strong deck reports a non-`none` `first_missing_source_action`.
- [ ] No deck is blocked by partial source status alone.
- [ ] No new dependency is added.
- [ ] No generated runtime evidence, logs, replay files, or private runtime exports are staged.
- [ ] Focused pytest suite passes.
- [ ] `scripts/sync_installed_skill.py --check` passes.
- [ ] `git diff --check` exits 0.

## Subagent Execution Split

- [ ] **Explorer subagent, read-only:** inspect `docs/operator/README.md`, `.agents/skills/hsconfig/SKILL.md`, `src/hsconfig/commands/configure.py`, and `src/hsconfig/source_status_resolver.py`; confirm the plan uses the normal configure path and not a second apply/status path.
- [ ] **Source QA subagent, read-only:** inspect the generated `source_acquisition`, `source_autopilot`, `source_documents.json`, and source reports for ShadowPriest; verify seed URLs did not count as strong without claim extraction.
- [ ] **Runtime Contract reviewer, read-only:** inspect generated `operator_summary.json`, `source_to_runtime_explainability.json`, `source_evidence_closure.json`, `strong_promotion_report.json`, `SW_448.json`, and `Mulligan.json`; confirm no default-only, no source apply blocking, and Darkbishop effect-only behavior.
- [ ] **Matrix reviewer, read-only:** inspect matrix outputs or `tests/test_universal_wild_no_block_matrix.py` results; confirm all listed decks remain load-safe and non-blocked.
- [ ] **Main worker:** perform source-input creation, configure runs, verification commands, and any minimal TDD fix if a real defect appears.

No subagent should write files unless the main worker explicitly assigns a single isolated file area. No subagent should run destructive git commands.

## Self-Review

- Spec coverage: The plan covers repo freshness, optimal ShadowPriest generation, no hidden default-only, honest `SOURCE_BACKED_STRONG`, Darkbishop effect-not-mulligan, twelve-deck no-block behavior, current online source seeds, and final verification.
- Placeholder scan: The plan contains no placeholder markers, deferred implementation wording, or unspecified test commands.
- Type and command consistency: The plan uses existing CLI arguments from `src/hsconfig/cli_parser.py`: `configure`, `--deck-name`, `--deck-code`, `--runtime-root`, `--out`, `--online-source`, `--auto-source`, `--source-search-results-json`, `--json`, and `validate --package`.

## Execution Handoff

Plan complete and ready for execution with:

```text
Setze den Plan SubAgent Driven um
```
