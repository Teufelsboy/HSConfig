# HSConfig Source-Depth Closure Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig reach strong, source-backed initial CustomConfig quality for the representative deck set without widening the skill into HSTuner-style replay, winrate, or post-game tuning.

**Architecture:** Keep the normal path narrow: `source_documents.json` -> `hsconfig research-deck` -> `hsconfig prepare` -> `reports/operator_summary.json` -> optional `hsconfig apply`. Improve source depth, evidence verification, runtime-surface lowering, and skill deployment sync so `SOURCE_BACKED_STRONG` remains strict but becomes reachable. Use ShadowPriest as the first proof, then close all 11 representative deck fixtures.

**Tech Stack:** Python 3.11+, `pytest`, `hearthstone>=9.0.0`, HearthRanger VisionAI JSON surfaces, HearthSim deckstrings, Hearthstone card metadata through existing HSConfig modules.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Keep HSConfig separate from HSTuner.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, runtime-log parsing, or post-run tuning.
- Normal runtime outputs are `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when a concrete exact combo sequence exists.
- Do not emit `Presume.json` or `Concede.json` in the normal path; keep them legacy/gated validator-supported surfaces only.
- Keep exact deck and CardID identity.
- Keep full `GlobalValues.json` key profiling.
- Every deck card must be represented in the gameplan contract and visible in per-card readiness.
- Do not relax `SOURCE_BACKED_STRONG` requirements to hide gaps. Close gaps with better source claims, static semantics, or documented runtime-surface logic.
- `operator_summary.json` is the canonical operator gate.
- Use `claim_can_lower_to_runtime()` as the mandatory runtime-lowering gate for every compiler.
- Generated runtime packages belong under `outputs/` or temp folders and are ignored by git.
- Do not commit raw runtime evidence, private logs, HearthRanger games, HDT exports, or local runtime packages.

---

## Current Evidence

Research-deep audit package:

- `docs/research/2026-07-07-hsconfig-skill-audit/outline.yaml`
- `docs/research/2026-07-07-hsconfig-skill-audit/fields.yaml`
- `docs/research/2026-07-07-hsconfig-skill-audit/results/*.json`

Verified baseline before this plan:

- `python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-07-hsconfig-skill-audit\fields.yaml -j docs\research\2026-07-07-hsconfig-skill-audit\results\HearthRanger_VisionAI_Runtime_Surface_Contract.json docs\research\2026-07-07-hsconfig-skill-audit\results\Hearthstone_Card_Identity_And_Static_Semantics.json docs\research\2026-07-07-hsconfig-skill-audit\results\Source-Backed_Guide_Claim_Depth.json docs\research\2026-07-07-hsconfig-skill-audit\results\Multi-Archetype_Deck_Coverage_Matrix.json docs\research\2026-07-07-hsconfig-skill-audit\results\Lean_Skill_Boundary_And_Operator_UX.json`
- Expected: `Validation passed: 5/5`
- `python -m pytest tests/test_skill_files.py tests/test_archetype_fixture_matrix.py tests/test_archetype_source_fixtures.py tests/test_archetype_fixture_e2e.py tests/test_research_audit_schema.py -q`
- Expected: all selected tests pass.

ShadowPriest proof gap from a current temp prepare run:

- `technical_status=VALID_PACKAGE`
- `semantic_status=VALID_BUT_NOT_GUIDE_STRONG`
- `next_action=IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY`
- `cards_needing_guide_claims=9`
- `cards_needing_runtime_surface=3`
- `generic_low_confidence=9`
- `has_globalvalues=True`
- `has_mulligan=True`
- `has_presume=False`
- `has_concede=False`

ShadowPriest cards that need guide claims:

- `CFM_637` Patches the Pirate
- `DRG_056` Parachute Brigand
- `REV_290` Cathedral of Atonement
- `SCH_514` Raise Dead
- `TOY_381` Papercraft Angel
- `TOY_518`
- `VAC_512`
- `WON_065`
- `YOD_032`

ShadowPriest cards that need runtime-surface closure:

- `NX2_019` Mind Sear
- `SW_446` Voidtouched Attendant
- `SW_448` Darkbishop Benedictus

---

## File Structure

### Skill Sync

- Create: `scripts/sync_installed_skill.py`
  - Copies `.agents/skills/hsconfig` into `C:\Users\darbo\.codex\skills\hsconfig`.
  - Supports `--check` to compare content without writing.
  - Supports `--install-root` for tests using temp dirs.
- Create: `tests/test_skill_sync.py`
  - Verifies `--check` detects matching and drifting skill folders.
  - Verifies copy mode replaces stale installed files.
- Modify: `README.md`
  - Add one short maintainer command for local skill sync.
- Modify: `tests/test_skill_files.py`
  - Assert repo skill docs mention the sync command or installed-skill drift check.

### Source Evidence Verification

- Create: `src/hsconfig/source_evidence_verifier.py`
  - New functions:
    - `verify_source_documents(source_documents: list[dict]) -> dict`
    - `source_ref_is_public_https(value: object) -> bool`
    - `claim_evidence_status(claim: dict, document: dict) -> dict`
  - No network fetch in verifier. It validates structure, public source refs, evidence fields, source families, claim specificity, and runtime lowering hints.
- Create: `tests/test_source_evidence_verifier.py`
  - Unit tests for public-source validation, low-confidence rejection, runtime-block validation, and report shape.
- Modify: `src/hsconfig/cli.py`
  - Write `reports/source_evidence_verification_report.json` during `research-deck`, `prepare`, and `build` when source documents or guide sources are available.
- Modify: `tests/test_prepare_cli.py`
  - Assert the new report exists and is referenced by operator warnings/blockers when evidence is weak.
- Modify: `tests/test_research_deck_cli.py`
  - Assert `research-deck --source-documents-json` writes the evidence report.

### Source Depth And Operator Truth

- Modify: `src/hsconfig/guide_source_depth.py`
  - Add explicit `source_depth_status`.
  - Distinguish lowerable guide/static claims from report-only claims in the primary status.
  - Avoid positive depth labels when low-confidence or report-only claims dominate.
- Modify: `src/hsconfig/operator_summary.py`
  - Keep `operator_summary.json` as final truth.
  - Add `source_evidence_summary` into `guide_strength_summary` when available.
  - Keep `SOURCE_BACKED_STRONG` strict.
- Modify: `tests/test_guide_source_depth.py`
  - Add tests for report-only-heavy bundles.
  - Add tests for all-card lowerable bundles.
- Modify: `tests/test_operator_summary.py`
  - Assert source-evidence failures cannot produce `SOURCE_BACKED_STRONG`.

### Runtime Surface Closure

- Modify: `src/hsconfig/card_behavior_surface_router.py`
  - Add exact routing for `hero_power_transform`, `known_bad_pattern`, `discover_choice`, and `choose_one_choice` where documented CardID blocks exist.
  - Keep unsupported or uncertain cases in `suppressed`.
- Modify: `src/hsconfig/config_readiness.py`
  - Add role-aware sufficiency logic so documented non-CardID surfaces can satisfy a card when that is the correct runtime surface.
  - Example: `hero_power_transform` may be satisfied by `GlobalValues.json` plus hero-power expectation when no meaningful per-card CardID surface exists.
- Modify: `tests/test_card_behavior_router.py`
  - Add routing tests for Hero Power use, burn/face targeting, Discover option resolution, and report-only bad patterns.
- Modify: `tests/test_config_readiness.py`
  - Assert `hero_power_transform` plus GlobalValues can close readiness only when source-backed and documented.
  - Assert generic low-confidence cards still need guide claims.

### ShadowPriest Closure

- Modify: `tests/fixtures/source_documents_shadowpriest_strong.json`
  - Add current, public HTTPS-backed claims for the 9 guide-claim gaps.
  - Add concrete lowerable claims for `NX2_019`, `SW_446`, and `SW_448` where a documented runtime surface exists.
  - Keep any unsupported claim as explicit report-only with `source_confidence=low` and a clear reason.
- Modify: `tests/test_archetype_source_fixtures.py`
  - Add ShadowPriest assertions for no generic-low-confidence source rows in the core fixture.
  - Assert Mind Sear, Voidtouched Attendant, and Darkbishop Benedictus each have an explicit runtime or documented non-CardID sufficiency route.
- Modify: `tests/test_archetype_fixture_e2e.py`
  - Add `test_shadowpriest_fixture_reaches_source_backed_strong`.

### Eleven-Deck Closure

- Create:
  - `tests/fixtures/source_documents_ctapaladin_strong.json`
  - `tests/fixtures/source_documents_piraterogue_strong.json`
  - `tests/fixtures/source_documents_treantdruid_strong.json`
  - `tests/fixtures/source_documents_mechpala_strong.json`
  - `tests/fixtures/source_documents_boarlock_strong.json`
  - `tests/fixtures/source_documents_piratedh_strong.json`
- Modify: `docs/operator/archetype-fixture-matrix.json`
  - Promote the six second-wave rows to `core_source_backed_fixture` only after each fixture passes.
- Modify: `tests/test_archetype_fixture_matrix.py`
  - Update `CORE_FIXTURES` to all 11 deck names after fixtures exist.
- Modify: `tests/test_archetype_source_fixtures.py`
  - Extend `FIXTURES` to all 11 decks.
  - Add archetype-specific assertions for each new deck.
- Modify: `tests/test_archetype_fixture_e2e.py`
  - Extend `DECKS` to all 11 decks.
  - Assert each deck has `VALID_PACKAGE` and at least one meaningful runtime surface.

### Docs And Legacy Surface Isolation

- Modify: `README.md`
  - Keep normal path short.
  - Add “Strong config checklist” pointing to `operator_summary.json`, not all reports.
- Modify: `.agents/skills/hsconfig/SKILL.md`
  - Keep installed/runtime-facing instructions in sync with current repo guidance.
- Modify:
  - `.agents/skills/hsconfig/references/workflow.md`
  - `.agents/skills/hsconfig/references/visionai-surfaces.md`
  - `.agents/skills/hsconfig/references/guide-research-policy.md`
  - `.agents/skills/hsconfig/references/globalvalues-policy.md`
  - `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `tests/test_skill_files.py`
  - Check concepts, not duplicated paragraphs.
  - Ensure `Presume.json` / `Concede.json` remain absent from normal workflow docs.

---

## Task 1: Installed Skill Sync And Drift Check

**Files:**

- Create: `scripts/sync_installed_skill.py`
- Create: `tests/test_skill_sync.py`
- Modify: `README.md`
- Modify: `tests/test_skill_files.py`

**Interfaces:**

- Consumes: repo skill folder `.agents/skills/hsconfig`.
- Produces:
  - CLI script `python scripts/sync_installed_skill.py [--check] [--install-root PATH]`.
  - Exit code `0` when installed skill matches.
  - Exit code `1` when `--check` finds drift.

- [ ] **Step 1: Write failing tests for sync behavior**

Add `tests/test_skill_sync.py`:

```python
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/sync_installed_skill.py")


def test_skill_sync_check_passes_when_installed_copy_matches(tmp_path: Path):
    install_root = tmp_path / "codex" / "skills"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    check = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    assert "in sync" in check.stdout.lower()


def test_skill_sync_check_fails_when_installed_copy_drifts(tmp_path: Path):
    install_root = tmp_path / "codex" / "skills"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    installed_skill = install_root / "hsconfig" / "SKILL.md"
    installed_skill.write_text(installed_skill.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")

    check = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert check.returncode == 1
    assert "drift" in (check.stdout + check.stderr).lower()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_skill_sync.py -q
```

Expected:

```text
FAILED tests/test_skill_sync.py::test_skill_sync_check_passes_when_installed_copy_matches
```

because `scripts/sync_installed_skill.py` does not exist.

- [ ] **Step 3: Implement the sync script**

Create `scripts/sync_installed_skill.py`:

```python
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SKILL = REPO_ROOT / ".agents" / "skills" / "hsconfig"


def _default_install_root() -> Path:
    return Path.home() / ".codex" / "skills"


def _iter_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def folders_match(left: Path, right: Path) -> bool:
    if not left.exists() or not right.exists():
        return False
    left_files = [path.relative_to(left) for path in _iter_files(left)]
    right_files = [path.relative_to(right) for path in _iter_files(right)]
    if left_files != right_files:
        return False
    return all(filecmp.cmp(left / rel, right / rel, shallow=False) for rel in left_files)


def sync_skill(install_root: Path) -> Path:
    target = install_root / "hsconfig"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(SOURCE_SKILL, target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync repo HSConfig skill into the local Codex skill directory.")
    parser.add_argument("--check", action="store_true", help="Only check whether the installed skill matches.")
    parser.add_argument("--install-root", type=Path, default=_default_install_root())
    args = parser.parse_args(argv)

    target = args.install_root / "hsconfig"
    if args.check:
        if folders_match(SOURCE_SKILL, target):
            print(f"HSConfig skill is in sync: {target}")
            return 0
        print(f"HSConfig skill drift detected: {target}", file=sys.stderr)
        return 1

    synced = sync_skill(args.install_root)
    print(f"Synced HSConfig skill to {synced}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Update docs and doc tests**

In `README.md`, add this short maintainer line under the normal operator path:

```markdown
Maintainer sync: after changing `.agents/skills/hsconfig`, run `python scripts/sync_installed_skill.py --check`; if drift is expected, run `python scripts/sync_installed_skill.py`.
```

In `tests/test_skill_files.py`, add:

```python
def test_readme_documents_installed_skill_sync():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "scripts/sync_installed_skill.py --check" in text
    assert "scripts/sync_installed_skill.py" in text
```

- [ ] **Step 5: Run task tests**

Run:

```powershell
python -m pytest tests/test_skill_sync.py tests/test_skill_files.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add scripts/sync_installed_skill.py tests/test_skill_sync.py tests/test_skill_files.py README.md
git commit -m "chore: add hsconfig installed skill sync check"
```

---

## Task 2: Source Evidence Verifier

**Files:**

- Create: `src/hsconfig/source_evidence_verifier.py`
- Create: `tests/test_source_evidence_verifier.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_research_deck_cli.py`
- Modify: `tests/test_prepare_cli.py`

**Interfaces:**

- Consumes: source documents in the existing `--source-documents-json` shape.
- Produces: `verify_source_documents(source_documents: list[dict]) -> dict`.
- Produces report file: `reports/source_evidence_verification_report.json`.

- [ ] **Step 1: Write failing verifier unit tests**

Create `tests/test_source_evidence_verifier.py`:

```python
from hsconfig.source_evidence_verifier import (
    claim_evidence_status,
    source_ref_is_public_https,
    verify_source_documents,
)


def test_public_https_source_ref_checker():
    assert source_ref_is_public_https("https://example.com/guide")
    assert not source_ref_is_public_https("http://example.com/guide")
    assert not source_ref_is_public_https("fixture://local")
    assert not source_ref_is_public_https("https://localhost/guide")


def test_verifier_accepts_specific_public_source_document():
    report = verify_source_documents(
        [
            {
                "source_url": "https://example.com/shadowpriest-guide",
                "source_title": "ShadowPriest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T10:00:00Z",
                "claims": [
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["NX2_019"],
                        "stance": "prefer_enemy_hero",
                        "runtime_block": "BeforePlayCardBonus",
                        "evidence_text_short": "Mind Sear is used as face burn in aggressive Shadow Priest.",
                        "source_confidence": "high",
                    }
                ],
            }
        ]
    )

    assert report["status"] == "passed"
    assert report["summary"]["claim_count"] == 1
    assert report["summary"]["runtime_lowering_claims"] == 1
    assert report["warnings"] == []


def test_verifier_flags_weak_runtime_lowering_claim():
    document = {
        "source_url": "https://example.com/weak-guide",
        "source_title": "Weak Guide",
        "source_family": "guide",
        "retrieved_at": "2026-07-07T10:00:00Z",
        "claims": [
            {
                "claim_kind": "targeting_rule",
                "cards": [],
                "runtime_block": "NotARealBlock",
                "evidence_text_short": "",
                "source_confidence": "low",
            }
        ],
    }
    report = verify_source_documents([document])

    assert report["status"] == "warnings"
    reasons = {warning["reason"] for warning in report["warnings"]}
    assert "claim_missing_cards" in reasons
    assert "claim_missing_evidence_text_short" in reasons
    assert "unsupported_runtime_block" in reasons
    assert "low_confidence_runtime_lowering" in reasons


def test_claim_evidence_status_returns_claim_level_details():
    row = claim_evidence_status(
        {
            "claim_kind": "card_role",
            "cards": ["SW_446"],
            "evidence_text_short": "Voidtouched Attendant increases hero damage pressure.",
            "source_confidence": "medium",
        },
        {"source_url": "https://example.com/source", "source_family": "guide"},
    )

    assert row["claim_kind"] == "card_role"
    assert row["cards"] == ["SW_446"]
    assert row["status"] == "passed"
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
python -m pytest tests/test_source_evidence_verifier.py -q
```

Expected: import failure for `hsconfig.source_evidence_verifier`.

- [ ] **Step 3: Implement verifier**

Create `src/hsconfig/source_evidence_verifier.py`:

```python
from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS


PUBLIC_URL_SCHEMES = {"https"}
RUNTIME_HINT_KEYS = {"runtime_block", "runtime_value"}


def source_ref_is_public_https(value: object) -> bool:
    text = str(value).strip()
    parsed = urlsplit(text)
    if parsed.scheme not in PUBLIC_URL_SCHEMES or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
    )


def verify_source_documents(source_documents: list[dict]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    claim_rows: list[dict[str, Any]] = []
    claim_count = 0
    runtime_lowering_claims = 0

    for document_index, document in enumerate(source_documents, start=1):
        if not source_ref_is_public_https(document.get("source_url", "")):
            warnings.append(
                {
                    "reason": "source_url_not_public_https",
                    "document_index": document_index,
                    "source_url": str(document.get("source_url", "")),
                }
            )
        claims = document.get("claims", [])
        if not isinstance(claims, list) or not claims:
            warnings.append({"reason": "document_has_no_claims", "document_index": document_index})
            continue
        for claim_index, claim in enumerate(claims, start=1):
            claim_count += 1
            row = claim_evidence_status(claim, document)
            row["document_index"] = document_index
            row["claim_index"] = claim_index
            claim_rows.append(row)
            runtime_lowering_claims += int(row["has_runtime_lowering_hint"])
            warnings.extend(row["warnings"])

    return {
        "schema_version": 1,
        "status": "passed" if not warnings else "warnings",
        "summary": {
            "document_count": len(source_documents),
            "claim_count": claim_count,
            "runtime_lowering_claims": runtime_lowering_claims,
            "warnings_count": len(warnings),
        },
        "claims": claim_rows,
        "warnings": warnings,
    }


def claim_evidence_status(claim: dict, document: dict) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    claim_kind = str(claim.get("claim_kind", claim.get("claim_type", "")))
    cards = _cards(claim)
    has_runtime_lowering_hint = any(key in claim for key in RUNTIME_HINT_KEYS)

    if claim_kind not in SUPPORTED_ATOMIC_CLAIM_KINDS:
        warnings.append({"reason": "unsupported_claim_kind", "claim_kind": claim_kind})
    if not cards and claim_kind not in {"archetype", "gameplan_posture"}:
        warnings.append({"reason": "claim_missing_cards", "claim_kind": claim_kind})
    if not str(claim.get("evidence_text_short", "")).strip():
        warnings.append({"reason": "claim_missing_evidence_text_short", "claim_kind": claim_kind})
    runtime_block = claim.get("runtime_block")
    if runtime_block is not None and str(runtime_block) not in CARD_BEHAVIOR_BLOCKS:
        warnings.append(
            {
                "reason": "unsupported_runtime_block",
                "claim_kind": claim_kind,
                "runtime_block": str(runtime_block),
            }
        )
    if has_runtime_lowering_hint and str(claim.get("source_confidence", "")).lower() == "low":
        warnings.append({"reason": "low_confidence_runtime_lowering", "claim_kind": claim_kind})

    return {
        "claim_kind": claim_kind,
        "cards": cards,
        "source_family": str(document.get("source_family", "")),
        "source_url": str(document.get("source_url", "")),
        "has_runtime_lowering_hint": has_runtime_lowering_hint,
        "status": "passed" if not warnings else "warnings",
        "warnings": warnings,
    }


def _cards(claim: dict) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    if not isinstance(cards, list):
        return []
    return [str(card) for card in cards if str(card)]
```

- [ ] **Step 4: Integrate report into CLI**

In `src/hsconfig/cli.py`, import:

```python
from hsconfig.source_evidence_verifier import verify_source_documents
```

Where the CLI has source documents loaded for `research-deck`, `prepare`, or `build`, write:

```python
source_evidence_report = verify_source_documents(source_documents)
write_json(reports_dir / "source_evidence_verification_report.json", source_evidence_report)
```

If the local function names differ, use existing `write_json` and existing reports directory variables from `cli.py`; do not introduce a second IO helper.

- [ ] **Step 5: Add CLI report assertions**

In `tests/test_research_deck_cli.py`, add an assertion to the existing source-document CLI test:

```python
assert (out / "source_evidence_verification_report.json").exists()
```

In `tests/test_prepare_cli.py`, add an assertion to a source-document prepare test:

```python
assert (out / "reports" / "source_evidence_verification_report.json").exists()
```

- [ ] **Step 6: Run task tests**

```powershell
python -m pytest tests/test_source_evidence_verifier.py tests/test_research_deck_cli.py tests/test_prepare_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/source_evidence_verifier.py src/hsconfig/cli.py tests/test_source_evidence_verifier.py tests/test_research_deck_cli.py tests/test_prepare_cli.py
git commit -m "feat: verify structured guide source evidence"
```

---

## Task 3: Guide Depth And Operator Truth Tightening

**Files:**

- Modify: `src/hsconfig/guide_source_depth.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `tests/test_guide_source_depth.py`
- Modify: `tests/test_operator_summary.py`

**Interfaces:**

- Consumes: `guide_claim_bundle`, `config_readiness_report`, optional `source_evidence_verification_report`.
- Produces:
  - `guide_source_depth_report["source_depth_status"]`
  - `guide_source_depth_report["summary"]["lowerable_claims"]`
  - `guide_source_depth_report["summary"]["report_only_claims"]`
  - `operator_summary["guide_strength_summary"]["source_evidence_warnings"]`

- [ ] **Step 1: Add failing tests for report-only-heavy depth**

In `tests/test_guide_source_depth.py`, add:

```python
def test_report_only_claims_do_not_produce_source_backed_depth():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A"],
                    "claim_readiness": "explicit_low_confidence",
                    "trust_ceiling": "report_only",
                    "source_family": "guide",
                }
            ],
            "unsupported_claims": [],
        },
        config_readiness_report={
            "summary": {"total_cards": 1, "runtime_emitted": 0, "generic_low_confidence": 1},
            "cards": {
                "CARD_A": {
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                }
            },
        },
    )

    assert report["summary"]["lowerable_claims"] == 0
    assert report["summary"]["report_only_claims"] == 1
    assert report["source_depth_status"] == "needs_more_research"
```

In `tests/test_operator_summary.py`, add:

```python
def test_source_evidence_warnings_prevent_source_backed_strong():
    summary = build_operator_summary(
        deck_name="Deck",
        deck_code="AAEBAQ==",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "summary": {"claim_count": 3, "lowerable_claims": 3, "report_only_claims": 0},
            "source_evidence": {"warnings_count": 1},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/deck/GlobalValues.json"],
        claim_coverage_report={
            "summary": {"guide_backed": 1, "static_semantics_backfilled": 0},
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0},
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["guide_strength_summary"]["source_evidence_warnings"] == 1
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
python -m pytest tests/test_guide_source_depth.py::test_report_only_claims_do_not_produce_source_backed_depth tests/test_operator_summary.py::test_source_evidence_warnings_prevent_source_backed_strong -q
```

Expected: fail because `source_depth_status` and source evidence summary are not implemented.

- [ ] **Step 3: Implement source-depth status**

In `src/hsconfig/guide_source_depth.py`, include `source_depth_status` in the returned report:

```python
    source_depth_status = depth_status
    if lowerable_claims > 0 and report_only_claims == 0 and not warnings:
        source_depth_status = "source_backed"
    if lowerable_claims == 0 or cards_needing_guide_claims > 0:
        source_depth_status = "needs_more_research"
```

Return both fields:

```python
        "depth_status": depth_status,
        "source_depth_status": source_depth_status,
```

- [ ] **Step 4: Thread source evidence into operator summary**

In `src/hsconfig/operator_summary.py`, update `_semantic_status()` and `_guide_strength_summary()` to read:

```python
source_evidence = guide_source_depth.get("source_evidence", {}) if isinstance(guide_source_depth, dict) else {}
source_evidence_warnings = _int_value(source_evidence.get("warnings_count", 0))
```

Add `and source_evidence_warnings == 0` to the `SOURCE_BACKED_STRONG` condition.

Add this field to `guide_strength_summary`:

```python
"source_evidence_warnings": source_evidence_warnings,
```

- [ ] **Step 5: Run task tests**

```powershell
python -m pytest tests/test_guide_source_depth.py tests/test_operator_summary.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/guide_source_depth.py src/hsconfig/operator_summary.py tests/test_guide_source_depth.py tests/test_operator_summary.py
git commit -m "fix: align guide depth labels with source evidence"
```

---

## Task 4: Runtime Surface Closure For Source-Backed Mechanics

**Files:**

- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_config_readiness.py`

**Interfaces:**

- Consumes: normalized claims after `claim_can_lower_to_runtime()`.
- Produces: card behavior plan rows with `meaningful_runtime_surface=true` only when a documented VisionAI surface is used.
- Produces readiness closures for cards whose correct runtime surface is not a per-card CardID file.

- [ ] **Step 1: Add failing CardID routing tests**

In `tests/test_card_behavior_router.py`, add:

```python
def test_hero_power_transform_claim_routes_to_hero_power_surface():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_darkbishop",
                "claim_kind": "hero_power_transform",
                "cards": ["SW_448"],
                "claim_readiness": "source_backed_static_semantics",
                "stance": "shadow_hero_power_pressure",
                "runtime_block": "BeforeUseHeroPowerBonus",
                "runtime_value": "8",
                "condition": "*",
            }
        ]
    )

    assert plan["suppressed"] == []
    assert plan["rows"][0]["card_id"] == "SW_448"
    assert plan["rows"][0]["behavior_block"] == "BeforeUseHeroPowerBonus"
    assert plan["rows"][0]["meaningful_runtime_surface"] is True


def test_known_bad_pattern_stays_report_only_without_documented_block():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_bad",
                "claim_kind": "known_bad_pattern",
                "cards": ["CARD_A"],
                "claim_readiness": "guide_backed",
                "stance": "do_not_target_enemy_minion",
                "condition": "*",
            }
        ]
    )

    assert plan["rows"] == []
    assert plan["suppressed"][0]["reason"] == "no_documented_card_behavior_surface"
```

- [ ] **Step 2: Add failing readiness tests**

In `tests/test_config_readiness.py`, add:

```python
def test_source_backed_hero_power_transform_can_be_satisfied_by_globalvalues():
    report = build_config_readiness_report(
        deck_identity={"deck_name": "Deck", "cards": [{"card_id": "SW_448", "name": "Darkbishop Benedictus"}]},
        claim_coverage={"uncovered_cards": []},
        gameplan_contract={
            "deck_name": "Deck",
            "cards": {
                "SW_448": {
                    "card_id": "SW_448",
                    "name": "Darkbishop Benedictus",
                    "coverage_status": "source_backed_static_semantics",
                    "roles": ["hero_power_transform"],
                }
            },
            "hero_power_expectations": [{"source_card_id": "SW_448"}],
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": [{"key": "MyHeroPowerValue"}]},
        emitted_cardid_files=[],
    )

    row = report["cards"]["SW_448"]
    assert row["readiness_lane"] == "globalvalues_only"
    assert row["first_missing_link"] == "none"
```

- [ ] **Step 3: Run tests and verify failure**

```powershell
python -m pytest tests/test_card_behavior_router.py::test_hero_power_transform_claim_routes_to_hero_power_surface tests/test_config_readiness.py::test_source_backed_hero_power_transform_can_be_satisfied_by_globalvalues -q
```

Expected: fail because current routing/readiness does not close these cases.

- [ ] **Step 4: Implement router support**

In `src/hsconfig/card_behavior_surface_router.py`, add to `INTENT_BLOCKS`:

```python
"hero_power_transform": "BeforeUseHeroPowerBonus",
"discover_choice": "OnDiscoverCardBonus",
"choose_one_choice": "OnChooseOneCardBonus",
```

Keep `known_bad_pattern` out of `INTENT_BLOCKS` unless it has a valid explicit `runtime_block`; report-only suppression must remain visible.

- [ ] **Step 5: Implement readiness sufficiency**

In `src/hsconfig/config_readiness.py`, add:

```python
GLOBALVALUES_SUFFICIENT_ROLES = {"hero_power_transform"}
```

In `_lane_and_missing_link()`, before returning `globalvalues_only`, change the branch to:

```python
    if card_id in globalvalue_cards:
        if is_guide_backed and roles <= GLOBALVALUES_SUFFICIENT_ROLES:
            return "globalvalues_only", "none"
        return "globalvalues_only", "needs_runtime_surface"
```

If a card has multiple roles and any role is not in `GLOBALVALUES_SUFFICIENT_ROLES`, keep `needs_runtime_surface`.

- [ ] **Step 6: Run task tests**

```powershell
python -m pytest tests/test_card_behavior_router.py tests/test_config_readiness.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/card_behavior_surface_router.py src/hsconfig/config_readiness.py tests/test_card_behavior_router.py tests/test_config_readiness.py
git commit -m "feat: close source-backed runtime surface readiness"
```

---

## Task 5: ShadowPriest Source-Backed Strong Closure

**Files:**

- Modify: `tests/fixtures/source_documents_shadowpriest_strong.json`
- Modify: `tests/test_archetype_source_fixtures.py`
- Modify: `tests/test_archetype_fixture_e2e.py`

**Interfaces:**

- Consumes: real ShadowPriest deck identity already in `docs/operator/archetype-fixture-matrix.json`.
- Produces: ShadowPriest fixture path that reaches `SOURCE_BACKED_STRONG` or leaves only explicitly accepted report-visible gaps backed by a test.

- [ ] **Step 1: Add failing ShadowPriest strong test**

In `tests/test_archetype_fixture_e2e.py`, add:

```python
def test_shadowpriest_fixture_reaches_source_backed_strong(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "ShadowPriest"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )

    assert code == 0
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    readiness = json.loads((out / "reports" / "per_card_config_readiness_report.json").read_text(encoding="utf-8"))

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert readiness["summary"]["generic_low_confidence"] == 0
    assert readiness["summary"]["cards_needing_guide_claims"] == 0
    assert readiness["summary"]["cards_needing_runtime_surface"] == 0
```

- [ ] **Step 2: Add failing fixture coverage test**

In `tests/test_archetype_source_fixtures.py`, add:

```python
def test_shadowpriest_fixture_closes_known_audit_gaps():
    bundle = _source_bundle_for_fixture("ShadowPriest")
    claims_by_card = {}
    for claim in bundle["claims"]:
        for card in claim.get("cards", []):
            claims_by_card.setdefault(card, []).append(claim)

    expected_cards = {
        "CFM_637",
        "DRG_056",
        "REV_290",
        "SCH_514",
        "TOY_381",
        "TOY_518",
        "VAC_512",
        "WON_065",
        "YOD_032",
        "NX2_019",
        "SW_446",
        "SW_448",
    }
    assert expected_cards <= set(claims_by_card)
    assert any(claim.get("runtime_block") == "BeforePlayCardBonus" for claim in claims_by_card["NX2_019"])
    assert any(claim.get("runtime_block") in {"BeforePlayCardBonus", "OnBoardBonus"} for claim in claims_by_card["SW_446"])
    assert any(claim["claim_kind"] == "hero_power_transform" for claim in claims_by_card["SW_448"])
```

- [ ] **Step 3: Run tests and verify failure**

```powershell
python -m pytest tests/test_archetype_source_fixtures.py::test_shadowpriest_fixture_closes_known_audit_gaps tests/test_archetype_fixture_e2e.py::test_shadowpriest_fixture_reaches_source_backed_strong -q
```

Expected: fail until the fixture and runtime closure are complete.

- [ ] **Step 4: Extend ShadowPriest source documents**

Edit `tests/fixtures/source_documents_shadowpriest_strong.json` only with public source-backed claims. Add one or more documents using this shape; every string in the committed fixture must come from a real public HTTPS source inspected during implementation:

```json
{
  "source_url": "https://hearthstone.wiki.gg/wiki/Mind_Sear",
  "source_title": "Mind Sear - Hearthstone Wiki",
  "source_family": "guide",
  "retrieved_at": "2026-07-07T00:00:00Z",
  "deck_name": "ShadowPriest",
  "archetype": "aggro_burn_hero_power_transform",
  "claims": [
    {
      "claim_kind": "targeting_rule",
      "cards": ["NX2_019"],
      "stance": "prefer_enemy_hero",
      "runtime_block": "BeforePlayCardBonus",
      "runtime_value": "8",
      "condition": "*",
      "evidence_text_short": "Use the verified source text to support Mind Sear as aggressive burn before committing.",
      "source_confidence": "high"
    }
  ]
}
```

Before committing, verify every `source_url`, `source_title`, and `evidence_text_short` against the cited page or guide. The tests from Task 2 must reject private, local, fixture-only, or non-HTTPS sources.

Required card coverage in the fixture:

- `CFM_637`: pirate package or mulligan/discard expectation.
- `DRG_056`: pirate package or early-board pressure expectation.
- `REV_290`: location/board-pressure or report-only if no documented runtime block can express it.
- `SCH_514`: refill/raise-dead expectation.
- `TOY_381`: aggressive curve or synergy expectation.
- `TOY_518`: aggressive curve or synergy expectation.
- `VAC_512`: aggressive curve, burn, or pressure expectation.
- `WON_065`: aggressive curve, burn, or pressure expectation.
- `YOD_032`: early pressure or synergy expectation.
- `NX2_019`: source-backed burn/face rule with a documented CardID block.
- `SW_446`: source-backed board/face-pressure rule with a documented CardID block.
- `SW_448`: Hero Power transform/source-backed static semantic and GlobalValues posture.

- [ ] **Step 5: Run ShadowPriest tests**

```powershell
python -m pytest tests/test_archetype_source_fixtures.py::test_shadowpriest_fixture_closes_known_audit_gaps tests/test_archetype_fixture_e2e.py::test_shadowpriest_fixture_reaches_source_backed_strong -q
```

Expected: both tests pass.

- [ ] **Step 6: Commit**

```powershell
git add tests/fixtures/source_documents_shadowpriest_strong.json tests/test_archetype_source_fixtures.py tests/test_archetype_fixture_e2e.py
git commit -m "test: close shadowpriest source-backed fixture depth"
```

---

## Task 6: Second-Wave Source Fixture Closure For All 11 Decks

**Files:**

- Create:
  - `tests/fixtures/source_documents_ctapaladin_strong.json`
  - `tests/fixtures/source_documents_piraterogue_strong.json`
  - `tests/fixtures/source_documents_treantdruid_strong.json`
  - `tests/fixtures/source_documents_mechpala_strong.json`
  - `tests/fixtures/source_documents_boarlock_strong.json`
  - `tests/fixtures/source_documents_piratedh_strong.json`
- Modify:
  - `docs/operator/archetype-fixture-matrix.json`
  - `tests/test_archetype_fixture_matrix.py`
  - `tests/test_archetype_source_fixtures.py`
  - `tests/test_archetype_fixture_e2e.py`

**Interfaces:**

- Consumes: 11-deck matrix.
- Produces: source-backed fixture and prepare-path test coverage for every listed deck.

- [ ] **Step 1: Add failing fixture references**

In `tests/test_archetype_source_fixtures.py`, extend `FIXTURES`:

```python
FIXTURES = {
    "ShadowPriest": Path("tests/fixtures/source_documents_shadowpriest_strong.json"),
    "CtAPaladin": Path("tests/fixtures/source_documents_ctapaladin_strong.json"),
    "PirateRogue": Path("tests/fixtures/source_documents_piraterogue_strong.json"),
    "BigShaman": Path("tests/fixtures/source_documents_bigshaman_strong.json"),
    "Discolock": Path("tests/fixtures/source_documents_discolock_strong.json"),
    "TreantDruid": Path("tests/fixtures/source_documents_treantdruid_strong.json"),
    "ImbueMage": Path("tests/fixtures/source_documents_imbuemage_strong.json"),
    "MechPala": Path("tests/fixtures/source_documents_mechpala_strong.json"),
    "Kingslayer": Path("tests/fixtures/source_documents_kingslayer_strong.json"),
    "Boarlock": Path("tests/fixtures/source_documents_boarlock_strong.json"),
    "PirateDH": Path("tests/fixtures/source_documents_piratedh_strong.json"),
}
```

In `tests/test_archetype_fixture_matrix.py`, change:

```python
CORE_FIXTURES = {
    "ShadowPriest",
    "CtAPaladin",
    "PirateRogue",
    "BigShaman",
    "Discolock",
    "TreantDruid",
    "ImbueMage",
    "MechPala",
    "Kingslayer",
    "Boarlock",
    "PirateDH",
}
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
python -m pytest tests/test_archetype_fixture_matrix.py tests/test_archetype_source_fixtures.py -q
```

Expected: fail because second-wave fixture files do not exist and matrix still marks some rows as `second_wave_source_fixture`.

- [ ] **Step 3: Promote matrix rows only after fixture files are created**

For each second-wave row in `docs/operator/archetype-fixture-matrix.json`, change:

```json
"fixture_stage": "second_wave_source_fixture"
```

to:

```json
"fixture_stage": "core_source_backed_fixture"
```

Do this only for rows whose fixture file exists and passes source-fixture tests.

- [ ] **Step 4: Create each source fixture with required claims**

Each new fixture file must use this top-level shape:

```json
{
  "source_documents": [
    {
      "source_url": "https://hearthstone.wiki.gg/wiki/Deck",
      "source_title": "Deck - Hearthstone Wiki",
      "source_family": "guide",
      "retrieved_at": "2026-07-07T00:00:00Z",
      "deck_name": "DeckName",
      "archetype": "matrix_archetype_bucket",
      "claims": []
    }
  ]
}
```

Before committing a fixture, verify that the `source_url`, `source_title`, `deck_name`, `archetype`, and every claim evidence line match the actual public source used for that deck. Each deck must include:

- at least one `gameplan_posture` claim
- at least one `mulligan_keep` or `mulligan_discard` claim
- at least one `card_role` claim
- at least one claim that maps to a meaningful runtime surface when the archetype has a documented surface
- no private, local, fixture, or non-HTTPS source URLs

Deck-specific minimums:

- CtAPaladin: `recruit`, `board_flood`, `aura_pressure`, Call-to-Arms sequencing or board-flood posture.
- PirateRogue: `pirate`, `tempo`, `weapon_pressure`, early weapon/face pressure.
- TreantDruid: `token_board`, `treant`, `board_buff`, wide-board snowball posture.
- MechPala: `mech`, `magnetic`, `board_scaling`, board preservation/scaling posture.
- Boarlock: `combo`, `control`, `resource_setup`, explicit `combo_sequence` only if exact ordered cards and values are source-backed.
- PirateDH: `pirate`, `hero_attack`, `tempo_pressure`, weapon/hero attack posture.

- [ ] **Step 5: Extend E2E deck list**

In `tests/test_archetype_fixture_e2e.py`, extend `DECKS` to all 11 decks using exact deck codes from `docs/operator/archetype-fixture-matrix.json` and matching fixture paths.

- [ ] **Step 6: Add archetype-specific source tests**

In `tests/test_archetype_source_fixtures.py`, add focused tests:

```python
def test_ctapaladin_fixture_covers_recruit_board_flood():
    claims = [claim for document in _documents(FIXTURES["CtAPaladin"]) for claim in document["claims"]]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert any(marker in text for marker in ("recruit", "call to arms", "board", "flood"))


def test_piraterogue_fixture_covers_pirate_weapon_pressure():
    claims = [claim for document in _documents(FIXTURES["PirateRogue"]) for claim in document["claims"]]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert "pirate" in text
    assert any(marker in text for marker in ("weapon", "face", "tempo", "pressure"))


def test_treantdruid_fixture_covers_token_board_snowball():
    claims = [claim for document in _documents(FIXTURES["TreantDruid"]) for claim in document["claims"]]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert any(marker in text for marker in ("treant", "token", "wide board", "board buff"))


def test_mechpala_fixture_covers_mech_board_scaling():
    claims = [claim for document in _documents(FIXTURES["MechPala"]) for claim in document["claims"]]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert "mech" in text
    assert any(marker in text for marker in ("magnetic", "board", "scaling", "buff"))


def test_boarlock_fixture_covers_combo_resource_setup():
    claims = [claim for document in _documents(FIXTURES["Boarlock"]) for claim in document["claims"]]
    kinds = {claim["claim_kind"] for claim in claims}
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert any(marker in text for marker in ("combo", "resource", "setup", "boar"))
    assert {"card_role", "gameplan_posture"} <= kinds


def test_piratedh_fixture_covers_pirate_hero_attack_pressure():
    claims = [claim for document in _documents(FIXTURES["PirateDH"]) for claim in document["claims"]]
    text = " ".join(str(claim.get("evidence_text_short", "")) for claim in claims).lower()
    assert "pirate" in text
    assert any(marker in text for marker in ("hero attack", "weapon", "face", "tempo"))
```

- [ ] **Step 7: Run fixture and E2E tests**

```powershell
python -m pytest tests/test_archetype_fixture_matrix.py tests/test_archetype_source_fixtures.py tests/test_archetype_fixture_e2e.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```powershell
git add docs/operator/archetype-fixture-matrix.json tests/fixtures/source_documents_ctapaladin_strong.json tests/fixtures/source_documents_piraterogue_strong.json tests/fixtures/source_documents_treantdruid_strong.json tests/fixtures/source_documents_mechpala_strong.json tests/fixtures/source_documents_boarlock_strong.json tests/fixtures/source_documents_piratedh_strong.json tests/test_archetype_fixture_matrix.py tests/test_archetype_source_fixtures.py tests/test_archetype_fixture_e2e.py
git commit -m "test: close source-backed fixtures for representative decks"
```

---

## Task 7: Documentation And Legacy Surface Polish

**Files:**

- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/visionai-surfaces.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `tests/test_skill_files.py`

**Interfaces:**

- Consumes: current operator flow and status model.
- Produces: one clear normal path and no normal-path `Presume` / `Concede` ambiguity.

- [ ] **Step 1: Add failing docs tests for single operator contract**

In `tests/test_skill_files.py`, add:

```python
def test_docs_make_operator_summary_the_single_normal_gate():
    docs = "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/references/workflow.md").read_text(encoding="utf-8"),
        ]
    )

    assert docs.count("operator_summary.json") >= 3
    assert "single operator gate" in docs.lower()
    assert "replay" in docs.lower()
    assert "does not parse replays" in docs


def test_docs_do_not_advertise_presume_concede_as_normal_outputs():
    active_docs = [
        Path("README.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    forbidden = [
        "emit Presume.json",
        "emit Concede.json",
        "normal output includes Presume",
        "normal output includes Concede",
    ]
    for path in active_docs:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
python -m pytest tests/test_skill_files.py::test_docs_make_operator_summary_the_single_normal_gate tests/test_skill_files.py::test_docs_do_not_advertise_presume_concede_as_normal_outputs -q
```

Expected: first test fails until docs contain the exact “single operator gate” language.

- [ ] **Step 3: Update README**

Keep `README.md` short. Add this paragraph under `Status Model`:

```markdown
`reports/operator_summary.json` is the single operator gate. Use the detail reports to explain the gate, but do not make apply or handoff decisions from a lower-level report alone.
```

- [ ] **Step 4: Update skill workflow doc**

In `.agents/skills/hsconfig/references/workflow.md`, add:

```markdown
`reports/operator_summary.json` is the single operator gate for normal handoff or apply decisions. Lower-level reports explain why the package is strong, warning-only, or still needs source work.
```

- [ ] **Step 5: Update skill root doc**

In `.agents/skills/hsconfig/SKILL.md`, add:

```markdown
Use `reports/operator_summary.json` as the single operator gate. Detail reports are evidence, not independent apply permissions.
```

- [ ] **Step 6: Run docs tests**

```powershell
python -m pytest tests/test_skill_files.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Sync installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync
```

- [ ] **Step 8: Commit**

```powershell
git add README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md .agents/skills/hsconfig/references/visionai-surfaces.md .agents/skills/hsconfig/references/guide-research-policy.md .agents/skills/hsconfig/references/globalvalues-policy.md .agents/skills/hsconfig/references/card-behavior-policy.md tests/test_skill_files.py
git commit -m "docs: clarify hsconfig operator gate and legacy surfaces"
```

---

## Task 8: Final Verification And GitHub Update

**Files:**

- No planned source edits.
- Verify all touched files from prior tasks.

**Interfaces:**

- Consumes: all prior task outputs.
- Produces: green test evidence and synced `origin/main`.

- [ ] **Step 1: Run research audit validation**

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-07-hsconfig-skill-audit\fields.yaml -j docs\research\2026-07-07-hsconfig-skill-audit\results\HearthRanger_VisionAI_Runtime_Surface_Contract.json docs\research\2026-07-07-hsconfig-skill-audit\results\Hearthstone_Card_Identity_And_Static_Semantics.json docs\research\2026-07-07-hsconfig-skill-audit\results\Source-Backed_Guide_Claim_Depth.json docs\research\2026-07-07-hsconfig-skill-audit\results\Multi-Archetype_Deck_Coverage_Matrix.json docs\research\2026-07-07-hsconfig-skill-audit\results\Lean_Skill_Boundary_And_Operator_UX.json
```

Expected:

```text
Validation passed: 5/5
```

- [ ] **Step 2: Run targeted tests**

```powershell
python -m pytest tests/test_skill_sync.py tests/test_source_evidence_verifier.py tests/test_skill_files.py tests/test_guide_source_depth.py tests/test_operator_summary.py tests/test_card_behavior_router.py tests/test_config_readiness.py tests/test_archetype_fixture_matrix.py tests/test_archetype_source_fixtures.py tests/test_archetype_fixture_e2e.py tests/test_research_audit_schema.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run full suite**

```powershell
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Run ShadowPriest proof command**

```powershell
$out = Join-Path $env:TEMP 'hsconfig-proof-shadowpriest'
Remove-Item -LiteralPath $out -Recurse -Force -ErrorAction SilentlyContinue
python -m hsconfig prepare --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root (Join-Path $env:TEMP 'hsconfig-proof-runtime') --out $out --source-documents-json tests\fixtures\source_documents_shadowpriest_strong.json --json
$summary = Get-Content (Join-Path $out 'reports\operator_summary.json') -Raw | ConvertFrom-Json
$summary.technical_status
$summary.semantic_status
$summary.next_action
```

Expected:

```text
VALID_PACKAGE
SOURCE_BACKED_STRONG
READY_TO_APPLY_OR_HANDOFF
```

If `SOURCE_BACKED_STRONG` is not reached, inspect:

- `$out\reports\operator_summary.json`
- `$out\reports\per_card_config_readiness_report.json`
- `$out\reports\source_evidence_verification_report.json`

Then return to the task that owns the first listed missing link.

- [ ] **Step 5: Verify installed skill sync**

```powershell
python scripts/sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync
```

- [ ] **Step 6: Inspect diff and status**

```powershell
git status --short --branch
git log --oneline -8
```

Expected:

```text
## main...origin/main [ahead N]
```

or a clean synchronized state after push.

- [ ] **Step 7: Push main**

```powershell
git push origin main
```

Expected:

```text
main -> main
```

---

## Subagent Execution Notes

Recommended execution order:

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7
8. Task 8

Do not run Tasks 2, 3, 4, 5, and 6 as parallel write tasks because they touch shared compiler, readiness, fixture, and CLI reports. They can be explored in parallel read-only, but one worker should own final edits per task.

Task 6 can be split per deck only if each worker writes exactly one fixture file and does not modify shared tests or `docs/operator/archetype-fixture-matrix.json`. A coordinator must integrate those shared files afterward.

---

## Self-Review

Spec coverage:

- Skill-sync gap is covered by Task 1 and Task 7.
- Source evidence and strict runtime-lowering gap is covered by Task 2 and Task 3.
- ShadowPriest source-depth gap is covered by Task 5.
- Runtime surface closure for Hero Power, burn, and option semantics is covered by Task 4.
- Remaining 6 deck fixture gap is covered by Task 6.
- Docs/legacy surface polish is covered by Task 7.
- Full verification and GitHub update are covered by Task 8.

Deferred-work scan:

- The plan uses explicit test names, command lines, expected results, and function signatures.
- Fixture authoring requires real public sources; the task includes explicit failure conditions because source text cannot be fabricated in a plan.
- No deferred-work markers remain.

Type consistency:

- `verify_source_documents(source_documents: list[dict]) -> dict` is introduced in Task 2 and consumed by CLI/reporting tasks.
- `source_depth_status` is introduced in Task 3 and read by `operator_summary.py`.
- `hero_power_transform` routing and GlobalValues sufficiency are introduced in Task 4 and consumed by ShadowPriest closure in Task 5.
