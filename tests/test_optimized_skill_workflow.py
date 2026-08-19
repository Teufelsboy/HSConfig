from __future__ import annotations

import ast
from datetime import date
import json
from pathlib import Path
import runpy
import sys
from typing import Callable

import pytest

import hsconfig.cli as hsconfig_cli
import hsconfig.package_request as package_request
from hsconfig.external_skill_bundle import load_embedded_skill_bundle


_CANDIDATES = (
    ("candidate-1.json", "proactive_tempo"),
    ("candidate-2.json", "balanced"),
    ("candidate-3.json", "resource_oriented"),
)


def _candidate_receipts() -> list[dict[str, object]]:
    context_digest = "sha256:" + "c" * 64
    return [
        {
            "candidate_id": f"candidate-{index}",
            "candidate_revision": 1,
            "content_sha256": "sha256:" + str(index) * 64,
            "runtime_intent_sha256": "sha256:" + str(index + 3) * 64,
            "starter_context_sha256": context_digest,
            "strategy_role": role,
            "valid": True,
        }
        for index, (_filename, role) in enumerate(_CANDIDATES, start=1)
    ]


def _receipt_for_candidate_call(
    argv: list[str],
    receipts: list[dict[str, object]],
) -> dict[str, object]:
    candidate_path = Path(argv[argv.index("--candidate-json") + 1])
    index = [filename for filename, _role in _CANDIDATES].index(
        candidate_path.name
    )
    return receipts[index]


def _write_real_starter_bundle(root: Path) -> Path:
    from hsconfig.starter_context import build_starter_context
    from tests.helpers.audited_package_request import audited_request
    from tests.test_starter_decision import (
        three_candidates,
        write_selection_bundle,
    )

    conservative = audited_request(root.parent / "starter-request", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    return write_selection_bundle(root, context, three_candidates(context))


def _optimized_projection_for_starter(root: Path) -> dict[str, object]:
    from hsconfig.configure_workflow import (
        _load_validated_optimized_start_selection,
        _optimized_start_selection_summary,
    )

    selection = _load_validated_optimized_start_selection(root)
    return _optimized_start_selection_summary(selection)


def _materialize_helper(tmp_path: Path, relative: str) -> Path:
    target = tmp_path / Path(relative).name
    target.write_bytes(load_embedded_skill_bundle()[relative])
    return target


def _run_helper(
    helper: Path,
    arguments: list[str],
    monkeypatch: pytest.MonkeyPatch,
    main: Callable[[list[str]], int],
) -> object:
    monkeypatch.setattr(hsconfig_cli, "main", main)
    monkeypatch.setattr(sys, "argv", [str(helper), *arguments])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(helper), run_name="__main__")
    return stopped.value.code


def test_embedded_skill_defines_exact_three_candidate_critic_sequence() -> None:
    files = load_embedded_skill_bundle()
    skill = files["SKILL.md"].decode("utf-8")
    workflow = files["references/workflow.md"].decode("utf-8")
    checklist = files["references/contract-compiler-checklist.md"].decode(
        "utf-8"
    )
    policies = "\n".join(
        files[path].decode("utf-8")
        for path in (
            "references/globalvalues-policy.md",
            "references/card-behavior-policy.md",
        )
    )

    assert "Normal generation route: optimized three-candidate workflow" in skill
    ordered_markers = (
        "run `starter-context`",
        "treat `starter_context.json` as immutable",
        "create exactly `candidate-1.json`, `candidate-2.json`, and `candidate-3.json`",
        "seal each draft with `seal_starter_document`",
        "run `hsconfig starter-validate-candidate",
        "Record all three zero-exit receipts",
        "at most two targeted strategist repair rounds",
        "dispatch one independent clean-context critic agent",
        "write only `starter_config_decision.json`",
        "rank all three candidates without a numeric score",
        "run `configure --optimized-start --starter-decision-json`",
        "requires its exact live `optimized_start` projection",
        "only when the user requested live writing",
        "run `runtime-match`",
    )
    positions = [workflow.index(marker) for marker in ordered_markers]
    assert positions == sorted(positions)

    for filename, role in _CANDIDATES:
        assert f"`{filename}` -> `{role}`" in workflow
    assert "STARTER_CANDIDATE_FIELDS" in workflow
    assert "seal_starter_document" in workflow
    assert ".canonical_json" in workflow
    assert "The external starter directory is caller-owned and initially absent." in (
        workflow
    )
    assert "The repository makes no model call" in workflow
    assert "The critic is not started until all three receipts are valid." in (
        workflow
    )
    assert "best practical pre-game start config" in checklist
    assert "not measured gameplay optimality" in checklist
    assert "llm_optimized_start" in policies


def test_embedded_helpers_execute_only_fixed_read_only_or_package_phases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    starter_dir = tmp_path / "caller-owned-starter"
    runtime_root = tmp_path / "runtime"
    output_root = tmp_path / "outputs" / "ShadowPriest"
    base_arguments = [
        "--deck-name",
        "ShadowPriest",
        "--deck-code",
        "AAE=",
        "--runtime-root",
        str(runtime_root),
    ]
    calls: list[list[str]] = []
    receipts = _candidate_receipts()

    def main(argv: list[str]) -> int:
        calls.append(argv)
        if argv[0] == "starter-validate-candidate":
            print(json.dumps(_receipt_for_candidate_call(argv, receipts)))
        elif argv[0] == "configure":
            print(json.dumps(_optimized_projection_for_starter(starter_dir)))
        return 0

    code = _run_helper(
        helper,
        [
            "starter-context",
            "--starter-dir",
            str(starter_dir),
            *base_arguments,
        ],
        monkeypatch,
        main,
    )
    assert code == 0
    assert calls == [
        [
            "starter-context",
            *base_arguments,
            "--out",
            str(starter_dir),
            "--json",
        ]
    ]

    calls.clear()
    _write_real_starter_bundle(starter_dir)
    code = _run_helper(
        helper,
        ["validate-candidates", "--starter-dir", str(starter_dir)],
        monkeypatch,
        main,
    )
    assert code == 0
    assert calls == [
        [
            "starter-validate-candidate",
            "--starter-context-json",
            str(starter_dir / "starter_context.json"),
            "--candidate-json",
            str(starter_dir / filename),
            "--json",
        ]
        for filename, _role in _CANDIDATES
    ]

    calls.clear()
    code = _run_helper(
        helper,
        [
            "configure",
            "--starter-dir",
            str(starter_dir),
            *base_arguments,
            "--out",
            str(output_root),
        ],
        monkeypatch,
        main,
    )
    assert code == 0
    assert calls == [
        [
            "configure",
            *base_arguments,
            "--out",
            str(output_root),
            "--optimized-start",
            "--starter-decision-json",
            str(starter_dir / "starter_config_decision.json"),
            "--json",
        ]
    ]
    assert "--apply" not in calls[0]


def test_embedded_candidate_gate_emits_one_fixed_order_joint_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    starter_dir = tmp_path / "starter"
    starter_dir.mkdir()
    receipts = _candidate_receipts()

    def main(argv: list[str]) -> int:
        print(json.dumps(_receipt_for_candidate_call(argv, receipts)))
        return 0

    assert _run_helper(
        helper,
        ["validate-candidates", "--starter-dir", str(starter_dir)],
        monkeypatch,
        main,
    ) == 0
    assert json.loads(capsys.readouterr().out) == receipts


def test_embedded_candidate_gate_rejects_non_distinct_or_mismapped_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    starter_dir = tmp_path / "starter"
    starter_dir.mkdir()
    accepted: list[str] = []

    for defect in (
        "duplicate_candidate_id",
        "duplicate_content_digest",
        "duplicate_runtime_intent_digest",
        "different_context_digest",
        "swapped_roles",
    ):
        receipts = _candidate_receipts()
        if defect == "duplicate_candidate_id":
            receipts[1]["candidate_id"] = receipts[0]["candidate_id"]
        elif defect == "duplicate_content_digest":
            receipts[1]["content_sha256"] = receipts[0]["content_sha256"]
        elif defect == "duplicate_runtime_intent_digest":
            receipts[1]["runtime_intent_sha256"] = receipts[0][
                "runtime_intent_sha256"
            ]
        elif defect == "different_context_digest":
            receipts[1]["starter_context_sha256"] = "sha256:" + "f" * 64
        else:
            receipts[0]["strategy_role"], receipts[1]["strategy_role"] = (
                receipts[1]["strategy_role"],
                receipts[0]["strategy_role"],
            )

        def main(argv: list[str]) -> int:
            print(json.dumps(_receipt_for_candidate_call(argv, receipts)))
            return 0

        try:
            code = _run_helper(
                helper,
                ["validate-candidates", "--starter-dir", str(starter_dir)],
                monkeypatch,
                main,
            )
        except ValueError:
            continue
        if code == 0:
            accepted.append(defect)

    assert accepted == []


def test_embedded_candidate_gate_rejects_duplicated_real_candidate_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    starter_dir = tmp_path / "starter"
    _write_real_starter_bundle(starter_dir)
    (starter_dir / "candidate-2.json").write_bytes(
        (starter_dir / "candidate-1.json").read_bytes()
    )
    real_main = hsconfig_cli.main

    with pytest.raises(
        ValueError,
        match="^starter_candidate_receipt_set_invalid$",
    ):
        _run_helper(
            helper,
            ["validate-candidates", "--starter-dir", str(starter_dir)],
            monkeypatch,
            real_main,
        )


def test_embedded_build_helper_rejects_apply_and_document_selected_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    starter_dir = tmp_path / "starter"
    calls: list[list[str]] = []

    def main(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    assert _run_helper(
        helper,
        [
            "configure",
            "--starter-dir",
            str(starter_dir),
            "--apply",
        ],
        monkeypatch,
        main,
    ) == 2
    assert _run_helper(
        helper,
        [
            "configure",
            "--starter-dir",
            str(starter_dir),
            "--app",
        ],
        monkeypatch,
        main,
    ) == 2
    assert _run_helper(
        helper,
        [
            "configure",
            "--starter-dir",
            str(starter_dir),
            "--starter-decision-json",
            str(tmp_path / "attacker.json"),
        ],
        monkeypatch,
        main,
    ) == 2
    assert calls == []


@pytest.mark.parametrize(
    "arguments",
    (
        ["configure", "--starter-dir", "first", "--starter-dir", "second"],
        ["configure", "--starter-dir", "first", "--starter-d", "second"],
        ["configure", "--starter-dir", "first", "--st", "second"],
        ["configure", "--starter-dir", "first", "--runt", "runtime"],
        ["configure", "--starter-dir", "first", "--runtime-r", "runtime"],
        ["configure", "--starter-dir", "first", "--source-doc", "source.json"],
        ["configure", "--starter-dir", "first", "--out", "a", "--out", "b"],
        [
            "configure",
            "--starter-dir",
            "first",
            "--runtime-root",
            "a",
            "--runtime-root",
            "b",
        ],
    ),
)
def test_embedded_build_helper_rejects_ambiguous_or_duplicate_path_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
) -> None:
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    calls: list[list[str]] = []

    def main(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    assert _run_helper(helper, arguments, monkeypatch, main) == 2
    assert calls == []


def _render_real_optimized_package(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    confidence: str = "high",
) -> tuple[Path, dict[str, object], Path]:
    from hsconfig.configure_models import ConfigureRequest
    from hsconfig.configure_workflow import execute_configure
    from hsconfig.starter_context import build_starter_context
    from tests.helpers.audited_package_request import audited_request
    from tests.helpers.package_byte_contract import (
        _offline_build_inputs,
        _offline_network_and_card_data,
    )
    from tests.test_starter_decision import (
        three_candidates,
        write_selection_bundle,
    )

    conservative = audited_request(root / "request", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)

    def set_confidence(draft: dict[str, object]) -> None:
        critic = draft["critic_identity"]
        assert isinstance(critic, dict)
        critic["confidence"] = confidence

    decision_path = write_selection_bundle(
        root / "selection",
        context,
        three_candidates(context),
        mutate_decision=set_confidence,
    )
    preconfig = conservative.snapshot.general_preconfig.to_value()
    baseline_receipt = preconfig["globalvalues_baseline_receipt"]
    closure = conservative.acquisition_closure_input.to_value()
    monkeypatch.setattr(
        package_request,
        "build_preconfig_context",
        lambda *_args, **_kwargs: preconfig,
    )
    monkeypatch.setattr(
        package_request,
        "load_globalvalues_baseline",
        lambda _runtime_root: baseline_receipt,
    )
    monkeypatch.setattr(
        package_request,
        "_matching_strict_context",
        lambda **_kwargs: conservative.snapshot.strict_build_context,
    )
    monkeypatch.setattr(
        package_request,
        "build_source_acquisition_closure_report",
        lambda **_kwargs: {"acquisition_closure": closure},
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )
    _deck_cards, offline_cards, card_database = _offline_build_inputs()
    request = ConfigureRequest(
        deck_name="ShadowPriest",
        deck_code=conservative.invocation.deck_code,
        output_root=root / "configure-output",
        runtime_root=root / "runtime",
        apply_requested=False,
        current_date=date(2026, 7, 29),
        source_urls=(),
        online_source=False,
        auto_source=False,
        source_evidence_json=None,
        source_search_results_json=None,
        cards_json=None,
        collectible_cards_json=None,
        full_cards_json=None,
        source_fixture_url_map_json=None,
        source_fetch_timeout_seconds=6.0,
        allow_placeholder=False,
        json_output=True,
        optimized_start=True,
        starter_decision_json=decision_path,
    )
    with _offline_network_and_card_data(offline_cards, card_database):
        result = execute_configure(request)
    assert result.status == "OK", result.summary
    assert result.exit_code == 0
    assert result.published_output is not None
    assert not request.runtime_root.exists()
    summary = result.materialized_summary()
    assert "optimized_start" in summary
    return result.published_output.package_root, summary, decision_path.parent


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def test_embedded_validate_helper_requires_optimized_summary_and_assurance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _materialize_helper(tmp_path, "scripts/validate_package.py")
    package, summary, starter_dir = _render_real_optimized_package(
        tmp_path / "real-high",
        monkeypatch,
    )
    optimized = summary["optimized_start"]
    assert isinstance(optimized, dict)
    decision = json.loads(
        (starter_dir / "starter_config_decision.json").read_text(
            encoding="utf-8"
        )
    )
    selected = json.loads(
        (starter_dir / f"{decision['selected_candidate_id']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert optimized["selected_candidate_sha256"] == selected["content_sha256"]
    assert optimized["decision_sha256"] == decision["content_sha256"]
    calls: list[list[str]] = []
    real_main = hsconfig_cli.main

    def main(argv: list[str]) -> int:
        calls.append(argv)
        return real_main(argv)

    assert _run_helper(
        helper,
        ["--package", str(package)],
        monkeypatch,
        main,
    ) == 0
    assert calls == [["validate", "--package", str(package), "--json"]]


def test_embedded_validate_helper_rejects_real_package_authority_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _materialize_helper(tmp_path, "scripts/validate_package.py")
    package, _summary, _starter_dir = _render_real_optimized_package(
        tmp_path / "real-high",
        monkeypatch,
    )
    revision = package.parent
    summary_path = revision / "configure_summary.json"
    operator_path = package / "reports" / "operator_summary.json"
    receipt_path = package / "package_derivation_receipt.json"
    candidate_path = (
        package / "reports" / "optimized_start" / "candidate-2.json"
    )
    originals = {
        summary_path: summary_path.read_bytes(),
        operator_path: operator_path.read_bytes(),
        receipt_path: receipt_path.read_bytes(),
        candidate_path: candidate_path.read_bytes(),
    }
    accepted: list[str] = []

    def main(_argv: list[str]) -> int:
        return 0

    for defect in (
        "missing_receipt",
        "downgraded_receipt",
        "forged_assurance",
        "missing_candidate_report",
        "forged_operator_core",
    ):
        for path, content in originals.items():
            path.write_bytes(content)
        if defect == "missing_receipt":
            receipt_path.unlink()
        elif defect == "downgraded_receipt":
            receipt = json.loads(originals[receipt_path])
            receipt["schema_version"] = 2
            _write_json(receipt_path, receipt)
        else:
            operator = json.loads(originals[operator_path])
            if defect == "forged_assurance":
                operator["configuration_assurance"]["in_client_behavior"] = (
                    "proven_in_client"
                )
                operator["configuration_assurance"]["runtime_gate_impact"] = (
                    "apply_authority"
                )
                operator["configuration_assurance"]["forged_extra"] = True
                _write_json(operator_path, operator)
            elif defect == "missing_candidate_report":
                candidate_path.unlink()
            else:
                operator["optimized_start_derivation_validity"] = False
                _write_json(operator_path, operator)
        try:
            code = _run_helper(
                helper,
                ["--package", str(package)],
                monkeypatch,
                main,
            )
        except ValueError:
            continue
        if code == 0:
            accepted.append(defect)

    assert accepted == []


def test_embedded_configure_helper_validates_live_summary_and_confidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    _package, real_summary, starter_dir = _render_real_optimized_package(
        tmp_path / "real-low",
        monkeypatch,
        confidence="low",
    )
    optimized = real_summary["optimized_start"]
    assert isinstance(optimized, dict)
    assert optimized["status"] == "low_confidence"
    live_summary = real_summary

    def main(_argv: list[str]) -> int:
        print(json.dumps(live_summary))
        return 0

    assert _run_helper(
        helper,
        ["configure", "--starter-dir", str(starter_dir)],
        monkeypatch,
        main,
    ) == 0

    live_summary = json.loads(json.dumps(real_summary))
    live_summary["optimized_start"]["status"] = "selected"
    with pytest.raises(ValueError, match="^optimized_start_summary_invalid$"):
        _run_helper(
            helper,
            ["configure", "--starter-dir", str(starter_dir)],
            monkeypatch,
            main,
        )

    live_summary = json.loads(json.dumps(real_summary))
    del live_summary["optimized_start"]["selection_rationale"]
    with pytest.raises(ValueError, match="^optimized_start_summary_invalid$"):
        _run_helper(
            helper,
            ["configure", "--starter-dir", str(starter_dir)],
            monkeypatch,
            main,
        )


def test_embedded_bundle_contains_no_model_client_import_or_call() -> None:
    files = load_embedded_skill_bundle()
    forbidden_modules = {
        "anthropic",
        "google.generativeai",
        "openai",
    }
    forbidden_calls = {
        "Anthropic",
        "OpenAI",
        "chat.completions.create",
        "responses.create",
    }

    for path in ("scripts/build_config.py", "scripts/validate_package.py"):
        source = files[path].decode("utf-8")
        tree = ast.parse(source, filename=path)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        calls = {
            ast.unparse(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        assert imports.isdisjoint(forbidden_modules)
        assert calls.isdisjoint(forbidden_calls)
