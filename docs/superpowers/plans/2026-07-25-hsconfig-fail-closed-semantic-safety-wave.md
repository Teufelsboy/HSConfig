# HSConfig Fail-Closed Semantic Safety Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every behavior change and `superpowers:verification-before-completion` before declaring the work complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig fail closed whenever public-source evidence, VisionAI conditions, target semantics, or per-card runtime intent are ambiguous, while preserving load-safe package generation and exposing an honest semantic handoff status separate from source strength.

**Architecture:** Keep the existing `configure -> source acquisition/autopilot -> claim lifecycle -> surface routers -> compilers -> validation -> operator summary -> guarded apply` pipeline. Harden the existing boundaries instead of adding another pipeline or apply gate: normalize source context once, reject broadened conditions, require runtime-surface-specific evidence, remove untraced generic rows, validate physical runtime semantics, and project semantic readiness separately from technical load safety.

**Tech Stack:** Python 3.11+, `pytest`, standard library only, existing `hsconfig` CLI and report contracts, PowerShell, Git/GitHub.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Do not add HSTuner, replay parsing, runtime-log analysis, win-rate analysis, candidate promotion, or gameplay sequencing to HSConfig.
- Do not write to `C:\Users\darbo\Desktop\HS` during implementation or verification.
- Runtime writes remain available only through `hsconfig apply` or `hsconfig configure --apply`; this plan never invokes either.
- Preserve `reports/operator_summary.json` as the only normal apply authority.
- Preserve technical load-safe package generation when source evidence is partial; semantic attention remains diagnostic and non-blocking.
- Preserve exact deck/CardID identity and the Darkbishop effect-versus-Mulligan boundary.
- Normal output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for exact ordered, condition-safe combo evidence.
- Do not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- Do not add third-party dependencies.
- Use one canonical branch only. Do not create another feature branch or worktree.
- Keep local and GitHub state synchronized after every implementation commit.
- Finish with a clean worktree, no open pull request, and only the canonical `main` branch locally and remotely.

## Superseded Narrow Plans

This plan incorporates and supersedes the unimplemented scope of:

- `docs/superpowers/plans/2026-07-25-hsconfig-runtime-row-explainability-tightening.md`
- `docs/superpowers/plans/2026-07-25-hsconfig-shadowpriest-visionai-semantic-surface-audit.md`

Do not execute those plans separately after this plan begins.

## File Responsibility Map

### New files

- `src/hsconfig/source_claim_context.py`
  - Owns reusable opening-hand context and boilerplate-evidence predicates.
- `src/hsconfig/semantic_runtime_gate.py`
  - Owns the final semantic decision for whether a classified card intent may become an actionable VisionAI row.
- `tests/test_semantic_runtime_gate.py`
  - Unit contract for conditional, automatic-trigger, liability, and report-only intent decisions.
- `tests/test_shadowpriest_semantic_safety_wave.py`
  - Exact 30-card ShadowPriest package regression and report/runtime parity proof.

### Existing files modified by responsibility

- `src/hsconfig/source_claim_compiler.py`
  - Uses shared context predicates and stricter explicit combo evidence.
- `src/hsconfig/source_text_claim_extractor.py`
  - Stops independently broadening generic “keep” prose into Mulligan evidence.
- `src/hsconfig/source_acquisition.py`
  - Extracts explicit publication metadata and records quantitative deck overlap.
- `src/hsconfig/source_autopilot.py`
  - Distinguishes exact-deck, archetype, and card-overlap lanes.
- `src/hsconfig/condition_format.py`
  - Rejects a structured condition if any supplied atom is invalid.
- `src/hsconfig/combo_plan.py`
  - Suppresses a combo when its runtime condition is unsupported.
- `src/hsconfig/card_behavior_surface_router.py`
  - Requires actual target authority and applies the semantic runtime gate.
- `src/hsconfig/card_intent_taxonomy.py`
  - Gives risky mechanics precise intent reasons instead of broad “damage” or “board tempo” labels.
- `src/hsconfig/compile_cardid.py`
  - Serializes explicit behavior rows only; no unconditional generic priorities or pressure bonuses.
- `src/hsconfig/config_quality_contract.py`
  - Compares physical CardID rows with report rows and exposes semantic-surface attention.
- `src/hsconfig/validate_package.py`
  - Validates required surface blocks, allowed row keys, conditions, selectors, CardIDs, and numeric values.
- `src/hsconfig/globalvalues_baseline.py`
  - Provides a current complete bundled fallback snapshot with explicit provenance.
- `src/hsconfig/compile_globalvalues.py`
  - Reports every expected overlay key as emitted or missing.
- `src/hsconfig/config_readiness.py`
  - Separates file presence from semantically meaningful runtime closure.
- `src/hsconfig/commands/configure.py`
  - Projects `load_safe_to_install` and `semantic_handoff_status` without creating another apply gate.
- `.agents/skills/hsconfig/SKILL.md` and operator docs
  - Document the new fail-closed semantic contract.

---

### Task 1: Canonicalize The Repository To One Main Branch

**Files:**

- No source files modified.
- Git refs affected: local `main`, local `codex/hsconfig-semantic-intent-scoring`, `origin/main`, `origin/codex/hsconfig-semantic-intent-scoring`.

**Interfaces:**

- Consumes: the committed plan and all existing commits on `codex/hsconfig-semantic-intent-scoring`.
- Produces: `main` at the exact previous feature-branch HEAD, no feature branch, no open PR, clean local/remote parity.

- [ ] **Step 1: Refresh refs and prove the starting tree is clean**

Run:

```powershell
git fetch --all --prune --tags
git remote prune origin
git status --short --branch
git branch -vv --all
gh pr list --repo Teufelsboy/HSConfig --state open --json number,headRefName,baseRefName,url
```

Expected:

```text
The worktree has no staged or unstaged paths.
The current feature branch is not behind its upstream.
There is no open pull request.
```

- [ ] **Step 2: Fast-forward the canonical branch**

Run:

```powershell
git switch main
git merge --ff-only codex/hsconfig-semantic-intent-scoring
git push origin main
```

Expected:

```text
main and origin/main resolve to the same commit as the former feature branch.
```

- [ ] **Step 3: Remove the redundant branch locally and remotely**

Run:

```powershell
git push origin --delete codex/hsconfig-semantic-intent-scoring
git branch -d codex/hsconfig-semantic-intent-scoring
git fetch --all --prune --tags
git branch -vv --all
```

Expected:

```text
Only main and origin/main remain.
```

- [ ] **Step 4: Verify canonical parity before code work**

Run:

```powershell
python scripts/check_hsconfig_currentness.py --cwd . --json
git rev-list --left-right --count origin/main...HEAD
git status --short --branch
```

Expected:

```text
behind_origin_main is 0
ahead_origin_main is 0
rev-list prints 0  0
the worktree is clean
```

---

### Task 2: Unify Source Context And Reject False Strong Evidence

**Files:**

- Create: `src/hsconfig/source_claim_context.py`
- Modify: `src/hsconfig/source_claim_compiler.py`
- Modify: `src/hsconfig/source_text_claim_extractor.py`
- Modify: `src/hsconfig/source_acquisition.py`
- Modify: `src/hsconfig/source_autopilot.py`
- Test: `tests/test_source_claim_compiler.py`
- Test: `tests/test_source_autopilot.py`
- Test: `tests/test_configure_online_source.py`
- Test: `tests/test_source_acquisition.py`

**Interfaces:**

- Consumes: normalized source text, parsed publication metadata, deck identity rows.
- Produces:
  - `has_explicit_mulligan_context(text: str) -> bool`
  - `is_content_evidence(text: str) -> bool`
  - `is_explicit_combo_sentence(sentence: str, card_names: list[str]) -> bool`
  - acquisition fields `matched_card_count`, `unique_deck_card_count`, `card_overlap_ratio`, and an honest `deck_match_scope`.

- [ ] **Step 1: Write failing shared-context tests**

Add to `tests/test_source_claim_compiler.py`:

```python
def test_compiler_rejects_navigation_text_as_combo_or_gameplan():
    records = [
        {
            "source_url": "https://example.test/shadow-priest",
            "source_title": "Shadow Priest",
            "source_family": "guide",
            "source_visibility": "full_text",
            "source_record_strength": "candidate_strong",
            "deck_match_scope": "deck_matched",
            "publication_year": 2026,
            "normalized_text": (
                "Follow Us On Twitter Join us on Discord Home Cards "
                "Into the Emerald Dream Acupuncture Mind Blast Papercraft Angel"
            ),
        }
    ]

    compiled = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        source_search_records=records,
        current_date="2026-07-25",
    )

    assert [
        claim
        for claim in compiled["sources"][0]["claims"]
        if claim["claim_kind"] in {"combo_sequence", "gameplan_posture"}
    ] == []
```

Add to `tests/test_source_autopilot.py`:

```python
def test_autopilot_does_not_turn_keep_alive_into_mulligan_keep():
    ranked = [
        _strong_ranked_source(
            normalized_text=(
                "Strategy: Keep Voidtouched Attendant alive on the board "
                "so its aura continues."
            )
        )
    ]

    rows = extract_source_evidence_rows(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        ranked_sources=ranked,
        current_date="2026-07-25",
    )

    assert [row for row in rows if row["claim_kind"] == "mulligan_keep"] == []
```

- [ ] **Step 2: Run the tests and verify the current duplicate extractor fails**

Run:

```powershell
python -m pytest tests/test_source_claim_compiler.py::test_compiler_rejects_navigation_text_as_combo_or_gameplan tests/test_source_autopilot.py::test_autopilot_does_not_turn_keep_alive_into_mulligan_keep -v
```

Expected:

```text
At least one test fails because broad source text becomes a combo, gameplan, or Mulligan claim.
```

- [ ] **Step 3: Create the shared source-context module**

Create `src/hsconfig/source_claim_context.py`:

```python
from __future__ import annotations

import re


MULLIGAN_CONTEXT_MARKERS = ("mulligan", "opening hand", "opening-hand")
BOILERPLATE_MARKERS = (
    "follow us on twitter",
    "follow us on bluesky",
    "join us on discord",
    "help sign in",
    "home cards",
    "like us on facebook",
)
EXPLICIT_COMBO_MARKERS = ("combo sequence", "combo:", "sequence:")
ORDERED_CONNECTORS = (" then ", " into ", " followed by ", " + ", " -> ")


def has_explicit_mulligan_context(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return any(marker in lowered for marker in MULLIGAN_CONTEXT_MARKERS)


def is_content_evidence(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return bool(lowered) and not any(marker in lowered for marker in BOILERPLATE_MARKERS)


def is_explicit_combo_sentence(sentence: str, card_names: list[str]) -> bool:
    lowered = " ".join(sentence.lower().split())
    if len(lowered) > 500 or not is_content_evidence(lowered):
        return False
    positions = sorted(
        lowered.find(name.lower())
        for name in card_names
        if name and lowered.find(name.lower()) >= 0
    )
    if len(positions) < 2:
        return False
    if any(marker in lowered for marker in EXPLICIT_COMBO_MARKERS):
        return True
    return any(connector in lowered for connector in ORDERED_CONNECTORS)
```

- [ ] **Step 4: Make both claim paths use the shared contract**

In `source_claim_compiler.py`:

```python
from hsconfig.source_claim_context import (
    has_explicit_mulligan_context,
    is_content_evidence,
    is_explicit_combo_sentence,
)
```

Replace the local `_has_explicit_mulligan_context` calls with the shared function. In `_compile_combo_sequence_claims`, collect the mentioned card names and require:

```python
if not is_explicit_combo_sentence(sentence, mentioned_card_names):
    continue
```

Require `is_content_evidence(evidence_text)` before appending deckwide gameplan posture.

In `source_text_claim_extractor.py`, require both:

```python
if not has_explicit_mulligan_context(segment):
    continue
if not is_content_evidence(segment):
    continue
```

Remove any now-duplicated local Mulligan-context helper.

- [ ] **Step 5: Write failing publication and deck-match tests**

Add to `tests/test_source_acquisition.py`:

```python
def test_footer_year_does_not_make_old_guide_current():
    html = b"""
    <html>
      <head><title>Shadow Priest Guide</title></head>
      <body>
        <article><p>Published 2021. Mulligan: keep Mind Blast.</p></article>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """

    result = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        source_urls=["https://example.test/guide"],
        current_date="2026-07-25",
        fetcher=lambda _url, _timeout: (200, "text/html", html),
        resolver=lambda _host: ["93.184.216.34"],
    )

    record = result["source_records"][0]
    assert record["publication_year"] is None
    assert record["source_record_strength"] != "candidate_strong"
```

```python
def test_explicit_article_published_time_is_used():
    html = b"""
    <html>
      <head>
        <meta property="article:published_time" content="2026-05-03T12:00:00Z">
        <title>Shadow Priest Guide</title>
      </head>
      <body><article>Mulligan: keep Mind Blast.</article></body>
    </html>
    """

    result = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        source_urls=["https://example.test/guide"],
        current_date="2026-07-25",
        fetcher=lambda _url, _timeout: (200, "text/html", html),
        resolver=lambda _host: ["93.184.216.34"],
    )

    assert result["source_records"][0]["publication_year"] == 2026
```

```python
def test_five_of_sixteen_cards_is_archetype_not_exact_deck_match():
    identity = _identity_with_unique_cards(16)
    text = "ShadowPriest guide " + " ".join(
        card["name"] for card in identity["cards"][:5]
    )

    evidence, scope = _deck_match_evidence(
        "ShadowPriest",
        identity,
        "ShadowPriest Guide",
        text,
    )

    assert evidence["matched_card_count"] == 5
    assert evidence["unique_deck_card_count"] == 16
    assert evidence["card_overlap_ratio"] == 0.3125
    assert scope == "archetype_matched"
```

- [ ] **Step 6: Run the new source-classification tests**

Run:

```powershell
python -m pytest tests/test_source_acquisition.py -k "footer_year or article_published_time or five_of_sixteen" -v
```

Expected:

```text
The footer and overlap tests fail with the current full-text year scan and one-card deck match.
```

- [ ] **Step 7: Parse explicit publication metadata and quantitative overlap**

Extend `_VisibleTextParser` with:

```python
self.publication_values: list[str] = []
```

In `handle_starttag`, preserve the existing skip/title behavior and add:

```python
attributes = {str(key).lower(): str(value or "") for key, value in attrs}
if normalized_tag == "meta":
    marker = (attributes.get("property") or attributes.get("name") or "").lower()
    if marker in {
        "article:published_time",
        "article:modified_time",
        "date",
        "datepublished",
        "datemodified",
    }:
        content = attributes.get("content", "").strip()
        if content:
            self.publication_values.append(content)
if normalized_tag == "time":
    value = attributes.get("datetime", "").strip()
    if value:
        self.publication_values.append(value)
```

Return `publication_values` from `extract_visible_text`. Replace `_publication_year_from_text` with:

```python
def _publication_year_from_metadata(
    values: Sequence[str],
    *,
    current_date: str | date | None = None,
) -> int | None:
    current_year = _current_year(current_date)
    for value in values:
        match = re.search(r"\b(20[2-3]\d)\b", str(value))
        if not match:
            continue
        year = int(match.group(1))
        if current_year is None or year <= current_year:
            return year
    return None
```

Update `_deck_match_evidence`:

```python
unique_deck_card_ids = {
    str(card.get("card_id", ""))
    for card in deck_identity.get("cards", [])
    if isinstance(card, Mapping) and str(card.get("card_id", ""))
}
matched_unique = sorted(set(matched_card_ids))
overlap_ratio = (
    len(matched_unique) / len(unique_deck_card_ids)
    if unique_deck_card_ids
    else 0.0
)
if deck_name_evidenced and overlap_ratio >= 0.80:
    scope = "deck_matched"
elif deck_name_evidenced and len(matched_unique) >= 2:
    scope = "archetype_matched"
elif matched_unique:
    scope = "card_overlap"
else:
    scope = "unknown"
```

Add the count and ratio fields to the returned `deck_match` mapping.

- [ ] **Step 8: Make exact-deck strength require exact-deck evidence**

In `_source_record_strength`, allow `candidate_strong` only for `deck_match_scope == "deck_matched"`.

Change the `_rank_lane` signature so the quantitative acquisition result, not
the older Boolean heuristic, is authoritative:

```python
def _rank_lane(
    family: str,
    card_overlap: int,
    current_year: int | None,
    source: Mapping[str, Any],
    *,
    deck_match_scope: str,
) -> str:
```

Update the only call in `rank_public_sources`:

```python
deck_match_scope = str(match.get("deck_match_scope", "unknown"))
row["source_rank_lane"] = _rank_lane(
    family,
    card_overlap,
    current_year,
    row,
    deck_match_scope=deck_match_scope,
)
```

Then use:

```python
if (
    family in GUIDE_FAMILIES
    and deck_match_scope == "deck_matched"
    and current_year is not None
    and _publication_year(source) == current_year
):
    return "guide_current_deck_match"
if family in GUIDE_FAMILIES and deck_match_scope == "archetype_matched":
    return "guide_current_archetype_match"
```

Do not map `guide_current_archetype_match` to `deck_matched_public_guide`. Keep its card-specific claims eligible only through existing claim-level/card-overlap policy; it must not grant deckwide exact-list closure.

- [ ] **Step 9: Run source-focused suites**

Run:

```powershell
python -m pytest tests/test_source_claim_compiler.py tests/test_source_autopilot.py tests/test_source_acquisition.py tests/test_configure_online_source.py -q
```

Expected:

```text
All tests pass; generic keep prose, navigation claims, footer freshness, and five-of-sixteen exact-deck promotion are rejected.
```

- [ ] **Step 10: Commit and push**

Run:

```powershell
git add src/hsconfig/source_claim_context.py src/hsconfig/source_claim_compiler.py src/hsconfig/source_text_claim_extractor.py src/hsconfig/source_acquisition.py src/hsconfig/source_autopilot.py tests/test_source_claim_compiler.py tests/test_source_autopilot.py tests/test_source_acquisition.py tests/test_configure_online_source.py
git commit -m "fix: fail closed on public source evidence"
git push origin main
```

---

### Task 3: Make Runtime Condition Lowering Atomic And Fail Closed

**Files:**

- Modify: `src/hsconfig/condition_format.py`
- Modify: `src/hsconfig/combo_plan.py`
- Test: `tests/test_condition_format.py`
- Test: `tests/test_combo_plan.py`
- Test: `tests/test_card_behavior_router.py`
- Test: `tests/test_compile_mulligan.py`

**Interfaces:**

- Consumes: raw string or structured source condition.
- Produces: `lower_runtime_condition(value: Any) -> tuple[str, str | None]`, where every supplied atom is safe or the entire condition returns `("*", "unsupported_condition")`.

- [ ] **Step 1: Write failing atomicity tests**

Add to `tests/test_condition_format.py`:

```python
def test_coin_plus_invalid_hand_card_fails_closed():
    condition, reason = lower_runtime_condition(
        {"coin": True, "hand_contains": "BAD-ID"}
    )

    assert condition == "*"
    assert reason == "unsupported_condition"
```

```python
def test_hand_contains_any_fails_when_one_card_is_invalid():
    condition, reason = lower_runtime_condition(
        {"hand_contains_any": ["EX1_001", "BAD-ID"]}
    )

    assert condition == "*"
    assert reason == "unsupported_condition"
```

Add to `tests/test_combo_plan.py`:

```python
def test_combo_with_unsupported_condition_is_suppressed():
    claim = {
        "claim_id": "combo-condition",
        "claim_kind": "combo_sequence",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "20"],
        "conditions": {"unknown": "value"},
    }

    plan = build_combo_plan(
        deck_cards={"EX1_001", "EX1_002"},
        claims=[claim],
    )

    assert plan["combos"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "combo-condition",
            "cards": ["EX1_001", "EX1_002"],
            "reason": "unsupported_condition",
        }
    ]
```

- [ ] **Step 2: Verify the current code broadens the conditions**

Run:

```powershell
python -m pytest tests/test_condition_format.py -k "invalid_hand_card or one_card_is_invalid" tests/test_combo_plan.py::test_combo_with_unsupported_condition_is_suppressed -v
```

Expected:

```text
The structured-condition tests show invalid atoms being dropped, and the Combo test shows an emitted '*' row.
```

- [ ] **Step 3: Reject any invalid structured atom**

Replace the final filtering in `_atoms_from_structured_condition` with explicit validation:

```python
unsafe_atoms = [atom for atom in atoms if not _is_atom_safe(atom)]
if unsafe_atoms:
    return [], "unsupported_condition"
return atoms, None
```

Validate `hand_contains`, `combo_partner`, and every `hand_contains_any` value through the existing CardID-safe atom patterns before returning.

- [ ] **Step 4: Preserve Combo condition errors**

Replace `_condition` in `combo_plan.py` with:

```python
def _condition(claim: dict[str, Any]) -> tuple[str, str | None]:
    return lower_runtime_condition(
        claim.get("conditions", claim.get("condition", "*"))
    )
```

In `build_combo_plan`:

```python
condition, condition_error = _condition(claim)
if condition_error is not None:
    suppressed.append(
        _suppression(
            claim,
            [str(card) for card in contract.get("cards", [])],
            condition_error,
        )
    )
    continue
row["condition"] = condition
```

- [ ] **Step 5: Run all condition consumers**

Run:

```powershell
python -m pytest tests/test_condition_format.py tests/test_combo_plan.py tests/test_card_behavior_router.py tests/test_compile_mulligan.py -q
```

Expected:

```text
All callers suppress unsupported conditions; no caller silently emits '*'.
```

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add src/hsconfig/condition_format.py src/hsconfig/combo_plan.py tests/test_condition_format.py tests/test_combo_plan.py tests/test_card_behavior_router.py tests/test_compile_mulligan.py
git commit -m "fix: reject partially lowered runtime conditions"
git push origin main
```

---

### Task 4: Strengthen Physical VisionAI Package Validation

**Files:**

- Modify: `src/hsconfig/validate_package.py`
- Test: `tests/test_validate_package.py`

**Interfaces:**

- Consumes: compiled runtime JSON files and optional GlobalValues baseline/profile.
- Produces: validation errors for missing required surface blocks, unsupported row keys, unsafe conditions, invalid selectors/CardIDs, and nonnumeric values.

- [ ] **Step 1: Write failing semantic-validator tests**

Add to `tests/test_validate_package.py`:

```python
@pytest.mark.parametrize(
    ("filename", "payload", "expected"),
    [
        (
            "Mulligan.json",
            {"GameCardId": "Mulligan", "ConfigComment": "x"},
            "missing required block Mulligan",
        ),
        (
            "Combo.json",
            {"GameCardId": "Combo", "ConfigComment": "x"},
            "missing required block ComboList",
        ),
        (
            "EX1_001.json",
            {
                "GameCardId": "EX1_001",
                "ConfigComment": "x",
                "BeforePlayCardBonus": {
                    "values": [
                        {
                            "condition": "nonsense",
                            "value": "NaN",
                            "metadata": "leak",
                        }
                    ]
                },
            },
            "unsupported runtime condition",
        ),
    ],
)
def test_validate_package_rejects_semantically_invalid_rows(
    tmp_path, filename, payload, expected
):
    package = _strict_package(tmp_path)
    deck_dir = package / "CustomConfig" / "deck"
    (deck_dir / filename).write_text(json.dumps(payload), encoding="utf-8")

    result = validate_config_package(package, strict_package=True)

    assert result["status"] == "failed"
    assert any(expected in error for error in result["errors"])
```

Add:

```python
def test_validate_combo_requires_valid_cardids_numeric_values_and_safe_condition(tmp_path):
    package = _strict_package(tmp_path)
    combo = {
        "GameCardId": "Combo",
        "ConfigComment": "x",
        "ComboList": {
            "values": [
                {
                    "comment": "bad",
                    "condition": "nonsense",
                    "combo": "BAD-ID >> EX1_002",
                    "value": "ten >> 20",
                }
            ]
        },
    }
    deck_dir = package / "CustomConfig" / "deck"
    (deck_dir / "Combo.json").write_text(json.dumps(combo), encoding="utf-8")

    result = validate_config_package(package, strict_package=True)

    assert result["status"] == "failed"
    assert any("invalid Combo card id BAD-ID" in error for error in result["errors"])
    assert any("unsupported runtime condition" in error for error in result["errors"])
    assert any("Combo value segment ten must be numeric" in error for error in result["errors"])
```

- [ ] **Step 2: Run the tests and verify permissive validation**

Run:

```powershell
python -m pytest tests/test_validate_package.py -k "semantically_invalid_rows or valid_cardids_numeric_values" -v
```

Expected:

```text
The new cases pass validation incorrectly before implementation.
```

- [ ] **Step 3: Add shared runtime-row validation helpers**

Import:

```python
from hsconfig.condition_format import classify_runtime_condition
```

Add:

```python
RUNTIME_VALUE_ROW_KEYS = {"comment", "condition", "value"}
MULLIGAN_ROW_KEYS = {"comment", "condition", "mulligan", "value"}
COMBO_ROW_KEYS = {"comment", "condition", "combo", "value"}
CARD_ID_RE = re.compile(r"^[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+[A-Za-z0-9]*$")
NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")


def _validate_condition(path: Path, label: str, row: Mapping[str, Any]) -> list[str]:
    classified = classify_runtime_condition(row.get("condition"))
    if classified.status == "runtime_safe":
        return []
    return [f"{path}: {label} unsupported runtime condition"]


def _validate_numeric_value(path: Path, label: str, value: Any) -> list[str]:
    if NUMERIC_RE.fullmatch(str(value).strip()):
        return []
    return [f"{path}: {label} value {value} must be numeric"]
```

For ordinary CardID rows:

- require each item to be an object;
- reject keys outside `RUNTIME_VALUE_ROW_KEYS`;
- require `condition` and `value`;
- validate condition and numeric value.

For `Mulligan.json`:

- require the `Mulligan` block;
- reject row keys outside `MULLIGAN_ROW_KEYS`;
- validate condition;
- validate concrete selectors using the existing Mulligan selector parser;
- allow only `hold` and `discard`.

For `Combo.json`:

- require `ComboList`;
- reject row keys outside `COMBO_ROW_KEYS`;
- validate condition;
- validate each card segment against `CARD_ID_RE`;
- validate each value segment with `NUMERIC_RE`;
- preserve existing operator and segment-parity checks.

For `GlobalValues.json`:

- reject unsupported row keys;
- validate conditions;
- keep the existing safe arithmetic-expression support for values rather than restricting GlobalValues to plain decimals.

- [ ] **Step 4: Run validator tests**

Run:

```powershell
python -m pytest tests/test_validate_package.py -q
```

Expected:

```text
All existing and new validator tests pass.
```

- [ ] **Step 5: Commit and push**

Run:

```powershell
git add src/hsconfig/validate_package.py tests/test_validate_package.py
git commit -m "fix: validate VisionAI runtime row semantics"
git push origin main
```

---

### Task 5: Require Target-Specific Runtime Authority

**Files:**

- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/config_readiness.py`
- Test: `tests/test_card_behavior_router.py`
- Test: `tests/test_config_readiness.py`

**Interfaces:**

- Consumes: `targeting_rule` claim with optional `target_scope`, condition, and `runtime_block`.
- Produces: a target row only when the claim contains target scope and a compatible documented target block; otherwise a suppression row with a precise reason.

- [ ] **Step 1: Write failing target-authority tests**

Add to `tests/test_card_behavior_router.py`:

```python
def test_targeting_claim_without_target_scope_is_suppressed():
    claim = {
        "claim_id": "target-missing-scope",
        "claim_kind": "targeting_rule",
        "cards": ["NX2_019"],
        "stance": "prefer_enemy_minion",
        "source_claim_ids": ["target-missing-scope"],
    }

    report = route_card_behavior_surfaces([claim])

    assert report["rows"] == []
    assert report["suppressed"] == [
        {
            "claim_id": "target-missing-scope",
            "claim_kind": "targeting_rule",
            "cards": ["NX2_019"],
            "reason": "missing_target_scope",
        }
    ]
```

```python
def test_targeting_claim_requires_compatible_target_block():
    claim = {
        "claim_id": "target-wrong-block",
        "claim_kind": "targeting_rule",
        "cards": ["CARD_TARGET"],
        "target_scope": "enemy_minion",
        "runtime_block": "BeforePlayCardBonus",
        "source_claim_ids": ["target-wrong-block"],
    }

    report = route_card_behavior_surfaces([claim])

    assert report["rows"] == []
    assert report["suppressed"][0]["reason"] == "target_scope_not_encoded"
```

```python
def test_targeting_claim_with_scope_and_target_block_is_meaningful():
    claim = {
        "claim_id": "target-complete",
        "claim_kind": "targeting_rule",
        "cards": ["CARD_TARGET"],
        "target_scope": "enemy_minion",
        "runtime_block": "BeforeBattlecryTargetBonus",
        "condition": "my_target(count(),minion=true) > 0",
        "source_claim_ids": ["target-complete"],
    }

    report = route_card_behavior_surfaces([claim])

    assert report["suppressed"] == []
    assert report["rows"][0]["behavior_block"] == "BeforeBattlecryTargetBonus"
    assert report["rows"][0]["meaningful_runtime_surface"] is True
```

- [ ] **Step 2: Verify current fallback behavior**

Run:

```powershell
python -m pytest tests/test_card_behavior_router.py -k "targeting_claim_without or requires_compatible_target or scope_and_target_block" -v
```

Expected:

```text
The first two claims currently become generic BeforePlayCardBonus rows.
```

- [ ] **Step 3: Remove the target-to-play fallback**

Replace the current targeting branch with:

```python
if claim_kind == "targeting_rule":
    if not _is_target_backed_claim(claim):
        suppressed.append(
            _suppressed_row(claim, claim_kind, cards, "missing_target_scope")
        )
        continue
    if explicit_block not in TARGET_RUNTIME_BLOCKS:
        suppressed.append(
            _suppressed_row(claim, claim_kind, cards, "target_scope_not_encoded")
        )
        continue
    intent = _claim_intent(claim, fallback=claim_kind)
    rows.extend(
        _rows_for_cards(
            claim,
            cards,
            condition=condition,
            behavior_block=explicit_block,
            intent=intent,
            roles=[intent],
        )
    )
    continue
```

Define:

```python
TARGET_RUNTIME_BLOCKS = {
    "BeforeBattlecryTargetBonus",
    "OnDiscoverCardBonus",
    "OnChooseOneCardBonus",
    "OnAdaptCardBonus",
}
```

Do not mark a targetless play-timing fallback as meaningful target closure.

- [ ] **Step 4: Make readiness preserve the missing target link**

Teach `_cards_from_unsupported_condition_suppression` or replace it with a general `_cards_from_semantic_suppression` that recognizes:

```python
{
    "unsupported_condition": "needs_condition_lowering",
    "missing_target_scope": "needs_target_scope",
    "target_scope_not_encoded": "needs_target_surface",
}
```

Add to `tests/test_config_readiness.py`:

```python
def test_targeting_suppression_does_not_count_as_runtime_closed():
    report = build_config_readiness_report(
        deck_identity=_one_card_identity("NX2_019"),
        claim_coverage=_covered_claims("NX2_019", "guide_backed"),
        card_behavior_plan={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "target",
                    "claim_kind": "targeting_rule",
                    "cards": ["NX2_019"],
                    "reason": "missing_target_scope",
                }
            ],
        },
        mulligan_plan={"rules": [], "suppressed_rules": []},
        combo_plan={"combos": [], "suppressed": []},
        gameplan_contract={},
        global_values_authority_matrix={},
    )

    assert report["cards"]["NX2_019"]["readiness_lane"] != "runtime_emitted"
    assert report["cards"]["NX2_019"]["first_missing_link"] == "needs_target_scope"
```

- [ ] **Step 5: Run target and readiness suites**

Run:

```powershell
python -m pytest tests/test_card_behavior_router.py tests/test_config_readiness.py -q
```

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add src/hsconfig/card_behavior_surface_router.py src/hsconfig/config_readiness.py tests/test_card_behavior_router.py tests/test_config_readiness.py
git commit -m "fix: require target-specific VisionAI authority"
git push origin main
```

---

### Task 6: Gate Risky Static Semantics And Remove Generic Runtime Rows

**Files:**

- Create: `src/hsconfig/semantic_runtime_gate.py`
- Create: `tests/test_semantic_runtime_gate.py`
- Modify: `src/hsconfig/card_intent_taxonomy.py`
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/compile_cardid.py`
- Modify: `src/hsconfig/config_quality_contract.py`
- Test: `tests/test_card_intent_taxonomy.py`
- Test: `tests/test_card_behavior_router.py`
- Test: `tests/test_compile_cardid.py`
- Test: `tests/test_config_quality_contract.py`

**Interfaces:**

- Consumes: classified intent reason, source lane, condition, runtime block, claim kind.
- Produces:
  - `SemanticRuntimeDecision(allowed: bool, reason: str)`
  - explicit behavior rows only;
  - `runtime_row_trace_inventory` with no unreported physical rows.

- [ ] **Step 1: Write the semantic-gate tests**

Create `tests/test_semantic_runtime_gate.py`:

```python
import pytest

from hsconfig.semantic_runtime_gate import decide_semantic_runtime


@pytest.mark.parametrize(
    "reason",
    [
        "automatic_from_deck_trigger",
        "automatic_from_hand_trigger",
        "conditional_cost_reduction",
        "conditional_self_damage_resource",
        "conditional_draw",
        "conditional_target_kill_burn",
        "self_damage_liability_body",
        "location_activation",
    ],
)
def test_risky_static_intent_is_report_only_without_exact_runtime_evidence(reason):
    decision = decide_semantic_runtime(
        semantic_reason=reason,
        source_lane="official_static_semantics",
        condition="*",
        runtime_block="BeforePlayCardBonus",
        claim_kind="mechanic_usage",
    )

    assert decision.allowed is False
    assert decision.reason == "semantic_surface_not_expressible"


def test_direct_enemy_hero_burn_can_lower_to_play_bonus():
    decision = decide_semantic_runtime(
        semantic_reason="direct_enemy_hero_burn",
        source_lane="official_static_semantics",
        condition="*",
        runtime_block="BeforePlayCardBonus",
        claim_kind="mechanic_usage",
    )

    assert decision.allowed is True
    assert decision.reason == "semantic_surface_supported"
```

- [ ] **Step 2: Write failing taxonomy expectations**

Add to `tests/test_card_intent_taxonomy.py`:

```python
@pytest.mark.parametrize(
    ("card_id", "expected_reason"),
    [
        ("CFM_637", "automatic_from_deck_trigger"),
        ("DRG_056", "automatic_from_hand_trigger"),
        ("YOD_032", "conditional_cost_reduction"),
        ("SCH_514", "conditional_self_damage_resource"),
        ("SW_444", "conditional_draw"),
        ("NX2_019", "conditional_target_kill_burn"),
        ("VAC_512", "self_damage_liability_body"),
        ("REV_290", "location_deploy"),
    ],
)
def test_shadowpriest_risky_cards_have_precise_semantic_reason(
    card_id, expected_reason
):
    result = classify_card_intent(_shadowpriest_card(card_id))
    assert result.reason == expected_reason
```

- [ ] **Step 3: Run the new tests**

Run:

```powershell
python -m pytest tests/test_semantic_runtime_gate.py tests/test_card_intent_taxonomy.py -k "risky or direct_enemy or shadowpriest_risky" -v
```

Expected:

```text
The new module is absent and several cards still resolve to broad damage or board-tempo reasons.
```

- [ ] **Step 4: Implement the semantic runtime gate**

Create `src/hsconfig/semantic_runtime_gate.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


REPORT_ONLY_WITHOUT_EXACT_RUNTIME_EVIDENCE = {
    "automatic_from_deck_trigger",
    "automatic_from_hand_trigger",
    "conditional_cost_reduction",
    "conditional_self_damage_resource",
    "conditional_draw",
    "conditional_target_kill_burn",
    "self_damage_liability_body",
    "location_activation",
}
SUPPORTED_STATIC_ACTION_REASONS = {
    "damage_aura_amplifier",
    "direct_enemy_hero_burn",
    "hero_power_cost_aura",
    "hero_power_transform",
    "location_deploy",
    "reciprocal_hero_burn",
}


@dataclass(frozen=True)
class SemanticRuntimeDecision:
    allowed: bool
    reason: str


def decide_semantic_runtime(
    *,
    semantic_reason: str,
    source_lane: str,
    condition: str,
    runtime_block: str,
    claim_kind: str,
) -> SemanticRuntimeDecision:
    del condition, runtime_block, claim_kind
    if (
        source_lane in {"official_static_semantics", "source_backed_static_semantics"}
        and semantic_reason in REPORT_ONLY_WITHOUT_EXACT_RUNTIME_EVIDENCE
    ):
        return SemanticRuntimeDecision(False, "semantic_surface_not_expressible")
    if semantic_reason in SUPPORTED_STATIC_ACTION_REASONS:
        return SemanticRuntimeDecision(True, "semantic_surface_supported")
    if source_lane in {
        "deck_matched_public_guide",
        "archetype_matched_public_guide",
    }:
        return SemanticRuntimeDecision(True, "guide_surface_supported")
    return SemanticRuntimeDecision(False, "semantic_surface_not_proven")
```

Do not let a guide lane bypass Task 5 target authority or Task 3 condition safety; this gate runs after those gates.

- [ ] **Step 5: Give the risky cards precise intent reasons**

Update exact-card and signal profiles in `card_intent_taxonomy.py` so the eight tested CardIDs return the exact reasons above.

For `REV_290`, keep deployment separate from activation:

```python
reason="location_deploy"
matched_signals=("location", "deploy")
```

The separate `location_activation` mechanic remains report-only.

- [ ] **Step 6: Apply the semantic gate before appending a behavior row**

After semantic scoring has produced a candidate row in `card_behavior_surface_router.py`:

```python
decision = decide_semantic_runtime(
    semantic_reason=str(row["semantic_score"]["reason"]),
    source_lane=_claim_source_lane(claim),
    condition=str(row["condition"]),
    runtime_block=str(row["behavior_block"]),
    claim_kind=claim_kind,
)
if not decision.allowed:
    suppressed.append(
        _suppressed_row(claim, claim_kind, [str(row["card_id"])], decision.reason)
    )
    continue
rows.append(row)
```

Add `_claim_source_lane` that prefers `source_lane`, then maps `source_refs == ["hearthstonejson_static_semantics"]` to `official_static_semantics`.

- [ ] **Step 7: Remove automatic CardID runtime rows**

In `compile_cardid.py`, make `compile_cardid_behaviors` serialize only `card["behavior_rows"]`.

Remove automatic emission of:

- unconditional `InHandPlayPriority`;
- role-derived `pressure_play_bonus`;
- role-only fallback blocks.

Keep minimal per-card files with only `GameCardId` and `ConfigComment` when no behavior row is allowed. Keep explicit source/router behavior rows unchanged.

Replace the old generic-priority tests with:

```python
def test_compile_cardid_does_not_invent_priority_for_report_only_card():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_001": {
                "card_id": "EX1_001",
                "name": "Report Only",
                "roles": ["pressure", "tradeable"],
                "confidence": "source_backed_static_semantics",
                "behavior_rows": [],
            }
        },
    }

    payload = compile_cardid_behaviors(contract)["EX1_001.json"]

    assert payload == {
        "GameCardId": "EX1_001",
        "ConfigComment": "Fixture: generated behavior for EX1_001",
    }
```

```python
def test_compile_cardid_preserves_explicit_priority_row():
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_001",
            "behavior_block": "InHandPlayPriority",
            "condition": "*",
            "value": "9",
            "rule_id_suffix": "guide_priority",
            "source_claim_ids": ["claim-priority"],
            "confidence": "guide_backed",
        }
    ]

    payload = compile_cardid_behaviors(
        {"deck_name": "Fixture", "cards": {}},
        rows=rows,
    )["EX1_001.json"]

    assert payload["InHandPlayPriority"]["values"][0]["value"] == "9"
```

- [ ] **Step 8: Add physical/report row parity**

In `config_quality_contract.py`, add:

```python
def _runtime_row_signature(
    card_id: str,
    behavior_block: str,
    row: Mapping[str, Any],
) -> tuple[str, str, str, str]:
    return (
        card_id,
        behavior_block,
        str(row.get("condition", "")),
        str(row.get("value", "")),
    )
```

Inventory every physical row from `CustomConfig/*/<CARDID>.json` and every meaningful row from `card_behavior_plan_report.json`. Emit:

```python
{
    "status": "clean" if not unreported else "attention",
    "physical_cardid_runtime_rows": len(physical),
    "reported_cardid_runtime_rows": len(reported),
    "unreported_runtime_rows": unreported,
    "reported_rows_missing_runtime": missing_runtime,
}
```

Add to `tests/test_config_quality_contract.py`:

```python
def test_quality_contract_flags_unreported_physical_cardid_row(tmp_path):
    package = _clean_package(tmp_path)
    _write_cardid_row(
        package,
        card_id="EX1_001",
        behavior_block="InHandPlayPriority",
        condition="*",
        value="5",
    )

    report = build_config_quality_report(package)
    check = report["checks"]["runtime_row_trace_inventory"]

    assert check["status"] == "attention"
    assert check["unreported_runtime_rows"][0]["card_id"] == "EX1_001"
    assert check["unreported_runtime_rows"][0]["behavior_block"] == "InHandPlayPriority"
```

- [ ] **Step 9: Run semantic/card/runtime-row suites**

Run:

```powershell
python -m pytest tests/test_semantic_runtime_gate.py tests/test_card_intent_taxonomy.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_quality_contract.py -q
```

- [ ] **Step 10: Commit and push**

Run:

```powershell
git add src/hsconfig/semantic_runtime_gate.py src/hsconfig/card_intent_taxonomy.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/compile_cardid.py src/hsconfig/config_quality_contract.py tests/test_semantic_runtime_gate.py tests/test_card_intent_taxonomy.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_quality_contract.py
git commit -m "fix: gate actionable CardID semantics"
git push origin main
```

---

### Task 7: Make GlobalValues Fallback And Overlay Coverage Honest

**Files:**

- Modify: `src/hsconfig/globalvalues_baseline.py`
- Modify: `src/hsconfig/compile_globalvalues.py`
- Modify: `src/hsconfig/validate_package.py`
- Test: `tests/test_compile_globalvalues.py`
- Test: `tests/test_globalvalues_authority.py`

**Interfaces:**

- Consumes: runtime default when available, otherwise bundled snapshot; authority-matrix overlays.
- Produces: baseline receipt with explicit snapshot provenance and a profile where every expected overlay key is either emitted or listed in `missing_overlay_keys`.

- [ ] **Step 1: Write failing fallback completeness tests**

Add to `tests/test_compile_globalvalues.py`:

```python
def test_fallback_contains_current_runtime_key_families():
    baseline = load_globalvalues_baseline(None)

    assert baseline["source"] == "bundled_fallback"
    assert baseline["snapshot_status"] == "known_runtime_snapshot"
    assert baseline["snapshot_date"] == "2026-07-25"
    keys = set(baseline["baseline"])
    assert {
        "GlobalMinionAttack",
        "GlobalMinionIntrinsicValue",
        "GlobalLocationHealth",
        "GlobalLocationIntrinsicValue",
        "OppGlobalMinionAttack",
        "OppGlobalMinionIntrinsicValue",
        "OppGlobalLocationHealth",
        "OppGlobalLocationIntrinsicValue",
    } <= keys
```

```python
def test_compile_globalvalues_reports_authorized_overlay_missing_from_baseline():
    result = compile_globalvalues(
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "thin",
            "FirstTurnValueWeight": {
                "values": [{"condition": "*", "value": "0"}]
            },
        },
        {
            "global_values_authority_matrix": {
                "allowed_step1_overlays": [
                    {
                        "key": "GlobalMinionAttack",
                        "operation": "increase",
                        "reason": "aggro",
                    }
                ]
            }
        },
    )

    assert result["profile"]["summary"]["all_expected_overlay_keys_accounted_for"] is False
    assert result["profile"]["missing_overlay_keys"] == ["GlobalMinionAttack"]
    assert result["profile"]["status"] == "attention"
```

- [ ] **Step 2: Run the tests and verify silent overlay loss**

Run:

```powershell
python -m pytest tests/test_compile_globalvalues.py -k "fallback_contains or authorized_overlay_missing" -v
```

- [ ] **Step 3: Update the fallback snapshot**

Replace the 14-key fallback with the complete current runtime-default key set from `C:\Users\darbo\Desktop\HS\CustomConfig\default\GlobalValues.json`, preserving its numeric strings and both `Global*` and `OppGlobal*` families.

Do not add speculative keys that are absent from the runtime default. Keep `MyHeroPowerValue` only in `KNOWN_GENERATED_OVERLAY_DEFAULTS`, because it is a known generated deck overlay rather than a baseline key.

Return these receipt fields from `load_globalvalues_baseline`:

```python
"snapshot_status": "live_runtime" if runtime_path else "known_runtime_snapshot",
"snapshot_date": None if runtime_path else "2026-07-25",
```

- [ ] **Step 4: Report missing overlay keys**

In `compile_globalvalues`:

```python
missing_overlay_keys = sorted(
    key
    for key in expected_overlay_keys
    if key not in default_values and key not in generated_overlay_keys
)
all_expected_overlay_keys_accounted_for = not missing_overlay_keys
status = (
    "attention"
    if missing_overlay_keys
    else "overlay_changed"
    if changed_keys
    else "baseline_confirmed"
)
```

Expose `missing_overlay_keys` and `all_expected_overlay_keys_accounted_for` in both the profile and summary.

- [ ] **Step 5: Make strict validation reject a false complete profile**

When a required GlobalValues profile is supplied, `validate_package.py` must add an error if:

```python
profile["summary"]["all_expected_overlay_keys_accounted_for"] is not True
```

This is package-contract validation, not source strength or gameplay tuning.

- [ ] **Step 6: Run GlobalValues suites**

Run:

```powershell
python -m pytest tests/test_compile_globalvalues.py tests/test_globalvalues_authority.py tests/test_validate_package.py -q
```

- [ ] **Step 7: Commit and push**

Run:

```powershell
git add src/hsconfig/globalvalues_baseline.py src/hsconfig/compile_globalvalues.py src/hsconfig/validate_package.py tests/test_compile_globalvalues.py tests/test_globalvalues_authority.py
git commit -m "fix: make GlobalValues overlay coverage explicit"
git push origin main
```

---

### Task 8: Separate Load Safety From Semantic Handoff Readiness

**Files:**

- Modify: `src/hsconfig/config_readiness.py`
- Modify: `src/hsconfig/config_quality_contract.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/contract_preflight.py`
- Test: `tests/test_config_readiness.py`
- Test: `tests/test_config_quality_contract.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_configure_cli.py`
- Test: `tests/test_contract_preflight.py`

**Interfaces:**

- Consumes: technical validation, apply contract, source strength, semantic suppressions, runtime-row parity, GlobalValues completeness.
- Produces:
  - `load_safe_to_install: bool`
  - `semantic_handoff_status: "closed" | "attention" | "insufficient_evidence"`
  - `semantic_handoff_reasons: list[str]`
  - backward-compatible `use_config_now` explicitly documented as a load-safety alias.

- [ ] **Step 1: Write failing acceptance-projection tests**

Add to `tests/test_configure_cli.py`:

```python
def test_acceptance_summary_separates_load_safety_from_semantic_attention():
    operator = _operator_summary(
        technical_status="VALID_PACKAGE",
        runtime_apply_allowed=True,
        runtime_apply_mode="load_safe_apply",
        source_backed_status="SOURCE_BACKED_STRONG",
    )
    quality = {
        "status": "attention",
        "checks": {
            "runtime_row_trace_inventory": {
                "status": "attention",
                "unreported_runtime_rows": [{"card_id": "EX1_001"}],
            },
            "visionai_semantic_surface": {
                "status": "attention",
                "attention": ["semantic_surface_not_expressible"],
            },
        },
    }

    summary = _build_acceptance_summary(
        operator_summary=operator,
        validation_status="passed",
        config_quality_summary=quality,
        apply_requested=False,
        apply_status=None,
    )

    assert summary["load_safe_to_install"] is True
    assert summary["use_config_now"] is True
    assert summary["semantic_handoff_status"] == "attention"
    assert "unreported_runtime_rows" in summary["semantic_handoff_reasons"]
```

```python
def test_source_strong_does_not_imply_semantic_closed():
    summary = _build_acceptance_summary(
        operator_summary=_operator_summary(
            technical_status="VALID_PACKAGE",
            runtime_apply_allowed=True,
            runtime_apply_mode="load_safe_apply",
            source_backed_status="SOURCE_BACKED_STRONG",
        ),
        validation_status="passed",
        config_quality_summary={
            "status": "attention",
            "checks": {
                "visionai_semantic_surface": {
                    "status": "attention",
                    "attention": ["missing_target_scope"],
                }
            },
        },
        apply_requested=False,
        apply_status=None,
    )

    assert summary["source_strength"] == "SOURCE_BACKED_STRONG"
    assert summary["semantic_handoff_status"] == "attention"
```

- [ ] **Step 2: Run the tests and verify the current projection conflates usability**

Run:

```powershell
python -m pytest tests/test_configure_cli.py -k "separates_load_safety or source_strong_does_not" -v
```

- [ ] **Step 3: Add a single semantic handoff projector**

In `config_quality_contract.py`:

```python
def semantic_handoff_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    checks = report.get("checks", {})
    reasons: list[str] = []
    trace = checks.get("runtime_row_trace_inventory", {})
    if trace.get("unreported_runtime_rows"):
        reasons.append("unreported_runtime_rows")
    surface = checks.get("visionai_semantic_surface", {})
    reasons.extend(str(item) for item in surface.get("attention", []))
    globalvalues = checks.get("globalvalues", {})
    if globalvalues.get("missing_overlay_keys"):
        reasons.append("missing_globalvalues_overlay_keys")
    return {
        "semantic_handoff_status": "closed" if not reasons else "attention",
        "semantic_handoff_reasons": sorted(set(reasons)),
    }
```

When source evidence contains only generic/policy fallback lanes and no semantic runtime rows, return `insufficient_evidence` instead of `attention`.

- [ ] **Step 4: Project the distinction everywhere without adding an apply gate**

In `commands/configure.py`:

```python
load_safe_to_install = (
    technical_status == "VALID_PACKAGE"
    and runtime_apply_allowed is True
    and runtime_apply_mode == "load_safe_apply"
    and validation_status == "passed"
)
```

Set:

```python
"load_safe_to_install": load_safe_to_install,
"use_config_now": load_safe_to_install,
"use_config_now_scope": "load_safety_only",
```

Merge the semantic handoff projection into:

- `configure_summary.json.acceptance_summary`;
- `configure_summary.json.handoff_contract`;
- `reports/operator_summary.json`;
- package-mode `contract-preflight`.

Do not use `semantic_handoff_status` to change `runtime_apply_allowed`.

- [ ] **Step 5: Add readiness tests for file presence versus semantic closure**

Add to `tests/test_config_readiness.py`:

```python
def test_empty_per_card_file_is_visible_but_not_semantically_closed():
    report = build_config_readiness_report(
        deck_identity=_one_card_identity("CFM_637"),
        claim_coverage=_covered_claims("CFM_637", "source_backed_static_semantics"),
        card_behavior_plan={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "patches-trigger",
                    "claim_kind": "mechanic_usage",
                    "cards": ["CFM_637"],
                    "reason": "semantic_surface_not_expressible",
                }
            ],
        },
        emitted_cardid_files=["CFM_637.json"],
        mulligan_plan={"rules": [], "suppressed_rules": []},
        combo_plan={"combos": [], "suppressed": []},
        gameplan_contract={},
        global_values_authority_matrix={},
    )

    card = report["cards"]["CFM_637"]
    assert card["runtime_surfaces"] == ["CFM_637.json"]
    assert card["readiness_lane"] == "report_only_supported"
    assert card["first_missing_link"] == "semantic_surface_not_expressible"
```

- [ ] **Step 6: Run projection and readiness suites**

Run:

```powershell
python -m pytest tests/test_config_readiness.py tests/test_config_quality_contract.py tests/test_operator_summary.py tests/test_configure_cli.py tests/test_contract_preflight.py -q
```

- [ ] **Step 7: Commit and push**

Run:

```powershell
git add src/hsconfig/config_readiness.py src/hsconfig/config_quality_contract.py src/hsconfig/operator_summary.py src/hsconfig/commands/configure.py src/hsconfig/contract_preflight.py tests/test_config_readiness.py tests/test_config_quality_contract.py tests/test_operator_summary.py tests/test_configure_cli.py tests/test_contract_preflight.py
git commit -m "feat: separate load safety from semantic handoff"
git push origin main
```

---

### Task 9: Prove The Exact ShadowPriest Package And Sync The Skill Contract

**Files:**

- Create: `tests/test_shadowpriest_semantic_safety_wave.py`
- Modify: `tests/fixtures/source_documents_shadowpriest_strong.json`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/contract-compiler-checklist.md`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_skill_sync.py`
- Test: `tests/test_operator_docs_contract_policy.py`

**Interfaces:**

- Consumes: the exact ShadowPriest deck code and deterministic local source fixtures.
- Produces: a load-safe package whose misleading rows are absent, safe rows remain, every physical row is report-traced, and semantic attention is honest.

- [ ] **Step 1: Create the exact package regression fixture**

Create `tests/test_shadowpriest_semantic_safety_wave.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.config_quality_contract import build_config_quality_report


DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


@pytest.fixture
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    output = tmp_path / "shadowpriest"
    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            DECK_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(output),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )
    assert code == 0
    return output


def _card(package: Path, card_id: str) -> dict:
    path = package / "CustomConfig" / "shadowpriest" / f"{card_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _report(package: Path, name: str) -> dict:
    path = package / "reports" / name
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Add exact unsafe-row absence assertions**

```python
@pytest.mark.parametrize(
    "card_id",
    ["CFM_637", "DRG_056", "YOD_032", "SCH_514", "SW_444", "NX2_019", "VAC_512"],
)
def test_risky_static_cards_have_no_unconditional_action_row(package, card_id):
    payload = _card(package, card_id)

    assert "InHandPlayPriority" not in payload
    assert "BeforePlayCardBonus" not in payload
    assert "BeforeBattlecryTargetBonus" not in payload
```

```python
def test_cathedral_only_keeps_supported_deploy_semantics(package):
    payload = _card(package, "REV_290")

    assert "BeforePlayCardBonus" in payload
    assert "BeforeBattlecryTargetBonus" not in payload
    assert "BeforeUseHeroPowerBonus" not in payload
```

```python
def test_supported_burn_aura_and_hero_power_rows_remain(package):
    assert "BeforePlayCardBonus" in _card(package, "DS1_233")
    assert "BeforePlayCardBonus" in _card(package, "GVG_009")
    assert "OnBoardBonus" in _card(package, "SW_446")
    assert "OnBoardBonus" in _card(package, "TOY_381")
    assert "BeforePlayCardBonus" in _card(package, "VAC_419")
    assert "BeforeUseHeroPowerBonus" in _card(package, "SW_448")
```

- [ ] **Step 3: Add report honesty assertions**

```python
def test_shadowpriest_runtime_rows_are_report_traced(package):
    quality = build_config_quality_report(package)
    trace = quality["checks"]["runtime_row_trace_inventory"]

    assert trace["status"] == "clean"
    assert trace["unreported_runtime_rows"] == []
    assert trace["reported_rows_missing_runtime"] == []
    assert trace["physical_cardid_runtime_rows"] == trace["reported_cardid_runtime_rows"]
```

```python
def test_shadowpriest_is_load_safe_without_claiming_semantic_closure(package):
    operator = _report(package, "operator_summary.json")

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_allowed"] is True
    assert operator["load_safe_to_install"] is True
    assert operator["semantic_handoff_status"] in {"attention", "insufficient_evidence"}
    assert "semantic_surface_not_expressible" in operator["semantic_handoff_reasons"]
```

```python
def test_darkbishop_effect_does_not_become_mulligan_or_body_priority(package):
    mulligan = _card(package, "Mulligan")
    darkbishop = _card(package, "SW_448")

    selectors = [
        row["mulligan"]
        for row in mulligan["Mulligan"]["values"]
        if row["value"] == "hold"
    ]
    assert "SW_448" not in selectors
    assert "BeforeUseHeroPowerBonus" in darkbishop
    assert "InHandPlayPriority" not in darkbishop
    assert "BeforePlayCardBonus" not in darkbishop
```

- [ ] **Step 4: Run the exact package tests**

Run:

```powershell
python -m pytest tests/test_shadowpriest_semantic_safety_wave.py -q
```

Expected:

```text
All assertions pass after Tasks 2-8.
```

- [ ] **Step 5: Update the skill contract**

Add to `.agents/skills/hsconfig/SKILL.md` under Hard Boundaries:

```markdown
- `SOURCE_BACKED_STRONG` proves source closure only. It is necessary but not sufficient for semantic handoff.
- Read `semantic_handoff_status` and `semantic_handoff_reasons` before describing a package as semantically closed.
- Never lower generic gameplay “keep” prose into `Mulligan.json`; explicit opening-hand or Mulligan context is required.
- Reject the whole runtime row when any structured condition atom is unsupported.
- Targeting claims count as closed only when target scope and a compatible target surface are both encoded.
- Do not emit generic `InHandPlayPriority` or `BeforePlayCardBonus` rows solely to make every-card coverage appear complete.
```

Update the three skill references and operator docs with the same meanings. Preserve:

```markdown
reports/operator_summary.json remains the only normal apply authority.
semantic_handoff_status is diagnostic and never creates a second apply gate.
```

- [ ] **Step 6: Synchronize the installed skill through the repo script**

Run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected:

```text
The installed hsconfig skill matches .agents/skills/hsconfig byte-for-byte.
```

- [ ] **Step 7: Run skill and docs contract tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_skill_sync.py tests/test_operator_docs_contract_policy.py tests/test_shadowpriest_semantic_safety_wave.py -q
python scripts/check_contract_guardrails.py
```

- [ ] **Step 8: Commit and push**

Run:

```powershell
git add tests/test_shadowpriest_semantic_safety_wave.py tests/fixtures/source_documents_shadowpriest_strong.json .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/card-behavior-policy.md .agents/skills/hsconfig/references/guide-research-policy.md .agents/skills/hsconfig/references/contract-compiler-checklist.md docs/operator/README.md docs/operator/guide-research-policy.md docs/operator/universal-wild-no-block-contract.md tests/test_skill_files.py tests/test_skill_sync.py tests/test_operator_docs_contract_policy.py
git commit -m "test: prove fail-closed ShadowPriest semantics"
git push origin main
```

---

### Task 10: Full Verification, Fresh Preview, And Final One-Version Gate

**Files:**

- No tracked source file expected.
- Ignored preview output: `outputs/semantic-safety-shadowpriest-verification`.

**Interfaces:**

- Consumes: completed Tasks 1-9.
- Produces: full-suite evidence, fresh package diagnostics, runtime-match report, clean one-branch local/GitHub state.

- [ ] **Step 1: Run all focused safety suites**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_source_claim_compiler.py tests/test_source_autopilot.py tests/test_source_acquisition.py tests/test_condition_format.py tests/test_combo_plan.py tests/test_validate_package.py tests/test_card_behavior_router.py tests/test_semantic_runtime_gate.py tests/test_card_intent_taxonomy.py tests/test_compile_cardid.py tests/test_config_quality_contract.py tests/test_compile_globalvalues.py tests/test_config_readiness.py tests/test_configure_cli.py tests/test_shadowpriest_semantic_safety_wave.py -q -p no:cacheprovider
```

Expected:

```text
All focused suites pass.
```

- [ ] **Step 2: Run the full repository suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -p no:cacheprovider
```

Expected:

```text
No failures.
```

- [ ] **Step 3: Run static and contract guardrails**

Run:

```powershell
python scripts/check_contract_guardrails.py
python scripts/check_hsconfig_currentness.py --cwd . --json
python -m hsconfig.cli contract-preflight --json
```

Expected:

```text
installed_skill_sync_current is true
repo_current is true
no contract guardrail fails
```

- [ ] **Step 4: Generate a fresh read-only ShadowPriest preview**

Run:

```powershell
python -m hsconfig.cli configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out "outputs\semantic-safety-shadowpriest-verification" --online-source --auto-source --json
```

Do not add `--apply`.

- [ ] **Step 5: Inspect the first-read and authority reports**

Run:

```powershell
$summary = Get-Content -Raw "outputs\semantic-safety-shadowpriest-verification\configure_summary.json" | ConvertFrom-Json -Depth 100
$operator = Get-Content -Raw "outputs\semantic-safety-shadowpriest-verification\04_package\reports\operator_summary.json" | ConvertFrom-Json -Depth 100
$summary.acceptance_summary | ConvertTo-Json -Depth 20
$summary.handoff_contract | ConvertTo-Json -Depth 20
$operator | ConvertTo-Json -Depth 20
```

Confirm:

```text
technical_status is VALID_PACKAGE
load_safe_to_install is true
use_config_now_scope is load_safety_only
semantic_handoff_status is honest and supported by semantic_handoff_reasons
source_status_apply_blocking is false
runtime_write_performed is false
```

- [ ] **Step 6: Validate and compare to runtime without writing**

Run:

```powershell
python -m hsconfig.cli validate --package "outputs\semantic-safety-shadowpriest-verification\04_package" --json
python -m hsconfig.cli contract-doctor --package "outputs\semantic-safety-shadowpriest-verification\04_package" --json
python -m hsconfig.cli runtime-match --package "outputs\semantic-safety-shadowpriest-verification\04_package" --runtime-root "C:\Users\darbo\Desktop\HS" --json
```

Expected:

```text
validate passes
contract-doctor exposes no unreported runtime rows
runtime-match may report mismatch because this plan deliberately performs no apply
```

- [ ] **Step 7: Verify repository and GitHub topology**

Run:

```powershell
git status --short --branch
git rev-list --left-right --count origin/main...HEAD
git branch -vv --all
gh pr list --repo Teufelsboy/HSConfig --state open --json number,headRefName,baseRefName,url
gh api repos/Teufelsboy/HSConfig --jq '{default_branch,open_issues_count}'
```

Expected:

```text
clean worktree
0  0 local/remote divergence
only main and origin/main
no open pull request
default_branch is main
```

- [ ] **Step 8: Enforce task ownership for any verification failure**

No tracked correction is expected in this verification task. If `git status`
shows a source or test change, stop and return to the earlier task that owns
that exact file. Run that task's focused test, commit, and push there before
restarting Task 10. Do not create an ad hoc verification commit or an empty
commit.

- [ ] **Step 9: Final clean-state proof**

Run:

```powershell
git fetch --all --prune --tags
git status --short --branch
git rev-list --left-right --count origin/main...HEAD
python scripts/check_hsconfig_currentness.py --cwd . --json
```

Expected:

```text
clean tree
main synchronized with origin/main
no redundant branch
```

## Acceptance Criteria

- [ ] Generic gameplay “keep” prose cannot create a Mulligan hold.
- [ ] Navigation/footer text cannot create promotion-eligible combo or gameplan evidence.
- [ ] Publication freshness comes only from explicit publication/update metadata.
- [ ] A five-of-sixteen card overlap is not labeled an exact deck match.
- [ ] Any invalid structured condition atom suppresses the entire runtime rule.
- [ ] Unsupported Combo conditions suppress the Combo row instead of becoming `condition:"*"`.
- [ ] Strict validation rejects missing `Mulligan`/`ComboList` blocks, unsupported row keys, unsafe conditions, invalid CardIDs, and nonnumeric runtime values.
- [ ] Targeting claims require target scope and a compatible encoded target surface.
- [ ] Static automatic triggers, conditional resources, conditional discounts, liabilities, and unsupported target/activation semantics remain report-only.
- [ ] Generic role coverage does not emit unconditional `InHandPlayPriority` or `BeforePlayCardBonus`.
- [ ] Every physical CardID runtime row has a matching report row, and every meaningful report row exists physically.
- [ ] The current GlobalValues fallback contains the current runtime key families and cannot silently drop an expected overlay.
- [ ] `load_safe_to_install` is distinct from `semantic_handoff_status`.
- [ ] `SOURCE_BACKED_STRONG` does not imply semantic closure.
- [ ] The exact ShadowPriest package preserves supported burn/aura/Hero-Power rows and removes the identified misleading unconditional rows.
- [ ] Darkbishop remains absent from Mulligan and body priority while preserving Hero Power semantics.
- [ ] The installed skill matches the repository skill.
- [ ] The complete test suite and contract guardrails pass.
- [ ] No runtime apply occurs.
- [ ] Local and GitHub repositories finish clean, synchronized, PR-free, and on `main` only.

## Rollback Strategy

- Revert individual task commits in reverse order; do not reset or overwrite the worktree.
- Keep the source-evidence, condition, validator, targeting, CardID, GlobalValues, and readiness commits independent so a regression can be isolated.
- If branch canonicalization must be reversed, recreate the old branch from the preserved commit SHA; do not move `main` backward with a force push.
- Never roll back by copying old generated runtime files into `C:\Users\darbo\Desktop\HS`.
