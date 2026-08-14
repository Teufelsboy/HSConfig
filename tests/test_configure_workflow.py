from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import pickle

import pytest

import hsconfig.commands.configure as configure_command
from hsconfig.cli_parser import build_parser
from hsconfig.configure_models import ConfigureRequest, ConfigureResult
from hsconfig.configure_run_model import ConfigureRunModel
from hsconfig.configure_run_stage_contract import configure_summary_bytes
from hsconfig.configure_stages import ConfigureFaultPoint
from hsconfig.configure_workflow import execute_configure
from hsconfig.current_output import resolve_current_package
from hsconfig.package_assembler import PackageModel
from hsconfig.package_domain import FrozenDefinitionMapping
from tests.helpers.verified_deck_input import deck_code_for_cards


_CARDS = [
    {
        "card_id": "SW_448",
        "dbf_id": 64443,
        "count": 1,
        "name": "Darkbishop Benedictus",
        "text": (
            "Start of Game: If the spells in your deck are all Shadow, "
            "enter Shadowform."
        ),
    }
]
_DECK_CODE = deck_code_for_cards(_CARDS)


def test_configure_request_and_result_have_no_writable_object_state(
    tmp_path: Path,
) -> None:
    source_urls = ["https://example.invalid/guide"]
    summary = {"status": "failed", "nested": {"rows": ["one"]}}
    request = _request(tmp_path, source_urls=source_urls)
    result = ConfigureResult("failed", 1, None, None, summary)

    source_urls.clear()
    summary["nested"]["rows"].append("two")

    assert isinstance(request, tuple)
    assert isinstance(result, tuple)
    assert request.source_urls == ("https://example.invalid/guide",)
    assert result.summary == {
        "status": "failed",
        "nested": {"rows": ("one",)},
    }
    assert isinstance(result.summary, FrozenDefinitionMapping)
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(request, "deck_name", "mutated")
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(result, "status", "mutated")


def test_configure_result_requires_an_exact_summary_status_key() -> None:
    with pytest.raises(
        ValueError,
        match="configure_result_summary_status_required",
    ):
        ConfigureResult(
            "failed",
            1,
            None,
            None,
            {"stage": "fixture"},
        )


def test_cli_maps_every_configure_option_and_leaves_namespace_byte_identical(
    tmp_path: Path,
    monkeypatch,
) -> None:
    args = build_parser().parse_args(
        [
            "configure",
            "--deck-name",
            "Fixture Deck",
            "--deck-code",
            _DECK_CODE,
            "--out",
            str(tmp_path / "out"),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--source-evidence-json",
            str(tmp_path / "source-evidence.json"),
            "--auto-source",
            "--online-source",
            "--source-search-results-json",
            str(tmp_path / "search-results.json"),
            "--source-url",
            "https://example.invalid/one",
            "--source-url",
            "https://example.invalid/two",
            "--source-fixture-url-map-json",
            str(tmp_path / "fixture-map.json"),
            "--source-fetch-timeout-seconds",
            "9.5",
            "--current-date",
            "2026-07-30",
            "--cards-json",
            str(tmp_path / "cards.json"),
            "--collectible-cards-json",
            str(tmp_path / "collectible.json"),
            "--full-cards-json",
            str(tmp_path / "full.json"),
            "--allow-placeholder",
            "--apply",
            "--json",
        ]
    )
    before = pickle.dumps(vars(args), protocol=5)
    captured: list[ConfigureRequest] = []

    def fake_execute(
        request: ConfigureRequest,
        **_kwargs,
    ) -> ConfigureResult:
        captured.append(request)
        return ConfigureResult(
            "failed",
            1,
            None,
            None,
            {"status": "failed", "stage": "fixture"},
        )

    monkeypatch.setattr(configure_command, "execute_configure", fake_execute)

    assert configure_command.configure_payload(args) == (
        {"status": "failed", "stage": "fixture"},
        1,
    )
    assert pickle.dumps(vars(args), protocol=5) == before
    assert len(captured) == 1
    request = captured[0]
    assert request == ConfigureRequest(
        deck_name="Fixture Deck",
        deck_code=_DECK_CODE,
        output_root=tmp_path / "out",
        runtime_root=tmp_path / "runtime",
        apply_requested=True,
        current_date=date(2026, 7, 30),
        source_urls=(
            "https://example.invalid/one",
            "https://example.invalid/two",
        ),
        online_source=True,
        auto_source=True,
        source_evidence_json=tmp_path / "source-evidence.json",
        source_search_results_json=tmp_path / "search-results.json",
        cards_json=tmp_path / "cards.json",
        collectible_cards_json=tmp_path / "collectible.json",
        full_cards_json=tmp_path / "full.json",
        source_fixture_url_map_json=tmp_path / "fixture-map.json",
        source_fetch_timeout_seconds=9.5,
        allow_placeholder=True,
        json_output=True,
    )


def test_execute_configure_returns_stable_in_memory_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(json.dumps({"cards": _CARDS}), encoding="utf-8")
    _stub_card_fetches(monkeypatch)
    request = _request(tmp_path, cards_json=cards_json)

    result = execute_configure(request)

    published_package = resolve_current_package(request.output_root)
    persisted = json.loads(
        (published_package.parent / "configure_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert result.status == "OK"
    assert result.exit_code == 0
    assert isinstance(result.package_model, PackageModel)
    assert isinstance(result.configure_run_model, ConfigureRunModel)
    assert result.configure_run_model.package is result.package_model
    assert (
        result.package_model.compiled.deck_name
        == result.configure_run_model.deck_name
        == request.deck_name
    )
    assert (
        result.package_model.compiled.deck_fingerprint
        == result.configure_run_model.deck_fingerprint
    )
    stage_artifacts = {
        artifact.relative_path: artifact.content
        for artifact in result.configure_run_model.stage_artifacts
    }
    assert stage_artifacts["configure_summary.json"] == (
        configure_summary_bytes(
            deck_name=result.configure_run_model.deck_name,
            deck_fingerprint=(
                result.configure_run_model.deck_fingerprint
            ),
            paths=tuple(
                sorted(
                    path
                    for path in stage_artifacts
                    if path != "configure_summary.json"
                )
            ),
        )
    )
    assert stage_artifacts["configure_summary.json"] == (
        published_package.parent / "configure_summary.json"
    ).read_bytes()
    assert stage_artifacts["02_source_documents/stage_status.json"] == (
        b'{"reason":"not_requested","status":"unavailable"}\n'
    )
    assert (request.output_root / "current.json").is_file()
    assert published_package == result.published_output.package_root
    with pytest.raises(ValueError, match="configure_result_models_required"):
        ConfigureResult("OK", 0, None, None, {"status": "OK"})
    with pytest.raises(ValueError, match="configure_result_status_invalid"):
        ConfigureResult("passed", 0, None, None, {"status": "passed"})
    with pytest.raises(ValueError, match="configure_result_models_forbidden"):
        ConfigureResult(
            "failed",
            1,
            result.package_model,
            result.configure_run_model,
            {"status": "failed"},
        )
    with pytest.raises(ValueError, match="configure_result_status_exit_mismatch"):
        ConfigureResult("failed", 0, None, None, {"status": "failed"})
    assert persisted["deck_name"] == request.deck_name
    assert result.summary["package_path"] == str(published_package)
    assert result.summary["published_package"] == (
        published_package.relative_to(request.output_root).as_posix()
    )
    assert result == ConfigureResult(
        "OK",
        0,
        result.package_model,
        result.configure_run_model,
        dict(result.summary),
        result.published_output,
    )


def test_configure_stage_order_is_exact_and_deterministic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(json.dumps({"cards": _CARDS}), encoding="utf-8")
    _stub_card_fetches(monkeypatch)
    observed: list[ConfigureFaultPoint] = []

    result = execute_configure(
        _request(tmp_path, cards_json=cards_json),
        configure_fault_hook=observed.append,
    )

    assert result.exit_code == 0
    assert observed == [
        ConfigureFaultPoint.SOURCE_MANIFEST,
        ConfigureFaultPoint.RESEARCH_DECK,
        ConfigureFaultPoint.PREPARE,
        ConfigureFaultPoint.VALIDATE,
        ConfigureFaultPoint.CONFIGURE_SUMMARY,
    ]


@pytest.mark.parametrize(
    "fault_point",
    [
        ConfigureFaultPoint.SOURCE_MANIFEST,
        ConfigureFaultPoint.RESEARCH_DECK,
        ConfigureFaultPoint.PREPARE,
        ConfigureFaultPoint.VALIDATE,
        ConfigureFaultPoint.CONFIGURE_SUMMARY,
    ],
)
def test_each_offline_stage_failure_is_fail_closed_without_runtime_publication(
    tmp_path: Path,
    monkeypatch,
    fault_point: ConfigureFaultPoint,
) -> None:
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(json.dumps({"cards": _CARDS}), encoding="utf-8")
    _stub_card_fetches(monkeypatch)

    def fail_at(point: ConfigureFaultPoint) -> None:
        if point is fault_point:
            raise RuntimeError(f"injected:{point.value}")

    request = _request(tmp_path, cards_json=cards_json)
    result = execute_configure(request, configure_fault_hook=fail_at)

    assert result.exit_code == 1
    assert result.status == "failed"
    assert result.summary["stage"] == fault_point.value
    assert result.summary["errors"] == [f"injected:{fault_point.value}"]
    assert result.package_model is None
    assert result.configure_run_model is None
    assert not (request.output_root / "current.json").exists()
    assert not (request.output_root / "revisions").exists()
    assert not request.runtime_root.exists()
    if fault_point in {
        ConfigureFaultPoint.SOURCE_MANIFEST,
        ConfigureFaultPoint.RESEARCH_DECK,
        ConfigureFaultPoint.PREPARE,
    }:
        assert not (request.output_root / "04_package" / "CustomConfig").exists()


@pytest.mark.parametrize(
    ("fault_point", "request_overrides"),
    [
        (
            ConfigureFaultPoint.SOURCE_ACQUIRE,
            {
                "online_source": True,
                "source_urls": ("https://example.invalid/guide",),
            },
        ),
        (
            ConfigureFaultPoint.SOURCE_AUTOPILOT,
            {
                "auto_source": True,
                "source_search_results_json": Path("search-results.json"),
            },
        ),
        (
            ConfigureFaultPoint.DRAFT_SOURCE_DOCUMENTS,
            {"source_evidence_json": Path("source-evidence.json")},
        ),
        (
            ConfigureFaultPoint.APPLY,
            {"apply_requested": True},
        ),
    ],
)
def test_each_conditional_stage_failure_is_fail_closed_without_runtime_publication(
    tmp_path: Path,
    monkeypatch,
    fault_point: ConfigureFaultPoint,
    request_overrides: dict[str, object],
) -> None:
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(json.dumps({"cards": _CARDS}), encoding="utf-8")
    _stub_card_fetches(monkeypatch)
    request = _request(
        tmp_path,
        cards_json=cards_json,
        **request_overrides,
    )

    def fail_at(point: ConfigureFaultPoint) -> None:
        if point is fault_point:
            raise RuntimeError(f"injected:{point.value}")

    result = execute_configure(request, configure_fault_hook=fail_at)

    assert result.exit_code == 1
    assert result.status == "failed"
    assert result.summary["stage"] == fault_point.value
    assert result.summary["errors"] == [f"injected:{fault_point.value}"]
    assert result.package_model is None
    assert result.configure_run_model is None
    if fault_point is ConfigureFaultPoint.APPLY:
        assert resolve_current_package(request.output_root).is_dir()
    else:
        assert not (request.output_root / "current.json").exists()
        assert not (request.output_root / "revisions").exists()
    assert not request.runtime_root.exists()


def test_configure_command_budget_contracts() -> None:
    import ast

    command_source = Path("src/hsconfig/commands/configure.py").read_text(
        encoding="utf-8"
    )

    assert len(command_source.splitlines()) <= 200
    assert _function_source_lines(
        Path("src/hsconfig/configure_workflow.py"),
        "execute_configure",
    ) <= 160
    assert _function_source_lines(
        Path("src/hsconfig/operator_summary.py"),
        "build_operator_summary",
    ) <= 120
    assert (
        len(
            Path("src/hsconfig/config_quality_contract.py")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        <= 300
    )
    assert _function_source_lines(
        Path("src/hsconfig/config_quality_contract.py"),
        "build_config_quality_report",
    ) <= 40
    ast.parse(command_source)


def _function_source_lines(path: Path, function_name: str) -> int:
    import ast

    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    node = next(
        item
        for item in module.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == function_name
    )
    assert node.end_lineno is not None
    return node.end_lineno - node.lineno + 1


def _request(
    tmp_path: Path,
    *,
    source_urls: list[str] | tuple[str, ...] = (),
    cards_json: Path | None = None,
    apply_requested: bool = False,
    online_source: bool = False,
    auto_source: bool = False,
    source_evidence_json: Path | None = None,
    source_search_results_json: Path | None = None,
) -> ConfigureRequest:
    return ConfigureRequest(
        deck_name="Fixture Deck",
        deck_code=_DECK_CODE,
        output_root=tmp_path / "configure",
        runtime_root=tmp_path / "runtime",
        apply_requested=apply_requested,
        current_date=date(2026, 7, 30),
        source_urls=source_urls,
        online_source=online_source,
        auto_source=auto_source,
        source_evidence_json=source_evidence_json,
        source_search_results_json=source_search_results_json,
        cards_json=cards_json,
        collectible_cards_json=None,
        full_cards_json=None,
        source_fixture_url_map_json=None,
        source_fetch_timeout_seconds=6.0,
        allow_placeholder=False,
        json_output=True,
    )


def _stub_card_fetches(monkeypatch) -> None:
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )
