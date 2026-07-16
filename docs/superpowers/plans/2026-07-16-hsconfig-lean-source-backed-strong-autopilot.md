# HSConfig Lean Source-Backed Strong Autopilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's source and contract pipeline lean, autonomous, and technically strict enough that a valid deck always gets a load-safe, non-default-only config package, while `SOURCE_BACKED_STRONG` is awarded only when current public guide or official static semantics truly close the required deck profile.

**Architecture:** Keep the existing linear workflow: `source-acquire` -> `source-autopilot` -> `draft-source-documents` -> `prepare`. Strengthen only the bounded evidence and closure layer: source family trust ceilings, atomic claim extraction, per-card surface closure, profile verdicts, and operator documentation. `reports/operator_summary.json` remains the normal apply authority; source reports explain evidence quality and missing links.

**Tech Stack:** Python 3.11, existing HSConfig CLI modules, JSON fixtures, pytest, repository docs. No new runtime service, no new dependency, no HSTuner replay loop, no winrate module.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig` for this implementation.
- Preserve the current branch unless the operator creates a new `codex/` branch before starting.
- Do not use HSranger or HSTuner code paths for this change.
- Do not introduce a blocking human approval gate.
- Every syntactically valid deck input must still produce a load-safe config attempt.
- Missing guide evidence may lower evidence status, but must not block config generation.
- `SOURCE_BACKED_STRONG` is an evidence-quality verdict, not an apply gate.
- `SOURCE_BACKED_STRONG` must never be inferred from decklists, stats pages, policy defaults, generated defaults, runtime examples, snippets, stale guides, or non-public URLs.
- Public guide claims must be current, deck- or archetype-matched, and full-text enough to support the concrete runtime surface being lowered.
- Official static card semantics may support static effect rows, but may not prove mulligan keeps or deck-specific targeting by itself.
- No output package may hide behind default-only runtime surfaces; every requested surface must be explicitly emitted, explicitly suppressed, or reported as a source gap.
- Darkbishop Benedictus (`SW_448`) must preserve its start-of-game hero-power transform contract, but must not become an opening-hand keep unless a current explicit mulligan guide says to keep it.
- Explicit source-backed discard advice may mark Darkbishop as a mulligan discard; effect-only semantics still remain in the per-card runtime file.
- Presume and Concede generation stay out of the normal package.
- Keep changes narrow: source policy, source compiler, source autopilot report, closure tests, and operator docs only.

## File Structure

Modify these files:

- `src/hsconfig/source_evidence_policy.py`
- `src/hsconfig/source_claim_compiler.py`
- `src/hsconfig/source_document_model.py`
- `src/hsconfig/source_autopilot.py`
- `docs/operator/source-backed-strong-closure.md`
- `docs/operator/guide-research-policy.md`
- `.agents/skills/hsconfig/SKILL.md`

Add or extend these tests:

- `tests/test_source_evidence_policy.py`
- `tests/test_source_claim_compiler.py`
- `tests/test_source_autopilot.py`
- `tests/test_universal_wild_no_block_matrix.py`
- `tests/test_shadowpriest_fresh_closure_proof.py`
- `tests/test_lean_source_backed_strong_autopilot.py`

Add these fixtures:

- `tests/fixtures/source_guides/shadowpriest_current_guide.html`
- `tests/fixtures/source_guides/ctapaladin_current_guide.html`
- `tests/fixtures/source_guides/piraterogue_current_guide.html`
- `tests/fixtures/source_guides/decklist_only_page.html`
- `tests/fixtures/source_guides/stats_only_page.html`

## Task 1: Freeze The Strong Evidence Contract

**Files**

- `tests/test_lean_source_backed_strong_autopilot.py`
- `tests/test_source_evidence_policy.py`
- `src/hsconfig/source_evidence_policy.py`

**Interfaces**

- `classify_source_evidence(record, *, current_year: int) -> SourceEvidenceVerdict`
- Verdict fields required by tests:
  - `source_lane`
  - `trust_ceiling`
  - `promotion_eligible`
  - `strong_promotion_eligible`
  - `blockers`

**Steps**

- [ ] Add a regression test proving that a current, deck-matched, full-text guide can produce `trust_ceiling == "source_backed_strong"`.
- [ ] Add a regression test proving that a decklist-only page produces `trust_ceiling == "decklist_informed"` and `strong_promotion_eligible is False`.
- [ ] Add a regression test proving that a stats-only page produces `trust_ceiling == "source_informed_partial"` and cannot promote to strong.
- [ ] Add a regression test proving that official static semantics can support `static_semantics_only`, but cannot promote mulligan, targeting, or combo claims to strong.
- [ ] Add a regression test proving stale publication year, missing publication year, snippet-only visibility, and deck-scope mismatch block strong promotion.
- [ ] Patch `source_evidence_policy.py` so all tests pass without changing public CLI output shape.

**Test Code**

Add these exact tests as a starting block:

```python
from hsconfig.source_evidence_policy import classify_source_evidence


def _record(**overrides):
    base = {
        "url": "https://example.com/shadow-priest-guide-2026",
        "source_family": "guide",
        "visibility": "full_text",
        "deck_match": "deck_matched_public_guide",
        "publication_year": 2026,
        "evidence_strength": "guide_current_deck_match",
    }
    base.update(overrides)
    return base


def test_current_deck_matched_full_guide_can_be_source_backed_strong():
    verdict = classify_source_evidence(_record(), current_year=2026)

    assert verdict.trust_ceiling == "source_backed_strong"
    assert verdict.promotion_eligible is True
    assert verdict.strong_promotion_eligible is True
    assert verdict.blockers == []


def test_decklist_only_never_promotes_to_source_backed_strong():
    verdict = classify_source_evidence(
        _record(source_family="decklist", evidence_strength="decklist_match"),
        current_year=2026,
    )

    assert verdict.trust_ceiling == "decklist_informed"
    assert verdict.strong_promotion_eligible is False
    assert "decklist_not_guide" in verdict.blockers


def test_static_semantics_never_proves_deck_specific_runtime_claims():
    verdict = classify_source_evidence(
        _record(
            source_family="official_static_semantics",
            deck_match="official_static_semantics",
            evidence_strength="official_static_semantics",
        ),
        current_year=2026,
    )

    assert verdict.trust_ceiling == "static_semantics_only"
    assert verdict.strong_promotion_eligible is False
    assert "static_semantics_not_deck_strategy" in verdict.blockers
```

**Run**

```powershell
python -m pytest tests/test_source_evidence_policy.py tests/test_lean_source_backed_strong_autopilot.py -q
```

Expected result after implementation:

```text
passed
```

**Commit**

```powershell
git add src/hsconfig/source_evidence_policy.py tests/test_source_evidence_policy.py tests/test_lean_source_backed_strong_autopilot.py
git commit -m "Harden HSConfig source evidence trust ceilings"
```

## Task 2: Make Claim Extraction Atomic And Non-Default

**Files**

- `src/hsconfig/source_claim_compiler.py`
- `src/hsconfig/source_document_model.py`
- `tests/test_source_claim_compiler.py`

**Interfaces**

- `compile_source_search_records(records, deck_cards, deck_name, deck_code) -> SourceClaimCompilerResult`
- Emitted claim kinds:
  - `mulligan_keep`
  - `mulligan_discard`
  - `targeting_rule`
  - `combo_sequence`
  - `gameplan_posture`
  - `hero_power_transform`
  - `card_role`
  - `mechanic_usage`

**Steps**

- [ ] Add tests for positive opening-hand keep extraction from current guide text.
- [ ] Add tests for negative opening-hand keep extraction, including cost-band advice such as "do not keep 4-cost or higher cards".
- [ ] Add tests proving Darkbishop Benedictus is not emitted as `mulligan_keep` from effect text.
- [ ] Add tests proving Darkbishop Benedictus may be emitted as `mulligan_discard` when the guide explicitly says not to keep cards in its cost band.
- [ ] Add tests for Mind Spike and Shadowform style hero-power transform extraction as `hero_power_transform`.
- [ ] Add tests for direct face-damage targeting rules from guide text.
- [ ] Add tests for combo and setup sequencing from guide text when card names appear in ordered sentences.
- [ ] Patch the compiler so each emitted row contains one concrete claim, one source lane, and one runtime target.
- [ ] Patch `source_document_model.py` only if `opening_hand_relevant`, `runtime_lowering`, or `strong_promotion_eligible` metadata is too coarse for the new tests.
- [ ] Keep generated rows deterministic by sorting them by `claim_kind`, `card_id`, `surface`, and `source_url`.

**Test Code**

Add these exact behavioral tests:

```python
from hsconfig.source_claim_compiler import compile_source_search_records


DECK_CARDS = [
    {"id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform."},
    {"id": "BAR_735", "name": "Voidtouched Attendant", "cost": 1, "text": "Both heroes take one extra damage."},
    {"id": "DMF_237", "name": "Raise Dead", "cost": 0, "text": "Deal 3 damage to your hero. Return two friendly minions that died this game to your hand."},
]


def _guide(text):
    return {
        "url": "https://example.com/shadow-priest-guide-2026",
        "source_family": "guide",
        "visibility": "full_text",
        "deck_match": "deck_matched_public_guide",
        "publication_year": 2026,
        "evidence_strength": "guide_current_deck_match",
        "text": text,
    }


def _claims(text):
    result = compile_source_search_records(
        [_guide(text)],
        deck_cards=DECK_CARDS,
        deck_name="ShadowPriest",
        deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    )
    return result.claims


def test_darkbishop_effect_text_does_not_create_mulligan_keep():
    claims = _claims("Darkbishop Benedictus turns your hero power into Mind Spike at the start of the game.")

    assert not [
        claim for claim in claims
        if claim.card_id == "SW_448" and claim.claim_kind == "mulligan_keep"
    ]
    assert [
        claim for claim in claims
        if claim.card_id == "SW_448" and claim.claim_kind == "hero_power_transform"
    ]


def test_explicit_cost_band_discard_can_apply_to_darkbishop():
    claims = _claims("In the mulligan, keep Voidtouched Attendant and do not keep any 4-cost or higher cards.")

    assert [
        claim for claim in claims
        if claim.card_id == "BAR_735" and claim.claim_kind == "mulligan_keep"
    ]
    assert [
        claim for claim in claims
        if claim.card_id == "SW_448" and claim.claim_kind == "mulligan_discard"
    ]
    assert not [
        claim for claim in claims
        if claim.card_id == "SW_448" and claim.claim_kind == "mulligan_keep"
    ]
```

**Run**

```powershell
python -m pytest tests/test_source_claim_compiler.py -q
```

Expected result after implementation:

```text
passed
```

**Commit**

```powershell
git add src/hsconfig/source_claim_compiler.py src/hsconfig/source_document_model.py tests/test_source_claim_compiler.py
git commit -m "Compile atomic source-backed HSConfig claims"
```

## Task 3: Close Autopilot Profile Verdicts Per Surface

**Files**

- `src/hsconfig/source_autopilot.py`
- `tests/test_source_autopilot.py`
- `tests/test_lean_source_backed_strong_autopilot.py`

**Interfaces**

- `build_source_autopilot_bundle(*, deck_name: str, deck_identity: Mapping[str, Any], source_search_records: Sequence[Mapping[str, Any]], current_date: str | date | None = None) -> dict[str, Any]`
- Report keys:
  - `semantic_status`
  - `source_backed_strong_closure`
  - `strong_closure_summary`
  - `first_missing_source_action_by_card`
  - `first_missing_source_action_by_surface`
  - `default_only_runtime_surfaces`
  - `runtime_apply_authority`

**Steps**

- [ ] Add a failing test where source rows include strong mulligan and hero-power transform claims for ShadowPriest, and the bundle reports `semantic_status == "SOURCE_BACKED_STRONG"`.
- [ ] Add a failing test where the same deck has only decklist evidence, and the bundle reports a non-strong status plus a concrete first missing source action.
- [ ] Add a failing test where a runtime surface is requested but neither emitted nor suppressed, and the bundle lists it under `default_only_runtime_surfaces`.
- [ ] Add a failing test proving `runtime_apply_authority == "reports/operator_summary.json"` remains unchanged.
- [ ] Patch `source_autopilot.py` so report generation uses the closure profile verdict rather than a single global source flag.
- [ ] Ensure every card row in the report has one lane: `lowered`, `suppressed`, `source_gap`, `static_only`, or `not_applicable`.
- [ ] Ensure every surface row has one lane: `emitted`, `suppressed`, `source_gap`, or `profile_not_required`.

**Test Code**

Add this exact report assertion pattern:

```python
def assert_source_backed_strong_report(report):
    assert report["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert report["source_backed_strong_closure"]["closed"] is True
    assert report["default_only_runtime_surfaces"] == []
    assert report["runtime_apply_authority"] == "reports/operator_summary.json"
    assert report["first_missing_source_action_by_card"] == {}
    assert report["first_missing_source_action_by_surface"] == {}


def assert_partial_report_explains_first_missing_link(report):
    assert report["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert report["source_backed_strong_closure"]["closed"] is False
    assert report["runtime_apply_authority"] == "reports/operator_summary.json"
    assert report["first_missing_source_action_by_card"] or report["first_missing_source_action_by_surface"]
```

**Run**

```powershell
python -m pytest tests/test_source_autopilot.py tests/test_lean_source_backed_strong_autopilot.py -q
```

Expected result after implementation:

```text
passed
```

**Commit**

```powershell
git add src/hsconfig/source_autopilot.py tests/test_source_autopilot.py tests/test_lean_source_backed_strong_autopilot.py
git commit -m "Report HSConfig source closure by card and surface"
```

## Task 4: Add Bounded Guide Fixtures For Representative Wild Decks

**Files**

- `tests/fixtures/source_guides/shadowpriest_current_guide.html`
- `tests/fixtures/source_guides/ctapaladin_current_guide.html`
- `tests/fixtures/source_guides/piraterogue_current_guide.html`
- `tests/fixtures/source_guides/decklist_only_page.html`
- `tests/fixtures/source_guides/stats_only_page.html`
- `tests/test_universal_wild_no_block_matrix.py`
- `tests/test_lean_source_backed_strong_autopilot.py`

**Representative Decks**

- ShadowPriest
- CtAPaladin
- PirateRogue
- BigShaman
- Discolock
- TreantDruid
- ImbueMage
- MechPala
- Kingslayer
- Boarlock
- PirateDH

**Steps**

- [ ] Add small HTML fixtures with visible guide text, source-family markers, deck-year markers, and deck names.
- [ ] Add decklist-only and stats-only HTML fixtures to prove non-guide pages stay non-strong.
- [ ] Extend the Wild matrix test so every representative deck produces a load-safe package.
- [ ] Extend the Wild matrix test so every representative deck has `default_only_runtime_surfaces == []`.
- [ ] Extend the Wild matrix test so decks without complete guide evidence still report the first missing link instead of blocking.
- [ ] Extend the Wild matrix test so decks with complete current guide evidence can report `SOURCE_BACKED_STRONG`.
- [ ] Do not store raw live webpages; fixtures must be compact and source-shaped, not copied articles.

**Run**

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_lean_source_backed_strong_autopilot.py -q
```

Expected result after implementation:

```text
passed
```

**Commit**

```powershell
git add tests/fixtures/source_guides tests/test_universal_wild_no_block_matrix.py tests/test_lean_source_backed_strong_autopilot.py
git commit -m "Cover representative Wild deck source closure"
```

## Task 5: Rebuild ShadowPriest Proof Without A Default-Only Mulligan

**Files**

- `tests/test_shadowpriest_fresh_closure_proof.py`
- `docs/operator/source-backed-strong-closure.md`
- Runtime output fixture path already used by the repository's ShadowPriest proof tests

**Steps**

- [ ] Add or update a ShadowPriest proof test that runs the source-backed build path from deck input to generated package fixture.
- [ ] Assert `Mulligan.json` keeps guide-backed actual opening-hand cards only.
- [ ] Assert `Mulligan.json` does not keep `SW_448` unless the fixture source explicitly says to keep Darkbishop Benedictus.
- [ ] Assert `SW_448.json` contains the start-of-game hero-power transform row.
- [ ] Assert Mind Spike or Shadowform semantics are visible in the per-card runtime contract.
- [ ] Assert `reports/operator_summary.json` is still the apply authority.
- [ ] Assert `source_autopilot_report.json` explains the evidence status and closure lanes.

**Test Code**

Add this exact assertion block around the generated package object:

```python
def assert_shadowpriest_darkbishop_contract(package):
    mulligan = package.read_json("Mulligan.json")
    darkbishop_runtime = package.read_json("CardID/SW_448.json")
    operator_summary = package.read_json("reports/operator_summary.json")
    source_report = package.read_json("reports/source_autopilot_report.json")

    kept_ids = {
        row["card_id"]
        for row in mulligan.get("rules", [])
        if row.get("action") == "keep"
    }

    assert "SW_448" not in kept_ids
    assert any(
        row.get("kind") == "hero_power_transform"
        and "Mind Spike" in row.get("description", "")
        for row in darkbishop_runtime.get("rules", [])
    )
    assert operator_summary["runtime_apply_authority"] == "reports/operator_summary.json"
    assert source_report["default_only_runtime_surfaces"] == []
```

**Run**

```powershell
python -m pytest tests/test_shadowpriest_fresh_closure_proof.py -q
```

Expected result after implementation:

```text
passed
```

**Commit**

```powershell
git add tests/test_shadowpriest_fresh_closure_proof.py docs/operator/source-backed-strong-closure.md
git commit -m "Prove ShadowPriest source-backed Darkbishop semantics"
```

## Task 6: Keep Operator Docs And Skill Instructions Narrow

**Files**

- `docs/operator/source-backed-strong-closure.md`
- `docs/operator/guide-research-policy.md`
- `.agents/skills/hsconfig/SKILL.md`

**Steps**

- [ ] Update the source-backed closure doc with the final trust ceilings.
- [ ] Document that `SOURCE_BACKED_STRONG` is evidence-quality only and never blocks a load-safe config attempt.
- [ ] Document that no default-only runtime surface may be hidden.
- [ ] Document the Darkbishop split: effect row remains, opening-hand keep is not inferred.
- [ ] Document the representative Wild deck matrix statuses and the exact first missing link rule.
- [ ] Update the HSConfig skill so future runs follow the same compact source-acquire -> source-autopilot -> prepare flow.
- [ ] Remove wording that suggests broad orchestration, replay tuning, winrate tuning, Presume, or Concede belong in HSConfig.

**Run**

```powershell
python -m pytest tests/test_lean_source_backed_strong_autopilot.py tests/test_shadowpriest_fresh_closure_proof.py -q
```

Expected result after implementation:

```text
passed
```

**Commit**

```powershell
git add docs/operator/source-backed-strong-closure.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md
git commit -m "Document lean HSConfig source closure policy"
```

## Task 7: Final Verification And Current-State Handoff

**Files**

- All changed source, test, fixture, and docs files

**Steps**

- [ ] Run the targeted source closure suite.
- [ ] Run the full repository test suite.
- [ ] Inspect `git diff --stat HEAD~6..HEAD` if per-task commits were used.
- [ ] Inspect `git status --short --branch`.
- [ ] Confirm there are no generated cache files, raw logs, or private runtime evidence files staged.
- [ ] Confirm no package output contains Presume or Concede files in the normal path.
- [ ] Confirm the ShadowPriest package proves Darkbishop effect semantics without Darkbishop mulligan keep.
- [ ] Push the branch only when the user requested GitHub synchronization for this implementation run.

**Run**

```powershell
python -m pytest tests/test_source_evidence_policy.py tests/test_source_claim_compiler.py tests/test_source_autopilot.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_fresh_closure_proof.py tests/test_lean_source_backed_strong_autopilot.py -q
python -m pytest -q
git status --short --branch
```

Expected result after implementation:

```text
passed
## codex/hsconfig-source-backed-strong-autopilot
```

**Commit**

If task commits were not used, commit the consolidated implementation:

```powershell
git add src/hsconfig tests docs/operator .agents/skills/hsconfig
git commit -m "Close lean HSConfig source-backed strong autopilot"
```

## Self-Review Checklist

- [ ] Plan keeps HSConfig narrow and does not rebuild HSTuner.
- [ ] Plan keeps config generation autonomous and non-blocking.
- [ ] Plan makes `SOURCE_BACKED_STRONG` harder to earn, not easier to fake.
- [ ] Plan explicitly removes hidden default-only behavior.
- [ ] Plan preserves Darkbishop effect semantics while removing mistaken mulligan keep behavior.
- [ ] Plan covers the representative Wild deck matrix.
- [ ] Plan includes source policy, claim compiler, autopilot report, proof tests, docs, and skill instructions.
- [ ] Plan includes exact verification commands.
- [ ] Plan avoids new dependencies and broad architecture growth.

## Execution Handoff

Recommended execution mode:

```text
Subagent-Driven Umsetzung dieses Plans starten
```

Use read-only subagents for source-policy review, compiler behavior review, Wild-deck matrix review, and docs review. Use one worker for source-policy and compiler code, one worker for autopilot report code, and one worker for tests and fixtures. The main agent must consolidate all diffs and run the final verification commands.
