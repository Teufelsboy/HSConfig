# HSConfig Contract Spine Guardrail v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's source-to-runtime contract easier to audit and harder to mis-lower, while preserving the current no-block any-deck apply contract.

**Architecture:** Keep the existing two-lane design. `reports/operator_summary.json` remains the only normal apply authority; source-contract reports stay diagnostic-only. This wave adds compact active documentation, stronger false-lowering fixtures, and guardrail coverage around the already-existing contract spine rather than adding a new runtime surface or a second gate.

**Tech Stack:** Python 3.11, pytest, existing `hsconfig` package modules, existing markdown operator docs, existing GitHub Actions `contract-guardrails` workflow.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for the `Teufelsboy/HSConfig` repository.
- Do not add HSTuner, replay parsing, winrate validation, post-game tuning, candidate promotion, or runtime-evidence analysis to HSConfig.
- Do not add `Presume.json`, `Concede.json`, aggregate `CardBehavior.json`, or any new normal runtime surface.
- Do not create a second apply gate from `source_contract_audit.json`, `source_to_runtime_explainability.json`, `source_claim_gap_report.json`, `contract_spine_rows`, or research artifacts.
- Keep `reports/operator_summary.json` as the only normal apply authority.
- A valid deck must still produce a load-safe package even when source evidence is thin, mechanics are warning-only, option identity is unresolved, or some claims are report-only.
- Keep warnings visible but non-blocking unless the package has a true technical load-safety defect.
- Preserve the Darkbishop Benedictus boundary: effect semantics may be encoded, but start-of-game hero-power effects are not opening-hand mulligan keeps without explicit opening-hand evidence.
- Use the existing research package as evidence: `docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/`.

---

## File Structure

- Modify `docs/research/current-truth.md`: index the new 2026-07-14 research package as active evidence, not operator guidance.
- Create `docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/README.md`: mark the package as research evidence only.
- Create `docs/operator/source-contract-spine.md`: compact active reference for claim-kind lanes, runtime surfaces, false-lowering boundaries, and the single apply authority.
- Modify `docs/operator/README.md`: link the compact contract-spine reference without making it the normal command path.
- Modify `docs/operator/guide-research-policy.md`: add a short source-to-runtime decision rule section, not a new workflow.
- Modify `.agents/skills/hsconfig/SKILL.md`: mirror the one-paragraph source-contract boundary in the installed skill source.
- Modify `.agents/skills/hsconfig/references/guide-research-policy.md`: keep the skill reference in sync with operator policy.
- Modify `tests/test_docs_active_path.py`: assert the new research package is indexed and remains evidence-only.
- Modify `tests/test_operator_docs_contract_policy.py`: assert the new compact contract-spine doc names all supported claim kinds, stays diagnostic-only, and preserves one apply authority.
- Modify `tests/test_semantic_runtime_negative_boundaries.py`: add false-lowering tests for deckbuilding-only effects, random generated pools, location/secret/weapon timing, and modern Wild mechanics.
- Modify `tests/test_source_contract_conformance.py`: assert compact rendered conformance still contains all claim kinds and no apply authority fields.
- Modify `tests/test_check_contract_guardrails.py`: ensure the guardrail runner includes the strengthened docs and false-lowering tests.
- Modify `scripts/check_contract_guardrails.py` only if the new/changed test file is not already in `FOCUSED_CONTRACT_TESTS`.

---

### Task 1: Index the New Research Package Without Making It Operator Guidance

**Files:**
- Create: `docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/README.md`
- Modify: `docs/research/current-truth.md`
- Modify: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: existing research artifacts under `docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/`.
- Produces: active evidence index entry used by docs tests.

- [ ] **Step 1: Write the failing docs test**

Add this test to `tests/test_docs_active_path.py`:

```python
def test_current_truth_names_2026_07_14_contract_guardrail_audit():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")
    audit_readme = Path(
        "docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/README.md"
    ).read_text(encoding="utf-8")

    assert "2026-07-14-hsconfig-source-contract-logic-guardrail-audit" in text
    assert "Contract-spine Guardrail v2 evidence" in text
    assert "Research evidence only" in audit_readme
    assert "not operator instructions" in audit_readme
    assert "not runtime input" in audit_readme
    assert "`operator_summary.json` remains the normal apply authority." in audit_readme
    assert "`source_contract_audit.json` remains diagnostic." in audit_readme
    assert "`source_to_runtime_explainability.json` remains diagnostic." in audit_readme
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest -q tests/test_docs_active_path.py::test_current_truth_names_2026_07_14_contract_guardrail_audit
```

Expected: FAIL because the README and current-truth entry do not exist yet.

- [ ] **Step 3: Create the research README**

Create `docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/README.md` with:

```markdown
# 2026-07-14 HSConfig Source Contract Logic Guardrail Audit

Research evidence only.

This package is not operator instructions, not runtime input, and not an apply gate. Normal deck work starts at `docs/operator/README.md`.

## Evidence Scope

- Current HSConfig contract-spine guardrails
- HearthRanger VisionAI runtime-surface boundary
- Hearthstone semantic false-lowering risks
- Lean any-deck no-block contract

## Active Boundary

`operator_summary.json` remains the normal apply authority.

`source_contract_audit.json` remains diagnostic.

`source_to_runtime_explainability.json` remains diagnostic.

`contract_spine_rows` remain diagnostic.

Warnings are follow-up work, not runtime apply blockers.
```

- [ ] **Step 4: Add the current-truth entry**

In `docs/research/current-truth.md`, add one entry near the active evidence list:

```markdown
- `2026-07-14-hsconfig-source-contract-logic-guardrail-audit`: Contract-spine Guardrail v2 evidence. Confirms the current two-lane model: technical load safety decides normal apply, while source-contract, source-to-runtime, and mechanic warnings stay diagnostic and non-blocking.
```

- [ ] **Step 5: Run the test**

Run:

```powershell
python -m pytest -q tests/test_docs_active_path.py::test_current_truth_names_2026_07_14_contract_guardrail_audit
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit docs/research/current-truth.md tests/test_docs_active_path.py
git commit -m "docs: index contract guardrail audit research"
```

---

### Task 2: Add a Compact Active Source-Contract Spine Reference

**Files:**
- Create: `docs/operator/source-contract-spine.md`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes: `source_contract_policy_by_claim_kind()` and `SUPPORTED_ATOMIC_CLAIM_KINDS` contract semantics already enforced in code.
- Produces: one active human-readable reference that explains claim kind, surface, and non-blocking behavior.

- [ ] **Step 1: Write the failing docs policy test**

Add this test to `tests/test_operator_docs_contract_policy.py`:

```python
def test_source_contract_spine_reference_is_active_but_not_an_apply_gate():
    text = (ROOT / "docs" / "operator" / "source-contract-spine.md").read_text(
        encoding="utf-8"
    )

    required_claim_kinds = {
        "archetype",
        "mulligan_keep",
        "mulligan_discard",
        "card_role",
        "targeting_rule",
        "combo_sequence",
        "gameplan_posture",
        "hero_power_transform",
        "mechanic_usage",
        "known_bad_pattern",
        "tech_slot",
        "replacement_option",
        "discover_choice",
        "choose_one_choice",
        "globalvalue_numeric_tuning",
    }

    assert "Diagnostic reference only" in text
    assert "`reports/operator_summary.json` remains the only normal apply authority." in text
    assert "does not create a second apply gate" in text
    assert "Mulligan.json" in text
    assert "GlobalValues.json" in text
    assert "Combo.json" in text
    assert "CARDID.json" in text
    assert "Presume.json" in text
    assert "Concede.json" in text
    for claim_kind in required_claim_kinds:
        assert f"`{claim_kind}`" in text
```

Add this test to the same file:

```python
def test_operator_readme_links_source_contract_spine_without_normal_path_drift():
    text = (ROOT / "docs" / "operator" / "README.md").read_text(encoding="utf-8")
    first_120_lines = "\n".join(text.splitlines()[:120])

    assert "docs/operator/source-contract-spine.md" in text
    assert "hsconfig configure" in first_120_lines
    assert "source-contract-spine" not in first_120_lines
    assert "source-contract-spine -> apply" not in text
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
python -m pytest -q tests/test_operator_docs_contract_policy.py::test_source_contract_spine_reference_is_active_but_not_an_apply_gate tests/test_operator_docs_contract_policy.py::test_operator_readme_links_source_contract_spine_without_normal_path_drift
```

Expected: FAIL because the new doc and link do not exist yet.

- [ ] **Step 3: Create `docs/operator/source-contract-spine.md`**

Create the file with:

```markdown
# Source Contract Spine

Diagnostic reference only.

`reports/operator_summary.json` remains the only normal apply authority.

This page explains why a source claim did or did not lower to runtime config. It does not create a second apply gate.

## Normal Runtime Surfaces

| Surface | Use |
| --- | --- |
| `Mulligan.json` | Explicit opening-hand `mulligan_keep` and `mulligan_discard` claims only. |
| `GlobalValues.json` | Governed Step 1 posture overlays from `gameplan_posture`; numeric tuning waits for runtime evidence. |
| `Combo.json` | Explicit ordered `combo_sequence` claims only. |
| `CARDID.json` | Card-local behavior such as targeting, hero-power transform, option identity, and supported mechanic behavior. |

`Presume.json` and `Concede.json` are documented HearthRanger concepts but not normal HSConfig runtime outputs.

## Claim-Kind Spine

| Claim Kind | Lane | Runtime Surface | Boundary |
| --- | --- | --- | --- |
| `archetype` | report_only | none | Context only; not a runtime row. |
| `mulligan_keep` | runtime_lowerable | `Mulligan.json` | Requires explicit opening-hand keep intent. |
| `mulligan_discard` | runtime_lowerable | `Mulligan.json` | Requires explicit opening-hand discard intent. |
| `card_role` | suppressed_or_conditional | `CARDID.json` | Requires supported card behavior surface. |
| `targeting_rule` | runtime_lowerable | `CARDID.json` | Requires supported target and block identity. |
| `combo_sequence` | runtime_lowerable | `Combo.json` | Requires complete ordered sequence. |
| `gameplan_posture` | runtime_lowerable | `GlobalValues.json` | Posture overlay only; not numeric runtime tuning. |
| `hero_power_transform` | suppressed_or_conditional | `CARDID.json` | Preserves effect semantics; not a mulligan keep by itself. |
| `mechanic_usage` | suppressed_or_conditional | `CARDID.json` | Requires documented CardID surface. |
| `known_bad_pattern` | suppressed_or_conditional | `CARDID.json` | Requires supported negative behavior row. |
| `tech_slot` | report_only | none | Deck construction advice only. |
| `replacement_option` | report_only | none | Deck replacement advice only. |
| `discover_choice` | suppressed_or_conditional | `CARDID.json` | Requires exact Discover option identity. |
| `choose_one_choice` | suppressed_or_conditional | `CARDID.json` | Requires exact Choose One option identity. |
| `globalvalue_numeric_tuning` | runtime_evidence_required | none | Requires runtime evidence before numeric write. |

## False-Lowering Boundaries

- Start-of-game effects are not opening-hand mulligan keeps unless the source explicitly says to keep the card in the opening hand.
- Deckbuilding effects are contract evidence, not live runtime actions.
- Discover and Choose One claims need exact option identity before lowering.
- Generated random pools stay report-visible unless the generated entity is deterministic.
- Secret timing, location activation, weapon attack posture, Titan choices, Tourist deckbuilding, Imbue, Forge, Excavate, and unknown mechanics stay warning/report-first until a deterministic runtime mapping exists.

Warnings are follow-up work, not runtime apply blockers.
```

- [ ] **Step 4: Link from operator docs outside the first normal-path section**

In `docs/operator/README.md`, add one sentence after the preferred normal path section, not before it:

```markdown
For the active claim-kind-to-runtime boundary, see `docs/operator/source-contract-spine.md`; it is a diagnostic reference, not a command path.
```

- [ ] **Step 5: Add the short decision rule to guide policy**

In `docs/operator/guide-research-policy.md`, add:

```markdown
## Source-To-Runtime Decision Rule

Source truth becomes runtime config only through `claim_kind`, the source contract matrix, and the surface gate for the target runtime file. Guide importance, archetype value, or effect relevance do not bypass this chain.

When the chain is incomplete, HSConfig should keep the claim visible in reports and still produce a load-safe package when the package is technically valid.
```

- [ ] **Step 6: Run the tests**

Run:

```powershell
python -m pytest -q tests/test_operator_docs_contract_policy.py tests/test_docs_active_path.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add docs/operator/source-contract-spine.md docs/operator/README.md docs/operator/guide-research-policy.md tests/test_operator_docs_contract_policy.py tests/test_docs_active_path.py
git commit -m "docs: add source contract spine reference"
```

---

### Task 3: Strengthen False-Lowering Boundary Tests

**Files:**
- Modify: `tests/test_semantic_runtime_negative_boundaries.py`
- Modify: `tests/test_static_semantics.py` only if a missing semantic family is discovered by the new tests.
- Modify: `src/hsconfig/static_semantics.py` only if a missing semantic family is discovered by the new tests.
- Modify: `src/hsconfig/source_document_model.py` only if surface gate behavior does not match the expected boundary.

**Interfaces:**
- Consumes: `infer_static_semantics(card: dict) -> dict`, `surface_gate_decision(claim, surface, context=None)`, `can_lower_to_mulligan(claim, card_roles=...)`, `route_card_behavior_surfaces(claims, identity_links=...)`.
- Produces: stronger proof that unsupported mechanics stay visible or suppressed without becoming wrong runtime rows.

- [ ] **Step 1: Write the failing tests**

Append these tests to `tests/test_semantic_runtime_negative_boundaries.py`:

```python
from hsconfig.static_semantics import infer_static_semantics


def test_deckbuilding_effect_does_not_lower_to_opening_hand_keep():
    claim = {
        "claim_id": "highlander_effect_not_keep",
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["HIGHLANDER_FIXTURE"],
        "semantic_qualifiers": {
            "timing": "start_of_game",
            "state_requirements": "deckbuilding_effect",
            "zone_scope": "deck",
        },
    }

    decision = can_lower_to_mulligan(
        claim,
        card_roles={
            "HIGHLANDER_FIXTURE": {
                "roles": ["start_of_game", "deckbuilding_modifier"],
                "semantic_families": ["start_of_game", "deckbuilding_modifier"],
            }
        },
    )

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_generated_random_pool_does_not_become_deterministic_cardid_behavior():
    claim = {
        "claim_id": "random_generate_claim",
        "claim_kind": "mechanic_usage",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["RANDOM_POOL_CARD"],
        "mechanic": "generated_entity_random_pool",
        "evidence_text_short": "Generate a random minion.",
    }

    result = route_card_behavior_surfaces([claim], identity_links={})

    assert result["rows"] == []
    assert result["suppressed"][0]["claim_id"] == "random_generate_claim"
    assert result["suppressed"][0]["reason"] in {
        "requires_supported_cardid_surface",
        "unsupported_mechanic_surface",
        "unresolved_option_identity",
    }


def test_timing_mechanics_are_warning_first_not_cross_surface_claims():
    cards = [
        {
            "id": "SECRET_FIXTURE",
            "type": "SPELL",
            "mechanics": ["SECRET"],
            "text": "Secret: When your opponent casts a spell, summon a random minion.",
        },
        {
            "id": "LOCATION_FIXTURE",
            "type": "LOCATION",
            "text": "Summon two Treants.",
        },
        {
            "id": "WEAPON_FIXTURE",
            "type": "WEAPON",
            "text": "After your hero attacks, Discover a spell.",
        },
    ]

    families_by_id = {
        card["id"]: set(infer_static_semantics(card)["families"])
        for card in cards
    }

    assert {"secret", "generated_entity_random_pool"} <= families_by_id["SECRET_FIXTURE"]
    assert "location" in families_by_id["LOCATION_FIXTURE"]
    assert {"weapon", "discover"} <= families_by_id["WEAPON_FIXTURE"]


def test_modern_wild_keywords_remain_report_first_until_surface_exists():
    for keyword in ("Titan", "Tourist", "Imbue", "Forge", "Excavate"):
        result = infer_static_semantics(
            {
                "id": f"{keyword.upper()}_FIXTURE",
                "type": "MINION",
                "text": f"{keyword}: fixture text.",
            }
        )

        assert keyword.lower() in result["families"]
        assert keyword.lower() in result["warning_only"]
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
python -m pytest -q tests/test_semantic_runtime_negative_boundaries.py
```

Expected: FAIL if any semantic family or suppression reason is missing.

- [ ] **Step 3: Implement only the missing boundary support**

If the modern keyword test fails, extend `src/hsconfig/static_semantics.py` so `infer_static_semantics()` adds these lowercase families and warning-only entries when the card text contains the keyword:

```python
MODERN_WARNING_ONLY_KEYWORDS = {
    "titan": "titan",
    "tourist": "tourist",
    "imbue": "imbue",
    "forge": "forge",
    "excavate": "excavate",
}
```

Use the existing text-normalization and family-addition pattern in `static_semantics.py`. Do not add runtime lowering.

If the random generated pool test fails because `route_card_behavior_surfaces()` emits a row, update `src/hsconfig/card_behavior_surface_router.py` to suppress `mechanic == "generated_entity_random_pool"` with reason `requires_supported_cardid_surface` or the existing closest supported suppression reason. Do not create a runtime row.

If the deckbuilding-effect mulligan test fails, update `src/hsconfig/source_document_model.py` only inside `_contains_start_of_game_non_hand_effect()` so `deckbuilding_effect` and `zone_scope=deck` continue to reject opening-hand lowering unless `has_explicit_opening_hand_mulligan_intent()` returns true.

- [ ] **Step 4: Run the focused boundary tests**

Run:

```powershell
python -m pytest -q tests/test_semantic_runtime_negative_boundaries.py tests/test_static_semantics.py tests/test_surface_authority_split.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_semantic_runtime_negative_boundaries.py tests/test_static_semantics.py src/hsconfig/static_semantics.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/source_document_model.py
git commit -m "test: harden semantic false-lowering boundaries"
```

---

### Task 4: Make the Contract-Spine Snapshot Explicitly Cover the New Reference

**Files:**
- Modify: `tests/test_source_contract_conformance.py`
- Modify: `src/hsconfig/source_contract_conformance.py` only if a missing markdown line is discovered.

**Interfaces:**
- Consumes: `build_source_contract_conformance_snapshot()` and `render_source_contract_conformance_markdown(snapshot)`.
- Produces: test coverage that the rendered conformance remains compact, diagnostic-only, and complete enough for the operator reference.

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_source_contract_conformance.py`:

```python
def test_rendered_conformance_snapshot_is_complete_reference_material():
    snapshot = build_source_contract_conformance_snapshot()
    markdown = render_source_contract_conformance_markdown(snapshot)

    for claim_kind in SUPPORTED_ATOMIC_CLAIM_KINDS:
        assert f"| {claim_kind} |" in markdown

    assert "Diagnostic only" in markdown
    assert "operator_summary.json remains the apply authority" in markdown
    assert "## Contract Spine" in markdown
    assert "## Start-of-Game Mulligan Boundary" in markdown
    assert "start_of_game_effect_does_not_require_opening_hand" in markdown
    assert "runtime_apply_allowed" not in markdown
    assert "technical_status" not in markdown
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest -q tests/test_source_contract_conformance.py::test_rendered_conformance_snapshot_is_complete_reference_material
```

Expected: PASS if current renderer already satisfies it; FAIL only if the rendered snapshot is missing a required boundary.

- [ ] **Step 3: Implement minimal renderer fix if needed**

If the test fails because a section is absent, update `render_source_contract_conformance_markdown()` in `src/hsconfig/source_contract_conformance.py` to include only the missing section header or row. Do not add apply authority fields to the snapshot or markdown.

- [ ] **Step 4: Run conformance tests**

Run:

```powershell
python -m pytest -q tests/test_source_contract_conformance.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_source_contract_conformance.py src/hsconfig/source_contract_conformance.py
git commit -m "test: lock contract spine reference completeness"
```

---

### Task 5: Sync Skill Text With the Active Source-Contract Boundary

**Files:**
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes: active operator policy from `docs/operator/guide-research-policy.md`.
- Produces: installed skill source that repeats the same boundary without becoming longer than necessary.

- [ ] **Step 1: Write the failing skill-doc test**

Add this test to `tests/test_operator_docs_contract_policy.py`:

```python
def test_skill_text_names_source_contract_spine_without_runtime_surface_expansion():
    skill = (ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    reference = (
        ROOT
        / ".agents"
        / "skills"
        / "hsconfig"
        / "references"
        / "guide-research-policy.md"
    ).read_text(encoding="utf-8")
    combined = f"{skill}\n{reference}"

    assert "`claim_kind`" in combined
    assert "source contract matrix" in combined
    assert "surface gate" in combined
    assert "operator_summary.json remains the normal apply authority" in combined
    assert "Warnings are follow-up work, not runtime apply blockers." in combined
    assert "normal HSConfig output must not emit `Presume.json` or `Concede.json`" in combined
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest -q tests/test_operator_docs_contract_policy.py::test_skill_text_names_source_contract_spine_without_runtime_surface_expansion
```

Expected: FAIL if the skill text does not yet contain the exact compact wording.

- [ ] **Step 3: Update the skill source**

Add this compact section to `.agents/skills/hsconfig/SKILL.md`:

```markdown
## Source Contract Boundary

`claim_kind`, the source contract matrix, and the surface gate decide whether source evidence may lower to runtime config. Effect relevance, guide importance, and archetype value do not bypass that chain.

`operator_summary.json` remains the normal apply authority. Source-contract reports are diagnostic only. Warnings are follow-up work, not runtime apply blockers.

Normal HSConfig output must not emit `Presume.json` or `Concede.json`.
```

- [ ] **Step 4: Update the skill reference**

Mirror the same section in `.agents/skills/hsconfig/references/guide-research-policy.md`.

- [ ] **Step 5: Run skill sync check**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: PASS if installed skill is already synced; FAIL if installed skill needs updating. If it fails, run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected after sync: PASS.

- [ ] **Step 6: Run docs test**

Run:

```powershell
python -m pytest -q tests/test_operator_docs_contract_policy.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/guide-research-policy.md tests/test_operator_docs_contract_policy.py
git commit -m "docs: sync skill source contract boundary"
```

---

### Task 6: Keep the Guardrail Runner Focused on This Boundary

**Files:**
- Modify: `scripts/check_contract_guardrails.py` only if required.
- Modify: `tests/test_check_contract_guardrails.py`

**Interfaces:**
- Consumes: `FOCUSED_CONTRACT_TESTS` from `scripts/check_contract_guardrails.py`.
- Produces: one fast developer command that proves the relevant guardrail set.

- [ ] **Step 1: Write or adjust the runner coverage test**

In `tests/test_check_contract_guardrails.py`, ensure this test exists or add it:

```python
def test_guardrail_runner_includes_source_contract_v2_boundary_tests():
    from scripts.check_contract_guardrails import FOCUSED_CONTRACT_TESTS

    expected = {
        "tests/test_source_claim_family_registry.py",
        "tests/test_contract_spine_sentinel.py",
        "tests/test_contract_spine_sentinel_cli.py",
        "tests/test_contract_spine_sentinel_docs.py",
        "tests/test_apply_authority_boundary.py",
        "tests/test_no_second_gate_contract.py",
        "tests/test_semantic_runtime_negative_boundaries.py",
        "tests/test_universal_wild_no_block_matrix.py",
        "tests/test_operator_docs_contract_policy.py",
        "tests/test_docs_active_path.py",
        "tests/test_claim_kind_runtime_contract.py",
        "tests/test_card_behavior_router.py",
        "tests/test_mechanic_support.py",
    }

    assert expected <= set(FOCUSED_CONTRACT_TESTS)
```

- [ ] **Step 2: Run the runner coverage test**

Run:

```powershell
python -m pytest -q tests/test_check_contract_guardrails.py::test_guardrail_runner_includes_source_contract_v2_boundary_tests
```

Expected: PASS if the runner already includes all tests; FAIL if one is missing.

- [ ] **Step 3: Update runner only if needed**

If the test fails, add the missing test path to `FOCUSED_CONTRACT_TESTS` in `scripts/check_contract_guardrails.py`. Do not add the full suite.

- [ ] **Step 4: Run the runner tests**

Run:

```powershell
python -m pytest -q tests/test_check_contract_guardrails.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/check_contract_guardrails.py tests/test_check_contract_guardrails.py
git commit -m "test: cover contract guardrail runner scope"
```

---

### Task 7: Final Verification and Push

**Files:**
- No direct file edits unless verification exposes a narrow failure.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: clean branch pushed to GitHub.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_semantic_runtime_negative_boundaries.py tests/test_source_contract_conformance.py tests/test_check_contract_guardrails.py
```

Expected: PASS.

- [ ] **Step 2: Run the contract guardrail command**

Run:

```powershell
python scripts\check_contract_guardrails.py
```

Expected output contains:

```text
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

- [ ] **Step 3: Run package-level smoke tests**

Run:

```powershell
python -m pytest -q tests/test_universal_wild_no_block_matrix.py tests/test_apply_gate.py tests/test_no_second_gate_contract.py
```

Expected: PASS.

- [ ] **Step 4: Inspect git status**

Run:

```powershell
git status --short --branch
```

Expected: branch has only the intended committed changes and no generated caches.

- [ ] **Step 5: Push**

Run:

```powershell
git push origin codex/hsconfig-contract-spine-guard-wave
```

Expected: push succeeds.

---

## Self-Review

- **Spec coverage:** The plan covers active research indexing, compact operator reference, false-lowering tests, conformance reference lock, skill text sync, guardrail runner scope, and final verification.
- **No second gate:** No task reads diagnostic reports from apply paths or changes apply permission. `operator_summary.json` remains the only normal apply authority.
- **No runtime surface expansion:** No task adds `Presume.json`, `Concede.json`, aggregate `CardBehavior.json`, replay logic, winrate logic, or post-run tuning.
- **No-block contract preserved:** New tests make warning-only and unsupported semantics visible or suppressed, not blocking.
- **Slimness:** The only likely new file outside docs/tests is optional and conditional; implementation should prefer tests/docs and existing modules.
- **Placeholders:** The plan contains concrete file paths, commands, and code snippets for each task.
