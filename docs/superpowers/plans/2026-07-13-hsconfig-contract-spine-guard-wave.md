# HSConfig Contract-Spine Guard Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden HSConfig's source-to-runtime contract spine so source claims stay slim, autonomous, non-blocking, and correctly separated from runtime apply authority.

**Architecture:** Preserve the existing single-spine model: source evidence becomes an explicit `claim_kind`, the source contract matrix defines the allowed surface, surface gates decide whether runtime lowering is legal, builders/routers emit runtime rows, and `reports/operator_summary.json` remains the only normal apply authority. This plan adds small regression guards and warning-only lint; it does not add a second gate, a new runtime surface, a new approval step, or post-game tuning logic.

**Tech Stack:** Python 3, pytest, existing `hsconfig` package modules, existing Superpowers plan workflow.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig pre-run only: no replay parsing, no winrate logic, no HSTuner orchestration, and no post-game candidate promotion.
- Keep `reports/operator_summary.json` as the only normal runtime apply authority.
- Keep `source_contract_audit.json`, `source_to_runtime_explainability.json`, `contract_spine_rows`, source-quality reports, and `contract-spine-sentinel` diagnostic-only.
- Do not add normal-path `Presume.json` or `Concede.json`.
- Do not block load-safe packages for weak source depth, warning-only mechanics, unsupported source claims, or thin but valid Mulligan evidence.
- Preserve the Darkbishop-style split: start-of-game / hero-power-transform effects remain visible, but the enabling card is not held in opening hand unless there is separate valid Mulligan evidence.
- Add no new dependencies.

---

## File Structure

- Modify `src/hsconfig/source_document_model.py`: merge embedded claim role hints into Mulligan surface suppression so direct or expert claims cannot bypass start-of-game non-hand suppression when `card_roles` is empty.
- Modify `src/hsconfig/source_evidence_verifier.py`: add warning-only lint for suspicious exact `mulligan_keep` claims that look like non-hand effects or broad importance rather than real opening-hand guidance.
- Modify `src/hsconfig/contract_spine_sentinel.py`: report missing configured active apply paths and keep diagnostic apply-token scanning stable.
- Modify `tests/test_claim_kind_runtime_contract.py`: add ingress and role-table regression coverage.
- Modify `tests/test_source_evidence_verifier.py`: add warning-only exact-keep lint coverage.
- Modify `tests/test_source_contract_spine_freeze.py`: add contract-metadata coverage for every supported claim kind.
- Modify `tests/test_contract_spine_sentinel.py`: add active-apply-path coverage.
- Modify `docs/operator/guide-research-policy.md`: document the claim-kind change checklist and suspicious exact-keep warning rule.

---

### Task 1: Close Role-Context Ingress For Start-Of-Game Mulligan Suppression

**Files:**
- Modify: `src/hsconfig/source_document_model.py`
- Test: `tests/test_claim_kind_runtime_contract.py`

**Interfaces:**
- Consumes: `surface_gate_decision(claim: Mapping[str, Any], surface: str, context: Mapping[str, Any] | None = None) -> SurfaceGateDecision`
- Consumes: `can_lower_to_mulligan(claim: Mapping[str, Any], *, card_roles: Mapping[str, Any] | None = None) -> SurfaceGateDecision`
- Produces: `_contains_start_of_game_non_hand_effect(cards: list[str], card_roles: Mapping[str, Any], claim: Mapping[str, Any] | None = None) -> bool`

- [ ] **Step 1: Write failing ingress tests**

Append these tests to `tests/test_claim_kind_runtime_contract.py`:

```python
def test_claim_embedded_start_of_game_roles_suppress_mulligan_keep_without_external_card_roles():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["SW_448"],
        "roles": ["start_of_game", "hero_power_transform"],
        "evidence_text_short": "The deck starts with Mind Spike because of Darkbishop Benedictus.",
    }

    decision = surface_gate_decision(claim, "mulligan", context={"card_roles": {}})

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_claim_embedded_semantic_families_suppress_mulligan_keep_without_external_card_roles():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_START"],
        "semantic_families": ["start_of_game", "passive_start_effect"],
        "evidence_text_short": "This passive effect is active at the start of the game.",
    }

    decision = surface_gate_decision(claim, "mulligan", context={"card_roles": {}})

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py::test_claim_embedded_start_of_game_roles_suppress_mulligan_keep_without_external_card_roles tests/test_claim_kind_runtime_contract.py::test_claim_embedded_semantic_families_suppress_mulligan_keep_without_external_card_roles -q
```

Expected: both tests fail because embedded claim roles are not considered by `_contains_start_of_game_non_hand_effect`.

- [ ] **Step 3: Implement embedded-role merging**

In `src/hsconfig/source_document_model.py`, change the Mulligan gate call:

```python
if claim_kind == "mulligan_keep" and _contains_start_of_game_non_hand_effect(
    cards,
    card_roles or {},
    claim,
):
```

Replace `_contains_start_of_game_non_hand_effect` with this implementation:

```python
def _contains_start_of_game_non_hand_effect(
    cards: list[str],
    card_roles: Mapping[str, Any],
    claim: Mapping[str, Any] | None = None,
) -> bool:
    for card_id in cards:
        roles = _roles_for_card(card_id, card_roles, claim)
        if "start_of_game" not in roles:
            continue
        if roles & START_OF_GAME_NON_HAND_EFFECT_ROLES:
            return True
        if "mulligan_anchor" not in roles:
            return True
    return False
```

Add this helper below it:

```python
def _roles_for_card(
    card_id: str,
    card_roles: Mapping[str, Any],
    claim: Mapping[str, Any] | None,
) -> set[str]:
    roles: set[str] = set()
    role_row = card_roles.get(str(card_id), {})
    if isinstance(role_row, Mapping):
        roles.update(str(role).lower() for role in role_row.get("roles", []))
        roles.update(
            str(role).lower() for role in role_row.get("semantic_families", [])
        )
    if isinstance(claim, Mapping):
        roles.update(str(role).lower() for role in claim.get("roles", []))
        roles.update(
            str(role).lower() for role in claim.get("semantic_families", [])
        )
        roles.update(
            str(role).lower() for role in claim.get("mechanic_families", [])
        )
    return {role for role in roles if role}
```

- [ ] **Step 4: Run targeted tests and verify pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py -q
```

Expected: all tests in `tests/test_claim_kind_runtime_contract.py` pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/hsconfig/source_document_model.py tests/test_claim_kind_runtime_contract.py
git commit -m "test: guard mulligan role context ingress"
```

---

### Task 2: Add Warning-Only Suspicious Exact-Keep Lint

**Files:**
- Modify: `src/hsconfig/source_evidence_verifier.py`
- Test: `tests/test_source_evidence_verifier.py`

**Interfaces:**
- Consumes: `claim_evidence_status(claim: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]`
- Produces warning rows with `reason == "suspicious_mulligan_keep_non_hand_effect"`

- [ ] **Step 1: Write failing source-verifier tests**

Append these tests to `tests/test_source_evidence_verifier.py`:

```python
def test_verifier_warns_for_suspicious_exact_keep_on_non_hand_effect():
    report = verify_source_documents(
        [
            _base_document(
                claims=[
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_448"],
                        "roles": ["start_of_game", "hero_power_transform"],
                        "evidence_text_short": "Darkbishop Benedictus starts the game with Mind Spike.",
                        "source_confidence": "high",
                    }
                ]
            )
        ]
    )

    assert report["status"] == "warnings"
    assert "suspicious_mulligan_keep_non_hand_effect" in {
        warning["reason"] for warning in report["warnings"]
    }


def test_verifier_does_not_warn_for_explicit_opening_hand_keep_language():
    report = verify_source_documents(
        [
            _base_document(
                claims=[
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["EX1_001"],
                        "roles": ["mulligan_anchor"],
                        "evidence_text_short": "Always keep this one-drop in the mulligan.",
                        "source_confidence": "high",
                    }
                ]
            )
        ]
    )

    assert "suspicious_mulligan_keep_non_hand_effect" not in {
        warning["reason"] for warning in report["warnings"]
    }
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_evidence_verifier.py::test_verifier_warns_for_suspicious_exact_keep_on_non_hand_effect tests/test_source_evidence_verifier.py::test_verifier_does_not_warn_for_explicit_opening_hand_keep_language -q
```

Expected: the first test fails because the warning reason is not emitted yet.

- [ ] **Step 3: Implement the warning-only lint**

In `src/hsconfig/source_evidence_verifier.py`, extend the import:

```python
from hsconfig.source_document_model import (
    START_OF_GAME_NON_HAND_EFFECT_ROLES,
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    runtime_claim_kind,
)
```

Add constants below `ACTIONABLE_SPECIFICITY_KEYS`:

```python
OPENING_HAND_LANGUAGE = (
    "mulligan",
    "opening hand",
    "starting hand",
    "keep this",
    "always keep",
    "hard keep",
)

SUSPICIOUS_KEEP_ROLE_KEYS = (
    "roles",
    "semantic_families",
    "mechanic_families",
)
```

Inside `claim_evidence_status`, after the `runtime_lowering_claim_lacks_actionable_specificity` block, add:

```python
    suspicious_keep_warning = _suspicious_exact_keep_warning(claim, claim_kind)
    if suspicious_keep_warning is not None:
        warnings.append(suspicious_keep_warning)
```

Add these helpers before `_cards`:

```python
def _suspicious_exact_keep_warning(
    claim: dict[str, Any],
    claim_kind: str,
) -> dict[str, Any] | None:
    if claim_kind != "mulligan_keep":
        return None
    evidence = _claim_evidence_text(claim).lower()
    if _has_opening_hand_language(evidence):
        return None
    roles = _claim_role_hints(claim)
    if "start_of_game" in roles or roles & START_OF_GAME_NON_HAND_EFFECT_ROLES:
        return {
            "reason": "suspicious_mulligan_keep_non_hand_effect",
            "claim_kind": claim_kind,
            "roles": sorted(roles),
        }
    return None


def _has_opening_hand_language(evidence: str) -> bool:
    return any(term in evidence for term in OPENING_HAND_LANGUAGE)


def _claim_role_hints(claim: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    for key in SUSPICIOUS_KEEP_ROLE_KEYS:
        value = claim.get(key, [])
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            roles.update(str(item).strip().lower() for item in value if str(item).strip())
    return roles
```

- [ ] **Step 4: Run verifier tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_evidence_verifier.py -q
```

Expected: all source verifier tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/hsconfig/source_evidence_verifier.py tests/test_source_evidence_verifier.py
git commit -m "feat: warn on suspicious exact mulligan keeps"
```

---

### Task 3: Make The Non-Hand Effect Role Table Self-Guarding

**Files:**
- Modify: `tests/test_claim_kind_runtime_contract.py`

**Interfaces:**
- Consumes: `START_OF_GAME_NON_HAND_EFFECT_ROLES`
- Produces: tests that fail when new non-hand roles are added without exercising Mulligan suppression

- [ ] **Step 1: Replace hard-coded parametrization with the production constant**

In `tests/test_claim_kind_runtime_contract.py`, update the import:

```python
from hsconfig.source_document_model import (
    START_OF_GAME_NON_HAND_EFFECT_ROLES,
    runtime_claim_kind,
    surface_gate_decision,
)
```

Replace the current hard-coded `@pytest.mark.parametrize("role", [...])` for `test_start_of_game_non_hand_roles_suppress_mulligan_keep` with:

```python
@pytest.mark.parametrize("role", sorted(START_OF_GAME_NON_HAND_EFFECT_ROLES))
```

- [ ] **Step 2: Add an explicit sanity test for the role table**

Append this test near the role-table tests:

```python
def test_start_of_game_non_hand_role_table_contains_known_effect_families():
    assert "hero_power_transform" in START_OF_GAME_NON_HAND_EFFECT_ROLES
    assert "deckbuilding_modifier" in START_OF_GAME_NON_HAND_EFFECT_ROLES
    assert "passive_start_effect" in START_OF_GAME_NON_HAND_EFFECT_ROLES
    assert "start_in_deck_requirement" in START_OF_GAME_NON_HAND_EFFECT_ROLES
```

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit Task 3**

```powershell
git add tests/test_claim_kind_runtime_contract.py
git commit -m "test: freeze start-of-game non-hand role coverage"
```

---

### Task 4: Add Claim-Kind Change Guard And Operator Documentation

**Files:**
- Modify: `tests/test_source_contract_spine_freeze.py`
- Modify: `docs/operator/guide-research-policy.md`

**Interfaces:**
- Consumes: `source_contract_policy_by_claim_kind() -> dict[str, dict[str, object]]`
- Produces: a test-backed checklist for adding or changing claim kinds

- [ ] **Step 1: Write policy metadata guard test**

Append this test to `tests/test_source_contract_spine_freeze.py`:

```python
def test_each_policy_row_has_complete_contract_metadata():
    policy = source_contract_policy_by_claim_kind()

    for claim_kind, row in policy.items():
        assert row["semantic_lane"] == row["lane"], claim_kind
        assert isinstance(row["required_fields"], tuple), claim_kind
        assert "claim_kind" in row["required_fields"], claim_kind
        assert "claim_readiness" in row["required_fields"], claim_kind
        assert "trust_ceiling" in row["required_fields"], claim_kind
        assert isinstance(row["runtime_lowerable"], bool), claim_kind
        assert isinstance(row["default_suppression_reason"], str), claim_kind
        assert row["default_suppression_reason"], claim_kind
        assert row["operator_gate_impact"] == "diagnostic_only", claim_kind
        assert set(row["allowed_surfaces"]).issubset(
            {"mulligan", "globalvalues", "cardid", "combo"}
        ), claim_kind
```

- [ ] **Step 2: Run the policy test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_contract_spine_freeze.py -q
```

Expected: all policy freeze tests pass.

- [ ] **Step 3: Document the claim-kind change checklist**

Add this section to `docs/operator/guide-research-policy.md` after the existing source claim policy section:

```markdown
## Claim-Kind Change Checklist

Changing or adding a `claim_kind` is a contract change, not a local parser tweak.
Every such change must update all of these surfaces in the same pull request:

- `SUPPORTED_ATOMIC_CLAIM_KINDS` in `src/hsconfig/source_document_model.py`
- the policy row and policy details in `src/hsconfig/source_contract_matrix.py`
- the matching surface gate in `src/hsconfig/source_document_model.py`
- the builder, router, or diagnostic path that owns the final runtime effect
- conformance and freeze coverage in `tests/test_source_contract_spine_freeze.py`
- runtime contract coverage in `tests/test_claim_kind_runtime_contract.py`

Diagnostics may explain a claim, but they must not grant or deny runtime apply.
`reports/operator_summary.json` remains the normal apply authority.
```

Add this warning rule near the Mulligan policy text:

```markdown
Exact `mulligan_keep` claims should describe opening-hand intent. If the evidence
only describes a start-of-game effect, hero-power transform, deckbuilding rule, or
broad card importance, HSConfig may warn about a suspicious exact keep. That
warning is diagnostic only; it does not block a load-safe package.
```

- [ ] **Step 4: Run docs and focused policy tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_docs_contract_policy.py tests/test_source_contract_spine_freeze.py -q
```

Expected: docs-policy tests and freeze tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add docs/operator/guide-research-policy.md tests/test_source_contract_spine_freeze.py
git commit -m "docs: document claim-kind contract change guard"
```

---

### Task 5: Harden Contract-Spine Sentinel Active Apply Path Coverage

**Files:**
- Modify: `src/hsconfig/contract_spine_sentinel.py`
- Test: `tests/test_contract_spine_sentinel.py`

**Interfaces:**
- Consumes: `ACTIVE_APPLY_PATHS`
- Produces: `checks["active_apply_paths_missing"]`
- Produces: `problems` row with `check == "active_apply_paths_missing"` when a configured active apply path does not exist

- [ ] **Step 1: Write failing sentinel path test**

Append this test to `tests/test_contract_spine_sentinel.py`:

```python
from pathlib import Path


def test_contract_spine_sentinel_flags_missing_active_apply_path(tmp_path, monkeypatch):
    from hsconfig import contract_spine_sentinel as sentinel

    existing = tmp_path / "src" / "hsconfig" / "apply_gate.py"
    existing.parent.mkdir(parents=True)
    existing.write_text("def evaluate_apply_gate():\n    return None\n", encoding="utf-8")

    monkeypatch.setattr(
        sentinel,
        "ACTIVE_APPLY_PATHS",
        (
            "src/hsconfig/apply_gate.py",
            "src/hsconfig/runtime_apply.py",
        ),
    )

    report = sentinel.build_contract_spine_sentinel_report(repo_root=tmp_path)

    assert report["status"] == "drift_detected"
    assert report["checks"]["active_apply_paths_missing"] == [
        "src/hsconfig/runtime_apply.py"
    ]
    assert {
        "check": "active_apply_paths_missing",
        "value": ["src/hsconfig/runtime_apply.py"],
    } in report["problems"]
```

- [ ] **Step 2: Run the new sentinel test and verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_spine_sentinel.py::test_contract_spine_sentinel_flags_missing_active_apply_path -q
```

Expected: test fails because `active_apply_paths_missing` is not reported yet.

- [ ] **Step 3: Implement missing-path reporting**

In `src/hsconfig/contract_spine_sentinel.py`, add this check inside the `checks` dictionary:

```python
"active_apply_paths_missing": _missing_active_apply_paths(root),
```

Replace `_active_apply_diagnostic_consumers` with this safer implementation:

```python
def _active_apply_diagnostic_consumers(root: Path) -> list[dict[str, str]]:
    consumers: list[dict[str, str]] = []
    for relative_path in ACTIVE_APPLY_PATHS:
        path = root / relative_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for token in DIAGNOSTIC_ONLY_TOKENS:
            if token in content:
                consumers.append({"path": relative_path, "token": token})
    return consumers
```

Add this helper next to it:

```python
def _missing_active_apply_paths(root: Path) -> list[str]:
    return [
        relative_path
        for relative_path in ACTIVE_APPLY_PATHS
        if not (root / relative_path).exists()
    ]
```

In `_problems`, add `"active_apply_paths_missing"` to `list_checks`:

```python
list_checks = (
    "policy_missing_claim_kinds",
    "policy_extra_claim_kinds",
    "spine_missing_claim_kinds",
    "spine_extra_claim_kinds",
    "non_diagnostic_policy_claim_kinds",
    "spine_rows_with_apply_authority_fields",
    "conformance_apply_authority_fields_present",
    "active_apply_diagnostic_consumers",
    "active_apply_paths_missing",
)
```

- [ ] **Step 4: Run sentinel tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_contract_spine_sentinel.py tests/test_contract_spine_sentinel_cli.py -q
```

Expected: all sentinel tests pass.

- [ ] **Step 5: Commit Task 5**

```powershell
git add src/hsconfig/contract_spine_sentinel.py tests/test_contract_spine_sentinel.py
git commit -m "test: harden contract spine sentinel path coverage"
```

---

### Task 6: Final Verification And Research Artifact Decision

**Files:**
- Review: `docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v2/`
- Review: all files changed in Tasks 1-5

**Interfaces:**
- Consumes: focused guard tests
- Produces: clean git state and a pushed branch or main commit, depending on the execution request

- [ ] **Step 1: Run the focused guard suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_source_evidence_verifier.py tests/test_source_contract_spine_freeze.py tests/test_contract_spine_sentinel.py tests/test_contract_spine_sentinel_cli.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run sentinel CLI**

Run:

```powershell
$env:PYTHONPATH='src'; python -m hsconfig contract-spine-sentinel --json
```

Expected:

```json
{
  "status": "clean",
  "authority": "diagnostic_only",
  "operator_gate_impact": "diagnostic_only",
  "apply_blocking": false,
  "problems": []
}
```

The actual JSON contains more fields; these key values must match.

- [ ] **Step 3: Run a wider regression slice**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_apply_gate.py tests/test_surface_authority_split.py tests/test_source_contract_conformance.py tests/test_source_to_runtime_explainability.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_depth_e2e.py -q
```

Expected: all selected regression tests pass.

- [ ] **Step 4: Inspect git diff**

Run:

```powershell
git diff -- src/hsconfig/source_document_model.py src/hsconfig/source_evidence_verifier.py src/hsconfig/contract_spine_sentinel.py tests/test_claim_kind_runtime_contract.py tests/test_source_evidence_verifier.py tests/test_source_contract_spine_freeze.py tests/test_contract_spine_sentinel.py docs/operator/guide-research-policy.md
```

Expected: diff only contains the guard changes from this plan. It must not add new runtime surfaces, new apply gates, `Presume.json`, `Concede.json`, replay parsing, winrate logic, or HSTuner logic.

- [ ] **Step 5: Decide research package handling**

Run:

```powershell
git status --short
```

If `docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v2/` is still untracked, include it in the final commit only if the user wants the research evidence preserved in repo. If it is not committed, mention it explicitly in the final handoff.

- [ ] **Step 6: Commit final docs/research decision if needed**

If committing the research package:

```powershell
git add docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v2
git commit -m "docs: add contract spine guard research"
```

If not committing it, do not delete it unless the user explicitly asks to keep the repo free of local research artifacts.

---

## Self-Review

- Spec coverage: The plan covers the recommended five-part Contract-Spine Guard Wave: role-context ingress, suspicious exact-keep lint, non-hand role-table guard, claim-kind checklist, and sentinel active apply path coverage.
- Scope: The plan does not add runtime surfaces, dependencies, replay parsing, HSTuner logic, winrate logic, or a second apply gate.
- Type consistency: The plan uses existing names from the codebase: `START_OF_GAME_NON_HAND_EFFECT_ROLES`, `surface_gate_decision`, `can_lower_to_mulligan`, `claim_evidence_status`, `source_contract_policy_by_claim_kind`, `ACTIVE_APPLY_PATHS`, and `build_contract_spine_sentinel_report`.
- No placeholders: All tasks include exact files, test names, code snippets, commands, and expected outcomes.
