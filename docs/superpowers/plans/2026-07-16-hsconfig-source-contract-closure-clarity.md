# HSConfig Source Contract Closure Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's source/contract closure unmistakable: no default-only success, static semantics are surface-scoped, first-missing source actions are precise, and `SOURCE_BACKED_STRONG` remains honest without blocking valid deck config generation.

**Architecture:** Keep `reports/operator_summary.json` as the only runtime apply authority. Source-autopilot remains diagnostic preflight, source evidence policy classifies trust ceilings, and operator summary remains the runtime-package truth for default-only surfaces. The implementation adds only small fields/helpers/tests around existing modules.

**Tech Stack:** Python, pytest, HSConfig CLI, HearthRanger VisionAI CustomConfig JSON, existing `hsconfig` package modules.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not add new dependencies.
- Do not create replay, winrate, HSTuner, or post-game behavior in HSConfig.
- `operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation or apply gate.
- Any valid deck code should still produce a load-safe package when technically valid.
- `decklist_only`, stats, snippets, policy fallback, default runtime, and unsupported runtime hints must not promote `SOURCE_BACKED_STRONG`.
- Static semantics may close deterministic CardID/effect surfaces only when the claim matches that surface; static semantics must not prove mulligan, combo, targeting, or deck-gameplan posture by itself.
- Default-only runtime surfaces must be visible, not silent.
- Darkbishop Benedictus / `SW_448` must preserve `hero_power_transform` / Mind Spike effect semantics while staying out of opening-hand keeps unless an explicit mulligan source says to keep it.
- Normal HSConfig output must not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.

---

## File Structure

- Modify `src/hsconfig/source_evidence_policy.py`
  - Add explicit surface-scoped static semantics fields without turning static records into deck-strategy guide evidence.
- Modify `src/hsconfig/source_autopilot.py`
  - Clarify preflight default-only status.
  - Add more specific first-missing source actions.
  - Recognize static surface support only for supported CardID/effect surfaces.
- Modify `src/hsconfig/operator_summary.py` only if tests show the existing static semantics wording conflicts with operator closure fields.
  - Keep changes minimal and do not alter runtime apply policy.
- Modify `tests/test_source_evidence_policy.py`
  - Freeze static-semantics trust ceiling and non-promotion behavior.
- Modify `tests/test_lean_source_backed_strong_autopilot.py`
  - Cover preflight default-only wording and source-action specificity.
- Modify `tests/test_source_autopilot.py`
  - Add focused report-shape and action-map regressions.
- Modify `tests/test_universal_wild_no_block_matrix.py`
  - Ensure all representative decks stay load-safe, no-default-only, and non-blocking.
- Modify `docs/operator/source-backed-strong-closure.md`
  - Clarify static semantics and source-autopilot default-only wording.
- Modify `.agents/skills/hsconfig/SKILL.md`
  - Keep operator guidance in sync with the docs.
- Run `scripts/sync_installed_skill.py` after skill edits.

---

### Task 1: Freeze Static-Semantics Surface Scope

**Files:**
- Modify: `tests/test_source_evidence_policy.py`
- Modify: `src/hsconfig/source_evidence_policy.py`
- Modify: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**
- Consumes: `classify_source_evidence(record: Mapping[str, Any], *, deck_name: str, current_date: str | date | None) -> dict[str, Any]`
- Produces: additional classification fields:
  - `static_runtime_surface_eligible: bool`
  - `static_runtime_surface_scope: str`
  - `static_runtime_surface_limit: str`

- [ ] **Step 1: Add failing source-policy tests**

Append these tests to `tests/test_source_evidence_policy.py`:

```python
from datetime import date

from hsconfig.source_evidence_policy import classify_source_evidence


def test_official_static_semantics_can_support_cardid_but_not_deck_strategy():
    record = {
        "source_family": "official_static_semantics",
        "source_type": "official_static_semantics",
        "source_visibility": "full_text",
        "publication_year": 2026,
        "source_record_strength": "candidate_strong",
        "deck_match_scope": "deck_or_archetype_matched",
        "deck_match": {
            "deck_name": "ShadowPriest",
            "matched_card_ids": ["SW_448"],
        },
        "claim_kind": "hero_power_transform",
        "cards": ["SW_448"],
        "normalized_text": (
            "Darkbishop Benedictus has Start of Game text that enters "
            "Shadowform when the deck's spells are all Shadow."
        ),
    }

    result = classify_source_evidence(
        record,
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 16),
    )

    assert result["trust_ceiling"] == "static_semantics_only"
    assert result["strong_promotion_eligible"] is False
    assert result["static_runtime_surface_eligible"] is True
    assert result["static_runtime_surface_scope"] == "cardid_effect"
    assert result["static_runtime_surface_limit"] == (
        "static_semantics_supports_cardid_effects_only"
    )
    assert "static_semantics_not_deck_strategy" in result["promotion_blockers"]


def test_static_semantics_never_promotes_mulligan_claims():
    record = {
        "source_family": "official_static_semantics",
        "source_type": "official_static_semantics",
        "source_visibility": "full_text",
        "publication_year": 2026,
        "source_record_strength": "candidate_strong",
        "deck_match_scope": "deck_or_archetype_matched",
        "claim_kind": "mulligan_keep",
        "cards": ["SW_448"],
    }

    result = classify_source_evidence(
        record,
        deck_name="ShadowPriest",
        current_date="2026-07-16",
    )

    assert result["strong_promotion_eligible"] is False
    assert result["static_runtime_surface_eligible"] is False
    assert result["static_runtime_surface_scope"] == "not_runtime_surface_static"
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_evidence_policy.py -q
```

Expected before implementation:

```text
FAILED ... KeyError: 'static_runtime_surface_eligible'
```

- [ ] **Step 3: Implement the static-scope fields**

In `src/hsconfig/source_evidence_policy.py`, add this helper near `_trust_ceiling`:

```python
STATIC_CARDID_EFFECT_CLAIM_KINDS = {
    "hero_power_transform",
    "mechanic_usage",
    "card_role",
}


def _static_runtime_surface_scope(record: Mapping[str, Any], family: str) -> dict[str, Any]:
    claim_kind = _text(record.get("claim_kind", "")).lower()
    if family not in STATIC_FAMILIES:
        return {
            "static_runtime_surface_eligible": False,
            "static_runtime_surface_scope": "not_static_semantics",
            "static_runtime_surface_limit": "",
        }
    if claim_kind in STATIC_CARDID_EFFECT_CLAIM_KINDS:
        return {
            "static_runtime_surface_eligible": True,
            "static_runtime_surface_scope": "cardid_effect",
            "static_runtime_surface_limit": "static_semantics_supports_cardid_effects_only",
        }
    return {
        "static_runtime_surface_eligible": False,
        "static_runtime_surface_scope": "not_runtime_surface_static",
        "static_runtime_surface_limit": "static_semantics_does_not_prove_strategy_surface",
    }
```

Then in `classify_source_evidence(...)`, before `result.update(...)`, add:

```python
    static_scope = _static_runtime_surface_scope(record, family)
```

And include the helper output in `result.update(...)`:

```python
            **static_scope,
```

- [ ] **Step 4: Run Task 1 tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_evidence_policy.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Update docs for the static-scope decision**

In `docs/operator/source-backed-strong-closure.md`, replace the static semantics bullet under `SOURCE_BACKED_STRONG Contract` with this wording:

```markdown
- explicit `official_static_semantics` may close deterministic CardID/effect surfaces such as `hero_power_transform`, but it does not prove deck-specific mulligan, combo, targeting, or gameplan posture by itself
```

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add src/hsconfig/source_evidence_policy.py tests/test_source_evidence_policy.py docs/operator/source-backed-strong-closure.md
git commit -m "clarify static source surface scope"
```

---

### Task 2: Make Source-Autopilot Default-Only Status Explicit

**Files:**
- Modify: `tests/test_lean_source_backed_strong_autopilot.py`
- Modify: `tests/test_source_autopilot.py`
- Modify: `src/hsconfig/source_autopilot.py`
- Modify: `docs/operator/source-backed-strong-closure.md`

**Interfaces:**
- Consumes: `build_source_autopilot_bundle(...) -> dict[str, Any]`
- Produces report fields:
  - `runtime_apply_authority: "reports/operator_summary.json"`
  - `default_only_runtime_surfaces: []`
  - `default_only_runtime_surface_status: "not_evaluated_in_source_preflight"`
  - `default_only_runtime_surfaces_scope: "source_preflight_not_runtime_proof"`

- [ ] **Step 1: Add failing tests for preflight default-only scope**

Append to `tests/test_lean_source_backed_strong_autopilot.py`:

```python
def test_source_autopilot_default_only_fields_are_preflight_not_runtime_authority():
    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[_guide_record()],
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]

    assert report["runtime_apply_authority"] == "reports/operator_summary.json"
    assert report["default_only_runtime_surfaces"] == []
    assert report["default_only_runtime_surface_status"] == (
        "not_evaluated_in_source_preflight"
    )
    assert report["default_only_runtime_surfaces_scope"] == (
        "source_preflight_not_runtime_proof"
    )
    assert report["source_backed_strong_closure"]["diagnostic_only"] is True
```

- [ ] **Step 2: Run the new test and confirm it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_lean_source_backed_strong_autopilot.py::test_source_autopilot_default_only_fields_are_preflight_not_runtime_authority -q
```

Expected before implementation:

```text
FAILED ... KeyError: 'default_only_runtime_surface_status'
```

- [ ] **Step 3: Add report fields in source-autopilot**

In `src/hsconfig/source_autopilot.py`, in `_build_report(...)`, update the returned report near `runtime_apply_authority` and `default_only_runtime_surfaces`:

```python
        "runtime_apply_authority": "reports/operator_summary.json",
        "default_only_runtime_surfaces": [],
        "default_only_runtime_surface_status": "not_evaluated_in_source_preflight",
        "default_only_runtime_surfaces_scope": "source_preflight_not_runtime_proof",
```

In `_source_backed_strong_closure(...)`, keep:

```python
        "default_only_runtime_surface_status": "not_evaluated_in_source_preflight",
```

and add:

```python
        "default_only_runtime_surfaces_scope": "source_preflight_not_runtime_proof",
```

- [ ] **Step 4: Run Task 2 tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_lean_source_backed_strong_autopilot.py tests/test_source_autopilot.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Update docs for preflight-vs-runtime truth**

In `docs/operator/source-backed-strong-closure.md`, after the paragraph about `source_autopilot_report.json`, add:

```markdown
`source_autopilot_report.json.default_only_runtime_surfaces` is a source-preflight diagnostic, not runtime-package proof. Runtime default-only truth is read from `reports/operator_summary.json`; source preflight exposes `default_only_runtime_surface_status=not_evaluated_in_source_preflight` so this boundary is machine-readable.
```

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add src/hsconfig/source_autopilot.py tests/test_lean_source_backed_strong_autopilot.py tests/test_source_autopilot.py docs/operator/source-backed-strong-closure.md
git commit -m "clarify source autopilot default-only scope"
```

---

### Task 3: Make First-Missing Source Actions Specific

**Files:**
- Modify: `tests/test_source_autopilot.py`
- Modify: `tests/test_lean_source_backed_strong_autopilot.py`
- Modify: `src/hsconfig/source_autopilot.py`

**Interfaces:**
- Consumes:
  - `_first_missing_source_action_by_card(deck_identity, evidence_rows, *, current_date) -> dict[str, str]`
  - `_first_missing_source_action_by_surface(evidence_rows, *, current_date, summary) -> dict[str, str]`
- Produces:
  - `add_exact_mulligan_keep_or_discard_source`
  - `add_card_specific_targeting_source`
  - `add_combo_sequence_source`
  - `add_runtime_surface_lowering_source`
  - `add_current_card_specific_runtime_source`

- [ ] **Step 1: Add failing tests for action specificity**

Append to `tests/test_source_autopilot.py`:

```python
def test_source_autopilot_names_targeting_missing_action():
    deck_identity = {
        "deck_name": "TargetDeck",
        "cards": [
            {"card_id": "CARD_001", "name": "Face Spell", "cost": 1, "count": 2},
        ],
    }
    bundle = build_source_autopilot_bundle(
        deck_name="TargetDeck",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/target-deck",
                "source_title": "Target Deck Current Guide",
                "source_family": "guide",
                "source_visibility": "snippet_only",
                "publication_year": 2026,
                "deck_match": {
                    "deck_name": "TargetDeck",
                    "matched_card_ids": ["CARD_001"],
                },
                "claims": [
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_001"],
                        "stance": "prefer_enemy_hero",
                    }
                ],
            }
        ],
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]

    assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["first_missing_source_action_by_card"]["CARD_001"] == (
        "add_card_specific_targeting_source"
    )
    assert report["first_missing_source_action_by_surface"]["CardID.json"] == (
        "add_card_specific_targeting_source"
    )


def test_source_autopilot_names_combo_sequence_missing_action():
    deck_identity = {
        "deck_name": "ComboDeck",
        "cards": [
            {"card_id": "CARD_001", "name": "Combo Piece", "cost": 1, "count": 2},
        ],
    }
    bundle = build_source_autopilot_bundle(
        deck_name="ComboDeck",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/combo-deck",
                "source_title": "Combo Deck Current Guide",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2026,
                "deck_match": {
                    "deck_name": "ComboDeck",
                    "matched_card_ids": ["CARD_001"],
                },
                "deck_match_scope": "deck_or_archetype_matched",
                "normalized_text": "Combo Deck Current Guide. " * 20,
                "claims": [
                    {
                        "claim_kind": "combo_sequence",
                        "cards": ["CARD_001"],
                        "stance": "assemble_combo",
                    }
                ],
            }
        ],
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]

    assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["first_missing_source_action_by_card"]["CARD_001"] == (
        "add_combo_sequence_source"
    )
    assert report["first_missing_source_action_by_surface"]["Combo.json"] == (
        "add_combo_sequence_source"
    )
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py::test_source_autopilot_names_targeting_missing_action tests/test_source_autopilot.py::test_source_autopilot_names_combo_sequence_missing_action -q
```

Expected before implementation:

```text
FAILED ... AssertionError: 'add_current_deck_guide_or_mulligan_guide' != ...
```

- [ ] **Step 3: Add a claim-kind-to-source-action helper**

In `src/hsconfig/source_autopilot.py`, near `_action_from_profile_gap(...)`, add:

```python
def _source_action_for_claim_kind(claim_kind: str) -> str:
    normalized = _text(claim_kind).lower()
    if normalized in {"mulligan_keep", "mulligan_discard"}:
        return "add_exact_mulligan_keep_or_discard_source"
    if normalized == "targeting_rule":
        return "add_card_specific_targeting_source"
    if normalized == "combo_sequence":
        return "add_combo_sequence_source"
    if normalized in {"discover_choice", "choose_one_choice"}:
        return "add_generated_entity_or_option_identity_source"
    if normalized in {"hero_power_transform", "card_role", "mechanic_usage"}:
        return "add_current_card_specific_runtime_source"
    return "add_runtime_surface_lowering_source"
```

- [ ] **Step 4: Use the helper in card missing actions**

In `_first_missing_source_action_by_card(...)`, replace the generic fallback:

```python
            by_card[card_id] = "add_current_deck_guide_or_mulligan_guide"
```

with:

```python
            card_claim_kinds = [
                _text(row.get("claim_kind", ""))
                for row in evidence_rows
                if card_id in {_text(value) for value in _as_list(row.get("cards", []))}
            ]
            by_card[card_id] = (
                _source_action_for_claim_kind(card_claim_kinds[0])
                if card_claim_kinds
                else "add_current_card_specific_runtime_source"
            )
```

- [ ] **Step 5: Use the helper in surface missing actions**

In `_first_missing_source_action_by_surface(...)`, when a surface is not strong, compute a claim-kind action before falling back:

```python
        surface_claim_kinds = [
            _text(row.get("claim_kind", ""))
            for row in evidence_rows
            if surface in _runtime_surfaces_for_row(row)
        ]
        if surface_claim_kinds:
            by_surface[_display_surface(surface)] = _source_action_for_claim_kind(
                surface_claim_kinds[0]
            )
        elif surface == "mulligan":
            by_surface[_display_surface(surface)] = "add_exact_mulligan_keep_or_discard_source"
        elif first_missing and first_missing != "none":
            by_surface[_display_surface(surface)] = first_missing
        else:
            by_surface[_display_surface(surface)] = "add_current_card_specific_runtime_source"
```

If the current loop already uses display-surface keys, keep that local key style and only replace the assigned action values.

- [ ] **Step 6: Run Task 3 tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py tests/test_lean_source_backed_strong_autopilot.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add src/hsconfig/source_autopilot.py tests/test_source_autopilot.py tests/test_lean_source_backed_strong_autopilot.py
git commit -m "refine source autopilot missing actions"
```

---

### Task 4: Sync Operator Docs And Installed Skill

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Test: `tests/test_skill_sync.py`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: current docs and `.agents/skills/hsconfig/SKILL.md`
- Produces: installed skill sync through `scripts/sync_installed_skill.py`

- [ ] **Step 1: Add/adjust docs text**

In `docs/operator/guide-research-policy.md`, add this paragraph near the source-depth / strong-promotion section:

```markdown
Static semantics are surface-scoped. Official or HearthstoneJSON static records may support deterministic CardID/effect rows such as hero-power transforms, but they do not prove deck-specific mulligan, combo, targeting, or gameplan posture without public guide evidence. Source-autopilot is preflight only; runtime default-only truth is read from `reports/operator_summary.json`.
```

In `.agents/skills/hsconfig/SKILL.md`, ensure these two bullets are present in the source-depth section:

```markdown
- Static semantics are surface-scoped: they may support deterministic CardID/effect rows, but they do not prove deck-specific mulligan, combo, targeting, or gameplan posture by themselves.
- `source_autopilot_report.json.default_only_runtime_surfaces` is preflight diagnostic visibility; runtime default-only truth and apply permission remain in `reports/operator_summary.json`.
```

- [ ] **Step 2: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
```

Expected:

```text
Synced HSConfig skill to C:\Users\darbo\.codex\skills\hsconfig
```

If the script prints an already-current message, that is also acceptable.

- [ ] **Step 3: Run docs and skill tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_sync.py tests/test_skill_files.py tests/test_docs_active_path.py -q
python scripts/sync_installed_skill.py --check
```

Expected:

```text
passed
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 4: Commit Task 4**

Run:

```powershell
git add docs/operator/source-backed-strong-closure.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md C:/Users/darbo/.codex/skills/hsconfig/SKILL.md
git commit -m "sync source contract closure guidance"
```

If `C:/Users/darbo/.codex/skills/hsconfig/SKILL.md` is outside the repository and cannot be staged, commit only repo files and still keep the installed skill synced.

---

### Task 5: Final Verification And Matrix Proof

**Files:**
- Test only.
- No source files should change in this task except unavoidable installed-skill sync already handled in Task 4.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified branch ready for push/PR or fast-forward.

- [ ] **Step 1: Run targeted closure tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest `
  tests/test_source_evidence_policy.py `
  tests/test_lean_source_backed_strong_autopilot.py `
  tests/test_source_autopilot.py `
  tests/test_universal_wild_no_block_matrix.py `
  tests/test_shadowpriest_e2e.py `
  tests/test_claim_kind_runtime_contract.py `
  tests/test_skill_sync.py `
  tests/test_skill_files.py `
  -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run broader suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Confirm no hidden generated artifacts**

Run:

```powershell
git status --short
```

Expected: only intentional source, test, and docs changes are listed before commit; after final commit, output is empty.

- [ ] **Step 4: Commit final verification metadata only if needed**

If no files changed during verification, do not create a commit.

If docs or generated skill files changed during verification, run:

```powershell
git add <changed-files>
git commit -m "verify source contract closure clarity"
```

- [ ] **Step 5: Push branch**

Run:

```powershell
git push
```

Expected:

```text
Everything up-to-date
```

or a successful push of the current branch.

---

## Self-Review

**Spec coverage:** The plan covers all three recommendations: static semantics rule, source-autopilot default-only clarity, and more specific first-missing source actions. It also preserves no-block valid config generation, `operator_summary.json` apply authority, Darkbishop effect-not-mulligan behavior, docs, installed skill sync, and matrix proof.

**Placeholder scan:** No task uses TBD/TODO/fill-later wording. Every code step gives exact test snippets, helper snippets, command lines, and expected results.

**Type consistency:** New fields are consistently named:
- `static_runtime_surface_eligible`
- `static_runtime_surface_scope`
- `static_runtime_surface_limit`
- `default_only_runtime_surface_status`
- `default_only_runtime_surfaces_scope`

**Scope check:** This is one coherent source-contract closure plan. It deliberately excludes replay analysis, winrate analysis, runtime tuning, HSTuner, and broad research harvesting.
