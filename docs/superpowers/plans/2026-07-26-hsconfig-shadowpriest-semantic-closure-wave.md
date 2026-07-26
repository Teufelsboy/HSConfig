# HSConfig ShadowPriest Semantic Closure Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make source authority, Mulligan lowering, CardID behavior, GlobalValues posture, physical runtime rows, validation, and operator reporting semantically honest for the exact 30-card ShadowPriest deck.

**Architecture:** Preserve the existing source-document → lifecycle → gameplan → surface compiler → operator-summary pipeline. Add canonical exact-deck evidence at acquisition, fail closed at each surface gate, keep Darkbishop on its existing CardID/linked-identity boundary, deduplicate physical rows through one shared identity helper, and make read-only preflight use the same strict validator inputs as `validate` and `apply`.

**Tech Stack:** Python 3.12+, pytest, standard-library `html.parser`, HearthSim `hearthstone.deckstrings`, existing `hsconfig` package, HearthRanger VisionAI JSON, PowerShell.

**Design reference:** `docs/superpowers/specs/2026-07-26-hsconfig-shadowpriest-semantic-closure-design.md`

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Work directly on the single `main` line. Do not create a branch, worktree, pull request, or second version.
- Before the first implementation task, run:

  ```powershell
  git fetch --all --prune --tags
  git status --short --branch
  git rev-list --left-right --count main...origin/main
  python scripts/check_hsconfig_currentness.py --cwd . --json
  gh pr list --repo Teufelsboy/HSConfig --state open --json number,title,headRefName
  ```

- Required starting state: clean `main`, `0 0` divergence, only remote branch `main`, no open pull request.
- Do not use HSTuner.
- Do not add a dependency.
- Do not add undocumented VisionAI keys or new runtime-condition atoms.
- Preserve the normal runtime surfaces:
  - `GlobalValues.json`
  - `Mulligan.json`
  - per-card `<CARDID>.json`
  - `Combo.json` only for an exact, ordered, timing-complete sequence
- `reports/operator_summary.json` remains the only normal apply authority.
- `semantic_handoff_status`, config quality, and the new assurance projection remain diagnostic. They must not become a second apply gate.
- This plan must not execute `hsconfig apply`, `write-runtime`, `configure --apply`, or any direct runtime copy.
- Do not commit generated packages, HearthRanger/Hearthstone logs, replay files, HDT exports, private runtime evidence, caches, or temporary audit directories.
- Every behavior-changing task follows RED → minimal GREEN → focused regression → diff review → commit → push.
- Push `main` after each commit so local and GitHub remain one version.
- Preserve exact deck identity:

  ```text
  Deck name: ShadowPriest
  Deck code: AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
  Deck-code SHA-256: fd7afada1f4a7f60bb269dc56188ddf83603e4bb0147a163d3e337be388917f2
  Main-deck cards: 30
  Unique CardIDs: 16
  Hero DBF ID: 813
  Format: FT_WILD
  Sideboards: 0
  ```

- A metadata-only CardID file is valid output but is not `runtime_emitted`.
- Exact-guide absence is an honest partial result. Never fabricate exact Mulligan authority, `SOURCE_BACKED_STRONG`, unsupported conditions, combo timing, or in-client optimality.

---

## Locked File And Interface Map

### Source content isolation

- Modify: `src/hsconfig/source_acquisition.py`
  - `extract_visible_text(html: str) -> dict[str, Any]`
  - `_VisibleTextParser`
- Test: `tests/test_source_acquisition.py`

### Exact deck identity and promotion

- Modify: `src/hsconfig/source_acquisition.py`
  - `_deck_match_evidence(...)`
  - new `_decoded_deckstring_candidates(...)`
  - new `_candidate_matches_target_deck(...)`
- Modify: `src/hsconfig/source_evidence_policy.py`
  - exact-guide lane and strong-promotion decisions
- Modify: `src/hsconfig/source_autopilot.py`
  - exact-scope preservation and strong-lane checks
- Modify: `src/hsconfig/source_document_model.py`
  - source lane and strong-promotion normalization
- Modify: `src/hsconfig/source_document_builder.py`
  - verify exact-scope evidence against the target deck fingerprint
- Modify: `tests/fixtures/source_pages/shadowpriest_current_guide.html`
- Create: `tests/fixtures/source_pages/shadowpriest_archetype_only_guide.html`
- Create: `tests/fixtures/source_pages/shadowpriest_source_url_map.json`
- Modify: `tests/fixtures/source_documents_shadowpriest_strong.json`
- Test: `tests/test_source_acquisition.py`
- Test: `tests/test_source_evidence_policy.py`
- Test: `tests/test_source_autopilot.py`
- Test: `tests/test_source_document_builder.py`
- Test: `tests/test_source_acquisition_strong_closure.py`
- Test: `tests/test_configure_online_source.py`
- Test: `tests/test_guide_source_depth.py`
- Test: `tests/test_lean_source_backed_strong_autopilot.py`
- Test: `tests/test_source_claim_compiler.py`
- Test: `tests/test_source_claim_lifecycle.py`

### Mulligan surface gate

- Modify: `src/hsconfig/source_document_model.py`
  - `can_lower_to_mulligan(...)`
- Test: `tests/test_claim_kind_runtime_contract.py`
- Test: `tests/test_mulligan_plan.py`
- Test: `tests/test_shadowpriest_source_contract_acceptance.py`
- Create: `tests/test_shadowpriest_partial_source_acceptance.py`

### Safe static card semantics

- Modify: `src/hsconfig/card_intent_taxonomy.py`
- Modify: `src/hsconfig/static_semantics.py`
- Modify: `src/hsconfig/mechanic_support.py`
- Modify: `src/hsconfig/semantic_runtime_gate.py`
- Test: `tests/test_card_intent_taxonomy.py`
- Test: `tests/test_static_semantics.py`
- Test: `tests/test_semantic_runtime_gate.py`
- Test: `tests/test_card_behavior_router.py`
- Test: `tests/test_shadowpriest_semantic_safety_wave.py`
- Test: `tests/test_shadowpriest_visionai_semantic_surface_contract.py`

### Runtime-row identity and physical readiness

- Create: `src/hsconfig/runtime_row_identity.py`
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/compile_cardid.py`
- Modify: `src/hsconfig/config_readiness.py`
- Test: `tests/test_runtime_row_identity.py`
- Test: `tests/test_card_behavior_router.py`
- Test: `tests/test_compile_cardid.py`
- Test: `tests/test_config_readiness.py`
- Test: `tests/test_shadowpriest_semantic_safety_wave.py`

### Strict preflight parity

- Modify: `src/hsconfig/contract_preflight.py`
- Test: `tests/test_contract_preflight.py`

### Assurance and documentation

- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/operator_guidance.py`
- Modify: `src/hsconfig/semantic_audit.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-contract-spine.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_operator_guidance.py`
- Test: `tests/test_semantic_audit.py`
- Test: `tests/test_docs_active_path.py`
- Test: `tests/test_operator_docs_contract_policy.py`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_skill_sync.py`

---

### Task 1: Isolate Guide Content From Page Chrome

**Files:**

- Modify: `src/hsconfig/source_acquisition.py`
- Test: `tests/test_source_acquisition.py`

**Interfaces:**

- Consumes: raw HTML passed to `extract_visible_text(html)`.
- Produces:

  ```python
  {
      "title": str,
      "text": str,
      "publication_values": list[str],
      "content_scope": "main_or_article" | "visible_body_fallback",
  }
  ```

- Downstream matching and extraction continue consuming `parsed["text"]`.

- [ ] **Step 1: Write the failing primary-content test**

  Add to `tests/test_source_acquisition.py`:

  ```python
  from hsconfig.source_acquisition import extract_visible_text


  def test_visible_text_prefers_main_and_excludes_page_chrome():
      parsed = extract_visible_text(
          """
          <html>
            <head>
              <title>ShadowPriest Guide</title>
              <meta property="article:published_time" content="2026-07-25T00:00:00Z">
            </head>
            <body>
              <header>Help Sign In</header>
              <nav>Decks Cards Forums</nav>
              <main>
                <h1>Exact ShadowPriest plan</h1>
                <p>Keep the documented one-drop against slow decks.</p>
              </main>
              <aside>Follow Us On Twitter</aside>
              <footer>Privacy Terms</footer>
            </body>
          </html>
          """
      )

      assert parsed["title"] == "ShadowPriest Guide"
      assert parsed["content_scope"] == "main_or_article"
      assert "Exact ShadowPriest plan" in parsed["text"]
      assert "Keep the documented one-drop" in parsed["text"]
      assert "Help Sign In" not in parsed["text"]
      assert "Follow Us On Twitter" not in parsed["text"]
      assert parsed["publication_values"] == ["2026-07-25T00:00:00Z"]
  ```

- [ ] **Step 2: Write the failing sanitized fallback test**

  ```python
  def test_visible_text_uses_sanitized_body_when_primary_content_is_absent():
      parsed = extract_visible_text(
          """
          <html>
            <head><title>Legacy guide</title></head>
            <body>
              <nav>Help Sign In</nav>
              <section><h1>Mulligan</h1><p>Keep CARD_A.</p></section>
              <footer>Follow Us On Twitter</footer>
            </body>
          </html>
          """
      )

      assert parsed["content_scope"] == "visible_body_fallback"
      assert parsed["text"] == "Mulligan Keep CARD_A."
  ```

- [ ] **Step 3: Run the tests and verify RED**

  ```powershell
  pytest tests/test_source_acquisition.py -q
  ```

  Expected failure: `content_scope` is absent and page-chrome text is retained.

- [ ] **Step 4: Implement scoped visible-text collection**

  In `_VisibleTextParser`, add:

  ```python
  PRIMARY_CONTENT_TAGS = {"main", "article"}
  EXCLUDED_CONTENT_TAGS = {
      "nav",
      "header",
      "footer",
      "aside",
      "form",
      "script",
      "style",
      "noscript",
  }
  ```

  Track:

  ```python
  self.primary_text_parts: list[str] = []
  self.fallback_text_parts: list[str] = []
  self._primary_depth = 0
  self._excluded_depth = 0
  ```

  Update start/end handling so excluded content is ignored and visible text
  inside `<main>` or `<article>` is also added to `primary_text_parts`.
  `handle_data()` must retain title handling and then use:

  ```python
  if self._excluded_depth:
      return
  self.fallback_text_parts.append(text)
  if self._primary_depth:
      self.primary_text_parts.append(text)
  ```

  Update `extract_visible_text()`:

  ```python
  primary = " ".join(parser.primary_text_parts).strip()
  fallback = " ".join(parser.fallback_text_parts).strip()
  return {
      "title": " ".join(parser.title_parts).strip(),
      "text": primary or fallback,
      "publication_values": parser.publication_values,
      "content_scope": (
          "main_or_article" if primary else "visible_body_fallback"
      ),
  }
  ```

  Ensure title text is not also appended to fallback content.

- [ ] **Step 5: Run focused regressions**

  ```powershell
  pytest tests/test_source_acquisition.py tests/test_configure_online_source.py tests/test_source_document_builder.py -q
  ```

  Expected: all pass; source titles and publication metadata remain unchanged.

- [ ] **Step 6: Review, commit, and push**

  ```powershell
  git diff --check
  git diff -- src/hsconfig/source_acquisition.py tests/test_source_acquisition.py
  git add src/hsconfig/source_acquisition.py tests/test_source_acquisition.py
  git commit -m "fix: isolate guide content from page chrome"
  git push origin main
  ```

---

### Task 2: Establish Canonical Exact-Deck Source Identity

**Files:**

- Modify: `src/hsconfig/source_acquisition.py`
- Modify: `src/hsconfig/source_evidence_policy.py`
- Modify: `src/hsconfig/source_autopilot.py`
- Modify: `src/hsconfig/source_document_model.py`
- Modify: `src/hsconfig/source_document_builder.py`
- Modify: `tests/fixtures/source_pages/shadowpriest_current_guide.html`
- Create: `tests/fixtures/source_pages/shadowpriest_archetype_only_guide.html`
- Create: `tests/fixtures/source_pages/shadowpriest_source_url_map.json`
- Modify: `tests/fixtures/source_documents_shadowpriest_strong.json`
- Test: `tests/test_source_acquisition.py`
- Test: `tests/test_source_evidence_policy.py`
- Test: `tests/test_source_autopilot.py`
- Test: `tests/test_source_document_builder.py`
- Test: `tests/test_source_acquisition_strong_closure.py`
- Test: `tests/test_configure_online_source.py`
- Test: `tests/test_guide_source_depth.py`
- Test: `tests/test_lean_source_backed_strong_autopilot.py`
- Test: `tests/test_source_claim_compiler.py`
- Test: `tests/test_source_claim_lifecycle.py`

**Interfaces:**

- Produces `deck_match_scope="exact_deck_matched"` only from a successfully
  decoded source deckstring whose canonical main-deck fingerprint equals
  `deck_identity["deck_fingerprint"]`.
- Name plus card overlap produces `archetype_matched`, never an exact scope.
- `deck_match["exact_deck_evidence"]` contains only counts, fingerprints,
  hashes, and match booleans; it never contains a raw deckstring.

- [ ] **Step 1: Create exact and archetype-only guide fixtures**

  Add this line inside the `<main>` content of
  `tests/fixtures/source_pages/shadowpriest_current_guide.html`:

  ```html
  <p>Exact deck code: AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=</p>
  ```

  Create `tests/fixtures/source_pages/shadowpriest_archetype_only_guide.html`:

  ```html
  <!doctype html>
  <html lang="en">
    <head>
      <meta property="article:published_time" content="2026-07-25T00:00:00Z">
      <title>Wild Aggro Shadow Priest Archetype Guide</title>
    </head>
    <body>
      <main>
        <h1>Wild Aggro Shadow Priest Archetype Guide</h1>
        <p>Mind Blast and Papercraft Angel support aggressive hero pressure.</p>
        <h2>Mulligan</h2>
        <p>Keep Papercraft Angel and Twilight Deceptor.</p>
      </main>
    </body>
  </html>
  ```

  Create `tests/fixtures/source_pages/shadowpriest_source_url_map.json`:

  ```json
  {
    "https://example.test/shadowpriest-exact": "tests/fixtures/source_pages/shadowpriest_current_guide.html",
    "https://example.test/shadowpriest-archetype": "tests/fixtures/source_pages/shadowpriest_archetype_only_guide.html"
  }
  ```

  In the first guide document in
  `tests/fixtures/source_documents_shadowpriest_strong.json`, add:

  ```json
  "deck_match_scope": "exact_deck_matched",
  "deck_match": {
    "exact_deck_evidence": {
      "matched": true,
      "matched_deck_fingerprint": "831b989cf8d076bff87848b4d0d6f382c9d306fddea7619017f0c361bfc92327"
    }
  }
  ```

  This fixture intentionally models the exact-source acceptance branch. Do not
  add exact evidence to real archetype-only fixtures.

- [ ] **Step 2: Write exact-match and wrong-list acquisition tests**

  Add these imports and helpers to `tests/test_source_acquisition.py`:

  ```python
  import json

  from hsconfig.deck_identity import build_deck_identity
  from hsconfig.deckstring_decode import decode_deck_code


  SHADOWPRIEST_DECK_CODE = (
      "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQF"
      "yKEGxKgG/KgG17oG1cEGAAA="
  )


  def _exact_shadowpriest_identity() -> dict:
      decoded = decode_deck_code(SHADOWPRIEST_DECK_CODE)
      return build_deck_identity(
          deck_name="ShadowPriest",
          deck_code=SHADOWPRIEST_DECK_CODE,
          cards=decoded["cards"],
          hero_dbf_id=decoded["hero_dbf_id"],
          format=decoded["format"],
          sideboards=decoded["sideboards"],
      )


  def _fixture_fetcher(filename: str):
      page = FIXTURES / filename

      def fetcher(
          url: str,
          timeout_seconds: float,
      ) -> tuple[int, str, bytes]:
          del url, timeout_seconds
          return 200, "text/html", page.read_bytes()

      return fetcher
  ```

  Then add:

  ```python
  def test_exact_source_deckstring_promotes_to_exact_deck_scope():
      shadowpriest_identity = _exact_shadowpriest_identity()
      report = collect_public_source_records(
          deck_name="ShadowPriest",
          deck_identity=shadowpriest_identity,
          source_urls=["https://example.test/exact"],
          current_date="2026-07-26",
          fetcher=_fixture_fetcher("shadowpriest_current_guide.html"),
          resolver=_public_resolver,
      )

      record = report["source_records"][0]
      assert record["deck_match_scope"] == "exact_deck_matched"
      exact = record["deck_match"]["exact_deck_evidence"]
      assert exact["matched"] is True
      assert exact["matched_deck_fingerprint"] == shadowpriest_identity["deck_fingerprint"]
      assert "deck_code" not in exact
      assert "AAEBA" not in json.dumps(record)
  ```

  Add:

  ```python
  def test_name_and_card_overlap_remains_archetype_only():
      shadowpriest_identity = _exact_shadowpriest_identity()
      report = collect_public_source_records(
          deck_name="ShadowPriest",
          deck_identity=shadowpriest_identity,
          source_urls=["https://example.test/archetype"],
          current_date="2026-07-26",
          fetcher=_fixture_fetcher("shadowpriest_archetype_only_guide.html"),
          resolver=_public_resolver,
      )

      record = report["source_records"][0]
      assert record["deck_match_scope"] == "archetype_matched"
      assert record["strong_promotion_eligible"] is False
      assert "exact_deck_match_required" in record["promotion_blockers"]
  ```

  Add a test with a valid but different 40-card deckstring and assert
  `archetype_matched`, not `exact_deck_matched`.

  Add to `tests/test_source_document_builder.py`:

  ```python
  def test_explicit_exact_scope_requires_matching_target_fingerprint():
      bundle = build_source_document_bundle(
          deck_identity={
              "deck_name": "ShadowPriest",
              "deck_fingerprint": "target-fingerprint",
              "cards": [{"card_id": "TOY_381", "count": 2}],
          },
          card_metadata={},
          source_documents=[
              {
                  "source_url": "https://example.test/guide",
                  "source_title": "ShadowPriest guide",
                  "source_family": "guide",
                  "retrieved_at": "2026-07-26T00:00:00Z",
                  "deck_match_scope": "exact_deck_matched",
                  "deck_match": {
                      "exact_deck_evidence": {
                          "matched": True,
                          "matched_deck_fingerprint": "different-fingerprint",
                      }
                  },
                  "claims": [
                      {
                          "claim_kind": "mulligan_keep",
                          "cards": ["TOY_381"],
                          "evidence_text_short": "Keep Papercraft Angel.",
                          "source_confidence": "high",
                      }
                  ],
              }
          ],
          current_date="2026-07-26",
      )

      claim = bundle["claims"][0]
      assert claim["deck_match_scope"] == "archetype_matched"
  ```

- [ ] **Step 3: Run the acquisition tests and verify RED**

  ```powershell
  pytest tests/test_source_acquisition.py -q
  ```

  Expected: the current overlap heuristic returns `deck_matched` or lacks
  exact-deck evidence.

- [ ] **Step 4: Add decoded candidate extraction**

  In `src/hsconfig/source_acquisition.py`, import:

  ```python
  from hashlib import sha256

  from hsconfig.deck_identity import stable_deck_fingerprint
  from hsconfig.deckstring_decode import decode_deck_code
  ```

  Add:

  ```python
  DECKSTRING_TOKEN_RE = re.compile(
      r"(?<![A-Za-z0-9+/])([A-Za-z0-9+/]{24,}={0,2})(?![A-Za-z0-9+/=])"
  )
  ```

  Add a helper with this return shape:

  ```python
  def _decoded_deckstring_candidates(text: str) -> dict[str, Any]:
      tokens = list(dict.fromkeys(DECKSTRING_TOKEN_RE.findall(text)))
      decoded_candidates: list[dict[str, Any]] = []
      for token in tokens:
          try:
              decoded = decode_deck_code(token)
          except Exception:
              continue
          fingerprint = stable_deck_fingerprint(
              (str(card["card_id"]), int(card["count"]))
              for card in decoded["cards"]
          )
          decoded_candidates.append(
              {
                  "deck_code_hash": sha256(token.encode("utf-8")).hexdigest(),
                  "deck_fingerprint": fingerprint,
                  "hero_dbf_id": decoded.get("hero_dbf_id"),
                  "format": decoded.get("format"),
                  "card_count_total": decoded.get("card_count_total"),
                  "sideboard_count": decoded.get("sideboard_count"),
              }
          )
      return {
          "candidate_count": len(tokens),
          "decoded_candidates": decoded_candidates,
      }
  ```

  Add:

  ```python
  def _candidate_matches_target_deck(
      candidate: Mapping[str, Any],
      deck_identity: Mapping[str, Any],
  ) -> bool:
      if candidate["deck_fingerprint"] != deck_identity.get("deck_fingerprint"):
          return False
      for key in ("hero_dbf_id", "format", "card_count_total", "sideboard_count"):
          target = deck_identity.get(key)
          observed = candidate.get(key)
          if target is not None and observed is not None and observed != target:
              return False
      return True
  ```

- [ ] **Step 5: Replace overlap-as-exact matching**

  In `_deck_match_evidence(...)`:

  - call `_decoded_deckstring_candidates()` on sanitized text;
  - set `candidates = candidate_evidence["decoded_candidates"]`;
  - collect candidates matching the target;
  - set `scope="exact_deck_matched"` when at least one candidate matches;
  - otherwise set `archetype_matched` when the deck name and two or more cards
    overlap;
  - otherwise retain `card_overlap` or `unknown`.

  Add this diagnostic object:

  ```python
  "exact_deck_evidence": {
      "candidate_count": candidate_evidence["candidate_count"],
      "decoded_candidate_count": len(candidates),
      "matched": bool(matches),
      "matched_deck_fingerprint": (
          str(matches[0]["deck_fingerprint"]) if matches else ""
      ),
      "candidate_deck_code_hashes": sorted(
          str(candidate["deck_code_hash"]) for candidate in candidates
      ),
  }
  ```

  Do not return the raw candidate token.

- [ ] **Step 6: Make exact scope the only strong guide scope**

  In `source_evidence_policy.py`, `source_autopilot.py`, and
  `source_document_model.py`:

  - replace strong checks accepting `deck_matched` or
    `deck_or_archetype_matched` with `exact_deck_matched`;
  - map exact public guides to `deck_matched_public_guide`;
  - map overlap-only guides to `archetype_matched_public_guide`;
  - attach blocker `exact_deck_match_required` when a full-text guide is
    otherwise current but not exact;
  - keep static official-card semantics unchanged.

  The strong predicate must be equivalent to:

  ```python
  return (
      promotion_eligible
      and source_visibility == "full_text"
      and source_lane == "deck_matched_public_guide"
      and deck_match_scope == "exact_deck_matched"
      and freshness_status in {"", "current"}
  )
  ```

  In `source_document_builder.py`, add:

  ```python
  def _document_has_exact_deck_evidence(
      document: dict[str, Any],
      deck_identity: dict[str, Any],
  ) -> bool:
      deck_match = document.get("deck_match", {})
      if not isinstance(deck_match, dict):
          return False
      exact = deck_match.get("exact_deck_evidence", {})
      if not isinstance(exact, dict) or exact.get("matched") is not True:
          return False
      return (
          _clean_text(exact.get("matched_deck_fingerprint", ""))
          == _clean_text(deck_identity.get("deck_fingerprint", ""))
          != ""
      )
  ```

  Change `_claim_deck_match_scope()` so an explicit
  `exact_deck_matched` value is preserved only when
  `_document_has_exact_deck_evidence()` returns true. Otherwise downgrade it to
  `archetype_matched`. Legacy `deck_matched` and
  `deck_or_archetype_matched` values also normalize to
  `archetype_matched`. Update the deck-name inheritance check to accept the new
  `exact_deck_matched` and `archetype_matched` scopes.

- [ ] **Step 7: Run source-policy regressions**

  ```powershell
  pytest tests/test_source_acquisition.py tests/test_source_evidence_policy.py tests/test_source_autopilot.py tests/test_source_document_builder.py tests/test_source_acquisition_strong_closure.py tests/test_configure_online_source.py tests/test_guide_source_depth.py tests/test_lean_source_backed_strong_autopilot.py tests/test_source_claim_compiler.py tests/test_source_claim_lifecycle.py -q
  ```

  Expected:

  - exact fixture is exact and promotion-eligible;
  - archetype-only and different-deck fixtures are not strong;
  - static semantics remain eligible for their existing non-guide lane.

- [ ] **Step 8: Review, commit, and push**

  ```powershell
  git diff --check
  git diff -- src/hsconfig/source_acquisition.py src/hsconfig/source_evidence_policy.py src/hsconfig/source_autopilot.py src/hsconfig/source_document_model.py src/hsconfig/source_document_builder.py tests/fixtures/source_pages tests/fixtures/source_documents_shadowpriest_strong.json tests/test_source_acquisition.py tests/test_source_evidence_policy.py tests/test_source_autopilot.py tests/test_source_document_builder.py tests/test_source_acquisition_strong_closure.py tests/test_configure_online_source.py tests/test_guide_source_depth.py tests/test_lean_source_backed_strong_autopilot.py tests/test_source_claim_compiler.py tests/test_source_claim_lifecycle.py
  git add src/hsconfig/source_acquisition.py src/hsconfig/source_evidence_policy.py src/hsconfig/source_autopilot.py src/hsconfig/source_document_model.py src/hsconfig/source_document_builder.py tests/fixtures/source_pages/shadowpriest_current_guide.html tests/fixtures/source_pages/shadowpriest_archetype_only_guide.html tests/fixtures/source_pages/shadowpriest_source_url_map.json tests/fixtures/source_documents_shadowpriest_strong.json tests/test_source_acquisition.py tests/test_source_evidence_policy.py tests/test_source_autopilot.py tests/test_source_document_builder.py tests/test_source_acquisition_strong_closure.py tests/test_configure_online_source.py tests/test_guide_source_depth.py tests/test_lean_source_backed_strong_autopilot.py tests/test_source_claim_compiler.py tests/test_source_claim_lifecycle.py
  git commit -m "fix: require canonical exact deck source identity"
  git push origin main
  ```

---

### Task 3: Gate Guide Mulligan Claims On Exact Deck Evidence

**Files:**

- Modify: `src/hsconfig/source_document_model.py`
- Test: `tests/test_claim_kind_runtime_contract.py`
- Test: `tests/test_mulligan_plan.py`
- Test: `tests/test_shadowpriest_source_contract_acceptance.py`
- Create: `tests/test_shadowpriest_partial_source_acceptance.py`

**Interfaces:**

- Public-guide Mulligan claims lower only when:

  ```text
  deck_match_scope == exact_deck_matched
  promotion_eligible == true
  source_visibility == full_text
  source_lane == deck_matched_public_guide
  ```

- Rejected guide claims use stable reasons:
  - `guide_mulligan_requires_exact_deck_match`
  - `guide_mulligan_claim_not_promotion_eligible`
  - `guide_mulligan_requires_full_text`
- Policy-backed autonomous Mulligan remains independent and labeled.

- [ ] **Step 1: Write direct surface-gate tests**

  Add to `tests/test_claim_kind_runtime_contract.py`:

  ```python
  def _guide_keep(**overrides):
      claim = {
          "claim_kind": "mulligan_keep",
          "cards": ["TOY_381"],
          "source_type": "public_guide",
          "source_lane": "deck_matched_public_guide",
          "source_visibility": "full_text",
          "deck_match_scope": "exact_deck_matched",
          "promotion_eligible": True,
          "claim_readiness": "guide_backed",
          "trust_ceiling": "runtime_lowerable",
      }
      claim.update(overrides)
      return claim


  def test_exact_public_guide_keep_can_lower_to_mulligan():
      assert can_lower_to_mulligan(_guide_keep()).allowed is True


  def test_archetype_only_public_guide_keep_is_report_only():
      decision = can_lower_to_mulligan(
          _guide_keep(
              source_lane="archetype_matched_public_guide",
              deck_match_scope="archetype_matched",
              promotion_eligible=False,
          )
      )

      assert decision.allowed is False
      assert decision.reason == "guide_mulligan_requires_exact_deck_match"


  def test_non_promoting_exact_guide_keep_is_report_only():
      decision = can_lower_to_mulligan(
          _guide_keep(promotion_eligible=False)
      )

      assert decision.allowed is False
      assert decision.reason == "guide_mulligan_claim_not_promotion_eligible"
  ```

- [ ] **Step 2: Write Mulligan-plan provenance tests**

  Add to `tests/test_mulligan_plan.py`:

  ```python
  def test_archetype_guide_keep_is_suppressed_before_policy_fallback():
      plan = build_mulligan_plan(
          deck_name="ShadowPriest",
          claims=[
              {
                  "claim_id": "wrong-guide-keep",
                  "claim_kind": "mulligan_keep",
                  "cards": ["SW_444"],
                  "source_type": "public_guide",
                  "source_lane": "archetype_matched_public_guide",
                  "source_visibility": "full_text",
                  "deck_match_scope": "archetype_matched",
                  "promotion_eligible": False,
                  "claim_readiness": "guide_backed",
              }
          ],
          card_roles={},
          deck_cards=[],
          allow_policy_backed=False,
      )

      assert plan["rules"] == []
      assert plan["suppressed_rules"][0]["reason"] == (
          "guide_mulligan_requires_exact_deck_match"
      )
      assert plan["quality"]["source_backed_keep_rule_count"] == 0
  ```

- [ ] **Step 3: Run tests and verify RED**

  ```powershell
  pytest tests/test_claim_kind_runtime_contract.py tests/test_mulligan_plan.py -q
  ```

  Expected: archetype-only guide claims currently lower.

- [ ] **Step 4: Implement the public-guide Mulligan gate**

  In `source_document_model.py`, add:

  ```python
  def _is_public_guide_claim(claim: Mapping[str, Any]) -> bool:
      return _source_type(claim) in {"community_guide", "public_guide"}


  def _guide_mulligan_gate_reason(claim: Mapping[str, Any]) -> str | None:
      if not _is_public_guide_claim(claim):
          return None
      if _normalized_text(claim.get("deck_match_scope")) != "exact_deck_matched":
          return "guide_mulligan_requires_exact_deck_match"
      if not _bool_value(claim.get("promotion_eligible", False)):
          return "guide_mulligan_claim_not_promotion_eligible"
      if _normalized_text(claim.get("source_visibility")) != "full_text":
          return "guide_mulligan_requires_full_text"
      if _normalized_text(claim.get("source_lane")) != "deck_matched_public_guide":
          return "guide_mulligan_requires_exact_deck_match"
      return None
  ```

  In `can_lower_to_mulligan()`, after the claim-kind check and before the
  generic runtime gate:

  ```python
  guide_reason = _guide_mulligan_gate_reason(claim)
  if guide_reason is not None:
      return SurfaceGateDecision(False, guide_reason, claim_kind, "mulligan")
  ```

- [ ] **Step 5: Add exact-versus-partial acceptance coverage**

  Extend `tests/test_shadowpriest_source_contract_acceptance.py` so the exact
  guide fixture proves:

  ```python
  assert source_record["deck_match_scope"] == "exact_deck_matched"
  assert plan["quality"]["source_backed_keep_rule_count"] >= 1
  assert "TOY_381" in {
      row["card"] for row in plan["rules"] if row["action"] == "hold"
  }
  ```

  Create `tests/test_shadowpriest_partial_source_acceptance.py` and build the
  package with `shadowpriest_archetype_only_guide.html`. Assert:

  ```python
  assert source_record["deck_match_scope"] == "archetype_matched"
  assert source_record["strong_promotion_eligible"] is False
  assert mulligan_plan["quality"]["source_backed_keep_rule_count"] == 0
  assert "guide_mulligan_requires_exact_deck_match" in {
      row["reason"] for row in mulligan_plan["suppressed_rules"]
  }
  assert operator["source_backed_status"] != "SOURCE_BACKED_STRONG"
  ```

  If policy-backed Mulligan is enabled by the package fixture, assert every
  concrete keep has:

  ```python
  assert row["source_type"] == "policy_backed_autonomous_mulligan"
  ```

- [ ] **Step 6: Run focused acceptance**

  ```powershell
  pytest tests/test_claim_kind_runtime_contract.py tests/test_mulligan_plan.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py -q
  ```

- [ ] **Step 7: Review, commit, and push**

  ```powershell
  git diff --check
  git diff -- src/hsconfig/source_document_model.py tests/test_claim_kind_runtime_contract.py tests/test_mulligan_plan.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py
  git add src/hsconfig/source_document_model.py tests/test_claim_kind_runtime_contract.py tests/test_mulligan_plan.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py
  git commit -m "fix: require exact guide authority for mulligan"
  git push origin main
  ```

---

### Task 4: Lower Only The Safe Static Card Surfaces

**Files:**

- Modify: `src/hsconfig/card_intent_taxonomy.py`
- Modify: `src/hsconfig/static_semantics.py`
- Modify: `src/hsconfig/mechanic_support.py`
- Modify: `src/hsconfig/semantic_runtime_gate.py`
- Test: `tests/test_card_intent_taxonomy.py`
- Test: `tests/test_static_semantics.py`
- Test: `tests/test_semantic_runtime_gate.py`
- Test: `tests/test_card_behavior_router.py`
- Test: `tests/test_shadowpriest_semantic_safety_wave.py`
- Test: `tests/test_shadowpriest_visionai_semantic_surface_contract.py`

**Interfaces:**

- Adds semantic family `summon_trigger_board_engine`.
- It maps only to `CARDID.json:OnBoardBonus`.
- `reciprocal_hero_burn` becomes report-only until a proven health condition
  exists.
- `damage_aura_amplifier` keeps only `OnBoardBonus`; its unconditional
  `BeforePlayCardBonus` is removed.
- Existing Darkbishop ownership remains:
  - one `BeforeUseHeroPowerBonus`
  - no body priority
  - no Mulligan keep
- A separate `gameplan_posture` claim remains the only GlobalValues authority.

- [ ] **Step 1: Write trigger-engine classification tests**

  Add to `tests/test_card_intent_taxonomy.py`:

  ```python
  @pytest.mark.parametrize(
      ("card_id", "text"),
      [
          ("TOY_518", "After you summon a Pirate, give it +1 Attack."),
          ("WON_065", "After you summon a minion, give it +1 Health."),
      ],
  )
  def test_summon_trigger_board_engines_are_not_classified_as_summoners(
      card_id,
      text,
  ):
      result = classify_card_intent(text, card_identity=card_id)

      assert result.reason == "summon_trigger_board_engine"
      assert result.value == "8"
  ```

- [ ] **Step 2: Write static-semantics tests**

  Add to `tests/test_static_semantics.py`:

  ```python
  @pytest.mark.parametrize(
      ("card_id", "text"),
      [
          ("TOY_518", "After you summon a Pirate, give it +1 Attack."),
          ("WON_065", "After you summon a minion, give it +1 Health."),
      ],
  )
  def test_summon_trigger_engine_claim_uses_on_board_surface(card_id, text):
      records = build_static_semantics_source_records(
          {
              "deck_name": "ShadowPriest",
              "cards": [{"card_id": card_id, "count": 2}],
          },
          {
              card_id: {
                  "card_id": card_id,
                  "name": card_id,
                  "type": "MINION",
                  "text": text,
              }
          },
          build_id="fixture",
      )

      claim = next(
          claim
          for claim in records[0]["claims"]
          if claim.get("mechanic") == "summon_trigger_board_engine"
      )
      assert claim["runtime_block"] == "OnBoardBonus"
      assert claim["trust_ceiling"] == "static_semantics"
  ```

- [ ] **Step 3: Write runtime-gate safety tests**

  Add to `tests/test_semantic_runtime_gate.py`:

  ```python
  def test_summon_trigger_engine_allows_only_on_board_value():
      allowed = decide_semantic_runtime(
          semantic_reason="summon_trigger_board_engine",
          source_lane="official_static_semantics",
          condition="*",
          runtime_block="OnBoardBonus",
          claim_kind="mechanic_usage",
      )
      rejected = decide_semantic_runtime(
          semantic_reason="summon_trigger_board_engine",
          source_lane="official_static_semantics",
          condition="*",
          runtime_block="BeforePlayCardBonus",
          claim_kind="mechanic_usage",
      )

      assert allowed.allowed is True
      assert rejected == SemanticRuntimeDecision(
          False,
          "semantic_surface_not_expressible",
      )


  @pytest.mark.parametrize("reason", ["reciprocal_hero_burn"])
  def test_health_dependent_static_burn_stays_report_only(reason):
      decision = decide_semantic_runtime(
          semantic_reason=reason,
          source_lane="official_static_semantics",
          condition="*",
          runtime_block="BeforePlayCardBonus",
          claim_kind="mechanic_usage",
      )

      assert decision.allowed is False
      assert decision.reason == "semantic_surface_not_expressible"
  ```

  Add a second parameterized call using
  `source_lane="deck_matched_public_guide"` and assert the wildcard reciprocal
  burn row is still rejected. Add a test proving `damage_aura_amplifier`
  allows `OnBoardBonus` but rejects `BeforePlayCardBonus` for both official
  static and exact-guide lanes. Recognized card semantics must not bypass the
  safety surface merely because the guide itself is exact.

- [ ] **Step 4: Run tests and verify RED**

  ```powershell
  pytest tests/test_card_intent_taxonomy.py tests/test_static_semantics.py tests/test_semantic_runtime_gate.py -q
  ```

- [ ] **Step 5: Add the trigger-engine semantic family**

  In `card_intent_taxonomy.py`, before generic summon handling, add:

  ```python
  if (
      _has_any(normalized, ("after you summon", "whenever you summon"))
      and _has_any(normalized, ("give it +", "give that minion +"))
  ) or identity_reason == "summon_trigger_board_engine":
      return CardIntentClassification(
          reason="summon_trigger_board_engine",
          value="8",
          band="medium",
          matched_signals=_signals(
              ("after_you_summon", "after you summon" in normalized),
              ("pirate_trigger", "pirate" in normalized),
              ("persistent_buff_engine", "give it +" in normalized),
          ),
      )
  ```

  Extend `_card_identity_reason()`:

  ```python
  "TOY_518".lower(): "summon_trigger_board_engine",
  "treasure distributor": "summon_trigger_board_engine",
  "WON_065".lower(): "summon_trigger_board_engine",
  "ship's chirurgeon": "summon_trigger_board_engine",
  "ship’s chirurgeon": "summon_trigger_board_engine",
  ```

  In `static_semantics.py`, detect:

  ```python
  if (
      _contains(lowered, "after you summon")
      and _contains(lowered, "give")
  ):
      _add(
          families,
          evidence,
          "summon_trigger_board_engine",
          "text",
          "persistent post-summon buff trigger",
      )
  ```

- [ ] **Step 6: Register the documented OnBoard surface**

  Add to `MECHANIC_SUPPORT` in `mechanic_support.py`:

  ```python
  "summon_trigger_board_engine": {
      "support_level": "partial",
      "normal_path_surfaces": ["CARDID.json:OnBoardBonus"],
      "warning_boundary": (
          "Board value is representable; exact summon sequencing and "
          "trigger eligibility remain broader bot evaluation."
      ),
  },
  ```

  In `semantic_runtime_gate.py`:

  - add `reciprocal_hero_burn` to
    `REPORT_ONLY_WITHOUT_EXACT_RUNTIME_EVIDENCE`;
  - remove its `STATIC_ACTION_SURFACES` entry;
  - change `damage_aura_amplifier` to allow only:

    ```python
    {
        ("OnBoardBonus", "card_role", "*"),
        ("OnBoardBonus", "mechanic_usage", "*"),
    }
    ```

  - add:

    ```python
    "summon_trigger_board_engine": {
        ("OnBoardBonus", "card_role", "*"),
        ("OnBoardBonus", "mechanic_usage", "*"),
    },
    ```

  Change `decide_semantic_runtime()` so recognized semantic reasons are locked
  before the general guide-lane allowance:

  ```python
  if semantic_reason in REPORT_ONLY_WITHOUT_EXACT_RUNTIME_EVIDENCE:
      return SemanticRuntimeDecision(
          False,
          "semantic_surface_not_expressible",
      )

  allowed_surfaces = STATIC_ACTION_SURFACES.get(semantic_reason)
  if allowed_surfaces is not None:
      if (runtime_block, claim_kind, condition) in allowed_surfaces:
          return SemanticRuntimeDecision(
              True,
              "semantic_surface_supported",
          )
      return SemanticRuntimeDecision(
          False,
          "semantic_surface_not_expressible",
      )

  if source_lane in STATIC_SOURCE_LANES:
      return SemanticRuntimeDecision(
          False,
          "semantic_surface_not_proven",
      )
  if source_lane in GUIDE_SOURCE_LANES:
      return SemanticRuntimeDecision(True, "guide_surface_supported")
  return SemanticRuntimeDecision(False, "semantic_surface_not_proven")
  ```

  This preserves guide lowering for semantics that do not have a recognized
  locked contract while preventing exact guides from reintroducing known unsafe
  wildcard rows.

- [ ] **Step 7: Lock the ShadowPriest semantic surface**

  Replace duplicate-oriented expectations in
  `tests/test_shadowpriest_semantic_safety_wave.py` with semantic ownership
  expectations. Before Task 5 deduplication, assert presence by set rather than
  exact row count:

  ```python
  SAFE_ACTIVE_SURFACES = {
      "DS1_233": {"BeforePlayCardBonus"},
      "REV_290": {"BeforePlayCardBonus"},
      "SW_446": {"OnBoardBonus"},
      "SW_448": {"BeforeUseHeroPowerBonus"},
      "TOY_381": {"OnBoardBonus"},
      "TOY_518": {"OnBoardBonus"},
      "WON_065": {"OnBoardBonus"},
  }

  REPORT_ONLY_CARD_IDS = {
      "CFM_637",
      "DRG_056",
      "GVG_009",
      "NX2_019",
      "SCH_514",
      "SW_444",
      "VAC_419",
      "VAC_512",
      "YOD_032",
  }
  ```

  Assert that report-only payloads contain only:

  ```python
  {"GameCardId", "ConfigComment"}
  ```

  Assert:

  - no `InHandPlayPriority` in any ShadowPriest CardID file;
  - no `BeforeBattlecryTargetBonus` for `GVG_009` or `SW_444`;
  - no `BeforePlayCardBonus` for `SW_448`;
  - `SW_448` is absent from Mulligan holds;
  - partial-source GlobalValues have no changed posture keys.

- [ ] **Step 8: Run focused semantic tests**

  ```powershell
  pytest tests/test_card_intent_taxonomy.py tests/test_static_semantics.py tests/test_semantic_runtime_gate.py tests/test_card_behavior_router.py tests/test_shadowpriest_semantic_safety_wave.py tests/test_shadowpriest_visionai_semantic_surface_contract.py -q
  ```

- [ ] **Step 9: Review, commit, and push**

  ```powershell
  git diff --check
  git diff -- src/hsconfig/card_intent_taxonomy.py src/hsconfig/static_semantics.py src/hsconfig/mechanic_support.py src/hsconfig/semantic_runtime_gate.py tests/test_card_intent_taxonomy.py tests/test_static_semantics.py tests/test_semantic_runtime_gate.py tests/test_card_behavior_router.py tests/test_shadowpriest_semantic_safety_wave.py tests/test_shadowpriest_visionai_semantic_surface_contract.py
  git add src/hsconfig/card_intent_taxonomy.py src/hsconfig/static_semantics.py src/hsconfig/mechanic_support.py src/hsconfig/semantic_runtime_gate.py tests/test_card_intent_taxonomy.py tests/test_static_semantics.py tests/test_semantic_runtime_gate.py tests/test_card_behavior_router.py tests/test_shadowpriest_semantic_safety_wave.py tests/test_shadowpriest_visionai_semantic_surface_contract.py
  git commit -m "fix: lower only safe ShadowPriest semantics"
  git push origin main
  ```

---

### Task 5: Deduplicate Runtime Rows And Derive Readiness From Physical Payloads

**Files:**

- Create: `src/hsconfig/runtime_row_identity.py`
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/compile_cardid.py`
- Modify: `src/hsconfig/config_readiness.py`
- Create: `tests/test_runtime_row_identity.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_compile_cardid.py`
- Modify: `tests/test_config_readiness.py`
- Modify: `tests/test_shadowpriest_semantic_safety_wave.py`

**Interfaces:**

- Produces:

  ```python
  card_behavior_signature(row) -> tuple[str, str, str, str]
  card_behavior_surface_key(row) -> tuple[str, str, str]
  deduplicate_card_behavior_rows(
      rows: Iterable[Mapping[str, Any]],
  ) -> CardBehaviorDedupeResult
  ```

- `CardBehaviorDedupeResult.rows` contains unique rows.
- Exact duplicates merge provenance.
- Same card/block/condition with different values produces a conflict and no
  physical row for that surface.
- `build_config_readiness_report()` accepts a mapping of filename to parsed
  payload; filename-only collections are rejected.

- [ ] **Step 1: Write the shared-identity unit tests**

  Create `tests/test_runtime_row_identity.py`:

  ```python
  import pytest

  from hsconfig.runtime_row_identity import (
      card_behavior_signature,
      deduplicate_card_behavior_rows,
  )


  def _row(value="8", claim_id="claim-a"):
      return {
          "card_id": "REV_290",
          "behavior_block": "BeforePlayCardBonus",
          "condition": "*",
          "value": value,
          "claim_id": claim_id,
          "source_claim_ids": [claim_id],
          "source_refs": [f"source-{claim_id}"],
      }


  def test_exact_runtime_duplicates_merge_provenance_once():
      result = deduplicate_card_behavior_rows(
          [_row(claim_id="claim-a"), _row(claim_id="claim-b")]
      )

      assert result.conflicts == []
      assert result.merged_duplicate_count == 1
      assert len(result.rows) == 1
      assert card_behavior_signature(result.rows[0]) == (
          "REV_290",
          "BeforePlayCardBonus",
          "*",
          "8",
      )
      assert result.rows[0]["source_claim_ids"] == ["claim-a", "claim-b"]
      assert result.rows[0]["merged_claim_ids"] == ["claim-a", "claim-b"]


  def test_conflicting_values_fail_closed_for_the_surface():
      result = deduplicate_card_behavior_rows(
          [_row(value="6", claim_id="claim-a"), _row(value="8", claim_id="claim-b")]
      )

      assert result.rows == []
      assert result.conflicts == [
          {
              "card_id": "REV_290",
              "behavior_block": "BeforePlayCardBonus",
              "condition": "*",
              "values": ["6", "8"],
              "reason": "conflicting_runtime_values",
              "claim_ids": ["claim-a", "claim-b"],
          }
      ]
  ```

- [ ] **Step 2: Run the new test and verify RED**

  ```powershell
  pytest tests/test_runtime_row_identity.py -q
  ```

  Expected: module import fails.

- [ ] **Step 3: Implement the shared row-identity module**

  Create `src/hsconfig/runtime_row_identity.py` with:

  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from typing import Any, Iterable, Mapping


  @dataclass(frozen=True)
  class CardBehaviorDedupeResult:
      rows: list[dict[str, Any]]
      conflicts: list[dict[str, Any]]
      merged_duplicate_count: int


  def card_behavior_signature(
      row: Mapping[str, Any],
  ) -> tuple[str, str, str, str]:
      return (
          str(row["card_id"]),
          str(row["behavior_block"]),
          str(row.get("condition", "*")),
          str(row["value"]),
      )


  def card_behavior_surface_key(
      row: Mapping[str, Any],
  ) -> tuple[str, str, str]:
      signature = card_behavior_signature(row)
      return signature[:3]
  ```

  Implement `deduplicate_card_behavior_rows()` in two passes:

  1. group by `card_behavior_surface_key`;
  2. when a group has more than one value, add one sorted conflict and emit no
     row for that surface;
  3. otherwise preserve the first row, merge sorted unique
     `source_claim_ids`, `source_refs`, and `claim_id` values into
     `merged_claim_ids`;
  4. sort output rows by `card_behavior_signature`.

  Use this implementation:

  ```python
  def _string_values(value: Any) -> list[str]:
      if isinstance(value, list):
          return [str(item) for item in value if str(item)]
      if value is None or not str(value):
          return []
      return [str(value)]


  def deduplicate_card_behavior_rows(
      rows: Iterable[Mapping[str, Any]],
  ) -> CardBehaviorDedupeResult:
      groups: dict[
          tuple[str, str, str],
          list[dict[str, Any]],
      ] = {}
      for raw_row in rows:
          row = dict(raw_row)
          groups.setdefault(
              card_behavior_surface_key(row),
              [],
          ).append(row)

      unique_rows: list[dict[str, Any]] = []
      conflicts: list[dict[str, Any]] = []
      merged_duplicate_count = 0

      for surface_key in sorted(groups):
          group = groups[surface_key]
          values = sorted({str(row["value"]) for row in group})
          claim_ids = sorted(
              {
                  claim_id
                  for row in group
                  for claim_id in (
                      _string_values(row.get("claim_id"))
                      + _string_values(row.get("merged_claim_ids"))
                  )
              }
          )
          if len(values) > 1:
              card_id, behavior_block, condition = surface_key
              conflicts.append(
                  {
                      "card_id": card_id,
                      "behavior_block": behavior_block,
                      "condition": condition,
                      "values": values,
                      "reason": "conflicting_runtime_values",
                      "claim_ids": claim_ids,
                  }
              )
              continue

          merged = dict(group[0])
          merged["source_claim_ids"] = sorted(
              {
                  item
                  for row in group
                  for item in _string_values(
                      row.get("source_claim_ids")
                  )
              }
          )
          merged["source_refs"] = sorted(
              {
                  item
                  for row in group
                  for item in _string_values(row.get("source_refs"))
              }
          )
          merged["merged_claim_ids"] = claim_ids
          merged_duplicate_count += len(group) - 1
          unique_rows.append(merged)

      unique_rows.sort(key=card_behavior_signature)
      return CardBehaviorDedupeResult(
          rows=unique_rows,
          conflicts=conflicts,
          merged_duplicate_count=merged_duplicate_count,
      )
  ```

  Export:

  ```python
  __all__ = (
      "CardBehaviorDedupeResult",
      "card_behavior_signature",
      "card_behavior_surface_key",
      "deduplicate_card_behavior_rows",
  )
  ```

- [ ] **Step 4: Apply dedupe in the semantic router**

  At the end of `route_card_behavior_surfaces()`:

  ```python
  dedupe = deduplicate_card_behavior_rows(rows)
  suppressed.extend(dedupe.conflicts)
  return {
      "rows": dedupe.rows,
      "suppressed": suppressed,
      "option_resolution": option_resolution,
      "merged_duplicate_row_count": dedupe.merged_duplicate_count,
      "conflicting_runtime_rows": dedupe.conflicts,
  }
  ```

  Update `tests/test_card_behavior_router.py` to prove:

  - Cathedral duplicate claims produce one physical-plan row;
  - identical Darkbishop claims produce one row;
  - conflicting values produce no row and one suppression reason.

- [ ] **Step 5: Add defensive physical compiler enforcement**

  In `compile_cardid.py`, deduplicate the combined behavior rows before
  `_append_explicit_behavior_rows()`:

  ```python
  dedupe = deduplicate_card_behavior_rows(
      [
          {**dict(row), "card_id": card_id}
          for row in card.get("behavior_rows", [])
      ]
  )
  if dedupe.conflicts:
      raise ValueError(
          f"{card_id}: conflicting runtime values: {dedupe.conflicts}"
      )
  _append_explicit_behavior_rows(
      config,
      deck_name,
      card_id,
      dedupe.rows,
  )
  ```

  Add compiler tests proving exact duplicates emit one JSON value row and
  conflicts raise before a package can be written.

- [ ] **Step 6: Reject filename-only readiness**

  Change `build_config_readiness_report()` to:

  ```python
  emitted_cardid_files: Mapping[str, Mapping[str, Any]] | None = None,
  ```

  Change `_emitted_cardid_file_map()`:

  ```python
  if emitted_cardid_files is None:
      return {}, set()
  if not isinstance(emitted_cardid_files, Mapping):
      raise TypeError(
          "emitted_cardid_files must map filename to parsed payload"
      )
  ```

  A card enters `meaningful_cardids` only when
  `_has_runtime_effect_rows(payload)` returns true.

  Update all test callers:

  - use `{}` when no physical file exists;
  - use `{"CARD_A.json": payload}` for a meaningful file;
  - assert metadata-only payloads do not count;
  - assert a list such as `["CARD_A.json"]` raises `TypeError`.

- [ ] **Step 7: Replace duplicate expectations with exact uniqueness**

  In `tests/test_shadowpriest_semantic_safety_wave.py`, assert:

  ```python
  EXPECTED_RUNTIME_ROWS = {
      ("DS1_233", "BeforePlayCardBonus", "*", "12"),
      ("REV_290", "BeforePlayCardBonus", "*", "8"),
      ("SW_446", "OnBoardBonus", "*", "10"),
      ("SW_448", "BeforeUseHeroPowerBonus", "*", "10"),
      ("TOY_381", "OnBoardBonus", "*", "8"),
      ("TOY_518", "OnBoardBonus", "*", "8"),
      ("WON_065", "OnBoardBonus", "*", "8"),
  }
  ```

  Build signatures from every physical CardID `values` row and assert:

  ```python
  assert set(signatures) == EXPECTED_RUNTIME_ROWS
  assert len(signatures) == len(set(signatures))
  ```

  Keep the existing runtime-row trace parity assertion:

  ```python
  assert trace["physical_cardid_runtime_rows"] == trace["reported_cardid_runtime_rows"]
  assert trace["unreported_runtime_rows"] == []
  assert trace["reported_rows_missing_runtime"] == []
  ```

- [ ] **Step 8: Run focused row/readiness tests**

  ```powershell
  pytest tests/test_runtime_row_identity.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_shadowpriest_semantic_safety_wave.py -q
  ```

- [ ] **Step 9: Review, commit, and push**

  ```powershell
  git diff --check
  git diff -- src/hsconfig/runtime_row_identity.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/compile_cardid.py src/hsconfig/config_readiness.py tests/test_runtime_row_identity.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_shadowpriest_semantic_safety_wave.py
  git add src/hsconfig/runtime_row_identity.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/compile_cardid.py src/hsconfig/config_readiness.py tests/test_runtime_row_identity.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_shadowpriest_semantic_safety_wave.py
  git commit -m "fix: deduplicate physical CardID runtime rows"
  git push origin main
  ```

---

### Task 6: Make Contract Preflight Match Strict Validate And Apply

**Files:**

- Modify: `src/hsconfig/contract_preflight.py`
- Modify: `tests/test_contract_preflight.py`

**Interfaces:**

- `build_package_contract_preflight(package)` loads the same baseline/profile
  artifacts and calls `validate_config_package()` with the same strict flags as
  `validate_payload()` and `apply_payload()`.
- `ready_to_use_from_operator_summary` is true only when validation passes,
  config quality is clean, and existing operator authority fields agree.
- No change to `evaluate_apply_gate()` or any write path.

- [ ] **Step 1: Write strict parity tests**

  Add this helper to `tests/test_contract_preflight.py`:

  ```python
  def _write_strict_globalvalues_reports(package: Path) -> None:
      globalvalues_path = (
          package
          / "CustomConfig"
          / "shadowpriest"
          / "GlobalValues.json"
      )
      globalvalues = json.loads(
          globalvalues_path.read_text(encoding="utf-8")
      )
      _write_json(
          package / "reports" / "globalvalues_baseline.json",
          globalvalues,
      )
      _write_json(
          package / "reports" / "globalvalues_profile.json",
          {
              "key_count": len(globalvalues),
              "keys": {
                  key: {"status": "baseline_confirmed"}
                  for key in globalvalues
              },
              "generated_overlay_keys": [],
              "expected_overlay_keys": [],
              "missing_overlay_keys": [],
              "summary": {
                  "all_expected_overlay_keys_accounted_for": True
              },
          },
      )
  ```

  Add:

  ```python
  def test_package_preflight_fails_when_required_globalvalues_profile_is_missing(
      tmp_path,
  ):
      package = _contract_preflight_clean_package(tmp_path)
      _write_strict_globalvalues_reports(package)
      (package / "reports" / "globalvalues_profile.json").unlink()

      report = build_package_contract_preflight(package)

      assert report["validate_config_package_status"] == "failed"
      assert report["ready_to_use_from_operator_summary"] is False
      assert "validate_config_package_failed" in report["failures"]


  def test_package_preflight_ready_requires_clean_quality(
      tmp_path,
      monkeypatch,
  ):
      package = _contract_preflight_clean_package(tmp_path)
      _write_strict_globalvalues_reports(package)
      monkeypatch.setattr(
          "hsconfig.config_quality_contract.build_config_quality_report",
          lambda package: {
              "status": "attention",
              "checks": {},
              "problems": [{"check": "fixture_attention"}],
          },
      )

      report = build_package_contract_preflight(package)

      assert report["validate_config_package_status"] == "passed"
      assert report["config_quality_status"] == "attention"
      assert report["ready_to_use_from_operator_summary"] is False
  ```

  Add a command-level parity test using the existing command payload instead of
  stdout parsing:

  ```python
  from hsconfig.commands.apply import validate_payload


  def test_validate_payload_and_preflight_agree_on_missing_profile(tmp_path):
      package = _contract_preflight_clean_package(tmp_path)
      _write_strict_globalvalues_reports(package)
      (package / "reports" / "globalvalues_profile.json").unlink()

      validation, exit_code = validate_payload(
          Namespace(package=str(package))
      )
      preflight = build_package_contract_preflight(package)

      assert exit_code == 1
      assert validation["status"] == "failed"
      assert preflight["validate_config_package_status"] == "failed"
      assert preflight["ready_to_use_from_operator_summary"] is False
  ```

- [ ] **Step 2: Run tests and verify RED**

  ```powershell
  pytest tests/test_contract_preflight.py -q
  ```

- [ ] **Step 3: Load the required package validation artifacts**

  In `contract_preflight.py`, import:

  ```python
  from hsconfig.package_io import read_optional_profile, read_required_baseline
  ```

  Replace the preflight validation call with:

  ```python
  baseline = read_required_baseline(package_path)
  profile = read_optional_profile(package_path)
  validation = validate_config_package(
      package_path,
      globalvalues_baseline=baseline,
      globalvalues_profile=profile,
      require_complete_package=True,
      require_globalvalues_profile=True,
  )
  ```

  Keep the existing exception-to-failed-report boundary.

- [ ] **Step 4: Make readiness include validation and quality**

  Replace the readiness projection with:

  ```python
  ready_to_use = (
      validation_status == "passed"
      and config_quality_status == "clean"
      and technical_status == "VALID_PACKAGE"
      and runtime_apply_mode == "load_safe_apply"
      and runtime_apply_allowed is True
      and runtime_apply_authority == normal_authority
  )
  ```

  Do not use this field inside the runtime apply gate.

- [ ] **Step 5: Run focused parity and apply-boundary tests**

  ```powershell
  pytest tests/test_contract_preflight.py tests/test_apply_gate.py tests/test_apply_authority_boundary.py tests/test_runtime_apply.py -q
  ```

  Expected:

  - preflight and validate agree;
  - apply authority remains `operator_summary.json`;
  - no config-quality or semantic-handoff field becomes a write gate.

- [ ] **Step 6: Review, commit, and push**

  ```powershell
  git diff --check
  git diff -- src/hsconfig/contract_preflight.py tests/test_contract_preflight.py
  git add src/hsconfig/contract_preflight.py tests/test_contract_preflight.py
  git commit -m "fix: align preflight with strict package validation"
  git push origin main
  ```

---

### Task 7: Separate Load Safety, Source Authority, Semantic Closure, And Optimality

**Files:**

- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/operator_guidance.py`
- Modify: `src/hsconfig/semantic_audit.py`
- Modify: `src/hsconfig/package_builder.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_operator_guidance.py`
- Test: `tests/test_semantic_audit.py`

**Interfaces:**

- Produces:

  ```python
  operator_summary["configuration_assurance"] = {
      "load_safety": "proven" | "not_proven",
      "source_authority": "exact_deck" | "archetype_only" | "partial" | "unproven",
      "semantic_closure": "closed" | "attention" | "insufficient_evidence",
      "in_client_behavior": "not_proven_by_pre_run_contract",
      "optimality_claim_allowed": False,
      "runtime_gate_impact": "none",
  }
  ```

- Does not alter `runtime_apply_allowed`, `runtime_apply_mode`,
  `runtime_apply_contract`, or `apply_policy`.
- Semantic audit reports metadata completeness separately from physical runtime
  coverage.

- [ ] **Step 1: Write operator-assurance tests**

  Add to `tests/test_operator_summary.py`:

  ```python
  def test_partial_load_safe_package_does_not_claim_optimality():
      summary = build_operator_summary(
          deck_name="ShadowPriest",
          deck_code="fixture",
          technical_validation={"status": "passed"},
          guide_source_depth={
              "source_depth_status": "static_semantics_only",
              "claim_count": 1,
          },
          generated_files=[
              "CustomConfig/shadowpriest/GlobalValues.json",
              "CustomConfig/shadowpriest/Mulligan.json",
          ],
          source_claim_gap_report={
              "summary": {
                  "first_missing_chain": {
                      "card_id": "VAC_419",
                      "first_missing_link": "needs_condition_lowering",
                      "next_action": "add_documented_health_condition",
                  },
                  "source_quality_lane_counts": {
                      "official_static_semantics": 1
                  },
              }
          },
          card_behavior_plan_report={
              "rows": [],
              "suppressed": [
                  {"reason": "semantic_surface_not_expressible"}
              ],
          },
      )

      assurance = summary["configuration_assurance"]
      assert assurance["load_safety"] == "proven"
      assert assurance["source_authority"] == "partial"
      assert assurance["semantic_closure"] == "attention"
      assert assurance["in_client_behavior"] == (
          "not_proven_by_pre_run_contract"
      )
      assert assurance["optimality_claim_allowed"] is False
      assert assurance["runtime_gate_impact"] == "none"
      assert summary["runtime_apply_allowed"] is True
  ```

  Add exact and archetype-only mappings:

  ```python
  from hsconfig.operator_summary import _configuration_source_authority


  @pytest.mark.parametrize(
      ("source_status", "source_lanes", "expected"),
      [
          (
              "SOURCE_BACKED_STRONG",
              ["deck_matched_public_guide"],
              "exact_deck",
          ),
          (
              "SOURCE_BACKED_PARTIAL",
              ["archetype_matched_public_guide"],
              "archetype_only",
          ),
          (
              "SOURCE_BACKED_PARTIAL",
              ["official_static_semantics"],
              "partial",
          ),
          ("SOURCE_NEEDED", [], "unproven"),
      ],
  )
  def test_assurance_source_authority_mapping(
      source_status,
      source_lanes,
      expected,
  ):
      assert _configuration_source_authority(
          source_status,
          source_lanes,
      ) == expected
  ```

- [ ] **Step 2: Write semantic-audit rendering tests**

  Add to `tests/test_semantic_audit.py`:

  ```python
  def test_semantic_audit_separates_metadata_from_runtime_coverage():
      markdown = render_semantic_audit_markdown(
          {
              "semantic_enrichment_status": "complete",
              "deckwide_effects": [],
              "cards": [],
              "semantic_enrichment_warnings": [],
          },
          config_readiness_report={
              "summary": {
                  "total_cards": 16,
                  "runtime_emitted": 7,
                  "report_only_supported": 9,
                  "globalvalues_only": 0,
              }
          },
      )

      assert "Metadata enrichment status: `complete`" in markdown
      assert "Runtime-emitted cards: `7/16`" in markdown
      assert "Report-only supported cards: `9`" in markdown
      assert "In-client behavior: `not proven`" in markdown
  ```

- [ ] **Step 3: Run tests and verify RED**

  ```powershell
  pytest tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_semantic_audit.py -q
  ```

- [ ] **Step 4: Add the non-gating assurance projection**

  In `operator_summary.py`, derive source authority with:

  ```python
  def _configuration_source_authority(
      source_status: str,
      source_lanes: list[str],
  ) -> str:
      if (
          source_status == "SOURCE_BACKED_STRONG"
          and "deck_matched_public_guide" in source_lanes
      ):
          return "exact_deck"
      if "archetype_matched_public_guide" in source_lanes:
          return "archetype_only"
      if source_status == "SOURCE_BACKED_PARTIAL":
          return "partial"
      return "unproven"
  ```

  After the existing semantic-handoff projection, add:

  ```python
  source_lanes = _operator_source_lanes(
      source_claim_gap_report or {},
      source_to_runtime_explainability_report or {},
  )
  configuration_assurance = {
      "load_safety": (
          "proven" if load_safe_to_install else "not_proven"
      ),
      "source_authority": _configuration_source_authority(
          source_status_resolution.source_backed_status,
          source_lanes,
      ),
      "semantic_closure": str(
          semantic_handoff.get(
              "semantic_handoff_status",
              "insufficient_evidence",
          )
      ),
      "in_client_behavior": "not_proven_by_pre_run_contract",
      "optimality_claim_allowed": False,
      "runtime_gate_impact": "none",
  }
  ```

  Add it to the summary and project it unchanged through
  `operator_guidance.py`. Do not reference it from apply-gate code.

- [ ] **Step 5: Extend semantic audit with physical readiness**

  Change:

  ```python
  def render_semantic_audit_markdown(
      report: dict[str, Any],
      *,
      config_readiness_report: dict[str, Any] | None = None,
  ) -> str:
  ```

  Render:

  ```markdown
  Metadata enrichment status: `<status>`

  ## Runtime Semantic Coverage

  - Runtime-emitted cards: `<runtime>/<total>`
  - Report-only supported cards: `<report_only>`
  - GlobalValues-only cards: `<globalvalues_only>`
  - In-client behavior: `not proven`
  ```

  In `package_builder.py`, pass the already-built
  `config_readiness_report` into the renderer.

- [ ] **Step 6: Run operator and apply-boundary regressions**

  ```powershell
  pytest tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_semantic_audit.py tests/test_apply_gate.py tests/test_apply_authority_boundary.py tests/test_runtime_apply.py -q
  ```

- [ ] **Step 7: Review, commit, and push**

  ```powershell
  git diff --check
  git diff -- src/hsconfig/operator_summary.py src/hsconfig/operator_guidance.py src/hsconfig/semantic_audit.py src/hsconfig/package_builder.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_semantic_audit.py
  git add src/hsconfig/operator_summary.py src/hsconfig/operator_guidance.py src/hsconfig/semantic_audit.py src/hsconfig/package_builder.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_semantic_audit.py
  git commit -m "docs: separate configuration assurance dimensions"
  git push origin main
  ```

---

### Task 8: Update Operator And Installed Skill Contracts

**Files:**

- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-contract-spine.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `tests/test_docs_active_path.py`
- Modify: `tests/test_operator_docs_contract_policy.py`
- Modify: `tests/test_skill_files.py`
- Modify: `tests/test_skill_sync.py`

**Interfaces:**

- Documents the code contracts established in Tasks 1–7.
- Preserves `operator_summary.json` as the only normal apply authority.
- Installed skill remains byte-for-byte synchronized through the existing sync
  script.

- [ ] **Step 1: Add exact documentation contract tests**

  Add this shared phrase tuple to the appropriate docs/skill tests:

  ```python
  REQUIRED_SEMANTIC_CLOSURE_PHRASES = (
      "`exact_deck_matched` requires a decoded canonical deck fingerprint match.",
      "Guide-backed Mulligan claims require `exact_deck_matched`.",
      "`hero_power_transform` remains a CardID-linked effect and does not authorize aggressive GlobalValues by itself.",
      "A metadata-only CardID file is not `runtime_emitted`.",
      "Load safety does not prove in-client optimality.",
      "`configuration_assurance` is diagnostic and has `runtime_gate_impact=none`.",
  )
  ```

  Assert all six statements appear in `docs/operator/README.md` or its directly
  linked policy page, and in `.agents/skills/hsconfig/SKILL.md` or its directly
  linked references.

- [ ] **Step 2: Run docs tests and verify RED**

  ```powershell
  pytest tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py -q
  ```

- [ ] **Step 3: Document source and Mulligan authority**

  In `docs/operator/guide-research-policy.md` and the matching skill reference,
  document:

  - source deckstring decoding;
  - canonical main-deck fingerprint equality;
  - exact versus archetype-only scope;
  - exact-guide Mulligan authority;
  - policy-backed fallback labeling;
  - why a different 40-card guide cannot authorize the target 30-card deck.

  Update the source-contract matrix row:

  ```markdown
  | `mulligan_keep` | runtime_lowerable | `Mulligan.json` | Public-guide claims require `exact_deck_matched`; policy-backed fallback remains separately labeled. |
  ```

- [ ] **Step 4: Document Darkbishop and GlobalValues ownership**

  Keep the `hero_power_transform` row on the CardID surface:

  ```markdown
  | `hero_power_transform` | suppressed_or_conditional | per-card CardID | May prioritize the exactly linked transformed Hero Power; never creates body priority or a Mulligan keep by itself. |
  ```

  In the GlobalValues policy, state:

  - only `gameplan_posture` authorizes posture overlays;
  - archetype-only source leaves posture values at baseline;
  - a neutral generated `MyHeroPowerValue=1.00` is not an aggressive overlay;
  - numeric runtime tuning still requires runtime evidence.

- [ ] **Step 5: Document card and row boundaries**

  In the card behavior policy, document:

  - `summon_trigger_board_engine -> OnBoardBonus`;
  - reciprocal burn without a proven health condition is report-only;
  - state-dependent mechanics remain report-only;
  - runtime signature
    `(card_id, behavior_block, condition, value)`;
  - exact duplicate provenance merge;
  - conflicting values fail closed;
  - metadata-only files do not count as runtime-emitted.

- [ ] **Step 6: Document assurance language**

  Add the exact sentence:

  ```markdown
  Load safety does not prove in-client optimality.
  ```

  Explain the six `configuration_assurance` fields and explicitly state that
  `runtime_gate_impact=none`.

- [ ] **Step 7: Sync and test the installed skill**

  ```powershell
  python scripts/sync_installed_skill.py
  python scripts/sync_installed_skill.py --check
  pytest tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py -q
  ```

  Expected:

  ```text
  HSConfig skill is in sync
  ```

- [ ] **Step 8: Review, commit, and push**

  ```powershell
  git diff --check
  git diff -- docs/operator .agents/skills/hsconfig tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py
  git add docs/operator/README.md docs/operator/source-contract-spine.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/guide-research-policy.md .agents/skills/hsconfig/references/globalvalues-policy.md .agents/skills/hsconfig/references/card-behavior-policy.md tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py
  git commit -m "docs: define exact semantic closure contract"
  git push origin main
  ```

---

### Task 9: Prove The Exact And Partial ShadowPriest Packages Read-Only

**Files:**

- Modify only the Task 1–8 owner file when a verification failure identifies a
  causal defect.
- Do not commit generated package output.

**Interfaces:**

- Produces complete repository verification and two temporary read-only
  packages:
  - exact-source fixture package;
  - current archetype-only source package.
- Performs no runtime write.

- [ ] **Step 1: Run the focused semantic closure suite**

  ```powershell
  pytest tests/test_source_acquisition.py tests/test_source_evidence_policy.py tests/test_source_autopilot.py tests/test_claim_kind_runtime_contract.py tests/test_mulligan_plan.py tests/test_card_intent_taxonomy.py tests/test_static_semantics.py tests/test_semantic_runtime_gate.py tests/test_runtime_row_identity.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_contract_preflight.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_semantic_audit.py tests/test_shadowpriest_visionai_semantic_surface_contract.py tests/test_shadowpriest_semantic_safety_wave.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py -q
  ```

  Expected: all pass.

- [ ] **Step 2: Run contract guardrails**

  ```powershell
  python scripts/check_contract_guardrails.py
  python scripts/sync_installed_skill.py --check
  ```

  Expected: contract spine clean and installed skill in sync.

- [ ] **Step 3: Run the complete suite**

  ```powershell
  $env:PYTHONDONTWRITEBYTECODE = '1'
  pytest -q -p no:cacheprovider
  ```

  Expected: all tests pass; only documented skips.

- [ ] **Step 4: Create validated temporary output paths**

  ```powershell
  $exactOut = 'C:\Users\darbo\AppData\Local\Temp\hsconfig-shadowpriest-exact-20260726'
  $partialOut = 'C:\Users\darbo\AppData\Local\Temp\hsconfig-shadowpriest-partial-20260726'
  $tempParent = (Resolve-Path -LiteralPath 'C:\Users\darbo\AppData\Local\Temp').Path
  foreach ($target in @($exactOut, $partialOut)) {
      $candidateParent = [System.IO.Path]::GetFullPath(
          [System.IO.Path]::GetDirectoryName($target)
      )
      if ($candidateParent -ne $tempParent) {
          throw "Unexpected audit output parent: $target"
      }
      if (Test-Path -LiteralPath $target) {
          throw "Audit output already exists: $target"
      }
  }
  ```

- [ ] **Step 5: Generate the exact fixture package without apply**

  Run the deterministic exact-source fixture through the normal configure
  surface:

  ```powershell
  hsconfig configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out "$exactOut" --auto-source --source-url "https://example.test/shadowpriest-exact" --source-fixture-url-map-json "tests\fixtures\source_pages\shadowpriest_source_url_map.json" --current-date "2026-07-26" --json
  ```

  The command intentionally omits `--apply`.

  Validate:

  ```powershell
  hsconfig validate --package "$exactOut\04_package" --json
  hsconfig contract-preflight --package "$exactOut\04_package" --json
  python -m hsconfig.cli runtime-match --package "$exactOut\04_package" --runtime-root "C:\Users\darbo\Desktop\HS" --json
  ```

  Expected:

  - validation passed;
  - `package_contract_current=true`;
  - runtime-match is read-only;
  - exact-source authority is visible;
  - no runtime write receipt exists.

- [ ] **Step 6: Generate the current partial-source package without apply**

  Run:

  ```powershell
  hsconfig configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out "$partialOut" --auto-source --source-url "https://example.test/shadowpriest-archetype" --source-fixture-url-map-json "tests\fixtures\source_pages\shadowpriest_source_url_map.json" --current-date "2026-07-26" --json
  ```

  Do not add `--apply`.

  Validate:

  ```powershell
  hsconfig validate --package "$partialOut\04_package" --json
  hsconfig contract-preflight --package "$partialOut\04_package" --json
  python -m hsconfig.cli runtime-match --package "$partialOut\04_package" --runtime-root "C:\Users\darbo\Desktop\HS" --json
  ```

  Expected:

  - validation passed;
  - source authority is archetype-only or partial, never exact;
  - guide-backed Mulligan count is zero;
  - aggressive GlobalValues are unchanged;
  - runtime-match may show differences but performs no write.

- [ ] **Step 7: Assert exact physical package invariants**

  Define one invariant script and run it for both package roots:

  ```powershell
  $cardInvariantScript = @'
  import json
  import sys
  from pathlib import Path

  from hsconfig.config_quality_contract import build_config_quality_report

  package = Path(sys.argv[1])
  expected_rows = {
      ("DS1_233", "BeforePlayCardBonus", "*", "12"),
      ("REV_290", "BeforePlayCardBonus", "*", "8"),
      ("SW_446", "OnBoardBonus", "*", "10"),
      ("SW_448", "BeforeUseHeroPowerBonus", "*", "10"),
      ("TOY_381", "OnBoardBonus", "*", "8"),
      ("TOY_518", "OnBoardBonus", "*", "8"),
      ("WON_065", "OnBoardBonus", "*", "8"),
  }
  report_only = {
      "CFM_637",
      "DRG_056",
      "GVG_009",
      "NX2_019",
      "SCH_514",
      "SW_444",
      "VAC_419",
      "VAC_512",
      "YOD_032",
  }
  deck = package / "CustomConfig" / "shadowpriest"
  reports = package / "reports"

  signatures = []
  for path in sorted(deck.glob("*.json")):
      if path.name in {"GlobalValues.json", "Mulligan.json", "Combo.json"}:
          continue
      payload = json.loads(path.read_text(encoding="utf-8-sig"))
      card_id = str(payload["GameCardId"])
      for block, block_payload in payload.items():
          if block in {"GameCardId", "ConfigComment"}:
              continue
          for row in block_payload.get("values", []):
              signatures.append(
                  (
                      card_id,
                      block,
                      str(row.get("condition", "*")),
                      str(row["value"]),
                  )
              )
      if card_id in report_only:
          assert set(payload) == {"GameCardId", "ConfigComment"}, card_id

  assert set(signatures) == expected_rows
  assert len(signatures) == len(set(signatures))

  darkbishop = json.loads(
      (deck / "SW_448.json").read_text(encoding="utf-8-sig")
  )
  assert set(darkbishop) == {
      "GameCardId",
      "ConfigComment",
      "BeforeUseHeroPowerBonus",
  }

  readiness = json.loads(
      (reports / "per_card_config_readiness_report.json").read_text(
          encoding="utf-8"
      )
  )
  operator = json.loads(
      (reports / "operator_summary.json").read_text(encoding="utf-8")
  )
  quality = build_config_quality_report(package)

  assert readiness["summary"]["runtime_emitted"] == 7
  assert readiness["summary"]["report_only_supported"] == 9
  assert operator["configuration_assurance"]["optimality_claim_allowed"] is False
  assert operator["configuration_assurance"]["runtime_gate_impact"] == "none"
  trace = quality["checks"]["runtime_row_trace_inventory"]
  assert trace["unreported_runtime_rows"] == []
  assert trace["reported_rows_missing_runtime"] == []
  assert trace["physical_cardid_runtime_rows"] == trace["reported_cardid_runtime_rows"]
  print(f"ShadowPriest invariants passed: {package}")
'@

  $cardInvariantScript | python - "$exactOut\04_package"
  $cardInvariantScript | python - "$partialOut\04_package"

  @'
  import json
  import sys
  from pathlib import Path

  package = Path(sys.argv[1])
  reports = package / "reports"
  operator = json.loads(
      (reports / "operator_summary.json").read_text(encoding="utf-8")
  )
  global_profile = json.loads(
      (reports / "globalvalues_profile.json").read_text(
          encoding="utf-8"
      )
  )
  mulligan_plan = json.loads(
      (reports / "mulligan_plan_report.json").read_text(
          encoding="utf-8"
      )
  )

  assert operator["configuration_assurance"]["source_authority"] in {
      "archetype_only",
      "partial",
  }
  assert operator["source_backed_status"] != "SOURCE_BACKED_STRONG"
  assert global_profile["changed_keys"] == []
  assert mulligan_plan["quality"]["source_backed_keep_rule_count"] == 0
  for row in mulligan_plan["rules"]:
      if row["action"] == "hold":
          assert row["source_type"] == "policy_backed_autonomous_mulligan"
  print(f"ShadowPriest partial-source invariants passed: {package}")
  '@ | python - "$partialOut\04_package"
  ```

- [ ] **Step 8: Remove only the two validated temporary directories**

  Resolve and verify each exact path before removal:

  ```powershell
  foreach ($target in @($exactOut, $partialOut)) {
      if (-not (Test-Path -LiteralPath $target)) {
          continue
      }
      $resolved = (Resolve-Path -LiteralPath $target).Path
      if (
          $resolved -notin @(
              'C:\Users\darbo\AppData\Local\Temp\hsconfig-shadowpriest-exact-20260726',
              'C:\Users\darbo\AppData\Local\Temp\hsconfig-shadowpriest-partial-20260726'
          )
      ) {
          throw "Unexpected removal target: $resolved"
      }
      [System.IO.Directory]::Delete($resolved, $true)
  }
  ```

- [ ] **Step 9: Run final repository and GitHub checks**

  ```powershell
  python scripts/sync_installed_skill.py --check
  python scripts/check_hsconfig_currentness.py --cwd . --json
  git diff --check
  git status --short --branch
  git rev-list --left-right --count main...origin/main
  git branch --all
  git ls-remote --heads origin
  gh pr list --repo Teufelsboy/HSConfig --state open --json number,title,headRefName,baseRefName,url
  ```

  Expected:

  - installed skill in sync;
  - clean `main`;
  - `0 0` divergence;
  - only branch `main`;
  - no open pull requests;
  - temporary package directories absent.

- [ ] **Step 10: Handle verification defects without an omnibus commit**

  If Steps 1–9 expose a defect:

  1. identify the earliest task that owns the defective contract;
  2. add or tighten that task's failing test;
  3. make the minimal causal correction in that task's listed files;
  4. rerun that task's focused suite;
  5. rerun Steps 1–9;
  6. commit with that task's commit message and push `main`.

  If no defect exists, do not create an empty commit.

---

## Final Acceptance Matrix

| Contract | Exact-source fixture | Current archetype-only source |
|---|---:|---:|
| Exact 30-card target identity | Pass | Pass |
| Source guide scope | `exact_deck_matched` | `archetype_matched` or partial |
| Strict package validation | Pass | Pass |
| Preflight validation parity | Pass | Pass |
| Runtime write during implementation | `false` | `false` |
| Guide-backed Mulligan | Allowed | Forbidden |
| Policy-backed Mulligan fallback | Optional and labeled | Optional and labeled |
| Darkbishop Mulligan keep | Absent | Absent |
| Darkbishop body priority | Absent | Absent |
| Darkbishop Hero Power row | Present once | Present once |
| Aggressive GlobalValues | Only with separate exact `gameplan_posture` | Baseline |
| Mind Blast play row | Present once | Present once |
| Cathedral deploy row | Present once | Present once |
| Voidtouched OnBoard row | Present once | Present once |
| Papercraft OnBoard row | Present once | Present once |
| Treasure Distributor OnBoard row | Present once | Present once |
| Ship's Chirurgeon OnBoard row | Present once | Present once |
| Reciprocal burn wildcard play rows | Absent | Absent |
| State-dependent wildcard action rows | Absent | Absent |
| Runtime-emitted cards | 7 | 7 |
| Report-only cards | 9 | 9 |
| Duplicate physical signatures | 0 | 0 |
| Conflicting runtime values | 0 | 0 |
| Physical/report row parity | Exact | Exact |
| `SOURCE_BACKED_STRONG` | Allowed only when all exact closure checks pass | Forbidden |
| Optimality claim allowed | `false` | `false` |
| Runtime apply in this plan | Never | Never |

## Out Of Scope

- Applying either generated package.
- HSTuner.
- Win-rate, matchup, or gameplay-improvement claims.
- Low-health numeric tuning.
- New condition atoms for graveyard state, damage this turn, current cost,
  exact lethal, minion death, target-kill, or location activation.
- New VisionAI keys.
- Moving `hero_power_transform` away from the existing CardID/linked-identity
  boundary.
- Treating a different 40-card guide as exact evidence for the 30-card deck.

## Implementation Completion Criteria

Implementation is complete only when:

1. Tasks 1–9 are checked.
2. Every task-specific RED test was observed before its implementation.
3. Every focused regression suite passes.
4. Contract guardrails pass.
5. The complete pytest suite passes.
6. Exact and partial read-only packages pass strict validation.
7. Preflight and validate agree for valid and invalid packages.
8. Runtime-match performs no write.
9. The exact seven active and nine report-only card contracts hold physically.
10. Duplicate and conflicting runtime rows are zero.
11. Generated temporary packages are removed.
12. The installed HSConfig skill is synchronized.
13. Git is clean on `main`, local and `origin/main` are `0 0`, only `main`
    exists, and no pull request is open.
14. No report, documentation, or final message claims in-client optimality from
    pre-run artifacts.
