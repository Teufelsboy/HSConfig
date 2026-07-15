# HSConfig Source-Backed Strong Harvester Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig generate an optimal load-safe config for every valid deck while promoting `SOURCE_BACKED_STRONG` only when the public source -> claim -> runtime/report chain is honestly closed and no expected surface is silently default-only.

**Architecture:** Keep the current HSConfig spine: `configure` -> `source_acquisition` -> `source_claim_compiler` -> `source_autopilot` -> `source_documents` -> package builders -> `operator_summary`. Harden the existing spine with a compact strong-closure ledger and bounded source harvesting; do not add a second runtime engine, second apply authority, browser-only workflow, or blocking human approval gate.

**Tech Stack:** Python 3.11+, pytest, JSON fixtures, existing HSConfig modules, stdlib-only online acquisition, existing installed `hsconfig` skill sync.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not use `C:\Users\darbo\Documents\HS`, temp checkouts, or shadow workspaces for this implementation.
- Always build a technically valid load-safe package for any valid decoded deck.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a package-generation gate.
- `reports/operator_summary.json` remains the only normal apply/operator authority.
- Weak public source coverage must produce `SOURCE_BACKED_PARTIAL` plus exact `first_missing_source_action`, not a blocked config.
- Decklists, snippets, static card text, policy fallback, replay stats, generic archetype inference, and default runtime rows must not prove `SOURCE_BACKED_STRONG` by themselves.
- No expected runtime surface may be hidden as default-only. Every surface must resolve to `source_backed`, `policy_backed`, `static_semantics_backed`, `suppressed_with_reason`, `not_expected`, `explicit_gap`, or `default_only_blocker`.
- Darkbishop Benedictus style start-of-game effects may produce `hero_power_transform` or card behavior semantics, but must never infer `mulligan_keep` unless an explicit opening-hand source says to keep the card.
- Keep source records compact and structured. Do not commit raw long guide pages, runtime logs, HDT files, HearthRanger logs, screenshots, or scraped bulk dumps.
- No new runtime dependencies.

---

## File Structure

Modify:

- `src/hsconfig/source_acquisition.py`
  - Strengthen bounded public source records with `source_visibility`, `source_lane_hint`, `publication_year`, `source_record_strength`, and policy fields.
  - Preserve online failure as non-blocking diagnostics.

- `src/hsconfig/source_claim_compiler.py`
  - Compile only explicit guide text into lowerable source claims.
  - Keep decklist/static/policy rows as non-promoting evidence.
  - Preserve effect-vs-mulligan separation for Darkbishop-like cards.

- `src/hsconfig/source_autopilot.py`
  - Emit a strong-closure summary from ranked sources, evidence rows, source documents, and verification.
  - Report `first_missing_source_action_by_card` and `first_missing_source_action_by_surface`.

- `src/hsconfig/source_to_runtime_explainability.py`
  - Add per-card/per-surface closure rows with runtime lowering status and missing links.

- `src/hsconfig/strong_promotion_report.py`
  - Require the strong-closure ledger to be clean before `SOURCE_BACKED_STRONG_CONFIRMED`.
  - Keep all failures diagnostic and non-apply-blocking.

- `src/hsconfig/operator_summary.py`
  - Surface the strong-closure ledger summary and no-default-only status without changing apply authority.

- `docs/operator/source-backed-strong-closure.md`
  - Document the final Strong contract.

- `docs/operator/source-builder-workflow.md`
  - Document the recommended online-source/autopilot path.

- `docs/operator/guide-research-policy.md`
  - Document which source families may and may not promote.

- `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
  - Sync the installed skill so future deck builds use the new source-backed path and never treat partial source coverage as a hard block.

Create:

- `tests/test_source_backed_strong_harvester_closure.py`
  - End-to-end contract tests for source acquisition -> compiler -> autopilot -> strong promotion.

- `tests/test_strong_closure_ledger.py`
  - Focused tests for closure row semantics and no-default-only blockers.

Modify tests:

- `tests/test_source_acquisition_strong_closure.py`
- `tests/test_source_claim_compiler.py`
- `tests/test_source_autopilot.py`
- `tests/test_source_to_runtime_explainability.py`
- `tests/test_strong_promotion_report.py`
- `tests/test_operator_summary.py`
- `tests/test_multideck_source_backed_e2e.py`
- `tests/test_universal_wild_no_block_matrix.py`
- `tests/test_skill_sync.py`

---

### Task 1: Strong Harvester Contract Tests

**Files:**
- Create: `tests/test_source_backed_strong_harvester_closure.py`
- Modify: `tests/fixtures/source_search_11_deck_matrix.json`

**Interfaces:**
- Consumes: `collect_public_source_records(...) -> dict[str, Any]`
- Consumes: `compile_source_search_records(...) -> dict[str, Any]`
- Consumes: `build_source_autopilot_bundle(...) -> dict[str, Any]`
- Produces: executable tests defining the desired Strong/Partial/no-block behavior.

- [ ] **Step 1: Write the ShadowPriest full-chain test**

Add this test to `tests/test_source_backed_strong_harvester_closure.py`:

```python
from __future__ import annotations

from hsconfig.source_acquisition import collect_public_source_records
from hsconfig.source_claim_compiler import compile_source_search_records
from hsconfig.source_autopilot import build_source_autopilot_bundle


def _shadow_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    del timeout_seconds
    html = """
    <html>
      <head><title>Shadow Priest Mulligan Guide 2026</title></head>
      <body>
        <p>Published July 15, 2026.</p>
        <p>Mulligan: keep Papercraft Angel, Twilight Deceptor, Raise Dead, and Shadowbomber.</p>
        <p>Do not keep any 4 cost or higher cards.</p>
        <p>Darkbishop Benedictus enables the Shadow hero power. Mind Spike can go face or clear enemy minions.</p>
      </body>
    </html>
    """
    return 200, "text/html", html.encode("utf-8")


def _resolver(hostname: str) -> list[str]:
    assert hostname == "example.test"
    return ["93.184.216.34"]


def test_shadowpriest_full_source_chain_promotes_without_benedictus_keep():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
            {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
            {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
        ],
    }
    acquired = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=["https://example.test/shadow-guide"],
        current_date="2026-07-15",
        fetcher=_shadow_fetcher,
        resolver=_resolver,
    )
    compiled = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        acquired_records=acquired["source_records"],
        current_date="2026-07-15",
    )
    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_search_records=compiled["records"],
        current_date="2026-07-15",
    )

    rows = bundle["source_evidence_rows"]
    keep_cards = {
        card_id
        for row in rows
        if row["claim_kind"] == "mulligan_keep"
        for card_id in row["cards"]
    }
    effect_cards = {
        card_id
        for row in rows
        if row["claim_kind"] == "hero_power_transform"
        for card_id in row["cards"]
    }

    assert {"TOY_381", "SW_444", "SCH_514", "GVG_009"} <= keep_cards
    assert "SW_448" not in keep_cards
    assert "SW_448" in effect_cards
    assert bundle["source_autopilot_report"]["strong_closure_summary"]["first_missing_source_action"] == "none"
```

- [ ] **Step 2: Write the partial-source no-block test**

Add this test in the same file:

```python
def _decklist_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    del timeout_seconds
    html = """
    <html>
      <head><title>Wild Pirate Demon Hunter Decklist 2026</title></head>
      <body><p>Deck code: AAEBA-example</p><ul><li>Patches the Pirate</li></ul></body>
    </html>
    """
    return 200, "text/html", html.encode("utf-8")


def test_decklist_only_builds_evidence_but_cannot_promote_strong():
    deck_identity = {
        "deck_name": "PirateDH",
        "deck_slug": "piratedh",
        "deck_code_hash": "sha256:pirate",
        "cards": [{"card_id": "CFM_637", "name": "Patches the Pirate", "cost": 1, "count": 1}],
    }
    acquired = collect_public_source_records(
        deck_name="PirateDH",
        deck_identity=deck_identity,
        source_urls=["https://example.test/pirate-dh-list"],
        current_date="2026-07-15",
        fetcher=_decklist_fetcher,
        resolver=_resolver,
    )
    compiled = compile_source_search_records(
        deck_name="PirateDH",
        deck_identity=deck_identity,
        acquired_records=acquired["source_records"],
        current_date="2026-07-15",
    )
    bundle = build_source_autopilot_bundle(
        deck_name="PirateDH",
        deck_identity=deck_identity,
        source_search_records=compiled["records"],
        current_date="2026-07-15",
    )

    summary = bundle["source_autopilot_report"]["strong_closure_summary"]
    assert summary["technical_no_block"] is True
    assert summary["source_backed_strong_ready"] is False
    assert summary["first_missing_source_action"] == "add_explicit_mulligan_source"
```

- [ ] **Step 3: Run tests and verify failures are specific**

Run:

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_backed_strong_harvester_closure.py -q
```

Expected: FAIL only because `strong_closure_summary` is missing or incomplete.

- [ ] **Step 4: Commit the failing contract tests**

```powershell
git add tests/test_source_backed_strong_harvester_closure.py tests/fixtures/source_search_11_deck_matrix.json
git commit -m "test: define source-backed strong harvester closure"
```

---

### Task 2: Acquisition And Claim Compiler Strongness Hygiene

**Files:**
- Modify: `src/hsconfig/source_acquisition.py`
- Modify: `src/hsconfig/source_claim_compiler.py`
- Modify: `tests/test_source_acquisition_strong_closure.py`
- Modify: `tests/test_source_claim_compiler.py`

**Interfaces:**
- Produces source records with stable fields:
  - `source_visibility`
  - `source_lane_hint`
  - `publication_year`
  - `source_record_strength`
  - `promotion_eligible`
  - `strong_promotion_eligible`
  - `first_missing_source_action`
- Produces compiled claim rows with stable `claim_kind`, `timing`, `promotion_eligible`, and `source_confidence`.

- [ ] **Step 1: Add acquisition assertions for source family ceilings**

Extend `tests/test_source_acquisition_strong_closure.py` with:

```python
def test_acquisition_policy_fields_make_decklist_and_snippet_non_strong():
    deck_identity = {
        "deck_name": "CtAPaladin",
        "deck_slug": "ctapaladin",
        "deck_code_hash": "sha256:cta",
        "cards": [{"card_id": "CFM_650", "name": "Call to Arms", "cost": 4, "count": 2}],
    }

    def fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
        del timeout_seconds
        pages = {
            "https://example.test/decklist": "<html><body><p>Deck code: AAEBA-list</p><p>Call to Arms</p></body></html>",
            "https://example.test/snippet": "<html><body><p>CtA Paladin is popular.</p></body></html>",
        }
        return 200, "text/html", pages[url].encode("utf-8")

    payload = collect_public_source_records(
        deck_name="CtAPaladin",
        deck_identity=deck_identity,
        source_urls=["https://example.test/decklist", "https://example.test/snippet"],
        current_date="2026-07-15",
        fetcher=fetcher,
        resolver=lambda host: ["93.184.216.34"],
    )

    records = {row["source_url"]: row for row in payload["source_records"]}
    assert records["https://example.test/decklist"]["strong_promotion_eligible"] is False
    assert records["https://example.test/decklist"]["first_missing_source_action"] != "none"
    assert records["https://example.test/snippet"]["strong_promotion_eligible"] is False
    assert records["https://example.test/snippet"]["source_visibility"] == "snippet_only"
```

- [ ] **Step 2: Add compiler assertions for explicit-only mulligan**

Extend `tests/test_source_claim_compiler.py` with:

```python
def test_compiler_does_not_turn_key_effect_text_into_mulligan_keep():
    deck_identity = {
        "cards": [
            {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
        ]
    }
    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        acquired_records=[
            {
                "source_family": "guide",
                "source_visibility": "full_text",
                "source_record_strength": "candidate_strong",
                "source_title": "Shadow Priest Guide 2026",
                "source_url": "https://example.test/shadow",
                "publication_year": 2026,
                "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448", "TOY_381"]},
                "deck_match_scope": "deck_and_cards",
                "normalized_text": (
                    "Mulligan: keep Papercraft Angel. "
                    "Darkbishop Benedictus enables the Shadow hero power and Mind Spike."
                ),
            }
        ],
        current_date="2026-07-15",
    )

    claims = [claim for record in payload["records"] for claim in record["claims"]]
    keep_ids = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "mulligan_keep"
        for card_id in claim["cards"]
    }
    transform_ids = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "hero_power_transform"
        for card_id in claim["cards"]
    }
    assert keep_ids == {"TOY_381"}
    assert transform_ids == {"SW_448"}
```

- [ ] **Step 3: Implement minimal acquisition hygiene**

In `src/hsconfig/source_acquisition.py`, keep the existing helpers and adjust only the policy handoff:

```python
policy = classify_source_evidence(
    record,
    deck_name=deck_name,
    current_date=current_date,
)
record.update(_record_policy_fields(policy))
```

Ensure `_record_policy_fields()` preserves at least:

```python
return {
    "promotion_eligible": bool(policy.get("promotion_eligible", False)),
    "strong_promotion_eligible": bool(policy.get("strong_promotion_eligible", False)),
    "promotion_blockers": list(policy.get("promotion_blockers", [])),
    "first_missing_source_action": str(policy.get("first_missing_source_action", "")),
    "source_lane": str(policy.get("source_lane", "")),
    "source_rank_lane": str(policy.get("source_rank_lane", "")),
}
```

- [ ] **Step 4: Implement minimal compiler hygiene**

In `src/hsconfig/source_claim_compiler.py`, enforce these rules in `_compile_guide_claims()` and `_explicit_keep_rows()`:

```python
if _is_non_opening_hand_effect_card(card):
    continue
```

and make non-guide/static/decklist rows non-promoting:

```python
claim["promotion_eligible"] = False
```

- [ ] **Step 5: Run task tests**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_acquisition_strong_closure.py tests/test_source_claim_compiler.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/source_acquisition.py src/hsconfig/source_claim_compiler.py tests/test_source_acquisition_strong_closure.py tests/test_source_claim_compiler.py
git commit -m "fix: keep source acquisition strongness honest"
```

---

### Task 3: Strong Closure Ledger

**Files:**
- Create: `tests/test_strong_closure_ledger.py`
- Modify: `src/hsconfig/source_autopilot.py`
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Modify: `src/hsconfig/strong_promotion_report.py`
- Modify: `tests/test_source_autopilot.py`
- Modify: `tests/test_source_to_runtime_explainability.py`
- Modify: `tests/test_strong_promotion_report.py`

**Interfaces:**
- Produces in `source_autopilot_report`:
  - `strong_closure_summary: dict[str, Any]`
  - `first_missing_source_action_by_card: dict[str, str]`
  - `first_missing_source_action_by_surface: dict[str, str]`
- Produces in explainability card rows:
  - `closure_lane`
  - `strong_ready`
  - `default_only_blocker`

- [ ] **Step 1: Write ledger unit tests**

Create `tests/test_strong_closure_ledger.py`:

```python
from __future__ import annotations

from hsconfig.strong_promotion_report import build_strong_promotion_report


def test_strong_promotion_requires_no_default_only_surfaces():
    report = build_strong_promotion_report(
        deck_name="ShadowPriest",
        fixture_stage="runtime",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "default_only_runtime_surfaces": ["Mulligan.json"],
            "semantic_blockers": [],
        },
        source_claim_gap_report={"summary": {"blocked_cards": 0, "deck_surface_gap_count": 0}},
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["first_missing_source_action"] == "replace_default_only_runtime_surface_with_source_or_policy_claim"


def test_strong_promotion_accepts_closed_chain():
    report = build_strong_promotion_report(
        deck_name="ShadowPriest",
        fixture_stage="runtime",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "default_only_runtime_surfaces": [],
            "semantic_blockers": [],
        },
        source_claim_gap_report={"summary": {"blocked_cards": 0, "deck_surface_gap_count": 0, "first_missing_chain": None}},
    )

    assert report["promotion_ready"] is True
    assert report["first_missing_source_action"] == "none"
```

- [ ] **Step 2: Add autopilot summary assertions**

Extend `tests/test_source_autopilot.py` with:

```python
def test_source_autopilot_report_contains_strong_closure_summary():
    bundle = build_source_autopilot_bundle(
        deck_name="FixtureDeck",
        deck_identity={"cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}]},
        source_search_records=[],
        current_date="2026-07-15",
    )

    summary = bundle["source_autopilot_report"]["strong_closure_summary"]
    assert summary["technical_no_block"] is True
    assert summary["source_backed_strong_ready"] is False
    assert summary["first_missing_source_action"] != "none"
```

- [ ] **Step 3: Implement autopilot summary builder**

In `src/hsconfig/source_autopilot.py`, add a helper used inside `_build_report()`:

```python
def _strong_closure_summary(
    *,
    ranked_sources: Sequence[Mapping[str, Any]],
    evidence_rows: Sequence[Mapping[str, Any]],
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    strong_sources = [
        row for row in ranked_sources
        if row.get("strong_promotion_eligible") is True
    ]
    warning_count = int(verification.get("warning_count", 0) or 0)
    claim_count = len(evidence_rows)
    source_backed_strong_ready = bool(strong_sources) and claim_count > 0 and warning_count == 0
    first_missing = "none" if source_backed_strong_ready else _first_missing_from_sources(ranked_sources)
    return {
        "technical_no_block": True,
        "source_backed_strong_ready": source_backed_strong_ready,
        "strong_source_count": len(strong_sources),
        "claim_count": claim_count,
        "source_evidence_warning_count": warning_count,
        "first_missing_source_action": first_missing,
    }
```

Add `_first_missing_from_sources()`:

```python
def _first_missing_from_sources(ranked_sources: Sequence[Mapping[str, Any]]) -> str:
    for source in ranked_sources:
        action = str(source.get("first_missing_source_action") or "")
        if action and action != "none":
            return action
    return "add_public_guide_url_or_use_static_semantics"
```

- [ ] **Step 4: Thread summary into `source_autopilot_report`**

In `_build_report()`, add:

```python
"strong_closure_summary": _strong_closure_summary(
    ranked_sources=ranked_sources,
    evidence_rows=evidence_rows,
    verification=verification,
),
```

- [ ] **Step 5: Harden explainability rows**

In `src/hsconfig/source_to_runtime_explainability.py`, extend card rows after `runtime_lowering_status` is calculated:

```python
"closure_lane": _closure_lane(related_claims, runtime_backed),
"strong_ready": _closure_lane(related_claims, runtime_backed) == "source_backed_runtime_lowered",
"default_only_blocker": first_missing_link == "default_only_runtime_surface",
```

Add helper:

```python
def _closure_lane(related_claims: list[dict[str, Any]], runtime_backed: bool) -> str:
    if any(claim.get("promotion_eligible") is True for claim in related_claims) and runtime_backed:
        return "source_backed_runtime_lowered"
    if runtime_backed:
        return "runtime_backed_non_strong"
    if any(claim.get("policy_lane") == "policy_fallback" for claim in related_claims):
        return "policy_backed"
    return "explicit_gap"
```

- [ ] **Step 6: Run task tests**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_strong_closure_ledger.py tests/test_source_autopilot.py tests/test_source_to_runtime_explainability.py tests/test_strong_promotion_report.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/source_autopilot.py src/hsconfig/source_to_runtime_explainability.py src/hsconfig/strong_promotion_report.py tests/test_strong_closure_ledger.py tests/test_source_autopilot.py tests/test_source_to_runtime_explainability.py tests/test_strong_promotion_report.py
git commit -m "feat: add source-backed strong closure ledger"
```

---

### Task 4: Multideck No-Default-Only Proof

**Files:**
- Modify: `tests/test_multideck_source_backed_e2e.py`
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `src/hsconfig/operator_summary.py`

**Interfaces:**
- Consumes existing package/report artifacts.
- Produces operator fields:
  - `source_backed_strong_closure`
  - `no_default_only_runtime_status`
  - `first_missing_source_action`

- [ ] **Step 1: Add multideck no-block/Strong split assertions**

Extend `tests/test_multideck_source_backed_e2e.py` with a matrix assertion:

```python
def test_multideck_matrix_never_blocks_valid_config_but_keeps_strong_honest():
    expected_partial = {
        "CtAPaladin",
        "Discolock",
        "TreantDruid",
        "Kingslayer",
        "Boarlock",
        "PirateDH",
    }
    expected_strong_or_strong_ready = {
        "ShadowPriest",
        "PirateRogue",
        "BigShaman",
        "ImbueMage",
        "MechPala",
    }

    for deck_name, row in load_multideck_fixture_rows():
        assert row["technical_status"] == "VALID_PACKAGE"
        assert row["operator_summary"]["next_action"] in {
            "READY_TO_APPLY_OR_HANDOFF",
            "SOURCE_CLOSURE_NEEDED",
        }
        if deck_name in expected_partial:
            assert row["operator_summary"]["semantic_status"] != "SOURCE_BACKED_STRONG" or row["strong_promotion_report"]["promotion_ready"] is False
            assert row["strong_promotion_report"]["first_missing_source_action"] != "none"
        if deck_name in expected_strong_or_strong_ready:
            assert row["operator_summary"]["default_only_runtime_surfaces"] == []
```

If `load_multideck_fixture_rows()` does not exist, add it in the test file as a local helper that loads the current fixture JSON already used by that file.

- [ ] **Step 2: Add operator summary assertions**

Extend `tests/test_operator_summary.py`:

```python
def test_operator_summary_exposes_no_default_only_status_without_apply_gate_change():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        generated_files=["Mulligan.json", "GlobalValues.json"],
        source_to_runtime_explainability_report={
            "summary": {"cards_with_first_missing_link": 0},
            "card_rows": [],
        },
        strong_promotion_report={
            "promotion_ready": True,
            "first_missing_source_action": "none",
        },
    )

    assert summary["apply_authority"] == "operator_summary"
    assert summary["source_backed_strong_closure"]["first_missing_source_action"] == "none"
    assert summary["no_default_only_runtime_status"] in {"clean", "not_reported"}
```

- [ ] **Step 3: Implement operator summary fields**

In `src/hsconfig/operator_summary.py`, add fields near the existing source/report summary output:

```python
"source_backed_strong_closure": _source_backed_strong_closure(strong_promotion_report),
"no_default_only_runtime_status": _no_default_only_runtime_status(default_only_runtime_surfaces),
```

Add helpers:

```python
def _source_backed_strong_closure(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {"status": "not_reported", "first_missing_source_action": "unknown"}
    return {
        "status": "ready" if report.get("promotion_ready") is True else "needs_source_closure",
        "first_missing_source_action": str(report.get("first_missing_source_action", "unknown")),
        "promotion_ready": report.get("promotion_ready") is True,
    }


def _no_default_only_runtime_status(surfaces: list[str] | None) -> str:
    if surfaces is None:
        return "not_reported"
    return "clean" if not surfaces else "has_default_only_surfaces"
```

- [ ] **Step 4: Run task tests**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_operator_summary.py tests/test_multideck_source_backed_e2e.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/operator_summary.py tests/test_operator_summary.py tests/test_multideck_source_backed_e2e.py tests/test_universal_wild_no_block_matrix.py
git commit -m "feat: expose strong closure and no-default-only status"
```

---

### Task 5: Operator Docs And Installed Skill Sync

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/source-builder-workflow.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
- Modify: `tests/test_skill_sync.py`
- Modify: `tests/test_docs_active_path.py`

**Interfaces:**
- Produces documented normal command path:
  - `hsconfig configure --deck-name <name> --deck-code <code> --online-source --auto-source --apply`
- Produces documented contract:
  - valid config always
  - Strong only on closed source chain
  - partial source coverage exposes next action

- [ ] **Step 1: Add docs assertions**

Extend `tests/test_docs_active_path.py`:

```python
from pathlib import Path


def test_docs_define_source_backed_strong_without_second_gate():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "operator" / "source-backed-strong-closure.md").read_text(encoding="utf-8")

    assert "SOURCE_BACKED_STRONG is an evidence-quality label" in text
    assert "operator_summary.json remains the only normal apply authority" in text
    assert "valid load-safe config" in text
    assert "default-only" in text
```

- [ ] **Step 2: Update `source-backed-strong-closure.md`**

Ensure the file contains this exact contract paragraph:

```markdown
`SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation gate. HSConfig must still build a valid load-safe config when public source coverage is partial. A deck or surface may only be Strong when every lowerable claim has visible source text or deterministic official static semantics, no expected runtime surface is default-only, and `first_missing_source_action` is `none`.
```

- [ ] **Step 3: Update workflow docs**

In `docs/operator/source-builder-workflow.md`, document the normal path:

Add this text:

```text
Recommended fresh deck command:
```

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --online-source --auto-source --apply
```

Add this paragraph:

```text
If public sources are thin, the command still writes a valid package and reports the first missing source action. Do not manually relabel `SOURCE_BACKED_PARTIAL` as `SOURCE_BACKED_STRONG`.
```

- [ ] **Step 4: Update installed skill**

In `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`, ensure the “fresh config” path says:

```markdown
For an optimal fresh deck config, prefer the source-backed path:
`hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --online-source --auto-source --apply`.

Do not block a valid deck because public guide coverage is thin. Build the load-safe config, keep `operator_summary.json` as the apply authority, and report `first_missing_source_action` when `SOURCE_BACKED_STRONG` is not honestly closed.
```

- [ ] **Step 5: Verify skill sync**

Run:

```powershell
python scripts/sync_installed_skill.py --check
```

Expected: PASS. If it fails because the repo skill copy differs from the installed skill, run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

- [ ] **Step 6: Run docs tests**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_docs_active_path.py tests/test_skill_sync.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add docs/operator/source-backed-strong-closure.md docs/operator/source-builder-workflow.md docs/operator/guide-research-policy.md tests/test_docs_active_path.py tests/test_skill_sync.py
git add C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
git commit -m "docs: document source-backed strong closure workflow"
```

---

### Task 6: Final Verification And Git Hygiene

**Files:**
- No planned code changes.

**Interfaces:**
- Produces final evidence that the implementation is complete and current.

- [ ] **Step 1: Run targeted test suite**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_backed_strong_harvester_closure.py tests/test_source_acquisition_strong_closure.py tests/test_source_claim_compiler.py tests/test_source_autopilot.py tests/test_source_to_runtime_explainability.py tests/test_strong_promotion_report.py tests/test_operator_summary.py tests/test_multideck_source_backed_e2e.py tests/test_universal_wild_no_block_matrix.py tests/test_docs_active_path.py tests/test_skill_sync.py -q
```

Expected: PASS.

- [ ] **Step 2: Run wider no-block/source contract suite**

```powershell
$env:PYTHONPATH='src'
python -m pytest tests/test_source_evidence_policy.py tests/test_source_autopilot.py tests/test_source_to_runtime_explainability.py tests/test_strong_promotion_report.py tests/test_universal_wild_no_block_matrix.py tests/test_multideck_source_backed_e2e.py tests/test_configure_online_source.py tests/test_configure_auto_source.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full test suite if targeted suite is green**

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: Verify installed skill sync**

```powershell
python scripts/sync_installed_skill.py --check
```

Expected: `HSConfig skill is in sync`.

- [ ] **Step 5: Review changed files**

```powershell
git status --short
git diff --stat
git diff -- docs/operator/source-backed-strong-closure.md docs/operator/source-builder-workflow.md docs/operator/guide-research-policy.md
git diff -- src/hsconfig/source_acquisition.py src/hsconfig/source_claim_compiler.py src/hsconfig/source_autopilot.py src/hsconfig/source_to_runtime_explainability.py src/hsconfig/strong_promotion_report.py src/hsconfig/operator_summary.py
```

Expected: only files from this plan changed.

- [ ] **Step 6: Commit final verification metadata if needed**

If Task 6 creates no file changes, do not create an empty commit. If docs or sync files changed during final verification, commit them:

```powershell
git add docs/operator C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
git commit -m "chore: finalize source-backed strong closure docs"
```

- [ ] **Step 7: Push current branch**

```powershell
git push
```

Expected: branch is current on GitHub.

---

## Self-Review Checklist

- Spec coverage: The plan covers source acquisition, claim compiler, source-to-runtime explainability, no-default-only proof, Strong promotion, operator docs, installed skill sync, and final verification.
- No second gate: `operator_summary.json` remains the only normal apply authority.
- No fake Strong: decklists, snippets, static facts, policy rows, default rows, and archetype inference cannot independently promote.
- No blocked deck: partial source coverage must still produce a valid package with `first_missing_source_action`.
- Darkbishop boundary: effect semantics remain runtime-visible; opening-hand keep requires explicit mulligan source.
- Slimness: no new runtime dependencies, no browser-only workflow, no parallel engine.
- Execution mode: Implement with `superpowers:subagent-driven-development`; one subagent per task, with review between tasks.
