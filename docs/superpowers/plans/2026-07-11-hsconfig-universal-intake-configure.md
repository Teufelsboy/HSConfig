# HSConfig Universal Intake Configure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a narrow one-command HSConfig configure path that produces a load-safe pre-run HearthRanger CustomConfig package for every valid deck input, while improving card-data and mechanic-drift intake without adding HSTuner, replay, winrate, or post-run scope.

**Architecture:** Keep the current HSConfig package compiler and guarded apply gate as the authority. Add a small orchestration command over the existing source-manifest -> draft-source-documents -> research-deck -> prepare -> validate path, plus a focused card-data intake module that gates deck cards through collectible HearthstoneJSON data and enriches linked companion entities from full cards.json. Mechanic drift remains warning-only and report-visible; only true technical load-safety failures block.

**Tech Stack:** Python standard library, existing `hsconfig` package modules, `pytest`, HearthstoneJSON-compatible JSON fixtures, existing HearthRanger VisionAI output validators.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- HSConfig remains pre-run only.
- Do not add replay parsing, winrate analysis, HSTuner sessions, post-run tuning, candidate promotion, or runtime log analysis.
- `reports/operator_summary.json` remains the single normal apply gate.
- `technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` remains normal runtime-write permission.
- `SOURCE_BACKED_STRONG` remains a source-confidence label, not the runtime-write gate.
- `generic_low_confidence`, thin Mulligan, warning-only mechanics, future mechanic drift, and config usefulness gaps stay non-blocking.
- Hard blocks remain limited to true technical/load-safety failures: malformed deck code, invalid JSON, missing required `GlobalValues.json` or `Mulligan.json`, undeclared/nested runtime files, normal-path `Presume.json` or `Concede.json`, or forged/stale apply evidence.
- Normal runtime output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and optional concrete `Combo.json`.
- Do not emit `Presume.json` or `Concede.json` in the normal path.
- Avoid new dependencies.
- Keep docs and installed skill in sync with `scripts/sync_installed_skill.py`.

---

## File Structure

- Create `src/hsconfig/commands/configure.py`: one-command orchestration for valid deck input to package output.
- Modify `src/hsconfig/cli.py`: route the new `configure` command.
- Modify `src/hsconfig/cli_parser.py`: expose `configure` as the normal top-level entry point while keeping lower-level commands available.
- Create `src/hsconfig/card_data_intake.py`: collectible deck-card gate and full-feed companion enrichment.
- Modify `src/hsconfig/hearthstonejson.py`: add collectible-feed constant/fetch helper, keep existing full-feed helper.
- Modify `src/hsconfig/card_metadata.py`: accept enriched companion metadata without changing current output schema incompatibly.
- Modify `src/hsconfig/mechanic_drift.py`: use a small versioned text/rule map for known drift mechanics and keep drift warning-only.
- Modify `src/hsconfig/commands/source_workflow.py`: thread card-data intake into research-deck context without blocking generation.
- Modify `docs/operator/README.md`: make `configure` the first normal path, with lower-level commands documented as diagnostics/advanced.
- Modify `docs/operator/universal-wild-no-block-contract.md`: document the three-layer intake and no-block boundary.
- Modify `.codex/skills/hsconfig/SKILL.md` source location if repo carries the installable skill source, then run sync; otherwise update the repo skill source used by `scripts/sync_installed_skill.py`.
- Test files:
  - Create `tests/test_configure_cli.py`
  - Create `tests/test_card_data_intake.py`
  - Modify `tests/test_cli_help.py`
  - Modify `tests/test_mechanic_drift.py`
  - Modify `tests/test_full_chain_cli_integration.py`
  - Modify `tests/test_universal_wild_no_block_matrix.py`
  - Modify `tests/test_skill_sync.py` only if its expected wording needs adjustment.

---

### Task 1: Add One-Command `configure` CLI Skeleton

**Files:**
- Create: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `src/hsconfig/cli_parser.py`
- Test: `tests/test_configure_cli.py`
- Test: `tests/test_cli_help.py`

**Interfaces:**
- Consumes:
  - existing `source_manifest_payload(args) -> tuple[dict, int]`
  - existing `draft_source_documents_payload(args) -> tuple[dict, int]`
  - existing `research_deck_payload(args) -> tuple[dict, int]`
  - existing `run_prepare_command(args, expert_mode=False) -> int`
  - existing `run_validate_command(args) -> int`
- Produces:
  - `run_configure_command(args: argparse.Namespace) -> int`
  - `configure_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]`
  - output directories:
    - `<out>/01_manifest`
    - `<out>/02_source_documents`
    - `<out>/03_research`
    - `<out>/04_package`
  - top-level `<out>/configure_summary.json`

- [ ] **Step 1: Write failing CLI help test**

Add to `tests/test_cli_help.py`:

```python
def test_root_help_names_configure_as_preferred_normal_path():
    help_text = _build_parser().format_help()

    assert "Preferred normal path: configure" in help_text
    assert "Lower-level normal path:" in help_text
    assert "source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply" in help_text


def test_configure_help_is_marked_preferred_normal_path(capsys):
    help_text = _subcommand_help("configure", capsys)

    assert "Preferred one-command pre-run package path" in help_text
    assert "--deck-name" in help_text
    assert "--deck-code" in help_text
    assert "--runtime-root" in help_text
    assert "--out" in help_text
    assert "--source-evidence-json" in help_text
    assert "--apply" in help_text
```

- [ ] **Step 2: Run help tests and verify failure**

Run:

```powershell
python -m pytest tests/test_cli_help.py::test_root_help_names_configure_as_preferred_normal_path tests/test_cli_help.py::test_configure_help_is_marked_preferred_normal_path -q
```

Expected: fail because `configure` is not registered yet.

- [ ] **Step 3: Write failing configure smoke test**

Create `tests/test_configure_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_configure_builds_valid_load_safe_package_without_source_evidence(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_cards", lambda timeout=10.0: [])

    out = tmp_path / "configure"
    runtime_root = tmp_path / "runtime"

    assert main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--json",
        ]
    ) == 0

    package = out / "04_package"
    operator = _read_json(package / "reports" / "operator_summary.json")
    summary = _read_json(out / "configure_summary.json")

    assert summary["status"] == "OK"
    assert summary["package_path"] == str(package)
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert (package / "CustomConfig").exists()
    assert list(package.glob("CustomConfig/*/GlobalValues.json"))
    assert list(package.glob("CustomConfig/*/Mulligan.json"))
```

- [ ] **Step 4: Run configure smoke test and verify failure**

Run:

```powershell
python -m pytest tests/test_configure_cli.py::test_configure_builds_valid_load_safe_package_without_source_evidence -q
```

Expected: fail because the command does not exist.

- [ ] **Step 5: Register parser command**

Modify `src/hsconfig/cli_parser.py`.

Update the parser epilog to:

```python
        epilog=(
            "Normal operator docs: docs/operator/README.md\n"
            "Preferred normal path: configure.\n"
            "Lower-level normal path: source-manifest -> draft-source-documents -> research-deck -> "
            f"prepare -> validate -> apply. {NEGATIVE_SCOPE_TEXT}\n"
            "Expert and legacy path: build, --claims-json, "
            "--cards-json, --plan-reports-dir."
        ),
```

Add this subparser before `build`:

```python
    configure = subparsers.add_parser(
        "configure",
        help="preferred one-command pre-run package path",
        description=(
            "Preferred one-command pre-run package path. Decode a deck, build "
            "source/research artifacts, prepare a load-safe package, validate it, "
            "and optionally apply it through the existing guarded apply gate."
        ),
    )
    configure.add_argument("--deck-name", required=True)
    configure.add_argument("--deck-code", required=True)
    configure.add_argument("--out", required=True)
    configure.add_argument("--runtime-root", required=True)
    configure.add_argument("--source-evidence-json")
    configure.add_argument("--cards-json")
    configure.add_argument("--collectible-cards-json")
    configure.add_argument("--full-cards-json")
    configure.add_argument("--allow-placeholder", action="store_true")
    configure.add_argument("--apply", action="store_true")
    configure.add_argument("--json", action="store_true")
```

- [ ] **Step 6: Create command skeleton**

Create `src/hsconfig/commands/configure.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hsconfig.commands.apply import run_apply_command, run_validate_command
from hsconfig.commands.common import emit_result
from hsconfig.commands.prepare import run_prepare_command
from hsconfig.commands.source_workflow import (
    draft_source_documents_payload,
    research_deck_payload,
    source_manifest_payload,
)
from hsconfig.io import write_json
from hsconfig.package_io import prepare_research_output_dir


def run_configure_command(args: argparse.Namespace) -> int:
    payload, status = configure_payload(args)
    return emit_result(payload, bool(getattr(args, "json", False)), status)


def configure_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)

    manifest_dir = out / "01_manifest"
    draft_dir = out / "02_source_documents"
    research_dir = out / "03_research"
    package_dir = out / "04_package"

    common = {
        "deck_name": args.deck_name,
        "deck_code": args.deck_code,
        "cards_json": getattr(args, "cards_json", None),
        "collectible_cards_json": getattr(args, "collectible_cards_json", None),
        "full_cards_json": getattr(args, "full_cards_json", None),
        "allow_placeholder": bool(getattr(args, "allow_placeholder", False)),
        "json": True,
    }

    manifest_payload, manifest_status = source_manifest_payload(
        SimpleNamespace(**common, out=str(manifest_dir))
    )
    if manifest_status != 0:
        return _finish(out, "failed", manifest_payload, manifest_status)

    source_documents_json = None
    if getattr(args, "source_evidence_json", None):
        draft_payload, draft_status = draft_source_documents_payload(
            SimpleNamespace(
                **common,
                source_evidence_json=args.source_evidence_json,
                out=str(draft_dir),
            )
        )
        if draft_status != 0:
            return _finish(out, "failed", draft_payload, draft_status)
        source_documents_json = draft_dir / "source_documents.json"

    research_payload, research_status = research_deck_payload(
        SimpleNamespace(
            **common,
            out=str(research_dir),
            source_documents_json=str(source_documents_json) if source_documents_json else None,
            source_evidence_json=getattr(args, "source_evidence_json", None),
            guide_sources_json=None,
            claims_json=None,
            skip_semantic_fetch=False,
            auto_research_fallback=True,
        )
    )
    if research_status != 0:
        return _finish(out, "failed", research_payload, research_status)

    prepare_status = run_prepare_command(
        SimpleNamespace(
            deck_name=args.deck_name,
            deck_code=args.deck_code,
            out=str(package_dir),
            runtime_root=args.runtime_root,
            guide_sources_json=str(research_dir / "guide_sources.json"),
            source_documents_json=str(source_documents_json) if source_documents_json else None,
            cards_json=getattr(args, "cards_json", None),
            claims_json=None,
            plan_reports_dir=None,
            allow_placeholder=bool(getattr(args, "allow_placeholder", False)),
            auto_research_fallback=True,
            json=True,
        ),
        expert_mode=False,
    )
    if prepare_status != 0:
        return _finish(out, "failed", {"stage": "prepare"}, prepare_status)

    validate_status = run_validate_command(SimpleNamespace(package=str(package_dir), json=True))
    if validate_status != 0:
        return _finish(out, "failed", {"stage": "validate"}, validate_status)

    apply_status = None
    if bool(getattr(args, "apply", False)):
        apply_status = run_apply_command(
            SimpleNamespace(
                package=str(package_dir),
                runtime_root=args.runtime_root,
                allow_source_informed=False,
                fake=False,
                from_fake_receipt=None,
                json=True,
            )
        )
        if apply_status != 0:
            return _finish(out, "failed", {"stage": "apply"}, apply_status)

    return _finish(
        out,
        "OK",
        {
            "manifest_path": str(manifest_dir / "source_research_manifest.json"),
            "research_path": str(research_dir),
            "package_path": str(package_dir),
            "apply_performed": bool(getattr(args, "apply", False)),
            "apply_status": apply_status,
        },
        0,
    )


def _finish(out: Path, status: str, payload: dict[str, Any], exit_code: int) -> tuple[dict[str, Any], int]:
    summary = {"schema_version": 1, "status": status, **payload}
    write_json(out / "configure_summary.json", summary)
    return summary, exit_code
```

- [ ] **Step 7: Route command**

Modify `src/hsconfig/cli.py` imports:

```python
from hsconfig.commands.configure import run_configure_command
```

Add before `apply`:

```python
    if args.command == "configure":
        return run_configure_command(args)
```

- [ ] **Step 8: Run focused tests**

Run:

```powershell
python -m pytest tests/test_configure_cli.py tests/test_cli_help.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

Run:

```powershell
git add src/hsconfig/commands/configure.py src/hsconfig/cli.py src/hsconfig/cli_parser.py tests/test_configure_cli.py tests/test_cli_help.py
git commit -m "feat: add hsconfig configure command"
```

---

### Task 2: Add Three-Layer Card Data Intake

**Files:**
- Create: `src/hsconfig/card_data_intake.py`
- Modify: `src/hsconfig/hearthstonejson.py`
- Test: `tests/test_card_data_intake.py`

**Interfaces:**
- Consumes:
  - deck cards with `card_id`, `dbf_id`, `count`
  - normalized HearthstoneJSON rows from `hearthstonejson.normalize_card_row`
- Produces:
  - `build_card_data_context(deck_cards: list[dict[str, Any]], collectible_cards: list[dict[str, Any]], full_cards: list[dict[str, Any]]) -> dict[str, Any]`
  - context keys:
    - `deck_source_records: dict[str, dict[str, Any]]`
    - `companion_source_records: dict[str, dict[str, Any]]`
    - `card_data_intake_report: dict[str, Any]`

- [ ] **Step 1: Write failing tests**

Create `tests/test_card_data_intake.py`:

```python
from hsconfig.card_data_intake import build_card_data_context


def test_card_data_context_gates_deck_cards_with_collectible_feed():
    deck_cards = [{"card_id": "EX1_001", "dbf_id": 1, "count": 2}]
    collectible = [
        {
            "id": "EX1_001",
            "dbf_id": 1,
            "name": "Deck Card",
            "type": "MINION",
            "text": "Battlecry: do something.",
            "mechanics": ["BATTLECRY"],
            "referenced_tags": [],
            "entourage": [],
            "hero_power_dbf_id": None,
        }
    ]
    full = []

    context = build_card_data_context(
        deck_cards=deck_cards,
        collectible_cards=collectible,
        full_cards=full,
    )

    assert context["deck_source_records"]["EX1_001"]["name"] == "Deck Card"
    assert context["card_data_intake_report"]["summary"]["matched_deck_cards"] == 1
    assert context["card_data_intake_report"]["summary"]["missing_deck_cards"] == 0


def test_card_data_context_enriches_referenced_companions_from_full_feed():
    deck_cards = [{"card_id": "HERO_01", "dbf_id": 10, "count": 1}]
    collectible = [
        {
            "id": "HERO_01",
            "dbf_id": 10,
            "name": "Hero",
            "type": "HERO",
            "text": "",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": ["TOKEN_01"],
            "hero_power_dbf_id": 20,
        }
    ]
    full = [
        {
            "id": "HP_01",
            "dbf_id": 20,
            "name": "Hero Power",
            "type": "HERO_POWER",
            "text": "Deal 2 damage.",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": [],
            "hero_power_dbf_id": None,
        },
        {
            "id": "TOKEN_01",
            "dbf_id": 30,
            "name": "Generated Token",
            "type": "MINION",
            "text": "Generated helper.",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": [],
            "hero_power_dbf_id": None,
        },
    ]

    context = build_card_data_context(
        deck_cards=deck_cards,
        collectible_cards=collectible,
        full_cards=full,
    )

    companions = context["companion_source_records"]
    assert companions["HP_01"]["type"] == "HERO_POWER"
    assert companions["TOKEN_01"]["name"] == "Generated Token"
    assert context["card_data_intake_report"]["summary"]["companion_records"] == 2


def test_card_data_context_keeps_missing_companions_non_blocking():
    deck_cards = [{"card_id": "HERO_01", "dbf_id": 10, "count": 1}]
    collectible = [
        {
            "id": "HERO_01",
            "dbf_id": 10,
            "name": "Hero",
            "type": "HERO",
            "text": "",
            "mechanics": [],
            "referenced_tags": [],
            "entourage": ["MISSING_TOKEN"],
            "hero_power_dbf_id": 999,
        }
    ]

    context = build_card_data_context(
        deck_cards=deck_cards,
        collectible_cards=collectible,
        full_cards=[],
    )

    report = context["card_data_intake_report"]
    assert report["non_blocking"] is True
    assert report["summary"]["missing_companion_records"] == 2
    assert report["warnings"][0]["reason"] in {"missing_companion_card", "missing_companion_dbf_id"}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_card_data_intake.py -q
```

Expected: fail because `hsconfig.card_data_intake` does not exist.

- [ ] **Step 3: Implement card data intake module**

Create `src/hsconfig/card_data_intake.py`:

```python
from __future__ import annotations

from typing import Any

from hsconfig.hearthstonejson import index_cards_by_id, normalize_card_row


COMPANION_ID_KEYS = ("entourage", "child_ids", "childIds")
COMPANION_DBF_KEYS = ("hero_power_dbf_id", "heroPowerDbfId")


def build_card_data_context(
    *,
    deck_cards: list[dict[str, Any]],
    collectible_cards: list[dict[str, Any]],
    full_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    collectible_index = index_cards_by_id(collectible_cards)
    full_index = index_cards_by_id(full_cards)

    deck_source_records: dict[str, dict[str, Any]] = {}
    companion_source_records: dict[str, dict[str, Any]] = {}
    missing_deck_cards: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for deck_card in deck_cards:
        card_id = str(deck_card.get("card_id", ""))
        dbf_id = deck_card.get("dbf_id")
        source = collectible_index.get(card_id) or collectible_index.get(str(dbf_id))
        if source is None:
            missing_deck_cards.append({"card_id": card_id, "dbf_id": dbf_id})
            warnings.append({"reason": "missing_collectible_deck_card", "card_id": card_id})
            continue
        normalized = normalize_card_row(source)
        deck_source_records[card_id] = normalized
        _collect_companions(
            source=normalized,
            full_index=full_index,
            companion_source_records=companion_source_records,
            warnings=warnings,
        )

    missing_companions = [
        warning
        for warning in warnings
        if warning["reason"] in {"missing_companion_card", "missing_companion_dbf_id"}
    ]
    return {
        "deck_source_records": deck_source_records,
        "companion_source_records": companion_source_records,
        "card_data_intake_report": {
            "schema_version": 1,
            "non_blocking": True,
            "warnings": warnings,
            "missing_deck_cards": missing_deck_cards,
            "summary": {
                "deck_cards": len(deck_cards),
                "matched_deck_cards": len(deck_source_records),
                "missing_deck_cards": len(missing_deck_cards),
                "companion_records": len(companion_source_records),
                "missing_companion_records": len(missing_companions),
            },
        },
    }


def _collect_companions(
    *,
    source: dict[str, Any],
    full_index: dict[str, dict[str, Any]],
    companion_source_records: dict[str, dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    for key in COMPANION_ID_KEYS:
        for companion_id in source.get(key, []) or []:
            companion = full_index.get(str(companion_id))
            if companion is None:
                warnings.append({"reason": "missing_companion_card", "card_id": str(companion_id)})
                continue
            normalized = normalize_card_row(companion)
            companion_source_records[normalized["id"]] = normalized

    for key in COMPANION_DBF_KEYS:
        dbf_id = source.get(key)
        if dbf_id in (None, ""):
            continue
        companion = full_index.get(str(dbf_id))
        if companion is None:
            warnings.append({"reason": "missing_companion_dbf_id", "dbf_id": int(dbf_id)})
            continue
        normalized = normalize_card_row(companion)
        companion_source_records[normalized["id"]] = normalized
```

- [ ] **Step 4: Add collectible fetch helper**

Modify `src/hsconfig/hearthstonejson.py`:

```python
HEARTHSTONEJSON_LATEST_ENUS_COLLECTIBLE_CARDS_URL = (
    "https://api.hearthstonejson.com/v1/latest/enUS/cards.collectible.json"
)
```

Add:

```python
def fetch_latest_collectible_cards(timeout: float = 10.0) -> list[dict[str, Any]]:
    request = Request(
        HEARTHSTONEJSON_LATEST_ENUS_COLLECTIBLE_CARDS_URL,
        headers={"User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise ValueError("HearthstoneJSON latest collectible cards response must be a list")
    return [normalize_card_row(row) for row in payload]
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest tests/test_card_data_intake.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/hsconfig/card_data_intake.py src/hsconfig/hearthstonejson.py tests/test_card_data_intake.py
git commit -m "feat: add hearthstone card data intake"
```

---

### Task 3: Thread Intake Into Research Context Without Blocking

**Files:**
- Modify: `src/hsconfig/commands/source_workflow.py`
- Modify: `src/hsconfig/card_metadata.py`
- Test: `tests/test_configure_cli.py`
- Test: `tests/test_full_chain_cli_integration.py`

**Interfaces:**
- Consumes:
  - `build_card_data_context(...)`
  - existing decoded deck cards from `load_cards(...)`
- Produces:
  - `card_data_intake_report.json` in `research-deck` output directory
  - `semantic_report["cards"]` enriched with companion-aware source records when available

- [ ] **Step 1: Write failing research output assertion**

Add to `tests/test_configure_cli.py`:

```python
def test_configure_writes_card_data_intake_report(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_collectible_cards", lambda timeout=10.0: [])

    out = tmp_path / "configure"

    assert main(
        [
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
        ]
    ) == 0

    report = _read_json(out / "03_research" / "card_data_intake_report.json")
    assert report["non_blocking"] is True
    assert "summary" in report
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests/test_configure_cli.py::test_configure_writes_card_data_intake_report -q
```

Expected: fail because the report is not written.

- [ ] **Step 3: Import intake helpers in source workflow**

Modify `src/hsconfig/commands/source_workflow.py` imports:

```python
from hsconfig.card_data_intake import build_card_data_context
from hsconfig.hearthstonejson import fetch_latest_cards, fetch_latest_collectible_cards
```

Replace the old single `fetch_latest_cards` import with the combined import above.

- [ ] **Step 4: Build card data context in `_build_research_context`**

In `_build_research_context`, after `cards = cards_payload["cards"]`, add:

```python
    collectible_cards: list[dict[str, Any]] = []
    full_cards: list[dict[str, Any]] = []
    card_data_fetch_error: str | None = None
    semantic_fetch_skipped = bool(getattr(args, "skip_semantic_fetch", False))
    if not semantic_fetch_skipped:
        try:
            collectible_cards = fetch_latest_collectible_cards(timeout=10.0)
            full_cards = fetch_latest_cards(timeout=10.0)
        except Exception as exc:
            card_data_fetch_error = str(exc)
```

Then replace the existing `source_records = source_records_from_cards(cards)` with:

```python
    card_data_context = build_card_data_context(
        deck_cards=cards,
        collectible_cards=collectible_cards,
        full_cards=full_cards,
    )
    source_records = {
        **source_records_from_cards(cards),
        **card_data_context["deck_source_records"],
        **card_data_context["companion_source_records"],
    }
    if card_data_fetch_error is not None:
        card_data_context["card_data_intake_report"]["warnings"].append(
            {"reason": "hearthstonejson_fetch_failed", "message": card_data_fetch_error}
        )
```

Remove the later duplicate `semantic_fetch_skipped`, `hearthstonejson_cards`, and `semantic_fetch_error` fetch block. Replace it with:

```python
    hearthstonejson_cards = [*collectible_cards, *full_cards]
    semantic_fetch_error = card_data_fetch_error
```

Add to the returned context:

```python
        "card_data_intake_report": card_data_context["card_data_intake_report"],
```

- [ ] **Step 5: Write the report in `research_deck_payload`**

In `research_deck_payload`, after writing `identity_gap_report.json`, add:

```python
    write_json(out / "card_data_intake_report.json", context["card_data_intake_report"])
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_configure_cli.py tests/test_full_chain_cli_integration.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add src/hsconfig/commands/source_workflow.py src/hsconfig/card_metadata.py tests/test_configure_cli.py tests/test_full_chain_cli_integration.py
git commit -m "feat: thread card data intake into research workflow"
```

---

### Task 4: Harden Mechanic Drift Rule Map

**Files:**
- Modify: `src/hsconfig/mechanic_drift.py`
- Modify: `src/hsconfig/mechanic_support.py`
- Test: `tests/test_mechanic_drift.py`
- Test: `tests/test_mechanic_support.py`

**Interfaces:**
- Consumes:
  - normalized card rows with `mechanics`, `referenced_tags`, `text`, `type`
- Produces:
  - stable report-only detection for text/rule mechanics:
    - `tourist`
    - `kindred`
    - `rewind`
    - `prepare`
    - `imbue`
    - `starship`

- [ ] **Step 1: Write failing drift tests**

Add to `tests/test_mechanic_drift.py`:

```python
from hsconfig.mechanic_drift import build_mechanic_drift_report


def test_text_only_new_mechanics_are_visible_and_non_blocking():
    report = build_mechanic_drift_report(
        [
            {"id": "T1", "type": "MINION", "text": "Kindred: Gain +1/+1.", "mechanics": []},
            {"id": "T2", "type": "SPELL", "text": "Rewind this.", "mechanics": []},
            {"id": "T3", "type": "SPELL", "text": "Prepare a spell.", "mechanics": []},
            {"id": "T4", "type": "MINION", "text": "Tourist", "mechanics": []},
        ]
    )

    assert report["non_blocking"] is True
    assert {"kindred", "rewind", "prepare", "tourist"} <= set(report["text_only_mechanics"])
    for mechanic in ("kindred", "rewind", "prepare", "tourist"):
        assert report["support_by_mechanic"][mechanic]["support_level"] == "warning_only"


def test_starship_and_imbue_are_detected_from_referenced_tags():
    report = build_mechanic_drift_report(
        [
            {"id": "S1", "type": "MINION", "text": "", "mechanics": ["STARSHIP_PIECE"], "referencedTags": ["STARSHIP"]},
            {"id": "I1", "type": "HERO_POWER", "text": "", "mechanics": [], "referencedTags": ["IMBUE"]},
        ]
    )

    assert "starship" in report["mechanics"]
    assert "imbue" in report["mechanics"]
    assert report["support_by_mechanic"]["starship"]["support_level"] == "warning_only"
    assert report["support_by_mechanic"]["imbue"]["support_level"] == "partial"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_mechanic_drift.py::test_text_only_new_mechanics_are_visible_and_non_blocking tests/test_mechanic_drift.py::test_starship_and_imbue_are_detected_from_referenced_tags -q
```

Expected: fail if `prepare` or `STARSHIP_PIECE` are not mapped correctly.

- [ ] **Step 3: Add rule entries**

Modify `src/hsconfig/mechanic_support.py`:

```python
    "prepare": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Prepare is a pre-play setup action with no documented normal-path VisionAI runtime block.",
        "proof_basis": "text drift visibility only; no documented VisionAI prepare action surface",
        "never_autopatch_reason": "Do not lower Prepare into card values without exact public VisionAI support.",
    },
```

Add aliases:

```python
    "starship_piece": "starship",
    "starship_piece_tag": "starship",
    "prepare_keyword": "prepare",
```

Modify `src/hsconfig/mechanic_drift.py`:

```python
    "prepare": ("prepare",),
```

Update `_canonical_token` only if needed so `STARSHIP_PIECE` becomes `starship` through the alias path.

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_mechanic_drift.py tests/test_mechanic_support.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/hsconfig/mechanic_drift.py src/hsconfig/mechanic_support.py tests/test_mechanic_drift.py tests/test_mechanic_support.py
git commit -m "feat: harden modern mechanic drift visibility"
```

---

### Task 5: Make `configure` the Operator-Facing Normal Path

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/universal-wild-no-block-contract.md`
- Modify: `README.md`
- Modify: installed/repo skill source used by `scripts/sync_installed_skill.py`
- Test: `tests/test_docs_active_path.py`
- Test: `tests/test_skill_sync.py`
- Test: `tests/test_cli_help.py`

**Interfaces:**
- Consumes:
  - `hsconfig configure`
  - `reports/operator_summary.json`
- Produces:
  - updated operator path language:
    - preferred path: `configure`
    - lower-level path: `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`

- [ ] **Step 1: Write failing docs test**

Add to `tests/test_docs_active_path.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_operator_docs_name_configure_as_preferred_normal_path():
    text = (ROOT / "docs" / "operator" / "README.md").read_text(encoding="utf-8")

    assert "Preferred normal path" in text
    assert "hsconfig configure" in text
    assert "source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply" in text
    assert "HSConfig is pre-run only" in text
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py::test_operator_docs_name_configure_as_preferred_normal_path -q
```

Expected: fail until docs are updated.

- [ ] **Step 3: Update operator guide**

Modify `docs/operator/README.md` top section to include:

````markdown
## Preferred Normal Path

Use `hsconfig configure` for normal operation:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --json
```

This command runs the lower-level pre-run chain, writes a validated package, and leaves the final decision in `outputs/<DeckName>/04_package/reports/operator_summary.json`.

The lower-level normal path remains available for inspected work:

`source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`
````

Keep the existing pre-run-only and no-HSTuner text.

- [ ] **Step 4: Update universal no-block contract**

Add a section to `docs/operator/universal-wild-no-block-contract.md`:

```markdown
## Card Data Intake

HSConfig uses a three-layer intake policy:

- Layer 1: deck-card identity is gated through collectible deck-card metadata.
- Layer 2: directly referenced companion entities are enriched from full `cards.json` metadata when available.
- Layer 3: text-only or rule-only mechanics stay visible in mechanic-drift reports.

Layer 2 and Layer 3 gaps are warning-only. They must not block `load_safe_apply` when the package is otherwise `VALID_PACKAGE`.
```

- [ ] **Step 5: Update skill source and sync**

Find the repo skill source used by `scripts/sync_installed_skill.py`:

```powershell
python scripts/sync_installed_skill.py --check
```

If it reports drift or points to a repo source, update the source skill text to say:

```markdown
Normal workflow:

1. Prefer `hsconfig configure ...` for normal operation.
2. Use lower-level commands only when inspecting a stage:
   `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`.
3. Open `reports/operator_summary.json` first.
```

Then run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected: check passes.

- [ ] **Step 6: Run docs and skill tests**

Run:

```powershell
python -m pytest tests/test_docs_active_path.py tests/test_skill_sync.py tests/test_cli_help.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add README.md docs/operator/README.md docs/operator/universal-wild-no-block-contract.md .codex/skills/hsconfig/SKILL.md tests/test_docs_active_path.py tests/test_skill_sync.py tests/test_cli_help.py
git commit -m "docs: make configure the preferred hsconfig path"
```

If `.codex/skills/hsconfig/SKILL.md` is not tracked in this repo, omit it from `git add` and stage the tracked skill source file reported by `scripts/sync_installed_skill.py`.

---

### Task 6: Prove No-Block Configure Across Representative Decks

**Files:**
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Modify: `tests/test_configure_cli.py`
- Test data: reuse current deck matrix and user-provided deck codes already represented in repo tests.

**Interfaces:**
- Consumes:
  - `hsconfig configure`
  - `reports/operator_summary.json`
- Produces:
  - proof that every valid listed deck reaches `VALID_PACKAGE` and `load_safe_apply`
  - proof that warning-only mechanic gaps do not block runtime apply

- [ ] **Step 1: Add configure matrix test**

Add to `tests/test_universal_wild_no_block_matrix.py`:

```python
def test_configure_path_preserves_no_block_contract_for_matrix(tmp_path, monkeypatch):
    from hsconfig.cli import main

    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_collectible_cards", lambda timeout=10.0: [])

    for row in UNIVERSAL_WILD_NO_BLOCK_DECKS:
        out = tmp_path / row["deck_name"]
        assert main(
            [
                "configure",
                "--deck-name",
                row["deck_name"],
                "--deck-code",
                row["deck_code"],
                "--runtime-root",
                str(tmp_path / "runtime"),
                "--out",
                str(out),
                "--json",
            ]
        ) == 0

        operator = json.loads(
            (out / "04_package" / "reports" / "operator_summary.json").read_text(
                encoding="utf-8"
            )
        )
        assert operator["technical_status"] == "VALID_PACKAGE"
        assert operator["runtime_load_safe"] is True
        assert operator["runtime_apply_mode"] == "load_safe_apply"
        assert operator["mechanic_visibility_summary"]["non_blocking"] is True
```

Use the actual matrix constant name in the file. If the current file uses a different constant, adapt the test to that exact constant.

- [ ] **Step 2: Run matrix test and verify failure or pass**

Run:

```powershell
python -m pytest tests/test_universal_wild_no_block_matrix.py::test_configure_path_preserves_no_block_contract_for_matrix -q
```

Expected: pass after Task 1; if it fails, fix only integration issues in `configure`, not the no-block policy.

- [ ] **Step 3: Add apply-gate assertion for warning packages**

Add to `tests/test_configure_cli.py`:

```python
def test_configure_warning_package_can_fake_apply(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr("hsconfig.commands.source_workflow.fetch_latest_collectible_cards", lambda timeout=10.0: [])

    out = tmp_path / "configure"
    runtime_root = tmp_path / "runtime"

    assert main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--json",
        ]
    ) == 0

    assert main(
        [
            "apply",
            "--package",
            str(out / "04_package"),
            "--runtime-root",
            str(runtime_root),
            "--fake",
            "--json",
        ]
    ) == 0
```

- [ ] **Step 4: Run focused configure/apply tests**

Run:

```powershell
python -m pytest tests/test_configure_cli.py tests/test_universal_wild_no_block_matrix.py tests/test_apply_gate.py tests/test_runtime_apply.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_universal_wild_no_block_matrix.py tests/test_configure_cli.py
git commit -m "test: prove configure no-block matrix"
```

---

### Task 7: Final Verification, Skill Sync, and GitHub Update

**Files:**
- Modify only if tests reveal small wording/sync drift:
  - `README.md`
  - `docs/operator/README.md`
  - `docs/operator/universal-wild-no-block-contract.md`
  - skill source used by `scripts/sync_installed_skill.py`

**Interfaces:**
- Consumes all previous tasks.
- Produces:
  - green targeted tests
  - green full suite
  - clean git status
  - pushed `origin/main`

- [ ] **Step 1: Run skill sync**

Run:

```powershell
python scripts/sync_installed_skill.py --check
```

Expected: pass. If it fails, run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

- [ ] **Step 2: Run focused suite**

Run:

```powershell
python -m pytest tests/test_configure_cli.py tests/test_card_data_intake.py tests/test_mechanic_drift.py tests/test_mechanic_support.py tests/test_universal_wild_no_block_matrix.py tests/test_apply_gate.py tests/test_runtime_apply.py tests/test_cli_help.py tests/test_docs_active_path.py tests/test_skill_sync.py -q
```

Expected: pass.

- [ ] **Step 3: Run broad suite**

Run:

```powershell
python -m pytest -q
```

Expected: pass. Existing skips are acceptable if they are pre-existing and documented by pytest output.

- [ ] **Step 4: Search for forbidden scope creep**

Run:

```powershell
rg -n "replay|winrate|HSTuner|Power\\.log|candidate promotion|post-run|runtime log" src docs README.md tests -g "!docs/research/**" -g "!docs/superpowers/plans/**"
```

Expected: no new normal-path claims that HSConfig parses games, inspects winrate, tunes after games, or promotes candidates. Existing negative-scope text is acceptable.

- [ ] **Step 5: Confirm runtime surface boundary**

Run:

```powershell
rg -n "Presume\\.json|Concede\\.json" src docs tests README.md -g "!docs/research/**" -g "!docs/superpowers/plans/**"
```

Expected: only policy text and tests that keep these surfaces out of the normal path. No generator emits them.

- [ ] **Step 6: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: all intended files changed, no raw logs, no runtime evidence, no temp outputs.

- [ ] **Step 7: Final commit if needed**

If docs or sync changed after Task 6, run:

```powershell
git add README.md docs/operator/README.md docs/operator/universal-wild-no-block-contract.md .codex/skills/hsconfig/SKILL.md
git commit -m "docs: align hsconfig configure workflow"
```

Omit untracked paths that do not exist or are not part of this repo.

- [ ] **Step 8: Push**

Run:

```powershell
git push origin main
```

Expected: push succeeds.

---

## Self-Review

**Spec coverage:** The plan implements the recommendation: one-command configure path, collectible-gated plus full-feed companion card-data intake, mechanic-drift hardening, no-block warnings, docs/skill alignment, representative matrix proof, and final GitHub update.

**Placeholder scan:** The plan intentionally avoids placeholder steps. The only conditional instructions are operational safeguards for file paths that may or may not be tracked by git.

**Type consistency:** New interfaces are consistently named:

- `run_configure_command(args: argparse.Namespace) -> int`
- `configure_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]`
- `build_card_data_context(...) -> dict[str, Any]`

**Scope check:** The plan does not add replay parsing, winrate, HSTuner, post-run tuning, `Presume.json`, or `Concede.json` generation. It keeps HSConfig narrow and pre-run.
