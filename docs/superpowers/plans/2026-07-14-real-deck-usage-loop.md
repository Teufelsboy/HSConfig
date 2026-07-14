# HSConfig Real-Deck Usage Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a slim, executable real-deck usage loop proof so HSConfig can be used with a fresh deck through `hsconfig configure`, `operator_summary.json`, and guarded apply without adding another gate or broad architecture layer.

**Architecture:** The plan preserves the current authority model: `reports/operator_summary.json` is the only normal apply authority, and source-contract, source-to-runtime, default-only, closure, and mechanic reports stay diagnostic. Implementation is documentation plus regression proof first; production code changes are allowed only if the fresh real-deck proof exposes a concrete defect.

**Tech Stack:** Python 3.11, pytest, existing `hsconfig.cli.main`, existing HSConfig report JSONs, existing operator docs.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add a new runtime apply gate.
- Do not let `source_contract_audit.json`, `source_to_runtime_explainability.json`, `config_usefulness`, closure freshness, or default-only details grant or deny runtime writes independently.
- Keep `reports/operator_summary.json` as the only normal apply authority.
- Keep the normal operator path as `hsconfig configure`.
- Runtime writes remain only through `hsconfig apply` or `hsconfig configure --apply`.
- Default-only output must be visible, not silent.
- `policy_backed_autonomous_mulligan` is acceptable for load-safe no-block output but must stay weaker than source-backed guide evidence.
- Effect semantics are not opening-hand mulligan keeps. Darkbishop Benedictus / `SW_448` may preserve hero-power behavior in per-card runtime config but must not enter `Mulligan.json` unless explicit opening-hand keep evidence exists.
- Normal HSConfig output must not emit `Presume.json` or `Concede.json`.
- No new dependencies.
- No broad runtime-surface expansion in this wave.

---

## File Structure

- Modify: `docs/operator/README.md`
  - Add one short "Real-Deck Usage Loop" section near the top-level normal path.
  - Purpose: tell the operator exactly what to run and exactly which fields to read.
- Create: `tests/test_real_deck_usage_loop.py`
  - Purpose: pin the new docs section and prove the normal `configure` path works for a fresh ShadowPriest package.
- No planned production source modifications.
  - If `tests/test_real_deck_usage_loop.py` fails because current production behavior violates the contract, stop and use `superpowers:systematic-debugging` before editing the smallest responsible source file.

---

### Task 1: Add Real-Deck Usage Loop Docs Contract Test

**Files:**
- Create: `tests/test_real_deck_usage_loop.py`

**Interfaces:**
- Consumes: `docs/operator/README.md` as the active normal operator guide.
- Produces: a docs regression that prevents future drift toward a second apply gate or default-only silence.

- [ ] **Step 1: Write the failing docs test**

Create `tests/test_real_deck_usage_loop.py` with this initial content:

```python
import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_DECK_NAME = "ShadowPriest"
SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
DARKBISHOP_CARD_ID = "SW_448"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _single_deck_dir(package: Path) -> Path:
    deck_dirs = [path for path in (package / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    return deck_dirs[0]


def test_operator_docs_define_real_deck_usage_loop_without_new_gate():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "## Real-Deck Usage Loop" in text
    assert "Use this loop after a source-contract or no-default-only audit passes." in text
    assert "Do not add a second apply gate for real-deck usage." in text
    assert "Run `hsconfig configure`" in text
    assert "Open `reports/operator_summary.json` first." in text
    assert "`default_only_runtime_surfaces` must be inspected when non-empty." in text
    assert "`source_to_runtime_explainability.json` is diagnostic." in text
    assert "`source_contract_audit.json` is diagnostic." in text
    assert "Concrete defects get targeted fixes; warnings do not become blockers." in text
```

- [ ] **Step 2: Run the docs test to verify it fails**

Run:

```powershell
python -m pytest tests/test_real_deck_usage_loop.py::test_operator_docs_define_real_deck_usage_loop_without_new_gate -q
```

Expected:

```text
FAILED tests/test_real_deck_usage_loop.py::test_operator_docs_define_real_deck_usage_loop_without_new_gate
```

The failure should be an assertion for missing `## Real-Deck Usage Loop` or one of the exact required sentences.

- [ ] **Step 3: Commit nothing yet**

Do not commit after Task 1. Task 2 supplies the docs that make this test pass.

---

### Task 2: Document The Real-Deck Usage Loop

**Files:**
- Modify: `docs/operator/README.md`
- Test: `tests/test_real_deck_usage_loop.py`

**Interfaces:**
- Consumes: the docs expectations from Task 1.
- Produces: a short normal-path runbook for real-deck usage.

- [ ] **Step 1: Insert the docs section**

In `docs/operator/README.md`, insert this section after the existing "Normal Operator Path" paragraph and before "Source Claim vs Runtime Surface":

```markdown
## Real-Deck Usage Loop

Use this loop after a source-contract or no-default-only audit passes.

1. Run `hsconfig configure` with the deck name, deck code, runtime root, and output directory.
2. Open `reports/operator_summary.json` first.
3. Treat `technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` as the load-safe apply signal.
4. Inspect `mulligan_policy_status` to see whether Mulligan is source-backed or policy-backed.
5. `default_only_runtime_surfaces` must be inspected when non-empty.
6. `source_to_runtime_explainability.json` is diagnostic.
7. `source_contract_audit.json` is diagnostic.
8. Do not add a second apply gate for real-deck usage.
9. Concrete defects get targeted fixes; warnings do not become blockers.

The loop is intentionally narrow. It proves that a real deck can move through the existing normal path without turning source-depth warnings, closure freshness, default-only diagnostics, or mechanic visibility into runtime-write permission.
```

- [ ] **Step 2: Run the docs test to verify it passes**

Run:

```powershell
python -m pytest tests/test_real_deck_usage_loop.py::test_operator_docs_define_real_deck_usage_loop_without_new_gate -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Run active docs regression tests**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py -q
```

Expected:

```text
passed
```

If this fails because the new section duplicates wording too heavily or conflicts with an existing assertion, adjust only `docs/operator/README.md` or `tests/test_real_deck_usage_loop.py`. Do not weaken the existing `test_docs_active_path.py` contract.

- [ ] **Step 4: Commit**

```powershell
git add docs/operator/README.md tests/test_real_deck_usage_loop.py
git commit -m "docs: add real deck usage loop"
```

---

### Task 3: Prove The Normal Configure Path With ShadowPriest

**Files:**
- Modify: `tests/test_real_deck_usage_loop.py`

**Interfaces:**
- Consumes: `hsconfig.cli.main(args: list[str]) -> int`.
- Consumes: normal `configure` output layout: `outputs/<DeckName>/04_package/reports/operator_summary.json`.
- Produces: a real-deck regression that proves the recommended usage loop works through the normal command, not only lower-level `research-deck` and `prepare`.

- [ ] **Step 1: Add the ShadowPriest configure-path proof test**

Append this test to `tests/test_real_deck_usage_loop.py`:

```python
def test_shadowpriest_configure_path_real_deck_loop_uses_operator_summary_without_new_gate(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )

    out = tmp_path / SHADOWPRIEST_DECK_NAME
    runtime_root = tmp_path / "runtime"

    code = main(
        [
            "configure",
            "--deck-name",
            SHADOWPRIEST_DECK_NAME,
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    package = out / "04_package"
    reports = package / "reports"
    operator = _json(reports / "operator_summary.json")
    source_contract_audit = _json(reports / "source_contract_audit.json")
    source_to_runtime = _json(reports / "source_to_runtime_explainability.json")
    deck_dir = _single_deck_dir(package)
    mulligan = _json(deck_dir / "Mulligan.json")
    darkbishop = _json(deck_dir / f"{DARKBISHOP_CARD_ID}.json")

    assert code == 0
    assert payload["status"] == "OK"
    assert Path(payload["package_path"]) == package

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert operator["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )

    assert operator["default_only_runtime_surfaces"] == []
    assert operator["default_only_runtime_surface_details"] == []
    assert operator["mulligan_policy_status"]["default_only"] is False
    assert operator["mulligan_policy_status"]["status"] in {
        "policy_backed",
        "source_backed",
        "source_and_policy_backed",
    }

    assert source_contract_audit["schema_version"] == 1
    assert isinstance(source_contract_audit["claim_lifecycle_rows"], list)
    assert source_to_runtime["authority"] == "diagnostic_only"
    assert source_to_runtime["apply_blocking"] is False
    assert operator["source_contract_audit_summary"]["non_blocking"] is True
    assert operator["source_to_runtime_explainability_summary"]["non_blocking"] is True
    assert operator["source_to_runtime_explainability_summary"]["closure_schema_current"] is True
    assert operator["source_to_runtime_explainability_summary"]["cards_missing_closure"] == 0

    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()

    mulligan_text = json.dumps(mulligan, sort_keys=True)
    assert DARKBISHOP_CARD_ID not in mulligan_text
    assert darkbishop["GameCardId"] == DARKBISHOP_CARD_ID
    darkbishop_text = json.dumps(darkbishop, sort_keys=True)
    assert "BeforeUseHeroPowerBonus" in darkbishop_text
    assert "hero_power" in darkbishop_text.lower()
```

- [ ] **Step 2: Run only the new ShadowPriest configure proof**

Run:

```powershell
python -m pytest tests/test_real_deck_usage_loop.py::test_shadowpriest_configure_path_real_deck_loop_uses_operator_summary_without_new_gate -q
```

Expected:

```text
1 passed
```

If this fails, do not broaden the plan. Use `superpowers:systematic-debugging` and identify the first concrete defect:

- missing `operator_summary.json` authority
- `default_only_runtime_surfaces` not empty
- stale closure rows
- diagnostic report wrongly applying or blocking
- missing `SW_448.json`
- `SW_448` incorrectly in `Mulligan.json`
- normal-path `Presume.json` or `Concede.json`

Fix only that defect and add the smallest regression necessary.

- [ ] **Step 3: Run the existing ShadowPriest closure proof**

Run:

```powershell
python -m pytest tests/test_shadowpriest_fresh_closure_proof.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Commit**

```powershell
git add tests/test_real_deck_usage_loop.py
git commit -m "test: prove real deck configure loop"
```

---

### Task 4: Preserve The Focused Contract Proof Suite

**Files:**
- No source files expected.
- Verification only.

**Interfaces:**
- Consumes: existing tests and the new real-deck loop test.
- Produces: proof that the new loop did not weaken no-default-only, apply authority, or docs boundaries.

- [ ] **Step 1: Run focused no-default-only and apply-authority suite**

Run:

```powershell
python -m pytest tests/test_config_usefulness.py tests/test_operator_summary.py tests/test_universal_wild_no_block_matrix.py tests/test_no_default_only_semantic_archetype_matrix.py tests/test_shadowpriest_fresh_closure_proof.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py tests/test_real_deck_usage_loop.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Validate the latest research-deep package**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-14-hsconfig-source-contract-no-default-only-audit\fields.yaml -d docs\research\2026-07-14-hsconfig-source-contract-no-default-only-audit\results -q
```

Expected:

```text
Validation passed: 5/5
Average coverage: 100.0%
```

- [ ] **Step 3: Run docs boundary scan**

Run:

```powershell
rg -n "second apply gate|source_contract_audit.json remains the apply authority|source_to_runtime_explainability.json remains the apply authority|default_only_runtime_surfaces can be ignored|Presume.json.*normal output|Concede.json.*normal output" README.md docs .agents src tests
```

Expected:

```text
No matches.
```

If the scan finds intended warning text that contains a forbidden phrase only to negate it, rewrite the docs to avoid the ambiguous phrase. Do not add exclusions unless the match is in a historical Superpowers plan or archived research.

- [ ] **Step 4: Run full tests if the focused suite passed**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
passed
```

Existing skips are acceptable if pytest reports them as skipped and no test fails.

- [ ] **Step 5: Commit only if verification required file changes**

If Task 4 required no file changes, do not create an empty commit.

If Task 4 required a small wording or test correction:

```powershell
git add docs tests README.md .agents src
git commit -m "test: preserve real deck usage loop contracts"
```

---

### Task 5: Final Git And Handoff

**Files:**
- No source files expected.
- Git state only.

**Interfaces:**
- Consumes: commits from Tasks 2-4.
- Produces: clean branch ready for push or merge.

- [ ] **Step 1: Inspect final status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## main...origin/main [ahead N]
```

or:

```text
## main...origin/main
```

There must be no unstaged or uncommitted tracked changes. If generated outputs, caches, or temp package files exist, remove only those generated by this implementation.

- [ ] **Step 2: Inspect final diff if uncommitted changes remain**

Run:

```powershell
git diff -- docs/operator/README.md tests/test_real_deck_usage_loop.py
```

Expected:

```text
No output if everything was committed.
```

If there is output, either commit the intended plan changes or revert only files created by this implementation after confirming they are not needed.

- [ ] **Step 3: Push only when requested or when continuing the user's standing "keep GitHub current" direction**

Run:

```powershell
git push origin main
```

Expected:

```text
main -> main
```

- [ ] **Step 4: Final report**

Report these exact points:

- The real-deck usage loop is documented.
- The normal `configure` path is proven with ShadowPriest.
- `operator_summary.json` remains the only normal apply authority.
- Default-only surfaces remain visible and non-silent through the existing operator summary and config usefulness diagnostics.
- Darkbishop `SW_448` preserves hero-power behavior without becoming a Mulligan keep.
- Tests and git status result.

---

## Self-Review

- Spec coverage: The plan implements the recommended Option A by freezing the source-contract architecture and adding a real-deck usage proof instead of another architecture wave.
- No second gate: Every task keeps `operator_summary.json` as the only apply authority.
- No default-only silence: The new tests assert `default_only_runtime_surfaces == []`, empty details for ShadowPriest, and non-default Mulligan policy.
- Darkbishop boundary: The new configure-path proof checks `SW_448` is absent from `Mulligan.json` and present as a per-card hero-power behavior file.
- Slimness: No new production module, no new CLI command, and no new dependency are planned.
- Autonomy: Valid packages remain `load_safe_apply`; warnings stay diagnostic.
- Placeholder scan: No incomplete placeholder markers or unspecified implementation steps remain.
