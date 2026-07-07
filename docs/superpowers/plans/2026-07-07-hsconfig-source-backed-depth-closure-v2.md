# HSConfig Source-Backed Depth Closure V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig produce clearer, stronger pre-run config depth by turning every deck card into a visible source-backed, static-semantic, inferred, or low-confidence lane before runtime package apply.

**Architecture:** Keep HSConfig as a lean pre-game HearthRanger VisionAI CustomConfig compiler. Do not add HSTuner, replay parsing, winrate analysis, or post-game candidate promotion. Improve the existing source-document path, operator summary, deterministic linked-entity resolution, and compact depth-matrix tests so `VALID_PACKAGE` remains technical validity and `SOURCE_BACKED_STRONG` means actual guide/source depth.

**Tech Stack:** Python 3.11+, `pytest`, `hearthstone>=9.0.0`, existing HearthstoneJSON fetch/metadata helpers, existing HearthRanger VisionAI runtime JSON compilers.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep the normal workflow: researched `source_documents.json` -> `hsconfig research-deck` -> `hsconfig prepare` -> inspect `reports/operator_summary.json` -> `hsconfig apply` only when requested.
- Do not add replay parsing, HDT parsing, winrate validation, runtime log tuning, candidate promotion, or HSTuner state to HSConfig.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Runtime surfaces stay limited to `GlobalValues.json`, `Mulligan.json`, per-card `CARDID.json`, and `Combo.json` when a concrete valid combo exists.
- Preserve the semantic distinction: `VALID_PACKAGE` is load-safe structure; `SOURCE_BACKED_STRONG` is source-backed config depth.
- Do not weaken `SOURCE_BACKED_STRONG` thresholds to make reports greener.
- Keep source documents as the only human-authored guide/research input. Do not create a second source-document system.
- Curated linked-entity data is source-last: deckstrings, HearthstoneJSON, and upstream metadata win over curated fallback rows.
- Sideboards remain owned by the existing deckstring decode path, not by curated linked-entity supplements.
- All generated test outputs must live under `tmp_path`; do not write to a live HearthRanger runtime in tests.
- Use TDD: failing test first, minimal implementation, focused verification, then commit.

---

## File Structure

- Modify `src/hsconfig/operator_summary.py`: add machine-readable guide-strength summary and semantic blockers.
- Modify `src/hsconfig/cli.py`: pass full readiness reports into `build_operator_summary()` and mirror new summary fields in `prepare --json`.
- Modify `src/hsconfig/source_document_builder.py`: add explicit claim readiness/specificity fields to normalized claims.
- Modify `src/hsconfig/source_document_model.py`: centralize allowed claim-readiness/status constants.
- Create `src/hsconfig/linked_entity_supplement.py`: tiny deterministic source-last supplement and merge helper.
- Modify `src/hsconfig/option_identity_resolver.py`: accept optional curated supplement links and merge them after upstream links.
- Modify `src/hsconfig/semantic_enrichment.py`: use curated supplement for Shadowform/Mind Spike before built-in fallback.
- Create `tests/test_depth_matrix_e2e.py`: compact three-lane depth proof.
- Modify `tests/test_operator_summary.py`: prove semantic blockers and guide-strength summary.
- Modify `tests/test_prepare_cli.py`: prove `prepare --json` mirrors operator summary explanations.
- Modify `tests/test_source_document_builder.py`: prove claim readiness/specificity fields.
- Modify `tests/test_option_identity_resolver.py`: prove source-first/supplement-last linked-entity behavior.
- Modify `README.md`: short status matrix and normal operator path.
- Modify `.agents/skills/hsconfig/SKILL.md`: concise skill workflow and status language.
- Modify `.agents/skills/hsconfig/references/workflow.md`: add interpretation of `semantic_blockers` and `guide_strength_summary`.
- Modify `docs/operator/guide-research-policy.md`: align accepted claim/status language with implementation.

---

### Task 1: Operator Guide-Strength Summary And Semantic Blockers

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_prepare_cli.py`

**Interfaces:**
- Consumes: existing `claim_coverage_report`, `config_readiness_report`, `config_readiness_summary`, `claim_conflict_report`, `guide_source_depth_report`, and `global_values_authority_matrix`.
- Produces: `operator_summary["guide_strength_summary"]`, `operator_summary["semantic_blockers"]`, `prepare --json` fields with the same names.
- Keep `build_operator_summary()` backward compatible by adding optional parameter `config_readiness_report: dict[str, Any] | None = None`.

- [ ] **Step 1: Add failing operator summary tests**

Append these tests to `tests/test_operator_summary.py`:

```python
def test_operator_summary_explains_valid_but_not_guide_strong_with_semantic_blockers():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 8},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        claim_coverage_report={
            "summary": {
                "guide_backed": 2,
                "static_semantics_backfilled": 1,
                "uncovered_low_confidence": 2,
            },
            "uncovered_cards": ["CARD_A", "CARD_B"],
        },
        config_readiness_summary={
            "total_cards": 5,
            "runtime_emitted": 1,
            "mulligan_only": 1,
            "globalvalues_only": 0,
            "report_only_supported": 1,
            "archetype_inferred": 0,
            "generic_low_confidence": 2,
            "cards_needing_guide_claims": 2,
            "cards_needing_runtime_surface": 1,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={
            "cards": {
                "CARD_A": {
                    "name": "Card A",
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                },
                "CARD_B": {
                    "name": "Card B",
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                },
                "CARD_C": {
                    "name": "Card C",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                },
            }
        },
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["guide_strength_summary"] == {
        "total_cards": 5,
        "guide_backed_cards": 2,
        "static_semantics_cards": 1,
        "generic_low_confidence_cards": 2,
        "uncovered_cards": 2,
        "claim_conflicts": 0,
        "runtime_emitted_cards": 1,
        "cards_needing_guide_claims": 2,
        "cards_needing_runtime_surface": 1,
        "cards_needing_mulligan_claims": 0,
        "cards_needing_combo_sequence": 0,
        "cards_needing_condition_lowering": 0,
        "cards_needing_mechanic_lowering": 0,
        "source_backed_strong_requires": [
            "technical_status=VALID_PACKAGE",
            "source_depth_status=source_backed",
            "claim_count>0",
            "generic_low_confidence_cards=0",
            "uncovered_cards=0",
            "claim_conflicts=0",
        ],
    }
    assert summary["semantic_blockers"][0] == {
        "reason": "cards_need_guide_claims",
        "count": 2,
        "blocking_strength": "blocks_source_backed_strong",
        "report": "reports/per_card_config_readiness_report.json",
        "affected_cards": [
            {"card_id": "CARD_A", "name": "Card A"},
            {"card_id": "CARD_B", "name": "Card B"},
        ],
    }
    assert {
        "reason": "cards_need_runtime_surface",
        "count": 1,
        "blocking_strength": "report_visible_gap",
        "report": "reports/per_card_config_readiness_report.json",
        "affected_cards": [{"card_id": "CARD_C", "name": "Card C"}],
    } in summary["semantic_blockers"]
```

Also append:

```python
def test_operator_summary_explains_claim_conflict_blocker():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 8},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
        claim_conflict_report={"conflict_count": 1, "conflicts": [{"card_id": "CARD_A"}]},
        claim_coverage_report={
            "summary": {
                "guide_backed": 3,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={"total_cards": 3, "generic_low_confidence": 0},
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert {
        "reason": "claim_conflicts_present",
        "count": 1,
        "blocking_strength": "blocks_source_backed_strong",
        "report": "reports/claim_conflict_report.json",
        "affected_cards": [{"card_id": "CARD_A", "name": "CARD_A"}],
    } in summary["semantic_blockers"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_operator_summary.py -q
```

Expected: FAIL because `guide_strength_summary` and `semantic_blockers` do not exist.

- [ ] **Step 3: Implement summary and blocker helpers**

In `src/hsconfig/operator_summary.py`, update the signature:

```python
def build_operator_summary(
    *,
    deck_name: str,
    deck_code: str,
    technical_validation: dict[str, Any],
    guide_source_depth: dict[str, Any] | None,
    unsupported_conditions: list[dict[str, Any]] | None,
    globalvalue_authority: dict[str, Any] | None,
    generated_files: list[str],
    claim_coverage_report: dict[str, Any] | None = None,
    config_readiness_summary: dict[str, Any] | None = None,
    config_readiness_report: dict[str, Any] | None = None,
    claim_conflict_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

Build these values before the return:

```python
    guide_strength_summary = _guide_strength_summary(
        guide_source_depth=guide_source_depth or {},
        claim_coverage_report=claim_coverage_report or {},
        config_readiness_summary=config_readiness_summary or {},
        claim_conflict_report=claim_conflict_report or {},
    )
    semantic_blockers = _semantic_blockers(
        claim_coverage_report=claim_coverage_report or {},
        config_readiness_summary=config_readiness_summary or {},
        config_readiness_report=config_readiness_report or {},
        claim_conflict_report=claim_conflict_report or {},
        globalvalue_authority=globalvalue_authority or {},
        unsupported_conditions=unsupported_conditions or [],
    )
```

Add them to the returned dictionary:

```python
        "guide_strength_summary": guide_strength_summary,
        "semantic_blockers": semantic_blockers,
```

Add helpers:

```python
SOURCE_BACKED_STRONG_REQUIREMENTS = [
    "technical_status=VALID_PACKAGE",
    "source_depth_status=source_backed",
    "claim_count>0",
    "generic_low_confidence_cards=0",
    "uncovered_cards=0",
    "claim_conflicts=0",
]


def _guide_strength_summary(
    *,
    guide_source_depth: dict[str, Any],
    claim_coverage_report: dict[str, Any],
    config_readiness_summary: dict[str, Any],
    claim_conflict_report: dict[str, Any],
) -> dict[str, Any]:
    coverage_summary = claim_coverage_report.get("summary", {})
    if not isinstance(coverage_summary, dict):
        coverage_summary = {}
    uncovered_cards = _uncovered_cards(claim_coverage_report)
    return {
        "total_cards": _int_value(
            config_readiness_summary.get(
                "total_cards",
                claim_coverage_report.get("total_cards", 0),
            )
        ),
        "guide_backed_cards": _int_value(
            coverage_summary.get(
                "guide_backed",
                claim_coverage_report.get("guide_backed_cards", 0),
            )
        ),
        "static_semantics_cards": _int_value(
            coverage_summary.get("static_semantics_backfilled", 0)
        ),
        "generic_low_confidence_cards": _generic_low_confidence_count(
            config_readiness_summary=config_readiness_summary,
            claim_coverage_report=claim_coverage_report,
        ),
        "uncovered_cards": len(uncovered_cards),
        "claim_conflicts": _int_value(claim_conflict_report.get("conflict_count", 0)),
        "runtime_emitted_cards": _int_value(config_readiness_summary.get("runtime_emitted", 0)),
        "cards_needing_guide_claims": _int_value(
            config_readiness_summary.get("cards_needing_guide_claims", 0)
        ),
        "cards_needing_runtime_surface": _int_value(
            config_readiness_summary.get("cards_needing_runtime_surface", 0)
        ),
        "cards_needing_mulligan_claims": _int_value(
            config_readiness_summary.get("cards_needing_mulligan_claims", 0)
        ),
        "cards_needing_combo_sequence": _int_value(
            config_readiness_summary.get("cards_needing_combo_sequence", 0)
        ),
        "cards_needing_condition_lowering": _int_value(
            config_readiness_summary.get("cards_needing_condition_lowering", 0)
        ),
        "cards_needing_mechanic_lowering": _int_value(
            config_readiness_summary.get("cards_needing_mechanic_lowering", 0)
        ),
        "source_backed_strong_requires": SOURCE_BACKED_STRONG_REQUIREMENTS,
    }
```

Add blocker helpers:

```python
def _semantic_blockers(
    *,
    claim_coverage_report: dict[str, Any],
    config_readiness_summary: dict[str, Any],
    config_readiness_report: dict[str, Any],
    claim_conflict_report: dict[str, Any],
    globalvalue_authority: dict[str, Any],
    unsupported_conditions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    missing_link_reasons = {
        "needs_guide_claim": ("cards_need_guide_claims", "blocks_source_backed_strong"),
        "needs_runtime_surface": ("cards_need_runtime_surface", "report_visible_gap"),
        "needs_mulligan_claim": ("cards_need_mulligan_claims", "report_visible_gap"),
        "needs_combo_sequence": ("cards_need_combo_sequence", "report_visible_gap"),
        "needs_condition_lowering": ("cards_need_condition_lowering", "report_visible_gap"),
        "needs_mechanic_lowering": ("cards_need_mechanic_lowering", "report_visible_gap"),
    }
    for missing_link, (reason, strength) in missing_link_reasons.items():
        affected = _affected_cards_by_missing_link(config_readiness_report, missing_link)
        count = len(affected) or _int_value(config_readiness_summary.get(reason, 0))
        if count:
            blockers.append(
                {
                    "reason": reason,
                    "count": count,
                    "blocking_strength": strength,
                    "report": "reports/per_card_config_readiness_report.json",
                    "affected_cards": affected[:5],
                }
            )
    conflicts = claim_conflict_report.get("conflicts", [])
    conflict_count = _int_value(claim_conflict_report.get("conflict_count", 0))
    if conflict_count:
        blockers.append(
            {
                "reason": "claim_conflicts_present",
                "count": conflict_count,
                "blocking_strength": "blocks_source_backed_strong",
                "report": "reports/claim_conflict_report.json",
                "affected_cards": _affected_cards_from_conflicts(conflicts)[:5],
            }
        )
    if unsupported_conditions:
        blockers.append(
            {
                "reason": "unsupported_conditions_present",
                "count": len(unsupported_conditions),
                "blocking_strength": "report_visible_gap",
                "report": "reports/mulligan_plan_report.json",
                "affected_cards": _affected_cards_from_conditions(unsupported_conditions)[:5],
            }
        )
    blocked_globalvalues = [
        row for row in globalvalue_authority.get("blocked_until_runtime_evidence", [])
        if isinstance(row, dict)
    ]
    if blocked_globalvalues:
        blockers.append(
            {
                "reason": "globalvalues_runtime_evidence_required",
                "count": len(blocked_globalvalues),
                "blocking_strength": "runtime_evidence_required",
                "report": "reports/global_values_authority_matrix.json",
                "affected_cards": [],
            }
        )
    return blockers
```

Add support helpers:

```python
def _affected_cards_by_missing_link(
    config_readiness_report: dict[str, Any],
    missing_link: str,
) -> list[dict[str, str]]:
    cards = config_readiness_report.get("cards", {})
    if not isinstance(cards, dict):
        return []
    rows = []
    for card_id, row in sorted(cards.items()):
        if not isinstance(row, dict) or row.get("first_missing_link") != missing_link:
            continue
        rows.append({"card_id": str(card_id), "name": str(row.get("name", card_id))})
    return rows


def _affected_cards_from_conflicts(conflicts: Any) -> list[dict[str, str]]:
    if not isinstance(conflicts, list):
        return []
    rows = []
    for conflict in conflicts:
        if isinstance(conflict, dict) and conflict.get("card_id"):
            rows.append({"card_id": str(conflict["card_id"]), "name": str(conflict["card_id"])})
    return rows


def _affected_cards_from_conditions(conditions: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for condition in conditions:
        card_id = condition.get("card_id") or condition.get("card")
        if card_id:
            rows.append({"card_id": str(card_id), "name": str(card_id)})
    return rows
```

- [ ] **Step 4: Pass full readiness report and mirror fields in CLI**

In `src/hsconfig/cli.py`, update the `build_operator_summary()` call:

```python
        config_readiness_summary=config_readiness_report["summary"],
        config_readiness_report=config_readiness_report,
```

In the returned payload, add:

```python
            "guide_strength_summary": operator_summary["guide_strength_summary"],
            "semantic_blockers": operator_summary["semantic_blockers"],
```

- [ ] **Step 5: Add CLI mirror test**

Append to `tests/test_prepare_cli.py`:

```python
def test_prepare_json_mirrors_operator_summary_guide_strength_fields(tmp_path: Path, capsys):
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator_summary = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["guide_strength_summary"] == operator_summary["guide_strength_summary"]
    assert payload["semantic_blockers"] == operator_summary["semantic_blockers"]
    assert operator_summary["guide_strength_summary"]["source_backed_strong_requires"]
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_operator_summary.py tests/test_prepare_cli.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/cli.py tests/test_operator_summary.py tests/test_prepare_cli.py
git commit -m "feat: explain HSConfig guide strength blockers"
```

---

### Task 2: Source Claim Specificity And Readiness Lanes

**Files:**
- Modify: `src/hsconfig/source_document_model.py`
- Modify: `src/hsconfig/source_document_builder.py`
- Modify: `docs/operator/guide-research-policy.md`
- Test: `tests/test_source_document_builder.py`

**Interfaces:**
- Consumes: source documents accepted by `--source-documents-json`.
- Produces normalized claims with `claim_readiness`, `specificity_status`, and `trust_ceiling`.
- These fields are report/provenance fields only; they do not authorize runtime writes by themselves.

- [ ] **Step 1: Add failing source claim specificity tests**

Create `tests/test_source_document_builder.py` if it does not exist. If it exists, append:

```python
from hsconfig.source_document_builder import build_source_document_bundle


DECK_IDENTITY = {
    "deck_name": "Fixture",
    "cards": [
        {"card_id": "CARD_A", "name": "Card A", "count": 2},
        {"card_id": "CARD_B", "name": "Card B", "count": 2},
    ],
}

CARD_METADATA = {
    "cards": [
        {"card_id": "CARD_A", "name": "Card A", "count": 2},
        {"card_id": "CARD_B", "name": "Card B", "count": 2},
    ]
}


def test_source_claims_get_readiness_and_specificity_fields():
    bundle = build_source_document_bundle(
        deck_identity=DECK_IDENTITY,
        card_metadata=CARD_METADATA,
        source_documents=[
            {
                "source_url": "https://example.invalid/fixture-guide",
                "source_title": "Fixture Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_A"],
                        "stance": "prefer_enemy_hero",
                        "evidence_text_short": "Use Card A as face damage.",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
    )

    claim = bundle["claims"][0]
    assert claim["claim_readiness"] == "guide_backed"
    assert claim["specificity_status"] == "card_specific"
    assert claim["trust_ceiling"] == "guide"


def test_low_confidence_source_claim_is_visible_but_not_strong():
    bundle = build_source_document_bundle(
        deck_identity=DECK_IDENTITY,
        card_metadata=CARD_METADATA,
        source_documents=[
            {
                "source_url": "https://example.invalid/weak-guide",
                "source_title": "Weak Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "card_role",
                        "cards": ["CARD_B"],
                        "stance": "maybe_synergy",
                        "evidence_text_short": "Card B is sometimes used with the deck plan.",
                        "source_confidence": "low",
                    }
                ],
            }
        ],
    )

    claim = bundle["claims"][0]
    assert claim["claim_readiness"] == "explicit_low_confidence"
    assert claim["specificity_status"] == "card_specific"
    assert claim["trust_ceiling"] == "report_only"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_source_document_builder.py -q
```

Expected: FAIL because the new fields are absent.

- [ ] **Step 3: Add constants**

In `src/hsconfig/source_document_model.py`, add:

```python
SUPPORTED_CLAIM_READINESS = frozenset(
    {
        "guide_backed",
        "source_backed_static_semantics",
        "archetype_inferred",
        "explicit_low_confidence",
        "generic_low_confidence",
        "contract_gap",
    }
)

SUPPORTED_SPECIFICITY_STATUSES = frozenset(
    {
        "deck_scoped",
        "card_specific",
        "multi_card_specific",
        "not_card_specific",
    }
)
```

- [ ] **Step 4: Implement claim readiness helpers**

In `src/hsconfig/source_document_builder.py`, add helper functions near `_legacy_claim_type()`:

```python
def _claim_readiness(
    *,
    claim_confidence: str,
    source_family: str,
    cards: list[str],
    scope: str,
) -> str:
    confidence = claim_confidence.lower()
    family = source_family.lower()
    if confidence == "low":
        return "explicit_low_confidence"
    if family in {"card_text", "metadata", "hearthstonejson", "static_semantics"}:
        return "source_backed_static_semantics"
    if cards:
        return "guide_backed"
    if scope in {"deck", "archetype"}:
        return "archetype_inferred"
    return "contract_gap"


def _specificity_status(*, cards: list[str], scope: str) -> str:
    if len(cards) > 1:
        return "multi_card_specific"
    if len(cards) == 1:
        return "card_specific"
    if scope in {"deck", "archetype"}:
        return "deck_scoped"
    return "not_card_specific"


def _trust_ceiling(*, claim_readiness: str, source_family: str) -> str:
    if claim_readiness == "explicit_low_confidence":
        return "report_only"
    if claim_readiness == "source_backed_static_semantics":
        return "static_semantics"
    if source_family.lower() in {"guide", "mulligan_guide", "matchup_guide"}:
        return "guide"
    return "source"
```

In `_normalize_source_claim()`, after `claim_confidence` is finalized, calculate:

```python
    readiness = _claim_readiness(
        claim_confidence=claim_confidence,
        source_family=str(document.get("source_family", "guide")),
        cards=cards,
        scope=scope,
    )
```

Add these keys to `claim`:

```python
        "claim_readiness": readiness,
        "specificity_status": _specificity_status(cards=cards, scope=scope),
        "trust_ceiling": _trust_ceiling(
            claim_readiness=readiness,
            source_family=str(document.get("source_family", "guide")),
        ),
```

- [ ] **Step 5: Update guide policy docs**

In `docs/operator/guide-research-policy.md`, add this under "Per-Card Depth Rule":

```markdown
Claim readiness lanes:

- `guide_backed`: current source claim maps to one or more concrete deck cards.
- `source_backed_static_semantics`: card text or metadata supports a deterministic static expectation.
- `archetype_inferred`: deck-scoped posture without card-specific source support.
- `explicit_low_confidence`: source is current but weak or low confidence.
- `generic_low_confidence`: no useful source or static semantic support exists.
- `contract_gap`: the claim could not be made specific enough for the config contract.

Only `guide_backed` and `source_backed_static_semantics` can contribute toward strong guide-depth readiness.
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_source_document_builder.py tests/test_guide_source_builder.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
git add src/hsconfig/source_document_model.py src/hsconfig/source_document_builder.py tests/test_source_document_builder.py docs/operator/guide-research-policy.md
git commit -m "feat: classify source claim readiness"
```

---

### Task 3: Curated Linked-Entity Supplement

**Files:**
- Create: `src/hsconfig/linked_entity_supplement.py`
- Modify: `src/hsconfig/option_identity_resolver.py`
- Modify: `src/hsconfig/semantic_enrichment.py`
- Test: `tests/test_option_identity_resolver.py`
- Test: `tests/test_semantic_enrichment.py`

**Interfaces:**
- Consumes upstream linked entities from HearthstoneJSON and deterministic curated rows.
- Produces linked entity rows with `source` equal to `curated_linked_entity_supplement` only when upstream has no equivalent link.
- Does not handle sideboards, random pools, full token graphs, or runtime-generated option pools.

- [ ] **Step 1: Add failing option resolver supplement tests**

Append to `tests/test_option_identity_resolver.py`:

```python
def test_curated_supplement_adds_missing_link_source_last():
    cards = [{"id": "CARD_PARENT", "name": "Parent"}]
    index = {
        "CARD_CHILD": {
            "id": "CARD_CHILD",
            "dbf_id": 101,
            "name": "Child",
            "type": "SPELL",
        }
    }
    supplement = {
        "CARD_PARENT": [
            {
                "link_kind": "option_identity",
                "card_id": "CARD_CHILD",
                "dbf_id": 101,
                "name": "Child",
                "type": "SPELL",
                "source": "curated_linked_entity_supplement",
            }
        ]
    }

    links = resolve_linked_entities(cards, index, supplement_links=supplement)

    assert links["CARD_PARENT"] == [
        {
            "link_kind": "option_identity",
            "card_id": "CARD_CHILD",
            "dbf_id": 101,
            "name": "Child",
            "type": "SPELL",
            "source": "curated_linked_entity_supplement",
        }
    ]


def test_upstream_link_wins_over_curated_duplicate():
    cards = [{"id": "CARD_PARENT", "entourage": ["CARD_CHILD"]}]
    index = {
        "CARD_CHILD": {
            "id": "CARD_CHILD",
            "dbf_id": 101,
            "name": "Child",
            "type": "SPELL",
        }
    }
    supplement = {
        "CARD_PARENT": [
            {
                "link_kind": "entourage",
                "card_id": "CARD_CHILD",
                "dbf_id": 101,
                "name": "Child",
                "type": "SPELL",
                "source": "curated_linked_entity_supplement",
            }
        ]
    }

    links = resolve_linked_entities(cards, index, supplement_links=supplement)

    assert links["CARD_PARENT"] == [
        {
            "link_kind": "entourage",
            "card_id": "CARD_CHILD",
            "dbf_id": 101,
            "name": "Child",
            "type": "SPELL",
            "source": "hearthstonejson.entourage",
        }
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_option_identity_resolver.py -q
```

Expected: FAIL because `supplement_links` is not accepted.

- [ ] **Step 3: Create supplement module**

Create `src/hsconfig/linked_entity_supplement.py`:

```python
from __future__ import annotations

from typing import Any


CURATED_LINKED_ENTITIES: dict[str, list[dict[str, Any]]] = {
    "SW_448": [
        {
            "link_kind": "hero_power_transform",
            "card_id": "EX1_625t",
            "dbf_id": 1622,
            "name": "Mind Spike",
            "type": "HERO_POWER",
            "source": "curated_linked_entity_supplement",
            "reason": "Darkbishop Benedictus enters Shadowform at start of game, replacing the starting Hero Power with Mind Spike.",
        }
    ],
    "EX1_625": [
        {
            "link_kind": "hero_power_transform",
            "card_id": "EX1_625t",
            "dbf_id": 1622,
            "name": "Mind Spike",
            "type": "HERO_POWER",
            "source": "curated_linked_entity_supplement",
            "reason": "Shadowform changes the Priest Hero Power to Mind Spike.",
        }
    ],
}


def curated_links_for(card_id: str) -> list[dict[str, Any]]:
    return [dict(row) for row in CURATED_LINKED_ENTITIES.get(str(card_id), [])]


def curated_link_map_for(card_ids: list[str] | set[str] | tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    return {
        str(card_id): curated_links_for(str(card_id))
        for card_id in card_ids
        if curated_links_for(str(card_id))
    }
```

- [ ] **Step 4: Add supplement support to resolver**

Update `src/hsconfig/option_identity_resolver.py` signature:

```python
def resolve_linked_entities(
    cards: list[dict[str, Any]],
    card_index: dict[str, dict[str, Any]],
    *,
    supplement_links: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
```

After upstream row construction, merge supplement rows:

```python
        for supplement in (supplement_links or {}).get(card_id, []):
            if not isinstance(supplement, dict):
                continue
            if _has_equivalent_link(rows, supplement):
                continue
            rows.append(dict(supplement))
```

Add helper:

```python
def _has_equivalent_link(rows: list[dict[str, Any]], candidate: dict[str, Any]) -> bool:
    candidate_kind = str(candidate.get("link_kind", ""))
    candidate_card = str(candidate.get("card_id", ""))
    return any(
        str(row.get("link_kind", "")) == candidate_kind
        and str(row.get("card_id", "")) == candidate_card
        for row in rows
    )
```

- [ ] **Step 5: Use supplement in semantic enrichment**

In `src/hsconfig/semantic_enrichment.py`, import:

```python
from hsconfig.linked_entity_supplement import curated_link_map_for
```

Before the loop, build:

```python
    card_ids = [
        str(card.get("card_id") or card.get("id") or "")
        for card in card_metadata.get("cards", [])
        if str(card.get("card_id") or card.get("id") or "")
    ]
    curated_supplement = curated_link_map_for(card_ids)
```

Update the resolver call:

```python
        resolved_links = resolve_linked_entities(
            [enriched],
            hjson_index,
            supplement_links=curated_supplement,
        ).get(card_id, [])
```

Update `_starting_hero_power_link()` to accept `hero_power_transform` as a valid Shadowform target:

```python
        if row.get("link_kind") in {"starting_hero_power", "hero_power_transform"}:
            return row
```

- [ ] **Step 6: Add semantic enrichment test**

Append to `tests/test_semantic_enrichment.py`:

```python
def test_shadowpriest_hero_power_transform_uses_curated_supplement_before_builtin_warning():
    report = enrich_card_metadata(
        {
            "cards": [
                {
                    "card_id": "SW_448",
                    "dbf_id": 101,
                    "name": "Darkbishop Benedictus",
                    "type": "MINION",
                    "text": "At the start of the game, if the spells in your deck are all Shadow, enter Shadowform.",
                    "referenced_tags": ["START_OF_GAME_KEYWORD"],
                }
            ]
        },
        hearthstonejson_cards=[],
    )

    effect = report["deckwide_effects"][0]
    assert effect["source_card_id"] == "SW_448"
    assert effect["target_card_id"] == "EX1_625t"
    assert report["semantic_enrichment_warnings"] == []
    assert report["cards"][0]["linked_entities"][0]["source"] == "curated_linked_entity_supplement"
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python -m pytest tests/test_option_identity_resolver.py tests/test_semantic_enrichment.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

```powershell
git add src/hsconfig/linked_entity_supplement.py src/hsconfig/option_identity_resolver.py src/hsconfig/semantic_enrichment.py tests/test_option_identity_resolver.py tests/test_semantic_enrichment.py
git commit -m "feat: add curated linked entity supplement"
```

---

### Task 4: Compact Depth-Matrix E2E

**Files:**
- Create: `tests/test_depth_matrix_e2e.py`
- Reuse: `tests/fixtures/source_documents_shadowpriest_depth.json`
- Reuse: `tests/fixtures/source_documents_multiarchetype.json`

**Interfaces:**
- Consumes public CLI `hsconfig.cli.main`.
- Produces three proof lanes: ShadowPriest full-depth, MechPala contrast, synthetic linked-entity combo fixture.
- Does not write outside `tmp_path`.

- [ ] **Step 1: Create failing depth-matrix tests**

Create `tests/test_depth_matrix_e2e.py`:

```python
import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.io import read_json, write_json


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
MECHPALA_CODE = (
    "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/"
    "AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="
)


def test_depth_matrix_shadowpriest_primary_surface_contract(tmp_path: Path):
    out = tmp_path / "shadowpriest"
    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_depth.json",
            "--json",
        ]
    )

    reports = out / "reports"
    deck_dir = out / "CustomConfig" / "shadowpriest"
    operator = read_json(reports / "operator_summary.json")
    gameplan = read_json(reports / "gameplan_contract.json")
    globalvalues_profile = read_json(reports / "globalvalues_profile.json")

    assert code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert (deck_dir / "GlobalValues.json").exists()
    assert (deck_dir / "Mulligan.json").exists()
    assert any(path.name.endswith(".json") for path in deck_dir.glob("SW_*.json"))
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
    assert gameplan["cards"]["SW_448"]["linked_entities"]
    assert any(
        effect["target_card_id"] == "EX1_625t"
        for effect in gameplan["deckwide_effects"]
    )
    assert globalvalues_profile["keys"]["MyHeroPowerValue"]["status"] == "overlay_changed"


def test_depth_matrix_mechpala_real_contrast_posture(tmp_path: Path):
    fixture = json.loads(
        Path("tests/fixtures/source_documents_multiarchetype.json").read_text(
            encoding="utf-8"
        )
    )
    source_path = tmp_path / "mechpala_sources.json"
    write_json(source_path, fixture["MechPala"])
    out = tmp_path / "mechpala"

    code = main(
        [
            "prepare",
            "--deck-name",
            "MechPala",
            "--deck-code",
            MECHPALA_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            str(source_path),
            "--json",
        ]
    )

    operator = read_json(out / "reports" / "operator_summary.json")
    authority = read_json(out / "reports" / "global_values_authority_matrix.json")
    allowed = {row["key"] for row in authority["allowed_step1_overlays"]}

    assert code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert authority["posture"] == "token_board"
    assert allowed & {"GlobalMinionAttack", "GlobalMinionHealth", "GlobalMinionIntrinsicValue"}


def test_depth_matrix_linked_entity_combo_micro_fixture(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "hsconfig.cli.fetch_latest_cards",
        lambda timeout=10.0: [
            {
                "id": "DISCOVER_CARD",
                "dbf_id": 1,
                "name": "Discover Card",
                "type": "MINION",
                "text": "Discover a spell.",
                "entourage": ["OPTION_ALPHA"],
            },
            {
                "id": "OPTION_ALPHA",
                "dbf_id": 2,
                "name": "Option Alpha",
                "type": "SPELL",
                "text": "Deal damage.",
            },
            {
                "id": "COMBO_A",
                "dbf_id": 3,
                "name": "Combo A",
                "type": "SPELL",
                "text": "First combo card.",
            },
            {
                "id": "COMBO_B",
                "dbf_id": 4,
                "name": "Combo B",
                "type": "SPELL",
                "text": "Second combo card.",
            },
        ],
    )
    cards_json = tmp_path / "cards.json"
    write_json(
        cards_json,
        {
            "cards": [
                {"card_id": "DISCOVER_CARD", "dbf_id": 1, "count": 2, "name": "Discover Card"},
                {"card_id": "COMBO_A", "dbf_id": 3, "count": 2, "name": "Combo A"},
                {"card_id": "COMBO_B", "dbf_id": 4, "count": 2, "name": "Combo B"},
            ]
        },
    )
    source_documents = tmp_path / "source_documents.json"
    write_json(
        source_documents,
        {
            "source_documents": [
                {
                    "source_url": "https://example.invalid/depth-matrix",
                    "source_title": "Depth Matrix Fixture",
                    "source_family": "guide",
                    "retrieved_at": "2026-07-07T00:00:00Z",
                    "claims": [
                        {
                            "claim_kind": "discover_choice",
                            "cards": ["DISCOVER_CARD"],
                            "option_card_id": "OPTION_ALPHA",
                            "stance": "pick_option_alpha",
                            "evidence_text_short": "Prefer Option Alpha from this discover pool.",
                            "source_confidence": "high",
                        },
                        {
                            "claim_kind": "combo_sequence",
                            "cards": ["COMBO_A", "COMBO_B"],
                            "sequence": ["COMBO_A", "COMBO_B"],
                            "timing_kind": "same_turn",
                            "operator": ">>",
                            "values": ["8", "14"],
                            "evidence_text_short": "Play Combo A into Combo B on the same turn.",
                            "source_confidence": "high",
                        },
                    ],
                }
            ]
        },
    )
    out = tmp_path / "linked_combo"

    code = main(
        [
            "prepare",
            "--deck-name",
            "Linked Combo",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    deck_dir = out / "CustomConfig" / "linked_combo"
    reports = out / "reports"
    combo = read_json(deck_dir / "Combo.json")
    card_behavior = read_json(reports / "card_behavior_plan_report.json")
    suppression = read_json(reports / "card_behavior_suppression_report.json")
    discover = read_json(deck_dir / "DISCOVER_CARD.json")

    assert code == 0
    assert combo["ComboList"]["values"][0]["combo"] == "COMBO_A>>COMBO_B"
    assert combo["ComboList"]["values"][0]["value"] == "8>>14"
    assert card_behavior["option_resolution"][0]["status"] == "resolved"
    assert suppression == []
    assert "OnDiscoverCardBonus" in discover
    assert "source_claim_ids" not in json.dumps(discover)
```

- [ ] **Step 2: Run test to verify failing or expose existing bug**

Run:

```powershell
python -m pytest tests/test_depth_matrix_e2e.py -q
```

Expected: FAIL if any assertion exposes a missing current behavior. If it passes immediately, keep the test because it locks the compact proof matrix.

- [ ] **Step 3: Apply minimal fixes only if needed**

If the micro-fixture fails because resolved option rows produce a non-passing package, adjust only the specific package validation or card behavior output needed so a resolved option with documented runtime block is valid. Do not broaden validation for unresolved option identities.

If the ShadowPriest assertion fails because the link source is still built-in fallback, Task 3 must be completed before rerunning this task.

- [ ] **Step 4: Run focused depth matrix and adjacent tests**

Run:

```powershell
python -m pytest tests/test_depth_matrix_e2e.py tests/test_shadowpriest_depth_e2e.py tests/test_multideck_source_backed_e2e.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```powershell
git add tests/test_depth_matrix_e2e.py
git commit -m "test: add HSConfig depth matrix e2e proof"
```

If Task 4 required implementation fixes, include those exact changed files in the same commit.

---

### Task 5: Operator Docs And Skill Polish

**Files:**
- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `docs/operator/guide-research-policy.md`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- Consumes implementation terms from Tasks 1-4.
- Produces a single clear user path and status vocabulary.

- [ ] **Step 1: Add failing skill/docs test**

Append to `tests/test_skill_files.py`:

```python
from pathlib import Path


def test_skill_docs_explain_valid_package_vs_source_backed_strong():
    docs = "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/references/workflow.md").read_text(encoding="utf-8"),
        ]
    )

    assert "VALID_PACKAGE" in docs
    assert "SOURCE_BACKED_STRONG" in docs
    assert "guide_strength_summary" in docs
    assert "semantic_blockers" in docs
    assert "HSConfig does not parse replays" in docs
    assert "Presume.json" in docs
    assert "Concede.json" in docs
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_skill_files.py -q
```

Expected: FAIL until docs mention the new fields.

- [ ] **Step 3: Update README status matrix**

In `README.md`, keep the top short and add:

```markdown
## Status Model

| Status | Meaning | Normal action |
| --- | --- | --- |
| `VALID_PACKAGE` | Runtime JSON is structurally valid and load-safe. | Safe handoff or apply with warnings when requested. |
| `SOURCE_BACKED_STRONG` | Current source-backed card coverage supports a strong initial config. | Preferred apply/handoff state. |
| `STATIC_SEMANTICS_USABLE` | Static card semantics produced a valid package without enough live guide depth. | Use only as a safe baseline, then improve sources. |
| `VALID_BUT_NOT_GUIDE_STRONG` | Package is valid, but some cards still need guide claims, runtime surfaces, combo/mulligan detail, or conflict resolution. | Read `reports/operator_summary.json` fields `guide_strength_summary` and `semantic_blockers`. |

HSConfig does not parse replays, evaluate winrate, inspect post-game evidence, or tune from runtime logs. `Presume.json` and `Concede.json` are not emitted in the normal path.
```

- [ ] **Step 4: Update skill workflow**

In `.agents/skills/hsconfig/SKILL.md`, add under workflow verification:

```markdown
Use `reports/operator_summary.json` as the first readiness file. The fields
`guide_strength_summary` and `semantic_blockers` explain why a package is
`VALID_BUT_NOT_GUIDE_STRONG` and which source claims should be improved before
calling the config source-backed strong.
```

- [ ] **Step 5: Update workflow reference**

In `.agents/skills/hsconfig/references/workflow.md`, add:

```markdown
Readiness interpretation:

1. `technical_status=VALID_PACKAGE` means HearthRanger JSON structure is valid.
2. `semantic_status=SOURCE_BACKED_STRONG` means the card-level source coverage is strong enough for a high-confidence initial config.
3. If `semantic_status=VALID_BUT_NOT_GUIDE_STRONG`, open `semantic_blockers` first. Each blocker has `reason`, `count`, `blocking_strength`, `report`, and top affected cards.
4. Improve `source_documents.json` for `cards_need_guide_claims`; improve claim lowering or keep report-only for `cards_need_runtime_surface`; add exact sequence data for `cards_need_combo_sequence`.
```

- [ ] **Step 6: Run docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```powershell
git add README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md docs/operator/guide-research-policy.md tests/test_skill_files.py
git commit -m "docs: explain HSConfig guide strength readiness"
```

---

### Task 6: Final Verification And GitHub Hygiene

**Files:**
- No code files unless verification reveals a concrete regression.
- Review: all files touched by Tasks 1-5.

**Interfaces:**
- Consumes completed task commits.
- Produces green verification, clean Git status, and pushed `main`.

- [ ] **Step 1: Run focused verification**

Run:

```powershell
python -m pytest tests/test_operator_summary.py tests/test_prepare_cli.py tests/test_source_document_builder.py tests/test_option_identity_resolver.py tests/test_semantic_enrichment.py tests/test_depth_matrix_e2e.py tests/test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 2: Run adjacent workflow verification**

Run:

```powershell
python -m pytest tests/test_shadowpriest_depth_e2e.py tests/test_multideck_source_backed_e2e.py tests/test_compile_globalvalues.py tests/test_card_behavior_router.py tests/test_compile_combo.py tests/test_config_readiness.py tests/test_guide_source_depth.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: Check docs and placeholder cleanliness**

Run:

```powershell
rg -n "TB[D]|TO[D]O|implement late[r]|fill in detail[s]|Similar to Tas[k]|appropriate error handlin[g]|Write tests for the abov[e]" docs README.md .agents src tests
```

Expected: no matches introduced by this work.

- [ ] **Step 5: Review diff**

Run:

```powershell
git diff --stat
git diff -- README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md docs/operator/guide-research-policy.md
git diff -- src/hsconfig/operator_summary.py src/hsconfig/source_document_builder.py src/hsconfig/option_identity_resolver.py src/hsconfig/semantic_enrichment.py
```

Expected: changes stay within the plan scope and do not add HSTuner/runtime-log concepts.

- [ ] **Step 6: Final commit if verification changes were needed**

If Step 1-5 required fixes after earlier commits, commit those fixes:

```powershell
git add README.md .agents docs src tests
git commit -m "test: verify HSConfig source-backed depth closure"
```

If there are no remaining changes, skip this command.

- [ ] **Step 7: Push main**

Run:

```powershell
git status --short --branch
git push origin main
```

Expected: branch is clean and `main` pushes to `origin/main`.

---

## Self-Review

**Spec coverage:** The plan covers the recommended Source-Backed Depth Closure: stronger per-card claim lanes, better operator explanation, deterministic linked entities, compact depth matrix, docs/skill polish, and final verification. It intentionally excludes HSTuner, winrate, replay parsing, Presume, and Concede from the normal path.

**Placeholder scan:** This plan avoids deferred placeholders and gives exact files, test names, functions, commands, and expected outcomes.

**Type consistency:** New fields are consistently named `guide_strength_summary`, `semantic_blockers`, `claim_readiness`, `specificity_status`, and `trust_ceiling`. `build_operator_summary()` remains backward compatible through optional parameters.

**Execution note:** Use Subagent-Driven execution. Assign exactly one worker per task. Task 1 and Task 2 both touch reports/claims but their write scopes are disjoint enough when run sequentially. Task 3 and Task 4 should not run in parallel because Task 4 validates Task 3 behavior.
