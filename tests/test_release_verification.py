from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hsconfig.audited_deck_catalog import load_audited_deck_catalog
from hsconfig.audited_build_request import _render_selected_run
from hsconfig.build_input_catalog import (
    AuditedBuildInputSet,
    load_audited_build_inputs,
    load_audited_build_resource_store,
)
from hsconfig.deck_config_ini import read_deck_config
from hsconfig.output_publisher import publish_configure_run
from hsconfig.release_verification import (
    DeckVerification,
    _assert_no_serialized_root,
    _assert_semantic_closure,
    _capture_prior_runtime,
    _new_runtime_state_is_exact,
    _render_canonical_prior,
    _validate_private_work_roots,
    _verify_one_audited_deck,
    verify_audited_decks,
)
from hsconfig.runtime_installer import (
    install_runtime_package,
    plan_runtime_install,
    recover_runtime_state,
)
from hsconfig.runtime_state import RuntimeDeckState


BUILD_INPUTS_PATH = Path("src/hsconfig/resources/audited_build_inputs.json")
BUILD_RESOURCES_PATH = Path("src/hsconfig/resources/audited_build_resources.json")


def _deck_codes() -> dict[str, str]:
    return {
        str(row["deck_name"]): str(row["deck_code"])
        for row in load_audited_deck_catalog()
    }


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_private_cold_build_is_byte_identical_and_root_independent(
    tmp_path: Path,
) -> None:
    """Catches serialized absolute roots or divergent cold-build content."""
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(
        BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    root_a = (tmp_path / "first-absolute-root").resolve()
    root_b = (tmp_path / "second-absolute-root").resolve()
    root_a.mkdir()
    root_b.mkdir()

    row = _verify_one_audited_deck(
        inputs=audited.builds[0],
        resource_store=resources,
        deck_code=_deck_codes()["ShadowPriest"],
        work_root_a=root_a,
        work_root_b=root_b,
    )

    assert row.deck_name == "ShadowPriest"
    assert row.configure_run_bytes_equal is True
    assert row.first_content_root_sha256 == (
        row.second_content_root_sha256
    )

    first = _tree_bytes(root_a / "ShadowPriest" / "configure-run")
    second = _tree_bytes(root_b / "ShadowPriest" / "configure-run")
    assert first == second
    assert first
    forbidden = (str(root_a).encode("utf-8"), str(root_b).encode("utf-8"))
    assert all(
        marker not in content
        for content in first.values()
        for marker in forbidden
    )


def test_public_verifier_rejects_a_partial_audited_deck_set(
    tmp_path: Path,
) -> None:
    """Catches downgrading the public proof to one or fewer catalog rows."""
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    partial = AuditedBuildInputSet(
        schema_version=audited.schema_version,
        builds=(audited.builds[0],),
        content_sha256=audited.content_sha256,
    )
    resources = load_audited_build_resource_store(
        BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    root_a = (tmp_path / "partial-a").resolve()
    root_b = (tmp_path / "partial-b").resolve()

    with pytest.raises(ValueError, match="audited_build_input_set_invalid"):
        verify_audited_decks(
            build_inputs=partial,
            resource_store=resources,
            deck_codes=_deck_codes(),
            work_root_a=root_a,
            work_root_b=root_b,
        )

    assert not root_a.exists()
    assert not root_b.exists()


def test_public_verifier_requires_an_audited_build_input_set(
    tmp_path: Path,
) -> None:
    """Catches accepting an unverified object as the audited build input set."""
    with pytest.raises(TypeError, match="audited_build_inputs_required"):
        verify_audited_decks(
            build_inputs=object(),  # type: ignore[arg-type]
            resource_store=object(),  # type: ignore[arg-type]
            deck_codes={},
            work_root_a=tmp_path / "not-created-a",
            work_root_b=tmp_path / "not-created-b",
        )


def test_public_verifier_requires_a_frozen_build_resource_store(
    tmp_path: Path,
) -> None:
    """Catches accepting mutable or unaudited build resources."""
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)

    with pytest.raises(TypeError, match="frozen_build_resource_store_required"):
        verify_audited_decks(
            build_inputs=audited,
            resource_store=object(),  # type: ignore[arg-type]
            deck_codes=_deck_codes(),
            work_root_a=tmp_path / "not-created-a",
            work_root_b=tmp_path / "not-created-b",
        )


def test_private_verifier_requires_canonical_build_inputs(tmp_path: Path) -> None:
    """Catches the private cold-build primitive accepting arbitrary input rows."""
    with pytest.raises(TypeError, match="audited_build_input_required"):
        _verify_one_audited_deck(
            inputs=object(),  # type: ignore[arg-type]
            resource_store=object(),  # type: ignore[arg-type]
            deck_code="unreachable",
            work_root_a=tmp_path / "not-created-a",
            work_root_b=tmp_path / "not-created-b",
        )


def test_private_verifier_rejects_a_deck_code_with_the_wrong_digest(
    tmp_path: Path,
) -> None:
    """Catches bypassing the canonical input's exact deck-code digest."""
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(
        BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    root_a = (tmp_path / "first-root").resolve()
    root_b = (tmp_path / "second-root").resolve()
    root_a.mkdir()
    root_b.mkdir()

    with pytest.raises(ValueError, match="audited_build_deck_code_mismatch"):
        _verify_one_audited_deck(
            inputs=audited.builds[0],
            resource_store=resources,
            deck_code="not-the-canonical-deck-code",
            work_root_a=root_a,
            work_root_b=root_b,
        )


@pytest.mark.parametrize(
    ("case", "deck_codes", "error"),
    [
        (
            "missing_catalog_row",
            {"ShadowPriest": _deck_codes()["ShadowPriest"]},
            "audited_build_deck_codes_invalid",
        ),
        (
            "empty_deck_code",
            {**_deck_codes(), "ShadowPriest": ""},
            "audited_build_deck_codes_invalid",
        ),
        (
            "deck_code_digest_mismatch",
            {**_deck_codes(), "ShadowPriest": "not-the-canonical-deck-code"},
            "audited_build_deck_code_mismatch",
        ),
    ],
)
def test_public_verifier_rejects_invalid_exact_deck_code_mappings(
    tmp_path: Path,
    case: str,
    deck_codes: dict[str, str],
    error: str,
) -> None:
    """Catches accepting an incomplete, blank, or digest-mismatched deck map."""
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(
        BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    root_a = tmp_path / f"{case}-a"
    root_b = tmp_path / f"{case}-b"

    with pytest.raises(ValueError, match=error):
        verify_audited_decks(
            build_inputs=audited,
            resource_store=resources,
            deck_codes=deck_codes,
            work_root_a=root_a,
            work_root_b=root_b,
        )

    assert not root_a.exists()
    assert not root_b.exists()


def test_public_verifier_rejects_a_relative_fresh_root(tmp_path: Path) -> None:
    """Catches root preparation treating a relative output path as temporary."""
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(
        BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    root_b = tmp_path / "not-created-b"

    with pytest.raises(ValueError, match="verification_root_must_be_absolute"):
        verify_audited_decks(
            build_inputs=audited,
            resource_store=resources,
            deck_codes=_deck_codes(),
            work_root_a=Path("relative-task-four-root"),
            work_root_b=root_b,
        )

    assert not root_b.exists()


def test_public_verifier_rejects_an_existing_temporary_root(tmp_path: Path) -> None:
    """Catches a prior verification tree being reused as a cold-build root."""
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(
        BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    root_a = tmp_path / "already-exists"
    root_b = tmp_path / "not-created-b"
    root_a.mkdir()

    with pytest.raises(ValueError, match="verification_root_must_be_fresh"):
        verify_audited_decks(
            build_inputs=audited,
            resource_store=resources,
            deck_codes=_deck_codes(),
            work_root_a=root_a,
            work_root_b=root_b,
        )

    assert not root_b.exists()


def test_semantic_closure_rejects_an_empty_configure_run_view(
    tmp_path: Path,
) -> None:
    """Catches treating an empty configure-run directory as semantically valid."""
    run_root = tmp_path / "empty-configure-run"
    run_root.mkdir()

    with pytest.raises(ValueError, match="audited_build_semantic_closure_invalid"):
        _assert_semantic_closure(run_root)


def test_capture_prior_runtime_rejects_an_empty_runtime_directory(
    tmp_path: Path,
) -> None:
    """Catches attempting recovery without a persisted prior runtime state."""
    with pytest.raises(RuntimeError, match="prior_runtime_state_missing"):
        _capture_prior_runtime(SimpleNamespace(runtime_root=tmp_path))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "unsafe_root",
    [
        Path("outputs") / "task-4-unsafe-root",
        Path.home() / "Desktop" / "HS" / "task-4-unsafe-root",
    ],
)
def test_public_verifier_rejects_non_temporary_roots(
    tmp_path: Path,
    unsafe_root: Path,
) -> None:
    """Catches a verifier that could create a repository or runtime root."""
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(
        BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    root_a = unsafe_root.resolve()
    root_b = (tmp_path / "safe-temp-root").resolve()

    with pytest.raises(ValueError, match="verification_root_not_temporary"):
        verify_audited_decks(
            build_inputs=audited,
            resource_store=resources,
            deck_codes=_deck_codes(),
            work_root_a=root_a,
            work_root_b=root_b,
        )

    assert not root_a.exists()
    assert not root_b.exists()


def test_root_leakage_rejects_forward_slash_casefolded_root_variant() -> None:
    """Catches a root scan that only recognizes one native path spelling."""
    root_a = Path(r"C:\Temp\TaskFour\FirstRoot")
    root_b = Path(r"C:\Temp\TaskFour\SecondRoot")
    injected = str(root_a).replace("\\", "/").casefold().encode("utf-8")

    with pytest.raises(ValueError, match="audited_build_absolute_root_serialized"):
        _assert_no_serialized_root(
            {"reports/injected.json": b'{"path":"' + injected + b'"}'},
            root_a,
            root_b,
        )


def test_root_leakage_rejects_native_backslash_root_variant() -> None:
    root_a = Path(r"C:\Temp\TaskFour\FirstRoot")
    root_b = Path(r"C:\Temp\TaskFour\SecondRoot")
    with pytest.raises(ValueError, match="audited_build_absolute_root_serialized"):
        _assert_no_serialized_root(
            {"reports/injected.json": b'{"path":"C:\\Temp\\TaskFour\\FirstRoot"}'},
            root_a,
            root_b,
        )


@pytest.mark.parametrize("root", [Path("outputs") / "private-root", Path.home() / "Desktop" / "HS" / "private-root"])
def test_private_verifier_rejects_absent_or_persistent_roots(root: Path, tmp_path: Path) -> None:
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(BUILD_RESOURCES_PATH, audited_inputs=audited)
    with pytest.raises(ValueError, match="verification_private_roots_invalid"):
        _verify_one_audited_deck(inputs=audited.builds[0], resource_store=resources, deck_code=_deck_codes()["ShadowPriest"], work_root_a=root.resolve(), work_root_b=(tmp_path / "other").resolve())


def test_private_verifier_rejects_two_spellings_of_the_same_root(
    tmp_path: Path,
) -> None:
    """Catches alias paths bypassing the private root separation boundary."""
    root = (tmp_path / "same-root").resolve()
    root.mkdir()

    with pytest.raises(ValueError, match="verification_private_roots_invalid"):
        _validate_private_work_roots(root, root / ".." / root.name)


def test_private_verifier_rejects_nonempty_temporary_root(tmp_path: Path) -> None:
    """Catches a stale cold-build artifact leaking into a new verification."""
    left = (tmp_path / "nonempty").resolve()
    right = (tmp_path / "empty").resolve()
    left.mkdir()
    right.mkdir()
    (left / "stale.txt").write_text("not a cold root", encoding="utf-8")

    with pytest.raises(ValueError, match="verification_private_roots_invalid"):
        _validate_private_work_roots(left, right)


def _new_runtime_state_context(tmp_path: Path) -> tuple[object, object, object, object, object]:
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    inputs = audited.builds[0]
    resources = load_audited_build_resource_store(
        BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    deck_code = _deck_codes()[inputs.deck_name]
    rendered = _render_selected_run(
        inputs=inputs,
        resources=resources,
        deck_code=deck_code,
    )
    prior_rendered = _render_canonical_prior(
        rendered=rendered,
        inputs=inputs,
        resource_store=resources,
        deck_code=deck_code,
    )
    publication_root = tmp_path / "publication"
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    prior_plan = plan_runtime_install(
        published_output=publish_configure_run(prior_rendered, publication_root),
        runtime_root=runtime_root,
    )
    install_runtime_package(prior_plan)
    prior = _capture_prior_runtime(prior_plan)
    published = publish_configure_run(rendered, publication_root)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    install_runtime_package(plan)
    state = recover_runtime_state(runtime_root)
    ini = read_deck_config(
        runtime_root / "CustomConfig" / "deck_config.ini",
        deck_name=plan.deck_name,
    )
    return plan, published, prior, state, ini


def test_new_runtime_proof_fails_closed_without_an_ini_digest(
    tmp_path: Path,
) -> None:
    """Catches accepting a recovered runtime state without INI-digest evidence."""
    plan, published, prior, state, _ini = _new_runtime_state_context(tmp_path)
    assert state is not None

    assert _new_runtime_state_is_exact(
        plan=plan,
        published=published,
        prior=prior,
        state=state,
        ini_sha256=None,
        selected_config_dir=plan.versioned_config_dir,
    ) is False


def test_new_runtime_proof_fails_closed_without_runtime_state(
    tmp_path: Path,
) -> None:
    """Catches accepting a valid INI digest without recovered runtime state."""
    plan, published, prior, _state, ini = _new_runtime_state_context(tmp_path)

    assert _new_runtime_state_is_exact(
        plan=plan,
        published=published,
        prior=prior,
        state=None,
        ini_sha256=ini.sha256,
        selected_config_dir=plan.versioned_config_dir,
    ) is False


def test_new_runtime_proof_requires_the_selected_current_config_dir(
    tmp_path: Path,
) -> None:
    """Catches accepting a correct INI digest with the wrong deck selection."""
    plan, published, prior, state, ini = _new_runtime_state_context(tmp_path)

    assert _new_runtime_state_is_exact(
        plan=plan,
        published=published,
        prior=prior,
        state=state,
        ini_sha256=ini.sha256,
        selected_config_dir=plan.versioned_config_dir,
    ) is True
    assert _new_runtime_state_is_exact(
        plan=plan,
        published=published,
        prior=prior,
        state=state,
        ini_sha256=ini.sha256,
        selected_config_dir=prior.config_dir,
    ) is False


def test_new_runtime_proof_rejects_an_extra_unrelated_state_row(
    tmp_path: Path,
) -> None:
    """Catches a one-deck proof that silently tolerates another state row."""
    plan, published, prior, state, ini = _new_runtime_state_context(tmp_path)
    assert state is not None
    extra = RuntimeDeckState(
        state_key="unrelated-deck",
        deck_name="Unrelated Deck",
        config_dir="OtherConfig",
        package_root_sha256="0" * 64,
        ini_sha256="1" * 64,
    )

    assert _new_runtime_state_is_exact(
        plan=plan,
        published=published,
        prior=prior,
        state=replace(state, decks=state.decks + (extra,)),
        ini_sha256=ini.sha256,
        selected_config_dir=plan.versioned_config_dir,
    ) is False


def _script_module() -> object:
    path = Path("scripts/verify_twelve_decks.py").resolve()
    spec = importlib.util.spec_from_file_location("task4_verify_twelve_decks", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_emits_stable_twelve_row_json_and_cleans_its_temp_root(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catches omitted explicit resources, unstable JSON, or leaked CLI temp roots."""
    module = _script_module()
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(
        BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    calls: dict[str, object] = {}
    roots: list[Path] = []
    rows = tuple(
        DeckVerification(
            deck_name=build.deck_name,
            first_content_root_sha256=build.deck_fingerprint,
            second_content_root_sha256=build.deck_fingerprint,
            configure_run_bytes_equal=True,
            runtime_old_or_new_safe=True,
        )
        for build in audited.builds
    )

    def load_inputs(path: Path) -> AuditedBuildInputSet:
        calls["inputs"] = path
        return audited

    def load_resources(
        path: Path,
        *,
        audited_inputs: AuditedBuildInputSet,
    ) -> object:
        calls["resources"] = (path, audited_inputs)
        return resources

    def verify(**kwargs: object) -> tuple[DeckVerification, ...]:
        roots.extend((kwargs["work_root_a"], kwargs["work_root_b"]))  # type: ignore[arg-type]
        assert kwargs["build_inputs"] is audited
        assert kwargs["resource_store"] is resources
        assert kwargs["deck_codes"] == _deck_codes()
        return rows

    monkeypatch.setattr(module, "load_audited_build_inputs", load_inputs)
    monkeypatch.setattr(module, "load_audited_build_resource_store", load_resources)
    monkeypatch.setattr(module, "verify_audited_decks", verify)
    monkeypatch.setattr(module, "load_audited_deck_catalog", lambda path: load_audited_deck_catalog(path))

    assert module.main([
        "--build-inputs", str(BUILD_INPUTS_PATH),
        "--build-resources", str(BUILD_RESOURCES_PATH),
        "--deck-catalog", "docs/operator/audited-deck-catalog.json",
        "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert calls == {
        "inputs": BUILD_INPUTS_PATH,
        "resources": (BUILD_RESOURCES_PATH, audited),
    }
    assert payload == {
        "passed": True,
        "decks": [
            {
                "configure_run_bytes_equal": True,
                "deck_name": build.deck_name,
                "first_content_root_sha256": build.deck_fingerprint,
                "runtime_old_or_new_safe": True,
                "second_content_root_sha256": build.deck_fingerprint,
            }
            for build in audited.builds
        ],
    }
    assert roots and all(not root.parent.exists() for root in roots)


def test_cli_returns_nonzero_when_one_row_is_false(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catches a CLI that reports success despite a failed deck row."""
    module = _script_module()
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(
        BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    rows = tuple(
        replace(
            DeckVerification(
                deck_name=build.deck_name,
                first_content_root_sha256=build.deck_fingerprint,
                second_content_root_sha256=build.deck_fingerprint,
                configure_run_bytes_equal=True,
                runtime_old_or_new_safe=True,
            ),
            runtime_old_or_new_safe=build.deck_name != "ShadowPriest",
        )
        for build in audited.builds
    )
    monkeypatch.setattr(module, "load_audited_build_inputs", lambda _path: audited)
    monkeypatch.setattr(
        module,
        "load_audited_build_resource_store",
        lambda _path, *, audited_inputs: resources,
    )
    monkeypatch.setattr(module, "load_audited_deck_catalog", lambda path: load_audited_deck_catalog(path))
    monkeypatch.setattr(module, "verify_audited_decks", lambda **_kwargs: rows)

    assert module.main([
        "--build-inputs", str(BUILD_INPUTS_PATH),
        "--build-resources", str(BUILD_RESOURCES_PATH),
        "--deck-catalog", "docs/operator/audited-deck-catalog.json",
        "--json",
    ]) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False


@pytest.mark.parametrize("rows", ["partial", "misordered"])
def test_cli_returns_nonzero_for_noncanonical_all_true_rows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], rows: str
) -> None:
    module = _script_module()
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(BUILD_RESOURCES_PATH, audited_inputs=audited)
    result = tuple(DeckVerification(build.deck_name, build.deck_fingerprint, build.deck_fingerprint, True, True) for build in audited.builds)
    if rows == "partial":
        result = result[:-1]
    else:
        result = tuple(reversed(result))
    monkeypatch.setattr(module, "load_audited_build_inputs", lambda _path: audited)
    monkeypatch.setattr(module, "load_audited_build_resource_store", lambda _path, *, audited_inputs: resources)
    monkeypatch.setattr(module, "load_audited_deck_catalog", lambda path: load_audited_deck_catalog(path))
    monkeypatch.setattr(module, "verify_audited_decks", lambda **_kwargs: result)
    assert module.main(["--build-inputs", str(BUILD_INPUTS_PATH), "--build-resources", str(BUILD_RESOURCES_PATH), "--deck-catalog", "docs/operator/audited-deck-catalog.json", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False
