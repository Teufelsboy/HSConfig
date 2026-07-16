from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class SourceCandidate:
    url: str
    source_family: str
    deck_name: str
    archetype: str
    reason: str
    priority: int
    expected_strength: str
    format_scope: str = "wild"
    evergreen_wild_archetype: bool = False


_KNOWN_CANDIDATES: dict[str, tuple[SourceCandidate, ...]] = {
    "shadowpriest": (
        SourceCandidate(
            url="https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest",
            source_family="guide",
            deck_name="ShadowPriest",
            archetype="wild_aggro_shadow_priest",
            reason=(
                "current public Wild Shadow Priest guide with explicit mulligan "
                "and hero power guidance"
            ),
            priority=10,
            expected_strength="guide_current_deck_match",
        ),
    ),
    "bigshaman": (
        SourceCandidate(
            url="https://www.hearthpwn.com/decks/1186371-big-shaman-in-depth-guide",
            source_family="guide",
            deck_name="BigShaman",
            archetype="wild_big_shaman",
            reason="evergreen Wild archetype guide with deck strategy and matchup context",
            priority=8,
            expected_strength="guide_evergreen_wild_archetype",
            evergreen_wild_archetype=True,
        ),
    ),
}


def source_candidates_for_deck(
    deck_name: str,
    deck_code: str | None = None,
) -> list[SourceCandidate]:
    del deck_code
    candidates = list(_KNOWN_CANDIDATES.get(_slug(deck_name), ()))
    candidates.sort(key=lambda candidate: (-candidate.priority, candidate.url))
    return candidates


def candidate_urls(candidates: Sequence[SourceCandidate]) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for candidate in candidates:
        url = candidate.url.strip()
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _slug(value: str) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())
