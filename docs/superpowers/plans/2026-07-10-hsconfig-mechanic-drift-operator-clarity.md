# HSConfig Mechanic Drift Operator Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep HSConfig no-block and load-safe for every technically valid HearthRanger deck while making future Hearthstone mechanics, warning-only gaps, and legacy source-informed wording clearer.

**Architecture:** Preserve the existing pre-run package builder and apply gate. Add one small non-blocking mechanic drift report, surface its summary in `operator_summary.json`, and clarify that source-informed readiness is a legacy diagnostic surface rather than a runtime write gate. Do not add replay parsing, post-game tuning, candidate promotion, or winrate logic.

**Tech Stack:** Python 3.11, pytest, existing `hearthstone` dependency, existing HearthstoneJSON card row payloads, existing HSConfig CLI/report layout.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig pre-run only: no replay parsing, no Power.log/HDT/HSReplay analysis, no winrate logic, no HSTuner flow.
- Runtime apply permission remains controlled by `technical_status=VALID_PACKAGE`, `runtime_load_safe=true`, and `runtime_apply_mode=load_safe_apply`.
- Do not make `SOURCE_BACKED_STRONG`, `source_informed_apply_readiness`, guide depth, mechanic richness, or unknown mechanic coverage a runtime apply gate.
- Unknown or newly introduced mechanics must become visible as `warning_only` or report-only data and must not block a technically valid package.
- `GlobalValues.json` and `Mulligan.json` remain the minimal required runtime files.
- Per-card `<CARDID>.json` files remain normal rich output, not the minimal runtime apply gate.
- `Presume.json` and `Concede.json` remain outside the normal output path.
- Keep the repo slim: prefer one focused module, focused tests, and small doc updates over new orchestration.
- No new runtime dependencies.

---

## File Structure

- Modify `src/hsconfig/operator_summary.py`: add explicit diagnostic metadata to `source_informed_apply_readiness`; add mechanic drift summary passthrough.
- Modify `src/hsconfig/operator_guidance.py`: expose runtime-gate clarity and mechanic drift fields in operator guidance.
- Modify `src/hsconfig/cli_parser.py`: clarify `--allow-source-informed` help text.
- Modify `src/hsconfig/package_builder.py`: generate and write `reports/mechanic_drift_report.json`.
- Create `src/hsconfig/mechanic_drift.py`: build a non-blocking mechanic drift report from HearthstoneJSON-style card rows and current mechanic support mapping.
- Modify `src/hsconfig/report_ownership.py`: register `reports/mechanic_drift_report.json`.
- Modify `tests/test_operator_summary.py`: lock diagnostic-only source-informed readiness and mechanic drift summary.
- Modify `tests/test_operator_guidance.py`: lock operator guidance clarity.
- Modify `tests/test_cli_help.py`: lock CLI help wording for legacy source-informed flag.
- Create `tests/test_mechanic_drift.py`: unit tests for text-only keywords, unknown mechanics, unknown card types, and no-block semantics.
- Modify `tests/test_prepare_cli.py`: assert `prepare` writes the mechanic drift report and threads summary into operator output.
- Modify `tests/test_universal_wild_no_block_matrix.py`: assert no-block matrix still permits all representative Wild decks while warning surfaces remain non-blocking.
- Modify `tests/test_skill_files.py`: keep installed skill/docs language aligned.
- Modify `docs/operator/README.md`: document mechanic drift report and legacy diagnostic wording.
- Modify `docs/operator/universal-wild-no-block-contract.md`: document no-block mechanic drift behavior.
- Modify `.agents/skills/hsconfig/SKILL.md`: sync operator guidance language.
- Modify `.agents/skills/hsconfig/references/workflow.md`: sync report and gate wording.

---

### Task 1: Clarify Legacy Source-Informed Readiness As Diagnostic Only

**Files:**
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/operator_guidance.py`
- Modify: `src/hsconfig/cli_parser.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_operator_guidance.py`
- Test: `tests/test_cli_help.py`

**Interfaces:**
- Consumes: `build_operator_summary(...) -> dict[str, Any]`
- Produces: `source_informed_apply_readiness.runtime_gate_impact: "diagnostic_only"` and `source_informed_apply_readiness.legacy_flag_scope: "backward_compatible_only"`
- Produces: `operator_guidance.runtime_gate_truth: "runtime_apply_mode"` and `operator_guidance.source_informed_readiness_scope: "diagnostic_only"`

- [ ] **Step 1: Add failing operator summary test**

Append this test to `tests/test_operator_summary.py`:

```python
def test_source_informed_blocked_readiness_is_diagnostic_only_for_load_safe_apply():
    summary = build_operator_summary(
        deck_name="DiagnosticDeck",
        deck_code="AAECAf0EAAAA",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 1,
            "source_evidence": {"warnings_count": 0},
        },
        config_readiness_summary={
            "total_cards": 1,
            "runtime_emitted": 1,
            "cards_needing_runtime_surface": 1,
        },
        config_readiness_report={
            "cards": {
                "TEST_001": {
                    "first_missing_link": "needs_runtime_surface",
                    "name": "Test Card",
                }
            },
            "summary": {
                "mechanic_support": {
                    "support_level_counts": {
                        "direct": 0,
                        "partial": 0,
                        "warning_only": 0,
                    },
                    "warning_only_mechanics": [],
                    "warning_only_card_count": 0,
                },
                "mechanic_visibility": {
                    "non_blocking": True,
                    "bucket_counts": {
                        "direct": 0,
                        "identity_gated_direct": 0,
                        "partial": 0,
                        "warning_only": 0,
                    },
                    "mechanics_by_bucket": {
                        "direct": [],
                        "identity_gated_direct": [],
                        "partial": [],
                        "warning_only": [],
                    },
                    "warning_only_card_count": 0,
                    "first_warning_boundary": None,
                    "warning_boundaries": [],
                },
            },
        },
        claim_coverage_report={"summary": {"guide_backed": 1}},
        generated_files=[
            "CustomConfig/DiagnosticDeck/GlobalValues.json",
            "CustomConfig/DiagnosticDeck/Mulligan.json",
        ],
    )

    readiness = summary["source_informed_apply_readiness"]
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert readiness["status"] == "blocked"
    assert readiness["runtime_gate_impact"] == "diagnostic_only"
    assert readiness["legacy_flag_scope"] == "backward_compatible_only"
    assert readiness["requires_flag"] == "--allow-source-informed"
```

- [ ] **Step 2: Add failing operator guidance test**

Append this test to `tests/test_operator_guidance.py`:

```python
def test_operator_guidance_names_runtime_apply_mode_as_gate_truth():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "source_informed_apply_readiness": {
                "status": "blocked",
                "requires_flag": "--allow-source-informed",
                "runtime_gate_impact": "diagnostic_only",
                "legacy_flag_scope": "backward_compatible_only",
                "allowed_blocker_reasons": ["cards_need_guide_claims"],
                "blocking_reasons": ["cards_need_runtime_surface"],
                "source_gap_count": 0,
            },
        }
    )

    assert guidance["safe_to_apply"] is True
    assert guidance["runtime_apply_mode"] == "load_safe_apply"
    assert guidance["runtime_gate_truth"] == "runtime_apply_mode"
    assert guidance["source_informed_readiness_scope"] == "diagnostic_only"
    assert guidance["legacy_source_informed_flag_scope"] == "backward_compatible_only"
```

- [ ] **Step 3: Add failing CLI help test**

Update the existing `--allow-source-informed` test in `tests/test_cli_help.py` so it asserts this wording:

```python
def test_apply_help_marks_allow_source_informed_as_legacy_diagnostic_flag(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["apply", "--help"])
    help_text = capsys.readouterr().out
    assert "--allow-source-informed" in help_text
    assert "legacy diagnostic compatibility" in help_text
    assert "Normal load-safe packages do not require this flag" in help_text
```

- [ ] **Step 4: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py::test_source_informed_blocked_readiness_is_diagnostic_only_for_load_safe_apply tests/test_operator_guidance.py::test_operator_guidance_names_runtime_apply_mode_as_gate_truth tests/test_cli_help.py::test_apply_help_marks_allow_source_informed_as_legacy_diagnostic_flag -q
```

Expected: FAIL because the new readiness and guidance fields do not exist yet, and the CLI help text does not contain the exact legacy diagnostic wording.

- [ ] **Step 5: Implement summary diagnostic fields**

In `src/hsconfig/operator_summary.py`, add constants near the existing source-informed constants:

```python
LEGACY_SOURCE_INFORMED_FLAG = "--allow-source-informed"
SOURCE_INFORMED_RUNTIME_GATE_IMPACT = "diagnostic_only"
SOURCE_INFORMED_LEGACY_FLAG_SCOPE = "backward_compatible_only"
```

In `_source_informed_apply_readiness`, add these fields to every returned dict:

```python
"requires_flag": LEGACY_SOURCE_INFORMED_FLAG,
"runtime_gate_impact": SOURCE_INFORMED_RUNTIME_GATE_IMPACT,
"legacy_flag_scope": SOURCE_INFORMED_LEGACY_FLAG_SCOPE,
```

Replace literal `"--allow-source-informed"` values in this function with `LEGACY_SOURCE_INFORMED_FLAG`.

- [ ] **Step 6: Implement guidance fields**

In `src/hsconfig/operator_guidance.py`, add this helper:

```python
def _source_informed_scope_fields(summary: dict[str, Any]) -> dict[str, Any]:
    readiness = summary.get("source_informed_apply_readiness")
    if not isinstance(readiness, dict):
        return {
            "runtime_gate_truth": "runtime_apply_mode",
            "source_informed_readiness_scope": "not_present",
            "legacy_source_informed_flag_scope": "not_present",
        }
    return {
        "runtime_gate_truth": "runtime_apply_mode",
        "source_informed_readiness_scope": str(
            readiness.get("runtime_gate_impact", "diagnostic_only")
        ),
        "legacy_source_informed_flag_scope": str(
            readiness.get("legacy_flag_scope", "backward_compatible_only")
        ),
    }
```

Add `**_source_informed_scope_fields(summary),` to every returned guidance dict in `build_operator_guidance()`.

- [ ] **Step 7: Update CLI help text**

In `src/hsconfig/cli_parser.py`, replace the `apply` parser description and epilog with:

```python
description=(
    "Apply a validated pre-run CustomConfig package. "
    "--allow-source-informed is retained for legacy diagnostic compatibility. "
    "Normal load-safe packages do not require this flag."
),
epilog=(
    "Legacy diagnostic compatibility: --allow-source-informed is not the normal "
    "runtime write gate. Normal load-safe packages do not require this flag; "
    "runtime_apply_mode=load_safe_apply is the operator-facing write mode."
),
```

- [ ] **Step 8: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py::test_source_informed_blocked_readiness_is_diagnostic_only_for_load_safe_apply tests/test_operator_guidance.py::test_operator_guidance_names_runtime_apply_mode_as_gate_truth tests/test_cli_help.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

Run:

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/operator_guidance.py src/hsconfig/cli_parser.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_cli_help.py
git commit -m "clarify source-informed readiness as diagnostic"
```

---

### Task 2: Add Non-Blocking Mechanic Drift Report

**Files:**
- Create: `src/hsconfig/mechanic_drift.py`
- Test: `tests/test_mechanic_drift.py`

**Interfaces:**
- Consumes: HearthstoneJSON-style card rows as `Iterable[dict[str, Any]]`
- Consumes: `support_for_roles(roles: Iterable[str]) -> list[dict[str, Any]]`
- Produces: `build_mechanic_drift_report(cards: Iterable[dict[str, Any]]) -> dict[str, Any]`

- [ ] **Step 1: Write failing mechanic drift tests**

Create `tests/test_mechanic_drift.py` with this content:

```python
from hsconfig.mechanic_drift import build_mechanic_drift_report


def test_mechanic_drift_detects_text_only_tradeable_without_blocking():
    report = build_mechanic_drift_report(
        [
            {
                "id": "SW_001",
                "name": "Text Trade Card",
                "type": "SPELL",
                "mechanics": [],
                "referencedTags": [],
                "text": "Tradeable. Deal 2 damage.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["text_only_mechanics"] == ["tradeable"]
    assert report["unknown_mechanics"] == []
    assert report["support_by_mechanic"]["tradeable"]["support_level"] == "warning_only"


def test_mechanic_drift_keeps_unknown_mechanics_warning_only():
    report = build_mechanic_drift_report(
        [
            {
                "id": "FUTURE_001",
                "name": "Future Card",
                "type": "MINION",
                "mechanics": ["FUTURE_KEYWORD"],
                "referencedTags": [],
                "text": "Future Keyword: Do something.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["unknown_mechanics"] == ["future_keyword"]
    assert report["support_by_mechanic"]["future_keyword"]["support_level"] == "warning_only"
    assert report["support_by_mechanic"]["future_keyword"]["registered"] is False


def test_mechanic_drift_reports_unknown_card_types_without_blocking():
    report = build_mechanic_drift_report(
        [
            {
                "id": "FUTURE_TYPE_001",
                "name": "Future Type Card",
                "type": "STARSHIP",
                "mechanics": [],
                "referencedTags": [],
                "text": "A future card type.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["card_types"] == ["starship"]
    assert report["unknown_card_types"] == ["starship"]
    assert report["summary"]["unknown_card_type_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_drift.py -q
```

Expected: FAIL because `hsconfig.mechanic_drift` does not exist.

- [ ] **Step 3: Implement `mechanic_drift.py`**

Create `src/hsconfig/mechanic_drift.py` with this content:

```python
from __future__ import annotations

import re
from typing import Any, Iterable

from hsconfig.mechanic_support import support_for_roles


KNOWN_CARD_TYPES = {
    "enchantment",
    "hero",
    "hero_power",
    "location",
    "minion",
    "spell",
    "weapon",
}

TEXT_MECHANIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "choose_one": ("choose one",),
    "discover": ("discover",),
    "dredge": ("dredge",),
    "tradeable": ("tradeable",),
    "start_of_game": ("start of game",),
    "forge": ("forge",),
    "finale": ("finale",),
    "manathirst": ("manathirst",),
    "infuse": ("infuse", "infused"),
    "corrupt": ("corrupt", "corrupted"),
    "outcast": ("outcast",),
    "excavate": ("excavate",),
    "plague": ("plague",),
    "dormant": ("dormant",),
    "questline": ("questline",),
    "titan": ("titan",),
    "colossal": ("colossal",),
}


def build_mechanic_drift_report(cards: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [card for card in cards if isinstance(card, dict)]
    mechanics_by_card: dict[str, list[str]] = {}
    text_only_mechanics: set[str] = set()
    all_mechanics: set[str] = set()
    card_types: set[str] = set()

    for index, card in enumerate(rows):
        card_id = str(card.get("id") or card.get("card_id") or f"row_{index}")
        explicit = _explicit_mechanics(card)
        text_mechanics = _text_mechanics(str(card.get("text", "")))
        mechanic_set = set(explicit) | set(text_mechanics)
        text_only_mechanics.update(mechanic for mechanic in text_mechanics if mechanic not in explicit)
        all_mechanics.update(mechanic_set)
        mechanics_by_card[card_id] = sorted(mechanic_set)
        card_type = str(card.get("type", "")).strip().lower()
        if card_type:
            card_types.add(card_type)

    support_rows = support_for_roles(sorted(all_mechanics))
    support_by_mechanic = {str(row["mechanic"]): row for row in support_rows}
    unknown_mechanics = sorted(
        mechanic
        for mechanic, support in support_by_mechanic.items()
        if support.get("registered") is False
    )
    unknown_card_types = sorted(card_type for card_type in card_types if card_type not in KNOWN_CARD_TYPES)

    return {
        "schema_version": 1,
        "non_blocking": True,
        "total_cards": len(rows),
        "card_types": sorted(card_types),
        "unknown_card_types": unknown_card_types,
        "mechanics": sorted(all_mechanics),
        "unknown_mechanics": unknown_mechanics,
        "text_only_mechanics": sorted(text_only_mechanics),
        "mechanics_by_card": mechanics_by_card,
        "support_by_mechanic": support_by_mechanic,
        "summary": {
            "mechanic_count": len(all_mechanics),
            "unknown_mechanic_count": len(unknown_mechanics),
            "text_only_mechanic_count": len(text_only_mechanics),
            "unknown_card_type_count": len(unknown_card_types),
        },
    }


def _explicit_mechanics(card: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("mechanics", "referencedTags", "referenced_tags"):
        raw = card.get(key, [])
        if isinstance(raw, list):
            values.extend(_normalize_token(item) for item in raw if str(item).strip())
    return sorted(set(values))


def _text_mechanics(text: str) -> list[str]:
    normalized = " ".join(re.sub(r"<[^>]+>", " ", text).lower().split())
    found = set()
    for mechanic, patterns in TEXT_MECHANIC_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            found.add(mechanic)
    return sorted(found)


def _normalize_token(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_drift.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add src/hsconfig/mechanic_drift.py tests/test_mechanic_drift.py
git commit -m "add nonblocking mechanic drift report"
```

---

### Task 3: Thread Mechanic Drift Into Prepare Reports And Operator Summary

**Files:**
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/operator_guidance.py`
- Modify: `src/hsconfig/report_ownership.py`
- Test: `tests/test_prepare_cli.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_operator_guidance.py`

**Interfaces:**
- Consumes: `build_mechanic_drift_report(cards_payload["cards"]) -> dict[str, Any]`
- Produces: `reports/mechanic_drift_report.json`
- Produces: `operator_summary["mechanic_drift_summary"]`
- Produces: `operator_guidance["mechanic_drift_summary"]`

- [ ] **Step 1: Add failing operator summary unit test**

Append this test to `tests/test_operator_summary.py`:

```python
def test_operator_summary_threads_nonblocking_mechanic_drift_summary():
    summary = build_operator_summary(
        deck_name="DriftDeck",
        deck_code="AAECAf0EAAAA",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "static_semantics_only",
            "claim_count": 0,
        },
        mechanic_drift_report={
            "non_blocking": True,
            "summary": {
                "mechanic_count": 3,
                "unknown_mechanic_count": 1,
                "text_only_mechanic_count": 1,
                "unknown_card_type_count": 1,
            },
            "unknown_mechanics": ["future_keyword"],
            "text_only_mechanics": ["tradeable"],
            "unknown_card_types": ["starship"],
        },
        generated_files=[
            "CustomConfig/DriftDeck/GlobalValues.json",
            "CustomConfig/DriftDeck/Mulligan.json",
            "reports/mechanic_drift_report.json",
        ],
    )

    drift = summary["mechanic_drift_summary"]
    assert drift == {
        "non_blocking": True,
        "mechanic_count": 3,
        "unknown_mechanic_count": 1,
        "text_only_mechanic_count": 1,
        "unknown_card_type_count": 1,
        "unknown_mechanics": ["future_keyword"],
        "text_only_mechanics": ["tradeable"],
        "unknown_card_types": ["starship"],
    }
    assert summary["runtime_apply_mode"] == "load_safe_apply"
```

- [ ] **Step 2: Add failing prepare CLI integration test**

Append this test to `tests/test_prepare_cli.py`:

```python
def test_prepare_writes_mechanic_drift_report_and_operator_summary(tmp_path: Path, capsys):
    out = tmp_path / "package"
    runtime = tmp_path / "runtime"
    cards = tmp_path / "cards.json"
    cards.write_text(
        json.dumps(
            [
                {
                    "id": "SW_001",
                    "name": "Text Trade Card",
                    "type": "SPELL",
                    "mechanics": [],
                    "text": "Tradeable. Deal 2 damage.",
                },
                {
                    "id": "FUTURE_001",
                    "name": "Future Card",
                    "type": "STARSHIP",
                    "mechanics": ["FUTURE_KEYWORD"],
                    "text": "Future Keyword: Do something.",
                },
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "prepare",
            "--deck-name",
            "DriftDeck",
            "--deck-code",
            "AAECAf0EAAAA",
            "--out",
            str(out),
            "--runtime-root",
            str(runtime),
            "--cards-json",
            str(cards),
            "--allow-placeholder",
            "--json",
        ]
    )

    assert exit_code == 0
    reports = out / "reports"
    drift_report = json.loads((reports / "mechanic_drift_report.json").read_text(encoding="utf-8"))
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    assert drift_report["non_blocking"] is True
    assert drift_report["text_only_mechanics"] == ["tradeable"]
    assert drift_report["unknown_mechanics"] == ["future_keyword"]
    assert drift_report["unknown_card_types"] == ["starship"]
    assert operator["mechanic_drift_summary"]["unknown_mechanic_count"] == 1
    assert operator["mechanic_drift_summary"]["unknown_card_type_count"] == 1
    assert operator["runtime_apply_mode"] == "load_safe_apply"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py::test_operator_summary_threads_nonblocking_mechanic_drift_summary tests/test_prepare_cli.py::test_prepare_writes_mechanic_drift_report_and_operator_summary -q
```

Expected: FAIL because `mechanic_drift_report` is not accepted by `build_operator_summary()` and `prepare` does not write `mechanic_drift_report.json`.

- [ ] **Step 4: Implement package builder integration**

In `src/hsconfig/package_builder.py`, import:

```python
from hsconfig.mechanic_drift import build_mechanic_drift_report
```

After `semantic_report` is built and before reports are written, add:

```python
    mechanic_drift_report = build_mechanic_drift_report(cards_payload.get("cards", []))
```

Write the report after `semantic_enrichment_report.json`:

```python
    write_json(reports_dir / "mechanic_drift_report.json", mechanic_drift_report)
```

Add it to `operator_summary_kwargs`:

```python
        "mechanic_drift_report": mechanic_drift_report,
```

- [ ] **Step 5: Implement operator summary support**

In `src/hsconfig/operator_summary.py`, add parameter:

```python
    mechanic_drift_report: dict[str, Any] | None = None,
```

Add this field to the `summary` dict:

```python
        "mechanic_drift_summary": _mechanic_drift_summary(mechanic_drift_report),
```

Add helper:

```python
def _mechanic_drift_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "non_blocking": True,
            "mechanic_count": 0,
            "unknown_mechanic_count": 0,
            "text_only_mechanic_count": 0,
            "unknown_card_type_count": 0,
            "unknown_mechanics": [],
            "text_only_mechanics": [],
            "unknown_card_types": [],
        }
    summary = report.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        "non_blocking": bool(report.get("non_blocking", True)),
        "mechanic_count": _int_value(summary.get("mechanic_count", 0)),
        "unknown_mechanic_count": _int_value(summary.get("unknown_mechanic_count", 0)),
        "text_only_mechanic_count": _int_value(summary.get("text_only_mechanic_count", 0)),
        "unknown_card_type_count": _int_value(summary.get("unknown_card_type_count", 0)),
        "unknown_mechanics": [str(item) for item in report.get("unknown_mechanics", [])],
        "text_only_mechanics": [str(item) for item in report.get("text_only_mechanics", [])],
        "unknown_card_types": [str(item) for item in report.get("unknown_card_types", [])],
    }
```

- [ ] **Step 6: Implement operator guidance support**

In `src/hsconfig/operator_guidance.py`, add:

```python
def _mechanic_drift_fields(summary: dict[str, Any]) -> dict[str, Any]:
    drift = summary.get("mechanic_drift_summary")
    if isinstance(drift, dict):
        return {"mechanic_drift_summary": drift}
    return {
        "mechanic_drift_summary": {
            "non_blocking": True,
            "mechanic_count": 0,
            "unknown_mechanic_count": 0,
            "text_only_mechanic_count": 0,
            "unknown_card_type_count": 0,
            "unknown_mechanics": [],
            "text_only_mechanics": [],
            "unknown_card_types": [],
        }
    }
```

Add `**_mechanic_drift_fields(summary),` to every returned guidance dict in `build_operator_guidance()`.

- [ ] **Step 7: Register report ownership**

In `src/hsconfig/report_ownership.py`, add this report row to the returned ownership list:

```python
{
    "file": "reports/mechanic_drift_report.json",
    "producer": "prepare",
    "authority": "non_blocking_mechanic_drift_visibility",
    "open_when": "mechanic_drift_summary shows unknown mechanics, text-only mechanics, or unknown card types",
}
```

- [ ] **Step 8: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_drift.py tests/test_operator_summary.py::test_operator_summary_threads_nonblocking_mechanic_drift_summary tests/test_prepare_cli.py::test_prepare_writes_mechanic_drift_report_and_operator_summary tests/test_operator_guidance.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit Task 3**

Run:

```powershell
git add src/hsconfig/package_builder.py src/hsconfig/operator_summary.py src/hsconfig/operator_guidance.py src/hsconfig/report_ownership.py tests/test_prepare_cli.py tests/test_operator_summary.py tests/test_operator_guidance.py
git commit -m "surface mechanic drift in operator reports"
```

---

### Task 4: Expand Future Wild Mechanic Visibility Without New Blocks

**Files:**
- Modify: `src/hsconfig/mechanic_support.py`
- Test: `tests/test_mechanic_support.py`
- Test: `tests/test_mechanic_drift.py`

**Interfaces:**
- Consumes: `MECHANIC_SUPPORT`
- Produces: registered support rows for common future/Wild mechanics so they are visible with intentional support levels instead of accidental unknown fallback.

- [ ] **Step 1: Add failing common-Wild mechanic support test**

Append this test to `tests/test_mechanic_support.py`:

```python
def test_future_wild_mechanics_are_registered_without_blocking():
    rows = support_for_roles(
        [
            "questline",
            "highlander",
            "outcast",
            "infuse",
            "corrupt",
            "finale",
            "manathirst",
            "forge",
            "excavate",
            "plague",
            "titan",
            "colossal",
            "dormant",
            "invoke",
            "jade",
            "cthun_package",
            "spell_school",
        ]
    )
    by_mechanic = {row["mechanic"]: row for row in rows}

    expected = {
        "questline": "partial",
        "highlander": "partial",
        "outcast": "warning_only",
        "infuse": "partial",
        "corrupt": "partial",
        "finale": "partial",
        "manathirst": "partial",
        "forge": "warning_only",
        "excavate": "partial",
        "plague": "partial",
        "titan": "warning_only",
        "colossal": "partial",
        "dormant": "partial",
        "invoke": "partial",
        "jade": "partial",
        "cthun_package": "partial",
        "spell_school": "partial",
    }
    assert set(by_mechanic) == set(expected)
    for mechanic, support_level in expected.items():
        assert by_mechanic[mechanic]["support_level"] == support_level
        assert by_mechanic[mechanic].get("registered", True) is True
```

- [ ] **Step 2: Add failing drift test for registered future mechanics**

Append this test to `tests/test_mechanic_drift.py`:

```python
def test_mechanic_drift_treats_registered_future_mechanics_as_known():
    report = build_mechanic_drift_report(
        [
            {
                "id": "FUTURE_QUEST",
                "name": "Future Questline",
                "type": "SPELL",
                "mechanics": ["QUESTLINE", "MANATHIRST"],
                "text": "Questline. Manathirst (8): Improve this.",
            }
        ]
    )

    assert report["non_blocking"] is True
    assert report["unknown_mechanics"] == []
    assert report["support_by_mechanic"]["questline"]["support_level"] == "partial"
    assert report["support_by_mechanic"]["manathirst"]["support_level"] == "partial"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_support.py::test_future_wild_mechanics_are_registered_without_blocking tests/test_mechanic_drift.py::test_mechanic_drift_treats_registered_future_mechanics_as_known -q
```

Expected: FAIL because the listed future/Wild mechanics are not all registered.

- [ ] **Step 4: Add support rows**

In `src/hsconfig/mechanic_support.py`, add these entries to `MECHANIC_SUPPORT`:

```python
    "questline": {
        "support_level": "partial",
        "normal_path_surfaces": ["GlobalValues.json:deck_posture", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Questline progress and reward timing can be encouraged, not fully planned as a separate action tree.",
    },
    "highlander": {
        "support_level": "partial",
        "normal_path_surfaces": ["GlobalValues.json:deck_posture", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "No-duplicate payoff posture can be represented; deck legality remains deck construction.",
    },
    "outcast": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Exact hand-edge position has no documented normal-path VisionAI surface.",
    },
    "infuse": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:board_pressure"],
        "warning_boundary": "Infuse setup can be encouraged; exact counter state remains broader bot evaluation.",
    },
    "corrupt": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "Combo.json:exact_sequence"],
        "warning_boundary": "Corrupt sequencing can be represented when source-backed; exact hand-state timing remains partial.",
    },
    "finale": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Finale requires exact remaining-mana state, which is not a dedicated normal-path surface.",
    },
    "manathirst": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Mana-threshold timing can be encouraged; exact threshold control remains partial.",
    },
    "forge": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Forge is an alternate pre-play action with no documented normal-path runtime block.",
    },
    "excavate": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Excavate card timing can be encouraged; treasure chain identity remains report-only unless source-backed.",
    },
    "plague": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:deck_posture"],
        "warning_boundary": "Shuffle-pressure posture can be represented; opponent draw timing remains outside pre-run control.",
    },
    "titan": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Titan ability choice is option identity and has no documented normal-path runtime row.",
    },
    "colossal": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Colossal body timing can be represented; appendage interaction remains broader bot evaluation.",
    },
    "dormant": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Dormant payoff timing can be represented; wake-up timing remains partial.",
    },
    "invoke": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:deck_posture"],
        "warning_boundary": "Invoke progression can be encouraged; exact upgrade state remains partial.",
    },
    "jade": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:board_pressure"],
        "warning_boundary": "Jade scaling posture can be represented; exact summoned stat line is not a separate runtime surface.",
    },
    "cthun_package": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:deck_posture"],
        "warning_boundary": "C'Thun package setup can be represented; shard/order state remains broader bot evaluation.",
    },
    "spell_school": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:deck_posture"],
        "warning_boundary": "Spell-school synergy can be encouraged; exact school chain state remains source-dependent.",
    },
```

Add aliases where useful:

```python
    "quest": "questline",
    "sidequest": "questline",
    "no_duplicate": "highlander",
    "no_duplicates": "highlander",
    "cthun": "cthun_package",
    "c_thun": "cthun_package",
```

- [ ] **Step 5: Extend text pattern detection**

In `src/hsconfig/mechanic_drift.py`, add patterns for the registered mechanics that are not already present:

```python
    "highlander": ("if your deck has no duplicates", "no duplicates"),
    "jade": ("jade golem",),
    "cthun_package": ("c'thun", "cthun"),
    "spell_school": ("fire spell", "frost spell", "fel spell", "shadow spell", "holy spell", "nature spell", "arcane spell"),
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_support.py tests/test_mechanic_drift.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add src/hsconfig/mechanic_support.py src/hsconfig/mechanic_drift.py tests/test_mechanic_support.py tests/test_mechanic_drift.py
git commit -m "expand nonblocking wild mechanic visibility"
```

---

### Task 5: Document No-Block Drift Behavior And Sync Skill Text

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_docs_active_path.py`

**Interfaces:**
- Consumes: `operator_summary["mechanic_drift_summary"]`
- Produces: active docs and installed skill guidance that describe mechanic drift as non-blocking.

- [ ] **Step 1: Add failing skill/doc tests**

Append this test to `tests/test_skill_files.py`:

```python
def test_skill_docs_explain_mechanic_drift_is_nonblocking():
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(encoding="utf-8")
    combined = f"{skill}\n{workflow}"
    assert "mechanic_drift_summary" in combined
    assert "reports/mechanic_drift_report.json" in combined
    assert "Unknown mechanics are warning-only and do not block load-safe apply" in combined
```

Append this test to `tests/test_docs_active_path.py`:

```python
def test_operator_docs_explain_mechanic_drift_without_new_gate():
    docs = "\n".join(
        [
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
            Path("docs/operator/universal-wild-no-block-contract.md").read_text(encoding="utf-8"),
        ]
    )
    assert "reports/mechanic_drift_report.json" in docs
    assert "mechanic_drift_summary" in docs
    assert "Unknown mechanics are warning-only and do not block load-safe apply" in docs
    assert "Mechanic drift is not a runtime apply gate" in docs
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py::test_skill_docs_explain_mechanic_drift_is_nonblocking tests/test_docs_active_path.py::test_operator_docs_explain_mechanic_drift_without_new_gate -q
```

Expected: FAIL because the exact new wording is not present.

- [ ] **Step 3: Update operator README**

In `docs/operator/README.md`, add this paragraph near the existing mechanic visibility section:

```markdown
`reports/mechanic_drift_report.json` is the non-blocking current-card-data drift surface. `mechanic_drift_summary` in `reports/operator_summary.json` lists unknown mechanics, text-only mechanics, and unknown card types detected from HearthstoneJSON-style metadata. Unknown mechanics are warning-only and do not block load-safe apply. Mechanic drift is not a runtime apply gate; it tells the operator which future Wild mechanic should be mapped next.
```

- [ ] **Step 4: Update no-block contract**

In `docs/operator/universal-wild-no-block-contract.md`, add this paragraph under `Non-Blocking Warnings`:

```markdown
Mechanic drift is not a runtime apply gate. `reports/mechanic_drift_report.json` and `mechanic_drift_summary` expose unknown mechanics, text-only mechanics, and unknown card types as warning data. Unknown mechanics are warning-only and do not block load-safe apply when `technical_status=VALID_PACKAGE` and `runtime_apply_mode=load_safe_apply`.
```

- [ ] **Step 5: Update skill and workflow references**

In `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md`, add this sentence to the operator report guidance:

```markdown
Open `reports/mechanic_drift_report.json` when `mechanic_drift_summary` shows unknown mechanics, text-only mechanics, or unknown card types. Unknown mechanics are warning-only and do not block load-safe apply.
```

- [ ] **Step 6: Run doc tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 7: Sync installed skill**

Run:

```powershell
$env:PYTHONPATH='src'; python scripts/sync_installed_skill.py
$env:PYTHONPATH='src'; python scripts/sync_installed_skill.py --check
```

Expected: `HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig`.

- [ ] **Step 8: Commit Task 5**

Run:

```powershell
git add docs/operator/README.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_skill_files.py tests/test_docs_active_path.py
git commit -m "document nonblocking mechanic drift"
```

---

### Task 6: Final Regression, No-Block Proof, And GitHub Update

**Files:**
- Verify only unless a previous task missed a sync file.

**Interfaces:**
- Consumes: all implemented tasks.
- Produces: green focused and full test evidence, clean git state, pushed `main`.

- [ ] **Step 1: Run focused no-block suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_multideck_source_backed_e2e.py tests/test_supplemental_cute_warrior_load_safe.py tests/test_runtime_apply.py tests/test_apply_gate.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_mechanic_support.py tests/test_mechanic_drift.py tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: PASS. No representative deck may become blocked due to source depth, unknown mechanics, warning-only mechanics, or mechanic drift.

- [ ] **Step 2: Run full suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Check active docs for wrong gate wording**

Run:

```powershell
rg -n "source_informed_apply_readiness.*runtime gate|--allow-source-informed --json|Unknown mechanics.*must block|Unknown mechanics.*do block|Mechanic drift is a runtime apply gate|Mechanic drift.*must block" README.md docs .agents src tests
```

Expected:
- No `--allow-source-informed --json` normal-path command appears.
- No active doc says unknown mechanics must block load-safe apply.
- Active docs explicitly say mechanic drift is not a runtime apply gate.

- [ ] **Step 4: Check generated skill sync**

Run:

```powershell
$env:PYTHONPATH='src'; python scripts/sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

- [ ] **Step 5: Inspect git status**

Run:

```powershell
git status --short --branch
```

Expected: current branch is `main`; only intentional changes are present before the final commit.

- [ ] **Step 6: Commit remaining changes**

If Task 6 found only expected sync or doc-test corrections, run:

```powershell
git add src/hsconfig/operator_summary.py src/hsconfig/operator_guidance.py src/hsconfig/cli_parser.py src/hsconfig/package_builder.py src/hsconfig/mechanic_drift.py src/hsconfig/mechanic_support.py src/hsconfig/report_ownership.py docs/operator/README.md docs/operator/universal-wild-no-block-contract.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_cli_help.py tests/test_mechanic_drift.py tests/test_mechanic_support.py tests/test_prepare_cli.py tests/test_skill_files.py tests/test_docs_active_path.py tests/test_universal_wild_no_block_matrix.py
git commit -m "harden mechanic drift no-block clarity"
```

If there are no changes after previous task commits, skip this commit and record that the branch already contains all task commits.

- [ ] **Step 7: Push main**

Run:

```powershell
git push origin main
```

Expected: push succeeds and `git status --short --branch` shows `## main...origin/main`.

---

## Self-Review Checklist

- Spec coverage: The plan preserves no-block runtime apply, adds non-blocking mechanic drift visibility, clarifies legacy source-informed wording, expands future Wild mechanics, updates docs/skill text, and verifies the representative deck matrix.
- Placeholder scan: No task relies on an undefined file, undefined function, or unspecified test command.
- Type consistency: `build_mechanic_drift_report(cards: Iterable[dict[str, Any]]) -> dict[str, Any]`, `mechanic_drift_summary`, `runtime_gate_impact`, and `legacy_flag_scope` are introduced before later tasks consume them.
- Scope control: The plan does not add replay parsing, HSTuner behavior, winrate, candidate promotion, or runtime evidence processing.
- Risk control: Unknown mechanics stay warning-only and non-blocking; no task changes the core `load_safe_apply` condition.
