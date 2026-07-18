from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from hsconfig.source_candidate_registry import SourceCandidate, source_candidates_for_deck


SOURCE_CLOSURE_INTAKE_RECEIPT_RELATIVE_PATH = (
    "reports/02_source_acquisition/source_closure_intake_receipt.json"
)


@dataclass(frozen=True)
class SourceClosureIntakeSourceRow:
    url: str
    source_family: str
    source_visibility: str
    strength_ceiling: str
    expected_claim_kinds: tuple[str, ...]
    first_missing_source_action: str
    promotion_eligible_seed: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "source_family": self.source_family,
            "source_visibility": self.source_visibility,
            "strength_ceiling": self.strength_ceiling,
            "expected_claim_kinds": list(self.expected_claim_kinds),
            "first_missing_source_action": self.first_missing_source_action,
            "promotion_eligible_seed": self.promotion_eligible_seed,
        }


@dataclass(frozen=True)
class SourceClosureIntakeReceipt:
    deck_name: str
    deck_code: str
    source_rows: tuple[SourceClosureIntakeSourceRow, ...]
    fetched_record_count: int

    def to_json(self) -> dict[str, Any]:
        used_urls = [row.url for row in self.source_rows]
        first_missing_source_action = _first_missing_source_action(self.source_rows)
        promotion_eligible_seed_count = sum(
            1 for row in self.source_rows if row.promotion_eligible_seed
        )
        return {
            "schema_version": 1,
            "authority": "diagnostic_only",
            "deck_name": self.deck_name,
            "deck_code": self.deck_code,
            "candidate_count": len(self.source_rows),
            "fetched_record_count": self.fetched_record_count,
            "used_urls": used_urls,
            "source_rows": [row.to_json() for row in self.source_rows],
            "non_promoting_support_urls": [
                row.url for row in self.source_rows if not row.promotion_eligible_seed
            ],
            "promotion_eligible_seed_count": promotion_eligible_seed_count,
            "first_missing_source_action": first_missing_source_action,
            "source_status_apply_blocking": False,
        }


def build_source_closure_intake_receipt(
    deck_name: str,
    deck_code: str,
    *,
    candidate_rows: Sequence[SourceCandidate] | None = None,
    fetched_records: Sequence[Mapping[str, object]] = (),
) -> dict[str, Any]:
    rows = (
        list(candidate_rows)
        if candidate_rows is not None
        else source_candidates_for_deck(deck_name, deck_code)
    )
    receipt_rows = tuple(_candidate_to_receipt_row(row) for row in rows)
    return SourceClosureIntakeReceipt(
        deck_name=deck_name,
        deck_code=deck_code,
        source_rows=receipt_rows,
        fetched_record_count=len(fetched_records),
    ).to_json()


def summarize_source_closure_intake(receipt: Mapping[str, object]) -> dict[str, object]:
    return {
        "authority": "diagnostic_only",
        "candidate_count": _int_value(receipt.get("candidate_count", 0)),
        "promotion_eligible_seed_count": _int_value(
            receipt.get("promotion_eligible_seed_count", 0)
        ),
        "first_missing_source_action": str(
            receipt.get(
                "first_missing_source_action",
                "add_current_deck_guide_or_mulligan_guide",
            )
        ),
        "source_status_apply_blocking": False,
        "receipt_path": SOURCE_CLOSURE_INTAKE_RECEIPT_RELATIVE_PATH,
    }


def _candidate_to_receipt_row(candidate: SourceCandidate) -> SourceClosureIntakeSourceRow:
    expected_claim_kinds = tuple(candidate.expected_claim_kinds)
    if candidate.strength_ceiling == "context_only":
        expected_claim_kinds = ()
    return SourceClosureIntakeSourceRow(
        url=candidate.url,
        source_family=candidate.source_family,
        source_visibility=candidate.source_visibility,
        strength_ceiling=candidate.strength_ceiling,
        expected_claim_kinds=expected_claim_kinds,
        first_missing_source_action=candidate.first_missing_source_action,
        promotion_eligible_seed=_is_promotion_eligible_seed(candidate),
    )


def _is_promotion_eligible_seed(candidate: SourceCandidate) -> bool:
    return (
        candidate.strength_ceiling == "runtime_claims_possible"
        and candidate.first_missing_source_action == "none"
        and candidate.source_visibility == "full_text"
        and bool(candidate.expected_claim_kinds)
    )


def _first_missing_source_action(
    rows: Sequence[SourceClosureIntakeSourceRow],
) -> str:
    for row in rows:
        if row.first_missing_source_action != "none":
            return row.first_missing_source_action
    return "none"


def _int_value(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
