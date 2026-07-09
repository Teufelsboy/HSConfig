# HSConfig Visibility-Only Mechanic Polish And Current Truth Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig more transparent for Wild mechanics without adding new runtime surfaces or blocking valid deck packages.

**Architecture:** Keep the normal HSConfig pipeline unchanged: `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`. Extend only the operator-facing mechanic visibility layer, report summaries, and documentation so unsupported or identity-dependent mechanics are visible as non-blocking boundaries. Add one small current-truth research index so operators do not have to infer active guidance from many historical research folders.

**Tech Stack:** Python 3, pytest, stdlib JSON/dataclasses, existing HSConfig CLI/report modules, HearthRanger VisionAI JSON runtime surfaces.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- HSConfig is pre-run only; do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Do not change `hsconfig apply` gate semantics or runtime writer behavior in this wave.
- `operator_summary.json` stays the single operator gate.
- `VALID_PACKAGE`, `runtime_load_safe=true`, and `runtime_apply_mode=load_safe_apply` continue to control load-safe apply.
- Warning-only mechanics are descriptive and must not block load-safe apply.
- No normal-path `Presume.json` or `Concede.json`.
- Preserve exact deck and CardID identity, full `GlobalValues.json` key profiling, every-card contract coverage, strict JSON validation, and row-level provenance.
- Keep `generated_entity` and the `spell_generation` alias in `partial`, not `identity_gated_direct`.
- Research artifacts remain evidence, not operator instructions. Normal operator path starts at `docs/operator/README.md`.

---

## File Structure

- Modify `src/hsconfig/mechanic_support.py`
  - Owns the mechanic support registry, role aliases, operator visibility buckets, and mechanic visibility summary shape.
- Modify `src/hsconfig/operator_summary.py`
  - Sanitizes and exposes readiness summary fields, including `mechanic_visibility_summary`.
- Modify `src/hsconfig/operator_guidance.py`
  - Carries the same mechanic visibility summary into operator next-action guidance.
- Modify `docs/operator/universal-wild-no-block-contract.md`
  - Canonical no-block and mechanic boundary policy.
- Modify `docs/operator/README.md`
  - Normal operator entry point and short explanation of mechanic visibility.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Installed-source skill instructions.
- Modify `.agents/skills/hsconfig/references/workflow.md`
  - Skill workflow reference for operators.
- Modify `.agents/skills/hsconfig/references/card-behavior-policy.md`
  - Choice/target behavior policy reference.
- Modify `docs/research/README.md`
  - Add a small current-truth index pointer.
- Create `docs/research/current-truth.md`
  - One-page active evidence index for current guidance.
- Modify tests:
  - `tests/test_mechanic_support.py`
  - `tests/test_config_readiness.py`
  - `tests/test_operator_summary.py`
  - `tests/test_operator_guidance.py`
  - `tests/test_skill_files.py`
  - `tests/test_docs_active_path.py`

---

### Task 1: Mechanic Registry Visibility Slice

**Files:**
- Modify: `src/hsconfig/mechanic_support.py`
- Test: `tests/test_mechanic_support.py`

**Interfaces:**
- Consumes: `support_for_roles(roles: Iterable[str]) -> list[dict[str, Any]]`
- Consumes: `operator_visibility_bucket(support: dict[str, Any]) -> str`
- Produces: registry rows for `choose_one`, `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool`
- Produces: `choose_one` in the `identity_gated_direct` operator bucket

- [ ] **Step 1: Write failing tests for the new mechanic visibility classifications**

Append this test to `tests/test_mechanic_support.py`:

```python
def test_visibility_slice_classifies_choose_one_and_warning_boundaries():
    rows = support_for_roles(
        [
            "choose_one_choice",
            "choose_one",
            "board_position",
            "generic_spell_target",
            "location_activation",
            "secret_timing",
            "generated_entity_random_pool",
            "spell_generation",
        ]
    )

    by_mechanic = {row["mechanic"]: row for row in rows}

    assert by_mechanic["choose_one"]["support_level"] == "direct"
    assert operator_visibility_bucket(by_mechanic["choose_one"]) == "identity_gated_direct"
    assert by_mechanic["choose_one"]["normal_path_surfaces"] == [
        "CARDID.json:OnChooseOneCardBonus",
        "CARDID.json:BeforePlayCardBonus",
    ]

    for mechanic in [
        "board_position",
        "generic_spell_target",
        "location_activation",
        "secret_timing",
        "generated_entity_random_pool",
    ]:
        assert by_mechanic[mechanic]["support_level"] == "warning_only"
        assert by_mechanic[mechanic]["normal_path_surfaces"] == ["report-only"]
        assert operator_visibility_bucket(by_mechanic[mechanic]) == "warning_only"

    assert by_mechanic["generated_entity"]["support_level"] == "partial"
    assert operator_visibility_bucket(by_mechanic["generated_entity"]) == "partial"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_support.py::test_visibility_slice_classifies_choose_one_and_warning_boundaries -q
```

Expected: FAIL because `choose_one_choice` maps to an unknown warning-only role and the new warning-only submechanics are not registered.

- [ ] **Step 3: Add the new mechanic registry rows**

In `src/hsconfig/mechanic_support.py`, add these entries to `MECHANIC_SUPPORT`:

```python
    "choose_one": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:OnChooseOneCardBonus",
            "CARDID.json:BeforePlayCardBonus",
        ],
        "warning_boundary": "Only source-resolved Choose One option identity lowers; unresolved options stay suppressed.",
    },
    "board_position": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Exact minion placement has no documented normal-path VisionAI positioning surface.",
    },
    "generic_spell_target": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Generic spell target selection is not lowerable unless a documented card-specific target surface exists.",
    },
    "location_activation": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Repeated location activation and target choice have no documented normal-path runtime row.",
    },
    "secret_timing": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Hidden-information secret timing has no separate normal-path runtime row.",
    },
    "generated_entity_random_pool": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Random generated-entity pools stay report-only unless exact generated identity is source-backed.",
    },
```

Place `choose_one` near `discover`, and place the warning-only rows near related mechanics so the registry stays readable.

- [ ] **Step 4: Add aliases and identity-gated bucket coverage**

In `ROLE_ALIASES`, add:

```python
    "choose_one_choice": "choose_one",
    "positioning": "board_position",
    "spell_target": "generic_spell_target",
    "location_use": "location_activation",
    "secret_ordering": "secret_timing",
    "random_generation": "generated_entity_random_pool",
```

In `IDENTITY_GATED_DIRECT_MECHANICS`, add:

```python
    "choose_one",
```

- [ ] **Step 5: Run the registry tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_support.py -q
```

Expected: all tests in `tests/test_mechanic_support.py` pass.

- [ ] **Step 6: Commit this task**

Run:

```powershell
git add src/hsconfig/mechanic_support.py tests/test_mechanic_support.py
git commit -m "feat: expand nonblocking mechanic visibility registry"
```

---

### Task 2: Warning Boundary Summary Rows

**Files:**
- Modify: `src/hsconfig/mechanic_support.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/operator_guidance.py`
- Test: `tests/test_mechanic_support.py`
- Test: `tests/test_config_readiness.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_operator_guidance.py`

**Interfaces:**
- Consumes: `summarize_mechanic_visibility(rows: Iterable[dict[str, Any]]) -> dict[str, Any]`
- Produces: `warning_boundaries: list[dict[str, str]]`
- Preserves: `first_warning_boundary: dict[str, str] | None`
- Preserves: `non_blocking: True`

- [ ] **Step 1: Extend the mechanic visibility summary test**

In `tests/test_mechanic_support.py`, extend `test_summarize_mechanic_visibility_is_non_blocking_and_operator_readable` so the input includes two warning-only mechanics:

```python
            {
                "card_id": "POSITION_001",
                "mechanic_support": support_for_roles(["board_position"]),
            },
```

Update the expected warning bucket and add assertions:

```python
    assert summary["bucket_counts"]["warning_only"] == 2
    assert summary["mechanics_by_bucket"]["warning_only"] == [
        "board_position",
        "dredge",
    ]
    assert summary["warning_only_card_count"] == 2
    assert summary["first_warning_boundary"]["mechanic"] == "dredge"
    assert summary["warning_boundaries"] == [
        {
            "mechanic": "board_position",
            "warning_boundary": "Exact minion placement has no documented normal-path VisionAI positioning surface.",
        },
        {
            "mechanic": "dredge",
            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
        },
    ]
```

- [ ] **Step 2: Add passthrough tests for operator summary and guidance**

In `tests/test_operator_summary.py`, extend `test_operator_summary_exposes_mechanic_visibility_without_blocking_apply` with:

```python
                    "warning_boundaries": [
                        {
                            "mechanic": "dredge",
                            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
                        }
                    ],
```

Add assertions:

```python
    assert summary["mechanic_visibility_summary"]["warning_boundaries"] == [
        {
            "mechanic": "dredge",
            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
        }
    ]
    assert summary["operator_guidance"]["mechanic_visibility_summary"]["warning_boundaries"] == [
        {
            "mechanic": "dredge",
            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
        }
    ]
```

In `tests/test_operator_guidance.py`, extend `test_warning_guidance_carries_mechanic_visibility_summary` with the same `warning_boundaries` input and add:

```python
    assert guidance["mechanic_visibility_summary"]["warning_boundaries"] == [
        {
            "mechanic": "tradeable",
            "warning_boundary": "Trade-now decisions have no documented normal-path VisionAI runtime block.",
        }
    ]
```

- [ ] **Step 3: Run the new tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_support.py tests/test_operator_summary.py tests/test_operator_guidance.py -q
```

Expected: FAIL because `warning_boundaries` is not produced or sanitized through every report surface.

- [ ] **Step 4: Implement `warning_boundaries` in `summarize_mechanic_visibility`**

In `src/hsconfig/mechanic_support.py`, initialize a dictionary before the loop:

```python
    warning_boundaries_by_mechanic: dict[str, str] = {}
```

Inside the `if bucket == "warning_only":` block, after `first_warning_boundary` handling, add:

```python
                if mechanic and mechanic not in warning_boundaries_by_mechanic:
                    warning_boundaries_by_mechanic[mechanic] = str(
                        support.get("warning_boundary", "")
                    )
```

Add this field to the return object:

```python
        "warning_boundaries": [
            {
                "mechanic": mechanic,
                "warning_boundary": warning_boundaries_by_mechanic[mechanic],
            }
            for mechanic in sorted(warning_boundaries_by_mechanic)
        ],
```

- [ ] **Step 5: Preserve `warning_boundaries` through operator summary sanitization**

In `src/hsconfig/operator_summary.py`, update the default mechanic visibility object inside `_mechanic_visibility_summary` to include:

```python
        "warning_boundaries": [],
```

Before the return in `_mechanic_visibility_summary`, normalize:

```python
    warning_boundaries = visibility.get("warning_boundaries", [])
    if not isinstance(warning_boundaries, list):
        warning_boundaries = []
```

Add this field to the returned dictionary:

```python
        "warning_boundaries": [
            {
                "mechanic": str(item.get("mechanic", "")),
                "warning_boundary": str(item.get("warning_boundary", "")),
            }
            for item in warning_boundaries
            if isinstance(item, dict)
        ],
```

- [ ] **Step 6: Preserve default `warning_boundaries` in operator guidance fallback**

In `src/hsconfig/operator_guidance.py`, update the fallback summary inside `_mechanic_visibility_fields` to include:

```python
            "warning_boundaries": [],
```

No other `operator_guidance.py` behavior should change because real summaries are already passed through as dictionaries.

- [ ] **Step 7: Run the focused report tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_support.py tests/test_config_readiness.py tests/test_operator_summary.py tests/test_operator_guidance.py -q
```

Expected: all listed tests pass.

- [ ] **Step 8: Commit this task**

Run:

```powershell
git add src/hsconfig/mechanic_support.py src/hsconfig/operator_summary.py src/hsconfig/operator_guidance.py tests/test_mechanic_support.py tests/test_config_readiness.py tests/test_operator_summary.py tests/test_operator_guidance.py
git commit -m "feat: expose mechanic warning boundaries"
```

---

### Task 3: Operator And Skill Documentation Alignment

**Files:**
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: mechanic visibility buckets from Tasks 1 and 2
- Produces: operator-readable policy that these mechanics are visible but non-blocking
- Preserves: no normal-path `Presume.json` or `Concede.json`

- [ ] **Step 1: Add failing docs assertions**

Append this test to `tests/test_skill_files.py`:

```python
def test_docs_and_skill_explain_visibility_only_mechanic_polish():
    paths = [
        Path("docs/operator/universal-wild-no-block-contract.md"),
        Path("docs/operator/README.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
        Path(".agents/skills/hsconfig/references/card-behavior-policy.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "`choose_one`" in combined
    assert "`board_position`" in combined
    assert "`generic_spell_target`" in combined
    assert "`location_activation`" in combined
    assert "`secret_timing`" in combined
    assert "`generated_entity_random_pool`" in combined
    assert "warning_boundaries" in combined
    assert "must not block load-safe apply" in combined
    assert "`generated_entity` and its `spell_generation` alias stay in `partial`" in combined
```

- [ ] **Step 2: Run the docs test and verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py::test_docs_and_skill_explain_visibility_only_mechanic_polish -q
```

Expected: FAIL because the new mechanic names and `warning_boundaries` are not fully documented.

- [ ] **Step 3: Update the universal no-block contract**

In `docs/operator/universal-wild-no-block-contract.md`, add this paragraph in the mechanic visibility section:

```markdown
`choose_one` is `identity_gated_direct`: HSConfig can lower it through `OnChooseOneCardBonus` only when exact option identity is source-backed. `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are `warning_only`: they are visible in `warning_boundaries`, but they must not block load-safe apply. `generated_entity` and its `spell_generation` alias stay in `partial`, because exact generated identity can be represented only when the generated card is known.
```

- [ ] **Step 4: Update the normal operator README**

In `docs/operator/README.md`, extend the existing mechanic visibility paragraph with:

```markdown
`warning_boundaries` lists the concrete report-only mechanics the operator may inspect next. `choose_one` is identity-gated direct, while `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are warning-only. These warnings are explanatory; they must not block load-safe apply for a valid package.
```

- [ ] **Step 5: Update the skill entrypoint**

In `.agents/skills/hsconfig/SKILL.md`, add a rule near the existing mechanic visibility rule:

```markdown
- Use `warning_boundaries` in `mechanic_visibility_summary` to explain report-only mechanics. `choose_one` is identity-gated direct; `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are warning-only and must not block load-safe apply.
```

- [ ] **Step 6: Update skill reference docs**

In `.agents/skills/hsconfig/references/workflow.md`, add:

```markdown
For mechanic visibility, use `warning_boundaries` as the first readable explanation of report-only mechanics. Keep the workflow moving when the package is technically valid: warning-only mechanics describe limits, not blocks.
```

In `.agents/skills/hsconfig/references/card-behavior-policy.md`, add:

```markdown
`choose_one_choice` lowers to `choose_one` and is identity-gated direct. It may emit `OnChooseOneCardBonus` only when the option identity is source-backed. Generic spell targets, minion positioning, repeated location activation, secret timing, and random generated-entity pools stay warning-only unless a documented card-specific VisionAI surface is added.
```

- [ ] **Step 7: Run the docs tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: all listed tests pass.

- [ ] **Step 8: Commit this task**

Run:

```powershell
git add docs/operator/universal-wild-no-block-contract.md docs/operator/README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md .agents/skills/hsconfig/references/card-behavior-policy.md tests/test_skill_files.py
git commit -m "docs: document nonblocking mechanic visibility boundaries"
```

---

### Task 4: Current Truth Research Index

**Files:**
- Create: `docs/research/current-truth.md`
- Modify: `docs/research/README.md`
- Test: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: current research package `docs/research/2026-07-09-hsconfig-next-recommendation-mechanic-polish/`
- Produces: a one-page index that says which research packages are active evidence for current operator guidance
- Preserves: research artifacts are evidence, not operator instructions

- [ ] **Step 1: Add failing tests for the current-truth index**

Append these tests to `tests/test_docs_active_path.py`:

```python
def test_research_current_truth_index_exists_and_keeps_operator_boundary():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "HSConfig Current Truth Index" in text
    assert "Research artifacts are evidence, not operator instructions." in text
    assert "Normal operator path starts at `docs/operator/README.md`." in text
    assert "2026-07-09-hsconfig-next-recommendation-mechanic-polish" in text
    assert "Visibility-only Mechanic Polish" in text


def test_research_readme_points_to_current_truth_index():
    text = Path("docs/research/README.md").read_text(encoding="utf-8")

    assert "docs/research/current-truth.md" in text
    assert "Current truth index" in text
```

- [ ] **Step 2: Run the docs tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py -q
```

Expected: FAIL because `docs/research/current-truth.md` does not exist and `docs/research/README.md` does not point to it.

- [ ] **Step 3: Create `docs/research/current-truth.md`**

Create `docs/research/current-truth.md` with this content:

```markdown
# HSConfig Current Truth Index

Research artifacts are evidence, not operator instructions.

Normal operator path starts at `docs/operator/README.md`.

## Current Active Evidence

| Package | Role | Current implication |
| --- | --- | --- |
| `docs/research/2026-07-09-hsconfig-next-recommendation-mechanic-polish/` | Visibility-only Mechanic Polish | Add non-blocking mechanic visibility for `choose_one`, `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool`; do not change apply gates. |
| `docs/research/2026-07-09-hsconfig-current-no-block-wild-mechanic-audit/` | No-block Wild mechanic evidence | Valid deck packages should stay load-safe even when mechanic semantics are report-only. |
| `docs/research/2026-07-09-hsconfig-universal-no-block-skill-audit-v2/` | Universal no-block evidence | The no-block promise is implemented through warning visibility, not through broader runtime writes. |

## Superseded Evidence

Older packages remain useful background, but they are not normal operator guidance. When a claim conflicts with `docs/operator/README.md`, `.agents/skills/hsconfig/SKILL.md`, or `docs/operator/universal-wild-no-block-contract.md`, the operator and skill documents win.
```

- [ ] **Step 4: Update `docs/research/README.md`**

Add this paragraph after the existing opening boundary paragraph:

```markdown
Current truth index: `docs/research/current-truth.md`. Use it to find the small set of active evidence packages before opening older historical research folders.
```

- [ ] **Step 5: Run the docs active path tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py -q
```

Expected: all tests in `tests/test_docs_active_path.py` pass.

- [ ] **Step 6: Commit this task**

Run:

```powershell
git add docs/research/current-truth.md docs/research/README.md tests/test_docs_active_path.py
git commit -m "docs: add hsconfig current truth index"
```

---

### Task 5: Skill Sync And Verification

**Files:**
- Modify only if generated sync changes occur: installed skill files under `C:\Users\darbo\.codex\skills\hsconfig`
- Verify: all touched code, docs, and tests

**Interfaces:**
- Consumes: source skill files under `.agents/skills/hsconfig/`
- Produces: installed skill copy matching repository source

- [ ] **Step 1: Sync the installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
```

Expected: command exits with code 0 and reports the installed HSConfig skill was updated or already current.

- [ ] **Step 2: Verify installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: command exits with code 0.

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_support.py tests/test_config_readiness.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_skill_files.py tests/test_docs_active_path.py tests/test_universal_wild_no_block_matrix.py tests/test_apply_gate.py -q
```

Expected: all listed tests pass.

- [ ] **Step 4: Run the full test suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: full suite passes. If runtime is long, keep the process running until completion rather than stopping at a short timeout.

- [ ] **Step 5: Run whitespace/diff validation**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: `git diff --check` prints no errors. `git status --short --branch` shows the current branch and only intentional changes before final commit.

- [ ] **Step 6: Commit verification and sync changes if needed**

If `scripts\sync_installed_skill.py` changed tracked source files or repository docs, commit them:

```powershell
git add .agents/skills/hsconfig docs/operator docs/research src/hsconfig tests
git commit -m "chore: verify hsconfig mechanic visibility polish"
```

If no additional tracked files changed after Task 4, do not create an empty commit.

---

## Acceptance Criteria

- `support_for_roles(["choose_one_choice"])` returns a `choose_one` direct support row.
- `operator_visibility_bucket()` classifies `choose_one` as `identity_gated_direct`.
- `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are registered as `warning_only`.
- `generated_entity` and `spell_generation` remain `partial`.
- `summarize_mechanic_visibility()` returns `warning_boundaries` and preserves `first_warning_boundary`.
- `operator_summary.json` and `operator_guidance` carry `warning_boundaries`.
- Docs explain that visibility warnings are non-blocking and must not alter load-safe apply.
- `docs/research/current-truth.md` exists and points to the active research package for this wave.
- No HSTuner, replay, HDT, winrate, candidate promotion, or post-run tuning functionality is added.
- Targeted tests and full pytest pass.

## Self-Review Checklist

- [ ] Every requirement from the recommendation is represented by a task.
- [ ] No task changes `hsconfig apply` gate semantics.
- [ ] No task adds a new runtime JSON file type.
- [ ] No task converts warning-only mechanics into fake runtime rows.
- [ ] No task moves `generated_entity` out of `partial`.
- [ ] Documentation and installed skill copy stay aligned.
- [ ] Research index stays small and does not become a second operator manual.
