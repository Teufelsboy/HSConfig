import pytest

from hsconfig.cli import _build_parser
from hsconfig.cli_parser import build_parser


INSPECTED_PATH = (
    "source-manifest -> source-autopilot or draft-source-documents -> "
    "research-deck -> prepare -> validate -> apply"
)
OLD_LOWER_LEVEL_LABEL = "Lower-level " + "normal path:"
NORMAL_SKILL_ROUTE = "Normal installed-skill path: optimized single-candidate workflow."
CONSERVATIVE_CLI_ROUTE = "Conservative CLI Compatibility: raw configure."


def test_cli_help_presents_codex_first_live_route_and_preserves_expert_commands():
    parser = build_parser()
    text = parser.format_help()
    assert "Codex-first" in text
    assert "single-candidate" in text
    assert "Deck -> Config -> Validate -> Live -> Match" in text
    assert "three-candidate" not in text
    assert "valid enabled profile" in text
    assert "explicit preview" in text
    assert "Conservative CLI Compatibility" in text
    for command in ("configure", "apply", "runtime-match", "source-manifest", "research-deck", "build"):
        assert command in text
    args = parser.parse_args([
        "configure", "--deck-name", "Deck", "--deck-code", "AAE=",
        "--runtime-root", "runtime", "--out", "output", "--apply",
        "--optimized-start", "--starter-decision-json", "decision.json",
    ])
    assert args.apply and args.optimized_start
    assert args.starter_decision_json == "decision.json"


def test_cli_parser_module_builds_same_root_help():
    help_text = build_parser().format_help()

    assert "Codex-first HSConfig turns a deck name and deck code" in help_text
    assert "docs/operator/README.md" in help_text
    assert NORMAL_SKILL_ROUTE in help_text
    assert CONSERVATIVE_CLI_ROUTE in help_text
    assert "Preferred normal path: configure" not in help_text
    assert "Lower-level inspected path:" in help_text
    assert INSPECTED_PATH in help_text
    assert OLD_LOWER_LEVEL_LABEL not in help_text


def test_root_help_names_preferred_lower_level_and_expert_paths():
    help_text = _build_parser().format_help()

    assert NORMAL_SKILL_ROUTE in help_text
    assert CONSERVATIVE_CLI_ROUTE in help_text
    assert "Preferred normal path: configure" not in help_text
    assert "Lower-level inspected path:" in help_text
    assert INSPECTED_PATH in help_text
    assert OLD_LOWER_LEVEL_LABEL not in help_text
    assert "Expert and legacy path:" in help_text
    assert "build, --claims-json, --cards-json, --plan-reports-dir" in help_text


def test_root_help_marks_raw_configure_as_conservative_cli_compatibility():
    help_text = _build_parser().format_help()

    assert NORMAL_SKILL_ROUTE in help_text
    assert CONSERVATIVE_CLI_ROUTE in help_text
    assert "Preferred normal path: configure" not in help_text
    assert "Lower-level inspected path:" in help_text
    assert INSPECTED_PATH in help_text
    assert OLD_LOWER_LEVEL_LABEL not in help_text


def test_root_help_points_to_operator_docs():
    help_text = _build_parser().format_help()

    assert "docs/operator/README.md" in help_text
    assert NORMAL_SKILL_ROUTE in help_text
    assert CONSERVATIVE_CLI_ROUTE in help_text
    assert "Preferred normal path: configure" not in help_text
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


def test_configure_help_is_marked_conservative_cli_compatibility(capsys):
    help_text = _subcommand_help("configure", capsys)
    normalized_help = " ".join(help_text.split())

    assert "Conservative CLI Compatibility path" in normalized_help
    assert "The installed skill's optimized" in normalized_help
    assert "workflow is the normal generation route." in normalized_help
    assert "Raw configure decodes a deck" in normalized_help
    assert "Preferred one-command pre-run package path" not in help_text
    assert "--deck-name" in help_text
    assert "--deck-code" in help_text
    assert "--runtime-root" in help_text
    assert "--out" in help_text
    assert "--source-evidence-json" in help_text
    assert "--apply" in help_text


def test_starter_context_help_exposes_bounded_read_only_operands(capsys):
    help_text = _subcommand_help("starter-context", capsys)

    assert "bounded read-only starter context" in help_text.lower()
    assert "never writes runtime files" in help_text.lower()
    assert "--deck-name" in help_text
    assert "--deck-code" in help_text
    assert "--runtime-root" in help_text
    assert "--out" in help_text
    assert "--source-documents-json" in help_text
    assert "--cards-json" in help_text
    assert "--json" in help_text


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


def test_live_policy_help_preserves_explicit_profile_mutations(capsys):
    root_help = _subcommand_help("live-policy", capsys)
    assert "enable" in root_help
    assert "disable" in root_help

    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["live-policy", "enable", "--help"])
    enable_help = capsys.readouterr().out
    assert "--runtime-root" in enable_help
    assert "--output-base-root" in enable_help
    assert "--expected-absent" in enable_help
    assert "--expected-predecessor-sha256" in enable_help
    assert "--json" in enable_help

    with pytest.raises(SystemExit):
        parser.parse_args(["live-policy", "disable", "--help"])
    disable_help = capsys.readouterr().out
    assert "--expected-predecessor-sha256" in disable_help
    assert "--json" in disable_help
    assert "--expected-absent" not in disable_help
    assert "--runtime-root" not in disable_help
    assert "--output-base-root" not in disable_help


@pytest.mark.parametrize("options, as_json", [([], False), (["--json"], True)])
def test_live_policy_status_accepts_only_optional_json_without_mutation_requirements(
    options, as_json
):
    args = _build_parser().parse_args(["live-policy", "status", *options])
    assert args.live_policy_action == "status"
    assert args.json is as_json
    assert not hasattr(args, "expected_absent")
    assert not hasattr(args, "expected_predecessor_sha256")
