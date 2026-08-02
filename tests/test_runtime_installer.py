from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import hsconfig.runtime_installer as runtime_installer

from hsconfig.configure_run_model import (
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
)
from hsconfig.current_output import snapshot_and_verify_revision
from hsconfig.output_publisher import PublishedOutput, publish_configure_run
from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.runtime_installer import (
    RuntimeInstallPlan,
    install_runtime_package,
    plan_runtime_install,
    recover_runtime_state,
)
from hsconfig.runtime_state import (
    RuntimeDeckState,
    RuntimeState,
    read_runtime_state,
    serialize_runtime_state,
)
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionJournal,
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    runtime_transaction_journal_path,
    write_runtime_transaction_journal,
)
from hsconfig.package_io import path_identity
from tests.helpers.audited_package_request import audited_request


def build_rendered_run(root: Path, revision: int) -> RenderedConfigureRun:
    package = assemble_package(
        compile_package(audited_request(root, "ShadowPriest"))
    )
    return render_configure_run_model(
        create_configure_run_model(
            package=package,
            stage_artifacts={
                "01_manifest/input.json": (
                    f'{{"revision":{revision}}}\n'.encode()
                ),
                "02_source_documents/source.json": b'{"stage":2}\n',
                "03_research/research.json": b'{"stage":3}\n',
            },
        )
    )


def publish_fixture(
    tmp_path: Path,
    *,
    revision: int = 1,
) -> tuple[PublishedOutput, Path, RenderedConfigureRun]:
    rendered = build_rendered_run(tmp_path / f"source-{revision}", revision)
    output_root = tmp_path / "published"
    published = publish_configure_run(rendered, output_root)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    return published, runtime_root, rendered


def expected_runtime_entries(
    published: PublishedOutput,
) -> tuple[str, dict[str, bytes], str]:
    verified = snapshot_and_verify_revision(published.revision_root)
    prefix = "04_package/CustomConfig/"
    rows = [
        entry
        for entry in verified.manifest.entries
        if entry.relative_path.startswith(prefix)
    ]
    logical_names = {
        entry.relative_path[len(prefix) :].split("/", 1)[0]
        for entry in rows
    }
    assert len(logical_names) == 1
    logical_name = logical_names.pop()
    logical_prefix = f"{prefix}{logical_name}/"
    expected = {
        entry.relative_path[len(logical_prefix) :]: (
            published.revision_root / entry.relative_path
        ).read_bytes()
        for entry in rows
    }
    records = b"".join(
        (
            f"{path}\0{len(content)}\0"
            f"{hashlib.sha256(content).hexdigest()}\n"
        ).encode("utf-8")
        for path, content in sorted(expected.items())
    )
    return logical_name, expected, hashlib.sha256(records).hexdigest()


def state_key_for_test(deck_name: str) -> str:
    digest = hashlib.sha256(
        b"hsconfig-runtime-deck-state-v1\0"
        + deck_name.casefold().encode("utf-8")
    ).hexdigest()
    return f"shadowpriest--sha256-{digest}"


def seed_owned_old_revision(
    runtime_root: Path,
    *,
    phase: RuntimeTransactionPhase = RuntimeTransactionPhase.FINALIZED,
    logical_name: str = "shadowpriest-old",
    selected_name: str | None = None,
) -> tuple[Path, RuntimeTransactionJournal]:
    custom_config = runtime_root / "CustomConfig"
    transactions = runtime_root / ".hsconfig" / "transactions"
    (runtime_root / ".hsconfig" / "staging").mkdir(parents=True)
    (runtime_root / ".hsconfig" / "receipts").mkdir()
    transactions.mkdir()
    contents = {
        "A.json": b'{"old":"a"}\n',
        "B.json": b'{"old":"b"}\n',
        "C.json": b'{"old":"c"}\n',
    }
    records = b"".join(
        (
            f"{name}\0{len(content)}\0"
            f"{hashlib.sha256(content).hexdigest()}\n"
        ).encode("utf-8")
        for name, content in sorted(contents.items())
    )
    digest = hashlib.sha256(records).hexdigest()
    old_name = f"{logical_name}--sha256-{digest}"
    old_target = custom_config / old_name
    old_target.mkdir(parents=True)
    for name, content in contents.items():
        (old_target / name).write_bytes(content)
    mapped_name = old_name if selected_name is None else selected_name
    ini = custom_config / "deck_config.ini"
    ini.write_text(
        f"[CONFIGS]\nShadowPriest = {mapped_name}\n",
        encoding="utf-8",
    )
    identity = path_identity(old_target)
    transaction_id = "1" * 32
    journal = RuntimeTransactionJournal(
        schema_version=1,
        transaction_id=transaction_id,
        deck_name="ShadowPriest",
        source_manifest_sha256="a" * 64,
        state_key=state_key_for_test("ShadowPriest"),
        logical_config_dir=logical_name,
        package_root_sha256=digest,
        candidate_path=f".hsconfig/staging/{transaction_id}",
        target_path=f"CustomConfig/{old_name}",
        candidate_identity=identity,
        target_identity=identity,
        owns_target=True,
        previous_config_dir=None,
        next_config_dir=old_name,
        previous_ini_sha256=None,
        next_ini_sha256=hashlib.sha256(ini.read_bytes()).hexdigest(),
        phase=phase,
    )
    write_runtime_transaction_journal(
        runtime_transaction_journal_path(runtime_root, transaction_id),
        journal,
    )
    return old_target, journal


def test_apply_uses_full_runtime_subtree_digest_and_is_idempotent(
    tmp_path: Path,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    logical_name, expected_files, package_digest = expected_runtime_entries(
        published
    )

    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    first = install_runtime_package(plan)
    repeated = install_runtime_package(plan)

    expected_name = f"{logical_name}--sha256-{package_digest}"
    assert plan.versioned_config_dir == expected_name
    assert plan.package_root_sha256 == package_digest
    assert first.status == "applied"
    assert first.config_dir == expected_name
    assert repeated.status == "already_current"
    target = runtime_root / "CustomConfig" / expected_name
    actual_files = {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files
    assert (runtime_root / "CustomConfig" / "deck_config.ini").read_text(
        encoding="utf-8"
    ) == f"[CONFIGS]\nShadowPriest = {expected_name}"
    assert set(target.iterdir()) == {
        target / name for name in expected_files
    }

    state = read_runtime_state(runtime_root)
    assert state is not None
    assert len(state.decks) == 1
    deck = state.decks[0]
    assert deck.deck_name == "ShadowPriest"
    assert deck.config_dir == expected_name
    assert deck.package_root_sha256 == package_digest
    receipt = (
        runtime_root
        / ".hsconfig"
        / "receipts"
        / deck.state_key
        / "last_apply_receipt.json"
    )
    assert first.receipt_path == receipt
    assert repeated.receipt_path == receipt
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert "timestamp" not in payload
    assert payload["state_key"] == deck.state_key
    assert payload["source_manifest_sha256"] == published.content_root_sha256
    assert list((runtime_root / ".hsconfig" / "receipts").rglob("*.json")) == [
        receipt
    ]


def test_state_key_is_stable_and_path_component_boundaries_are_exact(
    tmp_path: Path,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    digest = "a" * 64
    accepted = replace(
        plan,
        logical_config_dir="x" * 182,
        versioned_config_dir=f"{'x' * 182}--sha256-{digest}",
        package_root_sha256=digest,
    )
    assert len(accepted.versioned_config_dir) == 255

    with pytest.raises(ValueError, match="runtime_config_component_too_long"):
        replace(
            plan,
            logical_config_dir="x" * 183,
            versioned_config_dir=f"{'x' * 183}--sha256-{digest}",
            package_root_sha256=digest,
        )

    install_runtime_package(plan)
    first_state = read_runtime_state(runtime_root)
    assert first_state is not None
    first_key = first_state.decks[0].state_key
    receipt_parent = (
        runtime_root / ".hsconfig" / "receipts" / first_key
    )
    assert receipt_parent.is_dir()
    assert first_key.endswith(
        hashlib.sha256(
            b"hsconfig-runtime-deck-state-v1\0shadowpriest"
        ).hexdigest()
    )
    assert first_key == first_key.lower()
    assert len(first_key) <= 160


def test_install_refreshes_stale_plan_snapshot_and_preserves_other_decks(
    tmp_path: Path,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    custom_config = runtime_root / "CustomConfig"
    custom_config.mkdir()
    ini_path = custom_config / "deck_config.ini"
    ini_path.write_text(
        "[CONFIGS]\nShadowPriest = old-shadow\nOtherDeck = other-v1\n",
        encoding="utf-8",
    )
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    ini_path.write_text(
        "[CONFIGS]\nShadowPriest = fresher-shadow\nOtherDeck = other-v2\n",
        encoding="utf-8",
    )
    other_content = b'{"other":true}\n'
    other_target = custom_config / "other-v2"
    other_target.mkdir()
    (other_target / "GlobalValues.json").write_bytes(other_content)
    other_record = (
        f"GlobalValues.json\0{len(other_content)}\0"
        f"{hashlib.sha256(other_content).hexdigest()}\n"
    ).encode("utf-8")
    state_dir = runtime_root / ".hsconfig"
    state_dir.mkdir()
    other = RuntimeDeckState(
        state_key=f"other--sha256-{'b' * 64}",
        deck_name="OtherDeck",
        config_dir="other-v2",
        package_root_sha256=hashlib.sha256(other_record).hexdigest(),
        ini_sha256="d" * 64,
    )
    (state_dir / "state.json").write_bytes(
        serialize_runtime_state(RuntimeState(1, (other,)))
    )

    result = install_runtime_package(plan)

    content = ini_path.read_text(encoding="utf-8")
    assert result.previous_config_dir == "fresher-shadow"
    assert "OtherDeck = other-v2" in content
    assert f"ShadowPriest = {plan.versioned_config_dir}" in content
    state = read_runtime_state(runtime_root)
    assert state is not None
    assert {deck.deck_name for deck in state.decks} == {
        "OtherDeck",
        "ShadowPriest",
    }
    preserved = next(
        deck for deck in state.decks if deck.deck_name == "OtherDeck"
    )
    assert preserved.state_key == other.state_key
    assert preserved.config_dir == other.config_dir
    assert preserved.package_root_sha256 == other.package_root_sha256


def test_retired_or_changed_source_fails_before_runtime_mutation(
    tmp_path: Path,
) -> None:
    first, runtime_root, _rendered = publish_fixture(tmp_path, revision=1)
    plan = plan_runtime_install(
        published_output=first,
        runtime_root=runtime_root,
    )
    second_rendered = build_rendered_run(tmp_path / "source-2", 2)
    second = publish_configure_run(second_rendered, first.output_root)
    assert second.content_root_sha256 != first.content_root_sha256

    with pytest.raises(ValueError, match="runtime_install_source_not_current"):
        install_runtime_package(plan)

    assert list(runtime_root.iterdir()) == []


def test_recovery_rejects_semantically_equal_but_byte_changed_runtime(
    tmp_path: Path,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    install_runtime_package(plan)
    target = (
        runtime_root
        / "CustomConfig"
        / plan.versioned_config_dir
        / "Mulligan.json"
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    target.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(
        RuntimeError,
        match="runtime_package_verification_failed",
    ):
        recover_runtime_state(runtime_root)


def test_unowned_existing_digest_target_fails_closed(
    tmp_path: Path,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    target = runtime_root / "CustomConfig" / plan.versioned_config_dir
    target.mkdir(parents=True)
    (target / "Mulligan.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="runtime_digest_target_conflict",
    ):
        install_runtime_package(plan)

    assert (target / "Mulligan.json").read_text(encoding="utf-8") == "{}\n"


def test_plan_rejects_manually_inconsistent_versioned_name(
    tmp_path: Path,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )

    with pytest.raises(ValueError, match="runtime_install_plan_invalid"):
        RuntimeInstallPlan(
            deck_name=plan.deck_name,
            logical_config_dir=plan.logical_config_dir,
            versioned_config_dir="wrong",
            package_root_sha256=plan.package_root_sha256,
            source_revision_root=plan.source_revision_root,
            source_package_root=plan.source_package_root,
            runtime_root=plan.runtime_root,
            ini_snapshot=plan.ini_snapshot,
        )


def test_recovery_fails_closed_on_unknown_staging_residue(
    tmp_path: Path,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    install_runtime_package(plan)
    unknown = runtime_root / ".hsconfig" / "staging" / ("9" * 32)
    unknown.mkdir()

    with pytest.raises(
        RuntimeError,
        match="runtime_recovery_ownership_ambiguous",
    ):
        recover_runtime_state(runtime_root)

    assert unknown.is_dir()


def test_recovery_fails_closed_on_duplicate_finalized_target_owner(
    tmp_path: Path,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    install_runtime_package(plan)
    owners = load_runtime_transaction_journals(runtime_root)
    assert len(owners) == 1
    duplicate_id = "2" * 32
    duplicate = replace(
        owners[0],
        transaction_id=duplicate_id,
        candidate_path=f".hsconfig/staging/{duplicate_id}",
    )
    write_runtime_transaction_journal(
        runtime_transaction_journal_path(runtime_root, duplicate_id),
        duplicate,
    )

    with pytest.raises(
        RuntimeError,
        match="runtime_recovery_ownership_ambiguous",
    ):
        recover_runtime_state(runtime_root)

    assert len(load_runtime_transaction_journals(runtime_root)) == 2


def test_casefolded_selected_owned_target_is_recovered_not_deleted(
    tmp_path: Path,
) -> None:
    _published, runtime_root, _rendered = publish_fixture(tmp_path)
    logical = "ShAdOwPrIeSt-Old"
    custom_config = runtime_root / "CustomConfig"
    custom_config.mkdir()
    old_target, journal = seed_owned_old_revision(
        runtime_root,
        phase=RuntimeTransactionPhase.RUNTIME_VERIFIED,
        logical_name=logical,
    )
    ini = custom_config / "deck_config.ini"
    mixed_selection = journal.next_config_dir.swapcase()
    ini.write_text(
        f"[cOnFiGs]\nshadowpriest = {mixed_selection}\n",
        encoding="utf-8",
    )
    updated = replace(
        journal,
        next_ini_sha256=hashlib.sha256(ini.read_bytes()).hexdigest(),
    )
    write_runtime_transaction_journal(
        runtime_transaction_journal_path(
            runtime_root,
            updated.transaction_id,
        ),
        updated,
    )

    state = recover_runtime_state(runtime_root)

    assert old_target.is_dir()
    assert {path.name for path in old_target.iterdir()} == {
        "A.json",
        "B.json",
        "C.json",
    }
    assert ini.read_text(encoding="utf-8") == (
        f"[cOnFiGs]\nshadowpriest = {mixed_selection}\n"
    )
    assert state is not None
    assert state.decks[0].config_dir == journal.next_config_dir
    owner = load_runtime_transaction_journals(runtime_root)
    assert len(owner) == 1
    assert owner[0].phase == RuntimeTransactionPhase.FINALIZED


def test_cleanup_retains_target_active_for_other_deck_with_case_variant(
    tmp_path: Path,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    (runtime_root / "CustomConfig").mkdir()
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    old_target, old_owner = seed_owned_old_revision(runtime_root)
    ini = runtime_root / "CustomConfig" / "deck_config.ini"
    ini.write_text(
        "[CONFIGS]\n"
        f"ShadowPriest = {old_owner.next_config_dir}\n"
        f"OtherDeck = {old_owner.next_config_dir.swapcase()}\n",
        encoding="utf-8",
    )
    updated_owner = replace(
        old_owner,
        next_ini_sha256=hashlib.sha256(ini.read_bytes()).hexdigest(),
    )
    write_runtime_transaction_journal(
        runtime_transaction_journal_path(
            runtime_root,
            updated_owner.transaction_id,
        ),
        updated_owner,
    )

    install_runtime_package(plan)

    assert old_target.is_dir()
    assert old_owner.next_config_dir.swapcase() in ini.read_text(
        encoding="utf-8"
    )
    owners = load_runtime_transaction_journals(runtime_root)
    assert len(owners) == 2
    assert {
        owner.target_path.casefold() for owner in owners if owner.owns_target
    } == {
        f"CustomConfig/{old_owner.next_config_dir}".casefold(),
        f"CustomConfig/{plan.versioned_config_dir}".casefold(),
    }


def test_plan_and_install_require_typed_contract_objects(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    with pytest.raises(TypeError, match="published_output_required"):
        plan_runtime_install(published_output=object(), runtime_root=runtime_root)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="runtime_install_plan_required"):
        install_runtime_package(object())  # type: ignore[arg-type]


def test_plan_rejects_inconsistent_published_paths(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    published = PublishedOutput(
        output_root=tmp_path / "out",
        revision_root=tmp_path / "wrong" / "revisions" / f"sha256-{'a' * 64}",
        package_root=tmp_path / "wrong-package",
        content_root_sha256="a" * 64,
        reused_existing_revision=False,
    )
    with pytest.raises(ValueError, match="published_output_invalid"):
        plan_runtime_install(published_output=published, runtime_root=runtime_root)


def test_plan_rejects_published_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "out"
    revision_root = output_root / "revisions" / f"sha256-{'a' * 64}"
    published = PublishedOutput(
        output_root=output_root,
        revision_root=revision_root,
        package_root=revision_root / "04_package",
        content_root_sha256="a" * 64,
        reused_existing_revision=False,
    )
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setattr(
        runtime_installer,
        "snapshot_and_verify_revision",
        lambda _path: SimpleNamespace(
            manifest=SimpleNamespace(content_root_sha256="b" * 64)
        ),
    )
    with pytest.raises(ValueError, match="published_output_invalid"):
        plan_runtime_install(published_output=published, runtime_root=runtime_root)


def test_plan_rejects_overlong_versioned_component(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "out"
    revision_root = output_root / "revisions" / f"sha256-{'a' * 64}"
    published = PublishedOutput(
        output_root=output_root,
        revision_root=revision_root,
        package_root=revision_root / "04_package",
        content_root_sha256="a" * 64,
        reused_existing_revision=False,
    )
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    manifest = SimpleNamespace(content_root_sha256="a" * 64)
    monkeypatch.setattr(
        runtime_installer,
        "snapshot_and_verify_revision",
        lambda _path: SimpleNamespace(manifest=manifest),
    )
    monkeypatch.setattr(
        runtime_installer,
        "_runtime_package_spec",
        lambda _manifest: SimpleNamespace(
            deck_name="Deck",
            logical_config_dir="x" * 250,
            package_root_sha256="b" * 64,
        ),
    )
    with pytest.raises(ValueError, match="runtime_config_component_too_long"):
        plan_runtime_install(published_output=published, runtime_root=runtime_root)


def test_install_locked_requires_current_source_snapshot(tmp_path: Path) -> None:
    plan = SimpleNamespace()
    with pytest.raises(ValueError, match="runtime_install_source_not_current"):
        runtime_installer._install_locked(
            plan,  # type: ignore[arg-type]
            SimpleNamespace(),  # type: ignore[arg-type]
            None,
            SimpleNamespace(),  # type: ignore[arg-type]
            runtime_installer.no_fault,
        )


def test_source_manifest_sha256_rejects_invalid_revision_name() -> None:
    plan = SimpleNamespace(source_revision_root=Path("revision-invalid"))
    with pytest.raises(ValueError, match="runtime_install_plan_invalid"):
        runtime_installer._source_manifest_sha256(plan)  # type: ignore[arg-type]


def _manifest(*paths: str) -> SimpleNamespace:
    entries = tuple(
        SimpleNamespace(relative_path=path, size=1, sha256="a" * 64)
        for path in paths
    )
    return SimpleNamespace(entries=entries, deck_name="Deck")


@pytest.mark.parametrize(
    "manifest",
    (
        None,
        _manifest("04_package/CustomConfig/OnlyConfig"),
        _manifest("04_package/CustomConfig//file.json"),
        _manifest("04_package/CustomConfig/A/file.json", "04_package/CustomConfig/B/file.json"),
        _manifest("04_package/CustomConfig/../file.json"),
        _manifest(),
    ),
)
def test_runtime_package_spec_rejects_invalid_manifest_shapes(
    manifest: SimpleNamespace | None,
) -> None:
    with pytest.raises(ValueError):
        runtime_installer._runtime_package_spec(manifest)  # type: ignore[arg-type]


def test_runtime_package_spec_rejects_unsorted_or_duplicate_paths() -> None:
    with pytest.raises(ValueError, match="runtime_package_manifest_invalid"):
        runtime_installer._runtime_package_spec(
            _manifest(
                "04_package/CustomConfig/Deck/z.json",
                "04_package/CustomConfig/Deck/a.json",
            )
        )
    with pytest.raises(ValueError, match="runtime_package_manifest_invalid"):
        runtime_installer._runtime_package_spec(
            _manifest(
                "04_package/CustomConfig/Deck/a.json",
                "04_package/CustomConfig/Deck/a.json",
            )
        )


def test_ensure_directory_accepts_create_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "new"

    def raced_create(*_args: object, **_kwargs: object) -> None:
        target.mkdir()
        raise FileExistsError()

    monkeypatch.setattr(runtime_installer, "secure_create_directory", raced_create)
    runtime_installer._ensure_directory(target)
    assert target.is_dir()


def test_copy_runtime_files_rejects_changed_source(
    tmp_path: Path,
) -> None:
    spec = runtime_installer._RuntimePackageSpec(
        deck_name="Deck",
        logical_config_dir="Deck",
        package_root_sha256="a" * 64,
        files=(
            runtime_installer._RuntimeFile(
                relative_path="nested/file.json",
                size=1,
                sha256=hashlib.sha256(b"x").hexdigest(),
                source_path="source.json",
            ),
        ),
    )
    source = SimpleNamespace(read_bytes=lambda _path: b"changed")
    with pytest.raises(ValueError, match="runtime_install_source_not_current"):
        runtime_installer._copy_runtime_files(tmp_path, spec, source)  # type: ignore[arg-type]
    assert (tmp_path / "nested").is_dir()


def test_copy_runtime_files_closes_descriptor_when_fdopen_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"x"
    spec = runtime_installer._RuntimePackageSpec(
        deck_name="Deck",
        logical_config_dir="Deck",
        package_root_sha256="a" * 64,
        files=(runtime_installer._RuntimeFile("file", 1, hashlib.sha256(content).hexdigest(), "source"),),
    )
    descriptor = os.open(tmp_path / "file", os.O_CREAT | os.O_RDWR)
    closes: list[int] = []
    real_close = os.close
    monkeypatch.setattr(runtime_installer, "secure_open_file_descriptor", lambda *_args, **_kwargs: descriptor)
    monkeypatch.setattr(runtime_installer.os, "fdopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fdopen")))
    monkeypatch.setattr(runtime_installer.os, "close", closes.append)
    with pytest.raises(RuntimeError, match="fdopen"):
        runtime_installer._copy_runtime_files(
            tmp_path,
            spec,
            SimpleNamespace(read_bytes=lambda _path: content),  # type: ignore[arg-type]
        )
    assert closes == [descriptor]
    real_close(descriptor)


@pytest.mark.parametrize("failure", ("directories", "content"))
def test_verify_runtime_tree_against_spec_wraps_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    row = runtime_installer._RuntimeFile("file", 1, hashlib.sha256(b"x").hexdigest(), "source")
    spec = runtime_installer._RuntimePackageSpec("Deck", "Deck", "a" * 64, (row,))
    snapshot = SimpleNamespace(
        file_names=lambda: ("file",),
        directory_names=("unexpected",) if failure == "directories" else (),
        read_bytes=lambda _path: b"wrong" if failure == "content" else b"x",
    )
    monkeypatch.setattr(runtime_installer, "snapshot_bounded_filesystem_package", lambda _root: snapshot)
    with pytest.raises(RuntimeError, match="runtime_package_verification_failed"):
        runtime_installer._verify_runtime_tree_against_spec(
            Path("root"),
            spec,
            None,
        )


def test_write_journal_detects_failed_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_installer, "write_runtime_transaction_journal", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "read_runtime_transaction_journal", lambda _path: None)
    with pytest.raises(RuntimeError, match="journal_commit_failed"):
        runtime_installer._write_journal(Path("journal"), object())  # type: ignore[arg-type]


def test_state_and_receipt_helpers_require_ini_digest(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="ini_commit_verification_failed"):
        runtime_installer._write_selected_state(tmp_path, object(), None)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="ini_commit_verification_failed"):
        runtime_installer._receipt_payload_for_plan(object(), None, "state")  # type: ignore[arg-type]


def test_write_selected_state_detects_failed_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = SimpleNamespace(
        state_key="deck",
        deck_name="Deck",
        next_config_dir="Config",
        package_root_sha256="a" * 64,
    )
    monkeypatch.setattr(runtime_installer, "read_runtime_state", lambda _root: None)
    monkeypatch.setattr(runtime_installer, "_plain_file_bytes_or_none", lambda _path: b"already")
    monkeypatch.setattr(runtime_installer, "atomic_write_bytes", lambda *_args: None)
    with pytest.raises(RuntimeError, match="state_commit_verification_failed"):
        runtime_installer._write_selected_state(tmp_path, journal, "b" * 64)  # type: ignore[arg-type]


def test_write_receipt_rejects_invalid_key_and_failed_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="runtime_receipt_invalid"):
        runtime_installer._write_receipt(tmp_path, {"state_key": "../bad"})
    monkeypatch.setattr(runtime_installer, "_ensure_directory", lambda _path: None)
    monkeypatch.setattr(runtime_installer, "atomic_write_bytes", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime_installer, "_plain_file_bytes_or_none", lambda _path: b"wrong")
    with pytest.raises(RuntimeError, match="receipt_commit_verification_failed"):
        runtime_installer._write_receipt(tmp_path, {"state_key": "valid"})


def test_owner_lookup_requires_exactly_one_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(runtime_installer, "load_runtime_transaction_journals", lambda _root: ())
    with pytest.raises(RuntimeError, match="runtime_digest_target_conflict"):
        runtime_installer._require_unambiguous_owner(tmp_path, target, "a" * 64)


@pytest.mark.parametrize(
    ("content", "expected"),
    (
        (b"\xff", None),
        (b"[OTHER]\nignored\n[CONFIGS]\n# comment\n; note\nno equals\nDeck=Config\n", {"config"}),
        (b"[CONFIGS]\nDeck=Config\ndeck=Other\n", None),
    ),
)
def test_active_config_dirs_parses_or_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
    expected: set[str] | None,
) -> None:
    monkeypatch.setattr(runtime_installer, "_plain_file_bytes_or_none", lambda _path: content)
    assert runtime_installer._active_config_dirs(tmp_path) == expected


def test_verify_active_state_targets_handles_invalid_and_inactive_mappings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deck = RuntimeDeckState("key", "Deck", "Config", "a" * 64, "b" * 64)
    state = RuntimeState(1, (deck,))
    calls: list[Path] = []
    monkeypatch.setattr(runtime_installer, "_verify_runtime_tree_digest", lambda path, _digest: calls.append(path))
    monkeypatch.setattr(runtime_installer, "_active_config_dirs", lambda _root: None)
    runtime_installer._verify_active_state_targets(tmp_path, state)
    monkeypatch.setattr(runtime_installer, "_active_config_dirs", lambda _root: set())
    runtime_installer._verify_active_state_targets(tmp_path, state)
    monkeypatch.setattr(runtime_installer, "_active_config_dirs", lambda _root: {"config"})
    runtime_installer._verify_active_state_targets(tmp_path, state)
    assert calls == [tmp_path / "CustomConfig" / "Config"]


def test_remove_owned_tree_rejects_identity_change_and_removes_directories(
    tmp_path: Path,
) -> None:
    root = tmp_path / "owned"
    (root / "nested").mkdir(parents=True)
    (root / "nested" / "file").write_bytes(b"x")
    identity = path_identity(root)
    with pytest.raises(RuntimeError, match="ownership_ambiguous"):
        runtime_installer._remove_owned_tree(
            root,
            (identity[0], identity[1] + 1, identity[2]),
        )
    runtime_installer._remove_owned_tree(root, identity)
    assert not root.exists()


def test_delete_journal_missing_is_noop(tmp_path: Path) -> None:
    runtime_installer._delete_journal(tmp_path / "missing.json")


class _HostileRuntimePrimary(BaseException):
    def add_note(self, _note: str) -> None:
        raise RuntimeError("hostile")


def test_runtime_add_note_never_masks_hostile_primary() -> None:
    runtime_installer._add_note(
        _HostileRuntimePrimary(),
        "cleanup",
        RuntimeError("secondary"),
    )


def test_resume_cleanup_rejects_invalid_journal_and_active_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = SimpleNamespace(cleanup_started=False, target_identity=None)
    with pytest.raises(RuntimeError, match="ownership_ambiguous"):
        runtime_installer._resume_owned_cleanup(tmp_path, invalid)  # type: ignore[arg-type]
    active = SimpleNamespace(
        cleanup_started=True,
        target_identity=(1, 2, 3),
        transaction_id="1" * 32,
        target_path="CustomConfig/Config",
        next_config_dir="Config",
    )
    monkeypatch.setattr(runtime_installer, "_active_config_dirs", lambda _root: {"config"})
    assert runtime_installer._resume_owned_cleanup(tmp_path, active) is False  # type: ignore[arg-type]


def test_resume_cleanup_deletes_journal_when_target_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = SimpleNamespace(
        cleanup_started=True,
        target_identity=(1, 2, 3),
        transaction_id="1" * 32,
        target_path="CustomConfig/Missing",
        next_config_dir="Missing",
    )
    deleted: list[Path] = []
    monkeypatch.setattr(runtime_installer, "_active_config_dirs", lambda _root: set())
    monkeypatch.setattr(runtime_installer, "_delete_journal", deleted.append)
    assert runtime_installer._resume_owned_cleanup(tmp_path, journal) is True  # type: ignore[arg-type]
    assert len(deleted) == 1


def test_resume_cleanup_rejects_target_identity_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "CustomConfig" / "Config"
    target.mkdir(parents=True)
    identity = path_identity(target)
    journal = SimpleNamespace(
        cleanup_started=True,
        target_identity=(identity[0], identity[1] + 1, identity[2]),
        transaction_id="1" * 32,
        target_path="CustomConfig/Config",
        next_config_dir="Config",
    )
    monkeypatch.setattr(runtime_installer, "_active_config_dirs", lambda _root: set())
    with pytest.raises(RuntimeError, match="ownership_ambiguous"):
        runtime_installer._resume_owned_cleanup(tmp_path, journal)  # type: ignore[arg-type]


def _unit_plan(tmp_path: Path) -> RuntimeInstallPlan:
    digest = "a" * 64
    logical = "Deck"
    versioned = f"{logical}--sha256-{digest}"
    revision = tmp_path / "out" / "revisions" / f"sha256-{'b' * 64}"
    return RuntimeInstallPlan(
        deck_name="Deck",
        logical_config_dir=logical,
        versioned_config_dir=versioned,
        package_root_sha256=digest,
        source_revision_root=revision,
        source_package_root=revision / "04_package",
        runtime_root=tmp_path / "runtime",
        ini_snapshot=runtime_installer.DeckConfigSnapshot(
            tmp_path / "runtime" / "CustomConfig" / "deck_config.ini",
            False,
            None,
            None,
            None,
        ),
    )


def _unit_journal(
    *,
    phase: RuntimeTransactionPhase = RuntimeTransactionPhase.PREPARED,
    candidate_identity: tuple[int, int, int] | None = None,
    target_identity: tuple[int, int, int] | None = None,
    owns_target: bool = False,
    previous_config_dir: str | None = None,
    transaction_id: str = "1" * 32,
) -> RuntimeTransactionJournal:
    digest = "a" * 64
    logical = "Deck"
    versioned = f"{logical}--sha256-{digest}"
    return RuntimeTransactionJournal(
        schema_version=1,
        transaction_id=transaction_id,
        deck_name="Deck",
        source_manifest_sha256="b" * 64,
        state_key=state_key_for_test("Deck"),
        logical_config_dir=logical,
        package_root_sha256=digest,
        candidate_path=f".hsconfig/staging/{transaction_id}",
        target_path=f"CustomConfig/{versioned}",
        candidate_identity=candidate_identity,
        target_identity=target_identity,
        owns_target=owns_target,
        previous_config_dir=previous_config_dir,
        next_config_dir=versioned,
        previous_ini_sha256=None,
        next_ini_sha256="c" * 64,
        phase=phase,
    )


def test_install_locked_reuses_existing_owned_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _unit_plan(tmp_path)
    identity = (1, 2, 3)
    spec = runtime_installer._RuntimePackageSpec("Deck", "Deck", "a" * 64, ())
    ini_bytes = b"[CONFIGS]\nDeck=Config"
    ini_digest = hashlib.sha256(ini_bytes).hexdigest()
    current_ini = runtime_installer.DeckConfigSnapshot(
        plan.ini_snapshot.path,
        False,
        None,
        None,
        None,
    )
    deleted: list[Path] = []
    monkeypatch.setattr(runtime_installer, "_write_journal", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "secure_create_directory", lambda *_args, **_kwargs: identity)
    monkeypatch.setattr(runtime_installer, "path_identity", lambda _path: identity)
    monkeypatch.setattr(runtime_installer, "_copy_runtime_files", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "_verify_runtime_tree_against_spec", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "path_lexists", lambda path: "CustomConfig" in str(path))
    monkeypatch.setattr(runtime_installer, "_plain_directory_identity", lambda _path: identity)
    monkeypatch.setattr(runtime_installer, "_require_unambiguous_owner", lambda *_args: object())
    monkeypatch.setattr(runtime_installer, "_remove_owned_tree", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "render_deck_config", lambda *_args, **_kwargs: ini_bytes)
    monkeypatch.setattr(runtime_installer, "replace_deck_config_if_unchanged", lambda *_args: ini_digest)
    monkeypatch.setattr(
        runtime_installer,
        "_read_actual_ini",
        lambda _plan: runtime_installer.DeckConfigSnapshot(
            plan.ini_snapshot.path,
            True,
            ini_bytes,
            ini_digest,
            plan.versioned_config_dir,
        ),
    )
    monkeypatch.setattr(runtime_installer, "_write_selected_state", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "_write_receipt", lambda *_args, **_kwargs: Path("receipt"))
    monkeypatch.setattr(runtime_installer, "_cleanup_old_revision", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime_installer, "_delete_journal", deleted.append)
    result = runtime_installer._install_locked(
        plan,
        spec,
        SimpleNamespace(),  # type: ignore[arg-type]
        current_ini,
        runtime_installer.no_fault,
    )
    assert result.status == "applied"
    assert len(deleted) == 1


@pytest.mark.parametrize("mode", ("target_identity", "ini_verification"))
def test_install_locked_detects_postcommit_identity_or_ini_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    plan = _unit_plan(tmp_path)
    identity = (1, 2, 3)
    spec = runtime_installer._RuntimePackageSpec("Deck", "Deck", "a" * 64, ())
    current_ini = plan.ini_snapshot
    ini_bytes = b"next"
    ini_digest = hashlib.sha256(ini_bytes).hexdigest()
    monkeypatch.setattr(runtime_installer, "_write_journal", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "secure_create_directory", lambda *_args, **_kwargs: identity)
    monkeypatch.setattr(runtime_installer, "path_identity", lambda _path: identity)
    monkeypatch.setattr(runtime_installer, "_copy_runtime_files", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "_verify_runtime_tree_against_spec", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "path_lexists", lambda _path: False)
    monkeypatch.setattr(runtime_installer, "secure_replace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runtime_installer,
        "_plain_directory_identity",
        lambda _path: (1, 9, 3) if mode == "target_identity" else identity,
    )
    monkeypatch.setattr(runtime_installer, "render_deck_config", lambda *_args, **_kwargs: ini_bytes)
    monkeypatch.setattr(runtime_installer, "replace_deck_config_if_unchanged", lambda *_args: ini_digest)
    monkeypatch.setattr(
        runtime_installer,
        "_read_actual_ini",
        lambda _plan: runtime_installer.DeckConfigSnapshot(
            plan.ini_snapshot.path,
            True,
            ini_bytes,
            "wrong",
            plan.versioned_config_dir,
        ),
    )
    expected = "target_identity_changed" if mode == "target_identity" else "ini_commit_verification_failed"
    with pytest.raises(RuntimeError, match=expected):
        runtime_installer._install_locked(
            plan,
            spec,
            SimpleNamespace(),  # type: ignore[arg-type]
            current_ini,
            runtime_installer.no_fault,
        )


def test_validate_leased_source_rejects_semantic_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _unit_plan(tmp_path)
    snapshot = SimpleNamespace()
    lease = SimpleNamespace(
        publication=object(),
        snapshot=snapshot,
        content_root_sha256="b" * 64,
        package_root=plan.source_package_root,
    )
    manifest = SimpleNamespace(content_root_sha256="b" * 64)
    monkeypatch.setattr(runtime_installer, "verify_tree_manifest", lambda _snapshot: manifest)
    monkeypatch.setattr(
        runtime_installer,
        "_runtime_package_spec",
        lambda _manifest: SimpleNamespace(
            deck_name="Other",
            logical_config_dir=plan.logical_config_dir,
            package_root_sha256=plan.package_root_sha256,
        ),
    )
    with pytest.raises(ValueError, match="runtime_install_source_not_current"):
        runtime_installer._validate_leased_source(plan, lease)  # type: ignore[arg-type]


def test_copy_runtime_files_rejects_unsafe_written_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"x"
    spec = runtime_installer._RuntimePackageSpec(
        "Deck",
        "Deck",
        "a" * 64,
        (runtime_installer._RuntimeFile("file", 1, hashlib.sha256(content).hexdigest(), "source"),),
    )
    real_fstat = os.fstat

    def changed_size(descriptor: int) -> SimpleNamespace:
        status = real_fstat(descriptor)
        return SimpleNamespace(
            st_mode=status.st_mode,
            st_ino=status.st_ino,
            st_dev=status.st_dev,
            st_nlink=status.st_nlink,
            st_size=2,
            st_file_attributes=getattr(status, "st_file_attributes", 0),
        )

    monkeypatch.setattr(runtime_installer.os, "fstat", changed_size)
    with pytest.raises(RuntimeError, match="runtime_staging_write_failed"):
        runtime_installer._copy_runtime_files(
            tmp_path,
            spec,
            SimpleNamespace(read_bytes=lambda _path: content),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "mode",
    (
        "candidate_mismatch",
        "cleanup_started",
        "cleanup_noop",
        "target_mismatch",
        "selected_invalid",
        "selected_candidate",
        "selected_unowned",
        "unselected_ini",
        "unselected_prepared",
        "unselected_finalized",
    ),
)
def test_recover_locked_handles_every_transaction_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    identity = (1, 2, 3)
    if mode in {"cleanup_started", "cleanup_noop"}:
        journal = replace(
            _unit_journal(
                phase=RuntimeTransactionPhase.FINALIZED,
                candidate_identity=identity,
                target_identity=identity,
                owns_target=True,
            ),
            cleanup_started=True,
        )
    elif mode == "target_mismatch":
        journal = _unit_journal(
            phase=RuntimeTransactionPhase.FINALIZED,
            candidate_identity=identity,
            target_identity=identity,
            owns_target=True,
        )
    elif mode in {"selected_unowned", "unselected_ini"}:
        phase = (
            RuntimeTransactionPhase.FINALIZED
            if mode == "selected_unowned"
            else RuntimeTransactionPhase.INI_COMMITTED
        )
        journal = _unit_journal(
            phase=phase,
            target_identity=identity,
            owns_target=False,
        )
    elif mode == "unselected_finalized":
        journal = _unit_journal(
            phase=RuntimeTransactionPhase.FINALIZED,
            candidate_identity=identity,
            target_identity=identity,
            owns_target=True,
        )
    elif mode == "selected_candidate":
        journal = _unit_journal(
            phase=RuntimeTransactionPhase.RUNTIME_VERIFIED,
            candidate_identity=identity,
        )
    elif mode == "candidate_mismatch":
        journal = _unit_journal(candidate_identity=identity)
    else:
        journal = _unit_journal()

    candidate_actual = None
    target_actual = None
    if mode == "candidate_mismatch":
        candidate_actual = (1, 9, 3)
    elif mode in {"cleanup_started", "cleanup_noop"}:
        target_actual = identity
    elif mode == "target_mismatch":
        target_actual = (1, 9, 3)
    elif mode in {"selected_invalid", "selected_candidate", "selected_unowned", "unselected_ini", "unselected_finalized"}:
        target_actual = identity
    if mode == "selected_candidate":
        candidate_actual = identity

    selected = mode.startswith("selected")
    ini_sha = "wrong" if mode == "selected_invalid" else journal.next_ini_sha256
    ini = runtime_installer.DeckConfigSnapshot(
        tmp_path / "deck_config.ini",
        True,
        b"ini",
        ini_sha,
        journal.next_config_dir if selected else None,
    )
    deleted: list[Path] = []
    removed: list[Path] = []
    written: list[RuntimeTransactionJournal] = []
    monkeypatch.setattr(runtime_installer, "load_runtime_transaction_journals", lambda _root: (journal,))
    monkeypatch.setattr(runtime_installer, "_validate_recovery_ownership", lambda *_args: None)

    def identity_or_none(path: Path) -> tuple[int, int, int] | None:
        return candidate_actual if "staging" in path.parts else target_actual

    monkeypatch.setattr(runtime_installer, "_directory_identity_or_none", identity_or_none)
    monkeypatch.setattr(
        runtime_installer,
        "_resume_owned_cleanup",
        lambda *_args, **_kwargs: mode != "cleanup_noop",
    )
    monkeypatch.setattr(runtime_installer, "read_deck_config", lambda *_args, **_kwargs: ini)
    monkeypatch.setattr(runtime_installer, "_verify_runtime_tree_digest", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "_remove_owned_tree", lambda path, _identity: removed.append(path))
    monkeypatch.setattr(runtime_installer, "read_runtime_state", lambda _root: None)
    monkeypatch.setattr(runtime_installer, "_write_selected_state", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "_receipt_path", lambda *_args: Path("receipt"))
    monkeypatch.setattr(runtime_installer, "_plain_file_bytes_or_none", lambda _path: runtime_installer._receipt_bytes(runtime_installer._receipt_payload(journal, ini_sha)))
    monkeypatch.setattr(runtime_installer, "_write_receipt", lambda *_args, **_kwargs: Path("receipt"))
    monkeypatch.setattr(runtime_installer, "_cleanup_old_revision", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime_installer, "_delete_journal", deleted.append)
    monkeypatch.setattr(runtime_installer, "_write_journal", lambda _path, row: written.append(row))
    monkeypatch.setattr(
        runtime_installer,
        "_active_config_dirs",
        lambda _root: {journal.next_config_dir.casefold()}
        if mode == "unselected_finalized"
        else set(),
    )
    monkeypatch.setattr(runtime_installer, "_verify_active_state_targets", lambda *_args: None)

    if mode in {"candidate_mismatch", "target_mismatch"}:
        with pytest.raises(RuntimeError, match="ownership_ambiguous"):
            runtime_installer._recover_locked(tmp_path)
    elif mode == "selected_invalid":
        with pytest.raises(RuntimeError, match="committed_target_invalid"):
            runtime_installer._recover_locked(tmp_path)
    elif mode == "unselected_ini":
        with pytest.raises(RuntimeError, match="runtime_recovery_ini_conflict"):
            runtime_installer._recover_locked(tmp_path)
    else:
        outcome = runtime_installer._recover_locked(tmp_path)
        if mode == "cleanup_started":
            assert outcome.repaired is True
        if mode == "selected_candidate":
            assert removed
        if mode in {"selected_unowned", "unselected_prepared"}:
            assert deleted


@pytest.mark.parametrize(
    "mode",
    ("missing", "identity_mismatch", "cleanup_started", "prepare_none"),
)
def test_cleanup_old_revision_handles_owned_target_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    old_path = tmp_path / "CustomConfig" / "Old"
    old_path.mkdir(parents=True)
    identity = path_identity(old_path)
    current = SimpleNamespace(previous_config_dir="Old", next_config_dir="New")
    owner = SimpleNamespace(
        phase=RuntimeTransactionPhase.FINALIZED,
        owns_target=True,
        target_path="CustomConfig/Old",
        transaction_id="1" * 32,
        target_identity=identity,
        cleanup_started=mode == "cleanup_started",
        package_root_sha256="a" * 64,
    )
    deleted: list[Path] = []
    resumed: list[object] = []
    monkeypatch.setattr(runtime_installer, "_active_config_dirs", lambda _root: set())
    monkeypatch.setattr(runtime_installer, "load_runtime_transaction_journals", lambda _root: (owner,))
    monkeypatch.setattr(runtime_installer, "path_lexists", lambda _path: mode != "missing")
    monkeypatch.setattr(
        runtime_installer,
        "_plain_directory_identity",
        lambda _path: (identity[0], identity[1] + 1, identity[2])
        if mode == "identity_mismatch"
        else identity,
    )
    monkeypatch.setattr(runtime_installer, "_delete_journal", deleted.append)
    monkeypatch.setattr(runtime_installer, "_verify_runtime_tree_digest", lambda *_args: None)
    monkeypatch.setattr(
        runtime_installer,
        "_resume_owned_cleanup",
        lambda *_args, **_kwargs: resumed.append(owner),
    )
    monkeypatch.setattr(runtime_installer, "_prepare_cleanup_journal", lambda *_args: None)
    if mode == "identity_mismatch":
        with pytest.raises(RuntimeError, match="ownership_ambiguous"):
            runtime_installer._cleanup_old_revision(tmp_path, current)  # type: ignore[arg-type]
    else:
        runtime_installer._cleanup_old_revision(tmp_path, current)  # type: ignore[arg-type]
    if mode == "missing":
        assert deleted
    if mode == "cleanup_started":
        assert resumed


def test_prepare_cleanup_journal_returns_none_when_serialization_rejects_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    owner = _unit_journal(
        phase=RuntimeTransactionPhase.FINALIZED,
        candidate_identity=path_identity(target),
        target_identity=path_identity(target),
        owns_target=True,
    )
    snapshot = SimpleNamespace(file_names=lambda: (), directory_names=())
    monkeypatch.setattr(runtime_installer, "snapshot_bounded_filesystem_package", lambda _path: snapshot)
    monkeypatch.setattr(
        runtime_installer,
        "runtime_transaction_journal_bytes",
        lambda _journal: (_ for _ in ()).throw(ValueError("too large")),
    )
    assert runtime_installer._prepare_cleanup_journal(tmp_path, owner, target) is None


def test_resume_cleanup_removes_directory_entries_and_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _unit_journal(
        phase=RuntimeTransactionPhase.FINALIZED,
        candidate_identity=(1, 2, 3),
        target_identity=(1, 2, 3),
        owns_target=True,
    )
    target = tmp_path / base.target_path
    nested = target / "nested"
    nested.mkdir(parents=True)
    target_identity = path_identity(target)
    entry = runtime_installer.RuntimeCleanupEntry(
        "directory",
        "nested",
        path_identity(nested),
    )
    journal = replace(
        base,
        candidate_identity=target_identity,
        target_identity=target_identity,
        cleanup_started=True,
        cleanup_entries=(entry,),
    )
    monkeypatch.setattr(runtime_installer, "_active_config_dirs", lambda _root: set())
    monkeypatch.setattr(runtime_installer, "_write_journal", lambda *_args: None)
    monkeypatch.setattr(runtime_installer, "_delete_journal", lambda _path: None)
    assert runtime_installer._resume_owned_cleanup(tmp_path, journal) is True
    assert not target.exists()


def test_resume_cleanup_rejects_changed_entry_and_leftover_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _unit_journal(
        phase=RuntimeTransactionPhase.FINALIZED,
        candidate_identity=(1, 2, 3),
        target_identity=(1, 2, 3),
        owns_target=True,
    )
    target = tmp_path / base.target_path
    target.mkdir(parents=True)
    target_identity = path_identity(target)
    file_path = target / "file"
    file_path.write_bytes(b"x")
    file_identity = path_identity(file_path)
    entry = runtime_installer.RuntimeCleanupEntry(
        "file",
        "file",
        (file_identity[0], file_identity[1] + 1, file_identity[2]),
    )
    changed = replace(
        base,
        candidate_identity=target_identity,
        target_identity=target_identity,
        cleanup_started=True,
        cleanup_entries=(entry,),
    )
    monkeypatch.setattr(runtime_installer, "_active_config_dirs", lambda _root: set())
    monkeypatch.setattr(runtime_installer, "_validate_remaining_cleanup_inventory", lambda *_args: None)
    with pytest.raises(RuntimeError, match="ownership_ambiguous"):
        runtime_installer._resume_owned_cleanup(tmp_path, changed)

    file_path.unlink()
    (target / "unknown").write_bytes(b"x")
    leftover = replace(
        base,
        candidate_identity=target_identity,
        target_identity=target_identity,
        cleanup_started=True,
    )
    with pytest.raises(RuntimeError, match="ownership_ambiguous"):
        runtime_installer._resume_owned_cleanup(tmp_path, leftover)


def test_repeated_install_recreates_missing_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    first = install_runtime_package(plan)
    assert first.receipt_path is not None
    first.receipt_path.unlink()
    monkeypatch.setattr(
        runtime_installer,
        "_recover_locked",
        lambda root: runtime_installer._RecoveryOutcome(
            read_runtime_state(root),
            False,
        ),
    )

    repeated = install_runtime_package(plan)

    assert repeated.status == "already_current"
    assert repeated.receipt_path is not None
    assert repeated.receipt_path.is_file()


def test_install_notes_best_effort_recovery_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published, runtime_root, _rendered = publish_fixture(tmp_path)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    monkeypatch.setattr(
        runtime_installer,
        "_recover_locked",
        lambda _root: (_ for _ in ()).throw(RuntimeError("recovery")),
    )

    def fail_after_lock(stage: str) -> None:
        if stage == "after_lock":
            raise ValueError("primary")

    with pytest.raises(ValueError, match="primary") as caught:
        install_runtime_package(plan, fault_hook=fail_after_lock)

    assert any(
        "best-effort runtime recovery failed" in note
        for note in caught.value.__notes__
    )


def test_recovery_ownership_rejects_more_than_entry_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / ".hsconfig" / "staging"
    staging.mkdir(parents=True)
    identity = path_identity(staging)
    prototype = _unit_journal(candidate_identity=identity)
    journals: list[RuntimeTransactionJournal] = []
    entries: list[SimpleNamespace] = []
    for index in range(1025):
        transaction_id = f"{index + 1:032x}"
        journals.append(
            replace(
                prototype,
                transaction_id=transaction_id,
                candidate_path=f".hsconfig/staging/{transaction_id}",
            )
        )
        entries.append(SimpleNamespace(name=transaction_id, path=str(staging)))

    class FakeScandir:
        def __enter__(self) -> object:
            return iter(entries)

        def __exit__(self, *_args: object) -> None:
            pass

    monkeypatch.setattr(runtime_installer.os, "scandir", lambda _path: FakeScandir())
    with pytest.raises(RuntimeError, match="ownership_ambiguous"):
        runtime_installer._validate_recovery_ownership(tmp_path, tuple(journals))
