# HSConfig Source Closure Intake v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use read-only subagents for source-contract audit, online-source workflow audit, ShadowPriest canary audit, and final review. The main agent owns all tracked writes and all commits.

**Goal:** Add a thin, diagnostic-only source-closure intake layer that makes current-source acquisition, claim-kind eligibility, default-only detection, and promotion readiness auditable before CustomConfig generation. The result must keep every supplied Wild deck load-safe, must not block package generation because a source is incomplete, must not hide default-only runtime surfaces, and must never promote a deck to `SOURCE_BACKED_STRONG` unless the existing source-contract resolver can prove it.

**Architecture:** Keep `src/hsconfig/source_status_resolver.py`, `src/hsconfig/source_evidence_closure.py`, `src/hsconfig/strong_promotion_report.py`, and `reports/operator_summary.json` as the existing authority chain. Add one pure intake module that turns `src/hsconfig/source_candidate_registry.py` rows and fetched source records into a deterministic receipt. Wire that receipt into the existing `configure --online-source --auto-source` report tree as diagnostics only. Candidate URLs, deck pages, search pages, snippets, and context-only rows remain acquisition seeds and support evidence, not promotion authority.

**Tech Stack:** Python dataclasses, pytest, existing HSConfig CLI, existing source-candidate registry, existing source acquisition/autopilot pipeline, existing operator report JSON, PowerShell on Windows.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Start every implementation session with `git fetch --all --prune --tags`, `git remote prune origin`, `git status --short --branch`, and `git rev-list --left-right --count HEAD...origin/main`.
- End every implementation session with `git status --short --branch` showing no uncommitted tracked changes.
- Do not push unless the user explicitly asks to push.
- Do not use destructive git cleanup. Preserve unrelated user changes if any appear.
- Do not apply generated packages to HearthRanger runtime.
- Do not add a second runtime apply authority.
- `reports/operator_summary.json` remains the normal apply authority.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a runtime gate and not an apply gate.
- `source_status_apply_blocking` must remain `false` for source-depth gaps.
- Default-only runtime surfaces must be visible and must prevent `SOURCE_BACKED_STRONG`.
- Default-only runtime surfaces must not block valid load-safe package generation.
- Context-only sources, decklist-only sources, source-candidate URLs, category pages, and snippets must not promote a deck to `SOURCE_BACKED_STRONG`.
- `Darkbishop Benedictus` / `SW_448` must preserve start-of-game hero-power-transform semantics in runtime card config while staying out of opening-hand `Mulligan.json` unless a source explicitly says to keep the card in the mulligan.
- Keep `Presume.json` and `Concede.json` outside normal generated CustomConfig packages.
- Generated proof packages must stay under ignored `outputs/2026-07-18-source-closure-intake-v2/`.
- Generated temporary diagnostics must stay under ignored `tmp/2026-07-18-source-closure-intake-v2/`.

---

## File Map

- Create: `src/hsconfig/source_closure_intake.py`
  - Pure receipt builder for candidate rows and fetched source metadata.
- Create: `tests/test_source_closure_intake.py`
  - Unit coverage for receipt semantics and non-promotion boundaries.
- Modify: `src/hsconfig/commands/configure.py`
  - Write the intake receipt into the existing output report tree during online-source/autosource runs.
- Modify only if the existing configure command delegates the report write elsewhere: `src/hsconfig/source_autopilot.py`
  - Attach receipt creation at the existing source-autopilot report boundary.
- Modify: `tests/test_configure_online_source.py`
  - Lock configure report output and prove the receipt is diagnostic-only.
- Modify: `tests/test_universal_wild_no_block_matrix.py`
  - Extend the 12-deck matrix to prove the new receipt does not block generation and does not hide default-only surfaces.
- Modify: `tests/test_shadowpriest_e2e.py`
  - Keep the ShadowPriest `SW_448` effect canary intact and add receipt assertions.
- Modify if operator summaries already centralize configure diagnostics: `src/hsconfig/operator_summary.py`
  - Add a compact diagnostic pointer or summary only; do not override canonical status fields.
- Modify if operator summary is touched: `tests/test_operator_summary.py`
  - Lock the diagnostic-only semantics.
- Modify: `docs/operator/source-builder-workflow.md`
  - Document the source-closure intake receipt and its authority boundary.
- Modify: `docs/operator/universal-wild-no-block-contract.md`
  - Document no-block behavior, default-only visibility, and Strong promotion boundary.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Sync repo-local operator skill guidance. Do not edit the user-global installed skill unless a separate packaging task explicitly asks for it.

---

### Task 1: Prove Fresh Clean Baseline

**Files:** git metadata only.

**Commit:** none.

- [ ] **Step 1: Refresh repository state**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git fetch --all --prune --tags
git remote prune origin
git status --short --branch
git rev-list --left-right --count HEAD...origin/main
```

Expected output:

```text
## codex/hsconfig-canonical-source-status-sync
<ahead-count>	0
```

If the second number is not `0`, inspect the divergence before editing files.

- [ ] **Step 2: Verify existing contract tests before edits**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_candidate_registry_matrix.py tests/test_source_status_resolver.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_e2e.py -q
```

Expected output:

```text
... passed
```

If this fails, capture the failing tests and fix only defects directly related to source-contract, default-only, or ShadowPriest canary behavior before continuing.

---

### Task 2: Add Pure Source Closure Intake Receipt

**Files:**
- Create: `src/hsconfig/source_closure_intake.py`
- Create: `tests/test_source_closure_intake.py`

**Commit:** `test: cover source closure intake receipts` followed by `feat: add source closure intake receipts`.

- [ ] **Step 1: Write failing receipt tests first**

Create `tests/test_source_closure_intake.py` with tests that import the planned module and assert exact behavior:

```python
from hsconfig.source_closure_intake import build_source_closure_intake_receipt


def test_shadowpriest_receipt_is_diagnostic_and_current_source_ready():
    receipt = build_source_closure_intake_receipt(
        "ShadowPriest",
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    )

    assert receipt["schema_version"] == 1
    assert receipt["authority"] == "diagnostic_only"
    assert receipt["source_status_apply_blocking"] is False
    assert receipt["first_missing_source_action"] == "none"
    assert any("hearthpwn.com" in url for url in receipt["used_urls"])
    assert receipt["promotion_eligible_seed_count"] >= 1


def test_big_shaman_historical_seed_remains_partial_action():
    receipt = build_source_closure_intake_receipt(
        "BigShaman",
        "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
    )

    assert receipt["authority"] == "diagnostic_only"
    assert receipt["source_status_apply_blocking"] is False
    assert receipt["first_missing_source_action"] == (
        "add_current_big_shaman_full_text_mulligan_or_gameplan_source"
    )
    assert receipt["promotion_eligible_seed_count"] == 0


def test_context_only_rows_do_not_become_runtime_claims():
    receipt = build_source_closure_intake_receipt(
        "MechPala",
        "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
    )

    context_only_rows = [
        row for row in receipt["source_rows"]
        if row["source_visibility"] == "context_only"
    ]
    assert context_only_rows
    assert all(row["expected_claim_kinds"] == [] for row in context_only_rows)
    assert receipt["source_status_apply_blocking"] is False
```

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_closure_intake.py -q
```

Expected red output:

```text
ModuleNotFoundError: No module named 'hsconfig.source_closure_intake'
```

- [ ] **Step 2: Implement the pure receipt module**

Create `src/hsconfig/source_closure_intake.py` with no network access and no file writes:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from hsconfig.source_candidate_registry import SourceCandidate, source_candidates_for_deck


@dataclass(frozen=True)
class SourceClosureIntakeSourceRow:
    url: str
    source_family: str
    source_visibility: str
    strength_ceiling: str
    expected_claim_kinds: tuple[str, ...]
    first_missing_source_action: str
    promotion_eligible_seed: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "source_family": self.source_family,
            "source_visibility": self.source_visibility,
            "strength_ceiling": self.strength_ceiling,
            "expected_claim_kinds": list(self.expected_claim_kinds),
            "first_missing_source_action": self.first_missing_source_action,
            "promotion_eligible_seed": self.promotion_eligible_seed,
        }


@dataclass(frozen=True)
class SourceClosureIntakeReceipt:
    deck_name: str
    deck_code: str
    source_rows: tuple[SourceClosureIntakeSourceRow, ...]
    fetched_record_count: int

    def to_json(self) -> dict[str, Any]:
        used_urls = [row.url for row in self.source_rows]
        first_action = _first_missing_source_action(self.source_rows)
        promotion_count = sum(1 for row in self.source_rows if row.promotion_eligible_seed)
        return {
            "schema_version": 1,
            "authority": "diagnostic_only",
            "deck_name": self.deck_name,
            "deck_code": self.deck_code,
            "candidate_count": len(self.source_rows),
            "fetched_record_count": self.fetched_record_count,
            "used_urls": used_urls,
            "source_rows": [row.to_json() for row in self.source_rows],
            "non_promoting_support_urls": [
                row.url for row in self.source_rows if not row.promotion_eligible_seed
            ],
            "promotion_eligible_seed_count": promotion_count,
            "first_missing_source_action": first_action,
            "source_status_apply_blocking": False,
        }


def build_source_closure_intake_receipt(
    deck_name: str,
    deck_code: str,
    *,
    candidate_rows: Sequence[SourceCandidate] | None = None,
    fetched_records: Sequence[Mapping[str, object]] = (),
) -> dict[str, Any]:
    rows = candidate_rows if candidate_rows is not None else source_candidates_for_deck(deck_name)
    receipt_rows = tuple(_candidate_to_receipt_row(row) for row in rows)
    return SourceClosureIntakeReceipt(
        deck_name=deck_name,
        deck_code=deck_code,
        source_rows=receipt_rows,
        fetched_record_count=len(fetched_records),
    ).to_json()
```

Implement helpers in the same file:

```python
def _candidate_to_receipt_row(candidate: SourceCandidate) -> SourceClosureIntakeSourceRow:
    claim_kinds = tuple(getattr(candidate, "expected_claim_kinds", ()) or ())
    visibility = getattr(candidate, "source_visibility", "runtime_claims_possible")
    strength_ceiling = getattr(candidate, "strength_ceiling", "SOURCE_BACKED_PARTIAL")
    first_action = getattr(candidate, "first_missing_source_action", "add_current_full_text_source")
    return SourceClosureIntakeSourceRow(
        url=candidate.url,
        source_family=getattr(candidate, "source_family", "unknown"),
        source_visibility=visibility,
        strength_ceiling=strength_ceiling,
        expected_claim_kinds=claim_kinds if visibility != "context_only" else (),
        first_missing_source_action=first_action,
        promotion_eligible_seed=(
            visibility == "runtime_claims_possible"
            and strength_ceiling == "SOURCE_BACKED_STRONG"
            and first_action == "none"
        ),
    )


def _first_missing_source_action(rows: Sequence[SourceClosureIntakeSourceRow]) -> str:
    for row in rows:
        if row.first_missing_source_action != "none":
            return row.first_missing_source_action
    return "none"
```

If `SourceCandidate` uses different field names, inspect `src/hsconfig/source_candidate_registry.py` and map existing field names explicitly. Do not use broad `dict.__dict__` serialization.

- [ ] **Step 3: Prove receipt module green**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_closure_intake.py tests/test_source_candidate_registry_matrix.py -q
```

Expected output:

```text
... passed
```

---

### Task 3: Wire Receipt Into Configure Online-Source Reports

**Files:**
- Modify: `src/hsconfig/commands/configure.py`
- Modify if required by existing ownership: `src/hsconfig/source_autopilot.py`
- Modify: `tests/test_configure_online_source.py`

**Commit:** `feat: write source closure intake receipt`.

- [ ] **Step 1: Add failing configure report test**

Extend an existing `configure --online-source` test or add a new focused test in `tests/test_configure_online_source.py`:

```python
def test_configure_writes_diagnostic_source_closure_intake_receipt(tmp_path):
    out_dir = tmp_path / "shadowpriest"
    result = run_configure_cli(
        deck_name="ShadowPriest",
        deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        out_dir=out_dir,
        extra_args=["--online-source", "--auto-source", "--current-date", "2026-07-18"],
    )

    assert result.exit_code == 0
    receipt_path = out_dir / "reports" / "02_source_acquisition" / "source_closure_intake_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["authority"] == "diagnostic_only"
    assert receipt["source_status_apply_blocking"] is False
    assert receipt["first_missing_source_action"] == "none"
```

Use the existing CLI helper in the file. If the file uses `CliRunner`, `run_cli`, or direct `configure_main`, reuse that helper instead of adding a second test harness.

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_configure_online_source.py -q
```

Expected red output:

```text
FileNotFoundError
```

for `source_closure_intake_receipt.json`, or an assertion showing the receipt is not yet written.

- [ ] **Step 2: Write the receipt at the source acquisition report boundary**

In the existing report creation path, import:

```python
from hsconfig.source_closure_intake import build_source_closure_intake_receipt
```

Then write the receipt after candidate acquisition metadata is known and before final operator summary writing:

```python
receipt = build_source_closure_intake_receipt(
    deck_name=deck_name,
    deck_code=deck_code,
    fetched_records=source_fetch_records,
)
receipt_path = reports_dir / "02_source_acquisition" / "source_closure_intake_receipt.json"
receipt_path.parent.mkdir(parents=True, exist_ok=True)
receipt_path.write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
```

Use the existing local variable names for `deck_name`, `deck_code`, `reports_dir`, and fetched source records. If fetched records are not available at this boundary, pass `fetched_records=()` and leave fetch classification to a later narrow enhancement.

- [ ] **Step 3: Prove configure output remains load-safe**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_configure_online_source.py tests/test_configure_auto_source.py -q
```

Expected output:

```text
... passed
```

---

### Task 4: Add Compact Operator Summary Pointer Without Authority Drift

**Files:**
- Modify: `src/hsconfig/operator_summary.py` or the existing configure summary writer.
- Modify: `tests/test_operator_summary.py` or `tests/test_configure_online_source.py`.

**Commit:** `feat: summarize source closure intake diagnostics`.

- [ ] **Step 1: Add failing summary assertion**

Use the same configure fixture and assert the operator summary contains only a compact diagnostic summary:

```python
operator_summary = json.loads(
    (out_dir / "reports" / "operator_summary.json").read_text(encoding="utf-8")
)
intake_summary = operator_summary["source_closure_intake"]
assert intake_summary == {
    "authority": "diagnostic_only",
    "candidate_count": receipt["candidate_count"],
    "promotion_eligible_seed_count": receipt["promotion_eligible_seed_count"],
    "first_missing_source_action": receipt["first_missing_source_action"],
    "source_status_apply_blocking": False,
    "receipt_path": "reports/02_source_acquisition/source_closure_intake_receipt.json",
}
```

Run the focused test and verify it fails because the field is absent.

- [ ] **Step 2: Implement a summary helper**

Add a helper near existing operator summary construction:

```python
def summarize_source_closure_intake(receipt: Mapping[str, object]) -> dict[str, object]:
    return {
        "authority": "diagnostic_only",
        "candidate_count": int(receipt.get("candidate_count", 0)),
        "promotion_eligible_seed_count": int(receipt.get("promotion_eligible_seed_count", 0)),
        "first_missing_source_action": str(
            receipt.get("first_missing_source_action", "add_current_full_text_source")
        ),
        "source_status_apply_blocking": False,
        "receipt_path": "reports/02_source_acquisition/source_closure_intake_receipt.json",
    }
```

Attach this summary under `source_closure_intake`. Do not mutate existing `source_status`, `strong_promotion`, `source_status_apply_blocking`, or apply fields.

- [ ] **Step 3: Prove summary does not become promotion authority**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py tests/test_strong_promotion_report.py tests/test_configure_online_source.py -q
```

Expected output:

```text
... passed
```

---

### Task 5: Extend 12-Deck No-Block Matrix For Intake Receipts

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: `tests/test_shadowpriest_e2e.py`

**Commit:** `test: cover source intake no-block matrix`.

- [ ] **Step 1: Add matrix assertions for receipt diagnostics**

For each deck in the existing 12-deck matrix, assert:

```python
assert receipt["authority"] == "diagnostic_only"
assert receipt["source_status_apply_blocking"] is False
assert "source_rows" in receipt
assert isinstance(receipt["source_rows"], list)
```

For decks that are not currently fully sourced, assert they remain valid package candidates without false Strong:

```python
if deck_name in {"BigShaman", "MechPala", "Kingslayer", "Boarlock", "CuteWarrior"}:
    assert receipt["first_missing_source_action"] != "none"
    assert receipt["promotion_eligible_seed_count"] == 0
```

Do not require every deck to be `SOURCE_BACKED_STRONG`.

- [ ] **Step 2: Preserve ShadowPriest Darkbishop canary**

Keep or add these assertions in the ShadowPriest E2E test:

```python
assert "SW_448" not in mulligan_card_ids
assert card_config_by_id["SW_448"]["start_of_game_effect"] == "hero_power_transform"
assert operator_summary["source_closure_intake"]["authority"] == "diagnostic_only"
```

Adapt key names to the existing generated card JSON shape. Do not weaken the existing effect assertion.

- [ ] **Step 3: Run no-block and canary tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_e2e.py -q
```

Expected output:

```text
... passed
```

---

### Task 6: Sync Operator Documentation And Repo-Local Skill

**Files:**
- Modify: `docs/operator/source-builder-workflow.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`

**Commit:** `docs: document source closure intake boundary`.

- [ ] **Step 1: Document the receipt boundary**

In `docs/operator/source-builder-workflow.md`, add a concise section:

```markdown
## Source Closure Intake Receipt

`reports/02_source_acquisition/source_closure_intake_receipt.json` is a diagnostic receipt for candidate source rows and fetched source metadata. It is not an apply gate and does not promote decks by itself.

The receipt may show current guide URLs, support URLs, context-only URLs, first missing source actions, and promotion-eligible seed counts. `SOURCE_BACKED_STRONG` remains controlled by the source evidence closure and status resolver. Candidate URLs alone are not sufficient for Strong.
```

- [ ] **Step 2: Document default-only and no-block semantics**

In `docs/operator/universal-wild-no-block-contract.md`, add:

```markdown
Default-only runtime surfaces must be visible in diagnostics and must prevent `SOURCE_BACKED_STRONG`. They do not block valid load-safe package generation. Source-depth gaps set `source_status_apply_blocking=false`.
```

Also include the ShadowPriest boundary:

```markdown
For ShadowPriest, `SW_448` / Darkbishop Benedictus can be represented as an effect card because the start-of-game hero-power transform matters. It must not be emitted as an opening-hand keep unless a source explicitly says to mulligan-keep the card.
```

- [ ] **Step 3: Update repo-local HSConfig skill**

In `.agents/skills/hsconfig/SKILL.md`, add a short operator rule:

```markdown
- Treat `source_closure_intake_receipt.json` as diagnostic-only. It can explain source readiness and first missing actions, but it cannot promote a deck, block load-safe generation, or replace `operator_summary.json` as the apply authority.
- Never treat default-only runtime surfaces as success for `SOURCE_BACKED_STRONG`.
```

- [ ] **Step 4: Run docs and skill tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_docs_contract_policy.py tests/test_skill_files.py -q
```

Expected output:

```text
... passed
```

If either file is not covered by a current test, add the smallest documentation policy test that verifies the exact phrases `diagnostic-only`, `default-only`, and `SOURCE_BACKED_STRONG`.

---

### Task 7: Generate Ignored 12-Deck Proof Packages

**Files:**
- Generated ignored: `outputs/2026-07-18-source-closure-intake-v2/`
- Generated ignored: `tmp/2026-07-18-source-closure-intake-v2/`

**Commit:** none for generated ignored artifacts.

- [ ] **Step 1: Generate ShadowPriest package without applying runtime**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m hsconfig configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --out "outputs/2026-07-18-source-closure-intake-v2/ShadowPriest" --online-source --auto-source --source-fetch-timeout-seconds 10 --current-date 2026-07-18 --json
```

Expected:

```text
"status": "ok"
```

and the output tree contains:

```text
outputs/2026-07-18-source-closure-intake-v2/ShadowPriest/reports/operator_summary.json
outputs/2026-07-18-source-closure-intake-v2/ShadowPriest/reports/02_source_acquisition/source_closure_intake_receipt.json
```

- [ ] **Step 2: Generate the remaining proof deck packages**

Run equivalent non-apply commands for:

```text
CtAPaladin
PirateRogue
BigShaman
Discolock
TreantDruid
ImbueMage
MechPala
Kingslayer
Boarlock
PirateDH
CuteWarrior
```

Use the deck codes supplied by the user in the task request. Keep the output folder name exactly matching the deck name.

- [ ] **Step 3: Validate generated receipts and summaries with a temporary guard**

Create `tmp/2026-07-18-source-closure-intake-v2/guard_receipts.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

root = Path("outputs/2026-07-18-source-closure-intake-v2")
decks = [
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
    "CuteWarrior",
]

for deck in decks:
    package = root / deck
    operator_summary = json.loads((package / "reports/operator_summary.json").read_text())
    receipt = json.loads(
        (package / "reports/02_source_acquisition/source_closure_intake_receipt.json").read_text()
    )
    assert receipt["authority"] == "diagnostic_only", deck
    assert receipt["source_status_apply_blocking"] is False, deck
    assert operator_summary["source_closure_intake"]["authority"] == "diagnostic_only", deck
    assert operator_summary["source_closure_intake"]["source_status_apply_blocking"] is False, deck
    assert not (package / "Mulligan.json").read_text().count("SW_448") if deck == "ShadowPriest" else True
```

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python tmp/2026-07-18-source-closure-intake-v2/guard_receipts.py
```

Expected: no output and exit `0`.

---

### Task 8: Full Verification And Clean Finish

**Files:** all touched tracked files.

**Commit:** `chore: verify source closure intake v2`.

- [ ] **Step 1: Run focused verification**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_closure_intake.py tests/test_configure_online_source.py tests/test_configure_auto_source.py tests/test_source_status_resolver.py tests/test_strong_promotion_report.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_e2e.py -q
```

Expected output:

```text
... passed
```

- [ ] **Step 2: Run full verification**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest -q
git diff --check
git status --short --branch
```

Expected output:

```text
... passed
## codex/hsconfig-canonical-source-status-sync
```

`git status` must not show tracked modified files. Ignored generated outputs under `outputs/` and `tmp/` are acceptable only if ignored by git.

- [ ] **Step 3: Final audit with read-only subagent**

Ask a read-only reviewer to inspect:

```text
src/hsconfig/source_closure_intake.py
src/hsconfig/commands/configure.py
src/hsconfig/operator_summary.py
tests/test_source_closure_intake.py
tests/test_configure_online_source.py
tests/test_universal_wild_no_block_matrix.py
tests/test_shadowpriest_e2e.py
docs/operator/source-builder-workflow.md
docs/operator/universal-wild-no-block-contract.md
.agents/skills/hsconfig/SKILL.md
```

Reviewer verdict must explicitly answer:

```text
Does any candidate URL, receipt field, context-only source, or default-only runtime surface become promotion or apply authority?
Does ShadowPriest preserve the Darkbishop effect without keeping the card in mulligan?
Can a source-depth gap block load-safe package generation?
Is the worktree clean after tracked commits?
```

Fix any confirmed defect with a focused follow-up commit.

---

## Expected Final State

- `src/hsconfig/source_closure_intake.py` exists and is pure, deterministic, network-free, and write-free.
- Online source configure runs write `reports/02_source_acquisition/source_closure_intake_receipt.json`.
- `operator_summary.json` includes only a compact diagnostic pointer or summary for the intake receipt.
- No code path uses the intake receipt to apply runtime, block valid packages, or force `SOURCE_BACKED_STRONG`.
- Default-only runtime surfaces remain visible and prevent Strong.
- ShadowPriest remains the canary for effect-vs-card behavior: `SW_448` effect preserved, no mulligan keep.
- The 12 supplied Wild decks generate load-safe packages without runtime apply.
- All touched tracked files are committed.
- `git status --short --branch` shows a clean worktree.

## Final Verification Commands

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_closure_intake.py tests/test_configure_online_source.py tests/test_configure_auto_source.py tests/test_source_status_resolver.py tests/test_strong_promotion_report.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_e2e.py -q
python -m pytest -q
git diff --check
git status --short --branch
git rev-list --left-right --count HEAD...origin/main
```

Expected final output:

```text
... passed
## codex/hsconfig-canonical-source-status-sync
<ahead-count>	0
```
