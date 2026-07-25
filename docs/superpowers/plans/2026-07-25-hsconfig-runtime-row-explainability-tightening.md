# HSConfig Runtime Row Explainability Tightening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every code change and `superpowers:verification-before-completion` before declaring the branch complete. Steps use checkbox (`- [ ]`) syntax for execution tracking.

**Goal:** Make HSConfig's generated VisionAI/CardID runtime package leaner and more explainable by ensuring every physical runtime row is either explicitly source-backed in the behavior report or intentionally classified as a narrow compiler policy row. The ShadowPriest package must remain `SOURCE_BACKED_STRONG`, have no `default_only_runtime_surfaces`, and must not contain generic `InHandPlayPriority` or `BeforePlayCardBonus` rows that are only artifacts of broad fallback logic.

**Architecture:** Preserve the existing source-contract pipeline. Tighten the compiler and quality contract rather than adding a new generation stage. The compiler should emit specific runtime keys from source-backed semantic behavior rows first, then add narrow policy fallback rows only for cards with no lowerable behavior. The quality contract should compare the generated physical `CustomConfig/<deck>/*.json` files against `reports/card_behavior_plan_report.json`, so a clean report cannot hide unreported runtime rows.

**Tech Stack:** Python package `hsconfig`, pytest, existing CLI commands, existing package reports, existing skill sync tooling, PowerShell on Windows.

**Target Repo:** `C:\Users\darbo\Documents\HSConfig`

**Runtime Evidence Boundary:** Do not commit real HearthRanger/Hearthstone logs, runtime evidence, or backups. Real runtime comparison against `C:\Users\darbo\Desktop\HS` is read-only unless the operator explicitly runs an apply command. Test fixtures must use temporary directories.

**Current Audit Facts Driving This Plan:**

- Generated ShadowPriest package: `C:\Users\darbo\Documents\HSConfig\outputs\ShadowPriest-2026-07-25-2772b6a\04_package`.
- `validate` passes and `contract-doctor` reports `technical_status=VALID_PACKAGE`, `semantic_status=SOURCE_BACKED_STRONG`, and `default_only_runtime_surfaces=[]`.
- Strict physical package audit found more physical CardID runtime rows than meaningful source-backed behavior rows: 38 physical rows versus 22 report rows.
- The excess rows are generic compiler fallback rows: broad `InHandPlayPriority` rows and one pressure `BeforePlayCardBonus` row.
- `config_quality_contract.py` currently evaluates report rows, but does not cross-check every physical runtime row in generated CardID JSON files.
- Repo skill source and installed skill are not byte-identical; the installed skill contains the stronger rule that `SOURCE_BACKED_STRONG` is necessary but not sufficient unless the VisionAI semantic surface audit is clean.

## Global Constraints

- [ ] Keep the solution narrow: no new pipeline stage, no new dependency, no HSTuner dependency.
- [ ] Keep HSConfig usable for every deck: no deck-specific hard block, no class-specific special case except tests that assert concrete ShadowPriest behavior.
- [ ] Keep `Darkbishop Benedictus` effect-only semantics intact: no mulligan keep without explicit mulligan source, no body priority for the card itself, preserve the Start-of-Game/Hero Power effect behavior.
- [ ] Keep runtime writes out of tests. Tests may create package-like temp directories only.
- [ ] Keep the worktree clean at completion: commit the implementation and verify `git status --short --branch` has no unstaged or staged changes.

---

## Task 1: Add Physical Runtime Row Inventory To The Quality Contract

**Purpose:** A package should not be marked fully clean while generated CardID JSON contains runtime rows that are absent from `card_behavior_plan_report.json`.

**Files:**

- `src/hsconfig/config_quality_contract.py`
- `tests/test_config_quality_contract.py`

### Test First

- [ ] Add `test_config_quality_flags_physical_cardid_rows_missing_behavior_report_trace`.

Expected fixture shape:

```python
def test_config_quality_flags_physical_cardid_rows_missing_behavior_report_trace(tmp_path):
    package = minimal_clean_package(tmp_path)
    custom_config = package / "CustomConfig" / "shadowpriest"
    custom_config.mkdir(parents=True, exist_ok=True)
    (custom_config / "EX1_001.json").write_text(
        json.dumps(
            {
                "GameCardId": "EX1_001",
                "BeforePlayCardBonus": {
                    "values": [
                        {
                            "condition": "*",
                            "value": "12",
                            "comment": "source-backed behavior",
                        }
                    ],
                },
                "InHandPlayPriority": {
                    "values": [
                        {
                            "condition": "*",
                            "value": "5",
                            "comment": "unreported generic fallback",
                        }
                    ],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    card_report = package / "reports" / "card_behavior_plan_report.json"
    payload = json.loads(card_report.read_text(encoding="utf-8"))
    payload["rows"] = [
        {
            "card_id": "EX1_001",
            "behavior_block": "BeforePlayCardBonus",
            "value": 12,
            "comment": "source-backed behavior",
            "source_claim_ids": ["claim-1"],
            "confidence": "source_backed",
        }
    ]
    card_report.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    report = build_config_quality_report(package)

    inventory = report["checks"]["runtime_row_trace_inventory"]
    assert inventory["status"] == "attention"
    assert inventory["physical_cardid_runtime_rows"] == 2
    assert inventory["reported_meaningful_cardid_runtime_rows"] == 1
    assert inventory["unreported_runtime_rows"] == [
        {
            "card_id": "EX1_001",
            "behavior_block": "InHandPlayPriority",
            "file": "CustomConfig/shadowpriest/EX1_001.json",
        }
    ]
```

- [ ] Run:

```powershell
python -m pytest tests/test_config_quality_contract.py -k physical_cardid_rows_missing_behavior_report_trace
```

- [ ] Confirm the test fails because `runtime_row_trace_inventory` does not exist or does not inspect physical JSON files.

### Implementation

- [ ] Import the existing supported CardID behavior registry:

```python
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS
```

- [ ] Add `_iter_physical_cardid_runtime_rows(package_root: Path) -> list[dict[str, str]]`.

Rules:

- Read `CustomConfig/*/*.json`.
- Ignore non-dict JSON.
- Use `GameCardId` as `card_id`; fall back to the file stem only when `GameCardId` is absent.
- Collect only keys in `CARD_BEHAVIOR_BLOCKS`.
- Return stable rows sorted by `(card_id, behavior_block, file)`.

- [ ] Add `_reported_cardid_runtime_rows(card_behavior: Mapping[str, Any]) -> set[tuple[str, str]]`.

Rules:

- Use the existing meaningful row predicate.
- Identity is `(card_id, behavior_block)` because runtime files do not preserve claim ids and comments as stable authority.
- Exclude report-only diagnostic rows already excluded by `_is_meaningful_cardid_row`.

- [ ] Add `_runtime_row_trace_inventory_check(package_root, card_behavior)`.

Return shape:

```python
{
    "status": "clean" | "attention",
    "physical_cardid_runtime_rows": int,
    "reported_meaningful_cardid_runtime_rows": int,
    "unreported_runtime_rows": [
        {
            "card_id": "EX1_001",
            "behavior_block": "InHandPlayPriority",
            "file": "CustomConfig/shadowpriest/EX1_001.json",
        }
    ],
}
```

- [ ] Add the check inside `build_config_quality_report(package: str | Path)` under `checks["runtime_row_trace_inventory"]`.
- [ ] Make the package-level `status` become `attention` when `unreported_runtime_rows` is non-empty.

### Verification

- [ ] Run:

```powershell
python -m pytest tests/test_config_quality_contract.py -k "runtime_row_trace_inventory or physical_cardid_rows_missing_behavior_report_trace"
```

- [ ] Run:

```powershell
python -m pytest tests/test_config_quality_contract.py
```

---

## Task 2: Make Generic In-Hand Priority A Last-Resort Policy Row

**Purpose:** `InHandPlayPriority` is only a search-order hint. It should not be emitted automatically for cards that already have a source-backed lowerable behavior row.

**Files:**

- `src/hsconfig/compile_cardid.py`
- `tests/test_compile_cardid.py`

### Test First

- [ ] Add `test_compile_cardid_skips_generic_inhand_priority_when_explicit_behavior_exists`.

Expected shape:

```python
def test_compile_cardid_skips_generic_inhand_priority_when_explicit_behavior_exists(tmp_path):
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_001": {
                "card_id": "EX1_001",
                "name": "Specific Card",
                "roles": ["pressure"],
                "source_claim_ids": ["claim-1"],
                "confidence": "source_backed",
            }
        },
    }
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_001",
            "behavior_block": "BeforePlayCardBonus",
            "value": "12",
            "comment": "Play before attacking face.",
            "source_claim_ids": ["claim-1"],
            "confidence": "source_backed",
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)
    payload = files["EX1_001.json"]

    assert "BeforePlayCardBonus" in payload
    assert "InHandPlayPriority" not in payload
```

- [ ] Add `test_compile_cardid_keeps_generic_inhand_priority_for_cards_without_behavior_rows`.

Expected shape:

```python
def test_compile_cardid_keeps_generic_inhand_priority_for_cards_without_behavior_rows(tmp_path):
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_002": {
                "name": "Report Only Card",
                "roles": ["pressure"],
                "source_claim_ids": ["claim-2"],
                "confidence": "source_backed",
            }
        },
    }

    files = compile_cardid_behaviors(contract)
    payload = files["EX1_002.json"]

    assert payload["GameCardId"] == "EX1_002"
    assert payload["InHandPlayPriority"]["values"][0]["value"] == "10"
```

- [ ] Run:

```powershell
python -m pytest tests/test_compile_cardid.py -k "generic_inhand_priority"
```

- [ ] Confirm the first test fails because current compiler emits `InHandPlayPriority` before inspecting explicit behavior rows.

### Implementation

- [ ] In `compile_cardid_behaviors`, build explicit behavior rows before adding automatic in-hand priority.
- [ ] Add helper:

```python
def _should_emit_generic_in_hand_priority(
    *,
    effect_only_start_of_game: bool,
    explicit_blocks: set[str],
) -> bool:
    return not effect_only_start_of_game and not explicit_blocks
```

- [ ] Change flow:

```python
explicit_blocks = _append_explicit_behavior_rows(
    config,
    deck_name,
    card_id,
    card.get("behavior_rows", []),
)

if _should_emit_generic_in_hand_priority(
    effect_only_start_of_game=effect_only_start_of_game,
    explicit_blocks=explicit_blocks,
):
    _append_block_row(
        config,
        "InHandPlayPriority",
        deck_name,
        card_id,
        "in_hand_priority",
        _priority_value(roles, confidence),
        source_claim_ids,
        confidence,
    )
```

- [ ] Keep `_priority_value` unchanged so cards without explicit behavior preserve existing role-based ordering.
- [ ] Keep effect-only cards excluded from body priority exactly as today.

### Verification

- [ ] Run:

```powershell
python -m pytest tests/test_compile_cardid.py -k "generic_inhand_priority or effect_only_darkbishop"
```

- [ ] Run:

```powershell
python -m pytest tests/test_compile_cardid.py
```

---

## Task 3: Suppress Generic Pressure Play Bonus When Specific Behavior Exists

**Purpose:** A broad role fallback `BeforePlayCardBonus` should not be added to a card that already has a specific source-backed behavior row such as `OnBoardBonus`.

**Files:**

- `src/hsconfig/compile_cardid.py`
- `tests/test_compile_cardid.py`

### Test First

- [ ] Add `test_compile_cardid_skips_pressure_play_bonus_when_specific_behavior_exists`.

Expected shape:

```python
def test_compile_cardid_skips_pressure_play_bonus_when_specific_behavior_exists(tmp_path):
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "TOY_381": {
                "card_id": "TOY_381",
                "name": "Pressure Card With Specific Board Text",
                "roles": ["pressure"],
                "source_claim_ids": ["claim-board"],
                "confidence": "source_backed",
            }
        },
    }
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "TOY_381",
            "behavior_block": "OnBoardBonus",
            "value": "18",
            "comment": "Specific source-backed board effect.",
            "source_claim_ids": ["claim-board"],
            "confidence": "source_backed",
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)
    payload = files["TOY_381.json"]

    assert "OnBoardBonus" in payload
    assert "BeforePlayCardBonus" not in payload
    assert "InHandPlayPriority" not in payload
```

- [ ] Add `test_compile_cardid_keeps_pressure_play_bonus_for_pressure_card_without_behavior_rows`.

Expected shape:

```python
def test_compile_cardid_keeps_pressure_play_bonus_for_pressure_card_without_behavior_rows(tmp_path):
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_003": {
                "name": "Plain Pressure Card",
                "roles": ["pressure"],
                "source_claim_ids": ["claim-pressure"],
                "confidence": "source_backed",
            }
        },
    }

    files = compile_cardid_behaviors(contract)
    payload = files["EX1_003.json"]

    assert payload["BeforePlayCardBonus"]["values"][0]["value"] == "8"
    assert payload["InHandPlayPriority"]["values"][0]["value"] == "10"
```

- [ ] Run:

```powershell
python -m pytest tests/test_compile_cardid.py -k "pressure_play_bonus"
```

- [ ] Confirm the first test fails under the current `pressure` fallback condition.

### Implementation

- [ ] Replace the current pressure fallback condition with:

```python
if (
    not effect_only_start_of_game
    and "pressure" in roles
    and not explicit_blocks
    and "BeforePlayCardBonus" not in config
):
    _append_block_row(
        config,
        "BeforePlayCardBonus",
        deck_name,
        card_id,
        "pressure_play_bonus",
        "8",
        source_claim_ids,
        confidence,
    )
```

- [ ] Preserve role fallbacks listed in `DIAGNOSTIC_ONLY_ROLE_FALLBACKS` for report visibility only; do not convert diagnostic-only roles into runtime behavior rows.

### Verification

- [ ] Run:

```powershell
python -m pytest tests/test_compile_cardid.py -k "pressure_play_bonus or generic_inhand_priority or effect_only_darkbishop"
```

- [ ] Run:

```powershell
python -m pytest tests/test_compile_cardid.py
```

---

## Task 4: Make The ShadowPriest Acceptance Proof Compare Report Rows To Physical Runtime Rows

**Purpose:** The exact ShadowPriest package should prove that every CardID runtime row is intentionally generated and report-backed.

**Files:**

- `tests/test_shadowpriest_runtime_row_explainability.py`
- `tests/fixtures/source_documents_shadowpriest_strong.json`

### Test First

- [ ] Create `tests/test_shadowpriest_runtime_row_explainability.py`.

Expected assertions:

```python
def test_shadowpriest_generated_package_has_no_unreported_cardid_runtime_rows(tmp_path, monkeypatch):
    package = generate_shadowpriest_package(tmp_path, monkeypatch)
    report = build_config_quality_report(package)

    inventory = report["checks"]["runtime_row_trace_inventory"]
    assert inventory["status"] == "clean"
    assert inventory["unreported_runtime_rows"] == []
    assert inventory["physical_cardid_runtime_rows"] == inventory[
        "reported_meaningful_cardid_runtime_rows"
    ]
```

- [ ] Add `test_shadowpriest_effect_only_and_key_semantics_remain_intact`.

Required assertions:

```python
def test_shadowpriest_effect_only_and_key_semantics_remain_intact(tmp_path, monkeypatch):
    package = generate_shadowpriest_package(tmp_path, monkeypatch)
    card_dir = next((package / "CustomConfig").iterdir())

    darkbishop = json.loads((card_dir / "SW_448.json").read_text(encoding="utf-8"))
    assert "InHandPlayPriority" not in darkbishop
    assert "BeforePlayCardBonus" not in darkbishop
    assert "BeforeUseHeroPowerBonus" in darkbishop

    voidtouched = json.loads((card_dir / "SW_446.json").read_text(encoding="utf-8"))
    assert "BeforePlayCardBonus" in voidtouched

    cathedral = json.loads((card_dir / "REV_290.json").read_text(encoding="utf-8"))
    assert "BeforePlayCardBonus" in cathedral or "OnBoardBonus" in cathedral

    mind_sear = json.loads((card_dir / "NX2_019.json").read_text(encoding="utf-8"))
    assert "BeforePlayCardBonus" in mind_sear
    assert "BeforeBattlecryTargetBonus" not in mind_sear
```

- [ ] Implement `generate_shadowpriest_package(tmp_path, monkeypatch)` inside the test module using the same public CLI entrypoint pattern as `tests/test_shadowpriest_visionai_semantic_surface_contract.py`:

```python
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def generate_shadowpriest_package(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    package = tmp_path / "shadowpriest"
    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )
    assert code == 0
    return package
```

- [ ] Run:

```powershell
python -m pytest tests/test_shadowpriest_runtime_row_explainability.py
```

- [ ] Confirm the first test fails before compiler and contract changes are complete.

### Implementation

- [ ] Use the real ShadowPriest deck code:

```text
AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
```

- [ ] Do not assert exact total row count. Assert equality between physical rows and report-backed rows so the test remains valid when new source-backed ShadowPriest behavior is added.

### Verification

- [ ] Run:

```powershell
python -m pytest tests/test_shadowpriest_runtime_row_explainability.py
python -m pytest tests/test_compile_cardid.py tests/test_config_quality_contract.py tests/test_shadowpriest_runtime_row_explainability.py
```

---

## Task 5: Sync The Repo Skill Contract With The Installed Skill Contract

**Purpose:** The repo skill must contain the same semantic-surface rule currently present in the installed skill, so future installs do not weaken the workflow.

**Files:**

- `.agents/skills/hsconfig/SKILL.md`
- `tests/test_hsconfig_skill_contract.py`

### Test First

- [ ] Add `tests/test_hsconfig_skill_contract.py` with:

```python
from pathlib import Path


def test_repo_skill_requires_semantic_surface_audit_beyond_source_backed_strong():
    text = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    assert (
        "Treat `SOURCE_BACKED_STRONG` as necessary but not sufficient"
        in text
    )
    assert "VisionAI semantic surface audit" in text
```

- [ ] Run:

```powershell
python -m pytest tests/test_hsconfig_skill_contract.py
```

- [ ] Confirm the test fails before editing the repo skill.

### Implementation

- [ ] Insert this exact rule in `.agents/skills/hsconfig/SKILL.md` near the source/contract acceptance rules:

```markdown
- Treat `SOURCE_BACKED_STRONG` as necessary but not sufficient: the generated package must also pass the VisionAI semantic surface audit. Do not emit target, combo, location, or hand-priority keys from source text that does not semantically support that runtime surface.
```

- [ ] Run the existing skill sync command after the repo skill passes its test:

```powershell
python scripts/sync_installed_skill.py
```

- [ ] Verify the installed skill contains the same rule:

```powershell
Select-String -Path C:\Users\darbo\.codex\skills\hsconfig\SKILL.md -Pattern "Treat `SOURCE_BACKED_STRONG` as necessary but not sufficient"
```

### Verification

- [ ] Run:

```powershell
python -m pytest tests/test_hsconfig_skill_contract.py
```

---

## Task 6: Regenerate And Validate ShadowPriest With The Tightened Contract

**Purpose:** Prove the current user-facing deck workflow still generates a valid package and that the package is leaner and semantically explainable.

**Commands:**

- [ ] Regenerate ShadowPriest:

```powershell
$out = "outputs\ShadowPriest-runtime-row-explainability-tightening"
$runtime = "C:\Users\darbo\Desktop\HS"
python -m hsconfig.cli configure `
  --deck-name "ShadowPriest" `
  --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
  --runtime-root $runtime `
  --out $out `
  --online-source `
  --auto-source `
  --source-fetch-timeout-seconds 30 `
  --json
$pkg = Join-Path $out "04_package"
```

- [ ] Open the generated package's `reports/operator_summary.json` and confirm:

```text
source_status = SOURCE_BACKED_STRONG
source_status_apply_blocking = false
default_only_runtime_surfaces = []
```

- [ ] Validate the package:

```powershell
python -m hsconfig.cli validate --package $pkg
```

- [ ] Run contract doctor:

```powershell
python -m hsconfig.cli contract-doctor --package $pkg --json
```

- [ ] Confirm the JSON contains:

```text
technical_status = VALID_PACKAGE
semantic_status = SOURCE_BACKED_STRONG
checks.runtime_row_trace_inventory.status = clean
checks.runtime_row_trace_inventory.unreported_runtime_rows = []
```

- [ ] Run runtime comparison read-only against the real runtime:

```powershell
python -m hsconfig.cli runtime-match --package $pkg --runtime-root C:\Users\darbo\Desktop\HS --json
```

- [ ] If the runtime comparison is `mismatch`, report that the generated package is correct and the installed runtime still needs an apply step. Do not modify `C:\Users\darbo\Desktop\HS` from tests.

---

## Task 7: Full Regression And Clean Worktree Closure

**Purpose:** Finish with evidence, a clean branch, and no generated residue.

### Verification

- [ ] Run the focused suite:

```powershell
python -m pytest tests/test_compile_cardid.py tests/test_config_quality_contract.py tests/test_shadowpriest_runtime_row_explainability.py tests/test_hsconfig_skill_contract.py
```

- [ ] Run the package health checks:

```powershell
$pkg = "outputs\ShadowPriest-runtime-row-explainability-tightening\04_package"
python -m hsconfig.cli validate --package $pkg
python -m hsconfig.cli contract-doctor --package $pkg --json
```

- [ ] Run currentness check:

```powershell
python scripts/check_hsconfig_currentness.py --cwd . --json
```

Expected:

```text
dirty = false after commit
clean_for_runtime_work = true
```

### Cleanup

- [ ] Remove temporary test directories and generated scratch outputs that are not part of the final committed result.
- [ ] Keep the regenerated package only when the repository already tracks the equivalent output artifact policy for generated packages. Otherwise leave outputs untracked and excluded from the commit.

### Commit

- [ ] Review diff:

```powershell
git diff -- src/hsconfig/compile_cardid.py src/hsconfig/config_quality_contract.py tests/test_compile_cardid.py tests/test_config_quality_contract.py tests/test_shadowpriest_runtime_row_explainability.py tests/test_hsconfig_skill_contract.py .agents/skills/hsconfig/SKILL.md
```

- [ ] Stage only implementation, tests, skill sync source, and this plan:

```powershell
git add src/hsconfig/compile_cardid.py src/hsconfig/config_quality_contract.py tests/test_compile_cardid.py tests/test_config_quality_contract.py tests/test_shadowpriest_runtime_row_explainability.py tests/test_hsconfig_skill_contract.py .agents/skills/hsconfig/SKILL.md docs/superpowers/plans/2026-07-25-hsconfig-runtime-row-explainability-tightening.md
```

- [ ] Commit:

```powershell
git commit -m "Tighten HSConfig runtime row explainability"
```

- [ ] Confirm clean:

```powershell
git status --short --branch
```

Expected final output shape:

```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring
```

The branch line may include an ahead count after local commits. No file rows may appear below the branch line.

---

## Acceptance Criteria

- [ ] `contract-doctor` cannot report clean while generated CardID JSON contains physical behavior rows missing from `card_behavior_plan_report.json`.
- [ ] Cards with explicit source-backed behavior rows do not receive broad automatic `InHandPlayPriority`.
- [ ] Pressure cards with explicit source-backed behavior rows do not receive broad automatic `BeforePlayCardBonus`.
- [ ] Cards without explicit behavior rows still receive the existing minimal search-order fallback when they are not effect-only start-of-game cards.
- [ ] `Darkbishop Benedictus` keeps only the effect semantics and no card-body priority.
- [ ] Generated ShadowPriest remains `SOURCE_BACKED_STRONG` with `default_only_runtime_surfaces=[]`.
- [ ] Repo skill and installed skill both include the stronger semantic-surface acceptance rule.
- [ ] Focused pytest suite passes.
- [ ] Worktree is clean after commit.
