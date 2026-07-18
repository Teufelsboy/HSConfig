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
    publication_year: int | None = None
    source_visibility: str = "full_text"
    strength_ceiling: str = "candidate_partial"
    expected_claim_kinds: tuple[str, ...] = ()
    first_missing_source_action: str = "add_current_deck_guide_or_mulligan_guide"


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
            publication_year=2026,
            strength_ceiling="runtime_claims_possible",
            expected_claim_kinds=(
                "archetype",
                "gameplan_posture",
                "mulligan_keep",
                "mulligan_discard",
                "targeting_rule",
                "hero_power_transform",
            ),
            first_missing_source_action="none",
        ),
    ),
    "ctapaladin": (
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/1u0kd33/any_help_with_cta_paladin_mulligan/",
            source_family="community_guide",
            deck_name="CtAPaladin",
            archetype="wild_cta_paladin",
            reason=(
                "current Wild CtA Paladin mulligan discussion with explicit "
                "Boogie Down, Call to Arms, disruption, board-clear, and "
                "matchup keep guidance"
            ),
            priority=10,
            expected_strength="guide_current_mulligan_match",
            publication_year=2026,
            strength_ceiling="runtime_claims_possible",
            expected_claim_kinds=("mulligan_keep",),
            first_missing_source_action="none",
        ),
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/1jydz4q/i_dont_understand_how_cta_paladin_is_any_good/",
            source_family="community_guide",
            deck_name="CtAPaladin",
            archetype="wild_cta_paladin",
            reason=(
                "older Wild CtA Paladin discussion with aggro posture and "
                "Crab Rider role support, without current card-specific "
                "mulligan closure"
            ),
            priority=9,
            expected_strength="guide_archetype_partial",
            publication_year=2025,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=("gameplan_posture", "card_role"),
            first_missing_source_action="add_current_cta_paladin_mulligan_keep_source",
        ),
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/1rzz9b1/rank_1_legend_with_cta_and_qldh/",
            source_family="community_guide",
            deck_name="CtAPaladin",
            archetype="wild_cta_paladin",
            reason=(
                "current Wild CtA Paladin positioning and card-choice evidence "
                "without full mulligan closure"
            ),
            priority=8,
            expected_strength="guide_current_archetype_partial",
            publication_year=2026,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=("gameplan_posture", "card_role", "mechanic_usage"),
            first_missing_source_action="add_current_cta_paladin_mulligan_keep_source",
        ),
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/1qdrc06/the_xl_cta_paladin_experience/",
            source_family="community_guide",
            deck_name="CtAPaladin",
            archetype="wild_cta_paladin",
            reason=(
                "current Wild CtA Paladin posture support without enough "
                "card-specific mulligan closure to promote by itself"
            ),
            priority=7,
            expected_strength="guide_current_archetype_partial",
            publication_year=2026,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=("gameplan_posture", "card_role"),
            first_missing_source_action="add_current_cta_paladin_mulligan_keep_source",
        ),
    ),
    "piraterogue": (
        SourceCandidate(
            url="https://www.hearthpwn.com/decks/1441097-ww-pirate-rogue",
            source_family="guide",
            deck_name="PirateRogue",
            archetype="wild_pirate_rogue",
            reason="Wild Pirate Rogue guide with tempo posture, mulligan, and combo package context",
            priority=8,
            expected_strength="guide_evergreen_archetype_partial",
            publication_year=2024,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=(
                "gameplan_posture",
                "mulligan_keep",
                "mulligan_discard",
                "card_role",
                "combo_sequence",
            ),
            first_missing_source_action="add_current_pirate_rogue_mulligan_or_role_source",
        ),
    ),
    "discolock": (
        SourceCandidate(
            url="https://www.reddit.com/r/CompetitiveHS/comments/1s7nr67/easy_wild_legend_discolock/",
            source_family="community_guide",
            deck_name="Discolock",
            archetype="wild_discard_warlock",
            reason="recent Wild Discolock legend writeup with mulligan and pressure posture",
            priority=10,
            expected_strength="guide_current_deck_match",
            publication_year=2026,
            strength_ceiling="runtime_claims_possible",
            expected_claim_kinds=(
                "gameplan_posture",
                "mulligan_keep",
                "mulligan_discard",
                "card_role",
            ),
            first_missing_source_action="none",
        ),
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/1nhpuu1/how_to_play_discolock/",
            source_family="community_guide",
            deck_name="Discolock",
            archetype="wild_discard_warlock",
            reason=(
                "Wild Discolock advice discussion with discard-priority "
                "context, without current full-text closure by itself"
            ),
            priority=8,
            expected_strength="guide_archetype_partial",
            publication_year=2025,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=("gameplan_posture", "mulligan_discard"),
            first_missing_source_action="add_current_discolock_full_text_mulligan_or_gameplan_source",
        ),
        SourceCandidate(
            url="https://hearthstone-decks.net/wild-decks/warlock-wild-decks/",
            source_family="decklist",
            deck_name="Discolock",
            archetype="wild_discard_warlock",
            reason="current Wild Warlock index context only",
            priority=3,
            expected_strength="meta_context_only",
            publication_year=2026,
            source_visibility="decklist_only",
            strength_ceiling="context_only",
            expected_claim_kinds=(),
            first_missing_source_action="add_current_full_text_mulligan_or_gameplan_source",
        ),
    ),
    "treantdruid": (
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/1mjge7n/treant_druid_to_early_legend/",
            source_family="community_guide",
            deck_name="TreantDruid",
            archetype="wild_treant_druid",
            reason="Wild Treant Druid legend writeup with mulligan, posture, and matchup notes",
            priority=10,
            expected_strength="guide_current_deck_match",
            publication_year=2026,
            strength_ceiling="runtime_claims_possible",
            expected_claim_kinds=(
                "gameplan_posture",
                "mulligan_keep",
                "card_role",
            ),
            first_missing_source_action="none",
        ),
        SourceCandidate(
            url="https://www.reddit.com/r/CompetitiveHS/comments/1oty3l8/treant_druid_wild_legend_deck/",
            source_family="community_guide",
            deck_name="TreantDruid",
            archetype="wild_treant_druid",
            reason=(
                "current Wild Treant Druid guide-style legend writeup with "
                "posture support, without card-specific mulligan closure by itself"
            ),
            priority=9,
            expected_strength="guide_current_archetype_partial",
            publication_year=2026,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=(
                "gameplan_posture",
                "card_role",
            ),
            first_missing_source_action="add_current_treant_druid_mulligan_keep_source",
        ),
    ),
    "imbuemage": (
        SourceCandidate(
            url="https://www.hearthpwn.com/decks/1462266-wild-imbue-mage",
            source_family="guide",
            deck_name="ImbueMage",
            archetype="wild_imbue_mage",
            reason="current Wild Imbue Mage public guide candidate for hero-power package closure",
            priority=8,
            expected_strength="guide_current_deck_match",
            publication_year=2026,
            strength_ceiling="runtime_claims_possible",
            expected_claim_kinds=(
                "gameplan_posture",
                "mulligan_keep",
                "card_role",
                "hero_power_transform",
            ),
            first_missing_source_action="none",
        ),
    ),
    "mechpala": (
        SourceCandidate(
            url=(
                "https://www.reddit.com/r/CompetitiveHS/comments/1rmjjhf/"
                "whats_working_and_what_isnt_friday_march_06_2026/"
            ),
            source_family="community_guide",
            deck_name="MechPala",
            archetype="wild_mech_paladin",
            reason=(
                "current Wild Mech Paladin discussion with explicit "
                "Treasuregill/Radar Detector mulligan guidance and "
                "Galvanizer combo-flood plan, but still missing full "
                "card-specific source closure"
            ),
            priority=10,
            expected_strength="guide_current_mulligan_and_combo_partial",
            publication_year=2026,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=(
                "gameplan_posture",
                "mulligan_keep",
                "card_role",
                "combo_sequence",
            ),
            first_missing_source_action="add_card_specific_source_claim",
        ),
        SourceCandidate(
            url="https://www.hearthpwn.com/decks/1463315-galvanizer-scrapyard-hand-dump",
            source_family="guide",
            deck_name="MechPala",
            archetype="wild_mech_paladin",
            reason=(
                "current Wild Mech Paladin guide supplement with gameplan, "
                "card-role, and mech-synergy context but no exact mulligan closure"
            ),
            priority=7,
            expected_strength="guide_current_archetype_partial",
            publication_year=2026,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=("gameplan_posture", "card_role", "mechanic_usage"),
            first_missing_source_action="add_card_specific_source_claim",
        ),
        SourceCandidate(
            url="https://hearthstone-decks.net/wild-decks/paladin-wild-decks/wild-mech-paladin/",
            source_family="decklist",
            deck_name="MechPala",
            archetype="wild_mech_paladin",
            reason="current Wild Mech Paladin decklist/category context only",
            priority=4,
            expected_strength="meta_context_only",
            publication_year=2026,
            source_visibility="decklist_only",
            strength_ceiling="context_only",
            expected_claim_kinds=(),
            first_missing_source_action="add_current_full_text_mulligan_or_gameplan_source",
        ),
    ),
    "kingslayer": (
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/1p8sp6f/legend_1478_kingsbane_rogue/",
            source_family="community_guide",
            deck_name="Kingslayer",
            archetype="wild_kingsbane_rogue",
            reason="Wild Kingsbane/Kingslayer legend writeup candidate with partial weapon-plan evidence",
            priority=7,
            expected_strength="guide_current_archetype_partial",
            publication_year=2026,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=("gameplan_posture", "mulligan_keep", "card_role"),
            first_missing_source_action="add_kingslayer_quick_pick_mulligan_source",
        ),
    ),
    "boarlock": (
        SourceCandidate(
            url="https://www.hearthpwn.com/decks/1455610-elwynn-boar-sneak-attack-otk",
            source_family="guide",
            deck_name="Boarlock",
            archetype="wild_boarlock",
            reason="Wild Boarlock combo writeup with combo sequence and partial mulligan evidence",
            priority=7,
            expected_strength="guide_combo_partial",
            publication_year=2025,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=("combo_sequence", "mulligan_keep", "card_role"),
            first_missing_source_action="add_boarlock_fracking_mulligan_source",
        ),
        SourceCandidate(
            url="https://hearthstone-decks.net/wild-decks/warlock-wild-decks/",
            source_family="decklist",
            deck_name="Boarlock",
            archetype="wild_boarlock",
            reason="current Wild Warlock index context only",
            priority=3,
            expected_strength="meta_context_only",
            publication_year=2026,
            source_visibility="decklist_only",
            strength_ceiling="context_only",
            expected_claim_kinds=(),
            first_missing_source_action="add_current_full_text_mulligan_or_gameplan_source",
        ),
    ),
    "piratedh": (
        SourceCandidate(
            url="https://hs.cardsrealm.com/en-bz/articles/hearthstone-wild-deck-guide-pirate-demon-hunter-become-a-legend",
            source_family="guide",
            deck_name="PirateDH",
            archetype="wild_pirate_demon_hunter",
            reason=(
                "historical full Pirate Demon Hunter guide with mulligan, "
                "pressure posture, card roles, and weapon/pirate usage"
            ),
            priority=10,
            expected_strength="guide_historical_archetype_match",
            publication_year=2024,
            strength_ceiling="runtime_claims_possible",
            expected_claim_kinds=(
                "gameplan_posture",
                "mulligan_keep",
                "card_role",
                "mechanic_usage",
            ),
            first_missing_source_action="none",
        ),
        SourceCandidate(
            url="https://hearthstone-decks.net/pirate-demon-hunter-223-legend-mangekou-score-49-32/",
            source_family="decklist_with_strategy",
            deck_name="PirateDH",
            archetype="wild_pirate_demon_hunter",
            reason="Wild Pirate Demon Hunter legend page with partial strategy and mulligan context",
            priority=7,
            expected_strength="guide_archetype_partial",
            publication_year=2025,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=("gameplan_posture", "mulligan_keep", "card_role"),
            first_missing_source_action="add_pirate_dh_card_role_or_mulligan_source",
        ),
    ),
    "cutewarrior": (
        SourceCandidate(
            url="https://www.reddit.com/r/wildhearthstone/comments/13e0x4w/powersliding_with_cute_warrior_to_rank_278/",
            source_family="community_guide",
            deck_name="CuteWarrior",
            archetype="wild_cute_warrior",
            reason="evergreen Wild Cute Warrior guide with mulligan and payoff-role context",
            priority=6,
            expected_strength="guide_evergreen_archetype_partial",
            publication_year=2023,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=("gameplan_posture", "mulligan_keep", "card_role"),
            first_missing_source_action="add_current_full_text_mulligan_or_gameplan_source",
        ),
        SourceCandidate(
            url="https://hearthstone-decks.net/wild-decks/warrior-wild-decks/",
            source_family="decklist",
            deck_name="CuteWarrior",
            archetype="wild_cute_warrior",
            reason="current Wild Warrior index context only",
            priority=3,
            expected_strength="meta_context_only",
            publication_year=2026,
            source_visibility="decklist_only",
            strength_ceiling="context_only",
            expected_claim_kinds=(),
            first_missing_source_action="add_current_full_text_mulligan_or_gameplan_source",
        ),
    ),
    "bigshaman": (
        SourceCandidate(
            url="https://hearthstone-decks.net/big-shaman-202-legend-abadon-score-98-64/",
            source_family="decklist_with_strategy",
            deck_name="BigShaman",
            archetype="wild_big_shaman",
            reason=(
                "current Wild Big Shaman legend page with explicit initial "
                "mulligan names and Y'Shaarj variant context"
            ),
            priority=10,
            expected_strength="current_legend_mulligan_source",
            publication_year=2025,
            strength_ceiling="runtime_claims_possible",
            expected_claim_kinds=(
                "archetype",
                "gameplan_posture",
                "mulligan_keep",
            ),
            first_missing_source_action="none",
        ),
        SourceCandidate(
            url="https://www.hearthpwn.com/decks/1186371-big-shaman-in-depth-guide",
            source_family="guide",
            deck_name="BigShaman",
            archetype="wild_big_shaman",
            reason=(
                "historical Wild Big Shaman archetype guide with strategy "
                "context, too stale for current-list strong closure by itself"
            ),
            priority=8,
            expected_strength="guide_stale_archetype_partial",
            publication_year=2018,
            strength_ceiling="candidate_partial",
            expected_claim_kinds=(
                "gameplan_posture",
                "mechanic_usage",
                "combo_sequence",
                "card_role",
            ),
            first_missing_source_action="add_current_big_shaman_full_text_mulligan_or_gameplan_source",
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
