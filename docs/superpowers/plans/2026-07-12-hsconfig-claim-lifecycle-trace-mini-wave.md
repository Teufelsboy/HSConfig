# HSConfig Claim Lifecycle Trace Mini-Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig source and contract logic visibly correct without widening the product surface: every relevant source claim should show how it moves from source evidence to policy lane, surface gate, builder/router decision, emitted runtime file or suppressed reason. This is diagnostic visibility only. `operator_summary.json` remains the single normal apply/readiness gate.

**Architecture:** Add an additive `claim_lifecycle_rows` section to `source_contract_audit.json`. Build it from the existing claim model, existing claim-kind policy matrix, existing surface-gate helpers, and the already-generated runtime surface reports in `package_builder.py`. Do not introduce a new pipeline, a new gate, or a new dependency. The trace answers: "What happened to this claim, and which link is missing if it did not reach runtime?"

**Tech Stack:** Python 3, existing HSConfig package modules under `src/hsconfig`, existing `pytest` test suite, existing CLI/package-builder flow.

## Global Constraints

- Do not change the normal runtime apply decision source: `operator_summary.json` is still the only normal operator gate.
- Keep `source_contract_audit.json` diagnostic-only. It must never authorize runtime writes.
- Keep `policy_lane` as static source-policy language. Add lifecycle fields so it cannot be mistaken for runtime emission.
- Do not block deck generation because a claim cannot lower to a runtime surface. Missing links must be visible as diagnostics, not as blockers.
- Do not remove or rewrite existing source-contract logic unless tests prove it is wrong.
- Do not add dependencies.
- Do not commit raw runtime logs, HDT files, HSReplay files, Power.log files, or private evidence.
- Keep the change small: one lifecycle helper, one package-builder wire-up, focused tests, and concise docs.

---

## Phase 0 - Baseline And Scope Lock

- [ ] Confirm repository and branch:

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  git status --short --branch
  ```

- [ ] Confirm these files exist and read their current shape before editing:

  ```powershell
  rg -n "def build_source_contract_audit|source_contract_audit|policy_lane|surface_gate_decision|claim_can_lower_to_runtime" src tests docs .agents
  ```

- [ ] Keep the scope to these likely files:

  - `src/hsconfig/source_contract_audit.py`
  - `src/hsconfig/package_builder.py`
  - `tests/test_source_contract_audit.py`
  - `tests/test_prepare_cli.py`
  - `tests/test_shadowpriest_e2e.py`
  - `tests/test_skill_files.py`
  - `docs/operator/README.md`
  - `docs/operator/guide-research-policy.md`
  - `.agents/skills/hsconfig/SKILL.md`
  - `.agents/skills/hsconfig/references/workflow.md`

- [ ] Do not touch generated runtime config packages unless a test fixture explicitly owns them.

---

## Phase 1 - Contract Tests First

### Task 1.1 - Unit Test The Claim Lifecycle Row Shape

- [ ] Add a test to `tests/test_source_contract_audit.py` named `test_claim_lifecycle_rows_explain_static_policy_and_runtime_outcome`.

- [ ] The test must call `build_source_contract_audit(...)` with a minimal synthetic source claim set and a synthetic runtime emission index, then assert that the audit contains `claim_lifecycle_rows`.

- [ ] Required row fields:

  ```python
  REQUIRED_LIFECYCLE_FIELDS = {
      "claim_id",
      "claim_kind",
      "policy_lane",
      "surface_gate_decision",
      "surface_gate_reason",
      "builder_or_router_decision",
      "runtime_surface",
      "emitted_files",
      "suppressed_reason",
      "first_missing_link",
      "operator_impact",
  }
  ```

- [ ] Assertions:

  - Every lifecycle row has all required fields.
  - `operator_impact` is always `"diagnostic_only"`.
  - A source-backed mulligan claim can produce:

    ```python
    {
        "builder_or_router_decision": "emitted",
        "runtime_surface": "Mulligan.json",
        "emitted_files": ["Mulligan.json"],
        "suppressed_reason": None,
        "first_missing_link": None,
    }
    ```

  - A non-lowerable or evidence-required claim can produce:

    ```python
    {
        "builder_or_router_decision": "suppressed",
        "runtime_surface": None,
        "emitted_files": [],
        "suppressed_reason": "runtime_evidence_required",
        "first_missing_link": "runtime_evidence",
    }
    ```

  - `policy_lane` remains present and unchanged from `source_contract_policy_by_claim_kind()`.

- [ ] Run the focused test and confirm it fails because `claim_lifecycle_rows` does not exist yet:

  ```powershell
  $env:PYTHONPATH='src'; pytest -q tests/test_source_contract_audit.py -k claim_lifecycle
  ```

### Task 1.2 - Integration Test The Generated Audit

- [ ] Extend `tests/test_prepare_cli.py` with an assertion in the existing package-generation path:

  - `source_contract_audit.json` contains non-empty `claim_lifecycle_rows`.
  - At least one row has `builder_or_router_decision` in `{"emitted", "suppressed"}`.
  - All rows have `operator_impact == "diagnostic_only"`.
  - `operator_summary.json` remains present and its status/readiness shape is unchanged.

- [ ] Extend `tests/test_shadowpriest_e2e.py` only for the Darkbishop/Benedictus split that the user cares about:

  - Darkbishop Benedictus must not be forced as a default opening-hand keep solely because its start-of-game effect matters.
  - The effect/hero-power-transform source claim must still be represented in source or card behavior diagnostics.
  - The lifecycle row for that claim must show why it was emitted or suppressed.

- [ ] Run focused tests and confirm expected failures:

  ```powershell
  $env:PYTHONPATH='src'; pytest -q tests/test_source_contract_audit.py tests/test_prepare_cli.py tests/test_shadowpriest_e2e.py -k "claim_lifecycle or source_contract or shadowpriest"
  ```

---

## Phase 2 - Implement The Lifecycle Builder

### Task 2.1 - Add A Small Lifecycle Helper

- [ ] In `src/hsconfig/source_contract_audit.py`, add a private constant:

  ```python
  _DIAGNOSTIC_OPERATOR_IMPACT = "diagnostic_only"
  ```

- [ ] Add a private helper that accepts existing claim rows and an optional emission index:

  ```python
  def _build_claim_lifecycle_rows(
      claim_rows: list[dict[str, object]],
      *,
      runtime_emission_index: dict[str, dict[str, object]] | None = None,
  ) -> list[dict[str, object]]:
      ...
  ```

- [ ] Helper rules:

  - `claim_id` is the stable key from the claim row. If a legacy row has no `claim_id`, derive a deterministic fallback from `claim_kind`, `card_id`, and row index.
  - `claim_kind` comes from the claim row.
  - `policy_lane` comes from the existing source policy matrix, not from runtime output.
  - `surface_gate_decision` and `surface_gate_reason` come from existing source-document gate logic.
  - `builder_or_router_decision` comes from `runtime_emission_index[claim_id]["decision"]` when present.
  - If the index is missing and `surface_gate_decision` is not runtime-lowerable, set:

    ```python
    builder_or_router_decision = "suppressed"
    runtime_surface = None
    emitted_files = []
    suppressed_reason = surface_gate_reason or "surface_gate_rejected"
    first_missing_link = "surface_gate"
    ```

  - If the index is missing and the surface gate allowed runtime lowering, set:

    ```python
    builder_or_router_decision = "not_seen_by_builder"
    runtime_surface = None
    emitted_files = []
    suppressed_reason = "builder_or_router_missing"
    first_missing_link = "builder_or_router"
    ```

  - If the index says emitted, keep its `runtime_surface` and `emitted_files`, with no suppressed reason.
  - If the index says suppressed, keep its `suppressed_reason` and calculate the first missing link from that reason.
  - Always set `operator_impact` to `"diagnostic_only"`.

- [ ] Add a tiny mapping helper in the same file:

  ```python
  def _first_missing_link_for_suppression(reason: str | None) -> str | None:
      ...
  ```

- [ ] Required mapping:

  | suppression reason | first missing link |
  | --- | --- |
  | `None` | `None` |
  | contains `source` | `source_evidence` |
  | contains `runtime_evidence` | `runtime_evidence` |
  | contains `guide` | `source_evidence` |
  | contains `surface_gate` | `surface_gate` |
  | contains `builder` or `router` | `builder_or_router` |
  | anything else | `runtime_surface` |

### Task 2.2 - Add Optional Runtime Emission Index To Audit API

- [ ] Extend `build_source_contract_audit(...)` with an optional keyword-only argument:

  ```python
  runtime_emission_index: dict[str, dict[str, object]] | None = None
  ```

- [ ] Keep all existing positional parameters unchanged.

- [ ] Add `claim_lifecycle_rows` to the returned audit dict:

  ```python
  "claim_lifecycle_rows": _build_claim_lifecycle_rows(
      claim_rows,
      runtime_emission_index=runtime_emission_index,
  )
  ```

- [ ] Do not bump schema version unless an existing schema policy requires it. This is an additive diagnostic field.

- [ ] Update markdown rendering in `render_source_contract_audit_markdown(...)` with a short section:

  ```markdown
  ## Claim Lifecycle Trace

  This section is diagnostic-only. `operator_summary.json` remains the normal apply gate.
  ```

- [ ] The markdown table should show:

  - claim id
  - claim kind
  - policy lane
  - surface gate
  - builder/router decision
  - runtime surface
  - first missing link

---

## Phase 3 - Wire Existing Builders Without Creating A New Pipeline

### Task 3.1 - Build A Runtime Emission Index In `package_builder.py`

- [ ] In `src/hsconfig/package_builder.py`, after the runtime plans/reports have been created and before `build_source_contract_audit(...)` is called, assemble a small local `runtime_emission_index`.

- [ ] Source of truth for emitted/suppressed decisions:

  - `Mulligan.json` generation report for mulligan claims.
  - `GlobalValues.json` authority/report for global value claims.
  - `Combo.json` plan/report for combo claims.
  - `card_behavior_surface_router.route_card_behavior_surfaces(...)` output for CardID behavior claims.

- [ ] If the exact report shapes differ, add only private normalization helpers in `package_builder.py`, for example:

  ```python
  def _index_runtime_emission_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, dict[str, object]]:
      ...
  ```

- [ ] Normalization output per claim id:

  ```python
  {
      "decision": "emitted" | "suppressed",
      "runtime_surface": "Mulligan.json" | "GlobalValues.json" | "Combo.json" | "<CARDID>.json" | None,
      "emitted_files": list[str],
      "suppressed_reason": str | None,
  }
  ```

- [ ] Merge order when multiple surfaces mention the same claim:

  1. Prefer `emitted` over `suppressed`.
  2. If multiple emitted surfaces exist, keep all file names in `emitted_files`.
  3. If only suppressed surfaces exist, keep the most specific reason in this order:
     `runtime_evidence_required`, `source_evidence_required`, `surface_gate_rejected`, `builder_or_router_missing`, then any other reason.

- [ ] Pass the index into `build_source_contract_audit(..., runtime_emission_index=runtime_emission_index)`.

### Task 3.2 - Preserve Runtime And Operator Behavior

- [ ] Confirm no code path reads `claim_lifecycle_rows` to decide whether to write runtime config.

- [ ] Confirm `operator_summary.json` remains unchanged except for any already-existing diagnostic links.

- [ ] Add a test assertion in `tests/test_prepare_cli.py` that `operator_summary.json` does not contain `claim_lifecycle_rows`.

---

## Phase 4 - Docs And Skill Alignment

### Task 4.1 - Active Operator Docs

- [ ] Update `docs/operator/README.md` with one short diagnostic sentence:

  ```markdown
  `source_contract_audit.json` is diagnostic. Its `claim_lifecycle_rows` explain source -> policy -> surface gate -> builder/router -> emitted/suppressed. Runtime readiness still comes from `operator_summary.json`.
  ```

- [ ] Update `docs/operator/guide-research-policy.md` to clarify:

  - `policy_lane` is static policy.
  - `claim_lifecycle_rows` are the concrete trace for what happened in the generated package.
  - A no-block deck can still include suppressed diagnostics when a source claim has no documented runtime surface.

### Task 4.2 - Skill Docs

- [ ] Update `.agents/skills/hsconfig/SKILL.md` with the same invariant:

  ```markdown
  Never treat `policy_lane` alone as runtime emission. Check `source_contract_audit.json.claim_lifecycle_rows` for diagnostic trace, and use `operator_summary.json` for normal readiness.
  ```

- [ ] Update `.agents/skills/hsconfig/references/workflow.md` where reports are described.

- [ ] Extend `tests/test_skill_files.py` or the current docs scan test so active docs contain:

  - `claim_lifecycle_rows`
  - `operator_summary.json`
  - `diagnostic`

- [ ] Ensure docs do not claim the audit is an apply gate.

---

## Phase 5 - Verification

### Task 5.1 - Focused Tests

- [ ] Run:

  ```powershell
  cd C:\Users\darbo\Documents\HSConfig
  $env:PYTHONPATH='src'; pytest -q tests/test_source_contract_audit.py tests/test_prepare_cli.py tests/test_shadowpriest_e2e.py tests/test_skill_files.py
  ```

### Task 5.2 - Broader Safety Tests

- [ ] Run the source/contract and no-block related tests:

  ```powershell
  $env:PYTHONPATH='src'; pytest -q tests/test_claim_kind_runtime_contract.py tests/test_surface_authority_split.py tests/test_card_behavior_router.py tests/test_universal_wild_no_block_matrix.py
  ```

- [ ] If these test files do not exist in the current repo state, replace only the missing file names with the closest current test files found by:

  ```powershell
  rg --files tests | rg "claim|surface|card_behavior|wild|source_contract|skill|shadowpriest"
  ```

### Task 5.3 - Full Suite

- [ ] Run:

  ```powershell
  $env:PYTHONPATH='src'; pytest -q
  ```

- [ ] Review diff:

  ```powershell
  git diff -- src/hsconfig/source_contract_audit.py src/hsconfig/package_builder.py tests docs .agents
  git status --short --branch
  ```

---

## Acceptance Criteria

- [ ] `source_contract_audit.json` includes `claim_lifecycle_rows`.
- [ ] Each lifecycle row has:

  - source identity: `claim_id`, `claim_kind`
  - static policy: `policy_lane`
  - gate: `surface_gate_decision`, `surface_gate_reason`
  - actual generation outcome: `builder_or_router_decision`, `runtime_surface`, `emitted_files`, `suppressed_reason`
  - diagnosis: `first_missing_link`
  - non-gate marker: `operator_impact == "diagnostic_only"`

- [ ] A claim can be visibly source-backed while still suppressed for runtime, with a concrete missing link.
- [ ] A claim can be visibly emitted to `Mulligan.json`, `GlobalValues.json`, `Combo.json`, or `<CARDID>.json`.
- [ ] `operator_summary.json` remains the normal readiness/apply gate.
- [ ] No runtime config generation is blocked by diagnostics alone.
- [ ] Darkbishop Benedictus logic remains correct for ShadowPriest:

  - no mistaken forced opening-hand keep purely because the start-of-game effect matters
  - the hero-power-transform/effect semantics remain represented in source/runtime diagnostics

- [ ] Focused and full tests pass.

---

## Suggested Subagent Split

- [ ] **Explorer Subagent:** Read-only map of current report shapes in `package_builder.py`, `source_contract_audit.py`, mulligan/global/combo/card behavior reports. Output only the field names needed for `runtime_emission_index`.
- [ ] **TDD Subagent:** Write failing tests in `tests/test_source_contract_audit.py`, `tests/test_prepare_cli.py`, and `tests/test_shadowpriest_e2e.py`.
- [ ] **Worker Subagent:** Implement `claim_lifecycle_rows` helper and package-builder wire-up after tests exist.
- [ ] **Docs Subagent:** Update operator docs and skill docs only.
- [ ] **Reviewer Subagent:** Read-only final diff review focused on accidental gate changes, runtime write behavior, and no-block deck generation.

The main agent owns final integration and test execution.

