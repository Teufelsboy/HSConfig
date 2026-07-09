# HSConfig No-Block Polish And Mechanic Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's no-block behavior easier to trust by fixing installed-skill sync hygiene and exposing richer mechanic coverage in the normal operator reports without widening HSConfig beyond pre-run config generation.

**Architecture:** Keep `reports/operator_summary.json` as the single normal gate. Keep `config_usefulness` and mechanic coverage descriptive and non-blocking. Add one richer visibility layer on top of the existing mechanic support registry so valid packages still apply even when some mechanics are partial or warning-only.

**Tech Stack:** Python 3, pytest, HearthRanger VisionAI JSON package outputs, repo-local Codex skill files in `.agents/skills/hsconfig`, installed skill copy in `C:\Users\darbo\.codex\skills\hsconfig`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- HSConfig is pre-run only: do not add replay parsing, HDT parsing, Power.log parsing, winrate validation, candidate promotion, or post-run tuning.
- Keep the normal runtime surface limited to `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and conditional exact-sequence `Combo.json`.
- `Presume.json` and `Concede.json` stay out of the normal path.
- `VALID_PACKAGE + runtime_load_safe=true + runtime_apply_mode=load_safe_apply` stays apply-eligible without manual approval.
- `config_usefulness`, mechanic warnings, partial support, missing guide claims, and warning-only mechanics are descriptive and must not become hidden apply blockers.
- Hard blockers remain: malformed deckcode, unresolved exact CardID identity, invalid JSON, unsupported filenames or blocks, missing required runtime files, undeclared files, nested files, forbidden normal-path optional surfaces, and forged or stale apply evidence.
- Keep the representative/no-block deck matrix stable; do not add more proof decks in this wave.

---

## File Structure

- `C:\Users\darbo\Documents\HSConfig\scripts\sync_installed_skill.py`
  - Keep syncing exact repo skill bytes to the installed Codex skill.
  - Add drift diagnostics so newline-only byte drift is understandable.
- `C:\Users\darbo\Documents\HSConfig\tests\test_skill_sync.py`
  - Lock the improved drift diagnostics and the exact-sync behavior.
- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\mechanic_support.py`
  - Keep the current support registry.
  - Add a richer operator-facing visibility summarizer.
- `C:\Users\darbo\Documents\HSConfig\tests\test_mechanic_support.py`
  - Lock direct, identity-gated direct, partial, and warning-only visibility buckets.
- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_readiness.py`
  - Add `summary.mechanic_visibility` alongside the existing `summary.mechanic_support`.
- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
  - Add `mechanic_visibility_summary` to the normal operator gate payload.
- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_guidance.py`
  - Mirror `mechanic_visibility_summary` into operator guidance.
- `C:\Users\darbo\Documents\HSConfig\tests\test_config_readiness.py`
  - Prove readiness emits visibility without blocking load-safe packages.
- `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`
  - Prove operator summary exposes visibility without changing apply permission.
- `C:\Users\darbo\Documents\HSConfig\tests\test_operator_guidance.py`
  - Prove guidance carries the visibility summary.
- `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
  - Explain where to read mechanic visibility.
- `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`
  - Document visibility buckets and the non-blocking rule.
- `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
  - Update operator instructions to inspect `mechanic_visibility_summary`.
- `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
  - Keep the skill reference aligned with the docs.
- `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
  - Lock docs/skill language so future edits do not hide the no-block visibility rule.

---

### Task 1: Skill Sync Hygiene And Drift Diagnostics

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\scripts\sync_installed_skill.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_sync.py`

**Interfaces:**
- Consumes: `SOURCE_SKILL: Path`, `DEFAULT_INSTALL_ROOT: Path`, `folders_match(left: Path, right: Path) -> bool`
- Produces: `folder_diff(left: Path, right: Path) -> dict[str, object]`
- Produces: `folders_match(left: Path, right: Path) -> bool` remains backward compatible

- [ ] **Step 1: Write failing tests for newline-only drift diagnostics**

Append this test to `C:\Users\darbo\Documents\HSConfig\tests\test_skill_sync.py`:

```python
def test_skill_sync_check_explains_newline_only_drift(tmp_path: Path):
    install_root = tmp_path / "codex" / "skills"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    installed_skill = install_root / "hsconfig" / "SKILL.md"
    installed_skill.write_bytes(
        installed_skill.read_bytes().replace(b"\r\n", b"\n")
    )

    check = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    output = check.stdout + check.stderr
    assert check.returncode == 1
    assert "SKILL.md" in output
    assert "normalized text matches" in output
    assert "run without --check to re-sync" in output
```

- [ ] **Step 2: Run the new test and confirm it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_sync.py::test_skill_sync_check_explains_newline_only_drift -q
```

Expected: FAIL because `sync_installed_skill.py --check` currently prints only `HSConfig skill drift detected`.

- [ ] **Step 3: Add exact drift diagnostics without relaxing the sync contract**

Modify `C:\Users\darbo\Documents\HSConfig\scripts\sync_installed_skill.py`.

Add these helpers after `_iter_files`:

```python
TEXT_LIKE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}


def _normalized_text_equal(left_bytes: bytes, right_bytes: bytes) -> bool:
    return left_bytes.replace(b"\r\n", b"\n") == right_bytes.replace(b"\r\n", b"\n")


def folder_diff(left: Path, right: Path) -> dict[str, object]:
    if not left.exists() or not right.exists():
        return {
            "matches": False,
            "reason": "missing_folder",
            "left_exists": left.exists(),
            "right_exists": right.exists(),
            "diffs": [],
        }

    left_files = _iter_files(left)
    right_files = _iter_files(right)
    diffs: list[dict[str, object]] = []
    if left_files != right_files:
        left_set = set(left_files)
        right_set = set(right_files)
        for rel in sorted(left_set - right_set):
            diffs.append({"path": rel.as_posix(), "kind": "missing_installed_file"})
        for rel in sorted(right_set - left_set):
            diffs.append({"path": rel.as_posix(), "kind": "unexpected_installed_file"})

    for rel in left_files:
        if rel not in right_files:
            continue
        left_bytes = (left / rel).read_bytes()
        right_bytes = (right / rel).read_bytes()
        if left_bytes == right_bytes:
            continue
        entry: dict[str, object] = {"path": rel.as_posix(), "kind": "bytes_differ"}
        if rel.suffix.lower() in TEXT_LIKE_SUFFIXES:
            entry["normalized_text_equal"] = _normalized_text_equal(left_bytes, right_bytes)
        diffs.append(entry)

    return {"matches": not diffs, "reason": "diffs_found" if diffs else "in_sync", "diffs": diffs}
```

Replace `folders_match(...)` with:

```python
def folders_match(left: Path, right: Path) -> bool:
    return bool(folder_diff(left, right).get("matches"))
```

In `main(...)`, replace the `--check` branch with:

```python
    if args.check:
        diff = folder_diff(SOURCE_SKILL, target)
        if diff["matches"]:
            print(f"HSConfig skill is in sync: {target}")
            return 0
        print(f"HSConfig skill drift detected: {target}", file=sys.stderr)
        for item in list(diff.get("diffs", []))[:10]:
            if not isinstance(item, dict):
                continue
            detail = f"- {item.get('path')}: {item.get('kind')}"
            if item.get("normalized_text_equal") is True:
                detail += " (normalized text matches; run without --check to re-sync exact bytes)"
            print(detail, file=sys.stderr)
        return 1
```

- [ ] **Step 4: Run sync tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_sync.py -q
```

Expected: all `tests/test_skill_sync.py` tests pass.

- [ ] **Step 5: Re-sync the installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected:

```text
Synced HSConfig skill to C:\Users\darbo\.codex\skills\hsconfig
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts\sync_installed_skill.py tests\test_skill_sync.py
git commit -m "chore: explain hsconfig skill sync drift"
```

---

### Task 2: Mechanic Visibility Buckets

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\mechanic_support.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_mechanic_support.py`

**Interfaces:**
- Consumes: `support_for_roles(roles: Iterable[str]) -> list[dict[str, Any]]`
- Consumes: each support row contains `mechanic`, `support_level`, `normal_path_surfaces`, and `warning_boundary`
- Produces: `operator_visibility_bucket(support: dict[str, Any]) -> str`
- Produces: `summarize_mechanic_visibility(rows: Iterable[dict[str, Any]]) -> dict[str, Any]`

- [ ] **Step 1: Write failing tests for richer visibility buckets**

Append these tests to `C:\Users\darbo\Documents\HSConfig\tests\test_mechanic_support.py`:

```python
from hsconfig.mechanic_support import (
    operator_visibility_bucket,
    summarize_mechanic_visibility,
    support_for_roles,
)


def test_operator_visibility_bucket_marks_identity_gated_direct_mechanics():
    rows = support_for_roles(["discover", "hero_power_transform", "battlecry"])
    buckets = {row["mechanic"]: operator_visibility_bucket(row) for row in rows}

    assert buckets["battlecry"] == "direct"
    assert buckets["discover"] == "identity_gated_direct"
    assert buckets["hero_power_transform"] == "identity_gated_direct"


def test_summarize_mechanic_visibility_is_non_blocking_and_operator_readable():
    summary = summarize_mechanic_visibility(
        [
            {
                "card_id": "DISCOVER_001",
                "mechanic_support": support_for_roles(["discover"]),
            },
            {
                "card_id": "DREDGE_001",
                "mechanic_support": support_for_roles(["dredge"]),
            },
            {
                "card_id": "AURA_001",
                "mechanic_support": support_for_roles(["magnetic"]),
            },
        ]
    )

    assert summary["non_blocking"] is True
    assert summary["bucket_counts"] == {
        "direct": 0,
        "identity_gated_direct": 1,
        "partial": 1,
        "warning_only": 1,
    }
    assert summary["mechanics_by_bucket"]["identity_gated_direct"] == ["discover"]
    assert summary["mechanics_by_bucket"]["partial"] == ["aura"]
    assert summary["mechanics_by_bucket"]["warning_only"] == ["dredge"]
    assert summary["warning_only_card_count"] == 1
    assert summary["first_warning_boundary"]["mechanic"] == "dredge"
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_support.py::test_operator_visibility_bucket_marks_identity_gated_direct_mechanics tests/test_mechanic_support.py::test_summarize_mechanic_visibility_is_non_blocking_and_operator_readable -q
```

Expected: FAIL because `operator_visibility_bucket` and `summarize_mechanic_visibility` are not defined.

- [ ] **Step 3: Add the visibility helpers**

Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\mechanic_support.py`.

Add this constant after `NON_MECHANIC_ROLES`:

```python
IDENTITY_GATED_DIRECT_MECHANICS = {
    "discover",
    "generated_entity",
    "hero_power_transform",
}
VISIBILITY_BUCKETS = ("direct", "identity_gated_direct", "partial", "warning_only")
```

Add these functions after `support_for_roles(...)`:

```python
def operator_visibility_bucket(support: dict[str, Any]) -> str:
    mechanic = str(support.get("mechanic", ""))
    support_level = str(support.get("support_level", ""))
    if support_level == "direct" and mechanic in IDENTITY_GATED_DIRECT_MECHANICS:
        return "identity_gated_direct"
    if support_level in {"direct", "partial", "warning_only"}:
        return support_level
    return "warning_only"


def summarize_mechanic_visibility(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    bucket_counts: Counter[str] = Counter()
    mechanics_by_bucket: dict[str, set[str]] = {bucket: set() for bucket in VISIBILITY_BUCKETS}
    warning_cards: set[str] = set()
    first_warning_boundary: dict[str, str] | None = None

    for row in rows:
        card_id = str(row.get("card_id", ""))
        for support in row.get("mechanic_support", []):
            if not isinstance(support, dict):
                continue
            mechanic = str(support.get("mechanic", ""))
            bucket = operator_visibility_bucket(support)
            bucket_counts[bucket] += 1
            if mechanic:
                mechanics_by_bucket.setdefault(bucket, set()).add(mechanic)
            if bucket == "warning_only":
                if card_id:
                    warning_cards.add(card_id)
                if first_warning_boundary is None:
                    first_warning_boundary = {
                        "mechanic": mechanic,
                        "warning_boundary": str(support.get("warning_boundary", "")),
                    }

    return {
        "non_blocking": True,
        "bucket_counts": {bucket: bucket_counts[bucket] for bucket in VISIBILITY_BUCKETS},
        "mechanics_by_bucket": {
            bucket: sorted(mechanics_by_bucket.get(bucket, set()))
            for bucket in VISIBILITY_BUCKETS
        },
        "warning_only_card_count": len(warning_cards),
        "first_warning_boundary": first_warning_boundary,
    }
```

- [ ] **Step 4: Run mechanic support tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_support.py -q
```

Expected: all mechanic support tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src\hsconfig\mechanic_support.py tests\test_mechanic_support.py
git commit -m "feat: expose mechanic visibility buckets"
```

---

### Task 3: Thread Mechanic Visibility Into Operator Reports

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_readiness.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_guidance.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_config_readiness.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_operator_guidance.py`

**Interfaces:**
- Consumes: `summarize_mechanic_visibility(rows: Iterable[dict[str, Any]]) -> dict[str, Any]`
- Produces: `per_card_config_readiness_report["summary"]["mechanic_visibility"]`
- Produces: `operator_summary["mechanic_visibility_summary"]`
- Produces: `operator_summary["operator_guidance"]["mechanic_visibility_summary"]`

- [ ] **Step 1: Write failing readiness test**

Add assertions to `test_config_readiness_reports_mechanic_support_without_blocking_load_safe` in `C:\Users\darbo\Documents\HSConfig\tests\test_config_readiness.py`:

```python
    visibility = report["summary"]["mechanic_visibility"]
    assert visibility["non_blocking"] is True
    assert visibility["bucket_counts"]["direct"] == 1
    assert visibility["bucket_counts"]["warning_only"] == 1
    assert visibility["mechanics_by_bucket"]["warning_only"] == ["dredge"]
    assert visibility["first_warning_boundary"]["mechanic"] == "dredge"
```

- [ ] **Step 2: Write failing operator summary test**

Append this test to `C:\Users\darbo\Documents\HSConfig\tests\test_operator_summary.py`:

```python
def test_operator_summary_exposes_mechanic_visibility_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="Mechanic Visibility",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        config_readiness_report={
            "summary": {
                "total_cards": 2,
                "generic_low_confidence": 0,
                "cards_needing_guide_claims": 0,
                "cards_needing_runtime_surface": 0,
                "cards_needing_mulligan_claims": 0,
                "cards_needing_combo_sequence": 0,
                "cards_needing_condition_lowering": 0,
                "cards_needing_mechanic_lowering": 0,
                "mechanic_visibility": {
                    "non_blocking": True,
                    "bucket_counts": {
                        "direct": 1,
                        "identity_gated_direct": 1,
                        "partial": 0,
                        "warning_only": 1,
                    },
                    "mechanics_by_bucket": {
                        "direct": ["battlecry"],
                        "identity_gated_direct": ["discover"],
                        "partial": [],
                        "warning_only": ["dredge"],
                    },
                    "warning_only_card_count": 1,
                    "first_warning_boundary": {
                        "mechanic": "dredge",
                        "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
                    },
                },
            },
            "cards": {},
        },
        generated_files=[
            "CustomConfig/mechanicvisibility/GlobalValues.json",
            "CustomConfig/mechanicvisibility/Mulligan.json",
            "CustomConfig/mechanicvisibility/DREDGE_001.json",
        ],
    )

    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["mechanic_visibility_summary"]["non_blocking"] is True
    assert summary["mechanic_visibility_summary"]["mechanics_by_bucket"]["warning_only"] == ["dredge"]
    assert summary["operator_guidance"]["mechanic_visibility_summary"]["warning_only_card_count"] == 1
```

- [ ] **Step 3: Write failing operator guidance test**

Append this test to `C:\Users\darbo\Documents\HSConfig\tests\test_operator_guidance.py`:

```python
def test_warning_guidance_carries_mechanic_visibility_summary():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "mechanic_visibility_summary": {
                "non_blocking": True,
                "bucket_counts": {
                    "direct": 0,
                    "identity_gated_direct": 0,
                    "partial": 1,
                    "warning_only": 1,
                },
                "mechanics_by_bucket": {
                    "direct": [],
                    "identity_gated_direct": [],
                    "partial": ["aura"],
                    "warning_only": ["tradeable"],
                },
                "warning_only_card_count": 1,
                "first_warning_boundary": {
                    "mechanic": "tradeable",
                    "warning_boundary": "Trade-now decisions have no documented normal-path VisionAI runtime block.",
                },
            },
            "semantic_blockers": [],
        }
    )

    assert guidance["safe_to_apply"] is True
    assert guidance["normal_next_step"] == "apply_with_warnings"
    assert guidance["mechanic_visibility_summary"]["non_blocking"] is True
    assert guidance["mechanic_visibility_summary"]["mechanics_by_bucket"]["partial"] == ["aura"]
```

- [ ] **Step 4: Run targeted tests and confirm they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_readiness.py::test_config_readiness_reports_mechanic_support_without_blocking_load_safe tests/test_operator_summary.py::test_operator_summary_exposes_mechanic_visibility_without_blocking_apply tests/test_operator_guidance.py::test_warning_guidance_carries_mechanic_visibility_summary -q
```

Expected: FAIL because `mechanic_visibility` and `mechanic_visibility_summary` are not yet emitted.

- [ ] **Step 5: Add readiness summary output**

Modify the import in `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_readiness.py`:

```python
from hsconfig.mechanic_support import (
    support_for_roles,
    summarize_mechanic_support,
    summarize_mechanic_visibility,
)
```

Modify `_summary(...)` to include:

```python
        "mechanic_visibility": summarize_mechanic_visibility(rows),
```

The final `_summary(...)` return must contain both keys:

```python
        "mechanic_support": summarize_mechanic_support(rows),
        "mechanic_visibility": summarize_mechanic_visibility(rows),
```

- [ ] **Step 6: Add operator summary extraction**

Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_summary.py`.

Add this helper after `_mechanic_warning_summary(...)`:

```python
def _mechanic_visibility_summary(
    config_readiness_report: dict[str, Any] | None,
    config_readiness_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    empty_summary = {
        "non_blocking": True,
        "bucket_counts": {
            "direct": 0,
            "identity_gated_direct": 0,
            "partial": 0,
            "warning_only": 0,
        },
        "mechanics_by_bucket": {
            "direct": [],
            "identity_gated_direct": [],
            "partial": [],
            "warning_only": [],
        },
        "warning_only_card_count": 0,
        "first_warning_boundary": None,
    }
    summary = {}
    if isinstance(config_readiness_report, dict):
        summary = config_readiness_report.get("summary", {})
    if not isinstance(summary, dict) or "mechanic_visibility" not in summary:
        summary = config_readiness_summary or {}
    if not isinstance(summary, dict):
        return empty_summary
    visibility = summary.get("mechanic_visibility", {})
    if not isinstance(visibility, dict):
        return empty_summary

    bucket_counts = visibility.get("bucket_counts", {})
    if not isinstance(bucket_counts, dict):
        bucket_counts = {}
    mechanics_by_bucket = visibility.get("mechanics_by_bucket", {})
    if not isinstance(mechanics_by_bucket, dict):
        mechanics_by_bucket = {}

    return {
        "non_blocking": bool(visibility.get("non_blocking", True)),
        "bucket_counts": {
            "direct": _int_value(bucket_counts.get("direct", 0)),
            "identity_gated_direct": _int_value(bucket_counts.get("identity_gated_direct", 0)),
            "partial": _int_value(bucket_counts.get("partial", 0)),
            "warning_only": _int_value(bucket_counts.get("warning_only", 0)),
        },
        "mechanics_by_bucket": {
            "direct": [str(item) for item in mechanics_by_bucket.get("direct", [])],
            "identity_gated_direct": [
                str(item) for item in mechanics_by_bucket.get("identity_gated_direct", [])
            ],
            "partial": [str(item) for item in mechanics_by_bucket.get("partial", [])],
            "warning_only": [
                str(item) for item in mechanics_by_bucket.get("warning_only", [])
            ],
        },
        "warning_only_card_count": _int_value(visibility.get("warning_only_card_count", 0)),
        "first_warning_boundary": visibility.get("first_warning_boundary"),
    }
```

In `build_operator_summary(...)`, after `mechanic_warning_summary = ...`, add:

```python
    mechanic_visibility_summary = _mechanic_visibility_summary(
        config_readiness_report,
        effective_config_readiness_summary,
    )
```

In the `summary = { ... }` payload, add this key directly after `mechanic_warning_summary`:

```python
        "mechanic_visibility_summary": mechanic_visibility_summary,
```

- [ ] **Step 7: Add operator guidance passthrough**

Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\operator_guidance.py`.

Add this helper after `_mechanic_warning_fields(...)`:

```python
def _mechanic_visibility_fields(summary: dict[str, Any]) -> dict[str, Any]:
    mechanic_visibility_summary = summary.get("mechanic_visibility_summary")
    if isinstance(mechanic_visibility_summary, dict):
        return {"mechanic_visibility_summary": mechanic_visibility_summary}
    return {
        "mechanic_visibility_summary": {
            "non_blocking": True,
            "bucket_counts": {
                "direct": 0,
                "identity_gated_direct": 0,
                "partial": 0,
                "warning_only": 0,
            },
            "mechanics_by_bucket": {
                "direct": [],
                "identity_gated_direct": [],
                "partial": [],
                "warning_only": [],
            },
            "warning_only_card_count": 0,
            "first_warning_boundary": None,
        }
    }
```

Add `**_mechanic_visibility_fields(summary),` immediately after every existing `**_mechanic_warning_fields(summary),` occurrence in `build_operator_guidance(...)`.

- [ ] **Step 8: Run targeted report tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_readiness.py tests/test_operator_summary.py tests/test_operator_guidance.py -q
```

Expected: all targeted report tests pass.

- [ ] **Step 9: Commit**

Run:

```powershell
git add src\hsconfig\config_readiness.py src\hsconfig\operator_summary.py src\hsconfig\operator_guidance.py tests\test_config_readiness.py tests\test_operator_summary.py tests\test_operator_guidance.py
git commit -m "feat: surface mechanic visibility in operator reports"
```

---

### Task 4: Docs, Skill Alignment, And Final Verification

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`

**Interfaces:**
- Consumes: `operator_summary["mechanic_visibility_summary"]`
- Consumes: `operator_guidance["mechanic_visibility_summary"]`
- Produces: docs and skill text that say mechanic visibility is descriptive and non-blocking

- [ ] **Step 1: Write failing docs/skill test**

Append this test to `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`:

```python
def test_docs_and_skill_explain_mechanic_visibility_without_blocking_apply():
    paths = [
        Path("docs/operator/README.md"),
        Path("docs/operator/universal-wild-no-block-contract.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "mechanic_visibility_summary" in combined
    assert "identity_gated_direct" in combined
    assert "warning-only mechanics are descriptive" in combined
    assert "must not block load-safe apply" in combined
```

- [ ] **Step 2: Run the new docs/skill test and confirm it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py::test_docs_and_skill_explain_mechanic_visibility_without_blocking_apply -q
```

Expected: FAIL until the docs and skill are updated.

- [ ] **Step 3: Update operator docs**

In `C:\Users\darbo\Documents\HSConfig\docs\operator\README.md`, in the section that tells the operator to open `reports/operator_summary.json`, add this paragraph:

```markdown
- `mechanic_visibility_summary` is descriptive and non-blocking. It shows `direct`, `identity_gated_direct`, `partial`, and `warning_only` mechanic buckets so a valid package can be applied while still making Dredge, Tradeable, unresolved generation, or partial targeting limits visible.
```

In `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`, under `## Mechanic Support Levels`, replace the current bullet list with:

```markdown
- `direct`: HSConfig can emit the documented normal-path runtime row.
- `identity_gated_direct`: HSConfig can emit the documented runtime row only when exact option, generated-card, or transformed-identity resolution is available.
- `partial`: HSConfig can emit only the parts that map to documented VisionAI blocks.
- `warning_only`: HSConfig must not invent a runtime row for the mechanic's signature action.

`mechanic_visibility_summary` is an operator-facing explanation layer. It is not an apply gate. Partial and warning-only mechanics are descriptive and must not block load-safe apply when `technical_status=VALID_PACKAGE` and `runtime_apply_mode=load_safe_apply`.
```

- [ ] **Step 4: Update the installed-skill source files**

In `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`, add this bullet near the existing `mechanic_warning_summary` or `operator_summary.json` guidance:

```markdown
- Inspect `mechanic_visibility_summary` in `reports/operator_summary.json` to understand direct, identity-gated direct, partial, and warning-only mechanic coverage. Treat warning-only mechanics as descriptive; they must not block load-safe apply.
```

In `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`, add this paragraph near the operator summary guidance:

```markdown
`mechanic_visibility_summary` explains mechanic coverage buckets: `direct`, `identity_gated_direct`, `partial`, and `warning_only`. Warning-only mechanics are descriptive and must not block load-safe apply when the package is technically valid.
```

- [ ] **Step 5: Run docs/skill tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py -q
```

Expected: all skill file tests pass.

- [ ] **Step 6: Sync installed skill and verify sync**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected:

```text
Synced HSConfig skill to C:\Users\darbo\.codex\skills\hsconfig
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 7: Run targeted no-block and operator suites**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_output_competence_matrix.py tests/test_skill_sync.py tests/test_scope_boundaries.py tests/test_mechanic_support.py tests/test_config_readiness.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_skill_files.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 8: Run full test suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: full suite passes. If the full suite exceeds the local timeout, rerun the targeted suites above and record the timeout as a verification limitation in the final response.

- [ ] **Step 9: Commit**

Run:

```powershell
git add docs\operator\README.md docs\operator\universal-wild-no-block-contract.md .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_skill_files.py
git commit -m "docs: explain mechanic visibility no-block contract"
```

---

## Final Verification Checklist

- [ ] `python scripts\sync_installed_skill.py --check`
- [ ] `$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_output_competence_matrix.py tests/test_skill_sync.py tests/test_scope_boundaries.py tests/test_mechanic_support.py tests/test_config_readiness.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_skill_files.py -q`
- [ ] `$env:PYTHONPATH='src'; python -m pytest -q`
- [ ] `git status --short --branch`

## Expected Final State

- Installed `hsconfig` skill is byte-synced with `.agents/skills/hsconfig`.
- `operator_summary.json` contains both:
  - `mechanic_warning_summary`
  - `mechanic_visibility_summary`
- `operator_guidance` mirrors both mechanic summaries.
- `config_readiness_report.summary` contains both:
  - `mechanic_support`
  - `mechanic_visibility`
- Valid packages remain apply-eligible even with partial or warning-only mechanic coverage.
- Dredge and Tradeable remain warning-only.
- Magnetic and Imbue are not overclaimed as fully direct support.
- HSConfig remains pre-run only and does not absorb HSTuner responsibilities.

## Self-Review

- **Spec coverage:** The plan covers sync hygiene, richer mechanic visibility, operator report threading, docs/skill alignment, and no-block verification.
- **Placeholder scan:** No placeholder tasks remain. Every code-changing task has concrete target files, tests, snippets, commands, and expected outcomes.
- **Type consistency:** New names are consistent across tasks: `operator_visibility_bucket`, `summarize_mechanic_visibility`, `mechanic_visibility`, and `mechanic_visibility_summary`.
- **Scope check:** The plan does not add replay analysis, winrate handling, post-run tuning, new deck fixtures, or new runtime surfaces.
