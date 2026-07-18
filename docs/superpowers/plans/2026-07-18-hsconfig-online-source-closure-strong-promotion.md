# HSConfig Online Source Closure Strong Promotion Implementation Plan

## Goal

Promote as many of the current Wild deck packages as honestly possible from `SOURCE_BACKED_PARTIAL` to `SOURCE_BACKED_STRONG` by closing the first missing source action per deck with fetched full-text guide evidence, while preserving these non-negotiable contracts:

- No runtime package is blocked by source quality alone.
- No `default_only_runtime_surfaces` can exist in a Strong package.
- `SOURCE_BACKED_STRONG` is never granted from decklists, meta pages, stats pages, search snippets, or currentness-only context.
- `operator_summary.json` remains the only apply authority.
- Final repo state is current, verified, committed, and clean.

The implementation must be narrow: reuse the existing source-candidate registry, source-closure optimizer, research-deep acceptance loop, package generation CLI, and tests. Add code only if an existing surface cannot express a proven source-closure fact.

## Current Baseline

The repository has already implemented the canonical source/status synchronization layer and the source closure priority queue. The expected baseline before this plan is executed is:

- Branch: `codex/hsconfig-canonical-source-status-sync`
- `behind_origin_main`: `0`
- Worktree: clean
- Current matrix: 12 decks
- Strong packages: at least `1`
- Partial packages: remaining decks until proven source closure
- Apply blockers from source quality: `0`
- Default-only runtime surfaces: `0`
- ShadowPriest: not a priority source-closure row unless a new regression appears

## Target End State

After implementation:

- All 12 provided deck packages still generate load-safe runtime artifacts.
- Every generated package has `source_status_apply_blocking=false`.
- Every generated package has `default_only_runtime_surfaces=[]`.
- Decks with fetched full-text explicit guide claims and complete lowerable runtime surfaces are promoted to `SOURCE_BACKED_STRONG`.
- Decks without enough explicit full-text guide claims remain `SOURCE_BACKED_PARTIAL` with a concrete `first_missing_source_action`.
- Context-only sources remain useful for discovery/currentness but cannot promote Strong.
- New or changed source evidence is captured in the smallest durable surface: acceptance-loop results, candidate registry/proof docs, tests, or docs only where needed.
- Final verification passes and the worktree is clean.

## Deck Matrix

Use this exact matrix as the primary regression set:

```text
ShadowPriest|AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=|2737726722|c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602
CtAPaladin|AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=|2737744316|f9b54950-ca24-48cf-805e-bf620eab47a0
PirateRogue|AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==|2740734095|c1e87d43-5802-460b-b955-31ae458eb41a
BigShaman|AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==|2737735409|6b26f907-6f1e-44c8-a4e4-d14e9d51f819
Discolock|AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA|2740357533|55241397-ac74-4d46-a662-089e5858839c
TreantDruid|AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==|2740360895|a120a28b-1840-4032-a3c9-2da4c51338ed
ImbueMage|AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=|2740361888|49c05560-8b30-4d06-b3a2-a8b0ff36d005
MechPala|AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==|2740734214|8f011f55-8ae2-436c-b53a-315f280e8833
Kingslayer|AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=|2740733989|1292ff02-8ebe-47a5-90b1-9a1899acd6aa
Boarlock|AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA|2740361505|7727c718-c93c-47ca-a766-5612c3806f0f
PirateDH|AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==|2737737281|2bc184ed-b59a-4420-900d-b0ed3d153979
CuteWarrior|AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=|2750150375|a753f091-b770-4a06-8da8-59f1d5269f6b
```

## Files And Artifacts

Expected durable files to inspect or update:

- `src/hsconfig/source_closure_optimizer.py`
- `src/hsconfig/source_candidate_registry.py`
- `src/hsconfig/source_document_model.py`
- `docs/operator/source-candidate-proof-decks.json`
- `docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/*.json`
- `tests/test_source_closure_priority_queue.py`
- `tests/test_source_candidate_registry_matrix.py`
- `tests/test_universal_wild_no_block_matrix.py`
- `tests/test_claim_kind_runtime_contract.py`
- `.agents/skills/hsconfig/SKILL.md`

Generated, non-durable working areas:

- `outputs/2026-07-18-source-closure-strong-promotion/`
- `tmp/2026-07-18-source-closure-strong-promotion/`

Do not commit generated package folders, logs, caches, raw runtime evidence, or temporary web captures.

## Task 1: Currentness And Baseline Snapshot

Verify that the local repo is current and clean before touching files.

```powershell
Set-Location C:\Users\darbo\Documents\HSConfig
git fetch --all --prune --tags
python scripts/check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Acceptance:

- `behind_origin_main` is `0`.
- `clean_for_runtime_work` is `true`.
- `git status --short --branch` has no file rows under the branch line.

If the worktree is dirty before implementation, inspect the diff and protect user changes. Only commit or remove files that were created by this plan.

Capture the current priority queue with the existing optimizer surface:

```powershell
python -m pytest tests/test_source_closure_priority_queue.py -q
```

Then generate a readable baseline report from the most recent available package matrix. If no matrix is present, regenerate it in Task 5 before comparing promotions.

## Task 2: Source Discovery For Priority Decks

Use the current source-closure priority queue as the authoritative order. Do not manually pick favorites. Start with decks whose `first_missing_source_action` is closest to closure.

For each priority deck, search for current online guide pages and source pages that can contain full-text runtime decisions:

- Mulligan guides with explicit keep/throw rules.
- Matchup guides with explicit conditional keeps.
- Combo/setup guides with explicit play sequencing.
- Full deck guide articles with card-level game-plan text.

Classify each found URL into exactly one bucket:

- `full_text_claim_candidate`: fetched page can contain explicit lowerable runtime claims.
- `currentness_only`: decklist, meta tier list, matchup stats, archetype presence, or popularity page.
- `stale_support`: useful historical context but not current enough for Strong.
- `rejected`: inaccessible, snippet-only, duplicated, non-public, or unrelated.

Strong promotion is forbidden from `currentness_only`, `stale_support`, and `rejected`.

Use web lookup only for current, online data. Prefer official or primary-ish Hearthstone deck/guide pages where available, then high-signal public deck-guide sites. Record source URLs and retrieval dates in the acceptance-loop result files or candidate registry only after confirming the page content is accessible.

## Task 3: Fetched Source Ingestion And Claim Extraction

For every `full_text_claim_candidate`, run the existing source workflow with explicit source ingestion enabled. Do not add a parallel ingestion script unless the current CLI cannot fetch the URL, rank the source records, and normalize source documents.

Use the current inspected path for one deck/source pair:

```powershell
$deckName = "<DeckName>"
$deckCode = "<DeckCode>"
$sourceUrl = "<FetchedFullTextGuideUrl>"
$deckOut = "outputs/2026-07-18-source-closure-strong-promotion/$deckName/source-proof"

python -m hsconfig source-acquire `
  --deck-name $deckName `
  --deck-code $deckCode `
  --source-url $sourceUrl `
  --source-fetch-timeout-seconds 10 `
  --current-date 2026-07-18 `
  --out "$deckOut/01_source_acquisition" `
  --json

python -m hsconfig source-autopilot `
  --deck-name $deckName `
  --deck-code $deckCode `
  --source-search-results-json "$deckOut/01_source_acquisition/source_search_results.json" `
  --current-date 2026-07-18 `
  --out "$deckOut/02_source_autopilot" `
  --json

python -m hsconfig research-deck `
  --deck-name $deckName `
  --deck-code $deckCode `
  --source-documents-json "$deckOut/02_source_autopilot/source_documents.json" `
  --out "docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results/$deckName.json" `
  --json
```

The normal one-command path in Task 5 may also ingest repeated `--source-url` values directly through `configure`. The inspected path above is for proving how the fetched URL was converted into source records, source documents, and normalized guide claims.

Normalize only explicit, runtime-lowerable claims:

- `opening_hand_keep`
- `opening_hand_throw`
- `conditional_keep`
- `combo_sequence`
- `matchup_plan`
- `resource_plan`
- `effect_runtime_config`

Reject these as Strong evidence:

- Generic archetype description.
- Decklist inclusion alone.
- Meta tier placement.
- Winrate, popularity, or matchup stats without explicit action.
- Card text without guide advice.
- Search result snippets.
- User-supplied expectation without source text.

ShadowPriest-specific invariant:

- Darkbishop Benedictus / `SW_448` can support hero-power-transform/effect runtime configuration.
- It must not create an opening-hand keep rule unless the fetched guide explicitly says to keep the card in the mulligan.

## Task 4: Candidate Registry And Proof Update

Update `src/hsconfig/source_candidate_registry.py` only for source candidates that are useful beyond a one-off run.

For each new candidate, encode the correct ceiling:

- `context_only` for decklists, current meta pages, stats, and popularity sources.
- `runtime_claims_possible` for pages that may contain explicit mulligan/strategy/combo text after fetching.
- `strong_claim_source` only when the fetched full text produced explicit lowerable claims and the contract layer accepted them.

Update `docs/operator/source-candidate-proof-decks.json` in the same commit when registry semantics change. The proof doc must explain why the URL can or cannot close Strong.

Regression check:

```powershell
python -m pytest tests/test_source_candidate_registry_matrix.py -q
```

Acceptance:

- Context-only candidates cannot set `first_missing_source_action=null`.
- A candidate with no explicit lowerable claims cannot promote a package to `SOURCE_BACKED_STRONG`.
- Existing proof deck behavior remains stable unless newly fetched evidence proves a change.

## Task 5: Regenerate The 12-Deck Package Matrix

Regenerate all 12 packages into a fresh output folder. Use ignored output paths and an isolated runtime root.

Create the deck matrix in-memory in PowerShell and call the repo's current generator entrypoint:

```powershell
$outRoot = "outputs/2026-07-18-source-closure-strong-promotion"
$runtimeRoot = "tmp/2026-07-18-source-closure-strong-promotion/runtime"
New-Item -ItemType Directory -Force -Path $outRoot, $runtimeRoot | Out-Null

$decks = @(
  @{ Name="ShadowPriest"; Code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" },
  @{ Name="CtAPaladin"; Code="AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=" },
  @{ Name="PirateRogue"; Code="AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==" },
  @{ Name="BigShaman"; Code="AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==" },
  @{ Name="Discolock"; Code="AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA" },
  @{ Name="TreantDruid"; Code="AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==" },
  @{ Name="ImbueMage"; Code="AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=" },
  @{ Name="MechPala"; Code="AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==" },
  @{ Name="Kingslayer"; Code="AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=" },
  @{ Name="Boarlock"; Code="AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA" },
  @{ Name="PirateDH"; Code="AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==" },
  @{ Name="CuteWarrior"; Code="AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=" }
)

foreach ($deck in $decks) {
  python -m hsconfig configure `
    --deck-name $deck.Name `
    --deck-code $deck.Code `
    --runtime-root $runtimeRoot `
    --out "$outRoot/$($deck.Name)" `
    --online-source `
    --auto-source `
    --source-fetch-timeout-seconds 10 `
    --current-date 2026-07-18 `
    --json
}
```

For decks with newly verified guide URLs, repeat `--source-url "<public-guide-url>"` on the `configure` command for each useful URL. If no new URL was verified for a deck, run the command without explicit `--source-url` so the existing candidate registry remains the only seed input.

For each generated package, inspect `operator_summary.json`:

```powershell
Get-ChildItem $outRoot -Recurse -Filter operator_summary.json |
  ForEach-Object {
    $json = Get-Content $_.FullName -Raw | ConvertFrom-Json
    [PSCustomObject]@{
      Deck = Split-Path (Split-Path $_.FullName -Parent) -Leaf
      TechnicalValid = $json.technical_valid
      SourceStatus = $json.source_status
      SourceApplyBlocking = $json.source_status_apply_blocking
      DefaultOnlyCount = @($json.default_only_runtime_surfaces).Count
      FirstMissingSourceAction = $json.first_missing_source_action
    }
  } | Format-Table -AutoSize
```

Acceptance:

- Every deck has `technical_valid=true`.
- Every deck has `source_status_apply_blocking=false`.
- Every deck has `DefaultOnlyCount=0`.
- Strong decks have no `FirstMissingSourceAction`.
- Partial decks have a concrete, useful `FirstMissingSourceAction`.

## Task 6: Contract Tests And Narrow Code Changes

Only edit source code when verification proves one of these concrete needs:

- The fetched full-text source contains explicit lowerable claims, but the claim-kind normalizer rejects a supported claim.
- The source-status calculator treats context-only pages as Strong.
- The package generator creates a default-only runtime surface instead of an explicit diagnostic.
- The priority queue does not surface the next useful source-closure action.

For each code change, write or update the narrowest test first.

Required focused tests:

```powershell
python -m pytest tests/test_claim_kind_runtime_contract.py -q
python -m pytest tests/test_source_closure_priority_queue.py -q
python -m pytest tests/test_source_candidate_registry_matrix.py -q
python -m pytest tests/test_universal_wild_no_block_matrix.py -q
```

Acceptance:

- No test asserts Strong from default-only or context-only evidence.
- No test encodes a source promotion without full-text claim evidence.
- ShadowPriest keeps the Benedictus effect-only behavior and does not reintroduce a Benedictus mulligan keep.

## Task 7: Documentation And Skill Sync

Update docs only when implementation changes user/operator behavior.

Allowed documentation updates:

- `docs/operator/universal-wild-no-block-contract.md`: only if diagnostics or no-block semantics changed.
- `docs/operator/guide-research-policy.md`: only if source classification wording changed.
- `.agents/skills/hsconfig/SKILL.md`: only if the operational workflow changed.

After any skill doc change, run the existing skill sync or verification command used by the repo. If there is no sync command change, leave the installed skill untouched.

Acceptance:

- Docs say source quality is diagnostic for package generation.
- Docs say `SOURCE_BACKED_STRONG` requires fetched full-text explicit runtime claims.
- Docs say default-only runtime surfaces prevent Strong.
- Docs do not instruct operators to block deck creation for source partial.

## Task 8: Final Verification, Commit, And Clean Worktree

Run verification before claiming completion:

```powershell
python scripts/check_hsconfig_currentness.py --cwd . --json
python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_source_closure_priority_queue.py tests/test_source_candidate_registry_matrix.py tests/test_universal_wild_no_block_matrix.py -q
git diff --check
git status --short --branch
```

If implementation changed runtime-facing behavior, also run the full test suite:

```powershell
python -m pytest -q
```

Commit all intentional durable changes:

```powershell
git add `
  src/hsconfig/source_closure_optimizer.py `
  src/hsconfig/source_candidate_registry.py `
  src/hsconfig/source_document_model.py `
  docs/operator/source-candidate-proof-decks.json `
  docs/research/2026-07-17-hsconfig-source-contract-acceptance-loop/results `
  tests/test_source_closure_priority_queue.py `
  tests/test_source_candidate_registry_matrix.py `
  tests/test_universal_wild_no_block_matrix.py `
  tests/test_claim_kind_runtime_contract.py `
  docs/operator/universal-wild-no-block-contract.md `
  docs/operator/guide-research-policy.md `
  .agents/skills/hsconfig/SKILL.md
git commit -m "feat: close source-backed strong promotion gaps"
```

If implementation changed an additional repo-owned file, stage that file only after reviewing the diff and confirming it belongs to this plan.

Do not push unless explicitly requested by the user.

Final acceptance:

- The final `git status --short --branch` output contains only the branch line.
- The branch is still current with fetched remotes.
- The final response reports exact verification commands and the resulting status.

## Subagent Execution Split

Use subagents for implementation because the source work is parallelizable and evidence-heavy.

- Explorer: read-only, map current source-status pipeline, generator command, and priority queue behavior.
- Research agents: read-only, one or more agents search current online sources for independent deck groups and return URL classifications plus evidence summaries.
- Worker: single writer for registry, research-result, tests, and code changes after the main agent consolidates evidence.
- Reviewer: read-only, inspect diff for over-promotion, default-only leakage, ShadowPriest Benedictus regression, and dirty/generated artifacts.

Only the main agent decides final source promotions and performs the commit.

## Rollback Plan

If a source promotion proves unsound:

```powershell
git restore --staged <affected files>
git restore <affected files>
```

Use `git restore` only for files changed by this implementation. Preserve unrelated user changes. Re-run final verification after rollback.
