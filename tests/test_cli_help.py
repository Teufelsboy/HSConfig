import pytest

from hsconfig.cli import _build_parser
from hsconfig.cli_parser import build_parser


def test_cli_parser_module_builds_same_root_help():
    help_text = build_parser().format_help()

    assert "HSConfig builds lean HearthRanger VisionAI CustomConfig packages" in help_text
    assert "docs/operator/README.md" in help_text
    assert "source-manifest -> draft-source-documents -> research-deck -> prepare -> apply" in help_text


def test_root_help_names_normal_and_expert_paths():
    help_text = _build_parser().format_help()

    assert "Normal path:" in help_text
    assert "source-manifest -> draft-source-documents -> research-deck -> prepare -> apply" in help_text
    assert "Expert and legacy path:" in help_text
    assert "build, --claims-json, --cards-json, --plan-reports-dir" in help_text


def test_root_help_points_to_operator_docs():
    help_text = _build_parser().format_help()

    assert "docs/operator/README.md" in help_text
    assert "Normal path:" in help_text
    assert "Expert and legacy path:" in help_text


def _subcommand_help(command: str, capsys) -> str:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([command, "--help"])
    return capsys.readouterr().out


def test_prepare_help_is_marked_normal_path(capsys):
    help_text = _subcommand_help("prepare", capsys)

    assert "Normal package creation path" in help_text


def test_build_help_is_marked_expert_path(capsys):
    help_text = _subcommand_help("build", capsys)

    assert "Expert lower-level package builder" in help_text
