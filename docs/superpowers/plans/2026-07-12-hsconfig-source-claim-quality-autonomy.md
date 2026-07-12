# HSConfig Source Claim Quality Autonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve HSConfig's deck-only autonomy by making every card land in a visible source/contract lane while preserving the current source-contract spine and no-block runtime apply behavior.

**Architecture:** Keep the existing spine: source documents -> `claim_kind` -> policy matrix -> surface gate -> builder/router -> runtime JSON or diagnostic report. Do not introduce a second apply gate; `reports/operator_summary.json` remains the only normal runtime apply authority. Add compact source-quality visibility and stronger static/source claim fallback inside existing HSConfig reports rather than creating a new HSTuner-like workflow.

**Tech Stack:** Python 3.11, pytest, existing `hsconfig` package under `src/`, existing JSON report artifacts, existing HearthRanger VisionAI runtime surfaces.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner: no replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning.
- Generated runtime packages belong under `outputs/` and are ignored by git.
- Preserve exact deck and CardID identity.
- Preserve full GlobalValues key profiling.
- Every card must be visible in the gameplan/source contract; source weakness must not block valid runtime package creation.
- Runtime apply authority remains `reports/operator_summary.json`.
- `reports/source_contract_audit.json`, `contract_spine_rows`, and `contract-doctor` stay diagnostic-only.
- `globalvalue_numeric_tuning` remains report-visible but Step1 runtime-evidence-required.
- Mulligan runtime rows require explicit `claim_kind == "mulligan_keep"` or `claim_kind == "mulligan_discard"`.
- Start-of-game, deckbuilding, hero-power-transform, and card-importance claims must not become opening-hand keeps without an explicit mulligan claim.
- No broad wildcard claim kinds such as `globalvalue_*`.
- No new runtime hard block except invalid JSON, missing minimal runtime files, unreadable package, unwritable target, or apply hash/guard failure.

---

## File Structure

Modify existing focused modules instead of adding broad orchestration:

- `src/hsconfig/guide_claim_builder.py`: strengthen source/static claim creation and coverage lanes.
- `src/hsconfig/source_claim_gap_report.py`: add compact per-card closure details that show each card's first missing link and next useful claim kind.
- `src/hsconfig/operator_summary.py`: surface the new source-claim quality summary without changing apply authority.
- `src/hsconfig/source_document_model.py`: only touch if a source-readiness helper is needed; do not add new claim kinds in this wave unless a task explicitly says so.
- `docs/operator/guide-research-policy.md`: document the source-quality lanes and no-block rule.
- `.agents/skills/hsconfig/SKILL.md`: keep the installed skill aligned with the operator path.

Test and fixture files:

- `tests/test_source_claim_quality_autonomy.py`: new focused tests for card closure, non-blocking source debt, and operator summary visibility.
- `tests/test_shadowpriest_e2e.py`: extend only for Darkbishop/source-quality regression.
- `tests/test_universal_wild_no_block_matrix.py`: extend only for matrix-level non-blocking behavior.
- `tests/test_source_contract_spine_freeze.py`: keep as spine freeze; do not weaken expectations.

No new dependencies are required.

---

### Task 1: Land And Freeze The Current Source-Contract Spine Baseline

**Files:**
- Modify: none
- Test: existing source-contract and no-block suites

**Interfaces:**
- Consumes: current pushed branch `codex/hsconfig-source-contract-spine-freeze`
- Produces: main baseline where the contract spine is current before source-quality work starts

- [ ] **Step 1: Verify branch state**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## codex/hsconfig-source-contract-spine-freeze...origin/codex/hsconfig-source-contract-spine-freeze
```

- [ ] **Step 2: Run source-contract baseline tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_contract_spine_freeze.py tests/test_source_contract_conformance.py tests/test_apply_authority_boundary.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Merge branch to main using fast-forward only**

Run:

```powershell
git fetch origin
git checkout main
git merge --ff-only origin/codex/hsconfig-source-contract-spine-freeze
```

Expected:

```text
Updating ...
Fast-forward
```

- [ ] **Step 4: Push main**

Run:

```powershell
git push origin main
```

Expected:

```text
main -> main
```

- [ ] **Step 5: Create new implementation branch**

Run:

```powershell
git checkout -b codex/hsconfig-source-claim-quality-autonomy
```

Expected:

```text
Switched to a new branch 'codex/hsconfig-source-claim-quality-autonomy'
```

- [ ] **Step 6: Commit state**

No commit is required for this task if the fast-forward merge and branch creation are the only actions.

---

### Task 2: Add Source-Claim Quality Summary To Existing Gap Report

**Files:**
- Modify: `src/hsconfig/source_claim_gap_report.py`
- Test: `tests/test_source_claim_quality_autonomy.py`

**Interfaces:**
- Consumes: existing `build_source_claim_gap_report(...) -> dict[str, Any]`
- Produces: report fields:
  - `summary.source_quality_lane_counts: dict[str, int]`
  - `summary.cards_with_generic_low_confidence: int`
  - `summary.cards_with_contract_gap: int`
  - `summary.next_claim_kind_counts: dict[str, int]`
  - each card row has `source_quality_lane`, `recommended_next_claim_kind`, and `recommended_next_source_action`

- [ ] **Step 1: Write failing test for source-quality lane summary**

Create `tests/test_source_claim_quality_autonomy.py` with:

```python
from hsconfig.source_claim_gap_report import build_source_claim_gap_report


def test_source_claim_gap_report_exposes_quality_lanes_for_every_card():
    report = build_source_claim_gap_report(
        deck_cards=[
            {"card_id": "A", "name": "Guide Card"},
            {"card_id": "B", "name": "Static Card"},
            {"card_id": "C", "name": "Thin Card"},
        ],
        claim_coverage_report={
            "card_rows": {
                "A": {
                    "source_depth_lane": "guide_backed",
                    "claim_kinds": ["mulligan_keep"],
                },
                "B": {
                    "source_depth_lane": "source_backed_static_semantics",
                    "claim_kinds": ["mechanic_usage"],
                },
                "C": {
                    "source_depth_lane": "generic_low_confidence",
                    "claim_kinds": [],
                },
            }
        },
        source_contract_audit={
            "card_rows": {
                "A": {"first_missing_link": "closed", "runtime_surfaces": ["Mulligan.json"]},
                "B": {"first_missing_link": "closed", "runtime_surfaces": ["B.json"]},
                "C": {"first_missing_link": "missing_source_claim", "runtime_surfaces": []},
            }
        },
    )

    assert report["summary"]["source_quality_lane_counts"] == {
        "generic_low_confidence": 1,
        "guide_backed": 1,
        "source_backed_static_semantics": 1,
    }
    assert report["summary"]["cards_with_generic_low_confidence"] == 1
    assert report["summary"]["cards_with_contract_gap"] == 0
    assert report["summary"]["next_claim_kind_counts"] == {"card_role": 1}
    assert report["card_rows"]["C"]["source_quality_lane"] == "generic_low_confidence"
    assert report["card_rows"]["C"]["recommended_next_claim_kind"] == "card_role"
    assert report["card_rows"]["C"]["recommended_next_source_action"] == (
        "add a card-specific guide claim or source-backed static semantic claim"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_quality_autonomy.py::test_source_claim_gap_report_exposes_quality_lanes_for_every_card -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Implement minimal report fields**

Modify `src/hsconfig/source_claim_gap_report.py`:

```python
SOURCE_QUALITY_LANES = {
    "guide_backed",
    "source_backed_static_semantics",
    "archetype_inferred",
    "explicit_low_confidence",
    "generic_low_confidence",
    "contract_gap",
}


def _source_quality_lane(row: dict[str, Any]) -> str:
    lane = str(row.get("source_depth_lane", "") or row.get("readiness_lane", ""))
    if lane in SOURCE_QUALITY_LANES:
        return lane
    first_missing_link = str(row.get("first_missing_link", ""))
    if first_missing_link in {"missing_source_claim", "missing_card_specific_source"}:
        return "generic_low_confidence"
    if first_missing_link in {"unsupported_claim_kind", "surface_gate_rejected"}:
        return "contract_gap"
    return "archetype_inferred"


def _recommended_next_claim_kind(first_missing_link: str, lane: str) -> str:
    if first_missing_link in {"missing_source_claim", "missing_card_specific_source"}:
        return "card_role"
    if first_missing_link == "missing_targeting_claim":
        return "targeting_rule"
    if first_missing_link == "missing_mulligan_claim":
        return "mulligan_keep"
    if first_missing_link == "missing_combo_sequence":
        return "combo_sequence"
    if lane == "generic_low_confidence":
        return "card_role"
    return "none"


def _recommended_next_source_action(first_missing_link: str, next_claim_kind: str) -> str:
    if next_claim_kind == "none":
        return "none"
    if next_claim_kind == "mulligan_keep":
        return "add an explicit opening-hand mulligan source claim"
    if next_claim_kind == "targeting_rule":
        return "add a card-specific target or usage claim"
    if next_claim_kind == "combo_sequence":
        return "add an ordered combo sequence with timing fields"
    return "add a card-specific guide claim or source-backed static semantic claim"
```

Integrate these helpers into `build_source_claim_gap_report` where card rows and summary are assembled. Keep existing keys unchanged.

- [ ] **Step 4: Run focused test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_quality_autonomy.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/hsconfig/source_claim_gap_report.py tests/test_source_claim_quality_autonomy.py
git commit -m "feat: expose source claim quality lanes"
```

---

### Task 3: Keep Darkbishop-Style Effect Claims Out Of Mulligan With Explicit Source-Quality Regression

**Files:**
- Modify: `tests/test_source_claim_quality_autonomy.py`
- Modify: `src/hsconfig/guide_claim_builder.py` only if the test exposes a regression
- Test: `tests/test_source_claim_quality_autonomy.py`

**Interfaces:**
- Consumes: `build_guide_claim_bundle(...)`
- Produces: regression that `hero_power_transform` and start-of-game effect claims are preserved as contract/CardID evidence but never become `mulligan_keep`

- [ ] **Step 1: Add failing or guarding test**

Append to `tests/test_source_claim_quality_autonomy.py`:

```python
from hsconfig.guide_claim_builder import build_guide_claim_bundle


def test_start_of_game_hero_power_effect_does_not_infer_mulligan_keep():
    result = build_guide_claim_bundle(
        deck_cards=[
            {
                "id": "SW_448",
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
            }
        ],
        source_documents=[
            {
                "source_url": "local://shadowpriest-test",
                "source_title": "ShadowPriest effect source",
                "source_family": "card_text",
                "retrieved_at": "2026-07-12T00:00:00Z",
                "deck_name": "ShadowPriest",
                "claims": [
                    {
                        "claim_kind": "hero_power_transform",
                        "cards": ["SW_448"],
                        "evidence_text_short": "Start of Game changes the Hero Power.",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
    )

    claims = result.claim_bundle["claims"]
    assert any(claim["claim_kind"] == "hero_power_transform" for claim in claims)
    assert not any(
        claim["claim_kind"] == "mulligan_keep" and "SW_448" in claim.get("cards", [])
        for claim in claims
    )
```

- [ ] **Step 2: Run focused test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_quality_autonomy.py::test_start_of_game_hero_power_effect_does_not_infer_mulligan_keep -q
```

Expected:

```text
passed
```

If it fails because the function signature differs, adapt only the test call to the actual `build_guide_claim_bundle` signature. If it fails because `mulligan_keep` is emitted, patch `guide_claim_builder.py` so free-text and hero-power-transform claims do not infer mulligan keeps.

- [ ] **Step 3: Commit**

Run:

```powershell
git add src/hsconfig/guide_claim_builder.py tests/test_source_claim_quality_autonomy.py
git commit -m "test: guard start-of-game effects from mulligan inference"
```

---

### Task 4: Surface Source-Quality Summary In Operator Summary Without Adding An Apply Gate

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `tests/test_source_claim_quality_autonomy.py`

**Interfaces:**
- Consumes: `source_claim_gap_report.summary.source_quality_lane_counts`
- Produces: `operator_summary["source_claim_quality_summary"]`

- [ ] **Step 1: Add failing test**

Append to `tests/test_source_claim_quality_autonomy.py`:

```python
from hsconfig.operator_summary import build_operator_summary


def test_operator_summary_exposes_source_quality_without_apply_block():
    operator = build_operator_summary(
        validation_report={
            "valid": True,
            "errors": [],
            "warnings": [],
            "summary": {},
        },
        config_readiness_report={
            "summary": {
                "cards_total": 3,
                "cards_ready": 3,
                "cards_missing": 0,
            },
            "card_rows": {},
        },
        source_claim_gap_report={
            "summary": {
                "source_quality_lane_counts": {
                    "guide_backed": 1,
                    "source_backed_static_semantics": 1,
                    "generic_low_confidence": 1,
                },
                "cards_with_generic_low_confidence": 1,
                "cards_with_contract_gap": 0,
                "next_claim_kind_counts": {"card_role": 1},
            }
        },
    )

    assert operator["source_claim_quality_summary"] == {
        "source_quality_lane_counts": {
            "generic_low_confidence": 1,
            "guide_backed": 1,
            "source_backed_static_semantics": 1,
        },
        "cards_with_generic_low_confidence": 1,
        "cards_with_contract_gap": 0,
        "next_claim_kind_counts": {"card_role": 1},
        "non_blocking": True,
    }
    assert operator["runtime_apply_contract"]["apply_authority"] == "reports/operator_summary.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_quality_autonomy.py::test_operator_summary_exposes_source_quality_without_apply_block -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Add operator summary helper**

Modify `src/hsconfig/operator_summary.py`:

```python
def _source_claim_quality_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    lane_counts = summary.get("source_quality_lane_counts", {})
    if not isinstance(lane_counts, dict):
        lane_counts = {}
    next_claim_kind_counts = summary.get("next_claim_kind_counts", {})
    if not isinstance(next_claim_kind_counts, dict):
        next_claim_kind_counts = {}
    return {
        "source_quality_lane_counts": dict(sorted(lane_counts.items())),
        "cards_with_generic_low_confidence": _int_value(
            summary.get("cards_with_generic_low_confidence", 0)
        ),
        "cards_with_contract_gap": _int_value(summary.get("cards_with_contract_gap", 0)),
        "next_claim_kind_counts": dict(sorted(next_claim_kind_counts.items())),
        "non_blocking": True,
    }
```

Add the helper output to the dict returned by `build_operator_summary`:

```python
"source_claim_quality_summary": _source_claim_quality_summary(source_claim_gap_report),
```

Do not reference `source_claim_quality_summary` from `_technical_status`, `_next_action_and_policy`, or runtime apply hard-block logic.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_quality_autonomy.py tests/test_operator_summary.py tests/test_apply_authority_boundary.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/hsconfig/operator_summary.py tests/test_source_claim_quality_autonomy.py
git commit -m "feat: summarize source claim quality in operator report"
```

---

### Task 5: Strengthen Static Source Fallback For Common Hearthstone Semantics

**Files:**
- Modify: `src/hsconfig/guide_claim_builder.py`
- Test: `tests/test_source_claim_quality_autonomy.py`

**Interfaces:**
- Consumes: deck card metadata with `id`, `card_id`, `name`, and `text`
- Produces: static source claims with `claim_readiness == "source_backed_static_semantics"` for deterministic semantics

- [ ] **Step 1: Add failing static semantic test**

Append to `tests/test_source_claim_quality_autonomy.py`:

```python
def test_static_semantics_adds_visible_claims_for_common_mechanics():
    result = build_guide_claim_bundle(
        deck_cards=[
            {
                "id": "DISCOVER_CARD",
                "card_id": "DISCOVER_CARD",
                "name": "Discover Card",
                "text": "Discover a spell.",
            },
            {
                "id": "SILENCE_CARD",
                "card_id": "SILENCE_CARD",
                "name": "Silence Card",
                "text": "Silence a minion.",
            },
            {
                "id": "WEAPON_CARD",
                "card_id": "WEAPON_CARD",
                "name": "Weapon Card",
                "text": "Equip a 3/2 weapon.",
            },
        ],
        source_documents=[],
    )

    claims = result.claim_bundle["claims"]
    by_card = {
        card_id: [
            claim
            for claim in claims
            if card_id in claim.get("cards", [])
            and claim.get("claim_readiness") == "source_backed_static_semantics"
        ]
        for card_id in ["DISCOVER_CARD", "SILENCE_CARD", "WEAPON_CARD"]
    }

    assert any(claim["claim_kind"] == "discover_choice" for claim in by_card["DISCOVER_CARD"])
    assert any(claim["claim_kind"] == "targeting_rule" for claim in by_card["SILENCE_CARD"])
    assert any(claim["claim_kind"] == "mechanic_usage" for claim in by_card["WEAPON_CARD"])
```

- [ ] **Step 2: Run test to verify it fails or guards current behavior**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_quality_autonomy.py::test_static_semantics_adds_visible_claims_for_common_mechanics -q
```

Expected:

```text
FAILED
```

If the test already passes, keep it as regression coverage and skip implementation.

- [ ] **Step 3: Extend static semantic detection narrowly**

Modify `_static_semantic_claims`, `_static_mechanic_usage_families`, or `_static_claim` in `src/hsconfig/guide_claim_builder.py` so deterministic card text creates source-backed static claims:

```python
STATIC_TEXT_CLAIM_RULES = (
    ("discover", "discover_choice", "discover"),
    ("choose one", "choose_one_choice", "choose_one"),
    ("silence", "targeting_rule", "silence"),
    ("destroy", "targeting_rule", "destroy"),
    ("transform", "targeting_rule", "transform"),
    ("equip", "mechanic_usage", "weapon"),
    ("weapon", "mechanic_usage", "weapon"),
    ("hero power", "hero_power_transform", "hero_power"),
)
```

Each emitted static claim must include:

```python
{
    "claim_kind": claim_kind,
    "cards": [card_id],
    "claim_readiness": "source_backed_static_semantics",
    "source_confidence": "medium",
    "evidence_text_short": f"Static card text contains {keyword}.",
    "mechanic_family": mechanic_family,
}
```

Do not create `mulligan_keep` from these rules.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_quality_autonomy.py tests/test_guide_claim_builder.py tests/test_semantic_runtime_negative_boundaries.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/hsconfig/guide_claim_builder.py tests/test_source_claim_quality_autonomy.py
git commit -m "feat: enrich static source claims for common mechanics"
```

---

### Task 6: Preserve No-Block Behavior Across Representative Wild Decks

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: source modules only if the test exposes a runtime block regression

**Interfaces:**
- Consumes: existing representative deck matrix and `hsconfig configure`/prepare path
- Produces: regression proof that source debt is warning-only and valid decks remain apply-ready or warning-ready

- [ ] **Step 1: Add matrix assertions for source-quality summary**

Extend `tests/test_universal_wild_no_block_matrix.py` in the existing matrix test after loading `operator`:

```python
source_quality = operator["source_claim_quality_summary"]
assert source_quality["non_blocking"] is True
assert isinstance(source_quality["source_quality_lane_counts"], dict)
assert operator["next_action"] in {
    "READY_TO_APPLY_OR_HANDOFF",
    "READY_TO_APPLY_WITH_WARNINGS",
}
assert operator["runtime_apply_contract"]["apply_authority"] == "reports/operator_summary.json"
```

- [ ] **Step 2: Run matrix test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Fix only if source-quality summary is missing**

If the summary is missing from packages produced by the normal configure path, update the package/report assembly code that already passes `source_claim_gap_report` into `build_operator_summary`. Do not add a second report builder or second apply gate.

- [ ] **Step 4: Commit**

Run:

```powershell
git add tests/test_universal_wild_no_block_matrix.py src/hsconfig
git commit -m "test: preserve no-block source quality across wild decks"
```

---

### Task 7: Update Operator And Skill Docs For The New Source-Quality Contract

**Files:**
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Test: `tests/test_skill_files.py`, `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: `source_claim_quality_summary` and source-quality lanes from earlier tasks
- Produces: compact operator documentation with no new workflow branch

- [ ] **Step 1: Add docs test for source-quality wording**

Add to `tests/test_skill_files.py` or a focused docs test:

```python
from pathlib import Path


def test_docs_describe_source_quality_as_non_blocking():
    docs = (
        Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    )

    assert "source_claim_quality_summary" in docs
    assert "non-blocking" in docs.lower()
    assert "operator_summary.json" in docs
    assert "source_contract_audit.json" in docs
    assert "second apply gate" in docs.lower()
```

- [ ] **Step 2: Run docs test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py::test_docs_describe_source_quality_as_non_blocking -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Update docs concisely**

Add a short section to `docs/operator/guide-research-policy.md`:

```markdown
### Source Claim Quality Summary

`operator_summary.json.source_claim_quality_summary` is a compact source-depth
visibility block. It counts every-card lanes, generic-low-confidence cards,
contract-gap cards, and the next useful claim kinds. It is non-blocking:
source-quality debt explains what to improve next, but it does not replace
`operator_summary.json` as the apply authority and does not create a second
apply gate.
```

Add one bullet to `.agents/skills/hsconfig/SKILL.md`:

```markdown
- Open `operator_summary.json.source_claim_quality_summary` when a deck is valid but thin. It is non-blocking source-depth visibility, not a second apply gate.
```

Keep `docs/operator/README.md` to a one-line pointer if it already links to guide research policy.

- [ ] **Step 4: Run docs tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add docs/operator/guide-research-policy.md docs/operator/README.md .agents/skills/hsconfig/SKILL.md tests/test_skill_files.py
git commit -m "docs: document source claim quality summary"
```

---

### Task 8: Final Verification And Push

**Files:**
- Modify: none
- Test: targeted and full suite

**Interfaces:**
- Consumes: all prior task commits
- Produces: pushed branch ready for merge

- [ ] **Step 1: Run targeted contract/source suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_quality_autonomy.py tests/test_source_contract_spine_freeze.py tests/test_source_contract_conformance.py tests/test_apply_authority_boundary.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run full suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Check for raw runtime evidence before commit or push**

Run:

```powershell
git status --short
rg -n "Power\\.log|\\.hdtreplay|\\.hsreplay|HearthRangerLogs|HDT" .
```

Expected:

```text
No tracked raw runtime evidence added.
```

If `rg` finds references in documentation or tests, inspect them and confirm they are documentation strings, not committed private runtime evidence.

- [ ] **Step 4: Final diff review**

Run:

```powershell
git diff --stat origin/main...HEAD
git diff --check
```

Expected:

```text
git diff --check exits 0
```

- [ ] **Step 5: Push branch**

Run:

```powershell
git push -u origin codex/hsconfig-source-claim-quality-autonomy
```

Expected:

```text
codex/hsconfig-source-claim-quality-autonomy -> codex/hsconfig-source-claim-quality-autonomy
```

---

## Self-Review

**Spec coverage:** The plan preserves the source-contract spine, keeps `operator_summary.json` as the only apply authority, keeps source debt non-blocking, protects the Darkbishop effect-versus-mulligan boundary, and adds every-card source-quality visibility without adding HSTuner scope.

**Placeholder scan:** The plan contains no open placeholder markers or unspecified implementation steps. Each task includes concrete files, tests, commands, and expected outcomes.

**Type consistency:** New fields are consistently named `source_claim_quality_summary`, `source_quality_lane_counts`, `cards_with_generic_low_confidence`, `cards_with_contract_gap`, `next_claim_kind_counts`, `source_quality_lane`, `recommended_next_claim_kind`, and `recommended_next_source_action`.

**Scope control:** The plan does not add replay parsing, runtime evidence tuning, winrate validation, candidate promotion, or new dependencies. It improves source autonomy inside the existing HSConfig boundary.
