from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from hsconfig.cli import main
from hsconfig.cli_parser import build_parser
from hsconfig.commands.apply import apply_payload as real_apply_payload
from hsconfig.configure_workflow import _execute_configure_namespace
from hsconfig.current_output import resolve_current_package
from hsconfig.output_publisher import publish_configure_run
from tests.test_output_publisher import build_rendered_run


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _disable_remote_card_fetches(monkeypatch: object) -> None:
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


def _configure_args(output_root: Path, runtime_root: Path) -> list[str]:
    return [
        "configure",
        "--deck-name",
        "ShadowPriest",
        "--deck-code",
        SHADOWPRIEST_CODE,
        "--runtime-root",
        str(runtime_root),
        "--out",
        str(output_root),
        "--json",
    ]


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _walk_json(value: object):
    yield value
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_json(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def test_successful_configure_publishes_one_resolved_current_package(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _disable_remote_card_fetches(monkeypatch)
    output_root = tmp_path / "outputs" / "ShadowPriest"

    assert main(
        _configure_args(output_root, tmp_path / "runtime")
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    package_root = resolve_current_package(output_root)
    revision_root = package_root.parent
    assert set(path.name for path in output_root.iterdir()) == {
        ".publish.lock",
        ".publisher",
        "current.json",
        "revisions",
    }
    assert payload["output_root"] == str(output_root)
    assert payload["package_path"] == str(package_root)
    assert payload["published_revision"] == (
        revision_root.relative_to(output_root).as_posix()
    )
    assert payload["published_package"] == (
        package_root.relative_to(output_root).as_posix()
    )
    assert payload["publication_content_root_sha256"] == (
        revision_root.name.removeprefix("sha256-")
    )
    assert payload["reused_existing_revision"] is False
    persisted_summary = json.loads(
        (revision_root / "configure_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert not {
        "output_root",
        "package_path",
        "published_revision",
        "published_package",
        "publication_content_root_sha256",
        "reused_existing_revision",
    } & set(persisted_summary)
    forbidden_keys = {
        "output_root",
        "package_path",
        "published_revision",
        "published_package",
        "publication_content_root_sha256",
        "reused_existing_revision",
        "apply_receipt",
    }
    for value in _walk_json(persisted_summary):
        if isinstance(value, str):
            assert value not in forbidden_keys
            assert "hsconfig-configure-" not in value
            assert ".staging-" not in value
            assert not Path(value).is_absolute()


def test_failed_configure_leaves_previous_current_byte_identical(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _disable_remote_card_fetches(monkeypatch)
    output_root = tmp_path / "outputs" / "ShadowPriest"
    runtime_root = tmp_path / "runtime"
    assert main(_configure_args(output_root, runtime_root)) == 0
    capsys.readouterr()
    before_pointer = (output_root / "current.json").read_bytes()
    before_tree = _tree_bytes(output_root)
    failure_args = _configure_args(output_root, runtime_root)
    failure_args[failure_args.index(SHADOWPRIEST_CODE)] = "not-a-deck-code"

    assert main(failure_args) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert (output_root / "current.json").read_bytes() == before_pointer
    assert _tree_bytes(output_root) == before_tree


@pytest.mark.parametrize(
    "installer_status",
    [
        "applied",
        "already_current",
        "recovered",
        "committed_receipt_pending",
    ],
)
def test_configure_apply_runs_after_publication_against_digest_bound_revision(
    tmp_path: Path,
    monkeypatch,
    capsys,
    installer_status: str,
) -> None:
    _disable_remote_card_fetches(monkeypatch)
    output_root = tmp_path / "outputs" / "ShadowPriest"
    runtime_root = tmp_path / "runtime"
    observed: dict[str, object] = {}

    def fake_apply(args):
        package = Path(args.package)
        observed["package"] = package
        observed["current_revision"] = json.loads(
            (output_root / "current.json").read_bytes()
        )["revision"]
        observed["expected_digest"] = (
            args.expected_publication_content_root_sha256
        )
        observed["expected_package"] = Path(
            args.expected_published_package
        )
        return {
            "status": installer_status,
            "receipt": {
                "status": installer_status,
                "logical_config_dir": "shadowpriest",
                "versioned_config_dir": "shadowpriest--sha256-" + "a" * 64,
            },
        }, 0

    monkeypatch.setattr(
        "hsconfig.commands.configure.apply_payload",
        fake_apply,
    )
    args = _configure_args(output_root, runtime_root)
    args.insert(-1, "--apply")

    assert main(args) == 0

    payload = json.loads(capsys.readouterr().out)
    package = resolve_current_package(output_root)
    assert observed == {
        "package": output_root,
        "current_revision": package.parent.relative_to(
            output_root
        ).as_posix(),
        "expected_digest": package.parent.name.removeprefix("sha256-"),
        "expected_package": package,
    }
    assert payload["status"] == "OK"
    assert payload["apply_performed"] is True
    assert payload["apply_status"] == 0
    assert payload["apply_result"]["status"] == installer_status
    assert payload["apply_result"]["receipt"]["status"] == installer_status
    assert payload.get("runtime_package_match") is None
    assert payload.get("runtime_package_match_status") == "not_checked"
    assert (
        payload["publication_content_root_sha256"]
        == package.parent.name.removeprefix("sha256-")
    )


def test_configure_apply_failure_keeps_new_publication_current(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _disable_remote_card_fetches(monkeypatch)
    output_root = tmp_path / "outputs" / "ShadowPriest"
    runtime_root = tmp_path / "runtime"

    monkeypatch.setattr(
        "hsconfig.commands.configure.apply_payload",
        lambda _args: (
            {"status": "failed", "errors": ["runtime rejected"]},
            1,
        ),
    )
    args = _configure_args(output_root, runtime_root)
    args.insert(-1, "--apply")

    assert main(args) == 1

    payload = json.loads(capsys.readouterr().out)
    package = resolve_current_package(output_root)
    assert payload["status"] == "failed"
    assert payload["stage"] == "apply"
    assert payload["errors"] == ["runtime rejected"]
    assert payload["published_package"] == (
        package.relative_to(output_root).as_posix()
    )
    assert (
        payload["publication_content_root_sha256"]
        == package.parent.name.removeprefix("sha256-")
    )


def test_configure_apply_releases_publication_lease_before_consumer(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import hsconfig.configure_workflow as workflow

    _disable_remote_card_fetches(monkeypatch)
    output_root = tmp_path / "outputs" / "ShadowPriest"
    runtime_root = tmp_path / "runtime"
    lease_active = False
    real_lease = workflow.lease_package_input

    @contextmanager
    def instrumented_lease(package_input):
        nonlocal lease_active
        with real_lease(package_input) as lease:
            assert lease_active is False
            lease_active = True
            try:
                yield lease
            finally:
                lease_active = False

    def fake_apply(_args):
        assert lease_active is False, "configure_apply_self_deadlock"
        return {
            "status": "applied",
            "receipt": {"status": "applied"},
        }, 0

    monkeypatch.setattr(workflow, "lease_package_input", instrumented_lease)
    monkeypatch.setattr(
        "hsconfig.commands.configure.apply_payload",
        fake_apply,
    )
    args = _configure_args(output_root, runtime_root)
    args.insert(-1, "--apply")

    assert main(args) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "OK"
    assert payload["apply_result"]["receipt"]["status"] == "applied"


@pytest.mark.parametrize(
    "installer_status",
    [
        "applied",
        "already_current",
        "recovered",
        "committed_receipt_pending",
    ],
)
def test_namespace_configure_consumer_accepts_typed_status_without_runtime_match(
    tmp_path: Path,
    monkeypatch,
    installer_status: str,
) -> None:
    _disable_remote_card_fetches(monkeypatch)
    output_root = tmp_path / "namespace-output"
    args = build_parser().parse_args(
        [
            *_configure_args(output_root, tmp_path / "runtime")[:-1],
            "--apply",
            "--json",
        ]
    )

    payload, code = _execute_configure_namespace(
        args,
        apply_payload_fn=lambda _args: (
            {
                "status": installer_status,
                "receipt": {"status": installer_status},
            },
            0,
        ),
    )

    assert code == 0
    assert payload["status"] == "OK"
    assert payload["apply_status"] == 0
    assert payload["runtime_package_match_status"] == "not_checked"
    assert payload["runtime_package_match"] is None


def test_configure_apply_rejects_competing_current_digest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _disable_remote_card_fetches(monkeypatch)
    output_root = tmp_path / "outputs" / "ShadowPriest"
    runtime_root = tmp_path / "runtime"
    competing = build_rendered_run(tmp_path / "competitor", 2)
    apply_called = False

    def publish_then_compete(rendered, selected_output_root):
        first = publish_configure_run(rendered, selected_output_root)
        publish_configure_run(competing, selected_output_root)
        return first

    def fake_apply(_args):
        nonlocal apply_called
        apply_called = True
        return {
            "status": "applied",
            "receipt": {"status": "applied"},
        }, 0

    monkeypatch.setattr(
        "hsconfig.configure_workflow.publish_configure_run",
        publish_then_compete,
    )
    monkeypatch.setattr(
        "hsconfig.commands.configure.apply_payload",
        fake_apply,
    )
    args = _configure_args(output_root, runtime_root)
    args.insert(-1, "--apply")

    assert main(args) == 1

    payload = json.loads(capsys.readouterr().out)
    current_package = resolve_current_package(output_root)
    assert apply_called is False
    assert payload["status"] == "failed"
    assert payload["stage"] == "apply"
    assert payload["errors"] == [
        "configure_apply_publication_digest_mismatch"
    ]
    assert (
        current_package.parent.name
        == f"sha256-{competing.content_root_sha256}"
    )
    assert (
        payload["publication_content_root_sha256"]
        != competing.content_root_sha256
    )


def test_apply_payload_fails_closed_when_current_drifts_after_configure_lease(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "published"
    expected = publish_configure_run(
        build_rendered_run(tmp_path / "expected", 1),
        output_root,
    )
    current = publish_configure_run(
        build_rendered_run(tmp_path / "current", 2),
        output_root,
    )

    payload, code = real_apply_payload(
        SimpleNamespace(
            package=str(output_root),
            runtime_root=str(tmp_path / "runtime"),
            fake=False,
            from_fake_receipt=None,
            expected_publication_content_root_sha256=(
                expected.content_root_sha256
            ),
            expected_published_package=str(expected.package_root),
            json=True,
        )
    )

    assert code == 1
    assert payload["errors"] == [
        "configure_apply_publication_digest_mismatch"
    ]
    assert (
        payload["publication_content_root_sha256"]
        == current.content_root_sha256
    )


def test_configure_apply_keeps_published_revision_byte_identical(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _disable_remote_card_fetches(monkeypatch)
    output_root = tmp_path / "outputs" / "ShadowPriest"
    runtime_root = tmp_path / "runtime"
    observed: dict[str, object] = {}

    def apply_and_compare(args):
        revision_root = Path(args.expected_published_package).parent
        before = _tree_bytes(revision_root)
        result = real_apply_payload(args)
        observed["before"] = before
        observed["after"] = _tree_bytes(revision_root)
        observed["immutable_package"] = getattr(
            args,
            "immutable_package",
            False,
        )
        return result

    monkeypatch.setattr(
        "hsconfig.commands.configure.apply_payload",
        apply_and_compare,
    )
    args = _configure_args(output_root, runtime_root)
    args.insert(-1, "--apply")

    assert main(args) == 0

    payload = json.loads(capsys.readouterr().out)
    package = resolve_current_package(output_root)
    assert payload["status"] == "OK"
    assert observed["immutable_package"] is True
    assert observed["before"] == observed["after"]
    assert not (
        package / "reports" / "runtime_apply_fake_receipt.json"
    ).exists()
    assert not (
        package / "reports" / "runtime_apply_receipt.json"
    ).exists()
