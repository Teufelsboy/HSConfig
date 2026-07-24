import pytest

from hsconfig.cli import _build_parser
from hsconfig.cli_parser import build_parser


INSPECTED_PATH = (
    "source-manifest -> source-autopilot or draft-source-documents -> "
    "research-deck -> prepare -> validate -> apply"
)
OLD_LOWER_LEVEL_LABEL = "Lower-level " + "normal path:"


def test_cli_parser_module_builds_same_root_help():
    help_text = build_parser().format_help()

    assert "HSConfig builds lean HearthRanger VisionAI CustomConfig packages" in help_text
    assert "docs/operator/README.md" in help_text
    assert "Preferred normal path: configure" in help_text
    assert "Lower-level inspected path:" in help_text
    assert INSPECTED_PATH in help_text
    assert OLD_LOWER_LEVEL_LABEL not in help_text


def test_root_help_names_preferred_lower_level_and_expert_paths():
    help_text = _build_parser().format_help()

    assert "Preferred normal path: configure" in help_text
    assert "Lower-level inspected path:" in help_text
    assert INSPECTED_PATH in help_text
    assert OLD_LOWER_LEVEL_LABEL not in help_text
    assert "Expert and legacy path:" in help_text
    assert "build, --claims-json, --cards-json, --plan-reports-dir" in help_text


def test_root_help_names_configure_as_preferred_normal_path():
    help_text = _build_parser().format_help()

    assert "Preferred normal path: configure" in help_text
    assert "Lower-level inspected path:" in help_text
    assert INSPECTED_PATH in help_text
    assert OLD_LOWER_LEVEL_LABEL not in help_text


def test_root_help_points_to_operator_docs():
    help_text = _build_parser().format_help()

    assert "docs/operator/README.md" in help_text
    assert "Preferred normal path: configure" in help_text
    assert "Lower-level inspected path:" in help_text
    assert INSPECTED_PATH in help_text
    assert OLD_LOWER_LEVEL_LABEL not in help_text
    assert "Expert and legacy path:" in help_text


def _subcommand_help(command: str, capsys) -> str:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([command, "--help"])
    return capsys.readouterr().out


def test_prepare_help_is_marked_inspected_package_stage(capsys):
    help_text = _subcommand_help("prepare", capsys)

    assert "Inspected package creation stage" in help_text
    assert "Normal package creation path" not in help_text


def test_source_stage_help_is_marked_inspected_not_normal(capsys):
    for command in ("source-manifest", "draft-source-documents", "research-deck"):
        help_text = _subcommand_help(command, capsys)
        assert "inspected" in help_text.lower()
        assert "normal path" not in help_text.lower()


def test_configure_help_is_marked_preferred_normal_path(capsys):
    help_text = _subcommand_help("configure", capsys)

    assert "Preferred one-command pre-run package path" in help_text
    assert "--deck-name" in help_text
    assert "--deck-code" in help_text
    assert "--runtime-root" in help_text
    assert "--out" in help_text
    assert "--source-evidence-json" in help_text
    assert "--apply" in help_text


def test_prepare_help_groups_required_inputs_before_expert_fixture_inputs(capsys):
    help_text = _subcommand_help("prepare", capsys)

    assert "required package inputs" in help_text.lower()
    assert "expert/fixture inputs" in help_text.lower()
    assert help_text.lower().index("required package inputs") < help_text.lower().index(
        "expert/fixture inputs"
    )
    assert "--deck-name" in help_text
    assert "--deck-code" in help_text
    assert "--guide-sources-json" in help_text
    assert "--cards-json" in help_text
    assert "--claims-json" in help_text


def test_build_help_is_marked_expert_path(capsys):
    help_text = _subcommand_help("build", capsys)

    assert "Expert lower-level package builder" in help_text


def test_root_help_states_negative_scope():
    help_text = build_parser().format_help()

    assert "pre-run only" in help_text
    assert "does not parse replays, inspect winrate, or tune after games" in help_text


def test_apply_help_marks_allow_source_informed_as_legacy_diagnostic_flag(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["apply", "--help"])
    help_text = capsys.readouterr().out

    assert "--allow-source-informed" in help_text
    assert "legacy" in help_text.lower()
    assert "no-op" in help_text.lower()


def test_contract_spine_sentinel_help_is_diagnostic_only(capsys):
    help_text = _subcommand_help("contract-spine-sentinel", capsys)

    assert "read-only contract-spine drift diagnostic" in help_text
    assert "does not grant apply permission" in help_text
    assert "--out" in help_text
    assert "--json" in help_text
