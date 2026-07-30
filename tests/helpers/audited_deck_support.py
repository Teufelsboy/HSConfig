from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any


# Test-only identity mapping for visibility deck decoding. These rows are not
# part of the audited 192-row semantic snapshot and must never be used as
# semantic evidence.
VISIBILITY_IDENTITY_DECODE_ONLY_CARD_IDS = {
    1783: "FP1_004",
    2551: "AT_012",
    39767: "KAR_092",
    40299: "CFM_066",
    40323: "CFM_020",
    40373: "CFM_603",
    40583: "CFM_760",
    41173: "UNG_032",
    43408: "ICC_830",
    53756: "ULD_003",
    53822: "ULD_240",
    59029: "SCH_311",
    61585: "DMF_107",
    61944: "YOP_006",
    62879: "BAR_315",
    69566: "CORE_EX1_193",
    69607: "CORE_EX1_287",
    69702: "CORE_UNG_020",
    70020: "AV_324",
    70027: "AV_331",
    71781: "TSC_908",
    72007: "TSC_032",
    76314: "CORE_LOE_011",
    77305: "REV_249",
    78371: "REV_513",
    79486: "REV_841",
    84351: "MAW_101",
    86235: "CORE_LOOT_101",
    86626: "RLK_222",
    90749: "ETC_080",
    94822: "JAM_036",
    95336: "JAM_001",
    98403: "TTN_742",
    98413: "JAM_027",
    101955: "WW_384",
    101958: "WW_387",
    102221: "CORE_SW_072",
    102225: "CORE_CFM_790",
    102592: "WON_058",
    102718: "CORE_SW_448",
}


def captured_source_documents(
    deck: Mapping[str, Any],
) -> dict[str, Any]:
    fixture_bytes = f"{deck['deck_name']}:diagnostic-fixture".encode()
    return {
        "source_documents": [
            {
                "source_url": (
                    "https://example.invalid/diagnostic-fixture"
                ),
                "source_title": (
                    f"{deck['deck_name']} diagnostic fixture"
                ),
                "source_family": "guide",
                "retrieved_at": "2026-07-27T00:00:00Z",
                "acquisition_provenance": {
                    "mode": "captured_record",
                    "authority": "captured_unverified",
                    "content_sha256": (
                        f"sha256:{sha256(fixture_bytes).hexdigest()}"
                    ),
                },
                "source_visibility": "full_text",
                "source_lane": "archetype_matched_public_guide",
                "deck_name": str(deck["deck_name"]),
                "archetype": "diagnostic_fixture",
                "deck_match_scope": "archetype_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 0,
                        "decoded_candidate_count": 0,
                        "matched": False,
                        "matched_deck_fingerprint": "",
                        "candidate_deck_code_hashes": [],
                    }
                },
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "scope": "deck",
                        "cards": [],
                        "stance": "diagnostic_fixture",
                        "evidence_text_short": (
                            "Diagnostic captured source used for "
                            "read-only acceptance."
                        ),
                        "source_confidence": "medium",
                        "promotion_eligible": False,
                    }
                ],
            }
        ]
    }


__all__ = (
    "VISIBILITY_IDENTITY_DECODE_ONLY_CARD_IDS",
    "captured_source_documents",
)
