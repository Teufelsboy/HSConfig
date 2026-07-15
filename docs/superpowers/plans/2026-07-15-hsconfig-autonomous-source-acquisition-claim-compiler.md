# HSConfig Autonomous Source Acquisition And Claim Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig able to build a source-backed, no-default-only-visible CustomConfig package from only deck input by acquiring bounded public source records, compiling atomic claims, feeding the existing `source-autopilot` path, and preserving `SOURCE_BACKED_STRONG` as an honest closure label.

**Architecture:** Keep the current authority chain: `configure -> source-autopilot -> research-deck -> prepare -> validate -> operator_summary`. Add one bounded source acquisition module and one deterministic claim compiler before `source-autopilot`; do not add a parallel schema, a second apply gate, or a hidden browser dependency. Online failures, thin sources, stale pages, unresolved names, and unsupported mechanics downgrade confidence and create visible first-missing-link diagnostics, but they never block valid load-safe config creation.

**Tech Stack:** Python 3.11+, stdlib `urllib.request`, `html.parser`, `json`, `pathlib`, existing HSConfig modules, existing pytest test style, no new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.
- Do not move work to `C:\Users\darbo\Documents\HS`, temp checkouts, or shadow workspaces.
- Keep HSConfig pre-run only: no replay parsing, no winrate tuning, no post-game HSTuner logic.
- Runtime writes remain allowed only through existing `hsconfig apply` or `hsconfig configure --apply`.
- `reports/operator_summary.json` remains the normal apply authority.
- `SOURCE_BACKED_STRONG` is a semantic/source closure label, not a runtime apply blocker.
- Produce a valid load-safe config for any valid deck even when no public guide can be fetched.
- Do not fake guide strength from decklists, static card text, search snippets, replay statistics, or policy-backed defaults.
- Darkbishop Benedictus style effects stay split: preserve `hero_power_transform`/effect rows, but never infer `mulligan_keep` from start-of-game text.
- No default-only output may be hidden. Every surface must be reported as `source_backed`, `policy_backed`, `static_semantics_backed`, `explicit_gap`, `not_applicable`, or `default_only`.
- Keep source records short and structured. Do not commit raw long guide pages, private browsing dumps, logs, or scraped bulk text.

---

## File Structure

Create:

- `src/hsconfig/source_acquisition.py`
  - Bounded public-source collector. Builds search aliases, fetches explicit URLs and official card metadata URLs, extracts compact page text, normalizes source records, and reports fetch failures as non-blocking diagnostics.

- `src/hsconfig/source_claim_compiler.py`
  - Deterministic compiler from normalized source records plus deck identity into `source_search_records` accepted by existing `source_autopilot.build_source_autopilot_bundle`.

- `tests/test_source_acquisition.py`
  - Unit tests for URL validation, fake fetcher behavior, text extraction, official/static metadata lane, fetch failure lane, and no-block behavior.

- `tests/test_source_claim_compiler.py`
  - Unit tests for explicit mulligan keep/discard extraction, Darkbishop effect split, decklist-only non-strong lane, and unsupported claim visibility.

- `tests/test_configure_online_source.py`
  - End-to-end tests for `hsconfig configure --online-source`, using injected local fixture pages instead of live web.

- `tests/fixtures/source_pages/shadowpriest_voidburn.html`
  - Short synthetic fixture based on current public guide facts: explicit cheap-card keeps, do-not-keep 4+ rule, Shadow hero power gameplan.

- `tests/fixtures/source_pages/decklist_only.html`
  - Short synthetic fixture with a decklist but no strategic guide text.

Modify:

- `src/hsconfig/commands/source_workflow.py`
  - Add `source_acquire_payload(args)` and `run_source_acquire_command(args)`.

- `src/hsconfig/commands/configure.py`
  - Add optional `--online-source` stage before existing `--auto-source`. If `--online-source` is used, it writes `02_source_acquisition/source_search_results.json` and then feeds that path into source-autopilot.

- `src/hsconfig/cli_parser.py`
  - Add parser for `source-acquire`; add configure flags `--online-source`, `--source-url`, `--source-fixture-url-map-json`, and `--source-fetch-timeout-seconds`.

- `src/hsconfig/cli.py`
  - Dispatch `source-acquire`.

- `docs/operator/README.md`
  - Document the single normal high-autonomy path.

- `docs/operator/source-builder-workflow.md`
  - Document source-acquire -> source-autopilot -> package flow and manual fallback.

- `docs/operator/guide-research-policy.md`
  - Document what can and cannot promote to `SOURCE_BACKED_STRONG`.

- `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`
  - Update the local HSConfig skill so future runs prefer `configure --online-source --auto-source` when the user asks for an optimal fresh config and public source acquisition is desired.

---

### Task 1: Define Source Acquisition Contract Tests

**Files:**
- Create: `tests/fixtures/source_pages/shadowpriest_voidburn.html`
- Create: `tests/fixtures/source_pages/decklist_only.html`
- Create: `tests/test_source_acquisition.py`

**Interfaces:**
- Produces:
  - `SourceFetchResult`: dict with `url`, `status`, `text`, `title`, `source_family`, `error`.
  - `collect_public_source_records(deck_name, deck_identity, source_urls, current_date, fetcher, timeout_seconds) -> dict`.

- [ ] **Step 1: Create the ShadowPriest guide fixture page**

Write `tests/fixtures/source_pages/shadowpriest_voidburn.html`:

```html
<!doctype html>
<html>
  <head><title>Voidburn Wild Aggro Shadow Priest</title></head>
  <body>
    <h1>Voidburn Wild Aggro Shadow Priest</h1>
    <p>This is an aggressive Shadow Priest burn strategy using Darkbishop Benedictus to enable the Shadow hero power.</p>
    <h2>Mulligan</h2>
    <p>Keep Papercraft Angel, Twilight Deceptor, Raise Dead, and Shadowbomber. Do not keep any 4 cost or higher cards.</p>
    <h2>Hero Power</h2>
    <p>Mind Spike can clear the enemy board to keep pressure or go face against slower decks.</p>
  </body>
</html>
```

- [ ] **Step 2: Create the decklist-only fixture page**

Write `tests/fixtures/source_pages/decklist_only.html`:

```html
<!doctype html>
<html>
  <head><title>Thin Public Decklist</title></head>
  <body>
    <h1>Thin Public Decklist</h1>
    <p>Deck code: AAEBA-example</p>
    <ul>
      <li>Fixture Card</li>
      <li>Second Fixture Card</li>
    </ul>
  </body>
</html>
```

- [ ] **Step 3: Write failing acquisition tests**

Create `tests/test_source_acquisition.py`:

```python
from __future__ import annotations

from pathlib import Path

from hsconfig.source_acquisition import collect_public_source_records, extract_visible_text


FIXTURES = Path(__file__).parent / "fixtures" / "source_pages"


def _fake_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    if url.endswith("shadowpriest"):
        return 200, "text/html", (FIXTURES / "shadowpriest_voidburn.html").read_bytes()
    if url.endswith("decklist"):
        return 200, "text/html", (FIXTURES / "decklist_only.html").read_bytes()
    return 404, "text/plain", b"not found"


def test_extract_visible_text_removes_markup_and_keeps_title():
    html = (FIXTURES / "shadowpriest_voidburn.html").read_text(encoding="utf-8")

    parsed = extract_visible_text(html)

    assert parsed["title"] == "Voidburn Wild Aggro Shadow Priest"
    assert "Keep Papercraft Angel" in parsed["text"]
    assert "<p>" not in parsed["text"]


def test_collect_public_source_records_fetches_bounded_public_pages():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {"card_id": "BAR_735", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
            {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
        ],
    }

    payload = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=["https://example.test/shadowpriest"],
        current_date="2026-07-15",
        fetcher=_fake_fetcher,
        timeout_seconds=2.0,
    )

    assert payload["status"] == "OK"
    assert payload["source_records"][0]["source_family"] == "guide"
    assert payload["source_records"][0]["source_title"] == "Voidburn Wild Aggro Shadow Priest"
    assert "Keep Papercraft Angel" in payload["source_records"][0]["normalized_text"]
    assert payload["source_acquisition_report"]["failed_fetch_count"] == 0


def test_collect_public_source_records_keeps_fetch_failures_non_blocking():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    payload = collect_public_source_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_urls=["https://example.test/missing"],
        current_date="2026-07-15",
        fetcher=_fake_fetcher,
        timeout_seconds=2.0,
    )

    assert payload["status"] == "OK"
    assert payload["source_records"] == []
    assert payload["source_acquisition_report"]["failed_fetch_count"] == 1
    assert payload["source_acquisition_report"]["first_missing_source_action"] == "add_public_guide_url_or_use_static_semantics"
```

- [ ] **Step 4: Run the failing acquisition tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_acquisition.py -q
```

Expected: FAIL because `hsconfig.source_acquisition` does not exist.

- [ ] **Step 5: Commit failing tests**

Run:

```powershell
git add tests/fixtures/source_pages/shadowpriest_voidburn.html tests/fixtures/source_pages/decklist_only.html tests/test_source_acquisition.py
git commit -m "test: define public source acquisition contract"
```

---

### Task 2: Implement Bounded Source Acquisition

**Files:**
- Create: `src/hsconfig/source_acquisition.py`
- Test: `tests/test_source_acquisition.py`

**Interfaces:**
- Produces:
  - `extract_visible_text(html: str) -> dict[str, str]`
  - `collect_public_source_records(...) -> dict[str, Any]`

- [ ] **Step 1: Implement HTML text extraction and bounded fetch seam**

Create `src/hsconfig/source_acquisition.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any, Callable, Mapping, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen


Fetcher = Callable[[str, float], tuple[int, str, bytes]]


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text or self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(text)
        else:
            self.text_parts.append(text)


def extract_visible_text(html: str) -> dict[str, str]:
    parser = _VisibleTextParser()
    parser.feed(html)
    title = " ".join(parser.title_parts).strip()
    text = " ".join(parser.text_parts).strip()
    return {"title": title, "text": text}


def collect_public_source_records(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    source_urls: Sequence[str],
    current_date: str | date | None = None,
    fetcher: Fetcher | None = None,
    timeout_seconds: float = 6.0,
) -> dict[str, Any]:
    fetch = fetcher or _default_fetcher
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for url in _dedupe_urls(source_urls):
        if not _is_public_https(url):
            failures.append({"url": url, "error": "non_public_https_url"})
            continue
        try:
            status, content_type, body = fetch(url, timeout_seconds)
        except Exception as exc:
            failures.append({"url": url, "error": type(exc).__name__})
            continue
        if status < 200 or status >= 300:
            failures.append({"url": url, "error": f"http_status_{status}"})
            continue
        if "html" not in content_type.lower() and "text" not in content_type.lower():
            failures.append({"url": url, "error": f"unsupported_content_type:{content_type}"})
            continue
        parsed = extract_visible_text(body.decode("utf-8", errors="replace"))
        records.append(
            {
                "source_url": url,
                "source_title": parsed["title"] or url,
                "source_family": _infer_source_family(url, parsed["text"]),
                "retrieved_at": _iso_datetime(current_date),
                "deck_match": {
                    "deck_name": deck_name,
                    "archetype": _slug(deck_name),
                    "matched_card_ids": _matched_card_ids(deck_identity, parsed["text"]),
                },
                "normalized_text": parsed["text"],
            }
        )
    report = {
        "schema_version": 1,
        "deck_name": deck_name,
        "attempted_url_count": len(_dedupe_urls(source_urls)),
        "source_record_count": len(records),
        "failed_fetch_count": len(failures),
        "failures": failures,
        "first_missing_source_action": (
            "none" if records else "add_public_guide_url_or_use_static_semantics"
        ),
    }
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "status": "OK",
        "source_records": records,
        "source_acquisition_report": report,
    }


def _default_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    request = Request(url, headers={"User-Agent": "HSConfig/1.0 source acquisition"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return int(response.status), str(response.headers.get("Content-Type", "")), response.read(400_000)
    except URLError:
        raise


def _matched_card_ids(deck_identity: Mapping[str, Any], text: str) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    for card in deck_identity.get("cards", []):
        if not isinstance(card, Mapping):
            continue
        name = str(card.get("name", "")).strip()
        card_id = str(card.get("card_id", "")).strip()
        if name and card_id and name.lower() in lowered:
            matches.append(card_id)
    return matches


def _infer_source_family(url: str, text: str) -> str:
    lowered = f"{url} {text}".lower()
    if "mulligan" in lowered or "guide" in lowered or "keep " in lowered:
        return "guide"
    if "deck code" in lowered or "decklist" in lowered:
        return "decklist"
    return "public_page"


def _dedupe_urls(urls: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        value = str(url).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _is_public_https(url: str) -> bool:
    return url.startswith("https://")


def _iso_datetime(current_date: str | date | None) -> str:
    if current_date is None:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    if isinstance(current_date, date):
        return datetime.combine(current_date, datetime.min.time()).isoformat() + "Z"
    return current_date


def _slug(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())
```

- [ ] **Step 2: Run acquisition tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_acquisition.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit source acquisition implementation**

Run:

```powershell
git add src/hsconfig/source_acquisition.py tests/test_source_acquisition.py
git commit -m "feat: add bounded public source acquisition"
```

---

### Task 3: Define And Implement Claim Compiler

**Files:**
- Create: `tests/test_source_claim_compiler.py`
- Create: `src/hsconfig/source_claim_compiler.py`
- Modify: `src/hsconfig/source_acquisition.py`

**Interfaces:**
- Consumes: `source_records` from Task 2.
- Produces:
  - `compile_source_search_records(deck_name, deck_identity, acquired_records, current_date) -> dict[str, Any]`

- [ ] **Step 1: Write failing claim compiler tests**

Create `tests/test_source_claim_compiler.py`:

```python
from __future__ import annotations

from hsconfig.source_claim_compiler import compile_source_search_records


DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_slug": "shadowpriest",
    "deck_code_hash": "sha256:shadow",
    "cards": [
        {"card_id": "BAR_735", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
        {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
        {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
        {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
        {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
    ],
}


def test_compile_source_search_records_extracts_atomic_shadowpriest_claims():
    acquired = [
        {
            "source_url": "https://example.test/shadowpriest",
            "source_title": "Voidburn Wild Aggro Shadow Priest",
            "source_family": "guide",
            "retrieved_at": "2026-07-15T00:00:00Z",
            "deck_match": {"deck_name": "ShadowPriest", "archetype": "shadowpriest", "matched_card_ids": ["TOY_381", "SW_444", "SCH_514", "GVG_009", "BAR_735"]},
            "normalized_text": "Keep Papercraft Angel, Twilight Deceptor, Raise Dead, and Shadowbomber. Do not keep any 4 cost or higher cards. Darkbishop Benedictus enables the Shadow hero power. Mind Spike can clear the enemy board or go face against slower decks.",
        }
    ]

    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    record = payload["records"][0]
    assert record["mulligan"]["keep_card_ids"] == ["TOY_381", "SW_444", "SCH_514", "GVG_009"]
    assert record["mulligan"]["discard_cost_min"] == 4
    claim_kinds = [claim["claim_kind"] for claim in record["claims"]]
    assert "hero_power_transform" in claim_kinds
    assert "targeting_rule" in claim_kinds
    assert not any(claim["claim_kind"] == "mulligan_keep" and claim.get("cards") == ["BAR_735"] for claim in record["claims"])


def test_compile_source_search_records_keeps_decklist_only_non_promoting():
    acquired = [
        {
            "source_url": "https://example.test/decklist",
            "source_title": "Thin Public Decklist",
            "source_family": "decklist",
            "retrieved_at": "2026-07-15T00:00:00Z",
            "deck_match": {"deck_name": "ThinDeck", "archetype": "thindeck", "matched_card_ids": ["CARD_001"]},
            "normalized_text": "Deck code: AAEBA-example Fixture Card Second Fixture Card",
        }
    ]
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    payload = compile_source_search_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    assert payload["records"][0]["source_family"] == "decklist"
    assert payload["records"][0]["claims"][0]["claim_kind"] == "card_role"
    assert payload["records"][0]["claims"][0]["source_confidence"] == "medium"
    assert payload["source_claim_compiler_report"]["promotion_candidate_count"] == 0
```

- [ ] **Step 2: Run failing compiler tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_compiler.py -q
```

Expected: FAIL because `hsconfig.source_claim_compiler` does not exist.

- [ ] **Step 3: Implement deterministic compiler**

Create `src/hsconfig/source_claim_compiler.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


def compile_source_search_records(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    acquired_records: Sequence[Mapping[str, Any]],
    current_date: str | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    promotion_candidates = 0
    for acquired in acquired_records:
        text = str(acquired.get("normalized_text", ""))
        compiled = {
            "source_url": acquired.get("source_url"),
            "source_title": acquired.get("source_title"),
            "source_family": acquired.get("source_family", "public_page"),
            "retrieved_at": acquired.get("retrieved_at") or current_date,
            "deck_match": acquired.get("deck_match", {"deck_name": deck_name, "archetype": deck_name.lower(), "matched_card_ids": []}),
            "claims": [],
        }
        keep_ids = _explicit_keep_card_ids(deck_identity, text)
        if keep_ids:
            compiled["mulligan"] = {
                "keep_card_ids": keep_ids,
                "evidence_text_short": _short_evidence(text, "keep"),
            }
            for card_id in keep_ids:
                compiled["claims"].append(
                    _claim("mulligan_keep", [card_id], "opening_hand_keep", "Explicit public guide keep text.", "high")
                )
        discard_cost_min = _discard_cost_min(text)
        if discard_cost_min is not None:
            compiled.setdefault("mulligan", {})["discard_cost_min"] = discard_cost_min
            for card in deck_identity.get("cards", []):
                if isinstance(card, Mapping) and int(card.get("cost", -1)) >= discard_cost_min:
                    compiled["claims"].append(
                        _claim("mulligan_discard", [str(card["card_id"])], "discard_by_cost_rule", "Explicit public guide discard cost rule.", "high")
                    )
        if _mentions_any(text, ["darkbishop", "shadow hero power", "shadowform"]):
            compiled["claims"].append(
                _claim("hero_power_transform", _card_ids_named(deck_identity, text, fallback_names=["Darkbishop Benedictus"]), "enable_shadow_hero_power", "Public source or card text supports Shadow hero power transform.", "high")
            )
        if _mentions_any(text, ["mind spike", "go face", "clear the enemy board"]):
            compiled["claims"].append(
                _claim("targeting_rule", [], "conditional_board_or_face_pressure", "Public guide gives hero power target direction.", "high")
            )
        if not compiled["claims"] and str(compiled["source_family"]) == "decklist":
            for card_id in acquired.get("deck_match", {}).get("matched_card_ids", []):
                compiled["claims"].append(
                    _claim("card_role", [str(card_id)], "listed_card", "Public decklist contains this card.", "medium")
                )
        if str(compiled["source_family"]) == "guide" and any(claim.get("source_confidence") == "high" for claim in compiled["claims"]):
            promotion_candidates += 1
        records.append(compiled)
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "records": records,
        "source_claim_compiler_report": {
            "schema_version": 1,
            "deck_name": deck_name,
            "record_count": len(records),
            "claim_kind_counts": dict(Counter(claim["claim_kind"] for record in records for claim in record.get("claims", []))),
            "promotion_candidate_count": promotion_candidates,
        },
    }


def _explicit_keep_card_ids(deck_identity: Mapping[str, Any], text: str) -> list[str]:
    lowered = text.lower()
    if "keep " not in lowered:
        return []
    keep_ids: list[str] = []
    for card in deck_identity.get("cards", []):
        if not isinstance(card, Mapping):
            continue
        name = str(card.get("name", ""))
        card_id = str(card.get("card_id", ""))
        if name and card_id and name.lower() in lowered and not _is_start_of_game_enabler(name, lowered):
            keep_ids.append(card_id)
    return keep_ids


def _discard_cost_min(text: str) -> int | None:
    lowered = text.lower()
    for cost in range(1, 11):
        if f"do not keep any {cost} cost or higher" in lowered or f"don't keep any {cost} cost or higher" in lowered:
            return cost
    return None


def _card_ids_named(deck_identity: Mapping[str, Any], text: str, *, fallback_names: Sequence[str] = ()) -> list[str]:
    lowered = text.lower()
    names = {name.lower() for name in fallback_names}
    result: list[str] = []
    for card in deck_identity.get("cards", []):
        if not isinstance(card, Mapping):
            continue
        name = str(card.get("name", ""))
        card_id = str(card.get("card_id", ""))
        if card_id and ((name and name.lower() in lowered) or name.lower() in names):
            result.append(card_id)
    return result


def _claim(claim_kind: str, cards: list[str], stance: str, evidence: str, confidence: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "claim_kind": claim_kind,
        "stance": stance,
        "evidence_text_short": evidence,
        "source_confidence": confidence,
    }
    if cards:
        row["cards"] = cards
    return row


def _mentions_any(text: str, needles: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def _is_start_of_game_enabler(name: str, text_lower: str) -> bool:
    return name.lower() == "darkbishop benedictus" and ("start of game" in text_lower or "shadow hero power" in text_lower)


def _short_evidence(text: str, marker: str) -> str:
    sentences = [part.strip() for part in text.replace("!", ".").replace("?", ".").split(".") if part.strip()]
    for sentence in sentences:
        if marker in sentence.lower():
            return sentence[:220]
    return sentences[0][:220] if sentences else "Public source evidence."
```

- [ ] **Step 4: Run compiler tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_compiler.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit compiler**

Run:

```powershell
git add src/hsconfig/source_claim_compiler.py tests/test_source_claim_compiler.py
git commit -m "feat: compile public source records into source claims"
```

---

### Task 4: Add `source-acquire` CLI

**Files:**
- Modify: `src/hsconfig/commands/source_workflow.py`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/cli.py`
- Create: `tests/test_source_acquire_cli.py`

**Interfaces:**
- Consumes:
  - `collect_public_source_records(...)`
  - `compile_source_search_records(...)`
- Produces:
  - `source_search_results.json`
  - `source_acquisition_report.json`
  - `source_claim_compiler_report.json`

- [ ] **Step 1: Write CLI test**

Create `tests/test_source_acquire_cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


def test_source_acquire_cli_writes_compiled_source_search_results(tmp_path):
    fixture_map = tmp_path / "fixture_map.json"
    page = Path(__file__).parent / "fixtures" / "source_pages" / "shadowpriest_voidburn.html"
    fixture_map.write_text(
        json.dumps({"https://example.test/shadowpriest": str(page)}),
        encoding="utf-8",
    )
    out = tmp_path / "out"

    status = main([
        "source-acquire",
        "--deck-name", "ShadowPriest",
        "--deck-code", "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        "--source-url", "https://example.test/shadowpriest",
        "--source-fixture-url-map-json", str(fixture_map),
        "--out", str(out),
        "--json",
    ])

    assert status == 0
    source_search = json.loads((out / "source_search_results.json").read_text(encoding="utf-8"))
    assert source_search["records"][0]["source_family"] == "guide"
    assert source_search["records"][0]["mulligan"]["keep_card_ids"]
    assert (out / "source_acquisition_report.json").exists()
    assert (out / "source_claim_compiler_report.json").exists()
```

- [ ] **Step 2: Implement fixture fetcher seam in command layer**

In `src/hsconfig/commands/source_workflow.py`, add imports:

```python
from hsconfig.source_acquisition import collect_public_source_records
from hsconfig.source_claim_compiler import compile_source_search_records
```

Add:

```python
def source_acquire_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    common = _deck_common(args)
    fetcher = _fixture_fetcher(getattr(args, "source_fixture_url_map_json", None))
    acquired = collect_public_source_records(
        deck_name=common["deck_name"],
        deck_identity=common["deck_identity"],
        source_urls=list(getattr(args, "source_url", []) or []),
        current_date=getattr(args, "current_date", None),
        fetcher=fetcher,
        timeout_seconds=float(getattr(args, "source_fetch_timeout_seconds", 6.0)),
    )
    compiled = compile_source_search_records(
        deck_name=common["deck_name"],
        deck_identity=common["deck_identity"],
        acquired_records=acquired["source_records"],
        current_date=getattr(args, "current_date", None),
    )
    write_json(out / "source_acquisition_report.json", acquired["source_acquisition_report"])
    write_json(out / "source_claim_compiler_report.json", compiled["source_claim_compiler_report"])
    write_json(out / "source_search_results.json", compiled)
    return {
        "status": "OK",
        "source_search_results_json": str(out / "source_search_results.json"),
        "source_acquisition_report": acquired["source_acquisition_report"],
        "source_claim_compiler_report": compiled["source_claim_compiler_report"],
    }, 0


def run_source_acquire_command(args: argparse.Namespace) -> int:
    payload, status = source_acquire_payload(args)
    _print_payload(payload, args)
    return status
```

Add helper:

```python
def _fixture_fetcher(path_value: str | None):
    if not path_value:
        return None
    mapping = json.loads(Path(path_value).read_text(encoding="utf-8"))

    def fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
        if url not in mapping:
            return 404, "text/plain", b"fixture url not mapped"
        return 200, "text/html", Path(mapping[url]).read_bytes()

    return fetcher
```

- [ ] **Step 3: Register parser and dispatch**

In `src/hsconfig/cli_parser.py`, add:

```python
    source_acquire = subparsers.add_parser("source-acquire")
    source_acquire.add_argument("--deck-name", required=True)
    source_acquire.add_argument("--deck-code", required=True)
    source_acquire.add_argument("--source-url", action="append", default=[])
    source_acquire.add_argument("--source-fixture-url-map-json")
    source_acquire.add_argument("--source-fetch-timeout-seconds", type=float, default=6.0)
    source_acquire.add_argument("--current-date")
    source_acquire.add_argument("--out", required=True)
    source_acquire.add_argument("--json", action="store_true")
```

In `src/hsconfig/cli.py`, dispatch:

```python
    if args.command == "source-acquire":
        from hsconfig.commands.source_workflow import run_source_acquire_command
        return run_source_acquire_command(args)
```

- [ ] **Step 4: Run CLI test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_acquire_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit CLI**

Run:

```powershell
git add src/hsconfig/commands/source_workflow.py src/hsconfig/cli_parser.py src/hsconfig/cli.py tests/test_source_acquire_cli.py
git commit -m "feat: add source acquisition cli"
```

---

### Task 5: Integrate `configure --online-source`

**Files:**
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/cli_parser.py`
- Create: `tests/test_configure_online_source.py`

**Interfaces:**
- Consumes:
  - `source_acquire_payload(args) -> (payload, status)`
  - existing `source_autopilot_payload(args)`.
- Produces:
  - `configure --online-source --auto-source`.

- [ ] **Step 1: Write failing configure integration test**

Create `tests/test_configure_online_source.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


def test_configure_online_source_builds_source_backed_shadowpriest_package(tmp_path, monkeypatch):
    from tests.test_configure_auto_source import _stub_empty_fetches, _write_shadow_cards_json

    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    fixture_map = tmp_path / "fixture_map.json"
    page = Path(__file__).parent / "fixtures" / "source_pages" / "shadowpriest_voidburn.html"
    fixture_map.write_text(json.dumps({"https://example.test/shadowpriest": str(page)}), encoding="utf-8")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    out = tmp_path / "configure"

    status = main([
        "configure",
        "--deck-name", "ShadowPriest",
        "--deck-code", "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        "--runtime-root", str(runtime),
        "--out", str(out),
        "--cards-json", str(cards_json),
        "--online-source",
        "--auto-source",
        "--source-url", "https://example.test/shadowpriest",
        "--source-fixture-url-map-json", str(fixture_map),
        "--json",
    ])

    assert status == 0
    summary = json.loads((out / "configure_summary.json").read_text(encoding="utf-8"))
    operator = json.loads((out / "04_package" / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    mulligan = json.loads((out / "04_package" / "CustomConfig" / "shadowpriest" / "Mulligan.json").read_text(encoding="utf-8"))
    assert summary["source_acquisition_path"].endswith("02_source_acquisition")
    assert summary["source_autopilot_path"].endswith("03_source_autopilot")
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert operator["default_only_runtime_surfaces"] == []
    assert "BAR_735" not in json.dumps(mulligan)
```

- [ ] **Step 2: Register configure flags**

In `src/hsconfig/cli_parser.py`, add to configure:

```python
    configure.add_argument("--online-source", action="store_true")
    configure.add_argument("--source-url", action="append", default=[])
    configure.add_argument("--source-fixture-url-map-json")
    configure.add_argument("--source-fetch-timeout-seconds", type=float, default=6.0)
```

- [ ] **Step 3: Add source acquisition stage before source-autopilot**

In `src/hsconfig/commands/configure.py`, import:

```python
from hsconfig.commands.source_workflow import source_acquire_payload
```

Create directories:

```python
source_acquisition_dir = out / "02_source_acquisition"
autopilot_dir = out / "03_source_autopilot"
```

Before existing auto-source handling, add:

```python
    source_acquisition_path = None
    if bool(getattr(args, "online_source", False)):
        acquire_args = SimpleNamespace(
            **common,
            source_url=list(getattr(args, "source_url", []) or []),
            source_fixture_url_map_json=getattr(args, "source_fixture_url_map_json", None),
            source_fetch_timeout_seconds=getattr(args, "source_fetch_timeout_seconds", 6.0),
            current_date=getattr(args, "current_date", None),
            out=str(source_acquisition_dir),
            json=True,
        )
        acquire_payload, acquire_status = source_acquire_payload(acquire_args)
        if acquire_status != 0:
            return _finish(out, "failed", {"stage": "source-acquire", **acquire_payload}, acquire_status)
        args.source_search_results_json = acquire_payload["source_search_results_json"]
        args.auto_source = True
        source_acquisition_path = str(source_acquisition_dir)
```

Add to final summary:

```python
            "source_acquisition_path": source_acquisition_path,
```

- [ ] **Step 4: Run configure online-source test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_configure_online_source.py -q
```

Expected: PASS.

- [ ] **Step 5: Run configure/source regression tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_configure_online_source.py tests/test_configure_auto_source.py tests/test_source_acquire_cli.py tests/test_source_autopilot.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit configure online-source integration**

Run:

```powershell
git add src/hsconfig/commands/configure.py src/hsconfig/cli_parser.py tests/test_configure_online_source.py
git commit -m "feat: integrate online source acquisition into configure"
```

---

### Task 6: Add Any-Deck No-Block And No-Default-Only Visibility Tests

**Files:**
- Modify: `tests/test_configure_online_source.py`
- Modify: `tests/test_source_claim_compiler.py`

**Interfaces:**
- Consumes: source acquisition and configure integration.
- Produces: proof that weak/no online sources do not block package generation and do not fake `SOURCE_BACKED_STRONG`.

- [ ] **Step 1: Add no-source configure test**

Append to `tests/test_configure_online_source.py`:

```python
def test_configure_online_source_without_usable_guide_stays_load_safe_non_strong(tmp_path, monkeypatch):
    from tests.test_configure_auto_source import _stub_empty_fetches, _write_thin_cards_json

    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_thin_cards_json(cards_json)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    out = tmp_path / "configure"

    status = main([
        "configure",
        "--deck-name", "ThinDeck",
        "--deck-code", "AAEBA-thin",
        "--runtime-root", str(runtime),
        "--out", str(out),
        "--cards-json", str(cards_json),
        "--online-source",
        "--auto-source",
        "--source-url", "https://example.test/missing",
        "--source-fixture-url-map-json", str(tmp_path / "empty_map.json"),
        "--json",
    ])

    assert status == 0
    operator = json.loads((out / "04_package" / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    acquisition = json.loads((out / "02_source_acquisition" / "source_acquisition_report.json").read_text(encoding="utf-8"))
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert acquisition["first_missing_source_action"] == "add_public_guide_url_or_use_static_semantics"
```

Before running, write the empty fixture map inside the test:

```python
    (tmp_path / "empty_map.json").write_text("{}", encoding="utf-8")
```

Insert that line before the `main([...])` call.

- [ ] **Step 2: Run no-block tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_configure_online_source.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit no-block online-source proof**

Run:

```powershell
git add tests/test_configure_online_source.py tests/test_source_claim_compiler.py
git commit -m "test: prove online source no-block behavior"
```

---

### Task 7: Update Operator Docs And Local HSConfig Skill

**Files:**
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-builder-workflow.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

**Interfaces:**
- Consumes: CLI behavior from Tasks 4-6.
- Produces: one normal operator path and one explicit source-confidence boundary.

- [ ] **Step 1: Update operator README normal path**

Add this command to `docs/operator/README.md` as the preferred source-backed config path:

```markdown
Preferred fresh config path when public source URLs are available:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --source-url "<public-guide-url>" --json
```

This path writes `02_source_acquisition`, `03_source_autopilot`, and the normal `04_package`. It can reach `SOURCE_BACKED_STRONG` only when the acquired sources contain exact deck-matching guide claims. If sources are thin or unavailable, HSConfig still produces a load-safe package and reports the missing source link.
```

- [ ] **Step 2: Update source-builder workflow**

Add this ladder to `docs/operator/source-builder-workflow.md`:

```markdown
Autonomous source path:

```powershell
hsconfig source-acquire --deck-name "<DeckName>" --deck-code "<DeckCode>" --source-url "<public-guide-url>" --out "outputs/<DeckName>/02_source_acquisition" --json
hsconfig source-autopilot --deck-name "<DeckName>" --deck-code "<DeckCode>" --source-search-results-json "outputs/<DeckName>/02_source_acquisition/source_search_results.json" --out "outputs/<DeckName>/03_source_autopilot" --json
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --source-url "<public-guide-url>" --json
```
```

- [ ] **Step 3: Update guide research policy**

Add:

```markdown
Online source acquisition promotion rule:

- Public guide pages can promote `mulligan_keep`, `mulligan_discard`, `targeting_rule`, `card_role`, `known_bad_pattern`, and exact `combo_sequence` only when the claim is explicit and deck-matching.
- Official/static card data can promote deterministic identity and supported effect lanes such as `hero_power_transform`, but cannot prove opening-hand keeps or exact combo order by itself.
- Decklists, meta pages, snippets, and fetch failures remain source-informed or diagnostic. They do not count as `SOURCE_BACKED_STRONG`.
- A valid deck must never fail only because public source acquisition is weak.
```

- [ ] **Step 4: Update local HSConfig skill**

In `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`, update the normal command guidance:

```markdown
When the user asks for a fresh optimal config and wants public guide/source backing, prefer:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --source-url "<public-guide-url>" --json
```

If no public guide URL is known yet, use web research to identify candidate public guide URLs, then pass them as repeated `--source-url` values. Weak or missing source coverage is not a blocker; it must stay visible in source acquisition and operator reports.
```

- [ ] **Step 5: Run docs scan**

Run:

```powershell
rg -n "online-source|source-acquire|SOURCE_BACKED_STRONG|default-only|Darkbishop" docs/operator "C:\Users\darbo\.codex\skills\hsconfig\SKILL.md"
```

Expected: command/path references are present; no sentence says source strength blocks valid config creation.

- [ ] **Step 6: Commit docs and skill change**

Run:

```powershell
git add docs/operator/README.md docs/operator/source-builder-workflow.md docs/operator/guide-research-policy.md
git add "C:\Users\darbo\.codex\skills\hsconfig\SKILL.md"
git commit -m "docs: document autonomous online source path"
```

If git refuses to add the user-level skill because it is outside the repository, commit the repo docs and mention the local skill edit separately in the implementation summary.

---

### Task 8: Final Verification And Git Hygiene

**Files:**
- No new source files.
- Optional ignored verification output under `outputs/_verification_shadowpriest_online_source`.

**Interfaces:**
- Consumes all completed tasks.
- Produces final evidence for implementation completion.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_acquisition.py tests/test_source_claim_compiler.py tests/test_source_acquire_cli.py tests/test_configure_online_source.py -q
```

Expected: PASS.

- [ ] **Step 2: Run source-contract regression tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py tests/test_configure_auto_source.py tests/test_source_contract_conformance.py tests/test_source_to_runtime_explainability.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 3: Run broader test suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: PASS. If the full suite exceeds the local timeout, rerun with a longer timeout and report the exact timeout boundary plus all focused test results.

- [ ] **Step 4: Run current ShadowPriest verification package**

Run:

```powershell
$env:PYTHONPATH='src'; python -m hsconfig configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out "outputs/_verification_shadowpriest_online_source" --online-source --auto-source --source-url "https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest" --json
```

Expected:

- Exit code `0`.
- `outputs/_verification_shadowpriest_online_source/02_source_acquisition/source_search_results.json` exists.
- `outputs/_verification_shadowpriest_online_source/03_source_autopilot/source_autopilot_report.json` exists.
- `outputs/_verification_shadowpriest_online_source/04_package/reports/operator_summary.json` has `technical_status=VALID_PACKAGE`.
- If the live guide still exposes the expected text, `semantic_status=SOURCE_BACKED_STRONG`.
- If the guide markup changed, package remains valid and the first missing source link is visible.

- [ ] **Step 5: Inspect diff and status**

Run:

```powershell
git diff --stat
git status --short --branch
```

Expected: only intentional source, test, docs, and optional local skill changes.

- [ ] **Step 6: Commit and push**

Run:

```powershell
git add src/hsconfig/source_acquisition.py src/hsconfig/source_claim_compiler.py src/hsconfig/commands/source_workflow.py src/hsconfig/commands/configure.py src/hsconfig/cli_parser.py src/hsconfig/cli.py tests docs/operator
git commit -m "feat: add autonomous source acquisition path"
git push origin codex/hsconfig-source-backed-strong-autopilot
```

Expected: push succeeds. Merge to `main` only after focused and broad verification are green.

---

## Self-Review

**Spec coverage:**

- Source-/Contract-Logik: Tasks 1-5 feed public source records through existing source-autopilot and operator summary instead of creating a parallel authority.
- Kein `default only`: Task 6 makes weak/no-source behavior visible and non-promoting; Task 8 verifies operator summary surfaces.
- Schmal: two new pure modules, one CLI command, one configure bridge; no new dependency and no replay/HSTuner scope.
- Autonom: `configure --online-source --auto-source` can acquire URLs, compile claims, create source documents, and build the package in one operator command.
- `SOURCE_BACKED_STRONG`: guide/static/decklist boundaries are explicit in tasks, docs, tests, and final verification.
- ShadowPriest/Darkbishop: tests preserve effect behavior and prevent opening-hand keep inference.

**Placeholder scan:** No banned placeholder patterns or unspecified test step remains.

**Type consistency:**

- `collect_public_source_records` returns `source_records`; `compile_source_search_records` returns `records`; existing `source_autopilot` consumes `records`.
- CLI names are stable across parser, command, tests, docs: `source-acquire`, `--online-source`, `--auto-source`, `--source-url`, `--source-fixture-url-map-json`, `--source-fetch-timeout-seconds`.
- Report filenames are stable: `source_acquisition_report.json`, `source_claim_compiler_report.json`, `source_search_results.json`, `source_autopilot_report.json`.
