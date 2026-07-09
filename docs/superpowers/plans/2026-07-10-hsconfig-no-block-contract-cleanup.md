# HSConfig No-Block Contract Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's no-block contract unambiguous: valid decks can produce and apply load-safe pre-run packages, while source depth, per-card richness, combo detail, and warning-only mechanics remain visible but non-blocking.

**Architecture:** This is a contract and documentation cleanup, not a pipeline rewrite. Keep the current apply gate unchanged, add source-backing metadata where it improves clarity, and align active docs, installed skill text, and tests around one vocabulary: runtime hard blocks vs. promotion/richness gaps.

**Tech Stack:** Python package under `src/hsconfig`, pytest tests, Markdown operator docs, repo-local skill under `.agents/skills/hsconfig`, installed skill sync via `scripts/sync_installed_skill.py`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` on branch `codex/hsconfig-no-block-contract-closure`.
- Do not add replay parsing, HDT parsing, winrate analysis, candidate promotion, HSTuner behavior, or post-game tuning to HSConfig.
- Do not change the core runtime apply gate unless a test proves the current gate contradicts the no-block contract.
- Minimal load-safe runtime apply remains `GlobalValues.json` plus `Mulligan.json`.
- Per-card `<CARDID>.json` files are HSConfig rich-output repo policy, not the minimal runtime-apply gate and not an official HearthRanger minimum.
- `SOURCE_BACKED_STRONG` is a source-confidence label, not the runtime-write gate.
- `load_safe_apply` is an HSConfig operator policy, not a HearthRanger public-doc term.
- Normal path must not emit `Presume.json` or `Concede.json`.
- Research artifacts are evidence, not operator instructions; normal operator path starts at `docs/operator/README.md`.
- Keep the installed skill in sync with `.agents/skills/hsconfig` before completion.

---

## File Structure

- Modify `docs/operator/universal-wild-no-block-contract.md`: clarify proof-matrix rich-output policy versus minimal runtime gate.
- Modify `docs/operator/source-backed-strong-closure.md`: rename source-strength "hard blocker" language to promotion/source-depth language.
- Modify `docs/operator/README.md`: add one concise line that `load_safe_apply` is HSConfig policy and per-card-every-card is rich output.
- Modify `.agents/skills/hsconfig/SKILL.md`: mirror the same operator-facing distinction.
- Modify `.agents/skills/hsconfig/references/card-behavior-policy.md`: document source-backed versus repo-supported card behavior blocks.
- Modify `src/hsconfig/visionai_registry.py`: add non-behavior-changing source-backing metadata to supported card behavior blocks.
- Modify `tests/test_visionai_registry.py`: verify source-backing metadata for public-doc-confirmed and source-gap blocks.
- Modify `tests/test_docs_active_path.py`: verify current-truth and no-block contract wording.
- Modify `tests/test_skill_files.py`: verify skill and reference docs use the new terms and do not reintroduce source-informed apply confusion.
- Modify `docs/research/current-truth.md`: add the post-contract-closure audit as current active evidence.
- Include `docs/research/2026-07-10-hsconfig-post-contract-closure-skill-audit/**` as the active audit package if committing research evidence.
- Remove or intentionally leave untracked older generated research directories only after confirming they are not referenced by `docs/research/current-truth.md`.

---

### Task 1: Lock No-Block Vocabulary In Active Docs

**Files:**
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/README.md`
- Test: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: Existing operator docs and no-block audit results.
- Produces: Active docs where runtime hard blocks, promotion blockers, and rich-output policy cannot be confused.

- [ ] **Step 1: Write failing docs tests**

Add these tests to `tests/test_docs_active_path.py`:

```python
def test_universal_no_block_contract_labels_per_card_every_card_as_rich_policy():
    text = Path("docs/operator/universal-wild-no-block-contract.md").read_text(
        encoding="utf-8"
    )

    assert "HSConfig rich-output repo policy" in text
    assert "not the minimal runtime-apply gate" in text
    assert "not an official HearthRanger minimum" in text
    assert "one per-card JSON file for every unique deck CardID" in text


def test_source_backed_closure_uses_promotion_blocker_language():
    text = Path("docs/operator/source-backed-strong-closure.md").read_text(
        encoding="utf-8"
    )

    assert "Promotion blocker reason" in text
    assert "Hard blocker reason" not in text
    assert "runtime apply is no longer blocked by source strength" in text


def test_operator_docs_name_load_safe_apply_as_hsconfig_policy():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "`load_safe_apply` is an HSConfig operator policy" in text
    assert "not a HearthRanger public-doc term" in text
    assert "per-card-every-card coverage is HSConfig rich output" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py -q
```

Expected: FAIL on the three new assertions because the wording has not been added yet.

- [ ] **Step 3: Update `docs/operator/universal-wild-no-block-contract.md`**

In the "Runtime Apply Promise" section, keep the current minimal gate paragraph and add this sentence after it:

```markdown
The proof-matrix expectation that normal `prepare` emits one per-card JSON file for every unique deck CardID is HSConfig rich-output repo policy. It is not the minimal runtime-apply gate and not an official HearthRanger minimum.
```

In the "Proof Matrix" section, replace:

```markdown
Each deck must produce `VALID_PACKAGE`, `runtime_load_safe=true`,
`runtime_apply_mode=load_safe_apply`, `GlobalValues.json`, `Mulligan.json`, and
one per-card JSON file for every unique deck CardID.
```

with:

```markdown
Each deck must produce `VALID_PACKAGE`, `runtime_load_safe=true`,
`runtime_apply_mode=load_safe_apply`, `GlobalValues.json`, and `Mulligan.json`.
As HSConfig rich-output repo policy, normal `prepare` must also emit one per-card
JSON file for every unique deck CardID when deck-card identity is known. That
rich-output proof is not the minimal runtime-apply gate.
```

- [ ] **Step 4: Update `docs/operator/source-backed-strong-closure.md`**

Replace the table header:

```markdown
| Deck | Current decision | First missing link | Hard blocker reason |
```

with:

```markdown
| Deck | Current decision | First missing link | Promotion blocker reason |
```

If the file contains any source-strength sentence using "hard blocker" for promotion, rewrite it to "promotion blocker" or "source-depth blocker". Keep any existing sentence that explicitly says runtime apply is not blocked by source strength.

- [ ] **Step 5: Update `docs/operator/README.md`**

In "Load Safety vs. Config Richness", after the existing minimal load-safe bullet, add:

```markdown
- `load_safe_apply` is an HSConfig operator policy, not a HearthRanger public-doc term. Per-card-every-card coverage is HSConfig rich output for stronger control and matrix proof, not a minimal runtime-write requirement.
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```powershell
git add docs/operator/universal-wild-no-block-contract.md docs/operator/source-backed-strong-closure.md docs/operator/README.md tests/test_docs_active_path.py
git commit -m "docs: clarify no-block runtime vocabulary"
```

---

### Task 2: Add Source-Backing Metadata To VisionAI Registry

**Files:**
- Modify: `src/hsconfig/visionai_registry.py`
- Modify: `tests/test_visionai_registry.py`

**Interfaces:**
- Consumes: `runtime_block_support(block_name: str) -> dict[str, Any]`
- Produces: Extra metadata fields in the returned dict: `source_backing` and `source_note`. Existing callers keep working.

- [ ] **Step 1: Write failing registry tests**

Add these tests to `tests/test_visionai_registry.py`:

```python
def test_registry_marks_public_doc_confirmed_behavior_blocks():
    for block in [
        "BeforePlayCardBonus",
        "BeforeBattlecryTargetBonus",
        "BeforeUseHeroPowerBonus",
        "BeforePhysicalAttackBonus",
        "OnDiscoverCardBonus",
        "OnChooseOneCardBonus",
        "InHandPlayPriority",
    ]:
        row = runtime_block_support(block)
        assert row["support"] == "supported"
        assert row["normal_path_runtime"] is True
        assert row["source_backing"] == "public_doc_confirmed"
        assert "HearthRanger VisionAI public docs" in row["source_note"]


def test_registry_marks_repo_supported_public_doc_gaps():
    for block in ["OnAdaptCardBonus", "BeforeUpgradeCardBonus", "OnBoardPlayPriority"]:
        row = runtime_block_support(block)
        assert row["support"] == "supported"
        assert row["normal_path_runtime"] is True
        assert row["source_backing"] == "repo_supported_source_gap"
        assert "not confirmed in the latest public-doc audit" in row["source_note"]


def test_unknown_block_includes_source_backing_metadata():
    row = runtime_block_support("BeforeInventedCardBonus")

    assert row["support"] == "unsupported"
    assert row["normal_path_runtime"] is False
    assert row["source_backing"] == "unsupported"
    assert row["source_note"] == "No HSConfig runtime support."
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_visionai_registry.py -q
```

Expected: FAIL with missing `source_backing` or `source_note`.

- [ ] **Step 3: Implement metadata in `visionai_registry.py`**

Replace the current `CARD_BEHAVIOR_BLOCK_REGISTRY` construction with:

```python
PUBLIC_DOC_CONFIRMED_CARD_BEHAVIOR_BLOCKS = frozenset(
    {
        "InHandBonus",
        "OnBoardBonus",
        "BeforePlayCardBonus",
        "BeforeBattlecryTargetBonus",
        "BeforeUseHeroPowerBonus",
        "BeforePhysicalAttackBonus",
        "BeforeEndTurnBonus",
        "BeforeOverkilledBonus",
        "OnDiscoverCardBonus",
        "OnChooseOneCardBonus",
        "InHandPlayPriority",
    }
)

REPO_SUPPORTED_SOURCE_GAP_CARD_BEHAVIOR_BLOCKS = frozenset(
    {
        "OnAdaptCardBonus",
        "BeforeUpgradeCardBonus",
        "OnBoardPlayPriority",
    }
)

CARD_BEHAVIOR_BLOCKS = (
    PUBLIC_DOC_CONFIRMED_CARD_BEHAVIOR_BLOCKS
    | REPO_SUPPORTED_SOURCE_GAP_CARD_BEHAVIOR_BLOCKS
)


def _card_behavior_registry_row(block: str) -> dict[str, Any]:
    if block in REPO_SUPPORTED_SOURCE_GAP_CARD_BEHAVIOR_BLOCKS:
        return {
            "support": "supported",
            "normal_path_runtime": True,
            "surface_family": "card_behavior",
            "source_backing": "repo_supported_source_gap",
            "source_note": (
                "Repo-supported block; not confirmed in the latest public-doc audit."
            ),
        }
    return {
        "support": "supported",
        "normal_path_runtime": True,
        "surface_family": "card_behavior",
        "source_backing": "public_doc_confirmed",
        "source_note": "Confirmed by HearthRanger VisionAI public docs or prior HSConfig surface audit.",
    }


CARD_BEHAVIOR_BLOCK_REGISTRY: dict[str, dict[str, Any]] = {
    block: _card_behavior_registry_row(block)
    for block in CARD_BEHAVIOR_BLOCKS
}
```

In the `Presume.json` and `Concede.json` registry rows, add:

```python
"source_backing": "legacy_gated",
"source_note": "Known surface, intentionally outside the normal HSConfig path.",
```

In the `runtime_block_support()` unsupported return dict, add:

```python
"source_backing": "unsupported",
"source_note": "No HSConfig runtime support.",
```

- [ ] **Step 4: Run registry tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_visionai_registry.py -q
```

Expected: PASS.

- [ ] **Step 5: Run related validator/apply tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_validate_package.py tests/test_apply_gate.py -q
```

Expected: PASS. The metadata must not alter support behavior.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/hsconfig/visionai_registry.py tests/test_visionai_registry.py
git commit -m "chore: annotate VisionAI registry source backing"
```

---

### Task 3: Sync Skill Documentation With New Contract Language

**Files:**
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `tests/test_skill_files.py`
- Generated sync target: `C:\Users\darbo\.codex\skills\hsconfig\...` through `scripts/sync_installed_skill.py`

**Interfaces:**
- Consumes: Updated doc vocabulary and registry source-gap metadata.
- Produces: Repo skill and installed skill with the same no-block/rich-output terminology.

- [ ] **Step 1: Write failing skill doc tests**

Add these tests to `tests/test_skill_files.py`:

```python
def test_skill_docs_distinguish_rich_output_from_minimal_apply_gate():
    docs = "\n".join(
        [
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/references/workflow.md").read_text(
                encoding="utf-8"
            ),
            Path(".agents/skills/hsconfig/references/card-behavior-policy.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "HSConfig rich-output repo policy" in docs
    assert "not the minimal runtime-write gate" in docs
    assert "not an official HearthRanger minimum" in docs
    assert "`load_safe_apply` is an HSConfig operator policy" in docs


def test_skill_docs_mark_repo_supported_source_gap_blocks():
    card_policy = Path(
        ".agents/skills/hsconfig/references/card-behavior-policy.md"
    ).read_text(encoding="utf-8")

    for block in ["OnAdaptCardBonus", "BeforeUpgradeCardBonus", "OnBoardPlayPriority"]:
        assert block in card_policy
    assert "repo-supported source-gap blocks" in card_policy
    assert "not confirmed in the latest public-doc audit" in card_policy
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py -q
```

Expected: FAIL on the new wording assertions.

- [ ] **Step 3: Update `.agents/skills/hsconfig/SKILL.md`**

In the rules section after the minimal load-safe apply bullet, add:

```markdown
- Per-card-every-card coverage is HSConfig rich-output repo policy. It improves control and matrix proof, but it is not the minimal runtime-write gate and not an official HearthRanger minimum.
- `load_safe_apply` is an HSConfig operator policy, not a HearthRanger public-doc term.
```

- [ ] **Step 4: Update `.agents/skills/hsconfig/references/workflow.md`**

In the runtime apply section after the sentence explaining `runtime_apply_mode=load_safe_apply`, add:

```markdown
`load_safe_apply` is HSConfig's operator policy for structurally valid pre-run packages. It is not a HearthRanger public-doc term. Per-card-every-card coverage is HSConfig rich-output repo policy for stronger control and proof matrices, not the minimal runtime-write gate.
```

- [ ] **Step 5: Update `.agents/skills/hsconfig/references/card-behavior-policy.md`**

Add a short section near the block list:

```markdown
## Source Backing Notes

The public-doc-confirmed normal card behavior blocks include `BeforePlayCardBonus`,
`BeforeBattlecryTargetBonus`, `BeforeUseHeroPowerBonus`,
`BeforePhysicalAttackBonus`, `OnDiscoverCardBonus`, `OnChooseOneCardBonus`, and
`InHandPlayPriority`.

The repo-supported source-gap blocks are `OnAdaptCardBonus`,
`BeforeUpgradeCardBonus`, and `OnBoardPlayPriority`. Keep them visible as
supported HSConfig registry blocks, but do not describe them as confirmed in the
latest public-doc audit.

Per-card-every-card coverage is HSConfig rich-output repo policy. It is not the
minimal runtime-write gate and not an official HearthRanger minimum.
```

- [ ] **Step 6: Run skill tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 7: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected: final command prints:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 8: Commit Task 3**

```powershell
git add .agents/skills/hsconfig C:\Users\darbo\.codex\skills\hsconfig tests/test_skill_files.py
git commit -m "docs: sync HSConfig skill no-block wording"
```

If Git refuses the installed skill path because it is outside the repo, only commit `.agents/skills/hsconfig` and `tests/test_skill_files.py`; keep the installed skill synced locally.

---

### Task 4: Update Research Current Truth And Clean Generated Audit Noise

**Files:**
- Modify: `docs/research/current-truth.md`
- Add/keep: `docs/research/2026-07-10-hsconfig-post-contract-closure-skill-audit/outline.yaml`
- Add/keep: `docs/research/2026-07-10-hsconfig-post-contract-closure-skill-audit/fields.yaml`
- Add/keep: `docs/research/2026-07-10-hsconfig-post-contract-closure-skill-audit/results/*.json`
- Test: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: Validated research result package.
- Produces: Current-truth index that names the active post-contract audit and keeps older research out of the operator path.

- [ ] **Step 1: Write failing current-truth test**

Add to `tests/test_docs_active_path.py`:

```python
def test_current_truth_names_post_contract_closure_audit():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "2026-07-10-hsconfig-post-contract-closure-skill-audit" in text
    assert "Post-contract no-block cleanup evidence" in text
    assert "per-card-every-card coverage is HSConfig rich output" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py::test_current_truth_names_post_contract_closure_audit -q
```

Expected: FAIL because the current truth index does not yet list the new package.

- [ ] **Step 3: Update `docs/research/current-truth.md`**

Add this row at the top of "Current Active Evidence":

```markdown
| `docs/research/2026-07-10-hsconfig-post-contract-closure-skill-audit/` | Post-contract no-block cleanup evidence | Keep the core apply gate unchanged; runtime hard blocks are technical only, per-card-every-card coverage is HSConfig rich output, and source-strength gaps are promotion/richness gaps. |
```

- [ ] **Step 4: Validate research result package**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-10-hsconfig-post-contract-closure-skill-audit\fields.yaml -d docs\research\2026-07-10-hsconfig-post-contract-closure-skill-audit\results
```

Expected:

```text
Validation passed: 4/4
Average coverage: 100.0%
```

- [ ] **Step 5: Inspect untracked research directories**

Run:

```powershell
git status --short -- docs/research
```

Expected: shows the new audit package and older untracked generated research packages.

- [ ] **Step 6: Remove stale untracked generated research packages if they are not referenced by current-truth**

First verify all targets are inside the repo:

```powershell
$repo = (Resolve-Path .).Path
$targets = @(
  "docs\research\2026-07-08-hsconfig-skill-optimality-audit-v2",
  "docs\research\2026-07-09-hsconfig-next-recommendation-audit",
  "docs\research\2026-07-09-hsconfig-no-blocking-skill-audit",
  "docs\research\2026-07-09-hsconfig-post-boarlock-truth-skill-audit",
  "docs\research\2026-07-09-hsconfig-post-kingslayer-skill-audit",
  "docs\research\2026-07-09-hsconfig-skill-optimality-audit",
  "docs\research\2026-07-10-hsconfig-no-block-current-skill-audit"
)
foreach ($target in $targets) {
  $resolved = Resolve-Path -LiteralPath $target -ErrorAction SilentlyContinue
  if ($resolved -and -not $resolved.Path.StartsWith($repo)) {
    throw "Refusing to remove outside repo: $($resolved.Path)"
  }
}
```

Then remove only those verified untracked generated packages:

```powershell
foreach ($target in $targets) {
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
}
```

Do not remove any path that is referenced in `docs/research/current-truth.md`.

- [ ] **Step 7: Run current-truth tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```powershell
git add docs/research/current-truth.md docs/research/2026-07-10-hsconfig-post-contract-closure-skill-audit tests/test_docs_active_path.py
git commit -m "docs: record current no-block audit truth"
```

---

### Task 5: Final Contract Regression And Scope Guard

**Files:**
- Test only unless failures expose contradictions:
  - `tests/test_runtime_apply.py`
  - `tests/test_apply_gate.py`
  - `tests/test_validate_package.py`
  - `tests/test_universal_wild_no_block_matrix.py`
  - `tests/test_skill_sync.py`
  - `tests/test_skill_files.py`
  - `tests/test_docs_active_path.py`
  - `tests/test_scope_boundaries.py`
  - `tests/test_visionai_registry.py`

**Interfaces:**
- Consumes: All previous tasks.
- Produces: Verified no-block cleanup branch ready for integration.

- [ ] **Step 1: Run focused no-block contract suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py tests/test_apply_gate.py tests/test_validate_package.py tests/test_universal_wild_no_block_matrix.py tests/test_skill_sync.py tests/test_skill_files.py tests/test_docs_active_path.py tests/test_scope_boundaries.py tests/test_visionai_registry.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: PASS or only documented existing skips. If failures occur, fix only failures caused by this cleanup.

- [ ] **Step 3: Run active-doc scope scan**

Run:

```powershell
rg -n "Hard blocker reason|ALLOWED_SOURCE_INFORMED|--allow-source-informed --json|per-card files are required for minimal apply|HSTuner candidate|winrate|replay parser|normal output includes Presume|normal output includes Concede" README.md docs/operator .agents/skills/hsconfig src tests -g "!docs/research/**"
```

Expected: no misleading active-path hits. Allowed hits are test names that explicitly assert absence.

- [ ] **Step 4: Check installed skill sync**

Run:

```powershell
python scripts/sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 5: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: branch is clean except no ignored local files. No stale untracked research directories should remain.

- [ ] **Step 6: Commit any final test/doc adjustments**

If Step 1-5 required small fixes:

```powershell
git add <changed-files>
git commit -m "test: verify HSConfig no-block contract cleanup"
```

If no fixes were needed, do not create an empty commit.

---

### Task 6: Integration Handoff

**Files:**
- No file changes expected.

**Interfaces:**
- Consumes: Completed commits from Tasks 1-5.
- Produces: Branch ready to merge/push according to the user's normal GitHub preference.

- [ ] **Step 1: Show final commit stack**

Run:

```powershell
git log --oneline --decorate --max-count=10
```

Expected: shows the cleanup commits on top of `8cc67a5` or its successor.

- [ ] **Step 2: Confirm no accidental runtime/private artifacts**

Run:

```powershell
git status --short
rg -n "Power.log|\\.hdtreplay|\\.hsreplay|HDT|winrate|candidate promotion|analyze-step2" README.md docs/operator .agents/skills/hsconfig src tests -g "!docs/research/**"
```

Expected: no private runtime artifacts and no new HSConfig scope creep. Existing negative-scope phrases are acceptable when they say HSConfig does not do those tasks.

- [ ] **Step 3: Prepare final handoff**

Report:

```text
Implemented HSConfig no-block contract cleanup.
Verified:
- focused no-block contract suite
- full pytest suite
- installed skill sync
- active-doc scope scan
- git status
```

Do not claim real HearthRanger runtime load unless a live runtime load was actually performed.

---

## Self-Review

Spec coverage:
- No-block apply gate unchanged: Task 1, Task 5.
- Per-card-every-card as rich-output repo policy: Task 1, Task 3, Task 4.
- Source-backed vs repo-supported registry blocks: Task 2, Task 3.
- Research current truth and artifact hygiene: Task 4.
- Skill sync and scope guard: Task 3, Task 5.

Placeholder scan:
- No unresolved placeholder markers or deferred-work notes are used.
- Every task has exact files, test commands, and expected results.

Type consistency:
- `runtime_block_support(block_name: str) -> dict[str, Any]` remains the public function.
- New metadata keys are `source_backing` and `source_note` across tests and implementation.
- `load_safe_apply`, `SOURCE_BACKED_STRONG`, `VALID_PACKAGE`, and `runtime_load_safe` names match current repo terminology.
