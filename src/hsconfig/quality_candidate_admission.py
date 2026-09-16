"""Additional checks for NEW controller receipts, never stored-package authority.

Historical validators, serializers, intent digests and review facts remain the
reconstruction contract. Admission rejects unsafe new use of their known limits;
it does not silently rewrite the candidate or confer runtime authority.
"""

from decimal import Decimal
from itertools import combinations

from hsconfig.condition_format import (
    runtime_condition_is_provably_impossible,
    runtime_conditions_are_provably_disjoint,
)
from hsconfig.starter_candidate import (
    ValidatedStarterCandidate,
    _globalvalues_semantic_projection,
)
from hsconfig.starter_context import StarterContext


def validate_quality_candidate_admission(
    candidate: ValidatedStarterCandidate, context: StarterContext,
) -> None:
    """Reject a new schema-3 admission; unchanged sealed inputs remain untouched."""
    value = candidate.document.to_value()
    context_value = context.document.to_value()
    if value["schema_version"] != 3 or context_value["schema_version"] != 3:
        raise ValueError("starter_candidate_schema_pair_invalid")
    if value["starter_context_sha256"] != context.document.content_sha256:
        raise ValueError("starter_candidate_context_sha256_mismatch")

    condition_rows = [*value["mulligan"], *value["card_rules"]]
    if value["combo"] is not None:
        condition_rows.append(value["combo"])
    for block in value["globalvalues"].values():
        if isinstance(block, dict):
            condition_rows.extend(block["values"])
    for row in condition_rows:
        condition = " ".join(row["condition"].split())
        if " AND " in condition and " OR " in condition:
            raise ValueError("starter_candidate_condition_precedence_ambiguous")
        if runtime_condition_is_provably_impossible(condition):
            raise ValueError("starter_candidate_condition_impossible")

    metadata = context_value["card_metadata"]
    for row in value["card_rules"]:
        card_type = metadata[row["runtime_card_id"]]["type"]
        if (
            row["behavior_block"] == "BeforeUseHeroPowerBonus"
            and card_type not in {None, "UNKNOWN", "HERO_POWER"}
        ):
            raise ValueError("starter_candidate_card_surface_type_invalid")

    compiled_positions = {
        document.to_value()["rule_id_suffix"]: index
        for index, document in enumerate(candidate.card_behavior_rows)
    }
    for earlier, later in combinations(value["card_rules"], 2):
        if (
            earlier["runtime_card_id"] == later["runtime_card_id"]
            and earlier["behavior_block"] == later["behavior_block"]
            and compiled_positions[earlier["rule_id"]] > compiled_positions[later["rule_id"]]
            and Decimal(earlier["value"]) != Decimal(later["value"])
            and not runtime_conditions_are_provably_disjoint(
                " ".join(earlier["condition"].split()), " ".join(later["condition"].split())
            )
        ):
            raise ValueError("starter_candidate_card_order_ambiguous")

    baseline = _globalvalues_semantic_projection(context_value["globalvalues_baseline"]["values"])
    desired = _globalvalues_semantic_projection(value["globalvalues"])
    for key, block in desired.items():
        if not isinstance(block, dict) or block == baseline[key]:
            continue
        # Every ambiguous changed block is refused, not just permutations of the
        # baseline: otherwise two new orders could still share the legacy digest.
        for left, right in combinations(block["values"], 2):
            if (
                left["value"] != right["value"]
                and not runtime_conditions_are_provably_disjoint(
                    " ".join(left["condition"].split()), " ".join(right["condition"].split())
                )
            ):
                raise ValueError("starter_candidate_globalvalue_order_ambiguous")
