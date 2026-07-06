# CardID Semantic Lowering Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig lower guide-backed card expectations into the most specific documented HearthRanger VisionAI `CARDID.json` behavior blocks instead of flattening too much into generic play priority.

**Architecture:** Keep HSConfig lean and deterministic: Codex still performs live guide research, HSConfig compiles validated structured claims into runtime JSON. Extend the existing router row as the semantic intermediate by adding explicit `behavior_block`, `rule_id_suffix`, `value`, and `meaningful_runtime_surface` fields; then make the compiler and readiness reports consume those fields. Do not add replay, winrate, postgame tuning, HSTuner orchestration, or normal-path `Presume.json` / `Concede.json` emission.

**Tech Stack:** Python 3.11, pytest, HearthSim `hearthstone` deckstring support, HearthRanger VisionAI JSON files.

---

## Research And Current Evidence

Use these as context, not as runtime inputs:

- `tmp/research/2026-07-06-hsconfig-skill-audit/results/VisionAI_Surface_Coverage.json`
- `tmp/research/2026-07-06-hsconfig-skill-audit/results/Guide_Source_Depth_And_Card_Coverage.json`
- `tmp/research/2026-07-06-hsconfig-recommendation/results/CardID_Semantic_Lowering_Expansion.json`
- Official HearthRanger JSON config help: `https://www.hearthranger.com/onlinehelp/hs/visionai/VisionAI_how_to_understand_json_config.htm`
- Official HearthRanger GlobalValues help: `https://www.hearthranger.com/onlinehelp/hs/visionai/VisionAI_how_to_customize_global_values.htm`
- Official HearthRanger Mulligan help: `https://www.hearthranger.com/onlinehelp/hs/visionai/VisionAI_how_to_customize_mulligan.htm`
- Official HearthRanger Combo help: `https://www.hearthranger.com/onlinehelp/hs/visionai/VisionAI_how_to_customize_combo.htm`

The current gap: `src/hsconfig/compile_cardid.py` can emit several specific blocks, but many guide-backed claims still become generic `InHandPlayPriority` or `BeforePlayCardBonus`. `src/hsconfig/visionai_registry.py` also lacks at least `BeforeOverkilledBonus`, which prior research identified as part of the documented CardID block family.

---

## File Structure

Modify:

- `src/hsconfig/visionai_registry.py`
  - Single source for supported VisionAI runtime block names.
  - Add missing documented card behavior block support.

- `src/hsconfig/card_behavior_router.py`
  - Convert normalized guide claims into explicit semantic behavior rows.
  - Add block selection and suppression reasons before the compiler runs.

- `src/hsconfig/compile_cardid.py`
  - Emit explicit behavior rows with their requested block, condition, value, and rule id.
  - Keep current role fallback, but make it secondary to explicit semantic rows.

- `src/hsconfig/config_readiness.py`
  - Distinguish meaningful CardID behavior from generic generated fallback files.
  - Make card-level gaps clearer for the user.

- `src/hsconfig/guide_source_depth.py`
  - Optionally surface `usable_with_runtime_gaps` when guide coverage exists but behavior lowering is still incomplete.

- `docs/operator/guide-research-policy.md`
  - Document `runtime_block`, `value`, and lowering boundaries for structured guide sources.

- `.agents/skills/hsconfig/references/card-behavior-policy.md`
  - Document the new CardID behavior lowering policy for future Codex use.

- `.agents/skills/hsconfig/references/guide-research-policy.md`
  - Document how guide sources can request a specific runtime block safely.

- `C:\Users\darbo\.codex\skills\hsconfig\...`
  - Sync from `.agents/skills/hsconfig` only after tests pass.

Tests:

- `tests/test_validate_package.py`
- `tests/test_card_behavior_router.py`
- `tests/test_compile_cardid.py`
- `tests/test_config_readiness.py`
- `tests/test_guide_source_depth.py`
- `tests/test_shadowpriest_depth_e2e.py`
- `tests/test_skill_files.py`

Do not modify:

- HSTuner code.
- Replay, HDT, Power.log, winrate, candidate-promotion code.
- Normal-path `Presume.json` / `Concede.json` generation.

---

### Task 1: Close The CardID Block Registry Gap

**Files:**
- Modify: `src/hsconfig/visionai_registry.py`
- Modify: `tests/test_validate_package.py`

- [ ] **Step 1: Add failing registry and validator tests**

Append this to `tests/test_validate_package.py`:

```python
def test_card_behavior_registry_includes_before_overkilled_bonus():
    assert "BeforeOverkilledBonus" in CARD_BEHAVIOR_BLOCKS


def test_validate_package_accepts_before_overkilled_bonus_block(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "EX1_001.json",
        {
            "GameCardId": "EX1_001",
            "ConfigComment": "overkill test",
            "BeforeOverkilledBonus": {
                "values": [
                    {
                        "comment": "prefer overkill line",
                        "condition": "*",
                        "value": "7",
                    }
                ]
            },
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "passed"
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
python -m pytest tests/test_validate_package.py::test_card_behavior_registry_includes_before_overkilled_bonus tests/test_validate_package.py::test_validate_package_accepts_before_overkilled_bonus_block -q
```

Expected: FAIL because `BeforeOverkilledBonus` is missing from `CARD_BEHAVIOR_BLOCKS`.

- [ ] **Step 3: Implement the registry addition**

In `src/hsconfig/visionai_registry.py`, add the block next to the other `Before...Bonus` blocks:

```python
CARD_BEHAVIOR_BLOCKS = frozenset(
    {
        "InHandBonus",
        "OnBoardBonus",
        "BeforePlayCardBonus",
        "BeforeBattlecryTargetBonus",
        "BeforeUseHeroPowerBonus",
        "BeforePhysicalAttackBonus",
        "BeforeOverkilledBonus",
        "BeforeEndTurnBonus",
        "OnDiscoverCardBonus",
        "OnChooseOneCardBonus",
        "OnAdaptCardBonus",
        "BeforeUpgradeCardBonus",
        "InHandPlayPriority",
        "OnBoardPlayPriority",
    }
)
```

- [ ] **Step 4: Verify tests pass**

Run:

```powershell
python -m pytest tests/test_validate_package.py::test_card_behavior_registry_includes_before_overkilled_bonus tests/test_validate_package.py::test_validate_package_accepts_before_overkilled_bonus_block -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/visionai_registry.py tests/test_validate_package.py
git commit -m "feat: support overkill CardID behavior block"
```

---

### Task 2: Add Explicit Behavior Block Rows In The Router

**Files:**
- Modify: `src/hsconfig/card_behavior_router.py`
- Modify: `tests/test_card_behavior_router.py`

The router is the semantic handoff between guide claims and compiler. It should decide the intended CardID block while claims are still explicit.

- [ ] **Step 1: Add failing tests for overkill and explicit runtime block routing**

Append this to `tests/test_card_behavior_router.py`:

```python
def test_router_maps_overkill_mechanic_to_before_overkilled_bonus():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_overkill",
                "claim_kind": "mechanic_usage",
                "cards": ["EX1_001"],
                "mechanic": "overkill",
                "source_confidence": "high",
            }
        ]
    )

    row = report["card_rows"]["EX1_001"][0]

    assert row["behavior_block"] == "BeforeOverkilledBonus"
    assert row["intent"] == "use_overkill_according_to_card_text"
    assert row["roles"] == ["overkill"]
    assert row["meaningful_runtime_surface"] is True
    assert row["value"] == "6"


def test_router_accepts_explicit_documented_runtime_block():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_on_board",
                "claim_kind": "card_role",
                "cards": ["EX1_002"],
                "stance": "keep_on_board",
                "runtime_block": "OnBoardBonus",
                "runtime_value": "9",
                "condition": "my_minion(count(),cardid=EX1_002) > 0",
            }
        ]
    )

    row = report["card_rows"]["EX1_002"][0]

    assert row["behavior_block"] == "OnBoardBonus"
    assert row["intent"] == "keep_on_board"
    assert row["roles"] == ["keep_on_board"]
    assert row["condition"] == "my_minion(count(),cardid=EX1_002) > 0"
    assert row["value"] == "9"
    assert row["meaningful_runtime_surface"] is True


def test_router_suppresses_unsupported_explicit_runtime_block():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_bad_block",
                "claim_kind": "card_role",
                "cards": ["EX1_003"],
                "stance": "bad",
                "runtime_block": "NotARealVisionAIBlock",
            }
        ]
    )

    assert "EX1_003" not in report["card_rows"]
    assert report["suppressed"] == [
        {
            "claim_id": "claim_bad_block",
            "claim_kind": "card_role",
            "cards": ["EX1_003"],
            "reason": "unsupported_card_behavior_block",
            "runtime_block": "NotARealVisionAIBlock",
        }
    ]
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
python -m pytest tests/test_card_behavior_router.py::test_router_maps_overkill_mechanic_to_before_overkilled_bonus tests/test_card_behavior_router.py::test_router_accepts_explicit_documented_runtime_block tests/test_card_behavior_router.py::test_router_suppresses_unsupported_explicit_runtime_block -q
```

Expected: FAIL because the row fields and overkill routing do not exist yet.

- [ ] **Step 3: Add block routing constants and helper functions**

Modify `src/hsconfig/card_behavior_router.py`:

```python
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS


DEFAULT_ROW_VALUE = "6"

ROLE_BLOCKS = {
    "battlecry": "BeforeBattlecryTargetBonus",
    "discover": "OnDiscoverCardBonus",
    "dredge": "OnDiscoverCardBonus",
    "freeze": "BeforePlayCardBonus",
    "hero_power": "BeforeUseHeroPowerBonus",
    "location": "BeforePlayCardBonus",
    "overkill": "BeforeOverkilledBonus",
    "overload": "BeforePlayCardBonus",
    "prefer_enemy_hero": "BeforePlayCardBonus",
    "prefer_enemy_minion": "BeforeBattlecryTargetBonus",
    "prefer_friendly_minion": "BeforePlayCardBonus",
    "secret": "BeforePlayCardBonus",
    "tradeable": "BeforePlayCardBonus",
    "weapon": "BeforePhysicalAttackBonus",
}
```

Add helpers near the bottom:

```python
def _explicit_runtime_block(claim: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    block = claim.get("runtime_block")
    if block is None:
        return None, None
    normalized = str(block)
    if normalized not in CARD_BEHAVIOR_BLOCKS:
        return None, {
            "runtime_block": normalized,
            "reason": "unsupported_card_behavior_block",
        }
    return normalized, None


def _runtime_value(claim: dict[str, Any], default: str = DEFAULT_ROW_VALUE) -> str:
    return str(claim.get("runtime_value", claim.get("value", default)))


def _attach_behavior_fields(
    row: dict[str, Any],
    *,
    behavior_block: str,
    intent: str,
    roles: list[str],
    claim: dict[str, Any],
) -> dict[str, Any]:
    row["behavior_block"] = behavior_block
    row["intent"] = intent
    row["roles"] = roles
    row["rule_id_suffix"] = str(claim.get("rule_id_suffix", intent))
    row["value"] = _runtime_value(claim)
    row["meaningful_runtime_surface"] = True
    return row
```

- [ ] **Step 4: Wire explicit runtime block suppression**

Inside `route_card_behavior_claims`, after `condition_error` handling and before claim-kind branches, add:

```python
        explicit_block, explicit_error = _explicit_runtime_block(claim)
        if explicit_error is not None:
            suppressed.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "claim_kind": claim_kind,
                    "cards": cards,
                    **explicit_error,
                }
            )
            continue
```

- [ ] **Step 5: Update targeting, mechanic, and card_role branches**

Replace the targeting branch body with:

```python
        if claim_kind == "targeting_rule" and str(claim.get("stance")) in TARGETING_STANCES:
            intent = str(claim["stance"])
            behavior_block = explicit_block or ROLE_BLOCKS[intent]
            for card_id in cards:
                row = _base_row(claim, card_id, condition=condition)
                card_rows.setdefault(card_id, []).append(
                    _attach_behavior_fields(
                        row,
                        behavior_block=behavior_block,
                        intent=intent,
                        roles=[intent],
                        claim=claim,
                    )
                )
                strong_cards.add(card_id)
            continue
```

Update `MECHANIC_ROLE_MAP` to include overkill:

```python
MECHANIC_ROLE_MAP = {
    "battlecry": "battlecry",
    "discover": "discover",
    "dredge": "dredge",
    "tradeable": "tradeable",
    "overload": "overload",
    "overkill": "overkill",
    "freeze": "freeze",
    "weapon": "weapon",
    "secret": "secret",
    "location": "location",
}
```

Replace the mechanic branch row creation with:

```python
                behavior_block = explicit_block or ROLE_BLOCKS[role]
                for card_id in cards:
                    row = _base_row(claim, card_id, condition=condition)
                    card_rows.setdefault(card_id, []).append(
                        _attach_behavior_fields(
                            row,
                            behavior_block=behavior_block,
                            intent=f"use_{role}_according_to_card_text",
                            roles=[role],
                            claim=claim,
                        )
                    )
                continue
```

Replace the `card_role` branch row creation with:

```python
                intent = str(claim.get("stance", "deck_card"))
                row = _base_row(claim, card_id, condition=condition)
                if explicit_block is not None:
                    row = _attach_behavior_fields(
                        row,
                        behavior_block=explicit_block,
                        intent=intent,
                        roles=[intent],
                        claim=claim,
                    )
                else:
                    row["intent"] = "in_hand_priority"
                    row["roles"] = [intent]
                    row["rule_id_suffix"] = "in_hand_priority"
                    row["value"] = _runtime_value(claim, default="7")
                    row["meaningful_runtime_surface"] = False
                card_rows.setdefault(card_id, []).append(row)
```

- [ ] **Step 6: Run router tests**

Run:

```powershell
python -m pytest tests/test_card_behavior_router.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/card_behavior_router.py tests/test_card_behavior_router.py
git commit -m "feat: route explicit CardID behavior blocks"
```

---

### Task 3: Compile Explicit Behavior Rows Before Generic Role Fallbacks

**Files:**
- Modify: `src/hsconfig/compile_cardid.py`
- Modify: `tests/test_compile_cardid.py`

- [ ] **Step 1: Add failing compiler tests**

Append this to `tests/test_compile_cardid.py`:

```python
def test_compile_cardid_uses_explicit_behavior_block_rows():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_001": {
                "roles": ["deck_card"],
                "source_claim_ids": [],
                "confidence": "generic_low_confidence",
            }
        },
    }
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_001",
            "behavior_block": "BeforeOverkilledBonus",
            "rule_id_suffix": "overkill_behavior",
            "condition": "my_target(count(),minion=true) > 0",
            "value": "11",
            "roles": ["overkill"],
            "source_claim_ids": ["claim_overkill"],
            "confidence": "guide_backed",
            "meaningful_runtime_surface": True,
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)

    values = files["EX1_001.json"]["BeforeOverkilledBonus"]["values"]
    assert values == [
        {
            "comment": "Fixture: EX1_001_overkill_behavior",
            "condition": "my_target(count(),minion=true) > 0",
            "value": "11",
        }
    ]


def test_compile_cardid_does_not_duplicate_role_fallback_for_explicit_block():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_002": {
                "roles": ["discover"],
                "source_claim_ids": [],
                "confidence": "source_backed",
            }
        },
    }
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_002",
            "behavior_block": "OnDiscoverCardBonus",
            "rule_id_suffix": "prefer_specific_discover",
            "condition": "my_discover(count(),cardid=EX1_003) > 0",
            "value": "12",
            "roles": ["discover"],
            "source_claim_ids": ["claim_discover"],
            "confidence": "guide_backed",
            "meaningful_runtime_surface": True,
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)

    values = files["EX1_002.json"]["OnDiscoverCardBonus"]["values"]
    assert len(values) == 1
    assert values[0]["condition"] == "my_discover(count(),cardid=EX1_003) > 0"
    assert values[0]["value"] == "12"
```

- [ ] **Step 2: Run failing compiler tests**

Run:

```powershell
python -m pytest tests/test_compile_cardid.py::test_compile_cardid_uses_explicit_behavior_block_rows tests/test_compile_cardid.py::test_compile_cardid_does_not_duplicate_role_fallback_for_explicit_block -q
```

Expected: FAIL because `compile_cardid_behaviors` ignores `behavior_block`, row-specific `condition`, and row-specific `value`.

- [ ] **Step 3: Add explicit row handling to compiler**

In `src/hsconfig/compile_cardid.py`, update `_cards_from_rows` to store rows:

```python
def _cards_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("surface_family") != "CARDID.json" and row.get("surface") != "CARDID.json":
            continue
        card_id = str(row["card_id"])
        card = cards.setdefault(
            card_id,
            {
                "roles": [],
                "source_claim_ids": [],
                "confidence": row.get("confidence", "source_backed"),
                "behavior_rows": [],
            },
        )
        card["roles"].extend(str(role) for role in row.get("roles", []))
        if row.get("intent"):
            card["roles"].append(str(row["intent"]))
        card["source_claim_ids"].extend(row.get("source_claim_ids", []))
        if row.get("behavior_block"):
            card["behavior_rows"].append(dict(row))
    return cards
```

Update `_merge_row_cards` to merge row objects:

```python
        card["behavior_rows"] = [
            *list(card.get("behavior_rows", [])),
            *list(row_card.get("behavior_rows", [])),
        ]
```

Add this helper:

```python
def _append_explicit_behavior_rows(
    config: dict[str, Any],
    *,
    deck_name: str,
    card_id: str,
    rows: list[dict[str, Any]],
) -> set[str]:
    emitted_blocks: set[str] = set()
    for row in rows:
        block = str(row.get("behavior_block", ""))
        if not block:
            continue
        _append_block_row(
            config,
            block,
            deck_name,
            card_id,
            str(row.get("rule_id_suffix", row.get("intent", "behavior"))),
            str(row.get("value", "6")),
            [str(item) for item in row.get("source_claim_ids", [])],
            str(row.get("confidence", "source_backed")),
            condition=str(row.get("condition", "*")),
        )
        emitted_blocks.add(block)
    return emitted_blocks
```

Change `_append_block_row` signature and row condition:

```python
def _append_block_row(
    config: dict[str, Any],
    block: str,
    deck_name: str,
    card_id: str,
    rule_id_suffix: str,
    value: str,
    source_claim_ids: list[str],
    confidence: str,
    *,
    condition: str = "*",
) -> None:
    rule_id = f"{card_id}_{rule_id_suffix}"
    config.setdefault(block, {"values": []})["values"].append(
        {
            "comment": f"{deck_name}: {rule_id}",
            "condition": condition,
            "value": value,
        }
    )
```

Inside `compile_cardid_behaviors`, after `config` is created and before generic role blocks are appended, add:

```python
        explicit_blocks = _append_explicit_behavior_rows(
            config,
            deck_name=deck_name,
            card_id=card_id,
            rows=[dict(row) for row in card.get("behavior_rows", [])],
        )
```

In the role fallback loop, skip blocks already emitted explicitly:

```python
            if block is None or block in explicit_blocks:
                continue
```

- [ ] **Step 4: Run compiler tests**

Run:

```powershell
python -m pytest tests/test_compile_cardid.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/compile_cardid.py tests/test_compile_cardid.py
git commit -m "feat: compile explicit CardID behavior rows"
```

---

### Task 4: Tighten Readiness Around Meaningful CardID Behavior

**Files:**
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `tests/test_config_readiness.py`

The user-facing problem is not just whether a `CARDID.json` file exists. A generated fallback file is structurally useful, but it should not silently count as deep semantic coverage.

- [ ] **Step 1: Add failing readiness test**

Append this to `tests/test_config_readiness.py`:

```python
def test_readiness_counts_only_meaningful_cardid_rows_as_runtime_emitted():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": [
                {"card_id": "EX1_GENERIC", "name": "Generic", "count": 1},
                {"card_id": "EX1_DEEP", "name": "Deep", "count": 1},
            ],
        },
        claim_coverage={"uncovered_cards": []},
        gameplan_contract={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": {
                "EX1_GENERIC": {
                    "card_id": "EX1_GENERIC",
                    "name": "Generic",
                    "coverage_status": "guide_backed",
                    "roles": ["deck_card"],
                },
                "EX1_DEEP": {
                    "card_id": "EX1_DEEP",
                    "name": "Deep",
                    "coverage_status": "guide_backed",
                    "roles": ["overkill"],
                },
            },
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={
            "rows": [
                {
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "card_id": "EX1_GENERIC",
                    "roles": ["deck_card"],
                    "meaningful_runtime_surface": False,
                },
                {
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "card_id": "EX1_DEEP",
                    "roles": ["overkill"],
                    "behavior_block": "BeforeOverkilledBonus",
                    "meaningful_runtime_surface": True,
                },
            ],
            "suppressed": [],
        },
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files={"EX1_GENERIC.json", "EX1_DEEP.json"},
    )

    assert report["cards"]["EX1_DEEP"]["readiness_lane"] == "runtime_emitted"
    assert report["cards"]["EX1_DEEP"]["first_missing_link"] == "none"
    assert report["cards"]["EX1_GENERIC"]["readiness_lane"] == "report_only_supported"
    assert report["cards"]["EX1_GENERIC"]["first_missing_link"] == "needs_runtime_surface"
```

- [ ] **Step 2: Run failing readiness test**

Run:

```powershell
python -m pytest tests/test_config_readiness.py::test_readiness_counts_only_meaningful_cardid_rows_as_runtime_emitted -q
```

Expected: FAIL because any CardID row currently counts as concrete.

- [ ] **Step 3: Implement meaningful row filtering**

In `src/hsconfig/config_readiness.py`, replace `_cards_from_card_behavior` with:

```python
def _cards_from_card_behavior(card_behavior_plan: dict[str, Any]) -> set[str]:
    return {
        str(row["card_id"])
        for row in card_behavior_plan.get("rows", [])
        if _is_meaningful_cardid_runtime_row(row)
    }
```

Add:

```python
def _is_meaningful_cardid_runtime_row(row: Any) -> bool:
    return (
        _is_cardid_runtime_row(row)
        and row.get("meaningful_runtime_surface") is True
        and bool(row.get("behavior_block"))
    )
```

Keep `_is_cardid_runtime_row` as the generic shape check, because it is still useful for diagnostics and future report rows.

- [ ] **Step 4: Run config readiness tests**

Run:

```powershell
python -m pytest tests/test_config_readiness.py -q
```

Expected: PASS. If existing tests expected generic rows to be runtime-emitted, update those assertions so generic rows remain visible but not treated as deep runtime behavior.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/config_readiness.py tests/test_config_readiness.py
git commit -m "feat: distinguish meaningful CardID readiness"
```

---

### Task 5: Surface Runtime Gaps More Clearly In Depth Reports

**Files:**
- Modify: `src/hsconfig/guide_source_depth.py`
- Modify: `tests/test_guide_source_depth.py`

Current `depth_status=usable` can still contain runtime-surface warnings. Keep this permissive, but make it explicit so the user can see that a package is valid yet still has lowering work.

- [ ] **Step 1: Add failing depth status test**

Append this to `tests/test_guide_source_depth.py`:

```python
def test_depth_report_marks_usable_with_runtime_gaps():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [{"claim_kind": "card_role", "source_family": "guide"}],
            "unsupported_claims": [],
        },
        config_readiness_report={
            "summary": {"total_cards": 2},
            "cards": {
                "EX1_READY": {
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                },
                "EX1_GAP": {
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                },
            },
        },
    )

    assert report["depth_status"] == "usable_with_runtime_gaps"
    assert report["summary"]["cards_needing_runtime_surface"] == 1
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest tests/test_guide_source_depth.py::test_depth_report_marks_usable_with_runtime_gaps -q
```

Expected: FAIL because the summary lacks `cards_needing_runtime_surface` and status remains `usable`.

- [ ] **Step 3: Implement explicit runtime-gap summary**

In `src/hsconfig/guide_source_depth.py`, add:

```python
    cards_needing_runtime_surface = sum(
        1 for warning in warnings if warning["reason"] == "needs_runtime_surface"
    )
```

Update depth status logic:

```python
    depth_status = "usable"
    if total_cards > 0 and supported_cards == 0 and cards_needing_guide_claims == 0:
        depth_status = "insufficient"
    if total_cards > 0 and cards_needing_runtime_surface > 0 and cards_needing_guide_claims == 0:
        depth_status = "usable_with_runtime_gaps"
    if total_cards > 0 and cards_needing_guide_claims > 0:
        depth_status = "needs_more_research"
```

Add the summary field:

```python
            "cards_needing_runtime_surface": cards_needing_runtime_surface,
```

- [ ] **Step 4: Run guide depth tests**

Run:

```powershell
python -m pytest tests/test_guide_source_depth.py -q
```

Expected: PASS. If older tests expected `usable` with runtime warnings, update them to `usable_with_runtime_gaps`.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/guide_source_depth.py tests/test_guide_source_depth.py
git commit -m "feat: expose runtime gaps in guide depth"
```

---

### Task 6: Add A ShadowPriest Regression For Specific Lowering

**Files:**
- Modify: `tests/fixtures/shadowpriest_guide_sources.json`
- Modify: `tests/test_shadowpriest_depth_e2e.py`

The current ShadowPriest fixture already proves broad coverage. Extend it only enough to prove explicit block lowering without making the fixture unrealistic.

- [ ] **Step 1: Add one explicit runtime block claim to the fixture**

In `tests/fixtures/shadowpriest_guide_sources.json`, add or update one claim for `SW_446` Voidtouched Attendant to include a direct enemy-hero pressure rule. Use this shape inside the appropriate source document's `claims` array:

```json
{
  "claim_kind": "targeting_rule",
  "cards": ["SW_446"],
  "stance": "prefer_enemy_hero",
  "runtime_block": "BeforePlayCardBonus",
  "runtime_value": "12",
  "condition": "*",
  "evidence_text_short": "Voidtouched Attendant should support the face-damage pressure plan.",
  "source_confidence": "high"
}
```

If a similar claim already exists, add only `runtime_block` and `runtime_value` to that existing claim.

- [ ] **Step 2: Add E2E assertion for specific lowering**

In `tests/test_shadowpriest_depth_e2e.py`, inside `test_shadowpriest_depth_reports_show_broad_card_coverage`, after loading `mulligan`, load the card file:

```python
    voidtouched = json.loads(
        (out / "CustomConfig" / "shadowpriest" / "SW_446.json").read_text(
            encoding="utf-8"
        )
    )
```

Then assert:

```python
    before_play_values = voidtouched["BeforePlayCardBonus"]["values"]
    assert any(
        row["value"] == "12"
        and "prefer_enemy_hero" in row["comment"]
        for row in before_play_values
    )
```

Also assert the depth status allows either fully usable or usable with gaps:

```python
    assert depth["depth_status"] in {"usable", "usable_with_runtime_gaps"}
```

- [ ] **Step 3: Run the ShadowPriest depth test**

Run:

```powershell
python -m pytest tests/test_shadowpriest_depth_e2e.py::test_shadowpriest_depth_reports_show_broad_card_coverage -q
```

Expected: PASS.

- [ ] **Step 4: Run full ShadowPriest tests**

Run:

```powershell
python -m pytest tests/test_shadowpriest_depth_e2e.py tests/test_shadowpriest_e2e.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/fixtures/shadowpriest_guide_sources.json tests/test_shadowpriest_depth_e2e.py
git commit -m "test: prove specific ShadowPriest CardID lowering"
```

---

### Task 7: Update Operator And Skill Documentation

**Files:**
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `tests/test_skill_files.py`

- [ ] **Step 1: Add failing docs test**

Append this to `tests/test_skill_files.py`:

```python
def test_skill_docs_describe_cardid_runtime_block_lowering():
    root = Path(".agents/skills/hsconfig")
    card_policy = (root / "references" / "card-behavior-policy.md").read_text(encoding="utf-8")
    guide_policy = (root / "references" / "guide-research-policy.md").read_text(encoding="utf-8")

    assert "runtime_block" in guide_policy
    assert "BeforeOverkilledBonus" in card_policy
    assert "meaningful_runtime_surface" in card_policy
    assert "Presume.json" in card_policy
    assert "Concede.json" in card_policy
```

- [ ] **Step 2: Run failing docs test**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_skill_docs_describe_cardid_runtime_block_lowering -q
```

Expected: FAIL until docs are updated.

- [ ] **Step 3: Update card behavior policy**

Replace `.agents/skills/hsconfig/references/card-behavior-policy.md` with:

```markdown
# Card Behavior Policy

Every deck card must be represented in the gameplan contract.

Emit `<CARDID>.json` when documented VisionAI syntax can express a guide-backed
behavior, priority, target, discover, choice, attack, hero-power, overkill,
end-turn, upgrade, or timing rule.

Prefer the most specific documented block:

- `InHandBonus` for card value while held.
- `OnBoardBonus` for board-presence value.
- `BeforePlayCardBonus` for play-now timing.
- `BeforeBattlecryTargetBonus` for targeted Battlecry behavior.
- `BeforeUseHeroPowerBonus` for active hero-power use.
- `BeforePhysicalAttackBonus` for minion, hero, or weapon attack posture.
- `BeforeOverkilledBonus` for Overkill-specific payoff lines.
- `BeforeEndTurnBonus` for end-turn state preferences.
- `OnDiscoverCardBonus` for Discover option preferences.
- `OnChooseOneCardBonus` for resolved Choose One option preferences.
- `OnAdaptCardBonus` for resolved Adapt option preferences.
- `BeforeUpgradeCardBonus` for documented upgrade behavior.
- `InHandPlayPriority` and `OnBoardPlayPriority` only for search-order hints.

Guide claims may request a specific `runtime_block` only when the block is part
of the documented CardID behavior registry. Unsupported blocks stay in reports.

`meaningful_runtime_surface=true` means the row expresses a specific guide-backed
runtime behavior. Generic generated CardID fallback files must stay visible, but
they do not prove deep card-specific lowering.

If a claim cannot be lowered safely, keep it in reports instead of inventing
unsupported runtime syntax.

Do not emit `Presume.json` or `Concede.json` in the normal HSConfig path.
```

- [ ] **Step 4: Update guide research policy**

In `.agents/skills/hsconfig/references/guide-research-policy.md`, add this under the structured source shape section:

```markdown
Optional CardID lowering fields for card-specific claims:

- `runtime_block`: documented CardID block to use, for example
  `BeforePlayCardBonus`, `OnDiscoverCardBonus`, or `BeforeOverkilledBonus`.
- `runtime_value`: numeric string to emit in the VisionAI row.
- `condition`: VisionAI condition string. Use `*` unless the source clearly
  supports a condition.

Use `runtime_block` only for guide-backed or static-semantics-backed claims.
If the exact block is uncertain, omit it and let HSConfig route or report the
gap.
```

- [ ] **Step 5: Update operator guide policy**

In `docs/operator/guide-research-policy.md`, add the same operator-facing guidance:

```markdown
For CardID behavior claims, prefer source-backed `runtime_block` when the guide
or card text clearly maps to a documented VisionAI block. Examples:

- face pressure or play timing: `BeforePlayCardBonus`
- targeted Battlecry: `BeforeBattlecryTargetBonus`
- Hero Power use: `BeforeUseHeroPowerBonus`
- attack or weapon posture: `BeforePhysicalAttackBonus`
- Overkill payoff: `BeforeOverkilledBonus`
- Discover option preference: `OnDiscoverCardBonus`

Do not request undocumented blocks. Unsupported blocks are suppressed into
reports and do not become runtime JSON.
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add docs/operator/guide-research-policy.md .agents/skills/hsconfig/references/card-behavior-policy.md .agents/skills/hsconfig/references/guide-research-policy.md tests/test_skill_files.py
git commit -m "docs: describe CardID semantic lowering"
```

---

### Task 8: Sync Installed Skill Copy

**Files:**
- Source: `.agents/skills/hsconfig/**`
- Target: `C:\Users\darbo\.codex\skills\hsconfig\**`

Only run after the repo skill files and tests are green.

- [ ] **Step 1: Sync the installed skill files**

Run:

```powershell
$source = "C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig"
$target = "C:\Users\darbo\.codex\skills\hsconfig"
if (Test-Path -LiteralPath $target) {
  Remove-Item -LiteralPath $target -Recurse -Force
}
Copy-Item -LiteralPath $source -Destination $target -Recurse
```

- [ ] **Step 2: Verify installed skill references**

Run:

```powershell
Get-Content -Raw "C:\Users\darbo\.codex\skills\hsconfig\references\card-behavior-policy.md" | Select-String "BeforeOverkilledBonus"
Get-Content -Raw "C:\Users\darbo\.codex\skills\hsconfig\references\guide-research-policy.md" | Select-String "runtime_block"
```

Expected: both commands print matching lines.

- [ ] **Step 3: Commit repo changes only**

The installed skill copy is outside the repo. Do not stage it.

Run:

```powershell
git status --short --branch
```

Expected: no new tracked repo changes from the copy operation.

---

### Task 9: Final Verification

**Files:**
- No new source files.
- Verify all changed source, tests, docs, and skill references.

- [ ] **Step 1: Run focused CardID and readiness tests**

Run:

```powershell
python -m pytest tests/test_validate_package.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_guide_source_depth.py -q
```

Expected: PASS.

- [ ] **Step 2: Run ShadowPriest E2E tests**

Run:

```powershell
python -m pytest tests/test_shadowpriest_depth_e2e.py tests/test_shadowpriest_e2e.py -q
```

Expected: PASS.

- [ ] **Step 3: Run docs and skill tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_prepare_cli.py -q
```

Expected: PASS.

- [ ] **Step 4: Run the full suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Run a ShadowPriest prepare smoke**

Run:

```powershell
$out = "C:\Users\darbo\Documents\HSConfig\tmp\cardid_lowering_shadowpriest_smoke"
if (Test-Path -LiteralPath $out) {
  Remove-Item -LiteralPath $out -Recurse -Force
}
python -m hsconfig prepare `
  --deck-name "ShadowPriest" `
  --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
  --runtime-root "C:\Users\darbo\Desktop\HS" `
  --out $out `
  --guide-sources-json "tests\fixtures\shadowpriest_guide_sources.json" `
  --json
python -m hsconfig validate --package $out --json
```

Expected:

- `prepare` prints `"status": "passed"`.
- `validate` prints `"status": "passed"`.
- `guide_source_depth_status` is `usable` or `usable_with_runtime_gaps`.

- [ ] **Step 6: Inspect generated CardID file**

Run:

```powershell
Get-Content -Raw "$out\CustomConfig\shadowpriest\SW_446.json"
```

Expected: output includes a specific `BeforePlayCardBonus` row for the guide-backed enemy-hero pressure rule.

- [ ] **Step 7: Remove smoke output**

Run:

```powershell
if (Test-Path -LiteralPath $out) {
  Remove-Item -LiteralPath $out -Recurse -Force
}
```

- [ ] **Step 8: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: clean except no ignored cache output shown by default.

- [ ] **Step 9: Push if this branch is main and all tests passed**

Run:

```powershell
git push origin main
```

Expected: push succeeds.

---

## Acceptance Criteria

- `BeforeOverkilledBonus` is accepted by registry and validator.
- Router rows can carry explicit `behavior_block`, row `condition`, row `value`, and `meaningful_runtime_surface`.
- Compiler emits explicit behavior rows into the requested documented CardID block.
- Generic generated CardID fallback files do not falsely count as deep runtime behavior.
- Guide-depth reports expose runtime gaps as `usable_with_runtime_gaps` instead of hiding them behind plain `usable`.
- ShadowPriest still produces a valid package and now proves at least one specific CardID lowering path.
- No replay, winrate, postgame tuning, HSTuner, `Presume.json`, or `Concede.json` normal-path scope is added.
- Full test suite passes.

---

## Self-Review

- Spec coverage: The recommendation was to prioritize CardID semantic lowering over orchestration, SOP-only work, or apply hardening. Tasks 1-6 implement that. Task 7 documents it. Task 8 syncs the installed skill. Task 9 verifies it.
- Placeholder scan: No `TBD`, `TODO`, or unspecified test steps remain.
- Scope check: This plan touches only HSConfig pre-run config generation. It does not add HSTuner, replay, winrate, or postgame tuning.
- Type consistency: Router row fields are consistently named `behavior_block`, `rule_id_suffix`, `value`, `condition`, and `meaningful_runtime_surface`; compiler and readiness tasks consume the same names.
