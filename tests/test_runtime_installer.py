from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

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
