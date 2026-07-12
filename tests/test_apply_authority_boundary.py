from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

ACTIVE_APPLY_PATHS = [
    "src/hsconfig/apply_gate.py",
    "src/hsconfig/runtime_apply.py",
    "src/hsconfig/commands/apply.py",
]

DIAGNOSTIC_ONLY_TOKENS = [
    "source_contract_audit",
    "contract_spine_rows",
    "claim_lifecycle_rows",
    "source_contract_conformance",
]

FORBIDDEN_DIAGNOSTIC_IMPORTS = [
    "from hsconfig.contract_doctor",
    "import hsconfig.contract_doctor",
    "from hsconfig.source_contract_audit",
    "import hsconfig.source_contract_audit",
    "from hsconfig.source_contract_conformance",
    "import hsconfig.source_contract_conformance",
]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_active_apply_paths_do_not_consume_source_contract_diagnostics():
    for relative_path in ACTIVE_APPLY_PATHS:
        content = _read(relative_path)
        for token in DIAGNOSTIC_ONLY_TOKENS:
            assert token not in content, (relative_path, token)


def test_apply_gate_uses_operator_summary_as_single_authority():
    content = _read("src/hsconfig/apply_gate.py")

    assert 'package / "reports" / "operator_summary.json"' in content
    assert "technical_status" in content
    assert '"VALID_PACKAGE"' in content
    assert "source_contract_audit" not in content


def test_active_apply_paths_do_not_import_diagnostic_authorities():
    for relative_path in ACTIVE_APPLY_PATHS:
        content = _read(relative_path)
        for token in FORBIDDEN_DIAGNOSTIC_IMPORTS:
            assert token not in content, (relative_path, token)
