# HSConfig Source-Backed Strong Contract Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig generate a valid, non-blocking config package for any deck while promoting `SOURCE_BACKED_STRONG` only when source -> claim -> contract -> runtime/review outcomes are honestly backed and no default-only runtime surface remains.

**Architecture:** Keep the existing HSConfig contract spine. Add a thin `source_bundle` artifact that ties source records, qualified claims, surface decisions, default-only diagnostics, and first-missing-source actions together. Do not add a second apply gate: `operator_summary.json` remains the normal authority, and source reports remain diagnostic/explainability inputs.

**Tech Stack:** Python, pytest, existing HSConfig CLI/package builder, JSON runtime artifacts, current `src/hsconfig` modules.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not create a shadow workspace.
- No human approval gate for config generation.
- Any deck must produce a technically valid package when the deck code can be decoded.
- `SOURCE_BACKED_STRONG` is an evidence quality label, not a prerequisite for load-safe config generation.
- `operator_summary.json` remains the single normal apply authority.
- Policy-backed rows and default runtime rows may keep a package useful, but must never prove `SOURCE_BACKED_STRONG`.
- No default-only runtime surface may be hidden; `default_only_runtime_surfaces` must stay explicit.
- Darkbishop Benedictus / `SW_448`: preserve start-of-game hero-power transform semantics, but never infer opening-hand mulligan keep without explicit mulligan source.
- Avoid new runtime surfaces, new dependencies, and broad rewrites.

---

## File Structure

Create:

- `src/hsconfig/source_bundle.py`  
  Builds the package-level source bundle artifact from existing source records, compiled claims, surface decisions, operator summary, and explainability rows.

- `tests/test_source_bundle.py`  
  Unit tests for source bundle schema, source lane classification, missing-source actions, and default-only visibility.

Modify:

- `src/hsconfig/source_document_model.py`  
  Add explicit claim qualification helpers for source lane, deck match scope, opening-hand relevance, promotion eligibility, and static-vs-runtime distinction.

- `src/hsconfig/operator_summary.py`  
  Consume qualified source facts and no-default-only diagnostics when computing `semantic_status`, without changing the apply-authority boundary.

- `src/hsconfig/source_to_runtime_explainability.py`  
  Surface per-card and per-surface `first_missing_source_action`, source lane, and why a strong static claim did or did not lower to runtime.

- `src/hsconfig/strong_promotion_report.py`  
  Include the first missing link for `SOURCE_BACKED_STRONG` and distinguish static contract closure from runtime lowering.

- `src/hsconfig/commands/configure.py`  
  Write `source_bundle.json` into each prepared package and include its path/status in the JSON result.

- `tests/fixtures/source_documents_*.json`  
  Reclassify representative fixtures so strong fixtures are honest. Downgrade weak public evidence fixtures, especially PirateDH, to partial/policy-backed if no explicit public guide supports strong claims.

- `tests/test_shadowpriest_depth_e2e.py`  
  Keep the Darkbishop effect-vs-mulligan regression hard.

- `tests/test_no_default_only_semantic_archetype_matrix.py`  
  Extend matrix expectations to verify no hidden default-only runtime surfaces.

- `tests/test_multideck_source_backed_e2e.py`  
  Assert representative deck statuses match available evidence: strong where supported, partial/load-safe where sources are thin.

- `docs/operator/source-backed-strong-closure.md`  
  Document the strong-promotion contract and source lane definitions.

- `docs/operator/guide-research-policy.md`  
  Document which source types may and may not promote claims.

- `.agents/skills/hsconfig/SKILL.md`  
  Update the skill contract: always build, do not block arbitrary decks, promote strong only with source-backed claims, and keep default-only surfaces visible.

---

### Task 1: Source Bundle Artifact

**Files:**
- Create: `src/hsconfig/source_bundle.py`
- Create: `tests/test_source_bundle.py`
- Modify: `src/hsconfig/commands/configure.py`

**Interfaces:**
- Consumes:
  - `operator_summary: Mapping[str, Any]`
  - `source_records: Sequence[Mapping[str, Any]]`
  - `claims: Sequence[Mapping[str, Any]]`
  - `explainability_report: Mapping[str, Any]`
- Produces:
  - `build_source_bundle(...) -> dict[str, Any]`
  - package artifact `source_bundle.json`
  - configure JSON field `source_bundle_path`

- [ ] **Step 1: Write the failing source bundle schema test**

Add this test to `tests/test_source_bundle.py`:

```python
from hsconfig.source_bundle import build_source_bundle


def test_source_bundle_exposes_source_claim_runtime_chain():
    bundle = build_source_bundle(
        deck_name="ShadowPriest",
        deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        source_records=[
            {
                "source_id": "src-shadowpriest-guide",
                "source_type": "community_guide",
                "source_url": "https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "deck_or_archetype_matched",
            }
        ],
        claims=[
            {
                "claim_id": "claim-sw448-transform",
                "source_id": "src-shadowpriest-guide",
                "claim_kind": "hero_power_transform",
                "card_ids": ["SW_448"],
                "opening_hand_relevant": False,
                "runtime_lowering": "cardid_or_contract_only",
                "promotion_eligible": True,
            }
        ],
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "default_only_runtime_surfaces": [],
        },
        explainability_report={
            "card_rows": [
                {
                    "card_id": "SW_448",
                    "strongest_claim_kind": "hero_power_transform",
                    "runtime_backed": True,
                    "first_missing_link": None,
                    "next_source_action": "none",
                }
            ]
        },
    )

    assert bundle["schema_version"] == 1
    assert bundle["deck"]["name"] == "ShadowPriest"
    assert bundle["source_record_count"] == 1
    assert bundle["claim_count"] == 1
    assert bundle["default_only_runtime_surfaces"] == []
    assert bundle["promotion"]["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert bundle["promotion"]["first_missing_source_action"] == "none"
    assert bundle["card_coverage"][0]["card_id"] == "SW_448"
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m pytest tests/test_source_bundle.py::test_source_bundle_exposes_source_claim_runtime_chain -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.source_bundle'`.

- [ ] **Step 3: Implement `build_source_bundle`**

Create `src/hsconfig/source_bundle.py` with this public interface:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def build_source_bundle(
    *,
    deck_name: str,
    deck_code: str,
    source_records: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
    operator_summary: Mapping[str, Any],
    explainability_report: Mapping[str, Any],
) -> dict[str, Any]:
    default_only = list(operator_summary.get("default_only_runtime_surfaces") or [])
    card_rows = list(explainability_report.get("card_rows") or [])
    first_missing = _first_missing_source_action(card_rows, default_only)
    return {
        "schema_version": 1,
        "deck": {"name": deck_name, "code": deck_code},
        "source_record_count": len(source_records),
        "claim_count": len(claims),
        "source_records": [dict(row) for row in source_records],
        "claims": [dict(row) for row in claims],
        "default_only_runtime_surfaces": default_only,
        "card_coverage": [dict(row) for row in card_rows],
        "promotion": {
            "technical_status": operator_summary.get("technical_status"),
            "semantic_status": operator_summary.get("semantic_status"),
            "first_missing_source_action": first_missing,
        },
    }


def _first_missing_source_action(
    card_rows: Sequence[Mapping[str, Any]], default_only: Sequence[Any]
) -> str:
    if default_only:
        return "replace_default_only_runtime_surface_with_source_or_policy_claim"
    for row in card_rows:
        action = row.get("next_source_action")
        if action and action != "none":
            return str(action)
    return "none"
```

- [ ] **Step 4: Run source bundle tests**

Run:

```powershell
python -m pytest tests/test_source_bundle.py -q
```

Expected: PASS.

- [ ] **Step 5: Wire configure output**

Modify `src/hsconfig/commands/configure.py` where package artifacts are written. After `operator_summary.json` and explainability are available, call `build_source_bundle(...)`, write `source_bundle.json`, and include:

```python
result["source_bundle_path"] = str(source_bundle_path)
```

Use existing JSON write helpers in the file; do not introduce a new helper unless there is already a local pattern for it.

- [ ] **Step 6: Add configure integration assertion**

Extend `tests/test_configure_online_source.py` or `tests/test_configure_auto_source.py`:

```python
def test_configure_writes_source_bundle_for_online_source(tmp_path, monkeypatch):
    result = run_configure_with_fixture_online_source(tmp_path, monkeypatch)
    bundle_path = Path(result["source_bundle_path"])
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert bundle["schema_version"] == 1
    assert bundle["promotion"]["first_missing_source_action"] in {
        "none",
        "replace_default_only_runtime_surface_with_source_or_policy_claim",
        "add_explicit_mulligan_source",
        "map_claim_kind_or_keep_report_only",
    }
```

Use the existing test helper name in that file; if the helper has a different name, reuse it rather than creating duplicate setup.

- [ ] **Step 7: Commit Task 1**

```powershell
git add src/hsconfig/source_bundle.py src/hsconfig/commands/configure.py tests/test_source_bundle.py tests/test_configure_online_source.py tests/test_configure_auto_source.py
git commit -m "feat: write source bundle artifact"
```

---

### Task 2: Claim Qualification and Source Lanes

**Files:**
- Modify: `src/hsconfig/source_document_model.py`
- Modify: `tests/test_claim_kind_runtime_contract.py`
- Modify: `tests/test_source_contract_conformance.py`

**Interfaces:**
- Consumes: raw source claim dictionaries.
- Produces:
  - `qualify_source_claim(claim: Mapping[str, Any]) -> dict[str, Any]`
  - normalized fields:
    - `source_lane`
    - `deck_match_scope`
    - `opening_hand_relevant`
    - `promotion_eligible`
    - `runtime_lowering`
    - `strong_static_claim`

- [ ] **Step 1: Write qualification tests for static strong versus runtime lowering**

Add to `tests/test_claim_kind_runtime_contract.py`:

```python
from hsconfig.source_document_model import qualify_source_claim


def test_hero_power_transform_is_strong_static_but_not_opening_hand_relevant():
    claim = qualify_source_claim(
        {
            "claim_id": "claim-sw448",
            "claim_kind": "hero_power_transform",
            "source_type": "official_card_data",
            "card_ids": ["SW_448"],
        }
    )

    assert claim["promotion_eligible"] is True
    assert claim["strong_static_claim"] is True
    assert claim["opening_hand_relevant"] is False
    assert claim["runtime_lowering"] in {"cardid_or_contract_only", "contract_only"}


def test_policy_backed_claim_is_never_strong_promotion_evidence():
    claim = qualify_source_claim(
        {
            "claim_id": "policy-keep",
            "claim_kind": "mulligan_keep",
            "source_type": "policy_backed_autonomous_mulligan",
            "card_ids": ["CARD_001"],
        }
    )

    assert claim["promotion_eligible"] is False
    assert claim["strong_static_claim"] is False
    assert claim["source_lane"] == "policy_fallback"
```

- [ ] **Step 2: Run tests to verify failure**

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py::test_hero_power_transform_is_strong_static_but_not_opening_hand_relevant tests/test_claim_kind_runtime_contract.py::test_policy_backed_claim_is_never_strong_promotion_evidence -q
```

Expected: FAIL because `qualify_source_claim` does not exist or lacks fields.

- [ ] **Step 3: Implement qualification helper**

In `src/hsconfig/source_document_model.py`, add:

```python
def qualify_source_claim(claim: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(claim)
    claim_kind = normalized_claim_kind(normalized)
    source_type = str(normalized.get("source_type") or normalized.get("provenance") or "")
    normalized["claim_kind"] = claim_kind
    normalized["source_lane"] = _source_lane(source_type, normalized)
    normalized["deck_match_scope"] = str(normalized.get("deck_match_scope") or "unknown")
    normalized["opening_hand_relevant"] = _opening_hand_relevant(claim_kind, normalized)
    normalized["runtime_lowering"] = _runtime_lowering(claim_kind)
    normalized["promotion_eligible"] = _promotion_eligible(source_type, normalized)
    normalized["strong_static_claim"] = bool(
        normalized["promotion_eligible"]
        and claim_kind in {
            "hero_power_transform",
            "card_role",
            "gameplan_posture",
            "targeting_rule",
            "combo_sequence",
            "mulligan_keep",
            "mulligan_discard",
        }
    )
    return normalized
```

Add private helpers in the same file:

```python
def _source_lane(source_type: str, claim: Mapping[str, Any]) -> str:
    if source_type == "policy_backed_autonomous_mulligan":
        return "policy_fallback"
    if source_type in {"official_card_data", "hearthstonejson", "blizzard_card_library"}:
        return "official_static_semantics"
    if source_type in {"community_guide", "public_guide"}:
        return str(claim.get("source_lane") or "deck_matched_public_guide")
    if source_type in {"replay_stat_aggregate", "hsreplay", "hsguru"}:
        return "statistical_enrichment"
    return str(claim.get("source_lane") or "unknown")


def _opening_hand_relevant(claim_kind: str, claim: Mapping[str, Any]) -> bool:
    if claim_kind in {"mulligan_keep", "mulligan_discard"}:
        return True
    if "opening_hand_relevant" in claim:
        return bool(claim["opening_hand_relevant"])
    return False


def _runtime_lowering(claim_kind: str) -> str:
    if claim_kind in {"mulligan_keep", "mulligan_discard"}:
        return "mulligan"
    if claim_kind == "combo_sequence":
        return "combo"
    if claim_kind in {"targeting_rule", "hero_power_transform", "card_role"}:
        return "cardid_or_contract_only"
    if claim_kind == "gameplan_posture":
        return "globalvalues_or_contract_only"
    return "contract_only"


def _promotion_eligible(source_type: str, claim: Mapping[str, Any]) -> bool:
    if source_type == "policy_backed_autonomous_mulligan":
        return False
    if source_type in {"default_runtime", "generated_default"}:
        return False
    if claim.get("source_blocked") is True:
        return False
    if str(claim.get("source_visibility") or "") == "snippet_only":
        return False
    return source_type in {
        "official_card_data",
        "hearthstonejson",
        "blizzard_card_library",
        "community_guide",
        "public_guide",
    }
```

If equivalent helpers already exist, keep one canonical implementation and route the new public function to it.

- [ ] **Step 4: Run targeted contract tests**

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_source_contract_conformance.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/hsconfig/source_document_model.py tests/test_claim_kind_runtime_contract.py tests/test_source_contract_conformance.py
git commit -m "feat: qualify source claims for strong promotion"
```

---

### Task 3: Strong Promotion Gate Without Blocking Any Deck

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/strong_promotion_report.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_strong_fixture_closure.py`

**Interfaces:**
- Consumes: qualified claims and existing operator summary inputs.
- Produces:
  - `semantic_status == "SOURCE_BACKED_STRONG"` only when evidence is strong and no default-only normal runtime surface exists.
  - `runtime_apply_allowed == true` remains possible for weaker valid packages.
  - `semantic_blockers` and strong promotion report identify the first missing link.

- [ ] **Step 1: Write operator summary regression tests**

Add to `tests/test_operator_summary.py`:

```python
def test_policy_backed_package_is_load_safe_but_not_source_backed_strong(tmp_path):
    package = build_valid_package_with_policy_backed_mulligan(tmp_path)
    operator = read_operator_summary(package)

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_allowed"] is True
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert any(
        row.get("code") == "policy_claim_not_strong_evidence"
        for row in operator.get("semantic_blockers", [])
    )


def test_default_only_surface_blocks_strong_promotion_but_not_load_safe_apply(tmp_path):
    package = build_valid_package_with_default_only_surface(tmp_path)
    operator = read_operator_summary(package)

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_allowed"] is True
    assert operator["default_only_runtime_surfaces"]
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"
```

Use existing helper names if available. If the helpers do not exist, create narrow local helpers in the test file that write a minimal package, `operator_summary.json`, and the relevant source diagnostics.

- [ ] **Step 2: Run tests to verify failure or current drift**

```powershell
python -m pytest tests/test_operator_summary.py::test_policy_backed_package_is_load_safe_but_not_source_backed_strong tests/test_operator_summary.py::test_default_only_surface_blocks_strong_promotion_but_not_load_safe_apply -q
```

Expected: FAIL if current code promotes policy/default rows too strongly; PASS if already covered.

- [ ] **Step 3: Harden `operator_summary.py`**

In the semantic-status calculation, enforce:

```python
strong_ready = (
    technical_status == "VALID_PACKAGE"
    and source_depth_status == "source_backed"
    and claim_count > 0
    and not default_only_runtime_surfaces
    and not source_conflicts
    and not uncovered_source_backed_cards
    and not readiness_gaps
    and not policy_backed_runtime_claims
)
```

Add blocker codes:

```python
"policy_claim_not_strong_evidence"
"default_only_surface_not_strong_evidence"
"snippet_only_source_not_strong_evidence"
"runtime_row_missing_source_claim"
"static_claim_not_runtime_observed"
```

Do not route these blockers into the technical apply gate. They affect semantic promotion only.

- [ ] **Step 4: Update strong promotion report**

Modify `src/hsconfig/strong_promotion_report.py` so the report distinguishes:

```json
{
  "verdict": "SOURCE_BACKED_STRONG_CONFIRMED",
  "static_contract_status": "SOURCE_BACKED_STRONG",
  "runtime_lowering_status": "NO_DEFAULT_ONLY_RUNTIME_SURFACES",
  "first_missing_source_action": "none"
}
```

For partial packages:

```json
{
  "verdict": "PROMOTION_BLOCKED",
  "static_contract_status": "SOURCE_BACKED_PARTIAL",
  "runtime_lowering_status": "LOAD_SAFE_WITH_POLICY_OR_REVIEW_ROWS",
  "first_missing_source_action": "add_explicit_mulligan_source"
}
```

- [ ] **Step 5: Run targeted tests**

```powershell
python -m pytest tests/test_operator_summary.py tests/test_strong_fixture_closure.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/strong_promotion_report.py tests/test_operator_summary.py tests/test_strong_fixture_closure.py
git commit -m "fix: keep strong promotion evidence honest"
```

---

### Task 4: Representative Deck Evidence Matrix

**Files:**
- Modify: `tests/fixtures/source_documents_shadowpriest_strong.json`
- Modify: `tests/fixtures/source_documents_mechpala_strong.json`
- Modify: `tests/fixtures/source_documents_piraterogue_strong.json`
- Modify: `tests/fixtures/source_documents_bigshaman_strong.json`
- Modify: `tests/fixtures/source_documents_boarlock_strong.json`
- Modify: `tests/fixtures/source_documents_imbuemage_strong.json`
- Modify: `tests/fixtures/source_documents_treantdruid_strong.json`
- Modify: `tests/fixtures/source_documents_discolock_strong.json`
- Modify: `tests/fixtures/source_documents_piratedh_strong.json`
- Modify: `tests/fixtures/source_documents_ctapaladin_strong.json`
- Modify: `tests/fixtures/source_documents_kingslayer_strong.json`
- Modify: `tests/test_multideck_source_backed_e2e.py`
- Modify: `docs/operator/archetype-fixture-matrix.json`

**Interfaces:**
- Consumes: public guide evidence and fixture source documents.
- Produces: honest expected strong/partial status per representative deck.

- [ ] **Step 1: Encode expected status matrix in tests**

In `tests/test_multideck_source_backed_e2e.py`, add an expected-evidence table:

```python
EXPECTED_EVIDENCE_STATUS = {
    "ShadowPriest": "SOURCE_BACKED_STRONG",
    "MechPala": "SOURCE_BACKED_STRONG",
    "PirateRogue": "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH",
    "BigShaman": "SOURCE_BACKED_STRONG",
    "Boarlock": "SOURCE_BACKED_STRONG",
    "ImbueMage": "SOURCE_BACKED_STRONG",
    "TreantDruid": "SOURCE_BACKED_PARTIAL",
    "Discolock": "SOURCE_BACKED_PARTIAL",
    "PirateDH": "SOURCE_BACKED_PARTIAL",
    "CtAPaladin": "SOURCE_BACKED_PARTIAL_UNLESS_EXACT_GUIDE_MATCHED",
    "Kingslayer": "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH",
}
```

Add assertions:

```python
def test_representative_decks_do_not_fake_source_backed_strong(tmp_path):
    results = prepare_representative_source_matrix(tmp_path)
    for row in results:
        expected = EXPECTED_EVIDENCE_STATUS[row["deck_name"]]
        if expected == "SOURCE_BACKED_STRONG":
            assert row["semantic_status"] == "SOURCE_BACKED_STRONG", row
        if expected == "SOURCE_BACKED_PARTIAL":
            assert row["technical_status"] == "VALID_PACKAGE", row
            assert row["runtime_apply_allowed"] is True, row
            assert row["semantic_status"] != "SOURCE_BACKED_STRONG", row
```

Use the existing matrix preparation helper if present.

- [ ] **Step 2: Run matrix test**

```powershell
python -m pytest tests/test_multideck_source_backed_e2e.py -q
```

Expected: FAIL where fixtures currently overstate weak source coverage.

- [ ] **Step 3: Reclassify weak fixtures**

For `tests/fixtures/source_documents_piratedh_strong.json`, reclassify operational claims that lack explicit public Wild guide support:

```json
{
  "claim_kind": "gameplan_posture",
  "source_type": "policy_backed_autonomous_mulligan",
  "source_lane": "policy_fallback",
  "promotion_eligible": false,
  "operator_note": "Public sources establish fast pirate aggro identity only; exact mulligan, target, weapon timing, and sequencing remain policy-backed."
}
```

For `TreantDruid` and `Discolock`, keep only directly supported guide text as promotion-eligible. Mark exact per-card modern keep tables as partial unless the fixture contains explicit accessible source text.

For `PirateRogue`, `Kingslayer`, and `CtAPaladin`, add `deck_match_scope`:

```json
"deck_match_scope": "archetype_matched_not_exact_list"
```

if the guide is archetype-level but not exact list-matched.

- [ ] **Step 4: Add source URLs to matrix docs**

Update `docs/operator/archetype-fixture-matrix.json` with:

```json
{
  "deck_name": "PirateDH",
  "expected_semantic_status": "SOURCE_BACKED_PARTIAL",
  "reason": "Public sources support fast Pirate Demon Hunter identity but not exact mulligan or runtime sequencing.",
  "first_missing_source_action": "find_explicit_wild_piratedh_mulligan_or_gameplay_guide"
}
```

Repeat for any partial deck.

- [ ] **Step 5: Run representative tests**

```powershell
python -m pytest tests/test_multideck_source_backed_e2e.py tests/test_no_default_only_semantic_archetype_matrix.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```powershell
git add tests/fixtures/source_documents_*.json tests/test_multideck_source_backed_e2e.py docs/operator/archetype-fixture-matrix.json
git commit -m "test: align representative deck evidence strength"
```

---

### Task 5: ShadowPriest Darkbishop Regression Closure

**Files:**
- Modify: `tests/test_shadowpriest_depth_e2e.py`
- Modify: `tests/fixtures/shadowpriest_guide_sources.json`
- Modify: `tests/fixtures/source_documents_shadowpriest_strong.json`
- Modify: `src/hsconfig/mulligan_plan.py` only if regression fails.

**Interfaces:**
- Consumes: ShadowPriest source documents and compiled runtime package.
- Produces: Darkbishop effect preserved in CardID/contract, absent from opening-hand keep rows.

- [ ] **Step 1: Add explicit negative mulligan assertion**

Add or keep this assertion in `tests/test_shadowpriest_depth_e2e.py`:

```python
def test_shadowpriest_darkbishop_effect_is_not_mulligan_keep(tmp_path):
    package = prepare_shadowpriest_depth_fixture(tmp_path)
    mulligan = read_runtime_json(package, "Mulligan.json")
    concrete_keeps = json.dumps(mulligan)

    assert "SW_448" not in concrete_keeps

    card_behavior = read_runtime_json(package, "SW_448.json")
    assert "Mind Spike" in json.dumps(card_behavior) or "hero_power" in json.dumps(card_behavior).lower()

    explainability = read_json(package / "source_to_runtime_explainability.json")
    sw448 = next(row for row in explainability["card_rows"] if row["card_id"] == "SW_448")
    assert sw448["strongest_claim_kind"] == "hero_power_transform"
    assert sw448["default_only_risk"] is False
```

Use existing helper names if present.

- [ ] **Step 2: Run ShadowPriest regression**

```powershell
python -m pytest tests/test_shadowpriest_depth_e2e.py -q
```

Expected: PASS. If FAIL, fix claim classification before touching runtime builders.

- [ ] **Step 3: Ensure fixture claim kinds are explicit**

In ShadowPriest fixtures:

```json
{
  "claim_kind": "hero_power_transform",
  "card_ids": ["SW_448"],
  "opening_hand_relevant": false,
  "source_type": "official_card_data"
}
```

Do not encode `SW_448` as `mulligan_keep`. If a source says not to keep 4+ cost cards, encode that as `mulligan_discard` only if the runtime surface can safely express it for this card.

- [ ] **Step 4: Commit Task 5**

```powershell
git add tests/test_shadowpriest_depth_e2e.py tests/fixtures/shadowpriest_guide_sources.json tests/fixtures/source_documents_shadowpriest_strong.json src/hsconfig/mulligan_plan.py
git commit -m "test: lock Darkbishop effect versus mulligan boundary"
```

---

### Task 6: Explainability and First Missing Source Action

**Files:**
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Modify: `tests/test_source_to_runtime_explainability.py`
- Modify: `src/hsconfig/source_claim_gap_report.py`
- Modify: `tests/test_source_claim_gap_report.py`

**Interfaces:**
- Consumes: claim rows, surface decisions, runtime files.
- Produces:
  - per-card `first_missing_source_action`
  - per-card `source_lane`
  - per-card `runtime_lowering_status`
  - package-level operator attention row.

- [ ] **Step 1: Add first missing action test**

Add to `tests/test_source_to_runtime_explainability.py`:

```python
def test_explainability_points_to_first_missing_source_action_for_partial_deck():
    report = build_source_to_runtime_explainability_report(
        audit={
            "claim_rows": [
                {
                    "card_id": "PIRATE_DH_CARD",
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
    assert row["first_missing_source_action"] == "add_explicit_mulligan_source"
    assert row["runtime_lowering_status"] == "policy_backed_runtime"
```

- [ ] **Step 2: Run explainability tests**

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_source_claim_gap_report.py -q
```

Expected: FAIL if fields are missing.

- [ ] **Step 3: Implement fields**

In `src/hsconfig/source_to_runtime_explainability.py`, when building each card row, include:

```python
"source_lane": _best_source_lane(related_claims),
"first_missing_source_action": _next_source_action(
    first_missing_link=first_missing_link,
    why_not_emitted=why_not_emitted,
    claim_kind=claim_kind,
),
"runtime_lowering_status": _runtime_lowering_status(related_claims, runtime_backed),
```

Add:

```python
def _runtime_lowering_status(
    related_claims: Sequence[Mapping[str, Any]], runtime_backed: bool
) -> str:
    if any(str(row.get("source_type")) == "policy_backed_autonomous_mulligan" for row in related_claims):
        return "policy_backed_runtime" if runtime_backed else "policy_backed_contract_only"
    if runtime_backed:
        return "source_backed_runtime"
    if related_claims:
        return "source_backed_contract_only"
    return "missing_source_claim"
```

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_source_claim_gap_report.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```powershell
git add src/hsconfig/source_to_runtime_explainability.py src/hsconfig/source_claim_gap_report.py tests/test_source_to_runtime_explainability.py tests/test_source_claim_gap_report.py
git commit -m "feat: explain first missing source action"
```

---

### Task 7: Docs and Skill Contract

**Files:**
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`

**Interfaces:**
- Produces operator-facing rules matching code behavior.

- [ ] **Step 1: Update source-backed strong docs**

In `docs/operator/source-backed-strong-closure.md`, add this contract:

```markdown
## SOURCE_BACKED_STRONG Contract

HSConfig always attempts to build a technically valid package for a decoded deck.
`SOURCE_BACKED_STRONG` is not required for package generation or load-safe apply.

A package may be `SOURCE_BACKED_STRONG` only when:

- `technical_status=VALID_PACKAGE`
- `runtime_apply_allowed=true`
- every emitted normal runtime row is tied to a non-default source claim or an explicit non-promoting policy fallback
- `default_only_runtime_surfaces=[]`
- policy-backed rows do not count as strong evidence
- snippet-only sources do not count as strong evidence
- static-only claims are marked as `contract_only` or `review_only` unless the runtime surface can safely represent them

Darkbishop Benedictus is the canonical boundary case: the start-of-game hero-power transform belongs in contract/CardID semantics, not in opening-hand mulligan keep logic unless an explicit mulligan source says to keep the card.
```

- [ ] **Step 2: Update guide research policy**

In `docs/operator/guide-research-policy.md` and `.agents/skills/hsconfig/references/guide-research-policy.md`, add:

```markdown
## Source Lanes

- `official_static_semantics`: HearthstoneJSON, Blizzard card library, or equivalent card database facts.
- `deck_matched_public_guide`: explicit public guide for the exact list or close archetype.
- `archetype_matched_public_guide`: explicit guide for the same archetype but not exact decklist.
- `statistical_enrichment`: HSReplay/HSGuru-style aggregate or public stats surface.
- `policy_fallback`: internal autonomous rule used to keep packages useful.
- `default_runtime`: generated default row with no source claim.

Only `official_static_semantics`, `deck_matched_public_guide`, and carefully documented `archetype_matched_public_guide` may promote claims. `statistical_enrichment`, `policy_fallback`, and `default_runtime` must not prove `SOURCE_BACKED_STRONG` by themselves.
```

- [ ] **Step 3: Update skill instructions**

In `.agents/skills/hsconfig/SKILL.md`, add the operating rule:

```markdown
When source coverage is weak, still build the package. Do not block arbitrary decks.
Report the package as load-safe or partial as appropriate.
Do not label policy-backed or default-only runtime rows as `SOURCE_BACKED_STRONG`.
For start-of-game enablers such as Darkbishop Benedictus, separate effect semantics from opening-hand mulligan keep behavior.
```

- [ ] **Step 4: Run docs policy tests**

```powershell
python -m pytest tests/test_operator_docs_contract_policy.py tests/test_contract_spine_sentinel_docs.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 7**

```powershell
git add docs/operator/source-backed-strong-closure.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/guide-research-policy.md
git commit -m "docs: define source-backed strong contract"
```

---

### Task 8: Final Verification and GitHub Sync

**Files:**
- No source files unless verification reveals a narrow bug.

**Interfaces:**
- Produces a tested branch ready for push/merge.

- [ ] **Step 1: Run targeted closure suite**

```powershell
python -m pytest tests/test_source_bundle.py tests/test_claim_kind_runtime_contract.py tests/test_operator_summary.py tests/test_shadowpriest_depth_e2e.py tests/test_no_default_only_semantic_archetype_matrix.py tests/test_multideck_source_backed_e2e.py tests/test_source_to_runtime_explainability.py tests/test_source_claim_gap_report.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broad suite**

```powershell
python -m pytest -q
```

Expected: PASS or known skipped tests only.

- [ ] **Step 3: Build one fresh ShadowPriest proof package**

```powershell
python -m hsconfig configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --hdt-deck-id "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602" --hs-id "2737726722" --online-source --auto-source --json
```

Expected JSON:

```json
{
  "technical_status": "VALID_PACKAGE",
  "runtime_apply_allowed": true,
  "source_bundle_path": "...source_bundle.json"
}
```

Verify in the package from the configure JSON:

```powershell
$result = python -m hsconfig configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --hdt-deck-id "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602" --hs-id "2737726722" --online-source --auto-source --json | ConvertFrom-Json
$packagePath = $result.package_path
if (-not $packagePath) { $packagePath = $result.output_path }
if (-not $packagePath) { $packagePath = Split-Path -Parent $result.operator_summary_path }
if (-not $packagePath) { throw "configure JSON did not expose package_path, output_path, or operator_summary_path" }
$env:HSCONFIG_PACKAGE_PATH = $packagePath
python - <<'PY'
import json
import os
from pathlib import Path

package = Path(os.environ["HSCONFIG_PACKAGE_PATH"])
operator = json.loads((package / "operator_summary.json").read_text(encoding="utf-8"))
bundle = json.loads((package / "source_bundle.json").read_text(encoding="utf-8"))
print(operator["technical_status"])
print(operator["runtime_apply_allowed"])
print(operator.get("default_only_runtime_surfaces"))
print(bundle["promotion"]["first_missing_source_action"])
PY
```

Expected:

```text
VALID_PACKAGE
True
[]
none
```

If `first_missing_source_action` is not `none`, inspect it and decide whether the public source is honestly insufficient. Do not fake strong status.

- [ ] **Step 4: Inspect git status**

```powershell
git status --short
```

Expected: only intended files changed before final commit; clean after commit.

- [ ] **Step 5: Final commit if needed**

```powershell
git add src/hsconfig tests docs .agents
git commit -m "test: prove source-backed strong contract closure"
```

Skip this commit if every task already committed and `git status --short` is clean.

- [ ] **Step 6: Push branch**

```powershell
git push origin HEAD
```

Expected: push succeeds.

---

## Self-Review Checklist

- [ ] Any deck still produces a valid package if the deck code decodes.
- [ ] `SOURCE_BACKED_STRONG` never depends on policy-backed rows, default-only rows, or snippet-only sources.
- [ ] `operator_summary.json` remains the single normal apply authority.
- [ ] `source_bundle.json` is diagnostic/explainability, not a second gate.
- [ ] Darkbishop Benedictus effect semantics remain visible, but `SW_448` is not an inferred mulligan keep.
- [ ] Representative deck fixtures do not overstate weak public evidence.
- [ ] PirateDH remains load-safe/partial unless an explicit public Wild guide is found.
- [ ] No new dependency was added.
- [ ] Full tests pass.
