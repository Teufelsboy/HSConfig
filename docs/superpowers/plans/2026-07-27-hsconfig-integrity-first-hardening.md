# HSConfig Integrity-First Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every behavioral change, `superpowers:systematic-debugging` for unexpected failures, `superpowers:requesting-code-review` after each task, and `superpowers:verification-before-completion` before the final claim. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig reproducibly green, semantically exact, failure-auditable, and materially leaner without weakening its universal no-block operator contract or claiming unproven gameplay optimality.

**Architecture:** Harden the system in dependency order. First make a clean checkout reproduce CI. Then repair authority, source-to-runtime, mulligan, combo, runtime-match, rollback, and diagnostic boundaries. Only after those contracts are green, extract small immutable orchestration stages and consolidate duplicated audited-deck identity data. Finish with a fresh read-only 12-deck generation matrix and repository-level verification. `reports/operator_summary.json` remains the sole human-facing apply authority; all other reports remain supporting evidence or diagnostics.

**Tech Stack:** Python 3.11 and 3.12, pytest, Ruff, PyYAML, pip-audit, deterministic JSON/SHA-256 receipts, GitHub Actions, Hearthstone deck strings, HearthRanger VisionAI `CustomConfig`.

## Baseline and non-negotiable constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Work directly on the sole `main` branch. Do not create a branch, worktree, pull request, shadow checkout, or second implementation version.
- Before every task: `git fetch --all --prune --tags`, prove `HEAD == origin/main`, and require an empty `git status --short`.
- After every task: inspect the diff, run the stated tests, commit only that task, push `main`, prove `HEAD == origin/main`, and require an empty worktree.
- Use one writing agent per task. Give every task two independent read-only reviews: specification/contract review first, code-quality/regression review second. The writing agent must address both before commit.
- Use test-first red/green/refactor. A test that starts green does not prove the intended defect; correct the test before changing production code.
- Set `$env:PYTHONDONTWRITEBYTECODE='1'` and use `-p no:cacheprovider` for pytest. Do not commit caches or generated test output.
- Do not access or write `C:\Users\darbo\Desktop\HS` while executing this plan. Do not run `hsconfig apply`, HSTuner, replay analysis, live-game automation, or any runtime writer.
- Do not commit `outputs/`, source captures, runtime snapshots, apply receipts, HearthRanger/Hearthstone logs, HDT exports, replays, or private evidence.
- Do not introduce new VisionAI keys, speculative thresholds, numeric tuning, card behavior, mulligan keeps, or combo order from card text, archetype convention, or inference alone.
- `VALID_PACKAGE` is a technical/load-safe statement. `SOURCE_BACKED_STRONG`, `RUNTIME_SAMPLED`, gameplay improvement, and gameplay optimality remain distinct and must never be inferred from fixtures, validators, or a successful runtime match.
- Missing exact source evidence must remain visible and non-blocking for package generation. It may withhold a semantic promotion, but must not create a second human apply gate.
- Preserve the representative matrix boundary: eleven representative decks plus supplemental CuteWarrior. Do not silently promote CuteWarrior into the representative source-depth matrix.
- Do not mass-delete historical documentation or ignored outputs in this plan. Introduce policy, indexing, and bounded cleanup tooling only. Any destructive cleanup needs a later explicitly scoped operator action.
- Do not invent a license or publish repository metadata that requires an owner decision.

## Confirmed starting point

- Baseline commit: `bc953bb1f4119f4b7f9b926fe5eb6314d6f95cd5`.
- Local full suite: `2763 passed, 11 skipped`.
- Audited-deck acceptance: `31 passed`.
- GitHub `contract-spine`: green at the audited commit.
- GitHub `contract-guardrails`: red because `scripts/research_result_contract_sentinel.py` imports `yaml` while `PyYAML` is not declared in `pyproject.toml`.
- Ruff currently reports four findings: one intentional import-order exception and three unused imports.
- All twelve supplied deck codes decode to 30-card, zero-sideboard decks, and their supplied name/HS ID/HDT ID mappings match the tracked manifests.

## Required audited deck identities

The following identities are immutable inputs to the final matrix. Preserve deck-name spelling exactly.

| Deck | HS ID | HDT deck ID | Matrix role |
|---|---:|---|---|
| ShadowPriest | `2737726722` | `c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602` | representative |
| CtAPaladin | `2737744316` | `f9b54950-ca24-48cf-805e-bf620eab47a0` | representative |
| PirateRogue | `2740734095` | `c1e87d43-5802-460b-b955-31ae458eb41a` | representative |
| BigShaman | `2737735409` | `6b26f907-6f1e-44c8-a4e4-d14e9d51f819` | representative |
| Discolock | `2740357533` | `55241397-ac74-4d46-a662-089e5858839c` | representative |
| TreantDruid | `2740360895` | `a120a28b-1840-4032-a3c9-2da4c51338ed` | representative |
| ImbueMage | `2740361888` | `49c05560-8b30-4d06-b3a2-a8b0ff36d005` | representative |
| MechPala | `2740734214` | `8f011f55-8ae2-436c-b53a-315f280e8833` | representative |
| Kingslayer | `2740733989` | `1292ff02-8ebe-47a5-90b1-9a1899acd6aa` | representative |
| Boarlock | `2740361505` | `7727c718-c93c-47ca-a766-5612c3806f0f` | representative |
| PirateDH | `2737737281` | `2bc184ed-b59a-4420-900d-b0ed3d153979` | representative |
| CuteWarrior | `2750150375` | `a753f091-b770-4a06-8da8-59f1d5269f6b` | supplemental |

---

## Phase A — Reproducible baseline and authority correctness

### Task 1: Make CI reproducible from declared dependencies

**Files:**

- Modify: `pyproject.toml`
- Modify: `.github/workflows/contract-guardrails.yml`
- Modify: `.github/workflows/contract-spine.yml`
- Create: `.github/workflows/full-test-suite.yml`
- Modify: `scripts/sync_installed_skill.py`
- Modify: `src/hsconfig/source_claim_context.py`
- Modify: `tests/test_source_builder_matrix_closure.py`
- Modify: `tests/test_visionai_registry.py`
- Create: `tests/test_ci_contract.py`

- [ ] **Step 1: Write the failing dependency/workflow contract**

Add tests that parse `pyproject.toml` with `tomllib` and the workflow YAML as text. Assert:

```python
def test_runtime_dependencies_declare_yaml_parser():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert any(
        dependency.lower().startswith("pyyaml")
        for dependency in project["project"]["dependencies"]
    )


def test_ci_runs_lint_full_suite_and_contract_sentinels():
    workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path(".github/workflows").glob("*.yml")
    ).lower()
    assert "ruff check --no-cache src tests scripts" in workflows
    assert "python -m pytest -p no:cacheprovider" in workflows
    assert "check_contract_guardrails.py" in workflows
    assert "contract-spine-sentinel --json" in workflows
```

- [ ] **Step 2: Prove RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_ci_contract.py -q -p no:cacheprovider
python -m ruff check --no-cache src tests scripts
```

Expected: missing `PyYAML`, missing full-suite/Ruff workflow coverage, and the four already-audited Ruff findings.

- [ ] **Step 3: Declare the actual dependency and development tools**

Use:

```toml
[project]
dependencies = [
  "hearthstone>=9.0.0",
  "PyYAML>=6.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "ruff>=0.12",
  "pip-audit>=2.9",
]
```

Remove the three genuinely unused imports. For the intentional path bootstrap in `scripts/sync_installed_skill.py`, use a narrow per-line `# noqa: E402` with a short adjacent explanation; do not disable E402 globally.

- [ ] **Step 4: Add one full-suite workflow without duplicating semantic authority**

`full-test-suite.yml` must install `.[dev]`, run Ruff, run the full pytest suite on Windows/Python 3.11, and run `pip-audit`. Keep the focused contract workflows because they give fast boundary failures. Avoid three separate copies of dependency installation logic beyond the commands each workflow needs.

Use pinned major action versions already established in the repo for this task; immutable SHA pinning belongs to Task 13 after the functional baseline is green.

- [ ] **Step 5: Prove a clean environment can import every required module**

Create a temporary virtual environment outside the repository, install `-e ".[dev]"`, then run:

```powershell
python -c "import yaml, hsconfig; print(yaml.__version__)"
python scripts\research_result_contract_sentinel.py --help
python -m ruff check --no-cache src tests scripts
python -m pytest tests/test_ci_contract.py -q -p no:cacheprovider
```

Delete the temporary environment after verification.

- [ ] **Step 6: Run the full local CI equivalent**

```powershell
python scripts\sync_installed_skill.py --install-root .guardrail-skills
python scripts\check_contract_guardrails.py --skill-install-root .guardrail-skills
python -m hsconfig.cli contract-spine-sentinel --json
python -m pytest -q -p no:cacheprovider
python -m pip_audit
```

Remove `.guardrail-skills` after the run if it is not ignored.

- [ ] **Step 7: Review, commit, push**

Inspect `git diff --check` and the complete diff. Commit:

```text
ci: make contract verification reproducible
```

Push `main` and verify the three GitHub workflows are green before starting Task 2.

### Task 2: Remove the stale ShadowPriest second apply gate from the active plan

**Files:**

- Modify: `docs/superpowers/plans/2026-07-27-shadowpriest-live-config-apply.md`
- Modify: `docs/superpowers/specs/2026-07-27-shadowpriest-live-config-apply-design.md` if it repeats the gate
- Modify: `tests/test_no_second_gate_contract.py`
- Modify: `tests/test_operator_docs_contract_policy.py`

- [ ] **Step 1: Add a failing active-document policy test**

Assert that the active ShadowPriest plan:

```python
assert "operator_summary.json` is the sole normal apply authority" in text
assert "canonical_source_receipts must be nonempty" not in text.lower()
assert "stop before apply" not in canonical_receipt_diagnostic_section.lower()
```

The test must scope itself to active operator/spec/plan documents. Do not rewrite immutable historical evidence merely to make a text search pass.

- [ ] **Step 2: Prove RED against the current plan**

Run:

```powershell
python -m pytest tests/test_no_second_gate_contract.py tests/test_operator_docs_contract_policy.py -q -p no:cacheprovider
```

- [ ] **Step 3: Correct the plan and specification**

Replace the nonempty canonical-receipt stop with:

```text
Canonical receipt count and exact-source closure are diagnostics. Empty exact
source evidence must remain visible, but it does not create a second apply
authority. The operator decision is read only from reports/operator_summary.json;
the apply command independently recomputes package integrity and parity.
```

Add a dated correction note to the old plan rather than disguising the change as its original state.

- [ ] **Step 4: Verify policy consistency**

Run the two focused tests, `tests/test_skill_files.py`, `tests/test_docs_active_path.py`, and `scripts/check_contract_guardrails.py`.

- [ ] **Step 5: Review, commit, push**

Commit:

```text
docs: remove shadowpriest second apply gate
```

### Task 3: Bind canonical source receipts to exact claims and deck identity

**Files:**

- Modify: `src/hsconfig/package_derivation_receipt.py`
- Modify: `src/hsconfig/source_exact_evidence.py` only if the canonical signature helper already belongs there
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `tests/test_apply_authority_boundary.py`
- Create: `tests/test_package_derivation_receipt.py`
- Create: `tests/test_source_authority_receipts.py`

- [ ] **Step 1: Write semantic-tampering tests**

Starting from a fully valid fixture, mutate one field at a time and rebuild only outer package hashes where necessary:

Use one parameterized test with the exact mutation/reason pairs below. For each
row, build the current valid apply-eligible package with
`tests/helpers/current_apply_eligible_package.py`, mutate the bundle, rebuild
the package derivation receipt, call `evaluate_apply_gate(package)`, and assert
`allowed is False` plus the listed reason code.

```python
RECEIPT_TAMPERING_CASES = [
    ("unknown_claim_id", "source_receipt_claim_missing"),
    ("claim_signature_mismatch", "source_receipt_signature_mismatch"),
    ("deck_fingerprint_mismatch", "source_receipt_deck_mismatch"),
    ("duplicate_claim_receipt", "source_receipt_duplicate"),
    ("claim_receipt_parity_mismatch", "source_receipt_claim_parity_mismatch"),
]
```

Also add a zero-receipt test proving:

```python
assert context["canonical_receipt_count"] == 0
assert context["exact_source_closed"] is False
assert context["source_authority_verified"] is True
```

The empty case remains diagnostic and non-blocking; a malformed or falsely bound receipt blocks.

- [ ] **Step 2: Prove RED**

Run the three focused modules and confirm each mutation is currently accepted or underreported.

- [ ] **Step 3: Implement one exact validator**

Introduce one pure function with this shape:

Implement this exact public contract:

```python
def canonical_source_receipt_reasons(
    *,
    bundle: Mapping[str, Any],
    deck_identity: Mapping[str, Any],
) -> list[dict[str, str]]:
```

For every receipt:

1. Require `receipt_kind == "canonical_exact_deck_source_document"`.
2. Require live-verified acquisition provenance.
3. Require a nonempty, unique `claim_id`.
4. Resolve that ID to exactly one claim in the same bundle.
5. Recompute the canonical claim signature with the same helper used when emitting the receipt.
6. Require receipt and claim deck fingerprints to equal `deck_identity.deck_fingerprint`.
7. Require receipt/claim source URL, source document identity, and claim kind parity for fields already present in the schema.

Return stable reason codes, not prose-only failures. Keep `source_authority_reasons(package_root)` as the file-loading adapter.

- [ ] **Step 4: Project diagnostic visibility without creating a gate**

Add to the package authority context and operator summary:

```json
{
  "canonical_receipt_count": 0,
  "exact_source_closed": false
}
```

`exact_source_closed` means at least one canonical receipt exists and all canonical receipts validate. It is not an apply boolean.

- [ ] **Step 5: Verify**

Run the focused modules, `tests/test_no_second_gate_contract.py`, `tests/test_operator_summary.py`, `tests/test_strict_package_validation.py`, and the contract spine.

- [ ] **Step 6: Review, commit, push**

Commit:

```text
fix: bind source receipts to claims and deck identity
```

### Task 4: Make apply authority a single canonical decision projection

**Files:**

- Create: `src/hsconfig/apply_decision.py`
- Modify: `src/hsconfig/apply_gate.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `tests/test_apply_authority_boundary.py`
- Modify: `tests/test_no_second_gate_contract.py`
- Create: `tests/test_apply_decision.py`

- [ ] **Step 1: Write parity and forgery tests**

Cover:

- a valid package produces the same `allowed`, `mode`, and primary reason in configure output, operator summary, and apply evaluation;
- changing only serialized `allowed`, `mode`, `technical_status`, or `apply_policy` cannot authorize apply;
- missing exact source remains visible but does not become a second gate;
- malformed source receipts, invalid deck input, strict validation failure, forbidden surfaces, or derivation mismatch block;
- the deprecated `allow_source_informed` parameter cannot create a second path.

- [ ] **Step 2: Prove RED**

Run `tests/test_apply_decision.py`, `tests/test_apply_authority_boundary.py`, and `tests/test_no_second_gate_contract.py`.

- [ ] **Step 3: Implement the pure decision builder**

Use an immutable result:

```python
@dataclass(frozen=True)
class ApplyDecision:
    allowed: bool
    mode: str
    policy: str
    reasons: Sequence[Mapping[str, Any]]
```

Add `build_apply_decision(facts: ApplyFacts) -> ApplyDecision` as the sole pure
decision function.

`ApplyFacts` contains recomputed facts only: strict package validation, actual runtime-surface inventory, deck-input verification, source-receipt validity, source acquisition eligibility, derivation receipt validity, and package/summary parity. It must not trust a serialized `allowed` boolean.

- [ ] **Step 4: Serialize once, recompute at the write boundary**

Configure serializes the canonical decision into `operator_summary.json`. `evaluate_apply_gate()` reconstructs facts from the package, rebuilds the decision, and checks parity with the serialized core fields. `runtime_apply` consumes only the recomputed allowed decision.

Do not require semantic strongness. The load-safe mode remains allowed when all technical/integrity facts pass.

- [ ] **Step 5: Verify**

Run all apply, configure, operator-summary, derivation, fake-receipt, and strict-validation modules, then the contract spine.

- [ ] **Step 6: Review, commit, push**

Commit:

```text
refactor: unify apply decision projection
```

---

## Phase B — Hearthstone semantic boundaries

### Task 5: Require explicit opening-hand intent at the final Mulligan gate

**Files:**

- Modify: `src/hsconfig/source_claim_context.py`
- Modify: `src/hsconfig/source_document_model.py`
- Create: `tests/test_source_claim_context.py`
- Modify: `tests/test_claim_kind_runtime_contract.py`
- Modify: `tests/test_semantic_runtime_negative_boundaries.py`
- Modify: `tests/test_shadowpriest_visionai_semantic_surface_contract.py`

- [ ] **Step 1: Add negative and positive gate tests**

Required negatives:

- exact live public guide, exact deck fingerprint, and a card mention, but ordinary strategy prose only;
- `start of game`, `at the start`, or hero-power setup language without opening-hand intent;
- the word `keep` used outside a mulligan/opening-hand instruction.

Required positives:

- explicit prose such as `Mulligan: keep CARD`;
- structured timing/qualifier equal to `mulligan` or `opening_hand`, with all existing exact-source checks passing.

The expected negative reason is:

```text
mulligan_requires_explicit_opening_hand_context
```

- [ ] **Step 2: Prove RED**

Run the focused tests and demonstrate that a fully exact but ordinary card-role claim currently reaches Mulligan lowering.

- [ ] **Step 3: Add the final semantic predicate**

Define:

```python
def claim_has_explicit_mulligan_context(claim: Mapping[str, Any]) -> bool:
    structured = {
        normalized(claim.get("timing")),
        normalized(claim.get("qualifier")),
        normalized(claim.get("context")),
    }
    return bool(
        structured & {"mulligan", "opening_hand", "opening hand"}
        or has_explicit_mulligan_context(claim_text(claim))
    )
```

Call it in `can_lower_to_mulligan()` after source/deck verification and before the final `allowed` result. Preserve the more specific Darkbishop start-of-game reason when applicable.

- [ ] **Step 4: Verify**

Run Mulligan, source-document, semantic negative-boundary, ShadowPriest, and audited-deck acceptance tests.

- [ ] **Step 5: Review, commit, push**

Commit:

```text
fix: require explicit mulligan intent at final gate
```

### Task 6: Require directed evidence for ordered Combo lowering

**Files:**

- Modify: `src/hsconfig/source_claim_context.py`
- Modify: the current combo claim compiler/lowering module identified by `rg -n "has_explicit_combo|ORDERED_CONNECTORS|combo sequence" src`
- Modify: `tests/test_source_claim_context.py`
- Modify: `tests/test_compile_combo.py`
- Modify: `tests/test_semantic_runtime_negative_boundaries.py`
- Modify: `tests/test_boarlock_closure_wave.py`

- [ ] **Step 1: Add false-positive tests**

Reject:

- `Card A + Card B` as mere coexistence;
- a section label `Combo:` followed by an unordered list;
- two cards in one sentence without a directional connector;
- an exact deck list that contains both cards but no sequence instruction.

Accept only explicit order, such as `Card A then Card B`, `Card A into Card B`, `Card A followed by Card B`, or `Card A -> Card B`, with the existing exact-source and completeness gates.

- [ ] **Step 2: Prove RED**

Show that `" + "` or a marker alone currently returns true.

- [ ] **Step 3: Implement directed parsing**

Change:

```python
EXPLICIT_COMBO_MARKERS = ("combo sequence", "combo:", "sequence:")
ORDERED_CONNECTORS = (" then ", " into ", " followed by ", " -> ")
```

A marker may establish section context but never order by itself. Require a supported connector between resolved card mentions and preserve the textual left-to-right order in the emitted sequence. Do not infer timing or target semantics beyond the source.

- [ ] **Step 4: Verify**

Run combo, claim-context, semantic-boundary, Boarlock, no-default-only, and audited-deck tests.

- [ ] **Step 5: Review, commit, push**

Commit:

```text
fix: require directed source evidence for combos
```

### Task 7: Match `deck_config.ini` by exact deck identity and config directory

**Files:**

- Modify: `src/hsconfig/runtime_package_match.py`
- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `tests/test_runtime_package_match.py`
- Modify: `tests/test_runtime_apply.py`

- [ ] **Step 1: Add mapping-identity tests**

Cover:

```text
ShadowPriest=shadowpriest        -> exact match
WrongDeck=shadowpriest           -> mismatch
ShadowPriest=wrong-directory     -> mismatch
ShadowPriest=shadowpriest twice  -> ambiguous mismatch
ShadowPriest=shadowpriest plus a conflicting duplicate -> ambiguous mismatch
```

Also preserve UTF-8 BOM, comments, whitespace normalization, and unrelated mappings.

- [ ] **Step 2: Prove RED**

The `WrongDeck=shadowpriest` case must currently be accepted because only the right-hand value is checked.

- [ ] **Step 3: Parse and compare both sides**

Change the helper contract to:

Change the helper contract to
`_matching_mapping_lines(path: Path, *, expected_deck_name: str,
config_dir: str) -> list[str]`.

Read `expected_deck_name` from the verified package input manifest through the existing `_deck_name_from_manifest` contract. Report:

```json
{
  "expected_deck_name": "ShadowPriest",
  "matching_mapping_count": 1,
  "mapping_ambiguous": false
}
```

Exactly one matching logical mapping is required.

- [ ] **Step 4: Verify**

Run runtime-match, runtime-apply, fake-receipt, apply-authority, and full audited-deck acceptance tests.

- [ ] **Step 5: Review, commit, push**

Commit:

```text
fix: require exact runtime deck mapping identity
```

### Task 8: Record every post-mutation apply failure and rollback result

**Files:**

- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `src/hsconfig/runtime_apply_receipts.py`
- Modify: `tests/test_runtime_apply.py`
- Modify: `tests/test_runtime_apply_receipts.py`

- [ ] **Step 1: Add injected-failure tests**

Monkeypatch failures after:

1. target removal;
2. package copy;
3. `deck_config.ini` update;
4. runtime package-match verification;
5. success-history write.

For every failure after the first mutation, assert:

- the original exception type/message is re-raised;
- the previous runtime target and INI mapping are restored when possible;
- a package-local failure receipt is attempted;
- runtime history is attempted with `status: rolled_back` or `status: rollback_failed`;
- receipt/history failure is attached as an exception note and does not replace the original cause.

For a pre-mutation failure, assert no false `runtime_write_performed: true`.

- [ ] **Step 2: Prove RED**

Demonstrate that current history is written only if `success_history_written` became true.

- [ ] **Step 3: Track the mutation boundary explicitly**

Use:

```python
mutation_started = False
```

Set it immediately before the first destructive or write operation. In the exception path, build a stable failure payload:

```json
{
  "status": "rolled_back",
  "runtime_write_performed": true,
  "rollback_restored": true,
  "failure_type": "RuntimePackageMismatchError",
  "failure_message": "injected runtime package match failure",
  "runtime_snapshot_before": {},
  "runtime_snapshot_after_rollback": {}
}
```

Use `status: rollback_failed` when restore fails. Never report `applied` on a failed call.

- [ ] **Step 4: Make receipt/history writes best-effort and independent**

Attempt package receipt and runtime history separately. Record failures as notes. Preserve the original exception traceback.

- [ ] **Step 5: Verify**

Run runtime apply/receipt/match tests, apply-authority tests, and the full suite. No real runtime path may be used.

- [ ] **Step 6: Review, commit, push**

Commit:

```text
fix: audit failed runtime applies from first mutation
```

### Task 9: Make the Darkbishop diagnostic linked-owner aware

**Files:**

- Modify: `src/hsconfig/config_quality_contract.py`
- Modify: the existing linked-runtime-owner lookup module if a reusable resolver is needed
- Modify: `tests/test_config_quality_contract.py`
- Modify: `tests/test_shadowpriest_visionai_semantic_surface_contract.py`

- [ ] **Step 1: Add the correct-owner test**

Construct a ShadowPriest package where:

- `SW_448` is absent from `Mulligan.json`;
- its runtime effect is correctly emitted under linked owner `EX1_625t.json`;
- the linked-runtime-owner ledger/receipt proves the relationship.

Assert:

```python
assert check["seen"] is True
assert check["mulligan_keep_present"] is False
assert check["effect_runtime_present"] is True
assert check["runtime_owner_card_id"] == "EX1_625t"
```

Add negatives for a missing owner receipt and for behavior placed under an unrelated card ID.

- [ ] **Step 2: Prove RED**

The current diagnostic reads `SW_448.json` and must report `effect_runtime_present == False` for the correct package.

- [ ] **Step 3: Resolve the owner from package evidence**

Do not merely hardcode the filename inside the diagnostic. Resolve `SW_448 -> EX1_625t` through the existing linked-runtime-owner evidence/ledger, validate that evidence, and inspect the resolved owner payload. A hardcoded constant is acceptable only as a test oracle.

- [ ] **Step 4: Verify**

Run config-quality, linked-owner, strict-validation, ShadowPriest, and audited-deck acceptance tests.

- [ ] **Step 5: Review, commit, push**

Commit:

```text
fix: inspect darkbishop through linked runtime owner
```

### Task 10: Complete narrow semantic assertions for all twelve audited decks

**Files:**

- Modify: `tests/test_audited_deck_set_acceptance.py`
- Modify: `tests/fixtures/audited_deck_card_db.json` only if a verified card fixture is actually missing
- Modify: `docs/operator/universal-wild-no-block-contract.md`

- [ ] **Step 1: Add deck-specific boundary assertions without pinning volatile counts**

Add one named assertion function for each currently under-specified deck:

- `CtAPaladin`: unsupported secret timing remains warning-only/absent; no invented target/timing rule.
- `PirateRogue`: no inferred Combo sequence; unsupported Dredge/placement semantics remain visible and absent from runtime JSON.
- `BigShaman`: no inferred ordered Combo; location/board-position behavior remains warning-only unless the source contract explicitly supports it.
- `TreantDruid`: no unconditional variable-cost or board-count threshold invented from card/archetype text.
- `PirateDH`: Outcast/position and unsupported location activation semantics remain visible and absent; no legacy surface.
- `CuteWarrior`: stays supplemental, load-safe, and non-authoritative; unresolved choose-one/placement behavior is not emitted.

Reuse existing positive assertions for ShadowPriest, Discolock, ImbueMage, MechPala, Kingslayer, and Boarlock. Pin semantic boundaries, not warning totals or implementation-specific file ordering.

- [ ] **Step 2: Prove RED where coverage is missing**

Use mutation helpers to insert one forbidden semantic row per new assertion and show each assertion fails. Do not weaken the production builder merely to manufacture RED.

- [ ] **Step 3: Add production fixes only if a mutation reveals an actual live defect**

If current unmodified packages already satisfy every new invariant, this task is a test/documentation commit only. If a real defect appears, stop and add a focused TDD subtask before proceeding.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests/test_audited_deck_set_acceptance.py -q -p no:cacheprovider
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_no_default_only_semantic_archetype_matrix.py -q -p no:cacheprovider
```

- [ ] **Step 5: Review, commit, push**

Commit:

```text
test: complete twelve deck semantic boundaries
```

---

## Phase C — Slimness, consistency, and repository longevity

### Task 11: Consolidate audited-deck identity without changing matrix roles

**Files:**

- Create: `docs/operator/audited-deck-catalog.json`
- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/supplemental-proof-decks.json`
- Modify: `docs/operator/source-candidate-proof-decks.json`
- Modify: `src/hsconfig/source_candidate_registry.py`
- Modify: `tests/test_audited_deck_set_acceptance.py`
- Modify: `tests/test_source_candidate_registry_matrix.py`
- Modify: `tests/test_matrix_governance.py`
- Modify: `docs/operator/README.md`

- [ ] **Step 1: Add a failing single-source-of-identity test**

The catalog contains exactly twelve unique rows with:

```json
{
  "deck_name": "ShadowPriest",
  "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
  "hs_id": "2737726722",
  "hdt_deck_id": "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602",
  "matrix_role": "representative"
}
```

The other eleven rows must use the exact audited identities listed above, with CuteWarrior as `supplemental`. Assert uniqueness of deck name, deck code, HS ID, and HDT deck ID, and decode every deck code to 30 cards/zero sideboard.

- [ ] **Step 2: Prove RED**

The catalog does not yet exist and identity values are duplicated in several tests/manifests.

- [ ] **Step 3: Make role manifests reference names, not repeat identity**

Keep role-specific evidence, URLs, closure state, and policies in their existing manifests. Replace duplicated identity fields with a stable `deck_name` reference where loaders can resolve them from the catalog. Do not merge representative, supplemental, and candidate-proof semantics.

- [ ] **Step 4: Make the candidate API honest**

If `source_candidates_for_deck()` accepts a deck code but does not use it, choose one contract and test it:

- preferred: accept `deck_name` only and update callers; or
- if deck code remains: decode it and require its fingerprint to match the catalog row.

Do not retain a security-looking argument that is silently discarded.

- [ ] **Step 5: Verify**

Run catalog, matrix-governance, source-candidate, audited-deck, and full-suite tests.

- [ ] **Step 6: Review, commit, push**

Commit:

```text
refactor: centralize audited deck identity
```

### Task 12: Extract immutable configure/package stages without a rewrite

**Files:**

- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/commands/configure.py`
- Create: `src/hsconfig/configure_stages.py`
- Create: `tests/test_configure_stages.py`
- Modify: `tests/test_package_builder.py`
- Modify: `tests/test_configure_cli.py`

- [ ] **Step 1: Freeze current behavior with characterization tests**

For a deterministic fixture, record the in-memory values passed between:

1. deck identity and card lookup;
2. source acquisition/normalization;
3. claim compilation and surface gates;
4. runtime payload assembly;
5. strict validation/authority projection;
6. artifact writing.

Assert stable digests and public output parity, not private local-variable names.

- [ ] **Step 2: Prove characterization coverage**

Temporarily perturb one stage result in the test double and confirm the digest/parity assertion fails.

- [ ] **Step 3: Introduce immutable stage results**

Use small dataclasses:

```python
@dataclass(frozen=True)
class VerifiedDeckStage:
    identity: Mapping[str, Any]
    cards: Sequence[Mapping[str, Any]]
    input_verification: Mapping[str, Any]


@dataclass(frozen=True)
class LoweredRuntimeStage:
    runtime_files: Mapping[str, Mapping[str, Any]]
    warnings: Sequence[Mapping[str, Any]]
    source_contract: Mapping[str, Any]
```

Each stage is pure where practical and returns data; one final writer owns filesystem output. Do not create a framework or new dependency.

- [ ] **Step 4: Remove repeated validations only when digest-bound**

Within one configure run, a stage may reuse a prior validation result only if its inputs are immutable and identified by the same digest. Keep full strict validation and apply-decision recomputation at the runtime write boundary.

- [ ] **Step 5: Keep compatibility**

Preserve CLI flags, report schemas, file names, operator-summary semantics, reason codes, deterministic output, and the twelve-deck matrix.

- [ ] **Step 6: Verify**

Run configure/package-builder characterization tests, contract spine, audited-deck acceptance, then full suite. Compare a before/after generated fixture tree semantically and require no unexplained diff.

- [ ] **Step 7: Review, commit, push**

Commit:

```text
refactor: extract immutable configure stages
```

### Task 13: Establish bounded repository and output hygiene

**Files:**

- Create: `docs/history/README.md`
- Modify: `docs/operator/README.md`
- Create: `docs/operator/output-retention-policy.md`
- Create: `scripts/report_output_inventory.py`
- Create: `tests/test_output_inventory.py`
- Create: `SECURITY.md`
- Create: `CONTRIBUTING.md`
- Modify: `tests/test_ci_contract.py`
- Modify: `.github/workflows/contract-guardrails.yml`
- Modify: `.github/workflows/contract-spine.yml`
- Modify: `.github/workflows/full-test-suite.yml`

- [ ] **Step 1: Add tests for non-destructive inventory behavior**

Given a temporary output tree, assert the script reports deck, path, modified time, package status, and likely duplicates, but deletes or moves nothing. A `--delete`, `--clean`, or implicit retention mutation flag must not exist.

- [ ] **Step 2: Prove RED**

Run `tests/test_output_inventory.py` and confirm collection fails because the
inventory script does not yet exist. Then add only the minimum read-only
inventory implementation needed for the test to pass.

- [ ] **Step 3: Define active versus historical documentation**

`docs/operator/README.md` remains the entry point. `docs/history/README.md` explains:

- active operator truth is linked from the operator README;
- plans/specs/research are historical evidence unless explicitly marked active;
- historical files are not apply authority;
- archive moves preserve Git history and require a dedicated later cleanup task.

Do not move hundreds of files in this task.

- [ ] **Step 4: Define ignored-output retention**

Document a recommended one-current-package-per-deck convention and use the inventory script to list older candidates. Do not delete the existing ShadowPriest variants or any other output.

- [ ] **Step 5: Add repository maintenance files**

`SECURITY.md` documents private reporting and explicitly excludes runtime
logs/replays from issues. `CONTRIBUTING.md` documents TDD, no raw runtime
evidence, the single operator authority, and required verification.
Dependency maintenance uses immutable GitHub Actions pins, `pip-audit`, and
deliberate manual updates. While the sole-main policy is active, do not add a
Dependabot version-update configuration or other automation that creates
dependency-update branches or pull requests.

- [ ] **Step 6: Pin actions immutably**

Replace mutable action tags with commit SHAs and keep a trailing version comment, for example:

```yaml
- uses: actions/checkout@<verified-sha> # v4
```

Resolve the current official SHAs during implementation from the action repositories. Do not guess them.

- [ ] **Step 7: Verify**

Run output-inventory tests, docs/skill contract tests, YAML parsing, Ruff, `pip-audit`, and the full suite. Run the inventory script against `outputs` read-only and save no generated report in Git.

- [ ] **Step 8: Review, commit, push**

Commit:

```text
chore: establish repository and output hygiene
```

---

## Phase D — Final matrix generation and release proof

### Task 14: Generate and audit all twelve packages without runtime writes

**Files:**

- No tracked production changes expected
- Temporary generated packages: outside the repository or under an ignored, uniquely named output root
- Optional tracked result only if it contains no private/runtime evidence: `docs/operator/verification/2026-07-27-integrity-hardening-summary.md`

- [ ] **Step 1: Reprove repository and GitHub currentness**

Require:

```powershell
git fetch --all --prune --tags
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
gh run list --branch main --limit 10
```

All required workflows for the final commit must be green.

- [ ] **Step 2: Create one temporary matrix root**

Use a unique temporary directory outside the repository. Generate each of the twelve exact catalog identities through the normal non-apply configure path. Public source acquisition may be attempted, but a missing/unavailable source must remain an honest diagnostic and must not be replaced with fabricated or captured authority.

- [ ] **Step 3: Validate every generated package**

For every deck:

- deck code decodes to 30 cards/zero sideboard;
- deck name, fingerprint, HS ID, and HDT ID match the catalog;
- exactly one config directory exists;
- `GlobalValues.json` and `Mulligan.json` are valid;
- every per-card runtime file follows the registry schema;
- `Combo.json` exists only for a complete, ordered, exact-source-backed sequence;
- no forbidden legacy/aggregate/default-only surface is hidden;
- strict validation passes;
- operator summary and recomputed apply decision agree;
- `runtime_write_performed` is absent or false;
- source strength and exact-source closure are reported honestly.

- [ ] **Step 4: Run the final verification stack**

```powershell
python -m ruff check --no-cache src tests scripts
python -m pip_audit
python scripts\sync_installed_skill.py --install-root .guardrail-skills
python scripts\check_contract_guardrails.py --skill-install-root .guardrail-skills
python -m hsconfig.cli contract-spine-sentinel --json
python -m pytest tests/test_audited_deck_set_acceptance.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
```

Record exact pass/skip counts and command exit codes. Remove `.guardrail-skills`, pytest artifacts, and the temporary package root afterward.

- [ ] **Step 5: Inspect final repository state**

Run:

```powershell
git diff --check
git status --short
git ls-files | Select-String -Pattern 'Power\.log|\.hdtreplay|\.hsreplay|BotPlayHistory|runtime_apply_receipt'
```

Expected: no diff, empty status, and no raw runtime evidence tracked.

- [ ] **Step 6: Publish a bounded verification summary**

If the optional summary is tracked, include only:

- commit SHA;
- local test/Ruff/audit results;
- GitHub workflow links;
- 12/12 identity/package-validation counts;
- per-deck semantic status and diagnostic source closure;
- explicit `RUNTIME_SAMPLED: NOT_PROVEN`;
- explicit `GAMEPLAY_OPTIMALITY: NOT_PROVEN`;
- explicit `runtime writes: 0`.

Never include source captures, logs, personal paths, runtime snapshots, or replay-derived data.

If a tracked summary is added, review, commit, and push it as:

```text
docs: record integrity hardening verification
```

Otherwise leave the repository exactly clean at the Task 13 commit.

## Final acceptance criteria

The plan is complete only when all of the following are true:

1. A clean install from declared dependencies runs both sentinels, Ruff, pip-audit, and the full test suite.
2. All required GitHub workflows are green on the final `main` SHA.
3. Canonical source receipts are semantically bound to an existing claim, its signature, and the exact deck fingerprint.
4. Empty exact-source evidence remains visible and non-blocking; malformed or forged evidence blocks.
5. Configure, operator summary, apply evaluation, and runtime apply use one canonical decision model with recomputation at the write boundary.
6. No Mulligan row can lower without explicit opening-hand intent.
7. No ordered Combo can lower from `+`, adjacency, deck coexistence, or a `Combo:` label alone.
8. Runtime match requires the exact deck-name/config-directory mapping exactly once.
9. Every failure after the first runtime mutation produces best-effort failure/rollback evidence while preserving the original exception.
10. The Darkbishop diagnostic recognizes the verified linked runtime owner and still keeps `SW_448` out of Mulligan without explicit evidence.
11. All twelve audited decks have explicit negative semantic boundaries, while CuteWarrior remains supplemental.
12. Audited deck identity has one canonical catalog; role-specific manifests retain their distinct meanings.
13. Configure/package orchestration is split into immutable, digest-bound stages without schema or CLI drift.
14. Documentation and ignored-output growth have non-destructive governance; no historical or runtime evidence was mass-deleted.
15. Twelve fresh packages validate with exact identities, zero runtime writes, and no claim of runtime or gameplay proof.
16. `main == origin/main`, no other branch or PR was created, and `git status --short` is empty.

## Stop and escalation rules

- Stop the current task—not the whole plan—if its RED test does not reproduce the audited defect. Investigate the assumption with `superpowers:systematic-debugging`, correct the task notes, then continue.
- If live public sources are unavailable, preserve the diagnostic status and continue package/load-safe verification. Never substitute stale/captured data as live authority.
- If a task uncovers a new integrity defect, add the smallest TDD subtask immediately before the dependent task. Do not defer a write-boundary or authority defect behind refactoring.
- If GitHub is temporarily unavailable, complete local verification, keep the worktree clean, and resume the push/workflow checkpoint when service returns. Do not create an alternative branch.
- No blocker authorizes runtime apply, speculative card tuning, deletion of historical evidence, or a second implementation copy.
