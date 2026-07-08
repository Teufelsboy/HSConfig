# Task 7 Report

Status: complete

Commit:
- `405b3af` - `refactor: move source workflow command ownership`

Files changed:
- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\commands\source_workflow.py`
- `C:\Users\darbo\Documents\HSConfig\src\hsconfig\cli.py`
- `C:\Users\darbo\Documents\HSConfig\tests\test_cli.py`

Tests and outputs:
- `python -m pytest tests/test_source_manifest_cli.py tests/test_draft_source_documents_cli.py tests/test_research_deck_cli.py tests/test_cli.py::test_source_workflow_command_module_no_longer_imports_hsconfig_cli -q` -> `8 passed in 10.93s`
- `python -m pytest tests/test_cli.py -q` -> `20 passed in 20.40s`
- `git diff --check` -> no diff errors; only LF/CRLF warnings from Git

Self-review notes:
- `hsconfig.commands.source_workflow` now owns the source-workflow payload functions and the research output directory guard.
- `hsconfig.cli` keeps dispatch and the build/research-contract path, but no longer owns the moved source-workflow payload helpers.
- The boundary test now passes because `source_workflow.py` no longer imports `hsconfig.cli`.
- No new dependency was added, and the source workflow command surface stayed unchanged.

## Fix Report

Root cause:
- `hsconfig.cli._build_preconfig_context()` still resolved the no-guide-sources fallback through a private helper name that should have been shared, so the prepare path could break when that helper ownership changed.

Fix:
- Moved the fallback helper into `hsconfig.guide_source_builder` as `research_required_guide_sources`.
- Updated `hsconfig.cli` and `hsconfig.commands.source_workflow` to import and use the shared helper.
- Expanded the prepare regression test so it exercises the fallback path and verifies the shared helper result is written.

Verification:
- `python -m pytest tests/test_prepare_cli.py tests/test_research_deck_cli.py tests/test_source_manifest_cli.py tests/test_draft_source_documents_cli.py tests/test_cli.py -q` -> `48 passed in 42.95s`
