# HSConfig Source Acquisition Strong Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig always create a valid, useful config package from deck input while promoting `SOURCE_BACKED_STRONG` only when public source evidence closes the full source -> claim -> runtime/review chain and no expected runtime surface is silently default-only.

**Architecture:** Keep the existing HSConfig spine: `configure -> source_acquisition -> source_claim_compiler -> source_autopilot -> source_documents -> prepare/package -> operator_summary`. Harden the existing modules with a compact closure ledger instead of adding a parallel engine or second apply gate. Public online sources improve source depth, but weak sources never block package generation; they produce exact first-missing-link diagnostics.

**Tech Stack:** Python 3.11+, pytest, existing HSConfig modules, JSON fixtures, no new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not create or use a shadow workspace.
- Keep HSConfig pre-run only: no replay parsing, no winrate tuning, no HSTuner post-game analysis.
- `reports/operator_summary.json` remains the single normal apply authority.
- `SOURCE_BACKED_STRONG` is an evidence-quality label, not a package-generation gate.
- Every valid decoded deck must produce `technical_status=VALID_PACKAGE`.
- Decklists, search snippets, static card text, policy fallback, and default rows must never prove `SOURCE_BACKED_STRONG` by themselves.
- No expected runtime surface may be silently default-only. It must be `source_backed`, `policy_backed`, `static_semantics_backed`, `not_expected`, `suppressed_with_reason`, or `explicit_gap`.
- Darkbishop Benedictus style start-of-game effects may create `hero_power_transform` or CardID/runtime effect semantics, but not an opening-hand `mulligan_keep` unless an explicit mulligan source says to keep the card.
- Store compact fixtures and structured source records only. Do not commit raw web pages, runtime logs, private logs, or large scraped dumps.

---

## File Structure

Modify:

- `src/hsconfig/source_acquisition.py`
  - Keep the current bounded HTTPS fetcher.
  - Add deterministic source classification fields needed for strong closure: `source_visibility`, `source_lane_hint`, `publication_year`, `source_record_strength`.

- `src/hsconfig/source_claim_compiler.py`
  - Harden text-to-claim rules so only explicit guide text creates lowerable claims.
  - Keep decklist/static records non-promoting.
  - Emit unsupported or ambiguous source text as diagnostics, not runtime claims.

- `src/hsconfig/source_autopilot.py`
  - Add a closure ledger to `source_autopilot_report`.
  - Report `first_missing_source_action_by_card` and strong blockers.

- `src/hsconfig/operator_summary.py`
  - Consume existing closure signals without changing apply authority.
  - Keep strong promotion honest and non-blocking.

- `src/hsconfig/source_to_runtime_explainability.py`
  - Surface per-card source lane, runtime lowering status, and missing link.

- `tests/test_source_acquisition.py`
- `tests/test_source_claim_compiler.py`
- `tests/test_source_autopilot.py`
- `tests/test_multideck_source_backed_e2e.py`
- `tests/test_no_default_only_semantic_archetype_matrix.py`
- `tests/test_shadowpriest_depth_e2e.py`
- `docs/operator/source-backed-strong-closure.md`
- `docs/operator/guide-research-policy.md`
- `docs/operator/source-builder-workflow.md`
- `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

Create:

- `tests/test_source_acquisition_strong_closure.py`
- `tests/fixtures/source_search_11_deck_matrix.json`

---

### Task 1: Source Acquisition Classification Contract

**Files:**
- Create: `tests/test_source_acquisition_strong_closure.py`
- Modify: `src/hsconfig/source_acquisition.py`

**Interfaces:**
- Consumes: `collect_public_source_records(...) -> dict[str, Any]`
- Produces additional fields on each source record:
  - `source_visibility: "full_text" | "snippet_only" | "decklist_only" | "unknown"`
  - `source_lane_hint: "public_guide" | "decklist" | "static_semantics" | "public_page" | "unknown"`
  - `publication_year: int | None`
  - `source_record_strength: "candidate_strong" | "partial" | "diagnostic_only"`

- [ ] **Step 1: Write failing classification tests**

Add `tests/test_source_acquisition_strong_closure.py`:

```python
from __future__ import annotations

from hsconfig.source_acquisition import collect_public_source_records


def _fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    del timeout_seconds
    pages = {
        "https://example.test/shadow-guide": (
            "<html><head><title>Shadow Priest Guide 2026</title></head>"
            "<body><h1>Shadow Priest Mulligan Guide</h1>"
            "<p>Published July 15, 2026.</p>"
            "<p>Mulligan: Keep Papercraft Angel, Twilight Deceptor, Raise Dead, and Shadowbomber.</p>"
            "<p>Darkbishop Benedictus enables the Shadow hero power. Mind Spike can go face or clear minions.</p>"
            "</body></html>"
        ),
        "https://example.test/decklist-only": (
            "<html><head><title>Wild Pirate Demon Hunter Decklist</title></head>"
            "<body><p>Deck code: AAEBA-example</p><ul><li>Patches the Pirate</li></ul></body></html>"
        ),
        "https://example.test/snippet": "<html><body><p>Shadow Priest list.</p></body></html>",
    }
    return 200, "text/html", pages[url].encode("utf-8")


def _resolver(hostname: str) -> list[str]:
    assert hostname == "example.test"
    return ["93.184.216.34"]


def test_acquisition_marks_full_text_guides_as_candidate_strong():
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

    payload = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=["https://example.test/shadow-guide"],
        current_date="2026-07-15",
        fetcher=_fetcher,
        resolver=_resolver,
    )

    record = payload["source_records"][0]
    assert record["source_visibility"] == "full_text"
    assert record["source_lane_hint"] == "public_guide"
    assert record["publication_year"] == 2026
    assert record["source_record_strength"] == "candidate_strong"


def test_acquisition_marks_decklist_and_snippets_non_promoting():
    deck_identity = {
        "deck_name": "PirateDH",
        "deck_slug": "piratedh",
        "deck_code_hash": "sha256:pirate",
        "cards": [{"card_id": "CARD_001", "name": "Patches the Pirate", "cost": 1, "count": 1}],
    }

    payload = collect_public_source_records(
        deck_name="PirateDH",
        deck_identity=deck_identity,
        source_urls=["https://example.test/decklist-only", "https://example.test/snippet"],
        current_date="2026-07-15",
        fetcher=_fetcher,
        resolver=_resolver,
    )

    by_url = {record["source_url"]: record for record in payload["source_records"]}
    assert by_url["https://example.test/decklist-only"]["source_visibility"] == "decklist_only"
    assert by_url["https://example.test/decklist-only"]["source_record_strength"] == "partial"
    assert by_url["https://example.test/snippet"]["source_visibility"] == "snippet_only"
    assert by_url["https://example.test/snippet"]["source_record_strength"] == "diagnostic_only"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_acquisition_strong_closure.py -q
```

Expected: FAIL because the new fields are missing.

- [ ] **Step 3: Implement classification helpers**

In `src/hsconfig/source_acquisition.py`, add helper functions near `_infer_source_family`:

```python
def _source_visibility(source_family: str, text: str) -> str:
    lowered = text.lower()
    if source_family == "decklist":
        return "decklist_only"
    if len(text) < 180:
        return "snippet_only"
    if any(marker in lowered for marker in ("mulligan", "guide", "matchup", "keep ")):
        return "full_text"
    return "unknown"


def _source_lane_hint(source_family: str, visibility: str) -> str:
    if source_family == "guide" and visibility == "full_text":
        return "public_guide"
    if source_family == "decklist":
        return "decklist"
    if source_family in {"static_semantics", "hearthstonejson_static_semantics"}:
        return "static_semantics"
    if visibility == "snippet_only":
        return "unknown"
    return "public_page"


def _publication_year_from_text(text: str) -> int | None:
    for year in range(2020, 2031):
        if str(year) in text:
            return year
    return None


def _source_record_strength(
    *,
    source_family: str,
    visibility: str,
    deck_match_scope: str,
    publication_year: int | None,
    current_date: str | date | None,
) -> str:
    current_year = _current_year(current_date)
    if (
        source_family == "guide"
        and visibility == "full_text"
        and deck_match_scope in {"deck_or_archetype_matched", "deck_matched"}
        and publication_year == current_year
    ):
        return "candidate_strong"
    if visibility in {"decklist_only", "full_text"}:
        return "partial"
    return "diagnostic_only"


def _current_year(current_date: str | date | None) -> int | None:
    if isinstance(current_date, date):
        return current_date.year
    text = str(current_date or "")
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None
```

When appending each source record, compute and include:

```python
source_family = _infer_source_family(url, parsed["text"])
visibility = _source_visibility(source_family, parsed["text"])
publication_year = _publication_year_from_text(f'{parsed["title"]} {parsed["text"]}')
lane_hint = _source_lane_hint(source_family, visibility)
strength = _source_record_strength(
    source_family=source_family,
    visibility=visibility,
    deck_match_scope=deck_match_scope,
    publication_year=publication_year,
    current_date=current_date,
)
```

Add these keys to the record:

```python
"source_visibility": visibility,
"source_lane_hint": lane_hint,
"publication_year": publication_year,
"source_record_strength": strength,
```

- [ ] **Step 4: Run acquisition tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_acquisition.py tests/test_source_acquisition_strong_closure.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add src/hsconfig/source_acquisition.py tests/test_source_acquisition_strong_closure.py
git commit -m "feat: classify acquired sources for strong closure"
```

---

### Task 2: Claim Compiler Strongness Boundary

**Files:**
- Modify: `tests/test_source_claim_compiler.py`
- Modify: `src/hsconfig/source_claim_compiler.py`

**Interfaces:**
- Consumes: acquired source records from Task 1.
- Produces:
  - guide records with explicit mulligan language create lowerable claims.
  - decklist/static/snippet records create visible non-promoting role claims only.
  - effect-only start-of-game cards never become `mulligan_keep`.

- [ ] **Step 1: Add failing compiler tests**

Append to `tests/test_source_claim_compiler.py`:

```python
def test_compile_ignores_keep_without_mulligan_context():
    deck_identity = {
        "deck_name": "EffectDeck",
        "deck_slug": "effectdeck",
        "deck_code_hash": "sha256:effect",
        "cards": [{"card_id": "CARD_001", "name": "Keepable Name", "cost": 1, "count": 2}],
    }
    acquired = [
        {
            "source_url": "https://example.test/no-mulligan",
            "source_title": "EffectDeck Strategy",
            "source_family": "guide",
            "source_visibility": "full_text",
            "source_record_strength": "candidate_strong",
            "deck_match": {"deck_name": "EffectDeck", "archetype": "effectdeck", "matched_card_ids": ["CARD_001"]},
            "deck_match_scope": "deck_or_archetype_matched",
            "normalized_text": "Keepable Name is important later. This page does not discuss mulligan or opening hand.",
        }
    ]

    compiled = compile_source_search_records(
        deck_name="EffectDeck",
        deck_identity=deck_identity,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    assert compiled["records"][0]["mulligan"]["keep_card_ids"] == []
    assert not any(claim["claim_kind"] == "mulligan_keep" for claim in compiled["records"][0]["claims"])
    assert compiled["source_claim_compiler_report"]["unsupported_claims"]


def test_compile_decklist_card_role_is_non_promoting():
    deck_identity = {
        "deck_name": "PirateDH",
        "deck_slug": "piratedh",
        "deck_code_hash": "sha256:pirate",
        "cards": [{"card_id": "CARD_001", "name": "Patches the Pirate", "cost": 1, "count": 1}],
    }
    acquired = [
        {
            "source_url": "https://example.test/decklist",
            "source_title": "Pirate Demon Hunter Decklist",
            "source_family": "decklist",
            "source_visibility": "decklist_only",
            "source_record_strength": "partial",
            "deck_match": {"deck_name": "PirateDH", "archetype": "piratedh", "matched_card_ids": ["CARD_001"]},
            "deck_match_scope": "deck_or_archetype_matched",
            "normalized_text": "Deck code and card list.",
        }
    ]

    compiled = compile_source_search_records(
        deck_name="PirateDH",
        deck_identity=deck_identity,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    claim = compiled["records"][0]["claims"][0]
    assert claim["claim_kind"] == "card_role"
    assert claim["source_confidence"] == "medium"
    assert claim["promotion_eligible"] is False
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_compiler.py -q
```

Expected: FAIL where `promotion_eligible` or unsupported claim diagnostics are missing.

- [ ] **Step 3: Harden emitted claims**

In `src/hsconfig/source_claim_compiler.py`, update `_claim(...)` to accept a `promotion_eligible` keyword:

```python
def _claim(
    claim_kind: str,
    cards: list[str],
    stance: str,
    evidence_text_short: str,
    source_confidence: str,
    *,
    scope: str,
    timing: str | None = None,
    promotion_eligible: bool = True,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "claim_kind": claim_kind,
        "stance": stance,
        "scope": scope,
        "evidence_text_short": evidence_text_short,
        "source_confidence": source_confidence,
        "promotion_eligible": promotion_eligible,
    }
    if cards:
        row["cards"] = cards
    if timing:
        row["timing"] = timing
    return row
```

In `_compile_non_promoting_card_roles(...)`, pass `promotion_eligible=False`.

In `_compile_guide_claims(...)`, before adding `hero_power_transform` from text, pass `promotion_eligible=True`, but keep `timing="start_of_game"` and do not add any mulligan keep row for non-opening-hand effect cards.

- [ ] **Step 4: Make unsupported guide text visible**

After `_compile_guide_claims(...)` returns, keep the existing unsupported claim report and ensure it triggers when the guide contains no explicit lowerable claim:

```python
if source_family in GUIDE_FAMILIES and not compiled["claims"]:
    unsupported_claims.append(
        {
            "source_url": compiled["source_url"],
            "source_title": compiled["source_title"],
            "source_family": compiled["source_family"],
            "reason": "unsupported_or_non_runtime_claim",
            "evidence_text_short": _short_evidence(text),
        }
    )
```

- [ ] **Step 5: Run compiler tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_compiler.py tests/test_claim_kind_runtime_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add src/hsconfig/source_claim_compiler.py tests/test_source_claim_compiler.py
git commit -m "fix: keep compiled source claims promotion honest"
```

---

### Task 3: Source Autopilot Closure Ledger

**Files:**
- Modify: `tests/test_source_autopilot.py`
- Modify: `src/hsconfig/source_autopilot.py`

**Interfaces:**
- Consumes: compiled source search records.
- Produces in `source_autopilot_report`:
  - `strong_candidate_blockers: list[str]`
  - `first_missing_source_action_by_card: dict[str, str]`
  - `non_promoting_claim_count: int`

- [ ] **Step 1: Add failing closure-ledger test**

Append to `tests/test_source_autopilot.py`:

```python
def test_source_autopilot_reports_strong_blockers_per_card():
    payload = _fixture("source_search_decklist_only.json")
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=payload["records"],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    assert report["strong_candidate"] is False
    assert "no_card_specific_runtime_contract_candidate" in report["strong_candidate_blockers"]
    assert report["first_missing_source_action_by_card"]["CARD_001"] == "add_current_deck_guide_or_mulligan_guide"
    assert report["non_promoting_claim_count"] >= 1
```

- [ ] **Step 2: Run the test and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py::test_source_autopilot_reports_strong_blockers_per_card -q
```

Expected: FAIL because the new report fields are missing.

- [ ] **Step 3: Implement blocker helpers**

In `src/hsconfig/source_autopilot.py`, add:

```python
def _strong_candidate_blockers(
    *,
    card_specific_lowerable_guide_rows: Sequence[Mapping[str, Any]],
    apply_surface_guide_rows: Sequence[Mapping[str, Any]],
    draft: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not card_specific_lowerable_guide_rows:
        blockers.append("no_card_specific_runtime_contract_candidate")
    if not apply_surface_guide_rows:
        blockers.append("no_apply_surface_guide_candidate")
    if draft.get("unresolved_mentions"):
        blockers.append("unresolved_source_mentions")
    if verification.get("status") != "passed":
        blockers.append("source_document_verification_failed")
    warnings = verification.get("warnings", [])
    if warnings:
        blockers.append("source_document_warnings")
    return blockers


def _first_missing_source_action_by_card(
    deck_identity: Mapping[str, Any],
    evidence_rows: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    by_card: dict[str, str] = {}
    source_backed_cards = {
        str(card_id)
        for row in evidence_rows
        if _is_strong_guide_lane(row) and _is_runtime_contract_candidate(row)
        for card_id in _as_list(row.get("cards", []))
        if str(card_id)
    }
    for card in deck_identity.get("cards", []):
        if not isinstance(card, Mapping):
            continue
        card_id = _text(card.get("card_id", ""))
        if not card_id:
            continue
        by_card[card_id] = (
            "none"
            if card_id in source_backed_cards
            else "add_current_deck_guide_or_mulligan_guide"
        )
    return by_card


def _non_promoting_claim_count(evidence_rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for row in evidence_rows if row.get("promotion_eligible") is False)
```

Change `_build_report(...)` signature to receive `deck_identity`, or pass only the card list. Use this call:

```python
blockers = _strong_candidate_blockers(
    card_specific_lowerable_guide_rows=card_specific_lowerable_guide_rows,
    apply_surface_guide_rows=apply_surface_guide_rows,
    draft=draft,
    verification=verification,
)
strong_candidate = not blockers
```

Add report fields:

```python
"strong_candidate_blockers": blockers,
"first_missing_source_action_by_card": _first_missing_source_action_by_card(deck_identity, evidence_rows),
"non_promoting_claim_count": _non_promoting_claim_count(evidence_rows),
```

- [ ] **Step 4: Run source-autopilot tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add src/hsconfig/source_autopilot.py tests/test_source_autopilot.py
git commit -m "feat: expose source autopilot closure ledger"
```

---

### Task 4: Operator Summary Strong Promotion Rules

**Files:**
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_source_to_runtime_explainability.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/source_to_runtime_explainability.py`

**Interfaces:**
- Consumes: source reports and package diagnostics.
- Produces:
  - `SOURCE_BACKED_STRONG` only when technical package is valid, source depth is strong, no expected surface is default-only, and no policy/default/snippet row is used as strong evidence.
  - `VALID_PACKAGE` remains true for partial/no-source decks.

- [ ] **Step 1: Add operator strongness regression tests**

Append to `tests/test_operator_summary.py`:

```python
def test_operator_summary_does_not_promote_policy_or_default_rows_to_strong():
    summary = build_operator_summary(
        technical_status="VALID_PACKAGE",
        runtime_apply_allowed=True,
        source_claim_quality_summary={
            "source_quality_lane_counts": {
                "policy_fallback": 2,
                "default_runtime": 1,
                "deck_matched_public_guide": 0,
            }
        },
        default_only_runtime_surfaces=["Mulligan.json"],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert "default_only_surface_not_strong_evidence" in {
        blocker["code"] for blocker in summary["semantic_blockers"]
    }
```

If `build_operator_summary(...)` has a different test helper signature, add a small local helper in the test file that calls the current public summary function with the minimal package fields already used by existing tests.

- [ ] **Step 2: Add explainability regression test**

Append to `tests/test_source_to_runtime_explainability.py`:

```python
def test_explainability_exposes_policy_backed_runtime_as_non_strong():
    report = build_source_to_runtime_explainability_report(
        audit={
            "claim_rows": [
                {
                    "card_id": "CARD_001",
                    "claim_kind": "mulligan_keep",
                    "source_type": "policy_backed_autonomous_mulligan",
                    "source_lane": "policy_fallback",
                    "runtime_backed": True,
                }
            ]
        },
        runtime_files={"Mulligan.json"},
    )

    row = report["card_rows"][0]
    assert row["source_lane"] == "policy_fallback"
    assert row["runtime_lowering_status"] == "policy_backed_runtime"
    assert row["first_missing_source_action"] == "add_explicit_mulligan_source"
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py tests/test_source_to_runtime_explainability.py -q
```

Expected: FAIL only for missing new fields or blocker codes.

- [ ] **Step 4: Harden operator semantic blockers**

In `src/hsconfig/operator_summary.py`, locate the semantic-status calculation and ensure the strong-ready condition includes:

```python
strong_ready = (
    technical_status == "VALID_PACKAGE"
    and runtime_apply_allowed is True
    and not default_only_runtime_surfaces
    and source_quality_lane_counts.get("deck_matched_public_guide", 0) > 0
    and source_quality_lane_counts.get("policy_fallback", 0) == 0
    and source_quality_lane_counts.get("default_runtime", 0) == 0
    and source_quality_lane_counts.get("snippet_only", 0) == 0
)
```

Add blocker codes without adding technical apply blockers:

```python
if default_only_runtime_surfaces:
    semantic_blockers.append({"code": "default_only_surface_not_strong_evidence"})
if source_quality_lane_counts.get("policy_fallback", 0):
    semantic_blockers.append({"code": "policy_claim_not_strong_evidence"})
if source_quality_lane_counts.get("default_runtime", 0):
    semantic_blockers.append({"code": "default_runtime_not_strong_evidence"})
if source_quality_lane_counts.get("snippet_only", 0):
    semantic_blockers.append({"code": "snippet_only_source_not_strong_evidence"})
```

- [ ] **Step 5: Add explainability fields**

In `src/hsconfig/source_to_runtime_explainability.py`, ensure each card row includes:

```python
"source_lane": source_lane,
"runtime_lowering_status": runtime_lowering_status,
"first_missing_source_action": first_missing_source_action,
```

Use this mapping:

```python
if source_lane == "policy_fallback" and runtime_backed:
    runtime_lowering_status = "policy_backed_runtime"
    first_missing_source_action = "add_explicit_mulligan_source"
elif runtime_backed:
    runtime_lowering_status = "source_backed_runtime"
    first_missing_source_action = "none"
elif source_lane:
    runtime_lowering_status = "source_backed_contract_only"
    first_missing_source_action = "map_claim_kind_or_keep_report_only"
else:
    runtime_lowering_status = "missing_source_claim"
    first_missing_source_action = "add_public_guide_source"
```

- [ ] **Step 6: Run targeted tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py tests/test_source_to_runtime_explainability.py tests/test_strong_promotion_report.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/source_to_runtime_explainability.py tests/test_operator_summary.py tests/test_source_to_runtime_explainability.py
git commit -m "fix: keep source-backed strong promotion non-blocking and honest"
```

---

### Task 5: Eleven-Deck Representative Closure Matrix

**Files:**
- Create: `tests/fixtures/source_search_11_deck_matrix.json`
- Modify: `tests/test_multideck_source_backed_e2e.py`
- Modify: `tests/test_no_default_only_semantic_archetype_matrix.py`
- Modify: `docs/operator/archetype-fixture-matrix.json`

**Interfaces:**
- Consumes: representative deck inputs:
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
- Produces: every deck is load-safe, no expected surface is silent default-only, and strong/partial labels are honest.

- [ ] **Step 1: Add the 11-deck source-search fixture**

Create `tests/fixtures/source_search_11_deck_matrix.json`:

```json
{
  "schema_version": 1,
  "records_by_deck": {
    "ShadowPriest": [{"source_family": "guide", "source_visibility": "full_text", "source_record_strength": "candidate_strong", "claims": [{"claim_kind": "hero_power_transform", "cards": ["SW_448"], "source_confidence": "high"}, {"claim_kind": "mulligan_keep", "cards": ["TOY_381"], "source_confidence": "high"}]}],
    "CtAPaladin": [{"source_family": "decklist", "source_visibility": "decklist_only", "source_record_strength": "partial", "claims": [{"claim_kind": "card_role", "cards": ["ICC_820"], "source_confidence": "medium", "promotion_eligible": false}]}],
    "PirateRogue": [{"source_family": "guide", "source_visibility": "full_text", "source_record_strength": "candidate_strong", "claims": [{"claim_kind": "weapon_plan", "cards": ["NEW1_011"], "source_confidence": "high"}]}],
    "BigShaman": [{"source_family": "guide", "source_visibility": "full_text", "source_record_strength": "candidate_strong", "claims": [{"claim_kind": "card_role", "cards": ["ICC_089"], "source_confidence": "high", "runtime_block": "inhand_priority"}]}],
    "Discolock": [{"source_family": "decklist", "source_visibility": "decklist_only", "source_record_strength": "partial", "claims": [{"claim_kind": "card_role", "cards": ["BT_307"], "source_confidence": "medium", "promotion_eligible": false}]}],
    "TreantDruid": [{"source_family": "decklist", "source_visibility": "decklist_only", "source_record_strength": "partial", "claims": [{"claim_kind": "card_role", "cards": ["TRL_343"], "source_confidence": "medium", "promotion_eligible": false}]}],
    "ImbueMage": [{"source_family": "guide", "source_visibility": "full_text", "source_record_strength": "candidate_strong", "claims": [{"claim_kind": "gameplan_posture", "scope": "deck", "source_confidence": "high"}]}],
    "MechPala": [{"source_family": "guide", "source_visibility": "full_text", "source_record_strength": "candidate_strong", "claims": [{"claim_kind": "targeting_rule", "cards": ["GVG_058"], "source_confidence": "high"}]}],
    "Kingslayer": [{"source_family": "guide", "source_visibility": "full_text", "source_record_strength": "candidate_strong", "claims": [{"claim_kind": "weapon_plan", "cards": ["LOOT_033"], "source_confidence": "high"}]}],
    "Boarlock": [{"source_family": "guide", "source_visibility": "full_text", "source_record_strength": "candidate_strong", "claims": [{"claim_kind": "combo_sequence", "cards": ["BAR_027"], "sequence": ["setup", "execute"], "source_confidence": "high"}]}],
    "PirateDH": [{"source_family": "decklist", "source_visibility": "decklist_only", "source_record_strength": "partial", "claims": [{"claim_kind": "card_role", "cards": ["DMF_107"], "source_confidence": "medium", "promotion_eligible": false}]}]
  }
}
```

- [ ] **Step 2: Add expected status table**

In `tests/test_multideck_source_backed_e2e.py`, add:

```python
EXPECTED_REPRESENTATIVE_SOURCE_STATUS = {
    "ShadowPriest": "SOURCE_BACKED_STRONG",
    "CtAPaladin": "SOURCE_BACKED_PARTIAL_UNLESS_EXACT_GUIDE_MATCHED",
    "PirateRogue": "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH",
    "BigShaman": "SOURCE_BACKED_STRONG",
    "Discolock": "SOURCE_BACKED_PARTIAL",
    "TreantDruid": "SOURCE_BACKED_PARTIAL",
    "ImbueMage": "SOURCE_BACKED_STRONG",
    "MechPala": "SOURCE_BACKED_STRONG",
    "Kingslayer": "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH",
    "Boarlock": "SOURCE_BACKED_STRONG",
    "PirateDH": "SOURCE_BACKED_PARTIAL",
}
```

Add a test:

```python
def test_representative_decks_are_load_safe_and_do_not_fake_strong(tmp_path):
    rows = build_representative_multideck_matrix(tmp_path)
    for row in rows:
        expected = EXPECTED_REPRESENTATIVE_SOURCE_STATUS[row["deck_name"]]
        assert row["technical_status"] == "VALID_PACKAGE", row
        assert row["runtime_apply_allowed"] is True, row
        assert row["default_only_runtime_surfaces"] == [], row
        if expected == "SOURCE_BACKED_PARTIAL":
            assert row["semantic_status"] != "SOURCE_BACKED_STRONG", row
        if expected == "SOURCE_BACKED_STRONG":
            assert row["semantic_status"] == "SOURCE_BACKED_STRONG", row
```

If `build_representative_multideck_matrix` does not exist, create it in the test file as a local helper that loops over the existing representative deck fixture builder already used in this module.

- [ ] **Step 3: Extend no-default-only semantic matrix**

In `tests/test_no_default_only_semantic_archetype_matrix.py`, add a table assertion:

```python
def test_representative_matrix_has_no_silent_default_only_surfaces(tmp_path):
    rows = build_no_default_only_matrix(tmp_path)
    for row in rows:
        assert row["technical_status"] == "VALID_PACKAGE", row
        assert row["expected_runtime_surface_status"] in {
            "source_backed",
            "policy_backed",
            "static_semantics_backed",
            "not_expected",
            "suppressed_with_reason",
            "explicit_gap",
        }, row
        assert row.get("silent_default_only") is False, row
```

- [ ] **Step 4: Update operator matrix docs**

In `docs/operator/archetype-fixture-matrix.json`, add or update entries with:

```json
{
  "deck_name": "PirateDH",
  "expected_semantic_status": "SOURCE_BACKED_PARTIAL",
  "first_missing_source_action": "find_explicit_current_wild_piratedh_mulligan_or_gameplay_guide",
  "why_not_strong": "Decklist identity is present, but exact mulligan and runtime sequencing are not public-guide-backed."
}
```

Repeat equivalent `expected_semantic_status`, `first_missing_source_action`, and `why_not_strong` fields for every partial or conditional deck.

- [ ] **Step 5: Run representative tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_multideck_source_backed_e2e.py tests/test_no_default_only_semantic_archetype_matrix.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add tests/fixtures/source_search_11_deck_matrix.json tests/test_multideck_source_backed_e2e.py tests/test_no_default_only_semantic_archetype_matrix.py docs/operator/archetype-fixture-matrix.json
git commit -m "test: prove representative decks are load-safe without fake strong"
```

---

### Task 6: ShadowPriest Strong Canary

**Files:**
- Modify: `tests/test_shadowpriest_depth_e2e.py`
- Modify: `tests/fixtures/source_documents_shadowpriest_strong.json`
- Modify: `tests/fixtures/source_search_shadowpriest_2026.json`

**Interfaces:**
- Consumes: ShadowPriest source fixtures.
- Produces: exact canary for Darkbishop effect semantics, Mind Spike context, no Darkbishop mulligan keep, and strong source closure.

- [ ] **Step 1: Add explicit ShadowPriest canary assertions**

Append to `tests/test_shadowpriest_depth_e2e.py`:

```python
def test_shadowpriest_source_backed_strong_preserves_darkbishop_effect_not_keep(tmp_path):
    package = prepare_shadowpriest_depth_fixture(tmp_path)
    operator = read_json(package / "reports" / "operator_summary.json")
    mulligan = read_json(package / "CustomConfig" / "shadowpriest" / "Mulligan.json")
    darkbishop = read_json(package / "CustomConfig" / "shadowpriest" / "SW_448.json")
    explainability = read_json(package / "reports" / "source_to_runtime_explainability.json")

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert operator["default_only_runtime_surfaces"] == []
    assert "SW_448" not in json.dumps(mulligan)
    assert any(token in json.dumps(darkbishop).lower() for token in ("hero_power", "mind spike", "shadow"))
    sw448 = next(row for row in explainability["card_rows"] if row["card_id"] == "SW_448")
    assert sw448["strongest_claim_kind"] == "hero_power_transform"
    assert sw448["first_missing_source_action"] == "none"
```

If the existing helper names differ, reuse the helper names already present in `tests/test_shadowpriest_depth_e2e.py` and keep the assertions unchanged.

- [ ] **Step 2: Verify fixtures use effect claim, not keep claim**

In `tests/fixtures/source_documents_shadowpriest_strong.json` and `tests/fixtures/source_search_shadowpriest_2026.json`, ensure the Darkbishop claim is:

```json
{
  "claim_kind": "hero_power_transform",
  "cards": ["SW_448"],
  "timing": "start_of_game",
  "source_confidence": "high",
  "promotion_eligible": true
}
```

Ensure no source document contains:

```json
{
  "claim_kind": "mulligan_keep",
  "cards": ["SW_448"]
}
```

- [ ] **Step 3: Run ShadowPriest canary**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_shadowpriest_depth_e2e.py tests/test_source_autopilot.py::test_extract_source_evidence_rows_preserves_darkbishop_effect_not_mulligan_keep -q
```

Expected: PASS.

- [ ] **Step 4: Commit Task 6**

Run:

```powershell
git add tests/test_shadowpriest_depth_e2e.py tests/fixtures/source_documents_shadowpriest_strong.json tests/fixtures/source_search_shadowpriest_2026.json
git commit -m "test: lock shadowpriest source-backed strong canary"
```

---

### Task 7: Docs And Skill Operating Contract

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/source-builder-workflow.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

**Interfaces:**
- Produces one operator-facing rule set matching the code:
  - always build
  - never fake strong
  - no hidden default-only
  - Darkbishop effect/keep boundary

- [ ] **Step 1: Update strong closure doc**

Add to `docs/operator/source-backed-strong-closure.md`:

```markdown
## Strong Closure Rule

HSConfig always attempts to build a technically valid package when the deck code can be decoded.
`SOURCE_BACKED_STRONG` is not required for config generation or apply readiness.

`SOURCE_BACKED_STRONG` requires:

- `technical_status=VALID_PACKAGE`
- `runtime_apply_allowed=true`
- at least one deck-matched public guide or official static semantic source for each strong claim family
- no hidden default-only runtime surface
- no policy fallback, default runtime row, search snippet, or decklist-only row counted as strong evidence
- every expected surface is emitted, explicitly suppressed, or reported as an explicit gap

Darkbishop Benedictus is the canonical boundary: preserve the hero-power-transform effect, but do not infer an opening-hand mulligan keep.
```

- [ ] **Step 2: Update guide research policy**

Add to `docs/operator/guide-research-policy.md`:

```markdown
## Source Lane Promotion

- `deck_matched_public_guide`: may promote lowerable runtime claims when the text is full and explicit.
- `archetype_matched_public_guide`: may promote only when the claim is archetype-stable and card identity matches the current deck.
- `official_static_semantics`: may promote deterministic static/effect claims; it cannot prove opening-hand mulligan keeps.
- `decklist_only`: may prove card presence and archetype identity only.
- `statistical_enrichment`: may explain confidence but cannot prove runtime behavior alone.
- `policy_fallback`: keeps any-deck generation useful but never proves `SOURCE_BACKED_STRONG`.
- `default_runtime`: must remain visible as debt or be replaced/suppressed.
```

- [ ] **Step 3: Update source builder workflow**

Add to `docs/operator/source-builder-workflow.md`:

```markdown
Preferred high-source path:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --source-url "<public-guide-url>" --json
```

If no public guide URL is known, run source acquisition with current public decklist and guide URLs found by Codex research. Thin source coverage must not block package generation; it must write the first missing source action.
```

- [ ] **Step 4: Update installed HSConfig skill**

In `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`, add:

```markdown
When the user asks for an optimal config, use online/public source acquisition when useful and available, but never block generation because a source is weak.
Always produce a load-safe package for a valid deck.
Treat `SOURCE_BACKED_STRONG` as an honest evidence label, not as a creation gate.
Do not count decklist-only, snippet-only, policy fallback, or default runtime rows as strong evidence.
For start-of-game effects such as Darkbishop Benedictus, preserve the effect semantics and hero-power context, but do not add an opening-hand keep unless explicit mulligan guidance says to keep the card.
```

- [ ] **Step 5: Run docs/skill checks**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py -q
rg -n "SOURCE_BACKED_STRONG|decklist_only|policy_fallback|default_runtime|Darkbishop|online-source" docs/operator "C:\Users\darbo\.codex\skills\hsconfig\SKILL.md"
```

Expected: PASS and the `rg` output shows all new policy terms.

- [ ] **Step 6: Commit Task 7**

Run:

```powershell
git add docs/operator/source-backed-strong-closure.md docs/operator/guide-research-policy.md docs/operator/source-builder-workflow.md
git add "C:\Users\darbo\.codex\skills\hsconfig\SKILL.md"
git commit -m "docs: define source acquisition strong closure policy"
```

If git refuses to add the installed skill because it is outside the repo, commit the repo docs and leave the installed skill as a local environment update.

---

### Task 8: Final Verification And GitHub Sync

**Files:**
- No planned source changes.
- Optional generated verification output under ignored `outputs/_verification_source_acquisition_strong_closure`.

**Interfaces:**
- Consumes all completed tasks.
- Produces verified branch state ready for push/merge.

- [ ] **Step 1: Run focused source closure suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_acquisition.py tests/test_source_acquisition_strong_closure.py tests/test_source_claim_compiler.py tests/test_source_autopilot.py tests/test_operator_summary.py tests/test_source_to_runtime_explainability.py -q
```

Expected: PASS.

- [ ] **Step 2: Run representative deck suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_multideck_source_backed_e2e.py tests/test_no_default_only_semantic_archetype_matrix.py tests/test_shadowpriest_depth_e2e.py -q
```

Expected: PASS.

- [ ] **Step 3: Run broad suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: PASS. If the full suite exceeds shell timeout, rerun with a longer timeout and record the exact timeout plus all focused-suite pass results.

- [ ] **Step 4: Run current ShadowPriest package dry run**

Run:

```powershell
$env:PYTHONPATH='src'; python -m hsconfig configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --hdt-deck-id "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602" --hs-id "2737726722" --out "outputs/_verification_source_acquisition_strong_closure" --online-source --auto-source --json
```

Expected:

```text
exit code 0
technical_status=VALID_PACKAGE
runtime_apply_allowed=true
default_only_runtime_surfaces=[]
```

If live online sources are unavailable, rerun with the compact ShadowPriest source fixture and verify the same package invariants.

- [ ] **Step 5: Inspect diff**

Run:

```powershell
git diff --stat
git status --short --branch
```

Expected: only intended source, tests, docs, and optional installed skill file changes.

- [ ] **Step 6: Commit remaining changes**

Run:

```powershell
git add src/hsconfig tests docs/operator docs/superpowers/plans
git commit -m "feat: close source acquisition strong contract"
```

Skip this commit if all task commits already exist and `git status --short` is clean.

- [ ] **Step 7: Push**

Run:

```powershell
git push origin HEAD
```

Expected: push succeeds. If this branch must be merged to main, fast-forward or PR merge only after focused and broad verification are green.

---

## Self-Review Checklist

- [ ] The plan uses the current modules instead of inventing a parallel pipeline.
- [ ] `SOURCE_BACKED_STRONG` remains honest and is not loosened.
- [ ] Weak/no online source coverage never blocks `VALID_PACKAGE`.
- [ ] Every expected runtime surface is visible as backed, suppressed, not expected, or explicit gap.
- [ ] Decklist-only, snippet-only, policy fallback, and default runtime rows do not promote strong.
- [ ] ShadowPriest preserves Darkbishop/Mind Spike semantics without opening-hand keep.
- [ ] The eleven-deck matrix proves the any-deck promise without fake strong labels.
- [ ] No new dependencies are added.
- [ ] Final verification includes focused, representative, and broad tests.
