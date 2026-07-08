# HSConfig Report Consistency And Choice Surface Lowering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig reports internally consistent, keep the normal operator path lean, and close the next documented pre-run choice-surface lowering gap for Discover and Choose One behavior.

**Architecture:** Fix the report authority chain first: `source_claim_gap_report.json` owns the canonical first missing chain, and `strong_promotion_report.json` must not recompute a competing value. Then tighten the normal CLI/docs path without removing expert compatibility. Finally, extend the existing card behavior router/compiler path so source-backed choice claims become documented per-card `<CARDID>.json` behavior rows when option identity is resolved, while ambiguous rows stay suppressed and visible.

**Tech Stack:** Python 3, argparse, pytest, JSON artifacts, HearthRanger VisionAI CustomConfig, existing HSConfig modules under `src/hsconfig`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- HSConfig remains pre-run only: no replay parsing, no winrate inspection, no post-game tuning, no HSTuner orchestration.
- Normal operator path remains `source-manifest -> draft-source-documents -> research-deck -> prepare -> apply`.
- `reports/operator_summary.json` remains the single normal apply gate.
- Do not make `Presume.json` or `Concede.json` normal outputs.
- Do not add dependencies.
- Preserve existing expert and fixture flags; de-emphasize them instead of removing them.
- Use source-backed or static-semantics-backed claims only for runtime lowering.
- Keep ambiguous choice evidence visible in reports; do not guess runtime syntax.

---

## File Structure

- Modify `src/hsconfig/strong_promotion_report.py`
  - Responsibility: promotion confirmation report.
  - Change: consume `source_claim_gap_report.summary.first_missing_chain` as canonical data.

- Modify `tests/test_strong_promotion_report.py`
  - Responsibility: unit coverage for strong promotion report semantics.
  - Change: add regression coverage where alphabetical order and priority order disagree.

- Modify `src/hsconfig/cli_parser.py`
  - Responsibility: CLI command and help shape.
  - Change: group normal `prepare` inputs separately from expert/fixture inputs.

- Modify `tests/test_cli_help.py`
  - Responsibility: CLI help contract.
  - Change: assert the normal path appears before expert/fixture inputs.

- Modify `docs/operator/README.md`
  - Responsibility: normal operator entry point.
  - Change: standardize wording around per-card `<CARDID>.json` and expert path separation.

- Modify `.agents/skills/hsconfig/SKILL.md`
  - Responsibility: installed skill entry instructions.
  - Change: mirror the lean operator wording and preserve pre-run boundary.

- Modify `.agents/skills/hsconfig/references/workflow.md`
  - Responsibility: skill workflow detail.
  - Change: mirror normal path and per-card `<CARDID>.json` wording.

- Modify `.agents/skills/hsconfig/references/card-behavior-policy.md`
  - Responsibility: Card behavior lowering policy.
  - Change: document resolved Discover and Choose One lowering, and unresolved option suppression.

- Modify `src/hsconfig/card_behavior_surface_router.py`
  - Responsibility: claim-to-card-behavior row routing.
  - Change: derive a documented `my_discover(count(),cardid=<OPTION>) > 0` condition for resolved `discover_choice` claims that do not supply a condition.

- Modify `tests/test_card_behavior_router.py`
  - Responsibility: router-level behavior.
  - Change: add failing tests for resolved Discover default condition and Choose One explicit authoring.

- Modify `tests/test_prepare_cli.py`
  - Responsibility: end-to-end prepare behavior.
  - Change: assert `prepare` writes concrete `OnDiscoverCardBonus` and `OnChooseOneCardBonus` per-card files when option identity is resolved.

- Optional modify `tests/test_skill_files.py`
  - Responsibility: active skill docs contract.
  - Change only if docs changes require updated expected wording.

---

### Task 1: Canonical First Missing Chain In Strong Promotion Report

**Files:**
- Modify: `src/hsconfig/strong_promotion_report.py`
- Modify: `tests/test_strong_promotion_report.py`

**Interfaces:**
- Consumes: `source_claim_gap_report: dict[str, Any]` with optional `summary.first_missing_chain`.
- Produces: `strong_promotion_report["first_missing_chain"]` matching the canonical summary object when present.

- [ ] **Step 1: Add the failing priority-order regression test**

Append this test to `tests/test_strong_promotion_report.py`:

```python
def test_report_reuses_source_gap_summary_first_missing_chain_priority_order():
    canonical = {
        "card_id": "ZZZ_HIGH_PRIORITY",
        "name": "High Priority Card",
        "first_missing_link": "needs_runtime_surface",
        "recommended_source_claim_kind": "targeting_rule",
        "next_action": "add_runtime_lowerable_claim_or_router_support",
        "priority_score": 85,
        "priority_reason": "runtime surface gap outranks guide claim gap",
    }

    report = build_strong_promotion_report(
        deck_name="CuteWarrior",
        fixture_stage="runtime_prepare",
        operator_summary={
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "semantic_blockers": [{"reason": "cards_need_runtime_surface", "count": 1}],
            "generated_files": [],
        },
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 2,
                "first_missing_chain": canonical,
            },
            "cards": {
                "AAA_LOW_PRIORITY": {
                    "first_missing_link": "needs_guide_claim",
                    "recommended_source_claim_kind": "card_role",
                    "next_action": "add_card_specific_source_claim",
                },
                "ZZZ_HIGH_PRIORITY": {
                    "first_missing_link": "needs_runtime_surface",
                    "recommended_source_claim_kind": "targeting_rule",
                    "next_action": "add_runtime_lowerable_claim_or_router_support",
                },
            },
        },
    )

    assert report["promotion_ready"] is False
    assert report["verdict"] == "PROMOTION_BLOCKED"
    assert report["next_action"] == "close_first_missing_chain"
    assert report["first_missing_chain"] == canonical
```

- [ ] **Step 2: Run the focused test and verify the current failure**

Run:

```powershell
python -m pytest tests/test_strong_promotion_report.py::test_report_reuses_source_gap_summary_first_missing_chain_priority_order -q
```

Expected: FAIL because `strong_promotion_report.py` currently scans `cards` and returns `AAA_LOW_PRIORITY` instead of `summary.first_missing_chain`.

- [ ] **Step 3: Update the implementation to consume the canonical summary**

In `src/hsconfig/strong_promotion_report.py`, change the `_report_next_action` and `_first_missing_chain` type hints and helper body to:

```python
def _report_next_action(
    *,
    promotion_ready: bool,
    operator_summary: dict[str, Any],
    first_missing_chain: dict[str, Any] | None,
) -> str:
    if promotion_ready:
        return "fixture_can_be_core_source_backed"
    if operator_summary.get("technical_status") != "VALID_PACKAGE":
        return str(operator_summary.get("next_action", ""))
    if (
        operator_summary.get("next_action") == "SOURCE_INFORMED_APPLY_READY"
        and isinstance(operator_summary.get("source_informed_apply_readiness"), dict)
        and operator_summary["source_informed_apply_readiness"].get("status") == "ready"
    ):
        return "source_informed_apply_ready_but_not_strong"
    return "close_first_missing_chain"


def _first_missing_chain(source_claim_gap_report: dict[str, Any]) -> dict[str, Any] | None:
    summary = source_claim_gap_report.get("summary", {})
    if isinstance(summary, dict):
        canonical = summary.get("first_missing_chain")
        if isinstance(canonical, dict):
            return dict(canonical)

    cards = source_claim_gap_report.get("cards", {})
    if not isinstance(cards, dict):
        return None
    for card_id, row in sorted(cards.items()):
        if not isinstance(row, dict):
            continue
        if row.get("first_missing_link") == "none":
            continue
        return {
            "card_id": str(card_id),
            "first_missing_link": str(row.get("first_missing_link", "")),
            "recommended_source_claim_kind": str(row.get("recommended_source_claim_kind", "")),
            "next_action": str(row.get("next_action", "")),
        }
    return None
```

- [ ] **Step 4: Run focused report tests**

Run:

```powershell
python -m pytest tests/test_strong_promotion_report.py -q
```

Expected: all tests in `tests/test_strong_promotion_report.py` pass.

- [ ] **Step 5: Run the prepare report smoke test**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py::test_prepare_writes_source_gap_and_promotion_reports -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add src/hsconfig/strong_promotion_report.py tests/test_strong_promotion_report.py
git commit -m "fix: use canonical source gap chain in promotion report"
```

Expected: commit succeeds.

---

### Task 2: Lean Normal Operator Help And Wording

**Files:**
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `tests/test_cli_help.py`
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Optional modify: `tests/test_skill_files.py`

**Interfaces:**
- Consumes: existing CLI commands and flags.
- Produces: same command behavior, clearer help grouping, normalized operator wording.

- [ ] **Step 1: Add CLI help contract test**

Append this test to `tests/test_cli_help.py`:

```python
def test_prepare_help_groups_normal_inputs_before_expert_fixture_inputs(capsys):
    help_text = _subcommand_help("prepare", capsys)

    assert "normal required inputs" in help_text.lower()
    assert "expert/fixture inputs" in help_text.lower()
    assert help_text.lower().index("normal required inputs") < help_text.lower().index(
        "expert/fixture inputs"
    )
    assert "--deck-name" in help_text
    assert "--deck-code" in help_text
    assert "--guide-sources-json" in help_text
    assert "--cards-json" in help_text
    assert "--claims-json" in help_text
```

- [ ] **Step 2: Run the new help test and verify failure**

Run:

```powershell
python -m pytest tests/test_cli_help.py::test_prepare_help_groups_normal_inputs_before_expert_fixture_inputs -q
```

Expected: FAIL because the current `prepare` parser does not define those argument groups.

- [ ] **Step 3: Group `prepare` arguments without changing accepted flags**

In `src/hsconfig/cli_parser.py`, replace the current `prepare.add_argument(...)` block with:

```python
    prepare = subparsers.add_parser(
        "prepare",
        help="normal package creation path",
        description=(
            "Normal package creation path. Use deck identity, source-backed guide "
            "documents, and a runtime root to compile a pre-run CustomConfig package."
        ),
    )
    prepare_normal = prepare.add_argument_group("normal required inputs")
    prepare_normal.add_argument("--deck-name", required=True)
    prepare_normal.add_argument("--deck-code", required=True)
    prepare_normal.add_argument("--out", required=True)
    prepare_normal.add_argument("--runtime-root", required=True)

    prepare_source = prepare.add_argument_group("normal source inputs")
    prepare_source.add_argument("--guide-sources-json")
    prepare_source.add_argument("--source-documents-json")

    prepare_execution = prepare.add_argument_group("execution modifiers")
    prepare_execution.add_argument(
        "--auto-research-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    prepare_execution.add_argument("--json", action="store_true")

    prepare_expert = prepare.add_argument_group("expert/fixture inputs")
    prepare_expert.add_argument("--cards-json")
    prepare_expert.add_argument("--claims-json")
    prepare_expert.add_argument("--plan-reports-dir")
    prepare_expert.add_argument("--allow-placeholder", action="store_true")
```

- [ ] **Step 4: Run CLI help tests**

Run:

```powershell
python -m pytest tests/test_cli_help.py tests/test_scope_boundaries.py tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 5: Normalize active docs wording**

Edit the active docs so human-facing wording uses:

```markdown
per-card `<CARDID>.json`
```

Use this exact command to find active wording drift:

```powershell
rg -n "CardID\.json|<CardID>\.json|per-card CardID|CARDID\.json" README.md docs\operator .agents\skills\hsconfig
```

Expected after edits:

- active docs use `per-card <CARDID>.json` for the runtime file family;
- `Presume.json` and `Concede.json` appear only as non-normal-path compatibility or blocked-surface text;
- no doc says HSConfig tunes after games.

- [ ] **Step 6: Run docs and skill tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py tests/test_operator_guidance.py -q
```

Expected: PASS. If an assertion checks the older wording, update the assertion to the normalized text only when the doc behavior remains unchanged.

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add src/hsconfig/cli_parser.py tests/test_cli_help.py docs/operator/README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md .agents/skills/hsconfig/references/card-behavior-policy.md tests/test_skill_files.py
git commit -m "docs: clarify normal hsconfig operator path"
```

Expected: commit succeeds. If `tests/test_skill_files.py` was not modified, leave it unstaged.

---

### Task 3: Router-Level Discover And Choose One Choice Closure

**Files:**
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `tests/test_card_behavior_router.py`

**Interfaces:**
- Consumes: source-backed `discover_choice` and `choose_one_choice` claims.
- Produces: routed `CARDID.json` rows with documented behavior blocks and safe conditions.

- [ ] **Step 1: Add router tests for resolved choice surfaces**

Append these tests to `tests/test_card_behavior_router.py`:

```python
def test_resolved_discover_choice_derives_my_discover_condition():
    plan = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_pick_option_alpha",
                "claim_kind": "discover_choice",
                "cards": ["DISCOVER_CARD"],
                "option_card_id": "OPTION_ALPHA",
                "stance": "pick_option_alpha",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "runtime_value": "11",
            }
        ],
        identity_links={
            "DISCOVER_CARD": [
                {"link_kind": "entourage", "card_id": "OPTION_ALPHA"},
            ]
        },
    )

    assert plan["suppressed"] == []
    assert plan["option_resolution"] == [
        {
            "claim_id": "claim_pick_option_alpha",
            "card_id": "DISCOVER_CARD",
            "option_card_id": "OPTION_ALPHA",
            "status": "resolved",
        }
    ]
    row = plan["card_rows"]["DISCOVER_CARD"][0]
    assert row["behavior_block"] == "OnDiscoverCardBonus"
    assert row["condition"] == "my_discover(count(),cardid=OPTION_ALPHA) > 0"
    assert row["intent"] == "pick_option_alpha"
    assert row["value"] == "11"
    assert row["meaningful_runtime_surface"] is True


def test_choose_one_choice_with_resolved_option_lowers_to_choose_one_block():
    plan = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_choose_option_alpha",
                "claim_kind": "choose_one_choice",
                "cards": ["CHOOSE_CARD"],
                "choice_card_id": "OPTION_ALPHA",
                "stance": "choose_option_alpha",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "runtime_value": "9",
            }
        ],
        identity_links={
            "CHOOSE_CARD": [
                {"link_kind": "entourage", "card_id": "OPTION_ALPHA"},
            ]
        },
    )

    assert plan["suppressed"] == []
    row = plan["card_rows"]["CHOOSE_CARD"][0]
    assert row["behavior_block"] == "OnChooseOneCardBonus"
    assert row["condition"] == "*"
    assert row["intent"] == "choose_option_alpha"
    assert row["meaningful_runtime_surface"] is True
```

- [ ] **Step 2: Run the new router tests and verify failure for Discover condition**

Run:

```powershell
python -m pytest tests/test_card_behavior_router.py::test_resolved_discover_choice_derives_my_discover_condition tests/test_card_behavior_router.py::test_choose_one_choice_with_resolved_option_lowers_to_choose_one_block -q
```

Expected: the Discover test fails because the current condition is `*`; the Choose One test may already pass, which is acceptable because it locks the contract.

- [ ] **Step 3: Implement safe Discover default condition derivation**

In `src/hsconfig/card_behavior_surface_router.py`, add this helper near `_claim_option_card_id`:

```python
def _choice_surface_condition(
    claim_kind: str,
    condition: str,
    option_card_id: str | None,
) -> str:
    if condition != "*":
        return condition
    if claim_kind == "discover_choice" and option_card_id:
        return f"my_discover(count(),cardid={option_card_id}) > 0"
    return condition
```

Then update `route_card_behavior_surfaces(...)` after unresolved option checks and before rows are emitted:

```python
        option_card_id = _claim_option_card_id(claim)
        unresolved = _option_resolution_rows(
            claim=claim,
            claim_kind=claim_kind,
            cards=cards,
            identity_links=identity_links,
        )
        option_resolution.extend(unresolved)
        if any(row["status"] == "unresolved" for row in unresolved):
            suppressed.append(
                _suppressed_row(claim, claim_kind, cards, "unresolved_option_identity")
            )
            continue
        condition = _choice_surface_condition(claim_kind, condition, option_card_id)
```

Keep all existing unresolved-option behavior unchanged.

- [ ] **Step 4: Run router tests**

Run:

```powershell
python -m pytest tests/test_card_behavior_router.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add src/hsconfig/card_behavior_surface_router.py tests/test_card_behavior_router.py
git commit -m "feat: lower resolved discover choice conditions"
```

Expected: commit succeeds.

---

### Task 4: Prepare-Level Choice Surface Proof

**Files:**
- Modify: `tests/test_prepare_cli.py`

**Interfaces:**
- Consumes: `hsconfig prepare` with source documents and mocked HearthstoneJSON linked entities.
- Produces: generated per-card `<CARDID>.json` files containing `OnDiscoverCardBonus` and `OnChooseOneCardBonus` rows.

- [ ] **Step 1: Strengthen existing Discover prepare test**

In `tests/test_prepare_cli.py`, inside `test_prepare_routes_option_claim_with_identity_links`, after `discover_claim = next(...)`, add:

```python
    discover_config = json.loads(
        (package / "CustomConfig" / "discover_deck" / "DISCOVER_CARD.json").read_text(
            encoding="utf-8"
        )
    )
    discover_values = discover_config["OnDiscoverCardBonus"]["values"]

    assert discover_values == [
        {
            "comment": "Discover Deck: DISCOVER_CARD_pick_option_alpha",
            "condition": "my_discover(count(),cardid=OPTION_ALPHA) > 0",
            "value": "6",
        }
    ]
```

- [ ] **Step 2: Add a prepare-level Choose One proof test**

Append this test to `tests/test_prepare_cli.py`:

```python
def test_prepare_routes_choose_one_claim_with_identity_links(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [
            {
                "id": "CHOOSE_CARD",
                "dbf_id": 1,
                "name": "Choose Card",
                "type": "SPELL",
                "text": "Choose One - Option Alpha; or Option Beta.",
                "entourage": ["OPTION_ALPHA", "OPTION_BETA"],
            },
            {
                "id": "OPTION_ALPHA",
                "dbf_id": 2,
                "name": "Option Alpha",
                "type": "SPELL",
                "text": "Primary option.",
            },
            {
                "id": "OPTION_BETA",
                "dbf_id": 3,
                "name": "Option Beta",
                "type": "SPELL",
                "text": "Secondary option.",
            },
        ],
    )

    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "CHOOSE_CARD", "dbf_id": 1, "count": 2, "name": "Choose Card"},
                ]
            }
        ),
        encoding="utf-8",
    )
    source_documents = tmp_path / "source_documents.json"
    source_documents.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/choose-guide",
                        "source_title": "Choose Guide",
                        "source_family": "guide",
                        "retrieved_at": _today_utc_iso(),
                        "claims": [
                            {
                                "claim_kind": "choose_one_choice",
                                "cards": ["CHOOSE_CARD"],
                                "choice_card_id": "OPTION_ALPHA",
                                "stance": "choose_option_alpha",
                                "evidence_text_short": "Prefer Option Alpha when resolving Choose One.",
                                "source_confidence": "high",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "Choice Deck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    card_behavior = json.loads((reports / "card_behavior_plan_report.json").read_text(encoding="utf-8"))
    choose_claim = next(
        row for row in card_behavior["rows"] if row["claim_id"] and row["card_id"] == "CHOOSE_CARD"
    )
    choose_config = json.loads(
        (package / "CustomConfig" / "choice_deck" / "CHOOSE_CARD.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 1
    assert payload["status"] == "failed"
    assert choose_claim["behavior_block"] == "OnChooseOneCardBonus"
    assert card_behavior["suppressed"] == []
    assert card_behavior["option_resolution"] == [
        {
            "claim_id": choose_claim["claim_id"],
            "card_id": "CHOOSE_CARD",
            "option_card_id": "OPTION_ALPHA",
            "status": "resolved",
        }
    ]
    assert choose_config["OnChooseOneCardBonus"]["values"] == [
        {
            "comment": "Choice Deck: CHOOSE_CARD_choose_option_alpha",
            "condition": "*",
            "value": "6",
        }
    ]
```

- [ ] **Step 3: Run focused prepare tests**

Run:

```powershell
python -m pytest tests/test_prepare_cli.py::test_prepare_routes_option_claim_with_identity_links tests/test_prepare_cli.py::test_prepare_routes_choose_one_claim_with_identity_links -q
```

Expected: PASS after Task 3.

- [ ] **Step 4: Run related compile tests**

Run:

```powershell
python -m pytest tests/test_compile_cardid.py tests/test_condition_format.py tests/test_prepare_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add tests/test_prepare_cli.py
git commit -m "test: prove choice surfaces in prepare output"
```

Expected: commit succeeds.

---

### Task 5: Documentation And Installed Skill Sync

**Files:**
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `.agents/skills/hsconfig/references/visionai-surfaces.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/README.md`
- Sync: installed skill files under `C:\Users\darbo\.codex\skills\hsconfig` via `scripts/sync_installed_skill.py`

**Interfaces:**
- Consumes: repo-local skill docs.
- Produces: repo-local skill docs committed, installed HSConfig skill synchronized locally.

- [ ] **Step 1: Update card behavior policy wording**

Add this exact policy block to `.agents/skills/hsconfig/references/card-behavior-policy.md` under the card behavior lowering section:

```markdown
## Choice Surface Lowering

`discover_choice` may lower to `OnDiscoverCardBonus` only when the selected option card identity is resolved from source evidence and linked entity metadata. If no condition is supplied, HSConfig derives `my_discover(count(),cardid=<OPTION_CARD_ID>) > 0`.

`choose_one_choice` may lower to `OnChooseOneCardBonus` only when the selected option card identity is resolved from source evidence and linked entity metadata. HSConfig keeps the condition as `*` unless the source document supplies a documented runtime condition.

Unresolved option identity must stay visible in `card_behavior_suppression_report.json` with `reason=unresolved_option_identity`; do not emit guessed choice rows.
```

- [ ] **Step 2: Mirror the operator policy**

In `docs/operator/guide-research-policy.md`, ensure the accepted claim-kind section includes these exact bullets:

```markdown
- `discover_choice`: exact card-specific Discover option preference; requires `option_card_id` or `option_card` plus source-backed option identity.
- `choose_one_choice`: exact card-specific Choose One option preference; requires `choice_card_id` or `choice_card` plus source-backed option identity.
```

- [ ] **Step 3: Run active docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 4: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected: second command prints that the installed HSConfig skill is in sync.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add .agents/skills/hsconfig docs/operator
git commit -m "docs: document choice surface lowering policy"
```

Expected: commit succeeds. The installed skill sync remains a verified local state outside the repo, not a committed artifact.

---

### Task 6: Final Verification And GitHub Update

**Files:**
- No planned source changes.
- Verify the complete diff and push `main`.

**Interfaces:**
- Consumes: all previous task commits.
- Produces: verified `main` branch pushed to `origin/main`.

- [ ] **Step 1: Run targeted suite**

Run:

```powershell
python -m pytest tests/test_strong_promotion_report.py tests/test_cli_help.py tests/test_card_behavior_router.py tests/test_prepare_cli.py tests/test_compile_cardid.py tests/test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS, with any existing skips unchanged.

- [ ] **Step 3: Verify installed skill sync**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: installed HSConfig skill is in sync.

- [ ] **Step 4: Inspect active policy wording**

Run:

```powershell
rg -n "per-card <CARDID>\.json|OnDiscoverCardBonus|OnChooseOneCardBonus|unresolved_option_identity|does not parse replays|winrate" README.md docs\operator .agents\skills\hsconfig
```

Expected:

- `per-card <CARDID>.json` appears in active operator-facing docs.
- `OnDiscoverCardBonus` and `OnChooseOneCardBonus` appear in card behavior policy and guide research policy.
- `unresolved_option_identity` appears in card behavior policy.
- pre-run negative scope still appears.

- [ ] **Step 5: Inspect git status and log**

Run:

```powershell
git status --short --branch
git log --oneline -5
```

Expected: branch is ahead of `origin/main` by the new commits, with no unstaged changes.

- [ ] **Step 6: Push**

Run:

```powershell
git push origin main
```

Expected: push succeeds.

---

## Self-Review

**Spec coverage:** The plan covers the three recommended areas: report consistency, lean operator UX, and documented choice-surface lowering. It keeps HSConfig pre-run-only and does not add replay, winrate, HSTuner, Presume, or Concede scope.

**Placeholder scan:** The plan contains concrete files, test names, code blocks, commands, and expected results. It does not require undefined future design work to produce a passing implementation.

**Type consistency:** `first_missing_chain` changes from `dict[str, str] | None` to `dict[str, Any] | None` because the canonical summary includes integer priority fields. Choice routing keeps existing `option_resolution` row shape so existing exact tests remain stable.

**Risk note:** The plan intentionally treats Choose One condition derivation more conservatively than Discover. Discover gets a documented `my_discover(...)` condition from resolved option identity. Choose One emits `OnChooseOneCardBonus` only after identity resolution and keeps `*` unless source evidence supplies a documented runtime condition.
