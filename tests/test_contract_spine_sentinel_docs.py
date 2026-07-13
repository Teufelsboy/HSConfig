from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_contract_spine_sentinel_is_documented_as_diagnostic_only():
    skill = _read(".agents/skills/hsconfig/SKILL.md")
    operator = _read("docs/operator/README.md")

    for content in (skill, operator):
        assert "contract-spine-sentinel" in content
        assert "diagnostic" in content.lower()
        assert "operator_summary.json" in content


def test_docs_do_not_make_sentinel_the_normal_operator_path():
    operator = _read("docs/operator/README.md")

    assert "Preferred normal path" in operator or "configure" in operator
    assert "contract-spine-sentinel -> apply" not in operator
    assert "contract-spine-sentinel --apply" not in operator
