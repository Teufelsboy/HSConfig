# Task 5 Report: Operator Docs And Installed Skill Sync

## Status

DONE

## Implementation Commit

d3770d8451beff5d2efcfbb0ec7cd6af83c9b571

This is the implementation commit for the operator docs, repo skill mirror, reference mirror, and focused tests. This report is written after that commit so it can record the implementation hash.

## Files Changed

- `docs/operator/source-backed-strong-closure.md`
- `docs/operator/source-builder-workflow.md`
- `docs/operator/guide-research-policy.md`
- `.agents/skills/hsconfig/SKILL.md`
- `.agents/skills/hsconfig/references/guide-research-policy.md`
- `.agents/skills/hsconfig/references/workflow.md`
- `tests/test_docs_active_path.py`
- `tests/test_skill_sync.py`
- `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md` and skill references were updated by `python scripts/sync_installed_skill.py`

## What Changed

- Documented the exact `SOURCE_BACKED_STRONG` contract: evidence-quality label, valid load-safe config still builds under partial public source coverage, Strong only when lowerable source/static semantics are closed, no expected runtime surface is default-only, and `first_missing_source_action` is `none`.
- Documented the recommended fresh source-backed command:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --online-source --auto-source --apply
```

- Documented `source_backed_strong_closure` and `no_default_only_runtime_status` as compact diagnostic-only `operator_summary.json` summaries.
- Explicitly kept these summaries out of apply gating and kept `reports/operator_summary.json` as the normal apply authority.
- Mirrored the same guidance into the repo hsconfig skill and relevant reference files, then synced the installed skill.
- Added focused tests for the active operator docs and the skill sync output.

## Red Evidence

Command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py tests/test_skill_sync.py -q
```

Output before docs and skill edits:

```text
...........FF.........................F.                                 [100%]
================================== FAILURES ===================================
__________ test_docs_define_source_backed_strong_without_second_gate __________

    def test_docs_define_source_backed_strong_without_second_gate():
        root = Path(__file__).resolve().parents[1]
        text = (root / "docs" / "operator" / "source-backed-strong-closure.md").read_text(
            encoding="utf-8"
        )

>       assert "SOURCE_BACKED_STRONG is an evidence-quality label" in text
E       AssertionError: assert 'SOURCE_BACKED_STRONG is an evidence-quality label' in '# Source-Backed Strong Closure\n\nThis file tracks which representative HSConfig deck fixtures are truly strong.\n\nF...TIAL` | card-specific source claims needed for low-confidence or uncovered rows | `add_card_specific_source_claim` |\n'

tests\test_docs_active_path.py:169: AssertionError
____ test_operator_docs_define_closure_diagnostics_as_summaries_not_gates _____

    def test_operator_docs_define_closure_diagnostics_as_summaries_not_gates():
        closure = Path("docs/operator/source-backed-strong-closure.md").read_text(
            encoding="utf-8"
        )
        workflow = Path("docs/operator/source-builder-workflow.md").read_text(
            encoding="utf-8"
        )
        policy = Path("docs/operator/guide-research-policy.md").read_text(
            encoding="utf-8"
        )
        combined = "\n".join([closure, workflow, policy])

>       assert "source_backed_strong_closure" in combined
E       AssertionError: assert 'source_backed_strong_closure' in '# Source-Backed Strong Closure\n\nThis file tracks which representative HSConfig deck fixtures are truly strong.\n\nF...ck-only autonomy work. This document is intentionally a contract, not an implementation of web browsing or scraping.\n'

tests\test_docs_active_path.py:187: AssertionError
__________ test_skill_sync_propagates_source_backed_closure_guidance __________

tmp_path = WindowsPath('C:/Users/darbo/AppData/Local/Temp/pytest-of-darbo/pytest-4253/test_skill_sync_propagates_sou0')

    def test_skill_sync_propagates_source_backed_closure_guidance(tmp_path: Path):
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

        installed_root = install_root / "hsconfig"
        skill_text = (installed_root / "SKILL.md").read_text(encoding="utf-8")
        policy_text = (installed_root / "references" / "guide-research-policy.md").read_text(
            encoding="utf-8"
        )

>       assert "For an optimal fresh deck config, prefer the source-backed path:" in skill_text
E       AssertionError: assert 'For an optimal fresh deck config, prefer the source-backed path:' in '---\nname: hsconfig\ndescription: Generate guide-aligned HearthRanger VisionAI CustomConfig packages from a Hearthsto...d`; `references/guide-research-policy.md`; `references/globalvalues-policy.md`; `references/card-behavior-policy.md`\n'

tests\test_skill_sync.py:97: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_docs_active_path.py::test_docs_define_source_backed_strong_without_second_gate
FAILED tests/test_docs_active_path.py::test_operator_docs_define_closure_diagnostics_as_summaries_not_gates
FAILED tests/test_skill_sync.py::test_skill_sync_propagates_source_backed_closure_guidance
3 failed, 37 passed in 2.54s
```

## Green Evidence

Focused docs and skill tests after implementation:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py tests/test_skill_sync.py -q
```

Output:

```text
........................................                                 [100%]
40 passed in 1.99s
```

Focused docs and skill tests after final wording cleanup:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_docs_active_path.py tests/test_skill_sync.py -q
```

Output:

```text
........................................                                 [100%]
40 passed in 0.97s
```

Initial installed skill sync check:

```powershell
python scripts/sync_installed_skill.py --check
```

Output:

```text
HSConfig skill drift detected: C:\Users\darbo\.codex\skills\hsconfig
- references/guide-research-policy.md: bytes_differ
- references/workflow.md: bytes_differ
- SKILL.md: bytes_differ
```

Installed skill sync:

```powershell
python scripts/sync_installed_skill.py
```

Output:

```text
Synced HSConfig skill to C:\Users\darbo\.codex\skills\hsconfig
```

Post-sync check:

```powershell
python scripts/sync_installed_skill.py --check
```

Output:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

Final post-test sync check:

```powershell
python scripts/sync_installed_skill.py --check
```

Output:

```text
HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

Whitespace check:

```powershell
git diff --check
```

Output:

```text
warning: in the working copy of '.agents/skills/hsconfig/SKILL.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of '.agents/skills/hsconfig/references/guide-research-policy.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of '.agents/skills/hsconfig/references/workflow.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'docs/operator/guide-research-policy.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'docs/operator/source-backed-strong-closure.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'docs/operator/source-builder-workflow.md', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_docs_active_path.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_skill_sync.py', LF will be replaced by CRLF the next time Git touches it
```

Exit code was 0; no whitespace errors were reported.

## Self-Review Notes

- Scope stayed within active operator docs, repo hsconfig skill text, relevant skill reference mirrors, focused docs/skill tests, and installed skill sync artifacts.
- No runtime implementation files were edited.
- The new diagnostic fields are documented as summaries only; the wording says they do not create apply gates, do not grant or deny runtime writes, and do not replace `reports/operator_summary.json` authority.
- The fresh command path uses `hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --online-source --auto-source --apply`.
- The installed skill was synced from the repo mirror and verified with `--check`.

## Concerns

- None.
