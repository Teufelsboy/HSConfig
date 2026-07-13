# Task 1 Report: Shared Preconfig Context Authority

## Status

DONE

## Changed Files

- `src/hsconfig/preconfig_context.py`: added the single shared preconfig-context builder, including the research-only card-data intake report.
- `src/hsconfig/commands/source_workflow.py`: removed the research-local builder and delegated `research-deck` to the shared builder.
- `src/hsconfig/package_builder.py`: removed the prepare-local builder and delegated package/research-contract preparation to the shared builder.
- `tests/test_preconfig_context_parity.py`: added regression coverage for required shared context keys and duplicate-builder ownership.

## Commits

- `f8ff4d7 refactor: share preconfig context authority`

## Tests Run

- `python -m ruff check src/hsconfig/preconfig_context.py src/hsconfig/commands/source_workflow.py src/hsconfig/package_builder.py tests/test_preconfig_context_parity.py` - passed.
- `python -m pytest tests/test_preconfig_context_parity.py tests/test_autonomous_guide_workflow_e2e.py tests/test_prepare_cli.py -q -n 2 -rA` - 33 passed.

## Self-Review

- `build_preconfig_context` is the only implementation of the shared prepare/research context.
- `research-deck`, package build/prepare, and research-contract consume that single authority.
- Existing fetch and no-auto-research-fallback test seams are injected at caller boundaries; they do not duplicate context construction.
- No runtime write/apply path was added or changed. `reports/operator_summary.json` remains the normal apply authority.
- No runtime dependencies were added. Darkbishop Benedictus / Mind Spike semantics were not changed.

## Concerns

None.

## Review Fix: Research Contract Package Fetch Boundary

### Changed Files

- `src/hsconfig/package_builder.py`: made `research_contract_payload()` inject the same package-local context dependencies as `build_package_payload()`, including `fetch_latest_collectible_cards_fn=None` and `_research_required_guide_sources`.
- `tests/test_preconfig_context_parity.py`: added a regression test proving that the research-contract package path does not invoke the collectible-card fetch when no local feed is supplied.

### Commit

- `7954e99 fix: preserve research contract fetch boundary`

### Tests Run

- `python -m pytest tests/test_preconfig_context_parity.py tests/test_autonomous_guide_workflow_e2e.py tests/test_prepare_cli.py -q` - passed.

### Self-Review

- The research-contract path now preserves the former package-local no-collectible-fetch contract while retaining the package-local guide-source seam.
- The regression test was observed failing before the production change because the injectable collectible fetch was called once, then passing after the fix.
- No runtime write/apply path, generated runtime artifact, or unrelated implementation area was changed.
