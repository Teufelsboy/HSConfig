# ShadowPriest Live-Verified Configure and Guarded Apply Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a fresh live-verified ShadowPriest HSConfig package and install it into the active HearthRanger runtime only when the current package, source, semantic, and guarded apply contracts all pass.

**Architecture:** Use a two-phase normal operator flow. Phase 1 runs `hsconfig configure` without apply, validates the fresh package, and inspects the sole operator authority plus ShadowPriest-specific physical semantics. Phase 2 begins only for an allowed gate, creates a receipt-bound fake apply snapshot, then performs one explicit guarded apply and verifies package-to-runtime equality.

**Tech Stack:** Python 3.11, HSConfig CLI, deterministic JSON/SHA-256 receipts, PowerShell, pytest, Git, HearthRanger VisionAI `CustomConfig`.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Work directly on the existing sole `main` branch. Do not create a feature branch, worktree, pull request, shadow checkout, or second implementation version.
- Use deck name `ShadowPriest`.
- Use deck code `AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=`.
- Record Hearthstone deck ID `2737726722` and HDT deck ID `c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602` as operator identity metadata only. Do not invent CLI flags or edit unsupported runtime metadata for these IDs.
- Use runtime root `C:\Users\darbo\Desktop\HS`.
- Create only `outputs\ShadowPriest-2026-07-27-live-verified`; do not overwrite, delete, rename, or repair any earlier output.
- Use public live source URL `https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest`.
- The source must be fetched as `live_http` and normalized as `live_verified` before it can authorize apply.
- `reports/operator_summary.json` is the sole normal apply authority.
- Captured, fixture, manual, legacy, stale, or seed-only provenance must stop the run before a runtime write.
- Runtime writes are allowed only through `hsconfig apply`.
- Before the real apply, require a current receipt-bound `hsconfig apply --fake` snapshot. Use `--from-fake-receipt` for the real apply so package or runtime drift fails closed.
- Do not invoke HSTuner, parse replays, inspect win rate, tune after games, or claim gameplay optimality.
- Do not commit `outputs/`, apply receipts, runtime snapshots, HearthRanger logs, Hearthstone logs, HDT runtime exports, replay files, or runtime write history.
- If an implementation defect is discovered, stop this operational plan before editing production code. Start a separate systematic-debugging/TDD task and regenerate the package only after that fix is independently reviewed.
- Use `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` for Python verification.
- A successful runtime match proves installation integrity only. `RUNTIME_SAMPLED` and `GAMEPLAY_OPTIMALITY` remain `NOT_PROVEN`.

## Fixed paths and identities

Every task uses these exact values:

```powershell
$repoRoot = 'C:\Users\darbo\Documents\HSConfig'
$runtimeRoot = 'C:\Users\darbo\Desktop\HS'
$outRoot = Join-Path $repoRoot 'outputs\ShadowPriest-2026-07-27-live-verified'
$packageRoot = Join-Path $outRoot '04_package'
$configDir = 'shadowpriest'
$sourceUrl = 'https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest'
$deckName = 'ShadowPriest'
$deckCode = 'AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA='
$hsDeckId = '2737726722'
$hdtDeckId = 'c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602'
```

---

### Task 1: Establish the clean current execution baseline

**Files:**

- Inspect: `docs/operator/README.md`
- Inspect: `.agents/skills/hsconfig/SKILL.md`
- Inspect: `docs/operator/source-candidate-proof-decks.json`
- Run: `scripts/check_hsconfig_currentness.py`
- Run: `scripts/check_contract_guardrails.py`
- Run: `scripts/sync_installed_skill.py`

**Interfaces:**

- Consumes: Git `main`, `origin/main`, the installed HSConfig skill, and the repository contract spine.
- Produces: a clean, synchronized, guardrail-green baseline with no runtime write.

- [ ] **Step 1: Fetch current repository state**

Run:

```powershell
Set-Location 'C:\Users\darbo\Documents\HSConfig'
git fetch --all --prune --tags
git remote prune origin
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

Expected:

- branch is `main`;
- worktree has no tracked or untracked changes;
- local `HEAD` equals `origin/main`.

Stop before package generation if any expectation fails.

- [ ] **Step 2: Enforce machine-readable currentness**

Run:

```powershell
$currentness = python scripts/check_hsconfig_currentness.py --cwd . --json |
    ConvertFrom-Json
if ($currentness.branch -ne 'main' -or
    $currentness.dirty -ne $false -or
    $currentness.ahead_origin_main -ne 0 -or
    $currentness.behind_origin_main -ne 0 -or
    $currentness.clean_for_runtime_work -ne $true) {
    throw "HSConfig currentness gate failed: $($currentness | ConvertTo-Json -Compress)"
}
```

Expected: no exception.

- [ ] **Step 3: Verify installed skill and contract preflight**

Run:

```powershell
python scripts/sync_installed_skill.py --check
$preflight = hsconfig contract-preflight --repo-root . --json |
    ConvertFrom-Json
if ($preflight.status -ne 'PASS' -or
    $preflight.failures.Count -ne 0 -or
    $preflight.installed_skill_sync.status -ne 'in_sync' -or
    $preflight.runtime_write_performed -ne $false) {
    throw "HSConfig contract preflight failed: $($preflight | ConvertTo-Json -Depth 8 -Compress)"
}
```

Expected:

- installed skill is in sync;
- preflight status is `PASS`;
- failures are empty;
- `runtime_write_performed=false`.

- [ ] **Step 4: Run the repository contract guardrail**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python scripts/check_contract_guardrails.py
```

Expected:

- guardrail process exits `0`;
- installed-skill sync, contract-spine sentinel, and focused contract boundary tests report `OK`;
- the complete guardrail test slice passes.

- [ ] **Step 5: Confirm the output target is new**

Run:

```powershell
$outRoot = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified'
if (Test-Path -LiteralPath $outRoot) {
    throw "Fresh output path already exists; do not overwrite it: $outRoot"
}
git status --short
```

Expected:

- output path does not exist;
- Git status remains empty.

No commit is created in this task.

---

### Task 2: Generate the fresh package from live source without apply

**Files:**

- Create, ignored runtime artifact: `outputs/ShadowPriest-2026-07-27-live-verified/`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/configure_summary.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/02_source_acquisition/source_search_results.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/03_source_autopilot/source_documents.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/operator_summary.json`

**Interfaces:**

- Consumes: exact deck code, public live source URL, current local card data, and the clean Task 1 baseline.
- Produces: one fresh `04_package` plus live acquisition/receipt evidence; no runtime write.

- [ ] **Step 1: Confirm the registered candidate and exact invocation**

Run:

```powershell
$registry = Get-Content -LiteralPath 'docs\operator\source-candidate-proof-decks.json' -Raw |
    ConvertFrom-Json
$shadow = @($registry.decks | Where-Object deck_name -eq 'ShadowPriest')
if ($shadow.Count -ne 1) {
    throw "Expected exactly one ShadowPriest candidate registry row."
}
$expectedUrl = 'https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest'
if ($expectedUrl -notin @($shadow[0].candidate_urls)) {
    throw "The approved ShadowPriest source URL is not registered."
}
```

Expected: no exception.

- [ ] **Step 2: Run live configure without `--apply`**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
hsconfig configure `
    --deck-name 'ShadowPriest' `
    --deck-code 'AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=' `
    --runtime-root 'C:\Users\darbo\Desktop\HS' `
    --out 'outputs\ShadowPriest-2026-07-27-live-verified' `
    --online-source `
    --auto-source `
    --source-url 'https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest' `
    --current-date '2026-07-27' `
    --json
```

Expected:

- process exits `0`;
- `configure_summary.json` exists;
- `04_package` exists;
- command line does not contain `--apply`.

If the live fetch fails, preserve the newly created diagnostic output, report
the fetch/source blocker, and stop before Task 4.

- [ ] **Step 3: Prove Phase 1 performed no runtime write**

Run:

```powershell
$outRoot = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified'
$summary = Get-Content -LiteralPath (Join-Path $outRoot 'configure_summary.json') -Raw |
    ConvertFrom-Json
if ($summary.status -ne 'OK' -or
    $summary.apply_performed -ne $false -or
    $summary.runtime_package_match_status -ne 'not_checked' -or
    $null -ne $summary.runtime_package_match) {
    throw "Configure phase was not a clean no-apply build: $($summary | ConvertTo-Json -Depth 8 -Compress)"
}
$packageRoot = Join-Path $outRoot '04_package'
if (-not (Test-Path -LiteralPath $packageRoot -PathType Container)) {
    throw "Fresh 04_package is missing."
}
if (Test-Path -LiteralPath (Join-Path $packageRoot 'reports\runtime_apply_receipt.json')) {
    throw "A runtime apply receipt exists before apply."
}
```

Expected: no exception and no runtime apply receipt.

- [ ] **Step 4: Verify the acquisition was live and normalized**

Run:

```powershell
$outRoot = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified'
$acquisition = Get-Content -LiteralPath (
    Join-Path $outRoot '02_source_acquisition\source_search_results.json'
) -Raw | ConvertFrom-Json
$documents = Get-Content -LiteralPath (
    Join-Path $outRoot '03_source_autopilot\source_documents.json'
) -Raw | ConvertFrom-Json
$modes = @($acquisition.records | ForEach-Object {
    $_.acquisition_provenance.mode
} | Sort-Object -Unique)
$authorities = @($documents.source_documents | ForEach-Object {
    $_.acquisition_provenance.authority
} | Sort-Object -Unique)
if ('live_http' -notin $modes -or 'live_verified' -notin $authorities) {
    throw "Live source authority was not established. Modes=$modes Authorities=$authorities"
}
```

Expected:

- at least one acquisition record has mode `live_http`;
- at least one normalized source document has authority `live_verified`.

This step does not yet authorize apply; the package receipt and operator gate
must agree in Task 3.

- [ ] **Step 5: Confirm repository isolation**

Run:

```powershell
git status --short --branch
git check-ignore -v 'outputs/ShadowPriest-2026-07-27-live-verified'
```

Expected:

- branch remains clean apart from ignored output;
- the generated output is ignored.

No generated artifact is staged or committed.

---

### Task 3: Validate package authority and ShadowPriest semantics

**Files:**

- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/deck_identity.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/package_derivation_receipt.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/operator_summary.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/runtime_surface_ledger.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/per_card_config_readiness_report.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/source_to_runtime_explainability.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/globalvalues_profile.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/guide_claim_bundle.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/CustomConfig/shadowpriest/`

**Interfaces:**

- Consumes: the fresh Task 2 package.
- Produces: a strict validation verdict, exact source/apply authority verdict, and ShadowPriest physical semantic verdict.

- [ ] **Step 1: Run strict package validation**

Run:

```powershell
$packageRoot = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified\04_package'
$validation = hsconfig validate --package $packageRoot --json |
    ConvertFrom-Json
if ($validation.status -ne 'passed' -or $validation.errors.Count -ne 0) {
    throw "Strict package validation failed: $($validation | ConvertTo-Json -Depth 8 -Compress)"
}
```

Expected:

- `status=passed`;
- errors are empty;
- checked file count is greater than zero.

- [ ] **Step 2: Run package-mode contract preflight**

Run:

```powershell
$packageRoot = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified\04_package'
$preflight = hsconfig contract-preflight `
    --repo-root 'C:\Users\darbo\Documents\HSConfig' `
    --package $packageRoot `
    --json | ConvertFrom-Json
if ($preflight.status -ne 'PASS' -or
    $preflight.failures.Count -ne 0 -or
    $preflight.package_contract.package_contract_current -ne $true -or
    $preflight.package_contract.validation_status -ne 'passed' -or
    $preflight.package_contract.runtime_write_performed -ne $false) {
    throw "Package contract preflight failed: $($preflight | ConvertTo-Json -Depth 10 -Compress)"
}
```

Expected: current package contract, passed validation, and no runtime write.

- [ ] **Step 3: Verify exact deck and receipt-bound source authority**

Run from the repository root:

```powershell
@'
import json
from pathlib import Path

package = Path(r"outputs\ShadowPriest-2026-07-27-live-verified\04_package")
reports = package / "reports"

def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

identity = read(reports / "deck_identity.json")
operator = read(reports / "operator_summary.json")
receipt = read(package / "package_derivation_receipt.json")
claims = read(reports / "guide_claim_bundle.json")

assert identity["deck_name"] == "ShadowPriest"
assert identity["deck_slug"] == "shadowpriest"
assert identity["card_count_total"] == 30
assert identity["unresolved_card_count"] == 0
assert len(identity["deck_fingerprint"]) == 64
assert receipt["schema_version"] == 2
assert operator["package_derivation"]["schema_version"] == 2
assert operator["package_derivation"]["verified"] is True
assert operator["package_derivation"]["receipt_sha256"].startswith("sha256:")
assert claims["canonical_source_receipts"]
assert all(
    row["acquisition_provenance"]["mode"] == "live_http"
    and row["acquisition_provenance"]["authority"] == "live_verified"
    for row in claims["canonical_source_receipts"]
)
assert operator["technical_status"] == "VALID_PACKAGE"
assert operator["runtime_load_safe"] is True
assert operator["source_apply_eligible"] is True
assert operator["source_apply_eligibility_reasons"] == []
assert operator["runtime_apply_mode"] == "load_safe_apply"
assert operator["runtime_apply_allowed"] is True
assert operator["apply_policy"] in {"ALLOWED", "ALLOWED_WITH_WARNINGS"}
assert operator["runtime_apply_reason"] == "current_package_operator_gate_allowed"
print(json.dumps({
    "deck_fingerprint": identity["deck_fingerprint"],
    "source_apply_eligible": operator["source_apply_eligible"],
    "runtime_apply_allowed": operator["runtime_apply_allowed"],
}, sort_keys=True))
'@ | python -
```

Expected: all assertions pass.

If any assertion fails, record `operator_summary.json.primary_blockers`,
`runtime_apply_reason`, and `source_apply_eligibility_reasons`; do not continue
to Task 4.

- [ ] **Step 4: Verify physical ledger and ShadowPriest ownership**

Run:

```powershell
@'
import json
from pathlib import Path

package = Path(r"outputs\ShadowPriest-2026-07-27-live-verified\04_package")
reports = package / "reports"
deck = package / "CustomConfig" / "shadowpriest"

def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

ledger = read(reports / "runtime_surface_ledger.json")
readiness = read(reports / "per_card_config_readiness_report.json")
explain = read(reports / "source_to_runtime_explainability.json")
operator = read(reports / "operator_summary.json")
profile = read(reports / "globalvalues_profile.json")
mulligan = read(deck / "Mulligan.json")
darkbishop = read(deck / "SW_448.json")
mind_spike = read(deck / "EX1_625t.json")

ledger_hash = ledger["surface_ledger_sha256"]
assert len(ledger_hash) == 64
assert readiness["surface_ledger_sha256"] == ledger_hash
assert explain["surface_ledger_sha256"] == ledger_hash
assert operator["surface_ledger_sha256"] == ledger_hash
assert ledger["physical_errors"] == []
assert ledger["linked_runtime_entities"]["EX1_625t"] == {
    "source_card_id": "SW_448",
    "runtime_card_id": "EX1_625t",
    "link_kind": "hero_power_transform",
    "runtime_surface": "EX1_625t.json",
    "runtime_emitted": True,
}
assert "BeforeUseHeroPowerBonus" not in darkbishop
assert len(mind_spike["BeforeUseHeroPowerBonus"]["values"]) == 1
assert all(
    str(row.get("mulligan")) != "SW_448"
    for row in mulligan["Mulligan"]["values"]
)
assert profile["authority_parity"]["status"] == "matched"
assert (
    profile["authority_parity"]["authorized_overlay_keys"]
    == profile["authority_parity"]["emitted_overlay_keys"]
)
print(json.dumps({
    "surface_ledger_sha256": ledger_hash,
    "darkbishop_mulligan_keep": False,
    "linked_runtime_owner": "EX1_625t",
    "globalvalues_authority_parity": "matched",
}, sort_keys=True))
'@ | python -
```

Expected:

- all four consumer reports share the same 64-character physical ledger hash;
- no physical error exists;
- `SW_448 -> EX1_625t` ownership is exact;
- `SW_448` has no hero-power bonus and no Mulligan rule;
- `EX1_625t` owns exactly one hero-power bonus row;
- GlobalValues authority parity is `matched`.

- [ ] **Step 5: Verify Combo and forbidden output boundaries**

Run:

```powershell
$deckRoot = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified\04_package\CustomConfig\shadowpriest'
foreach ($forbidden in @('Presume.json', 'Concede.json', 'CardBehavior.json')) {
    if (Test-Path -LiteralPath (Join-Path $deckRoot $forbidden)) {
        throw "Forbidden normal-path runtime surface exists: $forbidden"
    }
}
if (Test-Path -LiteralPath (Join-Path $deckRoot 'Combo.json')) {
    $claims = Get-Content -LiteralPath (
        'outputs\ShadowPriest-2026-07-27-live-verified\04_package\reports\guide_claim_bundle.json'
    ) -Raw | ConvertFrom-Json
    $comboClaims = @($claims.claims | Where-Object claim_kind -eq 'combo_sequence')
    if ($comboClaims.Count -eq 0) {
        throw "Combo.json exists without an exact combo_sequence claim."
    }
}
```

Expected:

- forbidden legacy surfaces are absent;
- `Combo.json` is absent unless exact ordered combo evidence exists.

- [ ] **Step 6: Run focused ShadowPriest and runtime safety tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest -q -p no:cacheprovider `
    tests/test_shadowpriest_semantic_safety_wave.py `
    tests/test_shadowpriest_source_contract_acceptance.py `
    tests/test_runtime_package_match.py `
    tests/test_runtime_apply_receipts.py
```

Expected: all selected tests pass.

No package, source artifact, or test output is committed.

---

### Task 4: Create the receipt-bound pre-apply snapshot

**Files:**

- Create, ignored package artifact: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/runtime_apply_fake_receipt.json`
- Read only: `C:\Users\darbo\Desktop\HS\CustomConfig\deck_config.ini`
- Read only: `C:\Users\darbo\Desktop\HS\CustomConfig\shadowpriest\`

**Interfaces:**

- Consumes: the Task 3 apply-eligible package and current live runtime.
- Produces: a verified fake-apply receipt binding the exact package fingerprint to the exact pre-apply runtime snapshot; no runtime write.

- [ ] **Step 1: Recheck repository and package immediately before runtime access**

Run:

```powershell
$currentness = python scripts/check_hsconfig_currentness.py --cwd . --json |
    ConvertFrom-Json
if ($currentness.clean_for_runtime_work -ne $true -or
    $currentness.ahead_origin_main -ne 0 -or
    $currentness.behind_origin_main -ne 0) {
    throw "Repository drifted before pre-apply snapshot."
}
$packageRoot = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified\04_package'
$validation = hsconfig validate --package $packageRoot --json |
    ConvertFrom-Json
if ($validation.status -ne 'passed') {
    throw "Package drifted before pre-apply snapshot."
}
```

Expected: current repository and passed package.

- [ ] **Step 2: Create the fake apply receipt**

Run:

```powershell
$packageRoot = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified\04_package'
$runtimeRoot = 'C:\Users\darbo\Desktop\HS'
$fake = hsconfig apply `
    --package $packageRoot `
    --runtime-root $runtimeRoot `
    --fake `
    --json | ConvertFrom-Json
if ($fake.status -ne 'fake_apply_ready' -or
    $fake.runtime_write_performed -ne $false) {
    throw "Fake apply receipt was not created safely: $($fake | ConvertTo-Json -Depth 10 -Compress)"
}
```

Expected:

- `status=fake_apply_ready`;
- `runtime_write_performed=false`;
- the active runtime has not been modified.

- [ ] **Step 3: Validate the recorded pre-apply snapshot**

Run:

```powershell
$receiptPath = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified\04_package\reports\runtime_apply_fake_receipt.json'
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
if ($receipt.status -ne 'fake_apply_ready' -or
    $receipt.runtime_write_performed -ne $false -or
    $receipt.config_dir -ne 'shadowpriest' -or
    $receipt.runtime_root -ne 'C:\Users\darbo\Desktop\HS' -or
    [string]::IsNullOrWhiteSpace($receipt.package_fingerprint.package_sha256)) {
    throw "Fake receipt contents are incomplete."
}
if ($receipt.runtime_snapshot_before.config_dir -ne 'shadowpriest') {
    throw "Fake receipt runtime snapshot targets the wrong config directory."
}
```

Expected: exact runtime root, config directory, package hash, and before snapshot.

- [ ] **Step 4: Review gate before the destructive step**

The task reviewer must confirm:

- Task 3 strict validation and semantic assertions passed;
- `operator_summary.json.runtime_apply_allowed=true`;
- fake receipt is current and `runtime_write_performed=false`;
- package output, runtime root, and config directory are exact;
- no alternate writer or manual copy will be used.

If any item is unconfirmed, stop. No commit is created.

---

### Task 5: Apply through the single guarded writer

**Files:**

- Modify through `hsconfig apply` only: `C:\Users\darbo\Desktop\HS\CustomConfig\shadowpriest\`
- Modify through `hsconfig apply` only: `C:\Users\darbo\Desktop\HS\CustomConfig\deck_config.ini`
- Append through `hsconfig apply` only: `C:\Users\darbo\Desktop\HS\CustomConfig\hsconfig_write_history.jsonl`
- Create, ignored package artifact: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/runtime_apply_receipt.json`

**Interfaces:**

- Consumes: the exact Task 4 fake receipt, package, and unchanged live runtime snapshot.
- Produces: one guarded runtime installation or a rollback-backed failure; never a partial manual installation.

- [ ] **Step 1: Execute the receipt-bound real apply**

Run:

```powershell
$packageRoot = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified\04_package'
$runtimeRoot = 'C:\Users\darbo\Desktop\HS'
$fakeReceipt = Join-Path $packageRoot 'reports\runtime_apply_fake_receipt.json'
$apply = hsconfig apply `
    --package $packageRoot `
    --runtime-root $runtimeRoot `
    --from-fake-receipt $fakeReceipt `
    --json | ConvertFrom-Json
if ($apply.status -ne 'applied' -or
    $apply.runtime_write_performed -ne $true -or
    $apply.runtime_package_match.status -ne 'matched' -or
    $apply.fake_receipt_verified.status -ne 'verified') {
    throw "Guarded runtime apply did not complete with a matched receipt: $($apply | ConvertTo-Json -Depth 12 -Compress)"
}
```

Expected:

- `status=applied`;
- `runtime_write_performed=true`;
- fake receipt verification is `verified`;
- `runtime_package_match.status=matched`.

If package or runtime changed after Task 4, fake-receipt verification must fail
before the runtime write. If post-copy runtime matching fails, the guarded
writer must restore its rollback snapshot and return failure.

- [ ] **Step 2: Inspect the persisted apply receipt**

Run:

```powershell
$receiptPath = 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified\04_package\reports\runtime_apply_receipt.json'
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
if ($receipt.status -ne 'applied' -or
    $receipt.runtime_write_performed -ne $true -or
    $receipt.config_dir -ne 'shadowpriest' -or
    $receipt.runtime_package_match_status -ne 'matched' -or
    $receipt.runtime_package_match.status -ne 'matched') {
    throw "Persisted runtime apply receipt is not matched."
}
if ($receipt.runtime_snapshot_before.config_dir -ne 'shadowpriest' -or
    $receipt.runtime_snapshot_after.config_dir -ne 'shadowpriest') {
    throw "Runtime snapshots target the wrong configuration."
}
```

Expected: matched persisted receipt with both before and after snapshots.

- [ ] **Step 3: Run the independent read-only runtime match**

Run:

```powershell
$match = hsconfig runtime-match `
    --package 'C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-27-live-verified\04_package' `
    --runtime-root 'C:\Users\darbo\Desktop\HS' `
    --config-dir 'shadowpriest' `
    --json | ConvertFrom-Json
if ($match.status -ne 'matched' -or
    $match.runtime_write_performed -ne $false -or
    $match.semantic_mismatch_count -ne 0 -or
    $match.missing_in_runtime.Count -ne 0 -or
    $match.extra_in_runtime.Count -ne 0 -or
    $match.deck_config_ini.mentions_config_dir -ne $true) {
    throw "Read-only runtime match failed: $($match | ConvertTo-Json -Depth 10 -Compress)"
}
```

Expected:

- matched;
- zero missing, extra, or semantically changed files;
- `deck_config.ini` maps to `shadowpriest`;
- read-only match reports `runtime_write_performed=false`.

No runtime file is manually edited and no runtime evidence is committed.

---

### Task 6: Final package/runtime handoff and clean-state verification

**Files:**

- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/configure_summary.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/operator_summary.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/runtime_apply_receipt.json`
- Inspect: `outputs/ShadowPriest-2026-07-27-live-verified/04_package/reports/runtime_surface_ledger.json`

**Interfaces:**

- Consumes: all prior task verdicts and receipts.
- Produces: the final operator handoff with package, authority, installation, and unproven gameplay claims kept separate.

- [ ] **Step 1: Produce the final machine-readable verdict**

Run:

```powershell
@'
import json
from pathlib import Path

out = Path(r"outputs\ShadowPriest-2026-07-27-live-verified")
package = out / "04_package"
reports = package / "reports"

def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

identity = read(reports / "deck_identity.json")
operator = read(reports / "operator_summary.json")
apply_receipt = read(reports / "runtime_apply_receipt.json")
ledger = read(reports / "runtime_surface_ledger.json")

verdict = {
    "deck_name": "ShadowPriest",
    "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    "hs_deck_id": "2737726722",
    "hdt_deck_id": "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602",
    "identity": {
        "card_count": identity["card_count_total"],
        "unresolved": identity["unresolved_card_count"],
        "deck_fingerprint": identity["deck_fingerprint"],
    },
    "package": {
        "technical_status": operator["technical_status"],
        "source_apply_eligible": operator["source_apply_eligible"],
        "runtime_apply_allowed": operator["runtime_apply_allowed"],
        "surface_ledger_sha256": ledger["surface_ledger_sha256"],
    },
    "installation": {
        "status": apply_receipt["status"],
        "runtime_package_match": apply_receipt["runtime_package_match"]["status"],
        "config_dir": apply_receipt["config_dir"],
    },
    "runtime_sampled": "NOT_PROVEN",
    "gameplay_optimality": "NOT_PROVEN",
}
assert verdict["identity"]["card_count"] == 30
assert verdict["identity"]["unresolved"] == 0
assert verdict["package"]["technical_status"] == "VALID_PACKAGE"
assert verdict["package"]["source_apply_eligible"] is True
assert verdict["package"]["runtime_apply_allowed"] is True
assert verdict["installation"]["status"] == "applied"
assert verdict["installation"]["runtime_package_match"] == "matched"
print(json.dumps(verdict, indent=2, sort_keys=True))
'@ | python -
```

Expected: all assertions pass and the final JSON keeps runtime sampling and
gameplay optimality at `NOT_PROVEN`.

- [ ] **Step 2: Verify repository cleanliness and remote parity**

Run:

```powershell
git status --short --branch
$currentness = python scripts/check_hsconfig_currentness.py --cwd . --json |
    ConvertFrom-Json
if ($currentness.branch -ne 'main' -or
    $currentness.dirty -ne $false -or
    $currentness.ahead_origin_main -ne 0 -or
    $currentness.behind_origin_main -ne 0) {
    throw "Repository is not clean and synchronized after the run."
}
python scripts/sync_installed_skill.py --check
git diff --check
```

Expected:

- clean `main`;
- `ahead=0`, `behind=0`;
- installed skill remains synchronized;
- no generated or runtime evidence appears in Git status.

- [ ] **Step 3: Final independent review**

The final reviewer confirms:

- fresh output path was used;
- live source provenance is `live_http/live_verified`;
- exact deck identity is 30/0;
- package and derivation receipts are current;
- `operator_summary.json` alone authorized apply;
- Darkbishop was not inferred as a Mulligan keep;
- `SW_448 -> EX1_625t` linked ownership and physical output match;
- GlobalValues authority parity is exact;
- fake receipt bound the package and pre-apply runtime;
- real apply used only `--from-fake-receipt`;
- persisted and independent runtime matches are `matched`;
- no HSTuner, replay, win-rate, or gameplay-optimality claim was introduced.

- [ ] **Step 4: Commit boundary**

Do not create an operational commit. The fresh output and runtime receipts are
ignored/private evidence and must remain outside Git. If Git status is not
clean, stop and identify the unexpected path instead of staging it.

---

## Blocked-path handoff

If Task 2 or Task 3 produces a valid diagnostic package but
`runtime_apply_allowed=false`, end the run after these read-only actions:

```powershell
$operator = Get-Content -LiteralPath (
    'outputs\ShadowPriest-2026-07-27-live-verified\04_package\reports\operator_summary.json'
) -Raw | ConvertFrom-Json
$operator | Select-Object `
    technical_status, `
    runtime_load_safe, `
    source_apply_eligible, `
    source_apply_eligibility_reasons, `
    runtime_apply_mode, `
    runtime_apply_allowed, `
    runtime_apply_reason, `
    primary_blockers, `
    first_missing_source_action |
    ConvertTo-Json -Depth 8
```

Report the exact blocker and preserve:

- package validity;
- source authority;
- runtime apply authority;
- `RUNTIME_WRITE_PERFORMED=false`;
- `RUNTIME_SAMPLED=NOT_PROVEN`;
- `GAMEPLAY_OPTIMALITY=NOT_PROVEN`.

Do not run `hsconfig apply --fake`, real `hsconfig apply`, a manual copy, or an
alternate writer for a blocked package.
