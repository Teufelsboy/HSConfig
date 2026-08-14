from __future__ import annotations

from scripts.check_contract_guardrails import FOCUSED_CONTRACT_TESTS


def test_guardrail_suite_includes_handoff_and_research_sentinel_tests() -> None:
    assert "tests/test_configure_handoff_contract.py" in FOCUSED_CONTRACT_TESTS
    assert "tests/test_research_result_contract_sentinel.py" in FOCUSED_CONTRACT_TESTS
