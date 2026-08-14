from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any

import pytest

from hsconfig.configure_run_model import (
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
)
from hsconfig import output_inventory, output_reconciliation
from hsconfig.output_publisher import publish_configure_run
from hsconfig.output_inventory import (
    OutputInventory,
    reconcile_audited_outputs,
)
from hsconfig.output_reconciliation import (
    apply_audited_outputs,
    propose_legacy_deletion,
)
from tests.helpers.controlled_subprocess import controlled_python_environment


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "operator" / "audited-deck-catalog.json"
INVENTORY_FIELDS = (
    "audited_decks",
    "current_outputs",
    "revision_count",
    "staging_count",
    "unreferenced_revision_count",
    "backup_count",
    "rollback_count",
    "orphan_transaction_count",
    "orphan_receipt_count",
    "temporary_file_count",
    "invalid_count",
)


@pytest.fixture(scope="session")
def rendered_runs() -> Mapping[str, RenderedConfigureRun]:
    authority = output_inventory.load_catalog_authority(CATALOG)
    return output_reconciliation.build_rendered_audited_runs(authority)


@pytest.fixture()
def canonical_outputs(
    tmp_path: Path,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> Path:
    outputs = tmp_path / "outputs"
    for deck_name, rendered in rendered_runs.items():
        publish_configure_run(rendered, outputs / deck_name)
    return outputs


def _inventory(outputs: Path) -> OutputInventory:
    return reconcile_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
    )


def _rendered_revision_variant(
    rendered: RenderedConfigureRun,
) -> RenderedConfigureRun:
    stage_artifacts = {
        artifact.relative_path: artifact.content
        for artifact in rendered.model.stage_artifacts
        if artifact.relative_path != "configure_summary.json"
    }
    stage_artifacts["01_manifest/publisher_revision.json"] = (
        b'{"revision":2}\n'
    )
    return render_configure_run_model(
        create_configure_run_model(
            package=rendered.model.package,
            stage_artifacts=stage_artifacts,
        )
    )


def _tree_snapshot(root: Path) -> dict[str, tuple[Any, ...]]:
    snapshot: dict[str, tuple[Any, ...]] = {}
    for path in sorted(root.rglob("*")):
        node_stat = path.lstat()
        relative = path.relative_to(root).as_posix()
        common = (
            node_stat.st_mode,
            node_stat.st_dev,
            node_stat.st_ino,
            node_stat.st_size,
            node_stat.st_mtime_ns,
        )
        snapshot[relative] = (
            *common,
            path.read_bytes() if path.is_file() else None,
        )
    return snapshot


def _tree_identity_snapshot(root: Path) -> dict[str, tuple[int, ...]]:
    """Snapshot identities and metadata without opening deliberately locked files."""

    return {
        path.relative_to(root).as_posix(): (
            status.st_mode,
            status.st_dev,
            status.st_ino,
            status.st_size,
            status.st_mtime_ns,
            status.st_nlink,
        )
        for path in sorted(root.rglob("*"))
        for status in (path.lstat(),)
    }


def _write_legacy_root(root: Path, deck_name: str) -> None:
    reports = root / "04_package" / "reports"
    reports.mkdir(parents=True)
    (reports / "input_manifest.json").write_text(
        json.dumps({"deck_name": deck_name}),
        encoding="utf-8",
    )


def _approval_digest(outputs: Path) -> str:
    return propose_legacy_deletion(
        outputs_root=outputs,
        catalog_path=CATALOG,
    ).approval_digest


def _run_hard_kill_apply(
    outputs: Path,
    approval: str,
    fault_stage: str,
    *,
    exit_code: int = 76,
) -> subprocess.CompletedProcess[str]:
    child = """
import os
import sys
from pathlib import Path
from hsconfig.output_reconciliation import apply_audited_outputs

def hard_kill(stage: str) -> None:
    if stage == sys.argv[4]:
        os._exit(int(sys.argv[5]))

apply_audited_outputs(
    outputs_root=Path(sys.argv[1]),
    catalog_path=Path(sys.argv[2]),
    legacy_approval_digest=sys.argv[3],
    fault_hook=hard_kill,
)
"""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            child,
            str(outputs),
            str(CATALOG),
            approval,
            fault_stage,
            str(exit_code),
        ],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


def test_output_inventory_has_the_required_stable_field_order() -> None:
    assert tuple(field.name for field in fields(OutputInventory)) == (
        INVENTORY_FIELDS
    )


def test_empty_output_root_reports_all_twelve_audited_outputs_missing(
    tmp_path: Path,
) -> None:
    inventory = reconcile_audited_outputs(
        outputs_root=tmp_path / "outputs",
        catalog_path=CATALOG,
    )

    assert asdict(inventory) == {
        "audited_decks": 12,
        "current_outputs": 0,
        "revision_count": 0,
        "staging_count": 0,
        "unreferenced_revision_count": 0,
        "backup_count": 0,
        "rollback_count": 0,
        "orphan_transaction_count": 0,
        "orphan_receipt_count": 0,
        "temporary_file_count": 0,
        "invalid_count": 12,
    }


def test_canonical_twelve_deck_state_has_exact_expected_inventory(
    canonical_outputs: Path,
) -> None:
    assert asdict(_inventory(canonical_outputs)) == {
        "audited_decks": 12,
        "current_outputs": 12,
        "revision_count": 12,
        "staging_count": 0,
        "unreferenced_revision_count": 0,
        "backup_count": 0,
        "rollback_count": 0,
        "orphan_transaction_count": 0,
        "orphan_receipt_count": 0,
        "temporary_file_count": 0,
        "invalid_count": 0,
    }


def test_republishing_one_deck_keeps_the_inventory_canonical(
    canonical_outputs: Path,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    shadow_priest = rendered_runs["ShadowPriest"]

    publish_configure_run(
        _rendered_revision_variant(shadow_priest),
        canonical_outputs / "ShadowPriest",
    )

    inventory = _inventory(canonical_outputs)
    assert output_inventory.inventory_is_current(inventory)
    assert inventory.orphan_transaction_count == 0
    assert inventory.invalid_count == 0


def test_missing_and_unknown_extra_roots_fail_closed(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    unknown = outputs / "UnknownDeck"
    unknown.mkdir(parents=True)
    (unknown / "sentinel.txt").write_text("unknown", encoding="utf-8")

    inventory = _inventory(outputs)

    assert inventory.current_outputs == 0
    assert inventory.invalid_count == 13
    with pytest.raises(ValueError, match="unknown_output_root"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)
    assert (outputs / "UnknownDeck").is_dir()


@pytest.mark.parametrize("failure", ["missing", "invalid", "dangling"])
def test_missing_invalid_and_dangling_current_are_invalid(
    tmp_path: Path,
    rendered_runs: Mapping[str, RenderedConfigureRun],
    failure: str,
) -> None:
    root = tmp_path / "outputs" / "ShadowPriest"
    publish_configure_run(rendered_runs["ShadowPriest"], root)
    current = root / "current.json"
    if failure == "missing":
        current.unlink()
    elif failure == "invalid":
        current.write_bytes(b"{not-json")
    else:
        payload = json.loads(current.read_text(encoding="utf-8"))
        payload["revision"] = f"revisions/sha256-{'0' * 64}"
        payload["content_root_sha256"] = "0" * 64
        current.write_text(json.dumps(payload), encoding="utf-8")

    inventory = _inventory(tmp_path / "outputs")

    assert inventory.current_outputs == 0
    assert inventory.invalid_count >= 12
    assert inventory.unreferenced_revision_count == 1


def test_duplicate_revision_staging_and_invalid_manifest_are_counted(
    tmp_path: Path,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    root = tmp_path / "outputs" / "ShadowPriest"
    published = publish_configure_run(rendered_runs["ShadowPriest"], root)
    revisions = root / "revisions"
    duplicate = revisions / f"sha256-{'1' * 64}"
    shutil.copytree(published.revision_root, duplicate)
    (revisions / f".staging-{'2' * 32}").mkdir()
    (duplicate / "package_manifest.json").write_bytes(b"{}")

    inventory = _inventory(tmp_path / "outputs")

    assert inventory.revision_count == 2
    assert inventory.unreferenced_revision_count == 1
    assert inventory.staging_count == 1
    assert inventory.invalid_count >= 11


def test_one_corrupt_unreferenced_revision_adds_exactly_one_invalid(
    canonical_outputs: Path,
) -> None:
    before = _inventory(canonical_outputs)
    deck_root = canonical_outputs / "ShadowPriest"
    current = json.loads(
        (deck_root / "current.json").read_text(encoding="utf-8")
    )
    source = deck_root / current["revision"]
    extra = deck_root / "revisions" / f"sha256-{'1' * 64}"
    shutil.copytree(source, extra)
    (extra / "package_manifest.json").write_bytes(b"{}")

    after = _inventory(canonical_outputs)

    assert before.invalid_count == 0
    assert after.revision_count == before.revision_count + 1
    assert after.unreferenced_revision_count == 1
    assert after.invalid_count == before.invalid_count + 1


@pytest.mark.parametrize(
    ("relative_path", "counter"),
    [
        ("legacy-package-backup", "backup_count"),
        ("rollback-snapshot", "rollback_count"),
        ("orphan-receipt.json", "orphan_receipt_count"),
        ("leftover.tmp", "temporary_file_count"),
    ],
)
def test_named_residue_is_classified(
    tmp_path: Path,
    relative_path: str,
    counter: str,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / relative_path).write_bytes(b"residue")

    assert getattr(_inventory(outputs), counter) == 1


def test_legacy_timestamped_package_and_orphan_transaction_are_counted(
    tmp_path: Path,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(
        outputs / "ShadowPriest-2026-07-28-integrity-audited",
        "ShadowPriest",
    )
    root = outputs / "ShadowPriest"
    publish_configure_run(rendered_runs["ShadowPriest"], root)
    transaction = root / ".publisher" / "transactions" / "orphan.json"
    transaction.write_bytes(b"{}")

    inventory = _inventory(outputs)

    assert inventory.orphan_transaction_count == 1
    assert inventory.invalid_count >= 12


def test_self_declared_finalized_transaction_is_orphan_and_invalid(
    canonical_outputs: Path,
) -> None:
    transaction = (
        canonical_outputs
        / "ShadowPriest"
        / ".publisher"
        / "transactions"
        / f"{'f' * 32}.json"
    )
    transaction.write_text(
        json.dumps({"phase": "finalized"}),
        encoding="utf-8",
    )

    inventory = _inventory(canonical_outputs)

    assert inventory.orphan_transaction_count == 1
    assert inventory.invalid_count == 1


@pytest.mark.parametrize("failure", ["duplicate", "mismatch", "stale"])
def test_finalized_publisher_transaction_must_match_exact_authority(
    canonical_outputs: Path,
    failure: str,
) -> None:
    from hsconfig import output_publisher

    transactions = (
        canonical_outputs / "ShadowPriest" / ".publisher" / "transactions"
    )
    original_path = next(transactions.iterdir())
    original = output_publisher._parse_transaction(original_path.read_bytes())
    transaction_id = "e" * 32
    if transaction_id == original.transaction_id:
        transaction_id = "d" * 32
    changed = replace(
        original,
        transaction_id=transaction_id,
        staging=f"revisions/.staging-{transaction_id}",
    )
    if failure == "mismatch":
        changed = replace(changed, deck_name="CtAPaladin")
    elif failure == "stale":
        changed = replace(
            changed,
            content_root_sha256="0" * 64,
            revision=f"revisions/sha256-{'0' * 64}",
        )
    (transactions / f"{transaction_id}.json").write_bytes(
        output_publisher._transaction_bytes(changed)
    )

    inventory = _inventory(canonical_outputs)

    assert inventory.orphan_transaction_count >= 1
    assert inventory.invalid_count == 1


def test_check_and_cli_preserve_membership_bytes_mtimes_and_identities(
    canonical_outputs: Path,
) -> None:
    before = _tree_snapshot(canonical_outputs)

    inventory = _inventory(canonical_outputs)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "reconcile_outputs.py"),
            "--outputs",
            str(canonical_outputs),
            "--catalog",
            str(CATALOG),
            "--check",
            "--json",
        ],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert inventory.invalid_count == 0
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["current_outputs"] == 12
    assert _tree_snapshot(canonical_outputs) == before


def test_apply_build_failure_does_not_delete_old_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    legacy = outputs / "ShadowPriest-2026-07-28-integrity-audited"
    _write_legacy_root(legacy, "ShadowPriest")
    before = _tree_snapshot(outputs)

    def fail_build(_authority: object) -> dict[str, RenderedConfigureRun]:
        raise ValueError("injected_rebuild_failure")

    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        fail_build,
    )
    approval = _approval_digest(outputs)

    with pytest.raises(ValueError, match="injected_rebuild_failure"):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
        )
    assert _tree_snapshot(outputs) == before


def test_apply_verification_failure_does_not_delete_old_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    outputs = tmp_path / "outputs"
    legacy = outputs / "legacy-shadowpriest"
    _write_legacy_root(legacy, "ShadowPriest")
    before = _tree_snapshot(outputs)
    incomplete = dict(rendered_runs)
    incomplete.pop("CuteWarrior")
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: incomplete,
    )
    approval = _approval_digest(outputs)

    with pytest.raises(ValueError, match="rendered_deck_set_invalid"):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
        )

    assert _tree_snapshot(outputs) == before


def test_empty_root_apply_needs_no_legacy_token_and_leaves_no_sibling_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    outputs = tmp_path / "outputs"
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: dict(rendered_runs),
    )

    inventory = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
    )
    second = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
    )

    assert output_inventory.inventory_is_current(inventory)
    assert second == inventory
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-*"))


def test_successful_apply_retires_exact_legacy_manifest_after_full_verify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    outputs = tmp_path / "outputs"
    obsolete = []
    for index, deck_name in enumerate(rendered_runs):
        root = outputs / f"{deck_name}-2026-07-28-integrity-audited-{index}"
        _write_legacy_root(root, deck_name)
        obsolete.append(root)
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: dict(rendered_runs),
    )
    approval = _approval_digest(outputs)

    inventory = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )
    first_digests = {
        deck: json.loads(
            (outputs / deck / "current.json").read_text(encoding="utf-8")
        )["content_root_sha256"]
        for deck in rendered_runs
    }
    second = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
    )

    assert output_inventory.inventory_is_current(inventory)
    assert second == inventory
    assert all(not path.exists() for path in obsolete)
    assert first_digests == {
        deck: json.loads(
            (outputs / deck / "current.json").read_text(encoding="utf-8")
        )["content_root_sha256"]
        for deck in rendered_runs
    }


def test_apply_accepts_a_direct_legacy_package_at_the_stable_deck_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    outputs = tmp_path / "outputs"
    legacy = outputs / "ShadowPriest"
    _write_legacy_root(legacy, "ShadowPriest")
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: dict(rendered_runs),
    )
    approval = _approval_digest(outputs)

    inventory = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )

    assert output_inventory.inventory_is_current(inventory)
    assert not (outputs / "ShadowPriest" / "04_package").exists()
    assert (outputs / "ShadowPriest" / "current.json").is_file()


def test_unexpected_stable_file_fails_without_deletion(
    tmp_path: Path,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    root = tmp_path / "outputs" / "ShadowPriest"
    publish_configure_run(rendered_runs["ShadowPriest"], root)
    sentinel = root / "unexpected.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected_stable_output_entry"):
        apply_audited_outputs(
            outputs_root=tmp_path / "outputs",
            catalog_path=CATALOG,
        )
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_unexpected_legacy_file_fails_without_deletion(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    legacy = outputs / "legacy-shadowpriest"
    _write_legacy_root(legacy, "ShadowPriest")
    sentinel = legacy / "unexpected.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown_output_root"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_hardlink_in_deletion_candidate_fails_closed(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    legacy = outputs / "legacy-shadowpriest"
    _write_legacy_root(legacy, "ShadowPriest")
    source = legacy / "04_package" / "owned.txt"
    source.write_bytes(b"shared")
    outside = tmp_path / "outside.txt"
    try:
        os.link(source, outside)
    except OSError as error:
        pytest.skip(f"hardlinks unavailable: {error}")

    with pytest.raises(ValueError, match="hardlink"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)
    assert outside.read_bytes() == b"shared"
    assert source.read_bytes() == b"shared"


def test_symlink_deletion_candidate_fails_closed(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel.txt").write_text("keep", encoding="utf-8")
    outputs.mkdir()
    link = outputs / "legacy-shadowpriest"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(ValueError, match="directory_unsafe"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)
    assert (outside / "sentinel.txt").read_text(encoding="utf-8") == "keep"


def test_case_alias_root_fails_closed(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    alias = outputs / "shadowpriest"
    _write_legacy_root(alias, "ShadowPriest")

    with pytest.raises(ValueError, match="case_alias"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)
    assert alias.exists()


def test_manifest_path_traversal_identity_fails_closed(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    legacy = outputs / "legacy-traversal"
    _write_legacy_root(legacy, "../../outside")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown_output_root"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)

    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert legacy.exists()


def test_legacy_apply_requires_an_externally_reviewed_manifest_digest(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    before = _tree_snapshot(outputs)

    proposal = propose_legacy_deletion(
        outputs_root=outputs,
        catalog_path=CATALOG,
    )

    assert proposal.approval_digest.startswith("sha256:")
    assert proposal.manifest_bytes == propose_legacy_deletion(
        outputs_root=outputs,
        catalog_path=CATALOG,
    ).manifest_bytes
    with pytest.raises(ValueError, match="legacy_approval_required"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)
    assert _tree_snapshot(outputs) == before


def test_legacy_approval_digest_is_bound_to_exact_identity_and_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    outputs = tmp_path / "outputs"
    legacy = outputs / "legacy-shadowpriest"
    _write_legacy_root(legacy, "ShadowPriest")
    approval = _approval_digest(outputs)
    manifest = legacy / "04_package" / "reports" / "input_manifest.json"
    manifest.write_text(
        json.dumps({"deck_name": "ShadowPriest", "changed": True}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: dict(rendered_runs),
    )

    with pytest.raises(ValueError, match="legacy_approval_mismatch"):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
        )

    assert manifest.is_file()


def test_legacy_manifest_cli_is_deterministic_and_read_only(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    before = _tree_snapshot(outputs)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "reconcile_outputs.py"),
        "--outputs",
        str(outputs),
        "--catalog",
        str(CATALOG),
        "--propose-legacy-manifest",
        "--json",
    ]

    first = subprocess.run(
        command,
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        command,
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert payload["approval_digest"].startswith("sha256:")
    assert payload["manifest"]["entries"][0]["relative_root"] == (
        "legacy-shadowpriest"
    )
    assert _tree_snapshot(outputs) == before


class _InjectedHardKill(BaseException):
    pass


@pytest.mark.parametrize(
    "fault_stage",
    [
        "before_live_to_previous",
        "after_live_to_previous",
        "before_staged_to_live",
        "after_staged_to_live",
        "after_live_committed",
        "before_previous_cleanup",
        "during_previous_cleanup",
        "before_transaction_cleanup",
    ],
)
def test_root_swap_recovers_every_commit_and_cleanup_fault_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
    fault_stage: str,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: dict(rendered_runs),
    )
    raised = False

    def hard_kill(stage: str) -> None:
        nonlocal raised
        if stage == fault_stage and not raised:
            raised = True
            raise _InjectedHardKill(stage)

    with pytest.raises(_InjectedHardKill, match=fault_stage):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
            fault_hook=hard_kill,
        )

    recovered = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )

    assert output_inventory.inventory_is_current(recovered)
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-*"))


@pytest.mark.parametrize(
    "fault_stage",
    [
        "after_live_to_previous",
        "after_staged_to_live",
        "during_previous_cleanup",
        "before_transaction_cleanup",
    ],
)
def test_root_swap_recovers_after_real_process_hard_kill(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    child = """
import os
import sys
from pathlib import Path
from scripts.reconcile_outputs import apply_audited_outputs

def hard_kill(stage: str) -> None:
    if stage == sys.argv[4]:
        os._exit(73)

apply_audited_outputs(
    outputs_root=Path(sys.argv[1]),
    catalog_path=Path(sys.argv[2]),
    legacy_approval_digest=sys.argv[3],
    fault_hook=hard_kill,
)
"""

    killed = subprocess.run(
        [
            sys.executable,
            "-c",
            child,
            str(outputs),
            str(CATALOG),
            approval,
            fault_stage,
        ],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )

    assert killed.returncode == 73, (killed.stdout, killed.stderr)
    recovered = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )
    assert output_inventory.inventory_is_current(recovered)
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-*"))


def test_prebuild_hard_kill_rolls_back_and_preserves_the_old_root(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    before = _tree_snapshot(outputs)
    approval = _approval_digest(outputs)
    child = """
import os
import sys
from pathlib import Path
from scripts.reconcile_outputs import apply_audited_outputs

def hard_kill(stage: str) -> None:
    if stage == "after_prepare_published":
        os._exit(74)

apply_audited_outputs(
    outputs_root=Path(sys.argv[1]),
    catalog_path=Path(sys.argv[2]),
    legacy_approval_digest=sys.argv[3],
    fault_hook=hard_kill,
)
"""

    killed = subprocess.run(
        [sys.executable, "-c", child, str(outputs), str(CATALOG), approval],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert killed.returncode == 74, (killed.stdout, killed.stderr)
    with pytest.raises(ValueError, match="legacy_approval_required"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)
    assert _tree_snapshot(outputs) == before
    assert (tmp_path / ".hsconfig-output-reconcile-transaction").is_dir()


def test_earliest_hard_kill_leaves_unowned_shell_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    before = _tree_snapshot(outputs)
    approval = _approval_digest(outputs)
    killed = _run_hard_kill_apply(
        outputs,
        approval,
        "after_prepare_directory_create",
        exit_code=75,
    )

    assert killed.returncode == 75, (killed.stdout, killed.stderr)
    assert not (tmp_path / ".hsconfig-output-reconcile-transaction").exists()
    prepare = list(tmp_path.glob(".hsconfig-output-reconcile-prepare-*"))
    assert len(prepare) == 1
    assert not list(prepare[0].iterdir())
    prepare_identity = output_reconciliation.path_identity(prepare[0])
    before_recovery = _inventory(outputs)
    assert before_recovery.orphan_transaction_count == 1
    assert not output_inventory.inventory_is_current(before_recovery)
    assert _tree_snapshot(outputs) == before
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: dict(rendered_runs),
    )

    recovered = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )

    assert recovered == _inventory(outputs)
    assert recovered.current_outputs == 12
    assert recovered.orphan_transaction_count == 1
    assert not output_inventory.inventory_is_current(recovered)
    assert output_reconciliation.path_identity(prepare[0]) == prepare_identity
    assert not list(prepare[0].iterdir())
    after_recovery = _inventory(outputs)
    assert after_recovery.current_outputs == 12
    assert after_recovery.orphan_transaction_count == 1
    assert not output_inventory.inventory_is_current(after_recovery)
    assert not (tmp_path / ".hsconfig-output-reconcile-transaction").exists()
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-cleanup-*"))


def test_journalized_prepare_is_adopted_after_real_process_kill(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    before = _tree_snapshot(outputs)
    approval = _approval_digest(outputs)

    killed = _run_hard_kill_apply(
        outputs,
        approval,
        "before_active_rename",
        exit_code=83,
    )

    assert killed.returncode == 83, (killed.stdout, killed.stderr)
    prepares = list(tmp_path.glob(".hsconfig-output-reconcile-prepare-*"))
    assert len(prepares) == 1
    prepare_identity = output_reconciliation.path_identity(prepares[0])
    prepare_before = _tree_snapshot(prepares[0])
    assert prepare_before
    with pytest.raises(ValueError, match="legacy_approval_required"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)
    assert _tree_snapshot(outputs) == before
    assert output_reconciliation.path_identity(prepares[0]) == prepare_identity
    assert _tree_snapshot(prepares[0]) == prepare_before

    recovered = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )

    assert output_inventory.inventory_is_current(recovered)
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-prepare-*"))
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-transaction"))


def test_prepare_adoption_preserves_all_coordinator_identities_across_kill(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    old_live = _tree_snapshot(outputs)
    approval = _approval_digest(outputs)
    prepared = _run_hard_kill_apply(
        outputs,
        approval,
        "before_active_rename",
        exit_code=89,
    )
    assert prepared.returncode == 89, (prepared.stdout, prepared.stderr)
    prepare = next(tmp_path.glob(".hsconfig-output-reconcile-prepare-*"))
    identities = {
        relative: output_reconciliation.path_identity(prepare / relative)
        for relative in ("journal.ndjson", "lease.lock", "staged")
    }
    transaction_identity = output_reconciliation.path_identity(prepare)

    adopted = _run_hard_kill_apply(
        outputs,
        approval,
        "after_prepare_adopted",
        exit_code=90,
    )

    assert adopted.returncode == 90, (adopted.stdout, adopted.stderr)
    active = tmp_path / ".hsconfig-output-reconcile-transaction"
    assert output_reconciliation.path_identity(active) == transaction_identity
    assert {
        relative: output_reconciliation.path_identity(active / relative)
        for relative in ("journal.ndjson", "lease.lock", "staged")
    } == identities
    assert _tree_snapshot(outputs) == old_live
    recovered = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )
    assert output_inventory.inventory_is_current(recovered)
    assert not active.exists()


@pytest.mark.parametrize(
    "invalid_state",
    [
        "missing_lease",
        "missing_staged",
        "wrong_staged_identity",
        "staged_ready",
        "aborting",
        "aborted",
        "terminal",
    ],
)
def test_invalid_journalized_prepare_fails_closed_before_adoption(
    tmp_path: Path,
    invalid_state: str,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    killed = _run_hard_kill_apply(
        outputs,
        approval,
        "before_active_rename",
        exit_code=85,
    )
    assert killed.returncode == 85, (killed.stdout, killed.stderr)
    prepare = next(tmp_path.glob(".hsconfig-output-reconcile-prepare-*"))
    state, journal = output_reconciliation._load_root_transaction(
        prepare,
        expected_outputs_name=outputs.name,
    )
    if invalid_state == "missing_lease":
        (prepare / "lease.lock").unlink()
    elif invalid_state == "missing_staged":
        (prepare / "staged").rmdir()
    elif invalid_state == "wrong_staged_identity":
        (prepare / "staged").rmdir()
        (prepare / "staged").mkdir()
    else:
        phases = {
            "staged_ready": ["staged_ready"],
            "aborting": ["aborting"],
            "aborted": ["aborting", "aborted"],
            "terminal": [
                "staged_ready",
                "previous_moved",
                "live_committed",
                "terminal",
            ],
        }[invalid_state]
        for phase in phases:
            transaction = state.transaction
            if phase == "previous_moved":
                transaction = replace(
                    transaction,
                    previous_identity=transaction.live_identity,
                    phase=phase,
                )
            else:
                transaction = replace(transaction, phase=phase)
            state = output_reconciliation._append_root_transition(
                journal,
                state,
                transaction,
                fault_hook=lambda _stage: None,
            )
    prepare_identity = output_reconciliation.path_identity(prepare)
    prepare_before = _tree_snapshot(prepare)
    outputs_before = _tree_snapshot(outputs)

    with pytest.raises(ValueError, match="reconcile_prepare_invalid"):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
        )

    assert output_reconciliation.path_identity(prepare) == prepare_identity
    assert _tree_snapshot(prepare) == prepare_before
    assert _tree_snapshot(outputs) == outputs_before
    assert not (tmp_path / ".hsconfig-output-reconcile-transaction").exists()


def test_multiple_journalized_prepares_fail_closed_unchanged(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    killed = _run_hard_kill_apply(
        outputs,
        approval,
        "before_active_rename",
        exit_code=86,
    )
    assert killed.returncode == 86, (killed.stdout, killed.stderr)
    first = next(tmp_path.glob(".hsconfig-output-reconcile-prepare-*"))
    second = tmp_path / (".hsconfig-output-reconcile-prepare-" + "9" * 32)
    shutil.copytree(first, second)
    identities = [output_reconciliation.path_identity(path) for path in (first, second)]
    before = [_tree_snapshot(path) for path in (first, second)]
    outputs_before = _tree_snapshot(outputs)

    with pytest.raises(ValueError, match="reconcile_prepare_multiple"):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
        )

    assert [output_reconciliation.path_identity(path) for path in (first, second)] == identities
    assert [_tree_snapshot(path) for path in (first, second)] == before
    assert _tree_snapshot(outputs) == outputs_before


def test_prepare_adoption_revalidates_approved_live_manifest_before_rename(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    killed = _run_hard_kill_apply(
        outputs,
        approval,
        "before_active_rename",
        exit_code=87,
    )
    assert killed.returncode == 87, (killed.stdout, killed.stderr)
    prepare = next(tmp_path.glob(".hsconfig-output-reconcile-prepare-*"))
    manifest = (
        outputs
        / "legacy-shadowpriest"
        / "04_package"
        / "reports"
        / "input_manifest.json"
    )
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    prepare_identity = output_reconciliation.path_identity(prepare)
    prepare_before = _tree_snapshot(prepare)

    with pytest.raises(ValueError, match="reconcile_deletion_identity_changed"):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
        )

    assert output_reconciliation.path_identity(prepare) == prepare_identity
    assert _tree_snapshot(prepare) == prepare_before
    assert not (tmp_path / ".hsconfig-output-reconcile-transaction").exists()


def test_parent_swap_before_first_election_open_creates_no_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outputs = workspace / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    moved = tmp_path / "workspace-moved"
    original_enter = output_reconciliation.ExclusiveFileLock.__enter__
    swapped = False

    def swap_before_enter(lock: Any) -> Any:
        nonlocal swapped
        if lock.path.name == ".hsconfig-output-reconcile.lock" and not swapped:
            swapped = True
            os.replace(workspace, moved)
            workspace.mkdir()
        return original_enter(lock)

    monkeypatch.setattr(
        output_reconciliation.ExclusiveFileLock,
        "__enter__",
        swap_before_enter,
    )

    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)

    assert swapped
    assert not (workspace / ".hsconfig-output-reconcile.lock").exists()
    assert not (moved / ".hsconfig-output-reconcile.lock").exists()
    assert (moved / "outputs" / "legacy-shadowpriest").is_dir()


@pytest.mark.parametrize("attack", ["directory_swap", "lease_removed"])
def test_prepare_lease_open_never_creates_in_substituted_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    killed = _run_hard_kill_apply(
        outputs,
        approval,
        "before_active_rename",
        exit_code=88,
    )
    assert killed.returncode == 88, (killed.stdout, killed.stderr)
    prepare = next(tmp_path.glob(".hsconfig-output-reconcile-prepare-*"))
    moved = tmp_path / "attacker-moved-prepare"
    prepare_before = _tree_snapshot(prepare)
    outputs_before = _tree_snapshot(outputs)
    original_enter = output_reconciliation.ExclusiveFileLock.__enter__
    attacked = False

    def attack_before_enter(lock: Any) -> Any:
        nonlocal attacked
        if lock.path == prepare / "lease.lock" and not attacked:
            attacked = True
            if attack == "directory_swap":
                os.replace(prepare, moved)
                prepare.mkdir()
            else:
                (prepare / "lease.lock").unlink()
        return original_enter(lock)

    monkeypatch.setattr(
        output_reconciliation.ExclusiveFileLock,
        "__enter__",
        attack_before_enter,
    )

    with pytest.raises((FileNotFoundError, ValueError)):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
        )

    assert attacked
    assert _tree_snapshot(outputs) == outputs_before
    if attack == "directory_swap":
        assert _tree_snapshot(moved) == prepare_before
        assert not (prepare / "lease.lock").exists()
        assert not list(prepare.iterdir())
    else:
        expected = dict(prepare_before)
        expected.pop("lease.lock")
        assert _tree_snapshot(prepare) == expected
        assert not (prepare / "lease.lock").exists()
    assert not (tmp_path / ".hsconfig-output-reconcile-transaction").exists()


def test_active_recovery_never_recreates_a_removed_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    killed = _run_hard_kill_apply(
        outputs,
        approval,
        "after_prepare_published",
        exit_code=91,
    )
    assert killed.returncode == 91, (killed.stdout, killed.stderr)
    active = tmp_path / ".hsconfig-output-reconcile-transaction"
    active_identity = output_reconciliation.path_identity(active)
    active_before = _tree_snapshot(active)
    outputs_before = _tree_snapshot(outputs)
    original_enter = output_reconciliation.ExclusiveFileLock.__enter__
    attacked = False

    def remove_before_enter(lock: Any) -> Any:
        nonlocal attacked
        if lock.path == active / "lease.lock" and not attacked:
            attacked = True
            (active / "lease.lock").unlink()
        return original_enter(lock)

    monkeypatch.setattr(
        output_reconciliation.ExclusiveFileLock,
        "__enter__",
        remove_before_enter,
    )
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: pytest.fail(
            "active recovery continued after recreating a removed lease"
        ),
    )

    with pytest.raises(FileNotFoundError):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
        )

    assert attacked
    expected_active = dict(active_before)
    expected_active.pop("lease.lock")
    assert output_reconciliation.path_identity(active) == active_identity
    assert _tree_snapshot(active) == expected_active
    assert _tree_snapshot(outputs) == outputs_before


def test_root_swap_parent_identity_change_fails_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outputs = workspace / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    moved = tmp_path / "workspace-moved"
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: dict(rendered_runs),
    )

    def swap_parent(stage: str) -> None:
        if stage == "before_live_to_previous":
            try:
                os.replace(workspace, moved)
            except PermissionError as error:
                raise ValueError(
                    "filesystem_path_identity_changed_by_open_handle"
                ) from error
            workspace.mkdir()

    with pytest.raises(ValueError, match="identity_changed"):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
            fault_hook=swap_parent,
        )

    preserved = moved if moved.exists() else workspace
    assert (preserved / "outputs" / "legacy-shadowpriest").is_dir()


def test_root_swap_rejects_an_ancestor_reparse_alias(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")
    outputs = alias / "outputs"

    with pytest.raises(ValueError):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)

    assert alias.is_symlink()
    assert list(real.iterdir()) == []


def test_noop_apply_rejects_an_ancestor_reparse_alias(
    canonical_outputs: Path,
) -> None:
    alias = canonical_outputs.parent / "alias"
    try:
        alias.symlink_to(canonical_outputs.parent, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    before = _tree_snapshot(canonical_outputs)
    with pytest.raises(ValueError):
        apply_audited_outputs(
            outputs_root=alias / canonical_outputs.name,
            catalog_path=CATALOG,
        )

    assert alias.is_symlink()
    assert _tree_snapshot(canonical_outputs) == before


def test_child_identity_substitution_during_previous_cleanup_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: dict(rendered_runs),
    )
    replaced = False

    def substitute(stage: str) -> None:
        nonlocal replaced
        if stage == "before_previous_cleanup" and not replaced:
            replaced = True
            manifest = (
                tmp_path
                / ".hsconfig-output-reconcile-transaction"
                / "previous"
                / "legacy-shadowpriest"
                / "04_package"
                / "reports"
                / "input_manifest.json"
            )
            manifest.unlink()
            manifest.write_text("foreign", encoding="utf-8")

    with pytest.raises(ValueError, match="identity_changed"):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
            fault_hook=substitute,
        )

    assert _inventory(outputs).current_outputs == 12
    assert (
        tmp_path
        / ".hsconfig-output-reconcile-transaction"
        / "previous"
        / "legacy-shadowpriest"
        / "04_package"
        / "reports"
        / "input_manifest.json"
    ).read_text(encoding="utf-8") == "foreign"


def test_forged_reconcile_transaction_is_left_untouched(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    transaction = tmp_path / ".hsconfig-output-reconcile-transaction"
    transaction.mkdir()
    sentinel = transaction / "foreign.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="reconcile_transaction"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)

    assert sentinel.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("substitution", ["hardlink", "reparse"])
def test_forged_transaction_journal_substitutions_are_left_untouched(
    tmp_path: Path,
    substitution: str,
) -> None:
    outputs = tmp_path / "outputs"
    transaction = tmp_path / ".hsconfig-output-reconcile-transaction"
    transaction.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("foreign", encoding="utf-8")
    journal = transaction / "journal.ndjson"
    try:
        if substitution == "hardlink":
            os.link(outside, journal)
        else:
            journal.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"{substitution} unavailable: {error}")

    with pytest.raises(ValueError, match="filesystem_file_invalid"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)

    assert outside.read_text(encoding="utf-8") == "foreign"
    assert journal.exists()


def test_active_reconcile_lock_is_never_cleaned_by_a_competitor(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    before = _tree_snapshot(outputs)
    approval = _approval_digest(outputs)
    marker = tmp_path / "locked.marker"
    child = """
import sys
import time
from pathlib import Path
from scripts.reconcile_outputs import apply_audited_outputs

marker = Path(sys.argv[4])
def hold(stage: str) -> None:
    if stage == "after_active_lease_acquired":
        marker.write_text("locked", encoding="utf-8")
        time.sleep(30)

apply_audited_outputs(
    outputs_root=Path(sys.argv[1]),
    catalog_path=Path(sys.argv[2]),
    legacy_approval_digest=sys.argv[3],
    fault_hook=hold,
)
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child,
            str(outputs),
            str(CATALOG),
            approval,
            str(marker),
        ],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
    )
    try:
        for _ in range(200):
            if marker.is_file():
                break
            if process.poll() is not None:
                pytest.fail(f"lock holder exited early: {process.returncode}")
            time.sleep(0.05)
        assert marker.is_file()
        with pytest.raises(ValueError, match="reconcile_election_active"):
            apply_audited_outputs(
                outputs_root=outputs,
                catalog_path=CATALOG,
                legacy_approval_digest=approval,
            )
        assert (
            tmp_path / ".hsconfig-output-reconcile-transaction"
        ).is_dir()
    finally:
        process.terminate()
        process.wait(timeout=30)

    with pytest.raises(ValueError, match="legacy_approval_required"):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)
    assert _tree_snapshot(outputs) == before
    assert (tmp_path / ".hsconfig-output-reconcile-transaction").is_dir()
    recovered = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )
    assert output_inventory.inventory_is_current(recovered)
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-*"))


def test_concurrent_identity_replacement_is_not_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    outputs = tmp_path / "outputs"
    legacy = outputs / "legacy-shadowpriest"
    _write_legacy_root(legacy, "ShadowPriest")

    def replace_during_build(
        _authority: object,
    ) -> dict[str, RenderedConfigureRun]:
        shutil.rmtree(legacy)
        legacy.mkdir()
        (legacy / "concurrent.txt").write_text("keep", encoding="utf-8")
        return dict(rendered_runs)

    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        replace_during_build,
    )
    approval = _approval_digest(outputs)

    with pytest.raises(ValueError, match="changed"):
        apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
        )
    assert (legacy / "concurrent.txt").read_text(encoding="utf-8") == "keep"


def test_generated_outputs_are_ignored_and_no_backup_behavior_exists() -> None:
    completed = subprocess.run(
        [
            "git",
            "check-ignore",
            "outputs/probe",
            "tmp/probe",
            ".hsconfig-output-reconcile-transaction/probe",
            ".hsconfig-output-reconcile-prepare-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/probe",
            ".hsconfig-output-reconcile-cleanup-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/probe",
            ".hsconfig-output-reconcile.lock",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.splitlines() == [
        "outputs/probe",
        "tmp/probe",
        ".hsconfig-output-reconcile-transaction/probe",
        ".hsconfig-output-reconcile-prepare-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/probe",
        ".hsconfig-output-reconcile-cleanup-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/probe",
        ".hsconfig-output-reconcile.lock",
    ]


def test_parent_election_lock_is_persistent_plain_and_scanner_invisible(
    canonical_outputs: Path,
) -> None:
    parent = canonical_outputs.parent
    first = apply_audited_outputs(
        outputs_root=canonical_outputs,
        catalog_path=CATALOG,
    )
    election = parent / ".hsconfig-output-reconcile.lock"
    status = election.lstat()
    identity = output_reconciliation.path_identity(election)

    second = apply_audited_outputs(
        outputs_root=canonical_outputs,
        catalog_path=CATALOG,
    )

    assert status.st_nlink == 1
    assert output_reconciliation.path_identity(election) == identity
    assert first == second == _inventory(canonical_outputs)
    assert output_inventory.inventory_is_current(second)


def test_production_modules_own_inventory_and_reconciliation_interfaces() -> None:
    assert output_inventory.OutputInventory is OutputInventory
    assert (
        output_reconciliation.apply_audited_outputs
        is apply_audited_outputs
    )


def test_public_inventory_classifies_every_exact_sibling_coordinator_state(
    tmp_path: Path,
) -> None:
    for name in (
        ".hsconfig-output-reconcile-transaction",
        ".hsconfig-output-reconcile-prepare-" + "a" * 32,
        ".hsconfig-output-reconcile-cleanup-" + "b" * 32,
        ".hsconfig-output-reconcile-foreign",
    ):
        (tmp_path / name).mkdir()

    inventory = _inventory(tmp_path / "outputs")

    assert inventory.orphan_transaction_count == 4
    assert inventory.invalid_count == 17


@pytest.mark.parametrize(
    "fault_stage",
    [
        "after_staged_to_live",
        "after_live_committed",
        "during_previous_cleanup",
        "before_transaction_cleanup",
    ],
)
def test_public_check_is_noncanonical_through_every_commit_cleanup_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
    fault_stage: str,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: dict(rendered_runs),
    )
    observed = []

    def inspect_then_stop(stage: str) -> None:
        if stage == fault_stage and not observed:
            inventory = _inventory(outputs)
            observed.append(inventory)
            raise _InjectedHardKill(stage)

    with pytest.raises(_InjectedHardKill, match=fault_stage):
        output_reconciliation.apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
            legacy_approval_digest=approval,
            fault_hook=inspect_then_stop,
        )

    assert observed
    assert not output_inventory.inventory_is_current(observed[0])
    assert observed[0].orphan_transaction_count >= 1


@pytest.mark.parametrize(
    "transition",
    ["staged_ready", "previous_moved", "live_committed", "terminal"],
)
@pytest.mark.parametrize("writer_phase", ["before", "during", "after"])
def test_hash_chain_journal_recovers_real_process_kill_at_every_writer_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transition: str,
    writer_phase: str,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    fault_stage = f"{writer_phase}_journal_{transition}_append"

    killed = _run_hard_kill_apply(outputs, approval, fault_stage)

    assert killed.returncode == 76, (killed.stdout, killed.stderr)
    sibling_before = _tree_snapshot(tmp_path)
    with pytest.raises(ValueError, match="legacy_approval_required"):
        output_reconciliation.apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
        )
    assert _tree_snapshot(tmp_path) == sibling_before

    if transition == "staged_ready":
        monkeypatch.setattr(
            output_reconciliation,
            "_build_rendered_audited_runs",
            lambda _authority: pytest.fail(
                "staged-ready recovery rebuilt instead of resuming"
            ),
        )
    recovered = output_reconciliation.apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )
    assert output_inventory.inventory_is_current(recovered)
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-*"))


def test_cleanup_tombstone_is_recovered_after_real_process_kill(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)

    killed = _run_hard_kill_apply(
        outputs,
        approval,
        "after_cleanup_tombstone_publish",
        exit_code=78,
    )

    assert killed.returncode == 78, (killed.stdout, killed.stderr)
    tombstones = list(tmp_path.glob(".hsconfig-output-reconcile-cleanup-*"))
    assert len(tombstones) == 1
    assert not output_inventory.inventory_is_current(_inventory(outputs))
    with pytest.raises(ValueError, match="legacy_approval_required"):
        output_reconciliation.apply_audited_outputs(
            outputs_root=outputs,
            catalog_path=CATALOG,
        )
    recovered = output_reconciliation.apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )
    assert output_inventory.inventory_is_current(recovered)
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-*"))


def _minimal_journal_state(tmp_path: Path) -> tuple[Path, Any]:
    coordinator = tmp_path / ".hsconfig-output-reconcile-transaction"
    coordinator.mkdir()
    staged = coordinator / "staged"
    staged.mkdir()
    journal = coordinator / "journal.ndjson"
    parent_identity = output_reconciliation.path_identity(tmp_path)
    coordinator_identity = output_reconciliation.path_identity(coordinator)
    journal_identity = output_reconciliation._create_empty_journal(
        journal,
        expected_parent_identity=coordinator_identity,
    )
    transaction = output_reconciliation._RootTransaction(
        transaction_id="c" * 32,
        outputs_name="outputs",
        parent_identity=parent_identity,
        transaction_identity=coordinator_identity,
        journal_identity=journal_identity,
        live_identity=None,
        staged_identity=output_reconciliation.path_identity(staged),
        previous_identity=None,
        approval_digest=None,
        legacy_manifest={},
        phase="building",
    )
    state = output_reconciliation._append_root_transition(
        journal,
        None,
        transaction,
        fault_hook=lambda _stage: None,
    )
    return journal, state


def test_direct_building_to_aborted_transition_is_rejected_unchanged(
    tmp_path: Path,
) -> None:
    journal, state = _minimal_journal_state(tmp_path)
    before = journal.read_bytes()

    with pytest.raises(ValueError, match="reconcile_transaction_phase_invalid"):
        output_reconciliation._append_root_transition(
            journal,
            state,
            replace(state.transaction, phase="aborted"),
            fault_hook=lambda _stage: None,
        )

    assert journal.read_bytes() == before


def test_recovery_append_truncates_one_partial_terminal_tail(
    tmp_path: Path,
) -> None:
    journal, state = _minimal_journal_state(tmp_path)
    with journal.open("ab") as handle:
        handle.write(b'{"partial":')
        handle.flush()
        os.fsync(handle.fileno())

    advanced = output_reconciliation._append_root_transition(
        journal,
        state,
        replace(state.transaction, phase="staged_ready"),
        fault_hook=lambda _stage: None,
    )

    parsed = output_reconciliation._parse_root_journal(journal.read_bytes())
    assert parsed == advanced
    assert not parsed.has_partial_tail


@pytest.mark.parametrize(
    "corruption",
    ["complete_record", "hash_chain", "overflow"],
)
def test_invalid_journal_is_rejected_without_mutation(
    tmp_path: Path,
    corruption: str,
) -> None:
    journal, _state = _minimal_journal_state(tmp_path)
    raw = journal.read_bytes()
    if corruption == "complete_record":
        damaged = raw + b"{}\n"
    elif corruption == "hash_chain":
        payload = json.loads(raw.decode("utf-8"))
        payload["previous_record_sha256"] = "sha256:" + "f" * 64
        damaged = (
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
            + b"\n"
        )
    else:
        damaged = raw + b"x" * (
            output_reconciliation._ROOT_JOURNAL_RECORD_LIMIT + 1
        )
    journal.write_bytes(damaged)
    before = journal.read_bytes()

    with pytest.raises(ValueError, match="reconcile_transaction"):
        output_reconciliation._parse_root_journal(before)

    assert journal.read_bytes() == before


def test_apply_return_and_cli_exit_match_immediate_public_check_with_residue(
    canonical_outputs: Path,
) -> None:
    cleanup = (
        canonical_outputs.parent
        / (".hsconfig-output-reconcile-cleanup-" + "d" * 32)
    )
    cleanup.mkdir()

    returned = apply_audited_outputs(
        outputs_root=canonical_outputs,
        catalog_path=CATALOG,
    )
    checked = _inventory(canonical_outputs)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "reconcile_outputs.py"),
            "--outputs",
            str(canonical_outputs),
            "--catalog",
            str(CATALOG),
            "--apply",
            "--json",
        ],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert returned == checked
    assert returned.current_outputs == 12
    assert returned.orphan_transaction_count == 1
    assert not output_inventory.inventory_is_current(returned)
    assert completed.returncode == 1, completed.stderr
    assert json.loads(completed.stdout) == asdict(checked)


@pytest.mark.parametrize(
    "fault_stage",
    [
        "after_cleanup_tombstone_lease_unlink",
        "after_cleanup_tombstone_journal_unlink",
        "before_cleanup_tombstone_rmdir",
        "after_cleanup_tombstone_rmdir",
    ],
)
def test_cleanup_tombstone_recovers_every_real_process_retirement_kill(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)

    killed = _run_hard_kill_apply(
        outputs,
        approval,
        fault_stage,
        exit_code=81,
    )

    assert killed.returncode == 81, (killed.stdout, killed.stderr)
    recovered = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )
    checked = _inventory(outputs)
    assert recovered == checked
    assert recovered.current_outputs == 12
    if fault_stage in {
        "after_cleanup_tombstone_journal_unlink",
        "before_cleanup_tombstone_rmdir",
    }:
        assert recovered.orphan_transaction_count == 1
        assert not output_inventory.inventory_is_current(recovered)
        cleanup = list(tmp_path.glob(".hsconfig-output-reconcile-cleanup-*"))
        assert len(cleanup) == 1
        assert not list(cleanup[0].iterdir())
    else:
        assert output_inventory.inventory_is_current(recovered)
        assert not list(tmp_path.glob(".hsconfig-output-reconcile-cleanup-*"))


def test_parent_election_serializes_concurrent_cleanup_recovery(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    killed = _run_hard_kill_apply(
        outputs,
        approval,
        "after_cleanup_tombstone_publish",
        exit_code=84,
    )
    assert killed.returncode == 84, (killed.stdout, killed.stderr)
    tombstones = list(tmp_path.glob(".hsconfig-output-reconcile-cleanup-*"))
    assert len(tombstones) == 1
    tombstone_before = _tree_snapshot(tombstones[0])
    marker = tmp_path / "cleanup-election.marker"
    owner = """
import sys
import time
from pathlib import Path
from hsconfig.output_reconciliation import apply_audited_outputs

marker = Path(sys.argv[4])
def hold(stage: str) -> None:
    if stage == "after_election_acquired":
        marker.write_text("held", encoding="utf-8")
        time.sleep(30)

apply_audited_outputs(
    outputs_root=Path(sys.argv[1]),
    catalog_path=Path(sys.argv[2]),
    legacy_approval_digest=sys.argv[3],
    fault_hook=hold,
)
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            owner,
            str(outputs),
            str(CATALOG),
            approval,
            str(marker),
        ],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
    )
    try:
        for _ in range(400):
            if marker.is_file():
                break
            if process.poll() is not None:
                pytest.fail(f"cleanup recovery owner exited early: {process.returncode}")
            time.sleep(0.05)
        assert marker.is_file()
        with pytest.raises(ValueError, match="reconcile_election_active"):
            apply_audited_outputs(
                outputs_root=outputs,
                catalog_path=CATALOG,
                legacy_approval_digest=approval,
            )
        assert _tree_snapshot(tombstones[0]) == tombstone_before
    finally:
        process.terminate()
        process.wait(timeout=30)

    recovered = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )
    assert output_inventory.inventory_is_current(recovered)
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-cleanup-*"))


def test_empty_cleanup_diagnostic_does_not_block_new_active_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: Mapping[str, RenderedConfigureRun],
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    cleanup = tmp_path / (".hsconfig-output-reconcile-cleanup-" + "e" * 32)
    cleanup.mkdir()
    cleanup_identity = output_reconciliation.path_identity(cleanup)
    monkeypatch.setattr(
        output_reconciliation,
        "_build_rendered_audited_runs",
        lambda _authority: dict(rendered_runs),
    )

    returned = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )

    assert returned == _inventory(outputs)
    assert returned.current_outputs == 12
    assert returned.orphan_transaction_count == 1
    assert output_reconciliation.path_identity(cleanup) == cleanup_identity
    assert not list(cleanup.iterdir())
    assert not (tmp_path / ".hsconfig-output-reconcile-transaction").exists()


def test_multiple_empty_cleanup_diagnostics_are_nonblocking_and_public(
    canonical_outputs: Path,
) -> None:
    parent = canonical_outputs.parent
    cleanups = [
        parent / (".hsconfig-output-reconcile-cleanup-" + value * 32)
        for value in ("1", "2")
    ]
    for cleanup in cleanups:
        cleanup.mkdir()
    identities = [output_reconciliation.path_identity(path) for path in cleanups]

    returned = apply_audited_outputs(
        outputs_root=canonical_outputs,
        catalog_path=CATALOG,
    )

    assert returned == _inventory(canonical_outputs)
    assert returned.current_outputs == 12
    assert returned.orphan_transaction_count == 2
    assert not output_inventory.inventory_is_current(returned)
    assert [output_reconciliation.path_identity(path) for path in cleanups] == identities


def test_multiple_empty_prepare_diagnostics_are_nonblocking_and_public(
    canonical_outputs: Path,
) -> None:
    parent = canonical_outputs.parent
    prepares = [
        parent / (".hsconfig-output-reconcile-prepare-" + value * 32)
        for value in ("3", "4")
    ]
    for prepare in prepares:
        prepare.mkdir()
    identities = [output_reconciliation.path_identity(path) for path in prepares]

    returned = apply_audited_outputs(
        outputs_root=canonical_outputs,
        catalog_path=CATALOG,
    )

    assert returned == _inventory(canonical_outputs)
    assert returned.current_outputs == 12
    assert returned.orphan_transaction_count == 2
    assert not output_inventory.inventory_is_current(returned)
    assert [output_reconciliation.path_identity(path) for path in prepares] == identities
    assert all(not list(path.iterdir()) for path in prepares)


@pytest.mark.parametrize("residue_kind", ["sentinel", "hardlink", "reparse"])
def test_journal_less_nonempty_cleanup_fails_closed_unchanged(
    tmp_path: Path,
    residue_kind: str,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    cleanup = tmp_path / (".hsconfig-output-reconcile-cleanup-" + "f" * 32)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"do-not-touch")
    if residue_kind == "reparse":
        outside_directory = tmp_path / "outside-directory"
        outside_directory.mkdir()
        (outside_directory / "sentinel").write_bytes(b"do-not-touch")
        try:
            cleanup.symlink_to(outside_directory, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"symlinks unavailable: {error}")
        expected_error = None
        residue_before = _tree_snapshot(outside_directory)
    else:
        cleanup.mkdir()
        residue = cleanup / ("lease.lock" if residue_kind == "hardlink" else "sentinel")
        if residue_kind == "hardlink":
            try:
                os.link(outside, residue)
            except OSError as error:
                pytest.skip(f"hardlinks unavailable: {error}")
        else:
            residue.write_bytes(b"do-not-touch")
        expected_error = "reconcile_cleanup_residue"
        residue_before = _tree_snapshot(cleanup)
    cleanup_identity = cleanup.lstat()
    outputs_before = _tree_snapshot(outputs)

    with pytest.raises(ValueError, match=expected_error):
        apply_audited_outputs(outputs_root=outputs, catalog_path=CATALOG)

    cleanup_after = cleanup.lstat()
    assert (
        cleanup_after.st_dev,
        cleanup_after.st_ino,
        cleanup_after.st_mode,
    ) == (
        cleanup_identity.st_dev,
        cleanup_identity.st_ino,
        cleanup_identity.st_mode,
    )
    assert outside.read_bytes() == b"do-not-touch"
    assert _tree_snapshot(outputs) == outputs_before
    if residue_kind == "reparse":
        assert _tree_snapshot(outside_directory) == residue_before
    else:
        assert _tree_snapshot(cleanup) == residue_before


@pytest.mark.parametrize(
    "fault_stage",
    [
        "before_prepare_directory_create",
        "before_active_rename",
        "after_prepare_published",
    ],
)
def test_parent_election_serializes_two_real_apply_processes(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    approval = _approval_digest(outputs)
    marker = tmp_path / "election.marker"
    owner = """
import sys
import time
from pathlib import Path
from hsconfig.output_reconciliation import apply_audited_outputs

marker = Path(sys.argv[4])
def hold(stage: str) -> None:
    if stage == sys.argv[5]:
        marker.write_text("held", encoding="utf-8")
        time.sleep(30)

apply_audited_outputs(
    outputs_root=Path(sys.argv[1]),
    catalog_path=Path(sys.argv[2]),
    legacy_approval_digest=sys.argv[3],
    fault_hook=hold,
)
"""
    contender = """
import sys
from pathlib import Path
from hsconfig.output_reconciliation import apply_audited_outputs

try:
    apply_audited_outputs(
        outputs_root=Path(sys.argv[1]),
        catalog_path=Path(sys.argv[2]),
        legacy_approval_digest=sys.argv[3],
    )
except ValueError as error:
    print(str(error))
    raise SystemExit(79)
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            owner,
            str(outputs),
            str(CATALOG),
            approval,
            str(marker),
            fault_stage,
        ],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
    )
    try:
        for _ in range(400):
            if marker.is_file():
                break
            if process.poll() is not None:
                pytest.fail(f"election owner exited early: {process.returncode}")
            time.sleep(0.05)
        assert marker.is_file()
        before_contender = _tree_identity_snapshot(tmp_path)
        outputs_before_contender = _tree_snapshot(outputs)
        competed = subprocess.run(
            [
                sys.executable,
                "-c",
                contender,
                str(outputs),
                str(CATALOG),
                approval,
            ],
            cwd=ROOT,
            env=controlled_python_environment(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert competed.returncode == 79, (competed.stdout, competed.stderr)
        assert "reconcile_election_active" in competed.stdout
        assert _tree_identity_snapshot(tmp_path) == before_contender
        assert _tree_snapshot(outputs) == outputs_before_contender
        prepares = list(tmp_path.glob(".hsconfig-output-reconcile-prepare-*"))
        assert len(prepares) <= (0 if fault_stage == "after_prepare_published" else 1)
    finally:
        process.terminate()
        process.wait(timeout=30)

    recovered = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )
    assert output_inventory.inventory_is_current(recovered)
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-transaction"))


def _run_abort_hard_kill_apply(
    outputs: Path,
    approval: str,
    fault_stage: str,
) -> subprocess.CompletedProcess[str]:
    child = """
import os
import sys
from pathlib import Path
import hsconfig.output_reconciliation as reconciliation

original_publish = reconciliation.publish_configure_run
published = 0

def publish_one_then_fail(rendered, target):
    global published
    original_publish(rendered, target)
    published += 1
    if published == 1:
        raise RuntimeError("injected_partial_build_failure")

def fail_then_kill(stage: str) -> None:
    if stage == sys.argv[4]:
        os._exit(82)

reconciliation.publish_configure_run = publish_one_then_fail
reconciliation.apply_audited_outputs(
    outputs_root=Path(sys.argv[1]),
    catalog_path=Path(sys.argv[2]),
    legacy_approval_digest=sys.argv[3],
    fault_hook=fail_then_kill,
)
"""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            child,
            str(outputs),
            str(CATALOG),
            approval,
            fault_stage,
        ],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


@pytest.mark.parametrize(
    "fault_stage",
    [
        "during_abort_staging_cleanup",
        "after_abort_staging_rmdir",
        "before_journal_aborting_append",
        "during_journal_aborting_append",
        "after_journal_aborting_append",
        "before_journal_aborted_append",
        "during_journal_aborted_append",
        "after_journal_aborted_append",
    ],
)
def test_abort_transitions_recover_every_real_process_kill(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    outputs = tmp_path / "outputs"
    _write_legacy_root(outputs / "legacy-shadowpriest", "ShadowPriest")
    old_root = _tree_snapshot(outputs)
    approval = _approval_digest(outputs)

    killed = _run_abort_hard_kill_apply(outputs, approval, fault_stage)

    assert killed.returncode == 82, (killed.stdout, killed.stderr)
    assert _tree_snapshot(outputs) == old_root
    coordinator = output_reconciliation._locate_root_coordinator(tmp_path)
    assert coordinator is not None
    killed_state, _ = output_reconciliation._load_root_transaction(
        coordinator,
        expected_outputs_name=outputs.name,
    )
    expected_phase = {
        "before_journal_aborting_append": "building",
        "during_journal_aborting_append": "building",
        "after_journal_aborting_append": "aborting",
        "during_abort_staging_cleanup": "aborting",
        "after_abort_staging_rmdir": "aborting",
        "before_journal_aborted_append": "aborting",
        "during_journal_aborted_append": "aborting",
        "after_journal_aborted_append": "aborted",
    }[fault_stage]
    assert killed_state.transaction.phase == expected_phase
    recovered = apply_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
        legacy_approval_digest=approval,
    )
    assert recovered == _inventory(outputs)
    assert output_inventory.inventory_is_current(recovered)
    assert not list(tmp_path.glob(".hsconfig-output-reconcile-transaction"))
