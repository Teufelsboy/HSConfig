import pytest

from hsconfig.cli import _build_parser
from hsconfig.cli_parser import build_parser


NORMAL_PATH = (
    "source-manifest -> draft-source-documents -> research-deck -> "
    "prepare -> validate -> apply"
)


def test_cli_parser_module_builds_same_root_help():
    help_text = build_parser().format_help()

    assert "HSConfig builds lean HearthRanger VisionAI CustomConfig packages" in help_text
    assert "docs/operator/README.md" in help_text
    assert NORMAL_PATH in help_text


def test_root_help_names_preferred_lower_level_and_expert_paths():
    help_text = _build_parser().format_help()

    assert "Preferred normal path: configure" in help_text
    assert "Lower-level normal path:" in help_text
    assert NORMAL_PATH in help_text
    assert "Expert and legacy path:" in help_text
    assert "build, --claims-json, --cards-json, --plan-reports-dir" in help_text


def test_root_help_names_configure_as_preferred_normal_path():
    help_text = _build_parser().format_help()

    assert "Preferred normal path: configure" in help_text
    assert "Lower-level normal path:" in help_text
    assert (
        "source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply"
        in help_text
    )


def test_root_help_points_to_operator_docs():
    help_text = _build_parser().format_help()

    assert "docs/operator/README.md" in help_text
    assert "Preferred normal path: configure" in help_text
    assert "Lower-level normal path:" in help_text
    assert "Expert and legacy path:" in help_text


def _subcommand_help(command: str, capsys) -> str:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([command, "--help"])
    return capsys.readouterr().out


def test_prepare_help_is_marked_normal_path(capsys):
    help_text = _subcommand_help("prepare", capsys)

    assert "Normal package creation path" in help_text


def test_configure_help_is_marked_preferred_normal_path(capsys):
    help_text = _subcommand_help("configure", capsys)

    assert "Preferred one-command pre-run package path" in help_text
    assert "--deck-name" in help_text
    assert "--deck-code" in help_text
    assert "--runtime-root" in help_text
    assert "--out" in help_text
    assert "--source-evidence-json" in help_text
    assert "--apply" in help_text


def test_prepare_help_groups_normal_inputs_before_expert_fixture_inputs(capsys):
    help_text = _subcommand_help("prepare", capsys)

    assert "normal required inputs" in help_text.lower()
    assert "expert/fixture inputs" in help_text.lower()
    assert help_text.lower().index("normal required inputs") < help_text.lower().index(
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
    assert "legacy diagnostic compatibility" in help_text
    assert "Normal load-safe packages do not require this flag" in help_text
