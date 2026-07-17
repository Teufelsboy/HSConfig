# HSConfig Source Contract Acceptance Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig's source/contract logic provably canonical, no-block, no-default-only, and strong only when the full source-to-runtime chain honestly closes.

**Architecture:** Keep the existing pipeline and make it stricter at the acceptance boundaries: online/current sources feed source acquisition, claims normalize through `claim_kind`, runtime surfaces are admitted only through the source contract matrix and surface gates, and `reports/operator_summary.json` remains the only normal apply authority. `SOURCE_BACKED_STRONG` is resolved through `src/hsconfig/source_status_resolver.py` and mirrored by diagnostic reports; no report may become a second apply gate.

**Tech Stack:** Python stdlib, pytest, existing HSConfig CLI/modules, existing research skill outline format, no new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Before implementation, run `git fetch --all --prune` and `git rev-list --left-right --count HEAD...origin/main`; expected current result is `0 0`.
- Preserve the existing dirty worktree. Do not revert unrelated user or previous-agent changes.
- Keep `reports/operator_summary.json` as the only normal apply authority.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation gate and not an apply gate.
- `source_status_apply_blocking` must remain `false` for source-quality gaps.
- Every valid Wild deck must still build a load-safe package, even when source evidence is partial.
- No default-only runtime surface may be hidden or count as strong.
- Candidate URLs, decklists, snippets, HSGuru/HSReplay stats, and static card databases are support or acquisition seeds unless fetched full text and claim-kind/surface-gate evidence close the exact runtime surface.
- Darkbishop Benedictus (`SW_448`) keeps `hero_power_transform` / Shadowform / Mind Spike effect semantics, but is not emitted as an opening-hand mulligan keep without explicit full-text mulligan evidence.

---

## File Map

- Create: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/fields.yaml`
- Create: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/outline.yaml`
- Modify: `src/hsconfig/source_acquisition.py`
- Modify: `src/hsconfig/source_claim_compiler.py`
- Modify: `src/hsconfig/source_status_resolver.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/source_bundle.py`
- Modify: `src/hsconfig/source_evidence_closure.py`
- Modify: `src/hsconfig/strong_promotion_report.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `tests/test_source_acquisition.py`
- Modify: `tests/test_source_claim_compiler.py`
- Modify: `tests/test_source_status_resolver.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_source_bundle.py`
- Modify: `tests/test_source_evidence_closure.py`
- Modify: `tests/test_strong_promotion_report.py`
- Modify: `tests/test_configure_online_source.py`
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Create: `tests/test_shadowpriest_source_contract_acceptance.py`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`

## Deck Matrix

Use these exact deck names in all matrix checks:

```python
USER_WILD_DECKS = (
    ("ShadowPriest", "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="),
    ("CtAPaladin", "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA="),
    ("PirateRogue", "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA=="),
    ("BigShaman", "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA=="),
    ("Discolock", "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA"),
    ("TreantDruid", "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA=="),
    ("ImbueMage", "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA="),
    ("MechPala", "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="),
    ("Kingslayer", "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA="),
    ("Boarlock", "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA"),
    ("PirateDH", "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA=="),
    ("CuteWarrior", "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA="),
)
```

---

### Task 1: Create The Research-Deep Outline For Current Source Cross-Check

**Files:**
- Create: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/fields.yaml`
- Create: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/outline.yaml`

**Interfaces:**
- Consumes: the deck matrix above.
- Produces: a reproducible `research-deep` outline whose results can be used as source candidate input, not as direct runtime authority.

- [ ] **Step 1: Write `fields.yaml`**

Create `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/fields.yaml` with:

```yaml
fields:
  deck_name:
    type: string
    description: Exact HSConfig deck name.
  archetype:
    type: string
    description: Wild archetype or closest public archetype label.
  current_deck_sources:
    type: array
    description: Current public pages that list the deck or close archetype, with URL and source family.
  guide_sources:
    type: array
    description: Full-text guide or guide-like public sources that contain strategic, mulligan, combo, or usage claims.
  source_strength:
    type: string
    description: One of exact_full_text_guide, archetype_full_text_guide, decklist_or_stats_only, static_semantics_only, missing.
  lowerable_claim_kinds:
    type: array
    description: Claim kinds supported by the available source text.
  non_promoting_support:
    type: array
    description: Sources that are useful context but must not prove SOURCE_BACKED_STRONG by themselves.
  first_missing_source_action:
    type: string
    description: Concrete next source action when strong closure is not proven.
  notes:
    type: string
    description: Short implementation-relevant notes.
```

- [ ] **Step 2: Write `outline.yaml`**

Create `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/outline.yaml` with:

```yaml
topic: hsconfig_source_contract_acceptance_loop
execution:
  output_dir: ./results
  batch_size: 4
  items_per_agent: 1
items:
  - name: ShadowPriest
    category: Wild Hearthstone deck
    deck_code: AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
    focus: Source-backed ShadowPriest guide, mulligan, Darkbishop Benedictus effect-only boundary.
  - name: CtAPaladin
    category: Wild Hearthstone deck
    deck_code: AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=
    focus: Call to Arms Paladin source strength, board-flood/recruit claims, mulligan and runtime surfaces.
  - name: PirateRogue
    category: Wild Hearthstone deck
    deck_code: AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==
    focus: Pirate Rogue and weapon-pressure source strength, mulligan and weapon/runtime surfaces.
  - name: BigShaman
    category: Wild Hearthstone deck
    deck_code: AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==
    focus: Big Shaman cheat/recruit source strength, mulligan and combo-like setup surfaces.
  - name: Discolock
    category: Wild Hearthstone deck
    deck_code: AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA
    focus: Discolock discard-pressure source strength, discard claims and mulligan surfaces.
  - name: TreantDruid
    category: Wild Hearthstone deck
    deck_code: AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==
    focus: Treant Druid board-flood source strength, token setup claims and mulligan surfaces.
  - name: ImbueMage
    category: Wild Hearthstone deck
    deck_code: AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=
    focus: Imbue Mage hero-power source strength, imbue/hero-power claims and runtime surfaces.
  - name: MechPala
    category: Wild Hearthstone deck
    deck_code: AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==
    focus: Mech Paladin board-flood source strength, magnetize/mech pressure claims and mulligan surfaces.
  - name: Kingslayer
    category: Wild Hearthstone deck
    deck_code: AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=
    focus: Kingslayer weapon-pressure source strength, weapon setup claims and partial-source handling.
  - name: Boarlock
    category: Wild Hearthstone deck
    deck_code: AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA
    focus: Boarlock combo source strength, Elwynn Boar setup claims and low-confidence Fracking boundary.
  - name: PirateDH
    category: Wild Hearthstone deck
    deck_code: AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==
    focus: Pirate Demon Hunter weapon/aggro source strength, mulligan and weapon-pressure claims.
  - name: CuteWarrior
    category: Wild Hearthstone deck
    deck_code: AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=
    focus: Cute Warrior source strength, current decklist/stat support and missing full-text guide action.
```

- [ ] **Step 3: Verify YAML files are readable**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python - <<'PY'
from pathlib import Path
import yaml
base = Path("docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop")
for name in ("fields.yaml", "outline.yaml"):
    data = yaml.safe_load((base / name).read_text(encoding="utf-8"))
    assert data, name
print("research outline ok")
PY
```

Expected:

```text
research outline ok
```

---

### Task 2: Run Research-Deep And Convert Findings To Source Inputs

**Files:**
- Read: `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/*.json`
- Create or update: `docs/operator/source-inputs/2026-07-17-user-wild-source-cross-check.json`

**Interfaces:**
- Consumes: Task 1 outline results.
- Produces: deterministic source input records for HSConfig tests and configure runs.

- [ ] **Step 1: Run research-deep from the outline directory**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop
```

Then invoke the `research-deep` skill against the local `outline.yaml`. The skill must write one JSON result per item under:

```text
C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-17-hsconfig-source-contract-acceptance-loop\results
```

- [ ] **Step 2: Validate result count**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python - <<'PY'
from pathlib import Path
results = Path("docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results")
files = sorted(results.glob("*.json"))
assert len(files) == 12, [p.name for p in files]
print(f"research result count ok: {len(files)}")
PY
```

Expected:

```text
research result count ok: 12
```

- [ ] **Step 3: Write normalized source input JSON**

Create `docs/operator/source-inputs/2026-07-17-user-wild-source-cross-check.json` with this top-level shape:

```json
{
  "schema_version": 1,
  "retrieved_at": "2026-07-17",
  "usage": "source_candidates_only_not_runtime_authority",
  "decks": []
}
```

For every research result, append one deck object:

```json
{
  "deck_name": "ShadowPriest",
  "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
  "source_candidates": [
    {
      "url": "https://example.invalid/current-guide",
      "source_family": "public_guide",
      "source_strength": "exact_full_text_guide",
      "promotion_role": "candidate_only_until_fetched_and_claim_normalized"
    }
  ],
  "non_promoting_support": [
    {
      "url": "https://example.invalid/stats",
      "source_family": "stats_page",
      "promotion_role": "context_only"
    }
  ],
  "first_missing_source_action": "none"
}
```

Use actual URLs from the research output. Keep decklist/stat pages in `non_promoting_support` unless the source contains full-text strategic claims.

- [ ] **Step 4: Validate normalized source input**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python - <<'PY'
import json
from pathlib import Path
path = Path("docs/operator/source-inputs/2026-07-17-user-wild-source-cross-check.json")
data = json.loads(path.read_text(encoding="utf-8"))
assert data["schema_version"] == 1
assert data["usage"] == "source_candidates_only_not_runtime_authority"
assert len(data["decks"]) == 12
for row in data["decks"]:
    assert row["deck_name"]
    assert row["deck_code"]
    assert "source_candidates" in row
    assert "non_promoting_support" in row
    assert row["first_missing_source_action"]
print("source input ok")
PY
```

Expected:

```text
source input ok
```

---

### Task 3: Lock Canonical Source Status In Tests First

**Files:**
- Modify: `tests/test_source_status_resolver.py`
- Modify: `src/hsconfig/source_status_resolver.py`

**Interfaces:**
- Consumes: `resolve_source_status(...)`.
- Produces: canonical source status fields consumed by operator and diagnostic reports.

- [ ] **Step 1: Add failing resolver tests**

Append tests to `tests/test_source_status_resolver.py`:

```python
def test_decklist_only_or_stats_only_support_never_promotes_strong() -> None:
    for report in (
        {"summary": {"first_missing_chain": None, "deck_surface_gap_count": 1, "next_action": "add_full_text_public_guide_source"}},
        {"summary": {"first_missing_chain": None, "blocked_cards": 1, "next_source_builder_action": "add_explicit_mulligan_source"}},
    ):
        resolution = resolve_source_status(
            technical_status="VALID_PACKAGE",
            semantic_status="SOURCE_BACKED_STRONG",
            next_action="READY_TO_APPLY_OR_HANDOFF",
            semantic_blockers=[],
            default_only_runtime_surfaces=[],
            source_claim_gap_report=report,
            closure_profile_closed=True,
        )

        assert resolution.source_backed_status == "SOURCE_BACKED_PARTIAL"
        assert resolution.strong_ready is False
        assert resolution.first_missing_source_action != "none"
        assert resolution.apply_blocking is False


def test_source_status_apply_blocking_is_false_for_all_source_quality_gaps() -> None:
    scenarios = (
        {"default_only_runtime_surfaces": ["mulligan"], "source_claim_gap_report": None, "closure_profile_closed": True},
        {"default_only_runtime_surfaces": [], "source_claim_gap_report": {"summary": {"first_missing_chain": {"first_missing_link": "needs_guide_claim"}}}, "closure_profile_closed": True},
        {"default_only_runtime_surfaces": [], "source_claim_gap_report": None, "closure_profile_closed": False},
    )

    for scenario in scenarios:
        resolution = resolve_source_status(
            technical_status="VALID_PACKAGE",
            semantic_status="SOURCE_BACKED_STRONG",
            next_action="READY_TO_APPLY_OR_HANDOFF",
            semantic_blockers=[],
            default_only_runtime_surfaces=scenario["default_only_runtime_surfaces"],
            source_claim_gap_report=scenario["source_claim_gap_report"],
            closure_profile_closed=scenario["closure_profile_closed"],
            closure_profile_first_missing_link="missing_surface:mulligan",
        )

        assert resolution.source_status_diagnostic_only if hasattr(resolution, "source_status_diagnostic_only") else resolution.diagnostic_only
        assert resolution.apply_blocking is False
```

- [ ] **Step 2: Run the resolver tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py -q
```

Expected before implementation: either failure on missing semantics or pass if the current resolver already covers it. Expected after implementation: pass.

- [ ] **Step 3: Update resolver only if tests fail**

In `src/hsconfig/source_status_resolver.py`, keep `SourceStatusResolution` frozen and pure. Ensure:

```python
diagnostic_only: bool = True
apply_blocking: bool = False
```

Ensure default-only runtime surfaces return:

```python
source_backed_status=PARTIAL_SOURCE_STATUS
action=DEFAULT_ONLY_SOURCE_ACTION
reasons=("default_only_runtime_surface",)
```

Ensure unclosed source gap summaries return `SOURCE_BACKED_PARTIAL` before the strong-ready path.

- [ ] **Step 4: Re-run resolver tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_status_resolver.py -q
```

Expected: all tests pass.

---

### Task 4: Enforce One Source Status In Operator And Diagnostic Reports

**Files:**
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_source_bundle.py`
- Modify: `tests/test_source_evidence_closure.py`
- Modify: `tests/test_strong_promotion_report.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/source_bundle.py`
- Modify: `src/hsconfig/source_evidence_closure.py`
- Modify: `src/hsconfig/strong_promotion_report.py`

**Interfaces:**
- Consumes: `SourceStatusResolution.as_operator_fields()`.
- Produces: matching source status/action fields in all report surfaces.

- [ ] **Step 1: Add report consistency tests**

Add this helper to the most appropriate existing test file, or duplicate it locally in each report test when helper imports would add coupling:

```python
def assert_same_source_status(operator: dict, report: dict) -> None:
    assert report["source_backed_status"] == operator["source_backed_status"]
    assert report["source_strong_ready"] == operator["source_strong_ready"]
    assert report["first_missing_source_action"] == operator["first_missing_source_action"]
    assert report["source_status_apply_blocking"] is False
    assert operator["source_status_apply_blocking"] is False
```

Add tests that build one strong fixture and one partial fixture, then assert consistency across:

```text
operator_summary.json
source_bundle.json
source_evidence_closure.json
strong_promotion_report.json
```

- [ ] **Step 2: Run report consistency tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_summary.py tests/test_source_bundle.py tests/test_source_evidence_closure.py tests/test_strong_promotion_report.py -q
```

Expected before implementation: failure if any report computes a divergent status or omits a canonical field. Expected after implementation: pass.

- [ ] **Step 3: Wire all reports through the resolver**

In each source module listed above, remove duplicated first-missing/source-status calculations that conflict with `source_status_resolver.py`.

Each returned report must include:

```python
"source_backed_status": source_status_resolution.source_backed_status,
"source_strong_ready": source_status_resolution.strong_ready,
"first_missing_source_action": source_status_resolution.first_missing_source_action,
"source_missing_source_actions": list(source_status_resolution.missing_source_actions),
"source_status_reasons": list(source_status_resolution.reasons),
"source_status_diagnostic_only": source_status_resolution.diagnostic_only,
"source_status_apply_blocking": source_status_resolution.apply_blocking,
```

Keep report-specific fields intact. Do not remove existing compatibility fields unless tests prove they are unused and stale.

- [ ] **Step 4: Re-run report consistency tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_summary.py tests/test_source_bundle.py tests/test_source_evidence_closure.py tests/test_strong_promotion_report.py -q
```

Expected: all tests pass.

---

### Task 5: Prevent Default-Only Strong Promotion Without Blocking Packages

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/operator_summary.py`

**Interfaces:**
- Consumes: generated package runtime files and `operator_summary.json`.
- Produces: visible no-default-only status for all valid deck packages.

- [ ] **Step 1: Extend no-default-only assertions**

In `tests/test_universal_wild_no_block_matrix.py`, ensure `assert_no_runtime_surface_is_hidden_default` includes:

```python
assert operator["default_only_runtime_surfaces"] == []
assert operator["default_only_runtime_surface_details"] == []
assert operator["no_default_only_runtime_status"] == "clean"
assert operator["source_status_diagnostic_only"] is True
assert operator["source_status_apply_blocking"] is False
assert operator["source_backed_status"] in {
    "SOURCE_BACKED_STRONG",
    "SOURCE_BACKED_PARTIAL",
}
```

Add one negative unit test to `tests/test_operator_summary.py`:

```python
def test_default_only_runtime_surface_cannot_report_source_backed_strong():
    summary = build_operator_summary(...)

    assert summary["default_only_runtime_surfaces"] == ["mulligan"]
    assert summary["source_backed_status"] != "SOURCE_BACKED_STRONG"
    assert summary["source_strong_ready"] is False
    assert summary["source_status_apply_blocking"] is False
```

Use the existing local fixture/builder pattern in `tests/test_operator_summary.py`; do not create a second production builder for the test.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_summary.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected before implementation: failure if a default-only surface can still be strong or invisible. Expected after implementation: pass.

- [ ] **Step 3: Fix default-only visibility only where tests fail**

If tests fail, update `src/hsconfig/package_builder.py` or `src/hsconfig/operator_summary.py` so generated fallback rows are tagged and summarized into:

```python
"default_only_runtime_surfaces": [...]
"default_only_runtime_surface_details": [...]
"no_default_only_runtime_status": "clean" | "has_default_only_surfaces"
```

Do not block `runtime_apply_allowed` solely because a source surface is partial. Strong status must drop; package validity remains load-safe when technical validation passes.

- [ ] **Step 4: Re-run focused tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_summary.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all tests pass.

---

### Task 6: Lock ShadowPriest Darkbishop As Effect-Only Strong Canary

**Files:**
- Create: `tests/test_shadowpriest_source_contract_acceptance.py`
- Modify: `src/hsconfig/source_claim_compiler.py`
- Modify: `src/hsconfig/package_builder.py`

**Interfaces:**
- Consumes: ShadowPriest source documents and static card semantics.
- Produces: verified strong package where `SW_448` effect semantics exist and `SW_448` is absent from `Mulligan.json`.

- [ ] **Step 1: Write the failing ShadowPriest acceptance test**

Create `tests/test_shadowpriest_source_contract_acceptance.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_shadowpriest_source_backed_strong_preserves_darkbishop_effect_only(tmp_path, monkeypatch):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "shadowpriest"

    assert main([
        "configure",
        "--deck-name",
        "ShadowPriest",
        "--deck-code",
        SHADOWPRIEST_CODE,
        "--runtime-root",
        str(tmp_path / "runtime"),
        "--out",
        str(out),
        "--json",
    ]) == 0

    package = out / "04_package"
    operator = _load(package / "reports" / "operator_summary.json")
    deck_dir = next((package / "CustomConfig").iterdir())
    mulligan = _load(deck_dir / "Mulligan.json")
    darkbishop = _load(deck_dir / "SW_448.json")

    assert operator["source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert operator["source_strong_ready"] is True
    assert operator["first_missing_source_action"] == "none"
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["source_status_apply_blocking"] is False
    assert not any(
        row.get("mulligan") == "SW_448" or row.get("card_id") == "SW_448"
        for row in mulligan["Mulligan"]["values"]
    )
    assert darkbishop["BeforeUseHeroPowerBonus"]["values"]
    assert any(
        "shadow" in json.dumps(row).lower()
        or "mind spike" in json.dumps(row).lower()
        or "transformed_hero_power" in json.dumps(row).lower()
        for row in darkbishop["BeforeUseHeroPowerBonus"]["values"]
    )
```

- [ ] **Step 2: Run the ShadowPriest test**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_shadowpriest_source_contract_acceptance.py -q
```

Expected before implementation: failure if strong closure or Darkbishop effect-only behavior regressed. Expected after implementation: pass.

- [ ] **Step 3: Fix only the failing boundary**

If `SW_448` appears in `Mulligan.json`, update `src/hsconfig/source_claim_compiler.py` so start-of-game/effect wording normalizes to `hero_power_transform`, not `mulligan_keep`, unless the text explicitly says to keep Darkbishop in the opening hand.

If `SW_448.json` lacks effect semantics, update `src/hsconfig/package_builder.py` so `hero_power_transform` claims and static semantics emit `BeforeUseHeroPowerBonus` rows.

Do not add any generic "keep legendary enabler" rule.

- [ ] **Step 4: Re-run the ShadowPriest test**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_shadowpriest_source_contract_acceptance.py -q
```

Expected: pass.

---

### Task 7: Make Online Source Inputs Diagnostic And Deterministic

**Files:**
- Modify: `tests/test_source_acquisition.py`
- Modify: `tests/test_configure_online_source.py`
- Modify: `src/hsconfig/source_acquisition.py`

**Interfaces:**
- Consumes: source input JSON from Task 2 and existing source acquisition records.
- Produces: acquired source records that expose promotion eligibility without becoming runtime authority.

- [ ] **Step 1: Add source acquisition tests**

Add tests asserting these records:

```python
def test_decklist_and_stats_sources_are_non_promoting():
    record = acquire_source_record(...)

    assert record["source_category"] in {"decklist", "stats"}
    assert record["promotion_eligible"] is False
    assert record["strong_promotion_eligible"] is False
    assert record["first_missing_source_action"] != "none"


def test_full_text_public_guide_can_be_strong_candidate_only_after_fetch():
    record = acquire_source_record(...)

    assert record["source_visibility"] == "full_text"
    assert record["promotion_eligible"] is True
    assert record["strong_promotion_eligible"] is True
    assert record["first_missing_source_action"] == "none"
```

Use existing fixture-url-map patterns from `tests/test_configure_online_source.py`; do not rely on live network in tests.

- [ ] **Step 2: Run source acquisition tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_acquisition.py tests/test_configure_online_source.py -q
```

Expected before implementation: failure if fields are missing or source families over-promote. Expected after implementation: pass.

- [ ] **Step 3: Add or fix acquired record fields**

In `src/hsconfig/source_acquisition.py`, each acquired source record must carry:

```python
{
    "source_url": source_url,
    "source_title": source_title,
    "source_family": source_family,
    "source_category": source_category,
    "source_visibility": source_visibility,
    "deck_match_scope": deck_match_scope,
    "promotion_eligible": promotion_eligible,
    "strong_promotion_eligible": strong_promotion_eligible,
    "promotion_blockers": promotion_blockers,
    "first_missing_source_action": first_missing_source_action,
}
```

The values must follow this policy:

```python
if source_category in {"decklist", "stats", "snippet"}:
    promotion_eligible = False
    strong_promotion_eligible = False
if source_visibility == "full_text" and deck_match_scope in {"deck_matched", "archetype_matched", "deck_or_archetype_matched"}:
    promotion_eligible = True
```

Strong eligibility still requires later claim-kind normalization and surface closure; acquisition only marks the record as a candidate.

- [ ] **Step 4: Re-run source acquisition tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_acquisition.py tests/test_configure_online_source.py -q
```

Expected: pass.

---

### Task 8: Extend The Universal Wild No-Block Matrix

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: `docs/operator/source-candidate-proof-decks.json`

**Interfaces:**
- Consumes: the exact twelve deck names and codes.
- Produces: regression coverage that every valid Wild deck builds and no deck is blocked by source gaps.

- [ ] **Step 1: Ensure the matrix contains all twelve user decks**

In `tests/test_universal_wild_no_block_matrix.py`, ensure the `DECKS` constant equals the deck matrix above, including `CuteWarrior`.

In `docs/operator/source-candidate-proof-decks.json`, ensure `decks` contains the same twelve names.

- [ ] **Step 2: Add source status assertions for every deck**

For each generated package, assert:

```python
assert operator["technical_status"] == "VALID_PACKAGE"
assert operator["runtime_load_safe"] is True
assert operator["runtime_apply_allowed"] is True
assert operator["runtime_apply_mode"] == "load_safe_apply"
assert operator["source_status_diagnostic_only"] is True
assert operator["source_status_apply_blocking"] is False
assert operator["source_backed_status"] in {"SOURCE_BACKED_STRONG", "SOURCE_BACKED_PARTIAL"}
assert operator["first_missing_source_action"]
if operator["source_backed_status"] != "SOURCE_BACKED_STRONG":
    assert operator["first_missing_source_action"] != "none"
assert operator["default_only_runtime_surfaces"] == []
```

- [ ] **Step 3: Run the matrix tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Expected: all matrix tests pass.

---

### Task 9: Update Operator Docs And Installed Skill

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**
- Consumes: final source-status contract.
- Produces: operator docs and installed skill text aligned with runtime behavior.

- [ ] **Step 1: Add docs-policy assertions**

In `tests/test_operator_docs_contract_policy.py`, assert all three documents contain these exact contract phrases:

```python
REQUIRED_CONTRACT_PHRASES = (
    "operator_summary.json remains the only normal apply authority",
    "SOURCE_BACKED_STRONG is an evidence-quality label",
    "source_status_apply_blocking must remain false",
    "default-only runtime surfaces prevent SOURCE_BACKED_STRONG",
    "Darkbishop Benedictus",
)
```

Add a stale-term rejection list:

```python
STALE_CONTRACT_TERMS = (
    "source report apply authority",
    "candidate url proves strong",
    "default-only strong",
)
```

- [ ] **Step 2: Run docs-policy tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_docs_contract_policy.py -q
```

Expected before docs update: failure if required wording is absent. Expected after update: pass.

- [ ] **Step 3: Update docs and skill text**

Add concise contract text to:

```text
docs/operator/source-backed-strong-closure.md
docs/operator/universal-wild-no-block-contract.md
.agents/skills/hsconfig/SKILL.md
```

The text must state:

```markdown
`operator_summary.json` remains the only normal apply authority.
`SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation or apply gate.
`source_status_apply_blocking` must remain false for source-quality gaps.
Default-only runtime surfaces prevent `SOURCE_BACKED_STRONG`, but do not block a technically valid load-safe package by themselves.
Darkbishop Benedictus preserves start-of-game / hero-power-transform semantics and must not become a mulligan keep without explicit opening-hand source text.
```

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected: check exits 0 and reports the installed `hsconfig` skill is in sync.

- [ ] **Step 5: Re-run docs-policy tests**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_operator_docs_contract_policy.py -q
```

Expected: pass.

---

### Task 10: Final Verification And Handoff

**Files:**
- Verify all files modified by Tasks 1-9.

**Interfaces:**
- Consumes: final diff and test suite.
- Produces: evidence that the plan is complete and safe to review or commit.

- [ ] **Step 1: Run focused test suite**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python -m pytest tests/test_source_acquisition.py tests/test_source_claim_compiler.py tests/test_source_status_resolver.py tests/test_operator_summary.py tests/test_source_bundle.py tests/test_source_evidence_closure.py tests/test_strong_promotion_report.py tests/test_configure_online_source.py tests/test_universal_wild_no_block_matrix.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_operator_docs_contract_policy.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 2: Validate the current ShadowPriest final package if present**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
hsconfig validate --package outputs\2026-07-17-source-backed-strong-optimal\ShadowPriest_online_final\04_package --json
```

Expected:

```json
{"status":"passed"}
```

If the `hsconfig` executable is not on PATH, run:

```powershell
python -m hsconfig.cli validate --package outputs\2026-07-17-source-backed-strong-optimal\ShadowPriest_online_final\04_package --json
```

- [ ] **Step 3: Verify docs/skill sync**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
python scripts/sync_installed_skill.py --check
```

Expected: installed skill is in sync.

- [ ] **Step 4: Verify diff hygiene**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git diff --check
```

Expected: exit code 0.

- [ ] **Step 5: Verify upstream status**

Run:

```powershell
cd C:\Users\darbo\Documents\HSConfig
git fetch --all --prune
git rev-list --left-right --count HEAD...origin/main
git status --short --branch
```

Expected:

```text
0 0
```

and only intended source-contract acceptance files changed.

---

## Subagent Execution Split

- Explorer subagent, read-only:
  - Map the existing source acquisition, claim compiler, resolver, report, and package-builder flow.
  - Report duplicate status logic, hidden default-only paths, and any source report that looks like a second apply gate.
- Research subagent, output-file only:
  - Execute the research outline items and write JSON results only under the Task 1 results directory.
- Test subagent, write-limited to tests:
  - Add failing tests for Tasks 3-8.
- Worker subagent, write-limited to `src/hsconfig`:
  - Implement the minimal source changes required to pass tests.
- Docs subagent, write-limited to docs and skill files:
  - Update operator docs, skill contract, and run skill sync after source/tests are passing.
- Reviewer subagent, read-only:
  - Review final diff for duplicate authority, accidental source blocking, default-only strong promotion, and Darkbishop mulligan regression.

## Acceptance Criteria

- `SOURCE_BACKED_STRONG` is resolved by one canonical path.
- No default-only runtime surface can claim `SOURCE_BACKED_STRONG`.
- Source-quality gaps never set `source_status_apply_blocking=true`.
- Every provided Wild deck remains load-safe and no-block.
- Non-strong decks expose a concrete `first_missing_source_action`.
- ShadowPriest is `SOURCE_BACKED_STRONG` when full-text source closure is present.
- Darkbishop Benedictus effect semantics remain present, while `SW_448` is not kept in mulligan by default.
- Candidate URLs, decklists, snippets, stats, and static card records cannot prove strong strategy by themselves.
- `operator_summary.json`, `source_bundle.json`, `source_evidence_closure.json`, and `strong_promotion_report.json` agree on source status.
- Operator docs and installed `hsconfig` skill are synchronized.
- Focused tests, package validation, skill sync check, and `git diff --check` pass.
