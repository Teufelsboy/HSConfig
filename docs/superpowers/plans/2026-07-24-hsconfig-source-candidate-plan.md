# HSConfig Source Candidate Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a thin, deterministic source-candidate planning layer before `source-acquire` and `source-autopilot`, so HSConfig can explain which public guide URLs, search queries, and card-level claim targets are needed for the best possible pre-run config without adding HSTuner, replay/log analysis, runtime sequencing logic, or another apply gate.

**Architecture:** Build one pure planning module that consumes deck identity, candidate archetypes, explicit source URLs, and the existing source candidate registry. It emits a diagnostic `source_candidate_plan.json` with URL priority, query suggestions, card-level evidence targets, missing-source actions, and non-blocking boundaries. Wire that plan into `source-manifest` and `configure --online-source`, then keep the existing path unchanged: `source-acquire -> source-autopilot -> research-deck -> prepare -> validate -> optional apply`.

**Tech Stack:** Python, pytest, existing HSConfig CLI, existing deck identity/manifest/source registry modules, JSON reports, existing installed skill sync and contract guardrails.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Refresh repository state before implementation: `git fetch --all --prune --tags`, `git remote prune origin`, then inspect currentness.
- Keep the worktree clean at completion; no backup files, no generated runtime evidence, no uncommitted outputs.
- Keep HSConfig pre-run only.
- Do not add HSTuner, replay parsing, HDT parsing, Power.log parsing, winrate analysis, post-game tuning, or gameplay improvement claims.
- Do not encode HearthRanger play sequencing or assume HearthRanger misplays. HearthRanger remains the runtime actor.
- Do not create a new runtime apply authority. `reports/operator_summary.json` remains the only normal apply authority.
- Do not turn source quality, `SOURCE_BACKED_STRONG`, source-candidate planning, default-only visibility, or source closure into apply blockers.
- `source_status_apply_blocking` must remain `false` for source-quality work.
- No hidden default-only success: default-only runtime surfaces remain visible diagnostic quality debt.
- Normal output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for exact source-backed combo sequence evidence.
- `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` stay outside the normal HSConfig path.
- Static card semantics may support deterministic effect rows such as Darkbishop Benedictus / `SW_448` hero-power transform. They must not create opening-hand Mulligan keeps without explicit source text.
- Source candidate plans are acquisition guidance only: they may suggest URLs and queries, but they cannot promote, block, validate, or write runtime config.

---

## File Structure

- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_candidate_plan.py`
  - Responsibility: pure diagnostic source-candidate plan builder.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\source_workflow.py`
  - Responsibility: write `source_candidate_plan.json` from `source-manifest`; pass candidate count into source acquisition.
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
  - Responsibility: use the plan for `--online-source` URL ordering and expose a compact summary in `configure_summary.json`.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\autonomous-source-builder-next.md`
  - Responsibility: document source-candidate planning as the next acquisition step, not a runtime gate.
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-builder-workflow.md`
  - Responsibility: document where `source_candidate_plan.json` appears in the inspected workflow.
- Modify only if needed: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\guide-research-policy.md`
  - Responsibility: reference source-candidate plans without bloating `SKILL.md`.
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_source_candidate_plan.py`
  - Responsibility: unit-test the pure planner.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_manifest_cli.py`
  - Responsibility: assert `source-manifest` writes both manifest and candidate plan.
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_online_source.py` or `tests\test_configure_auto_source.py`
  - Responsibility: assert `configure --online-source` exposes the plan and still routes through the existing source/acquire/autopilot path.
- Modify only if needed: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`
  - Responsibility: ensure active docs mention the source-candidate plan if guide docs are updated.

---

### Task 1: Add Failing Source-Candidate Plan Tests

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_source_candidate_plan.py`

**Interfaces:**
- Imports `build_source_candidate_plan` from `hsconfig.source_candidate_plan`.
- Consumes deck identity dicts shaped like `build_deck_identity()` output.
- Produces tests that fail until the pure planner exists.

- [ ] **Step 1: Create the failing test module**

Add tests covering these cases:

```python
def test_source_candidate_plan_is_diagnostic_and_non_blocking_for_shadowpriest():
    plan = build_source_candidate_plan(
        deck_name="ShadowPriest",
        deck_code=SHADOWPRIEST_CODE,
        deck_identity=shadowpriest_identity(),
        candidate_archetypes={"primary_archetype": "wild_aggro_shadow_priest"},
        explicit_source_urls=[],
        current_date="2026-07-24",
    )

    assert plan["authority"] == "diagnostic_source_candidate_plan"
    assert plan["apply_blocking"] is False
    assert plan["runtime_write_performed"] is False
    assert plan["source_status_apply_blocking"] is False
    assert plan["candidate_registry_url_count"] >= 1
    assert plan["source_urls"][0].endswith("voidburn-wild-aggro-shadow-priest")
    assert plan["first_missing_source_action"] == "none"
    assert plan["query_count"] >= 1
    assert plan["target_summary"]["card_role_targets"] == len(plan["card_targets"])
```

Add a Darkbishop-specific assertion:

```python
def test_source_candidate_plan_keeps_darkbishop_effect_separate_from_mulligan():
    plan = build_source_candidate_plan(
        deck_name="ShadowPriest",
        deck_code=SHADOWPRIEST_CODE,
        deck_identity=shadowpriest_identity(),
        candidate_archetypes={"primary_archetype": "wild_aggro_shadow_priest"},
        explicit_source_urls=[],
        current_date="2026-07-24",
    )

    darkbishop = {
        row["card_id"]: row for row in plan["card_targets"]
    }["SW_448"]

    assert "hero_power_transform" in darkbishop["supported_static_claim_kinds"]
    assert "mulligan_keep" in darkbishop["requires_explicit_source_claim_kinds"]
    assert darkbishop["effect_semantics_not_mulligan_keep"] is True
```

Add an unknown-deck assertion:

```python
def test_source_candidate_plan_for_unknown_deck_suggests_queries_without_blocking():
    plan = build_source_candidate_plan(
        deck_name="UnknownDeck",
        deck_code="AAEBA-placeholder",
        deck_identity=unknown_identity(),
        candidate_archetypes={"primary_archetype": "generic_low_confidence"},
        explicit_source_urls=[],
        current_date="2026-07-24",
    )

    assert plan["candidate_registry_url_count"] == 0
    assert plan["source_urls"] == []
    assert plan["query_count"] >= 2
    assert plan["first_missing_source_action"] == "add_public_guide_url_or_use_static_semantics"
    assert plan["apply_blocking"] is False
    assert plan["source_status_apply_blocking"] is False
```

Add a URL ordering assertion:

```python
def test_source_candidate_plan_keeps_explicit_urls_before_registry_urls():
    explicit = ["https://example.com/manual-guide"]
    plan = build_source_candidate_plan(
        deck_name="ShadowPriest",
        deck_code=SHADOWPRIEST_CODE,
        deck_identity=shadowpriest_identity(),
        candidate_archetypes={"primary_archetype": "wild_aggro_shadow_priest"},
        explicit_source_urls=explicit,
        current_date="2026-07-24",
    )

    assert plan["explicit_source_url_count"] == 1
    assert plan["source_urls"][0] == explicit[0]
    assert len(plan["source_urls"]) == len(set(plan["source_urls"]))
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run:

```powershell
python -m pytest tests\test_source_candidate_plan.py -q
```

Expected: FAIL because `hsconfig.source_candidate_plan` does not exist yet.

Do not commit this red state.

---

### Task 2: Implement The Pure Source-Candidate Planner

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_candidate_plan.py`

**Interfaces:**
- Imports existing `source_candidates_for_deck`, `candidate_urls`, `DECK_ALIASES`, and optionally `infer_static_semantics`.
- Exports:
  - `build_source_candidate_plan(...) -> dict[str, Any]`

- [ ] **Step 1: Create `build_source_candidate_plan`**

Implement this signature:

```python
def build_source_candidate_plan(
    *,
    deck_name: str,
    deck_code: str,
    deck_identity: Mapping[str, Any],
    candidate_archetypes: Mapping[str, Any],
    explicit_source_urls: Sequence[str] = (),
    current_date: str | date | None = None,
) -> dict[str, Any]:
```

The returned payload must include:

```python
{
    "schema_version": 1,
    "authority": "diagnostic_source_candidate_plan",
    "apply_blocking": False,
    "runtime_write_performed": False,
    "source_status_apply_blocking": False,
    "deck_name": deck_name,
    "deck_code_hash": deck_identity.get("deck_code_hash", ""),
    "primary_archetype": candidate_archetypes.get("primary_archetype", ""),
    "search_aliases": [...],
    "explicit_source_urls": [...],
    "candidate_urls": [...],
    "source_urls": [...],
    "explicit_source_url_count": ...,
    "candidate_registry_url_count": ...,
    "query_count": ...,
    "queries": [...],
    "card_targets": [...],
    "target_summary": {...},
    "first_missing_source_action": "...",
    "promotion_boundaries": {
        "candidate_plan_can_promote": False,
        "candidate_plan_can_block_apply": False,
        "normal_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
    },
}
```

- [ ] **Step 2: Build candidate URL rows from the existing registry**

For each `SourceCandidate`, emit a compact diagnostic row:

```python
{
    "url": candidate.url,
    "source_family": candidate.source_family,
    "archetype": candidate.archetype,
    "priority": candidate.priority,
    "expected_strength": candidate.expected_strength,
    "strength_ceiling": candidate.strength_ceiling,
    "expected_claim_kinds": list(candidate.expected_claim_kinds),
    "first_missing_source_action": candidate.first_missing_source_action,
    "evergreen_wild_archetype": candidate.evergreen_wild_archetype,
}
```

Do not treat this row as source evidence. It is a seed only.

- [ ] **Step 3: Build card-level evidence targets**

For every deck card, emit:

```python
{
    "card_id": card_id,
    "name": name,
    "required_claim_kinds": [...],
    "supported_static_claim_kinds": [...],
    "requires_explicit_source_claim_kinds": [...],
    "effect_semantics_not_mulligan_keep": bool,
}
```

Rules:

- Always include `card_role` in `required_claim_kinds`.
- Include `mulligan_keep` only as a source-required target, not as static proof.
- Include `targeting_rule`, `mechanic_usage`, `combo_sequence`, or `gameplan_posture` only when the candidate archetype or source candidate expected claim kinds justify those targets.
- For Darkbishop Benedictus / `SW_448`, static semantics may support `hero_power_transform`, but `mulligan_keep` must stay in `requires_explicit_source_claim_kinds`.
- Keep this planner diagnostic-only. It must not write any runtime row.

- [ ] **Step 4: Build query suggestions without adding network search**

Generate deterministic query strings such as:

- `2026 Wild <alias> guide mulligan`
- `2026 Wild <alias> card roles`
- `2026 Wild <primary_archetype> mulligan guide`
- `Wild <alias> <top card names> keep mulligan`

Each query row must include:

```python
{
    "query": "...",
    "priority": 10,
    "target_claim_kinds": ["mulligan_keep", "card_role"],
    "reason": "find_public_guide_or_mulligan_source",
}
```

Do not call the web from this module. Codex/web research can use these queries outside HSConfig and then pass URLs back through `--source-url`.

- [ ] **Step 5: Make `first_missing_source_action` deterministic**

Use:

- `"none"` when the top non-context registry candidate has `first_missing_source_action="none"`.
- First non-`none` candidate action when candidates exist but need a better source.
- `"add_public_guide_url_or_use_static_semantics"` when no candidates and no explicit URLs exist.
- `"fetch_and_validate_explicit_source_urls"` when explicit URLs exist but no registry candidates exist.

- [ ] **Step 6: Run the focused test**

Run:

```powershell
python -m pytest tests\test_source_candidate_plan.py -q
```

Expected: PASS.

---

### Task 3: Wire The Plan Into `source-manifest`

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\source_workflow.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_manifest_cli.py`

**Interfaces:**
- `source-manifest` keeps writing `source_research_manifest.json`.
- It additionally writes `source_candidate_plan.json`.

- [ ] **Step 1: Build the plan in `source_manifest_payload`**

After `manifest = build_source_research_manifest(...)`, call:

```python
source_candidate_plan = build_source_candidate_plan(
    deck_name=args.deck_name,
    deck_code=args.deck_code,
    deck_identity=deck_identity,
    candidate_archetypes=candidate_archetypes,
    explicit_source_urls=[],
    current_date=getattr(args, "current_date", None),
)
```

Write it to:

```python
candidate_plan_path = out / "source_candidate_plan.json"
```

Return both written files:

```python
"written_files": [str(output_path), str(candidate_plan_path)]
```

- [ ] **Step 2: Add optional `--current-date` to `source-manifest` only if needed**

If `source_manifest_payload` needs current-date passthrough for deterministic query years, add:

```python
source_manifest.add_argument("--current-date")
```

Keep it optional.

- [ ] **Step 3: Update `tests\test_source_manifest_cli.py`**

Assert:

- `source_candidate_plan.json` exists.
- payload `written_files` includes both JSON paths.
- plan authority is `diagnostic_source_candidate_plan`.
- plan `apply_blocking` is `False`.
- plan `source_status_apply_blocking` is `False`.
- for `MechPala`, `candidate_registry_url_count >= 1`.
- plan `queries` is not empty.

- [ ] **Step 4: Run focused manifest tests**

Run:

```powershell
python -m pytest tests\test_source_candidate_plan.py tests\test_source_manifest_cli.py -q
```

Expected: PASS.

---

### Task 4: Use The Plan In `configure --online-source`

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\configure.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_configure_online_source.py` or `tests\test_configure_auto_source.py`

**Interfaces:**
- `configure --online-source` continues to call `source_acquire_payload`.
- URL order remains explicit user URLs first, registry candidate URLs second, de-duplicated.
- `configure_summary.json` gains plan path/summary fields.

- [ ] **Step 1: Build the candidate plan once inside `configure_payload`**

Use the same deck identity and candidate archetype data already built by `source_manifest_payload`, or read `01_manifest/source_candidate_plan.json` if Task 3 wrote it before online source acquisition.

Keep the existing `source_candidates_for_deck` and URL de-duplication behavior, but derive it from the plan:

```python
source_candidate_plan = read_json(manifest_dir / "source_candidate_plan.json")
source_candidate_urls = list(source_candidate_plan.get("candidate_urls", []))
source_urls = list(source_candidate_plan.get("source_urls", []))
```

If the plan stores candidate rows instead of raw strings, use the raw `url` fields.

- [ ] **Step 2: Write the plan into the configure summary**

Add these fields to the final `_finish(...)` payload:

```python
"source_candidate_plan_path": str(manifest_dir / "source_candidate_plan.json"),
"source_candidate_plan_summary": {
    "authority": "diagnostic_source_candidate_plan",
    "apply_blocking": False,
    "source_status_apply_blocking": False,
    "candidate_registry_url_count": source_candidate_plan["candidate_registry_url_count"],
    "explicit_source_url_count": source_candidate_plan["explicit_source_url_count"],
    "query_count": source_candidate_plan["query_count"],
    "first_missing_source_action": source_candidate_plan["first_missing_source_action"],
}
```

This summary is diagnostic only and must not influence `runtime_apply_allowed`.

- [ ] **Step 3: Keep source acquisition unchanged**

Continue calling `source_acquire_payload` with:

```python
source_url=source_urls
candidate_registry_url_count=len(source_candidate_urls)
```

Do not pass query strings to network code. They are for operator/Codex research outside the core package builder.

- [ ] **Step 4: Update configure tests**

In the online-source registry test, assert:

- `summary["source_candidate_plan_path"]` points to `01_manifest/source_candidate_plan.json`.
- `summary["source_candidate_plan_summary"]["authority"] == "diagnostic_source_candidate_plan"`.
- `apply_blocking` and `source_status_apply_blocking` are false.
- `query_count >= 1`.
- `source_urls == source_candidate_urls` when no explicit URLs are passed.
- operator summary still has `runtime_apply_contract.apply_authority == "reports/operator_summary.json"`.

Add one explicit URL ordering test if not already covered by unit tests:

- explicit URL first
- registry URL second
- no duplicates

- [ ] **Step 5: Run focused configure tests**

Run:

```powershell
python -m pytest tests\test_source_candidate_plan.py tests\test_source_manifest_cli.py tests\test_configure_online_source.py tests\test_configure_auto_source.py -q
```

Expected: PASS.

---

### Task 5: Keep Documentation And Skill References Current

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\autonomous-source-builder-next.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-builder-workflow.md`
- Modify only if needed: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\guide-research-policy.md`

**Interfaces:**
- Docs explain the new diagnostic plan without changing runtime boundaries.

- [ ] **Step 1: Update `autonomous-source-builder-next.md`**

Add a compact section:

```markdown
## Source Candidate Plan

`source_candidate_plan.json` is the deterministic pre-acquisition plan. It lists registry candidate URLs, explicit URL ordering, public-search query suggestions, card-level claim targets, and the first missing source action. It is diagnostic acquisition guidance only: it cannot promote, block apply, write runtime config, or replace `reports/operator_summary.json`.
```

- [ ] **Step 2: Update `source-builder-workflow.md`**

Document:

- `source-manifest` writes `source_research_manifest.json` and `source_candidate_plan.json`.
- `configure --online-source` uses `source_candidate_plan.json` to order explicit and registry URLs.
- Query strings are for Codex/operator research only; the core CLI does not scrape search result pages.

- [ ] **Step 3: Update active skill reference only if tests require it**

If active-doc tests require a reference, add one sentence to `.agents\skills\hsconfig\references\guide-research-policy.md`:

```markdown
`source_candidate_plan.json` is diagnostic source acquisition guidance only; it cannot promote, block apply, write runtime config, or replace `reports/operator_summary.json`.
```

Do not add this to `.agents\skills\hsconfig\SKILL.md`; keep the entrypoint thin.

- [ ] **Step 4: Run doc/skill tests**

Run:

```powershell
python -m pytest tests\test_skill_files.py tests\test_skill_contract_entrypoint.py tests\test_source_manifest_cli.py -q
```

Expected: PASS.

---

### Task 6: Verify Contract Boundaries And Currentness

**Files:**
- No additional code files unless failures reveal a narrow missing assertion.

**Interfaces:**
- Existing guardrails remain green.

- [ ] **Step 1: Run focused source tests**

Run:

```powershell
python -m pytest tests\test_source_candidate_plan.py tests\test_source_candidate_registry.py tests\test_source_candidate_registry_matrix.py tests\test_source_acquisition.py tests\test_source_acquire_cli.py tests\test_source_autopilot.py tests\test_configure_online_source.py tests\test_configure_auto_source.py -q
```

Expected: PASS.

- [ ] **Step 2: Run contract preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected:

- JSON parses.
- `diagnostic_only=true`.
- installed skill sync is visible.
- `runtime_apply_authority == "reports/operator_summary.json"`.
- `source_status_apply_blocking == false`.
- no source-candidate plan field is apply-blocking.

- [ ] **Step 3: Run contract guardrails**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected: PASS / zero return code.

- [ ] **Step 4: Run full tests**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Verify currentness and clean worktree**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:

- `dirty=false`
- `clean_for_runtime_work=true`
- `behind_origin_main=0`
- only the branch line in `git status` after commit

---

### Task 7: Commit And Push The Plan Implementation

**Files:**
- Stage only intentional source, docs, and tests from Tasks 1-6.

- [ ] **Step 1: Inspect diff**

Run:

```powershell
git diff -- src\hsconfig\source_candidate_plan.py src\hsconfig\commands\source_workflow.py src\hsconfig\commands\configure.py docs\operator\autonomous-source-builder-next.md docs\operator\source-builder-workflow.md .agents\skills\hsconfig\references\guide-research-policy.md tests\test_source_candidate_plan.py tests\test_source_manifest_cli.py tests\test_configure_online_source.py tests\test_configure_auto_source.py
```

Expected: diff contains only diagnostic source-candidate planning, docs, and tests. It must not contain runtime output files, logs, backups, or HSTuner scope.

- [ ] **Step 2: Stage intentional files**

Run:

```powershell
git add src\hsconfig\source_candidate_plan.py src\hsconfig\commands\source_workflow.py src\hsconfig\commands\configure.py docs\operator\autonomous-source-builder-next.md docs\operator\source-builder-workflow.md tests\test_source_candidate_plan.py tests\test_source_manifest_cli.py tests\test_configure_online_source.py tests\test_configure_auto_source.py
```

If `.agents\skills\hsconfig\references\guide-research-policy.md` changed, add it too and run skill sync:

```powershell
git add .agents\skills\hsconfig\references\guide-research-policy.md
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

- [ ] **Step 3: Commit**

Run:

```powershell
git commit -m "feat: add diagnostic source candidate planning"
```

Expected: commit succeeds.

- [ ] **Step 4: Push**

Run:

```powershell
git push
```

Expected: push succeeds and the branch has no uncommitted changes.

---

## Self-Review Checklist

- Source-candidate planning is diagnostic only and non-blocking.
- `operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` remains an evidence-quality result, not an apply prerequisite.
- Query suggestions do not call web search from HSConfig code.
- Explicit URLs remain user-controlled and first in acquisition order.
- Registry candidates remain seeds, not truth.
- Static semantics can support deterministic effect semantics but cannot create guide-only claims.
- Darkbishop Benedictus / `SW_448` remains the effect-not-mulligan canary.
- No normal-path `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- No HSTuner, replay/log parsing, winrate analysis, or post-game tuning.
- Focused tests, contract-preflight, guardrails, full pytest, currentness check, and clean worktree are required before completion.
