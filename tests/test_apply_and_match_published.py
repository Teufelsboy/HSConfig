from __future__ import annotations

import importlib
import json
import shutil
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event, Thread, get_ident
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from hsconfig import live_start_session
from hsconfig.atomic_io import ExclusiveFileLock
from hsconfig.current_output import revalidate_package_input_lease
from hsconfig.package_io import path_identity
from hsconfig.runtime_transaction_journal import runtime_transaction_journal_path
from tests.test_configure_prepublication_apply import (
    _controller,
    _lease_prepublication_capabilities,
    _physical_tree,
    _prepare_pipeline,
)
from tests.test_output_publisher import build_rendered_run


_ATTEMPT_A = "a" * 32
_ATTEMPT_B = "b" * 32
_THREAD_TIMEOUT = 20.0


def _published_apply() -> ModuleType:
    """Load the Task-10 surface at execution so all RED selectors collect."""

    return importlib.import_module("hsconfig.published_apply")


@contextmanager
def _lease_published_capabilities(
    prepared: SimpleNamespace,
) -> Iterator[SimpleNamespace]:
    controller = _controller()
    with _lease_prepublication_capabilities(prepared) as capabilities:
        validated, session_lease, profile_lease, operation_lease = capabilities
        published_session = controller.publish_validated_prepublication(
            validated=validated,
            session_lease=session_lease,
            expected_session=validated.updated_session,
            profile_lease=profile_lease,
            operation_lease=operation_lease,
        )
        assert (
            published_session.phase
            is live_start_session.LiveStartPhase.PUBLICATION_COMMITTED
        )
        publication = published_session.publication_binding
        assert isinstance(publication, Mapping)
        output_root = Path(str(publication["output_child_path"]))
        operation = controller.load_bound_output_operation_admission(
            published_session
        )
        yield SimpleNamespace(
            prepared=prepared,
            session_lease=session_lease,
            expected_session=published_session,
            profile_lease=profile_lease,
            output_operation_lease=operation_lease,
            output_operation_admission=operation,
            output_root=output_root,
            publication_content_root_sha256=str(
                publication["content_root_sha256"]
            ),
            runtime_root=prepared.runtime_root,
        )


def _composite(
    published_apply: ModuleType,
    held: SimpleNamespace,
    *,
    apply_attempt_id: str,
    fault_hook: Any | None = None,
) -> Any:
    kwargs = {
        "session_lease": held.session_lease,
        "expected_session": held.expected_session,
        "profile_lease": held.profile_lease,
        "output_operation_lease": held.output_operation_lease,
        "output_operation_admission": held.output_operation_admission,
        "output_root": held.output_root,
        "publication_content_root_sha256": (
            held.publication_content_root_sha256
        ),
        "runtime_root": held.runtime_root,
        "apply_attempt_id": apply_attempt_id,
    }
    if fault_hook is None:
        return published_apply.apply_and_match_published(**kwargs)
    return published_apply._apply_and_match_published(
        **kwargs,
        fault_hook=fault_hook,
    )


def _disposition_value(result: Any) -> str:
    value = result.physical_disposition
    return str(getattr(value, "value", value))


def _point_value(point: Any) -> str:
    return str(getattr(point, "value", point))


def _forbid_terminal_old_capability_reacquisition(
    *,
    published_apply: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbid_old_capability(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("terminal-fast-path-reacquired-old-capability")

    for name in (
        "load_operator_profile",
        "lease_operator_profile",
        "lease_output_operation_admission",
        "lease_package_input",
        "lease_controller_apply_pair",
    ):
        monkeypatch.setattr(published_apply, name, forbid_old_capability)


def _foreign_runtime_admission_bytes(historical: bytes) -> bytes:
    document = json.loads(historical)
    foreign_run_id = "c" * 32
    foreign_attempt_id = "d" * 32
    document["run_id"] = foreign_run_id
    document["apply_attempt_id"] = foreign_attempt_id
    document["retention_owner_run_id"] = foreign_run_id
    document["retention_fence_path"] = str(
        Path(str(document["runtime_root"]))
        / ".hsconfig"
        / "attempt-retention"
        / f"{foreign_attempt_id}.json"
    )
    document.pop("content_sha256", None)
    canonical_unsigned = json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    document["content_sha256"] = (
        "sha256:" + sha256(canonical_unsigned).hexdigest()
    )
    return json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _stage_alternate_publication(
    root: Path,
) -> tuple[Path, bytes]:
    from hsconfig.output_publisher import publish_configure_run

    rendered = build_rendered_run(root / "source", 2)
    output_root = root / "alternate-output"
    published = publish_configure_run(rendered, output_root)
    return published.revision_root, (output_root / "current.json").read_bytes()


def _install_identical_runtime(
    prepared: SimpleNamespace,
    root: Path,
) -> dict[str, Any]:
    from hsconfig.output_publisher import publish_configure_run
    from hsconfig.runtime_apply import apply_package

    rendered = _controller().render_configure_run_model(prepared.run_model)
    output_root = root / "preinstall-output"
    publish_configure_run(rendered, output_root)
    applied = apply_package(
        package_root=output_root,
        runtime_root=prepared.runtime_root,
    )
    assert applied["status"] in {"applied", "recovered", "already_current"}
    return applied


def _copy_alternate_revision(
    *,
    source_revision: Path,
    output_root: Path,
) -> None:
    destination = output_root / "revisions" / source_revision.name
    assert not destination.exists()
    shutil.copytree(source_revision, destination)


def _start_lock_contender(
    *,
    lock_path: Path,
    mutate: Any,
) -> tuple[Thread, Event, Event, list[BaseException]]:
    attempted = Event()
    acquired = Event()
    errors: list[BaseException] = []

    def contend() -> None:
        attempted.set()
        try:
            with ExclusiveFileLock(lock_path):
                acquired.set()
                mutate()
        except BaseException as error:  # pragma: no cover - asserted by caller
            errors.append(error)

    thread = Thread(target=contend)
    thread.start()
    assert attempted.wait(5)
    return thread, attempted, acquired, errors


def _join_contender(
    thread: Thread,
    acquired: Event,
    errors: list[BaseException],
) -> None:
    thread.join(_THREAD_TIMEOUT)
    assert not thread.is_alive()
    assert acquired.is_set()
    assert errors == []


def _mutate_one_runtime_json(runtime_root: Path, marker: str) -> Path:
    for candidate in sorted((runtime_root / "CustomConfig").rglob("*.json")):
        try:
            value = json.loads(candidate.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            value[marker] = True
        elif isinstance(value, list):
            value.append({marker: True})
        else:
            value = {"prior_value": value, marker: True}
        candidate.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return candidate
    raise AssertionError("runtime_json_fixture_missing")


def _runtime_revision_names(runtime_root: Path) -> set[str]:
    custom_config = runtime_root / "CustomConfig"
    if not custom_config.is_dir():
        return set()
    return {entry.name for entry in custom_config.iterdir() if entry.is_dir()}


def _optional_path(value: Path | None) -> str | None:
    return None if value is None else str(value)


def _optional_identity(value: Any) -> list[int] | None:
    return None if value is None else list(value)


def _terminalize_result(
    *,
    session_lease: Any,
    held: Any,
) -> Any:
    cursor = held.updated_session
    result = held.result
    publication = cursor.publication_binding
    assert isinstance(publication, Mapping)
    unique_cards = live_start_session._frozen_main_roster_count_under_lock(
        session_lease=session_lease,
        session_value=cursor,
    )
    intent = live_start_session.seal_embedded_document(
        "result_intent",
        {
            "schema_version": 1,
            "intent_kind": live_start_session.LIVE_START_RESULT_INTENT_KIND,
            "run_id": cursor.run_id,
            "terminal_status": result.terminal_status,
            "deck_name": cursor.deck_name,
            "candidate_revision": cursor.candidate_revision,
            "unique_main_deck_cards": unique_cards,
            "configured_cards": unique_cards,
            "deliberately_unconfigured_cards": 0,
            "review_confidence": "high",
            "visible_limitations": [],
            "apply_attempt_id": held.invocation.apply_attempt_id,
            "publication_revision": publication["revision"],
            "publication_content_root_sha256": publication[
                "content_root_sha256"
            ],
            "raw_apply_status": result.raw_apply_status,
            "physical_disposition": _disposition_value(result),
            "runtime_match_status": result.runtime_match_status,
            "runtime_match_sha256": result.runtime_match_sha256,
            "package_root_sha256": result.package_root_sha256,
            "last_apply_receipt_sha256": result.last_apply_receipt_sha256,
            "runtime_state_sha256": result.runtime_state_sha256,
            "deck_config_ini_sha256": result.deck_config_ini_sha256,
            "retained_attempt_record_path": _optional_path(
                result.retained_attempt_record_path
            ),
            "retained_attempt_record_identity": _optional_identity(
                result.retained_attempt_record_identity
            ),
            "retained_attempt_record_sha256": (
                result.retained_attempt_record_sha256
            ),
            "retained_journal_path": _optional_path(
                result.retained_journal_path
            ),
            "retained_journal_identity": _optional_identity(
                result.retained_journal_identity
            ),
            "retained_journal_sha256": result.retained_journal_sha256,
            "retained_target_owner_journal_path": _optional_path(
                result.retained_target_owner_journal_path
            ),
            "retained_target_owner_journal_identity": _optional_identity(
                result.retained_target_owner_journal_identity
            ),
            "retained_target_owner_journal_sha256": (
                result.retained_target_owner_journal_sha256
            ),
            "retained_candidate_identity": None,
            "runtime_admission_path": _optional_path(
                result.runtime_admission_path
            ),
            "runtime_admission_parent_identity": _optional_identity(
                result.runtime_admission_parent_identity
            ),
            "runtime_admission_identity": _optional_identity(
                result.runtime_admission_identity
            ),
            "runtime_admission_sha256": result.runtime_admission_sha256,
            "error_code": result.error_code,
            "retained_safe_state": (
                "ACTIVE_RUNTIME_MATCHED"
                if result.runtime_match_status == "matched"
                else (
                    "PREVIOUS_RUNTIME_UNCHANGED"
                    if _disposition_value(result) == "NOT_COMMITTED"
                    else "ATTEMPT_EVIDENCE_RETAINED"
                )
            ),
        },
    )
    evidence = held.acknowledgement_evidence
    acknowledgement = (
        None
        if evidence is None
        else live_start_session.seal_embedded_document(
            "attempt_acknowledgement",
            {
                "schema_version": 1,
                "acknowledgement_kind": (
                    live_start_session.LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_KIND
                ),
                "run_id": cursor.run_id,
                "apply_attempt_id": evidence.apply_attempt_id,
                "retention_owner_run_id": evidence.retention_owner_run_id,
                "retention_fence_path": str(evidence.retention_fence_path),
                "retention_fence_identity": list(
                    evidence.retention_fence_identity
                ),
                "retention_fence_sha256": evidence.retention_fence_sha256,
                "journal_path": str(evidence.journal_path),
                "journal_identity": list(evidence.journal_identity),
                "journal_sha256": evidence.journal_sha256,
                "target_owner_journal_path": str(
                    evidence.target_owner_journal_path
                ),
                "target_owner_journal_identity": list(
                    evidence.target_owner_journal_identity
                ),
                "target_owner_journal_sha256": (
                    evidence.target_owner_journal_sha256
                ),
                "target_path": str(evidence.target_path),
                "target_identity": list(evidence.target_identity),
                "package_root_sha256": evidence.package_root_sha256,
                "runtime_admission_path": str(evidence.runtime_admission_path),
                "runtime_admission_parent_identity": list(
                    evidence.runtime_admission_parent_identity
                ),
                "runtime_admission_identity": list(
                    evidence.runtime_admission_identity
                ),
                "runtime_admission_sha256": evidence.runtime_admission_sha256,
                "journal_owns_target": evidence.journal_owns_target,
                "acknowledgement_action": evidence.acknowledgement_action,
            },
        )
    )
    result_cursor = live_start_session.bind_result_intent_under_lock(
        session_lease=session_lease,
        expected_session=cursor,
        result_intent=intent,
        attempt_acknowledgement=acknowledgement,
    )
    return live_start_session.record_terminal_status_under_lock(
        session_lease=session_lease,
        expected_result_session=result_cursor,
    )


def _terminalize_success(
    *,
    session_lease: Any,
    held: Any,
) -> Any:
    assert held.acknowledgement_evidence is not None
    return _terminalize_result(session_lease=session_lease, held=held)


def test_composite_holds_one_publication_lease_through_apply_and_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    enters = 0
    exits = 0
    active_leases: list[Any] = []
    real_lease = published_apply.lease_package_input

    @contextmanager
    def traced_lease(*args: Any, **kwargs: Any) -> Iterator[Any]:
        nonlocal enters, exits
        enters += 1
        with real_lease(*args, **kwargs) as lease:
            active_leases.append(lease)
            yield lease
        exits += 1

    monkeypatch.setattr(published_apply, "lease_package_input", traced_lease)
    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            assert enters == 1
            assert exits == 0
            assert held.result.runtime_match_status == "matched"
            revalidate_package_input_lease(active_leases[0])
        assert exits == 1
    assert enters == exits == 1


def test_composite_output_handoff_uses_bound_release_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig.output_publisher import (
        release_output_operation_admission_under_lease,
    )

    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    releases: list[tuple[Any, Any, str]] = []

    def trace_release(**kwargs: Any) -> Any:
        disposition = release_output_operation_admission_under_lease(**kwargs)
        releases.append(
            (
                kwargs["operation_lease"],
                kwargs["expected"],
                disposition,
            )
        )
        return disposition

    monkeypatch.setattr(
        published_apply,
        "release_output_operation_admission_under_lease",
        trace_release,
    )

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            assert held.result.runtime_match_status == "matched"
            assert len(releases) == 1
            released_lease, released_evidence, disposition = releases[0]
            assert released_lease is capabilities.output_operation_lease
            assert released_evidence.admission_path == (
                capabilities.output_operation_admission.admission_path
            )
            assert released_evidence.admission_identity == (
                capabilities.output_operation_admission.admission_identity
            )
            assert disposition == "old_unlinked"
            assert not released_evidence.admission_path.exists()


def test_initial_recovery_adapter_rejects_equal_copied_admission_before_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    calls = {"mint": 0, "observe": 0}
    real_adapter = published_apply._observe_runtime_recovery_from_context

    def tamper_runtime_admission(**kwargs: Any) -> Any:
        original = kwargs["runtime_admission"]
        forged = replace(original)
        assert forged == original
        assert forged is not original
        return real_adapter(**{**kwargs, "runtime_admission": forged})

    def forbid_mint(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        calls["mint"] += 1
        raise AssertionError("invalid initial context reached observation mint")

    def forbid_observe(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        calls["observe"] += 1
        raise AssertionError("invalid initial context reached runtime observer")

    monkeypatch.setattr(
        published_apply,
        "_observe_runtime_recovery_from_context",
        tamper_runtime_admission,
    )
    monkeypatch.setattr(
        live_start_session,
        "_authorize_runtime_observation_under_lock",
        forbid_mint,
    )
    monkeypatch.setattr(
        published_apply,
        "observe_initial_runtime_install_from_pair",
        forbid_observe,
    )

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            live_start_session.SessionCapabilityError,
            match="^published_apply_recovery_invocation_context_invalid$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
            ):
                pass

    assert calls == {"mint": 0, "observe": 0}
    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert interrupted.phase is live_start_session.LiveStartPhase.APPLY_STARTED
    assert interrupted.apply_recovery is None


def test_composite_reenters_fresh_pair_after_output_operation_unlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_pair_lease = published_apply.lease_controller_apply_pair
    real_recover = published_apply.recover_runtime_attempt_from_pair
    events: list[str] = []
    pair_entries: list[dict[str, Any]] = []
    recovery_pair_tokens: list[Any] = []
    pair_depth = 0
    max_pair_depth = 0

    @contextmanager
    def traced_pair(*args: Any, **kwargs: Any) -> Iterator[Any]:
        nonlocal pair_depth, max_pair_depth
        runtime_admission = kwargs["runtime_admission"]
        label = "pre" if runtime_admission is None else "post"
        entry = {
            "runtime_admission": runtime_admission,
            "expected_session": kwargs["expected_session"],
            "output_admission_exists": kwargs[
                "output_operation_admission"
            ].admission_path.exists(),
        }
        pair_entries.append(entry)
        assert pair_depth == 0
        pair_depth += 1
        max_pair_depth = max(max_pair_depth, pair_depth)
        events.append(f"pair_enter_{label}")
        try:
            with real_pair_lease(*args, **kwargs) as pair:
                binding = (
                    published_apply._authenticate_controller_apply_pair_binding(
                        pair
                    )
                )
                entry["pair"] = pair
                entry["binding"] = binding
                entry["tokens"] = (
                    pair.pair_token,
                    binding.session_token,
                    binding.profile_token,
                    binding.output_operation_token,
                    binding.package_token,
                    binding.runtime_token,
                )
                events.append(f"pair_yield_{label}")
                yield pair
        finally:
            pair_depth -= 1
            events.append(f"pair_exit_{label}")

    def traced_recovery(*args: Any, **kwargs: Any) -> Any:
        recovery_pair_tokens.append(kwargs["lease_pair"].pair_token)
        return real_recover(*args, **kwargs)

    monkeypatch.setattr(
        published_apply,
        "lease_controller_apply_pair",
        traced_pair,
    )
    monkeypatch.setattr(
        published_apply,
        "recover_runtime_attempt_from_pair",
        traced_recovery,
    )

    interrupted: dict[str, Any] = {}
    with _lease_published_capabilities(prepared) as capabilities:
        historical = capabilities.output_operation_admission

        def crash_after_output_handoff(point: Any) -> None:
            if _point_value(point) != "after_output_operation_admission_unlink":
                return
            events.append("after_output_operation_admission_unlink")
            cursor = live_start_session.load_live_start_session_under_lock(
                session_lease=capabilities.session_lease
            )
            runtime_admission = (
                published_apply.load_runtime_live_attempt_admission()
            )
            assert cursor.phase is live_start_session.LiveStartPhase.APPLY_STARTED
            assert cursor.apply_recovery is None
            handoff = cursor.output_operation_admission_binding
            assert isinstance(handoff, Mapping)
            assert handoff["state"] == "RUNTIME_HANDOFF_RELEASE_AUTHORIZED"
            assert runtime_admission is not None
            assert runtime_admission.apply_attempt_id == _ATTEMPT_A
            assert not historical.admission_path.exists()
            interrupted["session"] = cursor
            interrupted["runtime_admission"] = runtime_admission
            raise RuntimeError("crash-after-output-operation-unlink")

        with pytest.raises(
            RuntimeError,
            match="^crash-after-output-operation-unlink$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_output_handoff,
            ):
                pass

        assert len(pair_entries) == 1
        assert pair_depth == 0
        assert not historical.admission_path.exists()
        with pytest.raises(
            ValueError,
            match="^controller_apply_pair_inactive_or_forged$",
        ):
            published_apply._authenticate_controller_apply_pair_binding(
                pair_entries[0]["pair"]
            )

    def forbid_second_apply(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("recovery-must-not-start-a-second-apply")

    def forbid_second_admission(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("recovery-must-not-claim-a-second-admission")

    monkeypatch.setattr(
        live_start_session,
        "prepare_apply_attempt_under_lock",
        forbid_second_apply,
    )
    monkeypatch.setattr(
        published_apply,
        "_claim_runtime_admission",
        forbid_second_admission,
    )
    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert isinstance(recovered, published_apply.ApplyAndMatchPublishedResult)
    assert recovered.raw_apply_status is None
    assert _disposition_value(recovered) == "NOT_COMMITTED"
    assert recovered.runtime_match_status == "not_run"
    assert recovered.terminal_status == "FAILED_PRESERVED"
    assert recovered.error_code == "apply_not_committed"
    assert len(pair_entries) == 2
    assert pair_depth == 0
    assert max_pair_depth == 1
    first, second = pair_entries
    assert first["pair"] is not second["pair"]
    assert all(
        current is not prior
        for prior, current in zip(
            first["tokens"],
            second["tokens"],
            strict=True,
        )
    )
    assert first["runtime_admission"] is None
    assert first["output_admission_exists"] is True
    assert first["expected_session"].phase is (
        live_start_session.LiveStartPhase.PUBLICATION_COMMITTED
    )
    assert first["binding"].entry_mode == "PRE_HANDOFF_READY"
    assert first["binding"].reentry_output_disposition == "exact_old"

    interrupted_session = interrupted["session"]
    interrupted_admission = interrupted["runtime_admission"]
    assert second["expected_session"] == interrupted_session
    assert (
        second["expected_session"].canonical_json
        == interrupted_session.canonical_json
    )
    assert (
        second["expected_session"].session_identity
        == interrupted_session.session_identity
    )
    assert second["runtime_admission"] == interrupted_admission
    assert second["binding"].runtime_admission is second["runtime_admission"]
    assert second["output_admission_exists"] is False
    assert second["binding"].entry_mode == "POST_HANDOFF_READY"
    assert second["binding"].reentry_output_disposition == "absent"
    assert first["binding"].run_id == second["binding"].run_id
    assert first["binding"].session_root == second["binding"].session_root
    assert (
        first["binding"].session_root_identity
        == second["binding"].session_root_identity
    )
    assert first["binding"].package_lease.publication == (
        second["binding"].package_lease.publication
    )
    assert first["binding"].runtime_lease.runtime_root == (
        second["binding"].runtime_lease.runtime_root
    )
    assert first["binding"].runtime_lease.runtime_root_identity == (
        second["binding"].runtime_lease.runtime_root_identity
    )
    assert recovery_pair_tokens
    assert set(recovery_pair_tokens) == {second["pair"].pair_token}
    assert events == [
        "pair_enter_pre",
        "pair_yield_pre",
        "after_output_operation_admission_unlink",
        "pair_exit_pre",
        "pair_enter_post",
        "pair_yield_post",
        "pair_exit_post",
    ]
    for entry in pair_entries:
        with pytest.raises(
            ValueError,
            match="^controller_apply_pair_inactive_or_forged$",
        ):
            published_apply._authenticate_controller_apply_pair_binding(
                entry["pair"]
            )


def test_composite_passes_invocation_attempt_id_to_runtime_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            assert held.invocation.apply_attempt_id == _ATTEMPT_A
            assert (
                held.runtime_admission_evidence.apply_attempt_id == _ATTEMPT_A
            )
            journal_path = held.result.retained_journal_path
            assert journal_path == runtime_transaction_journal_path(
                prepared.runtime_root,
                _ATTEMPT_A,
            )
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            assert journal["transaction_id"] == _ATTEMPT_A
            assert journal_path.name == f"{_ATTEMPT_A}.json"
            admission = held.runtime_admission_evidence
            assert admission.package_root_sha256 == (
                held.invocation.publication_content_root_sha256
            )
            assert journal["source_manifest_sha256"] == (
                admission.package_root_sha256.removeprefix("sha256:")
            )
            assert journal["target_path"].endswith(
                f"--sha256-{journal['package_root_sha256']}"
            )
            assert (
                journal["package_root_sha256"]
                != journal["source_manifest_sha256"]
            )


def test_composite_revalidates_outer_capabilities_immediately_before_complete_apply_started(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    validations: list[dict[str, Any]] = []
    complete_calls: list[dict[str, Any]] = []

    with _lease_published_capabilities(prepared) as capabilities:

        def stop_after_context_validation(
            *args: Any,
            **kwargs: Any,
        ) -> None:
            assert args == ()
            cursor = kwargs["cursor"]
            pending = cursor.pending_transition
            layout = cursor.runtime_layout_bootstrap
            pair = kwargs["lease_pair"]
            binding = (
                published_apply._authenticate_controller_apply_pair_binding(
                    pair
                )
            )
            assert cursor.phase is (
                live_start_session.LiveStartPhase.PUBLICATION_COMMITTED
            )
            assert isinstance(pending, Mapping)
            assert pending["operation"] == "install_apply_invocation"
            assert pending["stage"] == "PRIMARY_APPLIED"
            assert pending["external_file_action"] is None
            assert isinstance(layout, Mapping)
            assert layout["stage"] == "COMPLETE"
            assert kwargs["session_lease"] is capabilities.session_lease
            assert kwargs["profile_lease"] is capabilities.profile_lease
            assert binding.session_lease is kwargs["session_lease"]
            assert binding.profile_lease is kwargs["profile_lease"]
            assert binding.package_lease is kwargs["package_lease"]
            assert binding.runtime_admission is kwargs["runtime_admission"]
            assert kwargs["historical"] is binding.output_operation_admission
            assert kwargs["invocation"].apply_attempt_id == _ATTEMPT_A
            validations.append(dict(kwargs))
            raise live_start_session.SessionCapabilityError(
                "sentinel_pre_apply_started_outer_context_drift"
            )

        def forbid_complete_apply_started(
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            complete_calls.append({"args": args, **kwargs})
            raise AssertionError(
                "complete_apply_started_must_follow_context_validation"
            )

        monkeypatch.setattr(
            published_apply,
            "_require_recovery_invocation_context",
            stop_after_context_validation,
        )
        monkeypatch.setattr(
            live_start_session,
            "_complete_apply_started_under_lock",
            forbid_complete_apply_started,
        )

        with pytest.raises(
            live_start_session.SessionCapabilityError,
            match="^sentinel_pre_apply_started_outer_context_drift$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
            ):
                pass

        persisted = live_start_session.load_live_start_session_under_lock(
            session_lease=capabilities.session_lease
        )
        pending = persisted.pending_transition
        assert persisted.phase is (
            live_start_session.LiveStartPhase.PUBLICATION_COMMITTED
        )
        assert isinstance(pending, Mapping)
        assert pending["operation"] == "install_apply_invocation"
        assert pending["stage"] == "PRIMARY_APPLIED"
        assert persisted.apply_recovery is None

    assert len(validations) == 1
    assert complete_calls == []


def test_pointer_change_before_composite_blocks_without_runtime_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    alternate_revision, alternate_current = _stage_alternate_publication(
        tmp_path / "alternate"
    )
    with _lease_published_capabilities(prepared) as capabilities:
        _copy_alternate_revision(
            source_revision=alternate_revision,
            output_root=capabilities.output_root,
        )
        current_path = capabilities.output_root / "current.json"
        original_current = current_path.read_bytes()
        assert original_current != alternate_current
        current_path.write_bytes(alternate_current)
        runtime_before = _physical_tree(prepared.runtime_root)

        with pytest.raises((ValueError, live_start_session.SessionConflictError)):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
            ):
                pass

        assert _physical_tree(prepared.runtime_root) == runtime_before
        assert not runtime_transaction_journal_path(
            prepared.runtime_root,
            _ATTEMPT_A,
        ).exists()


def test_pointer_cannot_switch_between_apply_and_final_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    alternate_revision, alternate_current = _stage_alternate_publication(
        tmp_path / "alternate"
    )
    real_match = published_apply.build_runtime_package_match_report_from_pair
    contender: tuple[Thread, Event, Event, list[BaseException]] | None = None

    with _lease_published_capabilities(prepared) as capabilities:
        _copy_alternate_revision(
            source_revision=alternate_revision,
            output_root=capabilities.output_root,
        )
        current_path = capabilities.output_root / "current.json"

        def match_while_publisher_waits(*args: Any, **kwargs: Any) -> Any:
            nonlocal contender
            contender = _start_lock_contender(
                lock_path=capabilities.output_root / ".publish.lock",
                mutate=lambda: current_path.write_bytes(alternate_current),
            )
            assert not contender[2].wait(0.1)
            return real_match(*args, **kwargs)

        monkeypatch.setattr(
            published_apply,
            "build_runtime_package_match_report_from_pair",
            match_while_publisher_waits,
        )
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            assert held.result.runtime_match_status == "matched"
            assert contender is not None
            assert not contender[2].is_set()

    assert contender is not None
    _join_contender(contender[0], contender[2], contender[3])
    assert current_path.read_bytes() == alternate_current


def test_post_commit_runtime_mutation_is_applied_but_not_verified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    mutated: list[Path] = []

    def mutate_after_commit(point: Any) -> None:
        if (
            _point_value(point) == "after_physical_commit_before_installer_return"
            and not mutated
        ):
            mutated.append(
                _mutate_one_runtime_json(
                    prepared.runtime_root,
                    "task10_post_commit_mutation",
                )
            )

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
            fault_hook=mutate_after_commit,
        ) as held:
            assert len(mutated) == 1
            assert _disposition_value(held.result) == "COMMITTED"
            assert held.result.runtime_match_status == "mismatch"
            assert held.result.terminal_status == "APPLIED_BUT_NOT_VERIFIED"
            assert held.result.raw_apply_status == "applied"


def test_committed_mismatch_releases_admission_but_retains_fence_and_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    mutated: list[Path] = []

    def mutate_after_commit(point: Any) -> None:
        if (
            _point_value(point) == "after_physical_commit_before_installer_return"
            and not mutated
        ):
            mutated.append(
                _mutate_one_runtime_json(
                    prepared.runtime_root,
                    "task10_release_committed_mismatch",
                )
            )

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
            fault_hook=mutate_after_commit,
        ) as held:
            result = held.result
            assert result.runtime_match_status == "mismatch"
            assert result.terminal_status == "APPLIED_BUT_NOT_VERIFIED"
            assert held.acknowledgement_evidence is None
            retained_paths = {
                path
                for path in (
                    result.retained_attempt_record_path,
                    result.retained_journal_path,
                    result.retained_target_owner_journal_path,
                )
                if path is not None
            }
            assert len(retained_paths) >= 2
            retained_before = {
                path: (path_identity(path), path.read_bytes())
                for path in retained_paths
            }
            admission_path = held.runtime_admission_evidence.admission_path
            assert admission_path.is_file()

            terminal = _terminalize_result(
                session_lease=capabilities.session_lease,
                held=held,
            )
            assert terminal.attempt_acknowledgement is None
            terminal_status = terminal.terminal_status
            result_intent = terminal.result_intent
            resolved = held.resolve_and_release_after_terminal(
                session_lease=capabilities.session_lease,
                expected_terminal_session=terminal,
            )

            assert resolved.terminal_status == terminal_status
            assert resolved.result_intent == result_intent
            assert resolved.attempt_acknowledgement is None
            assert resolved.terminal_retirement is not None
            assert resolved.terminal_retirement["operation"] == (
                "release_committed_mismatch"
            )
            assert resolved.terminal_retirement["stage"] == (
                "ADMISSION_RELEASE_AUTHORIZED"
            )
            assert {
                path: (path_identity(path), path.read_bytes())
                for path in retained_paths
            } == retained_before
            assert not admission_path.exists()


def test_second_identical_composite_is_already_live_without_new_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    preinstalled = _install_identical_runtime(
        prepared,
        tmp_path / "preinstall",
    )
    revisions_before = _runtime_revision_names(prepared.runtime_root)
    selected = str(preinstalled["versioned_config_dir"])
    selected_before = _physical_tree(
        prepared.runtime_root / "CustomConfig" / selected
    )

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_B,
        ) as held:
            assert held.result.raw_apply_status == "already_current"
            assert _disposition_value(held.result) == "COMMITTED"
            assert held.result.runtime_match_status == "matched"
            assert held.result.terminal_status == "ALREADY_LIVE"
            assert _runtime_revision_names(prepared.runtime_root) == revisions_before
            assert _physical_tree(
                prepared.runtime_root / "CustomConfig" / selected
            ) == selected_before


def test_composite_never_recursively_acquires_publication_or_runtime_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_package_lease = published_apply.lease_package_input
    real_pair_lease = published_apply.lease_controller_apply_pair
    package_depth = 0
    pair_depth = 0
    package_entries = 0
    pair_entries = 0

    @contextmanager
    def one_package_lease(*args: Any, **kwargs: Any) -> Iterator[Any]:
        nonlocal package_depth, package_entries
        assert package_depth == 0
        package_depth += 1
        package_entries += 1
        try:
            with real_package_lease(*args, **kwargs) as lease:
                yield lease
        finally:
            package_depth -= 1

    @contextmanager
    def one_pair_lease(*args: Any, **kwargs: Any) -> Iterator[Any]:
        nonlocal pair_depth, pair_entries
        assert pair_depth == 0
        pair_depth += 1
        pair_entries += 1
        try:
            with real_pair_lease(*args, **kwargs) as lease:
                yield lease
        finally:
            pair_depth -= 1

    monkeypatch.setattr(
        published_apply,
        "lease_package_input",
        one_package_lease,
    )
    monkeypatch.setattr(
        published_apply,
        "lease_controller_apply_pair",
        one_pair_lease,
    )

    def forbidden_public_reacquire(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("composite_recursive_public_lock_acquisition")

    runtime_installer = importlib.import_module("hsconfig.runtime_installer")
    runtime_match = importlib.import_module("hsconfig.runtime_package_match")
    monkeypatch.setattr(
        runtime_installer,
        "install_runtime_package",
        forbidden_public_reacquire,
    )
    monkeypatch.setattr(
        runtime_installer,
        "lease_runtime_apply",
        forbidden_public_reacquire,
    )
    monkeypatch.setattr(
        runtime_match,
        "build_runtime_package_match_report",
        forbidden_public_reacquire,
    )

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            assert held.result.runtime_match_status == "matched"
            assert package_depth == pair_depth == 1

    assert package_entries == pair_entries == 1
    assert package_depth == pair_depth == 0


def test_public_install_and_controller_pair_cannot_deadlock_on_package_runtime_locks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    runtime_apply = importlib.import_module("hsconfig.runtime_apply")
    runtime_installer = importlib.import_module("hsconfig.runtime_installer")
    output_operation_admission = importlib.import_module(
        "hsconfig.output_operation_admission"
    )
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _install_identical_runtime(prepared, tmp_path / "preinstall")

    real_exclusive_file_lock = output_operation_admission.ExclusiveFileLock
    real_output_lease = runtime_apply.lease_output_operation_admission
    real_package_lease = runtime_apply.lease_package_input
    real_install_adapter = runtime_apply.install_runtime_package
    real_runtime_lease = runtime_installer._lease_runtime_apply_after_gates
    writer_thread_id: int | None = None
    writer_trace: list[str] = []
    writer_results: list[dict[str, Any]] = []
    writer_errors: list[BaseException] = []
    writer_context_after: list[Any] = []
    writer_started = Event()
    output_attempted = Event()
    output_acquired = Event()
    package_attempted = Event()
    runtime_attempted = Event()
    writer_finished = Event()

    def patient_exclusive_file_lock(*args: Any, **kwargs: Any) -> Any:
        options = dict(kwargs)
        options["timeout_seconds"] = 600.0
        return real_exclusive_file_lock(*args, **options)

    def in_writer_thread() -> bool:
        return writer_thread_id is not None and get_ident() == writer_thread_id

    @contextmanager
    def traced_output_lease(*args: Any, **kwargs: Any) -> Iterator[Any]:
        tracing = in_writer_thread()
        if tracing:
            writer_trace.append("output_enter")
            output_attempted.set()
        with real_output_lease(*args, **kwargs) as lease:
            if tracing:
                writer_trace.append("output_held")
                output_acquired.set()
            try:
                yield lease
            finally:
                if tracing:
                    writer_trace.append("output_releasing")
        if tracing:
            writer_trace.append("output_exit")

    @contextmanager
    def traced_package_lease(*args: Any, **kwargs: Any) -> Iterator[Any]:
        tracing = in_writer_thread()
        if tracing:
            writer_trace.append("package_enter")
            package_attempted.set()
        with real_package_lease(*args, **kwargs) as lease:
            if tracing:
                writer_trace.append("package_held")
            try:
                yield lease
            finally:
                if tracing:
                    writer_trace.append("package_releasing")
        if tracing:
            writer_trace.append("package_exit")

    def traced_install_adapter(*args: Any, **kwargs: Any) -> Any:
        tracing = in_writer_thread()
        if tracing:
            writer_trace.append("adapter_enter")
        try:
            return real_install_adapter(*args, **kwargs)
        finally:
            if tracing:
                writer_trace.append("adapter_exit")

    @contextmanager
    def traced_runtime_lease(*args: Any, **kwargs: Any) -> Iterator[Any]:
        tracing = in_writer_thread()
        if tracing:
            writer_trace.append("runtime_enter")
            runtime_attempted.set()
        with real_runtime_lease(*args, **kwargs) as lease:
            if tracing:
                writer_trace.append("runtime_held")
            try:
                yield lease
            finally:
                if tracing:
                    writer_trace.append("runtime_releasing")
        if tracing:
            writer_trace.append("runtime_exit")

    def forbidden_recursive_public_installer(
        *_args: Any,
        **_kwargs: Any,
    ) -> Any:
        raise AssertionError("runtime_apply_recursive_public_installer")

    monkeypatch.setattr(
        output_operation_admission,
        "ExclusiveFileLock",
        patient_exclusive_file_lock,
    )
    monkeypatch.setattr(
        runtime_apply,
        "lease_output_operation_admission",
        traced_output_lease,
    )
    monkeypatch.setattr(
        runtime_apply,
        "lease_package_input",
        traced_package_lease,
    )
    monkeypatch.setattr(
        runtime_apply,
        "install_runtime_package",
        traced_install_adapter,
    )
    monkeypatch.setattr(
        runtime_apply,
        "_install_runtime_package",
        forbidden_recursive_public_installer,
    )
    monkeypatch.setattr(
        runtime_installer,
        "_lease_runtime_apply_after_gates",
        traced_runtime_lease,
    )

    def assert_writer_waits_at_output_lock() -> None:
        assert output_attempted.is_set()
        assert not output_acquired.is_set()
        assert not package_attempted.is_set()
        assert not runtime_attempted.is_set()
        assert not writer_finished.is_set(), writer_errors

    writer: Thread | None = None
    runtime_before_public_writer: dict[str, tuple[str, Any, bytes | None]] | None = (
        None
    )
    try:
        with _lease_published_capabilities(prepared) as capabilities:

            def public_writer() -> None:
                nonlocal writer_thread_id
                writer_thread_id = get_ident()
                writer_started.set()
                try:
                    writer_results.append(
                        runtime_apply.apply_package(
                            package_root=capabilities.output_root,
                            runtime_root=prepared.runtime_root,
                        )
                    )
                except BaseException as error:  # pragma: no cover - asserted
                    writer_errors.append(error)
                finally:
                    writer_context_after.append(
                        runtime_apply._ACTIVE_OUTPUT_OPERATION_INSTALL.get()
                    )
                    writer_finished.set()

            writer = Thread(target=public_writer)
            writer.start()
            assert writer_started.wait(5)
            assert output_attempted.wait(5)
            assert not output_acquired.wait(0.1)
            assert_writer_waits_at_output_lock()

            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_B,
            ) as held:
                assert held.result.raw_apply_status == "already_current"
                assert held.result.runtime_match_status == "matched"
                assert_writer_waits_at_output_lock()

                terminal = _terminalize_success(
                    session_lease=capabilities.session_lease,
                    held=held,
                )
                assert terminal.terminal_status == "ALREADY_LIVE"
                assert_writer_waits_at_output_lock()

                acknowledged = held.acknowledge_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=terminal,
                )
                assert acknowledged.terminal_status == "ALREADY_LIVE"
                assert_writer_waits_at_output_lock()

            assert_writer_waits_at_output_lock()
            runtime_before_public_writer = _physical_tree(prepared.runtime_root)

        assert output_acquired.wait(_THREAD_TIMEOUT)
    finally:
        if writer is not None:
            writer.join(_THREAD_TIMEOUT)

    assert writer is not None
    assert not writer.is_alive()
    assert writer_finished.is_set()
    assert writer_errors == []
    assert len(writer_results) == 1
    assert writer_results[0]["status"] == "already_current"
    assert writer_results[0]["runtime_write_performed"] is False
    assert writer_context_after == [None]
    assert runtime_before_public_writer is not None
    assert writer_trace == [
        "output_enter",
        "output_held",
        "package_enter",
        "package_held",
        "adapter_enter",
        "runtime_enter",
        "runtime_held",
        "runtime_releasing",
        "runtime_exit",
        "adapter_exit",
        "package_releasing",
        "package_exit",
        "output_releasing",
        "output_exit",
    ]
    assert _physical_tree(prepared.runtime_root) == runtime_before_public_writer


def test_runtime_drift_before_locked_apply_blocks_without_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_capture = published_apply.capture_pre_apply_runtime_snapshot
    drift_path = prepared.runtime_root / "task10-drift-after-snapshot.txt"

    def capture_then_drift(*args: Any, **kwargs: Any) -> Any:
        captured = real_capture(*args, **kwargs)
        drift_path.write_bytes(b"external drift after sealed snapshot\n")
        return captured

    monkeypatch.setattr(
        published_apply,
        "capture_pre_apply_runtime_snapshot",
        capture_then_drift,
    )
    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises((ValueError, live_start_session.SessionConflictError)):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
            ):
                pass

    assert drift_path.read_bytes() == b"external drift after sealed snapshot\n"
    assert not (prepared.runtime_root / "CustomConfig" / "deck_config.ini").exists()
    assert _runtime_revision_names(prepared.runtime_root) == set()
    assert not runtime_transaction_journal_path(
        prepared.runtime_root,
        _ATTEMPT_A,
    ).exists()


def test_runtime_lock_prevents_mutation_between_apply_and_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_match = published_apply.build_runtime_package_match_report_from_pair
    contender: tuple[Thread, Event, Event, list[BaseException]] | None = None
    mutation_path = prepared.runtime_root / "task10-competing-runtime-write.txt"

    with _lease_published_capabilities(prepared) as capabilities:

        def match_while_runtime_writer_waits(*args: Any, **kwargs: Any) -> Any:
            nonlocal contender
            contender = _start_lock_contender(
                lock_path=prepared.runtime_root / ".hsconfig" / "apply.lock",
                mutate=lambda: mutation_path.write_bytes(b"after lock release\n"),
            )
            assert not contender[2].wait(0.1)
            return real_match(*args, **kwargs)

        monkeypatch.setattr(
            published_apply,
            "build_runtime_package_match_report_from_pair",
            match_while_runtime_writer_waits,
        )
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            assert held.result.runtime_match_status == "matched"
            assert contender is not None
            assert not contender[2].is_set()
            assert not mutation_path.exists()

    assert contender is not None
    _join_contender(contender[0], contender[2], contender[3])
    assert mutation_path.read_bytes() == b"after lock release\n"


def test_crash_after_nonowning_installer_return_recovers_exact_retained_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _install_identical_runtime(prepared, tmp_path / "preinstall")
    crashed = Event()

    def crash_after_return(point: Any) -> None:
        if _point_value(point) == "after_installer_return_before_apply_committed":
            crashed.set()
            raise RuntimeError("crash-after-nonowning-installer-return")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-after-nonowning-installer-return$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_B,
                fault_hook=crash_after_return,
            ):
                pass
        assert crashed.is_set()

    journal_path = runtime_transaction_journal_path(
        prepared.runtime_root,
        _ATTEMPT_B,
    )
    journal_raw = journal_path.read_bytes()
    journal_identity = path_identity(journal_path)
    journal_value = json.loads(journal_raw)
    assert journal_value["transaction_id"] == _ATTEMPT_B
    assert journal_value["owns_target"] is False

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered.retained_journal_path == journal_path
    assert recovered.retained_journal_identity == journal_identity
    assert recovered.retained_journal_sha256 == (
        "sha256:" + sha256(journal_raw).hexdigest()
    )
    assert recovered.physical_disposition.value == "COMMITTED"
    assert recovered.runtime_match_status == "matched"


def test_recovery_rebinds_session_receipt_profile_publication_snapshot_and_exact_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_before_apply_committed(point: Any) -> None:
        if _point_value(point) == "after_installer_return_before_apply_committed":
            raise RuntimeError("crash-before-authority-rebind")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-authority-rebind$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_before_apply_committed,
            ):
                pass

    from hsconfig.operator_profile import load_operator_profile
    from hsconfig.runtime_live_admission import (
        load_runtime_live_attempt_admission,
    )

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    admission = load_runtime_live_attempt_admission()
    invocation_path = prepared.session_root / "receipts" / "apply_invocation.json"
    invocation_raw = invocation_path.read_bytes()
    invocation = published_apply.load_apply_invocation(
        invocation_path,
        expected_parent_identity=path_identity(invocation_path.parent),
    )
    profile = load_operator_profile()
    publication = interrupted.publication_binding
    child = interrupted.output_child_binding
    operation = interrupted.output_operation_admission_binding
    assert admission is not None
    assert invocation.content_sha256 == interrupted.apply_invocation_sha256
    assert invocation.content_sha256 == admission.apply_invocation_sha256
    assert isinstance(publication, Mapping)
    assert isinstance(child, Mapping)
    assert isinstance(operation, Mapping)
    assert interrupted.artifact_bindings["receipts/apply_invocation.json"] == (
        "sha256:" + sha256(invocation_raw).hexdigest()
    )
    context_checks = 0
    parity_transactions: list[str] = []
    real_context = published_apply._require_recovery_invocation_context
    real_parity = (
        published_apply.revalidate_committed_runtime_control_plane_from_pair
    )

    def trace_context(*args: Any, **kwargs: Any) -> Any:
        nonlocal context_checks
        context_checks += 1
        bound_invocation = kwargs["invocation"]
        package_lease = kwargs["package_lease"]
        bound_admission = kwargs["runtime_admission"]
        assert package_lease.publication is not None
        assert bound_invocation.canonical_json == invocation_raw
        assert kwargs["cursor"] == interrupted
        assert kwargs["profile_lease"].profile.content_sha256 == (
            profile.content_sha256
        )
        assert bound_invocation.operator_profile_sha256 == profile.content_sha256
        assert bound_invocation.publication_revision == publication["revision"]
        assert bound_invocation.publication_revision == (
            package_lease.publication.revision
        )
        assert bound_invocation.publication_content_root_sha256 == (
            publication["content_root_sha256"]
        )
        assert bound_invocation.publication_content_root_sha256 == (
            bound_admission.package_root_sha256
        )
        assert bound_invocation.output_child_path == Path(
            str(child["output_child_path"])
        )
        assert bound_invocation.output_child_identity == tuple(
            child["output_child_identity"]
        )
        assert bound_invocation.output_operation_admission_sha256 == (
            operation["admission_sha256"]
        )
        assert bound_invocation.pre_apply_runtime_snapshot.content_sha256 == (
            bound_admission.pre_apply_runtime_snapshot_sha256
        )
        assert bound_invocation.apply_attempt_id == _ATTEMPT_A
        return real_context(*args, **kwargs)

    def trace_parity(*args: Any, **kwargs: Any) -> Any:
        parity_transactions.append(str(kwargs["transaction_id"]))
        assert kwargs["runtime_admission"] == admission
        assert kwargs["expected_recovery"].value == interrupted.apply_recovery
        return real_parity(*args, **kwargs)

    monkeypatch.setattr(
        published_apply,
        "_require_recovery_invocation_context",
        trace_context,
    )
    monkeypatch.setattr(
        published_apply,
        "revalidate_committed_runtime_control_plane_from_pair",
        trace_parity,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered.retained_journal_path is not None
    retained_journal = json.loads(recovered.retained_journal_path.read_bytes())
    assert context_checks == 1
    assert parity_transactions == [_ATTEMPT_A]
    assert retained_journal["transaction_id"] == _ATTEMPT_A
    assert recovered.raw_apply_status == "recovered"
    assert _disposition_value(recovered) == "COMMITTED"
    assert recovered.runtime_match_status == "matched"


def test_nonterminal_recovery_reaches_recovered_match_without_terminal_result_freeze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    crashed = Event()

    def crash_before_apply_committed(point: Any) -> None:
        if _point_value(point) == "after_installer_return_before_apply_committed":
            crashed.set()
            raise RuntimeError("crash-before-apply-committed")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(RuntimeError, match="^crash-before-apply-committed$"):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_before_apply_committed,
            ):
                pass
        assert crashed.is_set()

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert interrupted.phase is live_start_session.LiveStartPhase.APPLY_STARTED
    assert isinstance(interrupted.apply_recovery, Mapping)
    assert interrupted.apply_recovery["stable_physical_disposition"] == "COMMITTED"
    assert interrupted.result_intent is None
    assert interrupted.terminal_status is None

    from hsconfig.operator_profile import (
        lease_operator_profile,
        load_operator_profile,
    )
    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
    )

    with live_start_session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        expected = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                with published_apply.recover_apply_attempt_under_lock(
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    output_operation_lease=operation_lease,
                    expected_session=expected,
                ) as recovered:
                    assert recovered.updated_session is recovered.held.updated_session
                    assert recovered.held.result.raw_apply_status == "recovered"
                    assert _disposition_value(recovered.held.result) == "COMMITTED"
                    assert recovered.held.result.runtime_match_status == "matched"
                    assert recovered.updated_session.result_intent is None
                    assert recovered.updated_session.terminal_status is None

    persisted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert persisted.phase is live_start_session.LiveStartPhase.RUNTIME_MATCHED
    assert isinstance(persisted.apply_recovery, Mapping)
    assert persisted.apply_recovery["recovery_stage"] == "CLOSED"
    assert persisted.result_intent is None
    assert persisted.terminal_status is None


def test_recovery_context_yields_updated_session_cursor_without_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_before_apply_committed(point: Any) -> None:
        if _point_value(point) == "after_installer_return_before_apply_committed":
            raise RuntimeError("crash-before-cursor-lineage-recovery")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-cursor-lineage-recovery$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_before_apply_committed,
            ):
                pass

    from hsconfig.operator_profile import (
        lease_operator_profile,
        load_operator_profile,
    )
    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
    )

    real_pair_lease = published_apply.lease_controller_apply_pair
    real_advance = (
        live_start_session.advance_nonterminal_apply_recovery_under_lock
    )
    pair_entry_cursors: list[Any] = []
    closed_successors: list[Any] = []

    @contextmanager
    def trace_pair_entry(*args: Any, **kwargs: Any) -> Iterator[Any]:
        pair_entry_cursors.append(kwargs["expected_session"])
        assert kwargs["expected_session"] is expected
        with real_pair_lease(*args, **kwargs) as pair:
            yield pair

    def trace_recovery_advance(*args: Any, **kwargs: Any) -> Any:
        successor = real_advance(*args, **kwargs)
        if kwargs["transition"] == "recovery_closed":
            closed_successors.append(successor)
        return successor

    monkeypatch.setattr(
        published_apply,
        "lease_controller_apply_pair",
        trace_pair_entry,
    )
    monkeypatch.setattr(
        live_start_session,
        "advance_nonterminal_apply_recovery_under_lock",
        trace_recovery_advance,
    )

    with live_start_session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        expected = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                with published_apply.recover_apply_attempt_under_lock(
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    output_operation_lease=operation_lease,
                    expected_session=expected,
                ) as recovered:
                    assert len(closed_successors) == 1
                    assert recovered.updated_session is closed_successors[0]
                    assert recovered.held.updated_session is closed_successors[0]

    assert pair_entry_cursors == [expected]
    assert len(closed_successors) == 1


def test_recovery_resume_under_one_session_lease_never_reacquires(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_before_apply_committed(point: Any) -> None:
        if _point_value(point) == "after_installer_return_before_apply_committed":
            raise RuntimeError("crash-before-single-lease-recovery")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-single-lease-recovery$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_before_apply_committed,
            ):
                pass

    from hsconfig.operator_profile import (
        lease_operator_profile,
        load_operator_profile,
    )
    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
    )

    lease_session = live_start_session.lease_live_start_session
    with lease_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        expected = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )

        def forbid_session_reacquire(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            raise AssertionError("recovery-must-not-reacquire-session-lease")

        monkeypatch.setattr(
            published_apply.live_start_session,
            "lease_live_start_session",
            forbid_session_reacquire,
        )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                with published_apply.recover_apply_attempt_under_lock(
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    output_operation_lease=operation_lease,
                    expected_session=expected,
                ) as recovered:
                    assert recovered.held.result.raw_apply_status == "recovered"
                    assert recovered.held.result.runtime_match_status == "matched"


def test_nonterminal_recovery_threads_one_step_receipt_per_physical_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    crashed = Event()

    def crash_after_admission_bound(point: Any) -> None:
        if _point_value(point) == "after_admission_bound_before_invocation_write":
            crashed.set()
            raise RuntimeError("crash-after-admission-bound")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-after-admission-bound$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_admission_bound,
            ):
                pass
        assert crashed.is_set()

    physical_receipts: list[Any] = []
    consumed_receipts: list[Any] = []
    real_recover = published_apply.recover_runtime_attempt_from_pair
    real_advance = live_start_session.advance_nonterminal_apply_recovery_under_lock

    def trace_physical_step(*args: Any, **kwargs: Any) -> Any:
        result = real_recover(*args, **kwargs)
        if kwargs.get("nonterminal_recovery_authorization") is not None:
            assert result.apply_recovery_step_receipt is not None
            physical_receipts.append(result.apply_recovery_step_receipt)
        return result

    def trace_receipt_cas(*args: Any, **kwargs: Any) -> Any:
        predecessor = kwargs["expected_recovery_session"]
        result = real_advance(*args, **kwargs)
        if kwargs.get("transition") == "physical_recovery_advanced":
            receipt = kwargs.get("physical_step_receipt")
            assert receipt is physical_receipts[len(consumed_receipts)]
            before = predecessor.apply_recovery
            after = result.apply_recovery
            assert isinstance(before, Mapping)
            assert isinstance(after, Mapping)
            assert after["action_index"] == int(before["action_index"]) + 1
            consumed_receipts.append(receipt)
        return result

    monkeypatch.setattr(
        published_apply,
        "recover_runtime_attempt_from_pair",
        trace_physical_step,
    )
    monkeypatch.setattr(
        live_start_session,
        "advance_nonterminal_apply_recovery_under_lock",
        trace_receipt_cas,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered.runtime_match_status == "matched"
    assert len(physical_receipts) > 1
    assert consumed_receipts == physical_receipts
    assert len({id(receipt) for receipt in consumed_receipts}) == len(
        consumed_receipts
    )


def test_recovery_callback_failure_before_consume_discards_slot_without_classifying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    crashed = Event()

    def crash_after_first_nonterminal_recovery_cursor_cas(point: Any) -> None:
        if (
            _point_value(point) == "after_nonterminal_recovery_cursor_cas"
            and not crashed.is_set()
        ):
            crashed.set()
            raise RuntimeError("crash-before-slot-discard-recovery")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-slot-discard-recovery$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_first_nonterminal_recovery_cursor_cas,
            ):
                pass
        assert crashed.is_set()

    from hsconfig.operator_profile import (
        lease_operator_profile,
        load_operator_profile,
    )
    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
    )

    classification_calls = 0

    class PreconsumeRecoveryAbort(BaseException):
        pass

    def fail_before_consume(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise PreconsumeRecoveryAbort("preconsume-recovery-callback-failed")

    def forbid_classification(*args: Any, **kwargs: Any) -> Any:
        nonlocal classification_calls
        del args, kwargs
        classification_calls += 1
        raise AssertionError("unused authorization reached failure classification")

    with live_start_session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        expected = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        recovery = expected.apply_recovery
        assert isinstance(recovery, Mapping)
        assert recovery["recovery_stage"] == "ACTIVE"
        assert (
            recovery["expected_action"]
            in live_start_session.RUNTIME_APPLY_RECOVERY_ACTIONS
        )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                with monkeypatch.context() as failure_patch:
                    failure_patch.setattr(
                        published_apply,
                        "recover_runtime_attempt_from_pair",
                        fail_before_consume,
                    )
                    failure_patch.setattr(
                        published_apply,
                        "classify_runtime_failure_from_pair",
                        forbid_classification,
                    )
                    with pytest.raises(
                        PreconsumeRecoveryAbort,
                        match="^preconsume-recovery-callback-failed$",
                    ):
                        with published_apply.recover_apply_attempt_under_lock(
                            session_lease=session_lease,
                            profile_lease=profile_lease,
                            output_operation_lease=operation_lease,
                            expected_session=expected,
                        ):
                            pass

                assert classification_calls == 0
                unchanged = live_start_session.load_live_start_session_under_lock(
                    session_lease=session_lease
                )
                assert unchanged.canonical_json == expected.canonical_json
                with published_apply.recover_apply_attempt_under_lock(
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    output_operation_lease=operation_lease,
                    expected_session=unchanged,
                ) as recovered:
                    assert recovered.held.result.runtime_match_status == "matched"


def test_postconsume_failure_selects_terminal_observation_and_resume_uses_only_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hsconfig.runtime_installer as runtime_installer
    from tests.test_runtime_installer import _exercise_prior_owner_route

    published_apply = _published_apply()
    route = _exercise_prior_owner_route(
        tmp_path,
        monkeypatch,
        max_actions=4,
    )
    failed_action = str(route.recovery["expected_action"])
    assert route.actions[-1] == "commit_bound_prior_owner_planned_attempt_record"
    assert failed_action == "materialize_file_action_staging"
    assert route.recovery["recovery_stage"] == "ACTIVE"

    real_execute = runtime_installer._execute_apply_recovery_physical_step
    real_discard = (
        live_start_session._discard_unused_nonterminal_apply_recovery_authorization
    )
    real_classify = runtime_installer.classify_runtime_failure_from_pair
    real_observe_selection = (
        runtime_installer.observe_runtime_failure_selection_from_pair
    )
    real_authorize_observation = (
        live_start_session._authorize_runtime_observation_under_lock
    )
    real_advance = live_start_session.advance_nonterminal_apply_recovery_under_lock
    real_drive = published_apply._drive_recovery_rows
    real_recover = published_apply.recover_runtime_attempt_from_pair

    trace: list[str] = []
    initial_selections: list[Any] = []
    fresh_selections: list[Any] = []
    selection_receipts: list[Any] = []
    selected_cursors: list[Any] = []

    class PostConsumePhysicalFailure(RuntimeError):
        pass

    def fail_physical_callback_after_consume(
        *,
        recovery_authorization: Any,
        action: Any,
        physical_action: Any,
        fault_hook: Any,
    ) -> Any:
        del physical_action

        def fail_after_consume() -> Any:
            trace.append("physical_callback_after_consume")
            raise PostConsumePhysicalFailure("postconsume-physical-callback-failed")

        return real_execute(
            recovery_authorization=recovery_authorization,
            action=action,
            physical_action=fail_after_consume,
            fault_hook=fault_hook,
        )

    def trace_discard(*args: Any, **kwargs: Any) -> bool:
        discarded = real_discard(*args, **kwargs)
        trace.append(f"discard:{discarded}")
        return discarded

    def trace_initial_classification(*args: Any, **kwargs: Any) -> Any:
        trace.append("initial_classify")
        selection = real_classify(*args, **kwargs)
        initial_selections.append(selection)
        return selection

    def trace_fresh_terminal_reobservation(*args: Any, **kwargs: Any) -> Any:
        trace.append("fresh_terminal_reobserve")
        selection = real_classify(*args, **kwargs)
        fresh_selections.append(selection)
        return selection

    def trace_terminal_observation_authorization(
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        authorization = real_authorize_observation(*args, **kwargs)
        if kwargs.get("observation_family") == "terminal_classification":
            trace.append("terminal_observation_authorized")
        return authorization

    def trace_terminal_observation(*args: Any, **kwargs: Any) -> Any:
        trace.append("terminal_observation_enter")
        receipt = real_observe_selection(*args, **kwargs)
        trace.append("terminal_observation_receipt")
        selection_receipts.append(receipt)
        return receipt

    def trace_selection_cas(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("transition") != "select_terminal_classification":
            return real_advance(*args, **kwargs)
        assert len(selection_receipts) == 1
        assert kwargs.get("physical_step_receipt") is None
        assert kwargs.get("recovery_evidence") is None
        assert kwargs.get("recovery_authorization") is None
        assert kwargs.get("runtime_observation_receipt") is selection_receipts[0]
        cursor = real_advance(*args, **kwargs)
        trace.append("selection_cas")
        selected_cursors.append(cursor)
        return cursor

    def crash_after_selection_cas(point: Any) -> None:
        if _point_value(point) != "after_terminal_classification_selection_cas":
            return
        trace.append("crash_after_selection_cas")
        raise RuntimeError("crash-after-terminal-selection-cas")

    def drive_with_selection_crash(*args: Any, **kwargs: Any) -> Any:
        kwargs["fault_hook"] = crash_after_selection_cas
        return real_drive(*args, **kwargs)

    with monkeypatch.context() as failure_patch:
        failure_patch.setattr(
            runtime_installer,
            "_execute_apply_recovery_physical_step",
            fail_physical_callback_after_consume,
        )
        failure_patch.setattr(
            live_start_session,
            "_discard_unused_nonterminal_apply_recovery_authorization",
            trace_discard,
        )
        failure_patch.setattr(
            published_apply,
            "classify_runtime_failure_from_pair",
            trace_initial_classification,
        )
        failure_patch.setattr(
            runtime_installer,
            "classify_runtime_failure_from_pair",
            trace_fresh_terminal_reobservation,
        )
        failure_patch.setattr(
            live_start_session,
            "_authorize_runtime_observation_under_lock",
            trace_terminal_observation_authorization,
        )
        failure_patch.setattr(
            published_apply,
            "observe_runtime_failure_selection_from_pair",
            trace_terminal_observation,
        )
        failure_patch.setattr(
            live_start_session,
            "advance_nonterminal_apply_recovery_under_lock",
            trace_selection_cas,
        )
        failure_patch.setattr(
            published_apply,
            "_drive_recovery_rows",
            drive_with_selection_crash,
        )

        with pytest.raises(
            RuntimeError,
            match="^crash-after-terminal-selection-cas$",
        ):
            published_apply.recover_apply_attempt(
                session_root=route.fixture.pipeline.session_root
            )

    assert trace == [
        "physical_callback_after_consume",
        "discard:False",
        "initial_classify",
        "terminal_observation_authorized",
        "terminal_observation_enter",
        "fresh_terminal_reobserve",
        "terminal_observation_receipt",
        "selection_cas",
        "crash_after_selection_cas",
    ]
    assert len(initial_selections) == 1
    assert len(fresh_selections) == 1
    initial_selection = initial_selections[0]
    fresh_selection = fresh_selections[0]
    for selection in (initial_selection, fresh_selection):
        assert selection.disposition == "select_terminal_observation"
        assert selection.selected_observation == "observe_not_committed"
        assert selection.expected_recovery_sha256 == route.recovery["content_sha256"]
        assert selection.expected_action_index == route.recovery["action_index"]
        assert selection.expected_action == failed_action
    assert initial_selection == fresh_selection
    assert len(selected_cursors) == 1

    selected = selected_cursors[0]
    persisted = live_start_session.load_live_start_session(
        route.fixture.pipeline.session_root,
        local_app_data_root=route.fixture.pipeline.local_app_data,
    )
    assert persisted.canonical_json == selected.canonical_json
    assert persisted.session_identity == selected.session_identity
    assert persisted.phase is live_start_session.LiveStartPhase.APPLY_STARTED
    assert persisted.result_intent is None
    assert persisted.terminal_status is None
    selected_recovery = persisted.apply_recovery
    assert isinstance(selected_recovery, Mapping)
    assert selected_recovery["recovery_stage"] == "ACTIVE"
    assert selected_recovery["expected_action"] == "observe_not_committed"
    assert selected_recovery["action_index"] == route.recovery["action_index"] + 1
    for field, value in route.recovery.items():
        if field not in {"action_index", "expected_action", "content_sha256"}:
            assert selected_recovery[field] == value

    resume_actions: list[str] = []

    def trace_resume_action(*args: Any, **kwargs: Any) -> Any:
        authorization = kwargs.get("nonterminal_recovery_authorization")
        if authorization is not None:
            resume_actions.append(str(authorization._opaque.action))
        return real_recover(*args, **kwargs)

    def forbid_resume_path(label: str) -> Any:
        def forbidden(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            raise AssertionError(f"selected recovery resumed through {label}")

        return forbidden

    with monkeypatch.context() as resume_patch:
        resume_patch.setattr(
            published_apply,
            "recover_runtime_attempt_from_pair",
            trace_resume_action,
        )
        resume_patch.setattr(
            published_apply,
            "classify_runtime_failure_from_pair",
            forbid_resume_path("failure classification"),
        )
        resume_patch.setattr(
            published_apply,
            "observe_runtime_failure_selection_from_pair",
            forbid_resume_path("terminal selection observation"),
        )
        resume_patch.setattr(
            published_apply,
            "_prepare_initial_recovery",
            forbid_resume_path("initial recovery"),
        )
        resume_patch.setattr(
            published_apply,
            "_claim_runtime_admission",
            forbid_resume_path("runtime admission claim"),
        )
        resume_patch.setattr(
            live_start_session,
            "prepare_apply_attempt_under_lock",
            forbid_resume_path("second apply"),
        )

        recovered = published_apply.recover_apply_attempt(
            session_root=route.fixture.pipeline.session_root
        )

    assert resume_actions == ["observe_not_committed"]
    assert failed_action not in resume_actions
    assert recovered.raw_apply_status is None
    assert _disposition_value(recovered) == "NOT_COMMITTED"
    assert recovered.runtime_match_status == "not_run"
    assert recovered.terminal_status == "FAILED_PRESERVED"
    assert recovered.error_code == "apply_not_committed"


def test_recovery_cas_records_apply_committed_then_runtime_matched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_before_apply_committed(point: Any) -> None:
        if _point_value(point) == "after_installer_return_before_apply_committed":
            raise RuntimeError("crash-before-ordered-recovery")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-ordered-recovery$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_before_apply_committed,
            ):
                pass

    transitions: list[str] = []
    real_advance = live_start_session.advance_nonterminal_apply_recovery_under_lock
    real_match = published_apply.build_runtime_package_match_report_from_pair
    match_calls = 0

    def trace_transition(*args: Any, **kwargs: Any) -> Any:
        result = real_advance(*args, **kwargs)
        transitions.append(str(kwargs["transition"]))
        return result

    def crash_first_match(*args: Any, **kwargs: Any) -> Any:
        nonlocal match_calls
        match_calls += 1
        if match_calls == 1:
            raise RuntimeError("crash-after-apply-committed")
        return real_match(*args, **kwargs)

    monkeypatch.setattr(
        live_start_session,
        "advance_nonterminal_apply_recovery_under_lock",
        trace_transition,
    )
    monkeypatch.setattr(
        published_apply,
        "build_runtime_package_match_report_from_pair",
        crash_first_match,
    )

    with pytest.raises(RuntimeError, match="^crash-after-apply-committed$"):
        published_apply.recover_apply_attempt(session_root=prepared.session_root)

    committed = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert committed.phase is live_start_session.LiveStartPhase.APPLY_COMMITTED
    assert isinstance(committed.apply_recovery, Mapping)
    assert committed.apply_recovery["stable_physical_disposition"] == "COMMITTED"
    assert committed.apply_recovery["runtime_match_status"] == "unknown"
    assert committed.apply_recovery["runtime_match_sha256"] is None

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered.runtime_match_status == "matched"
    assert transitions == [
        "apply_committed",
        "runtime_matched",
        "recovery_closed",
    ]
    assert match_calls == 2


def test_recovery_commit_requires_receipt_state_ini_match_and_current_parity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_before_apply_committed(point: Any) -> None:
        if _point_value(point) == "after_installer_return_before_apply_committed":
            raise RuntimeError("crash-before-parity-recovery")

    with _lease_published_capabilities(prepared) as capabilities:
        output_root = capabilities.output_root
        with pytest.raises(
            RuntimeError,
            match="^crash-before-parity-recovery$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_before_apply_committed,
            ):
                pass

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    recovery = interrupted.apply_recovery
    assert interrupted.phase is live_start_session.LiveStartPhase.APPLY_STARTED
    assert isinstance(recovery, Mapping)
    assert recovery["stable_physical_disposition"] == "COMMITTED"
    journal_path = Path(str(recovery["predecessor_journal_path"]))
    journal = json.loads(journal_path.read_bytes())
    state_key = str(journal["state_key"])
    parity_paths = (
        prepared.runtime_root
        / ".hsconfig"
        / "receipts"
        / state_key
        / "last_apply_receipt.json",
        prepared.runtime_root / ".hsconfig" / "state.json",
        prepared.runtime_root / "CustomConfig" / "deck_config.ini",
    )
    session_path = prepared.session_root / "session.json"
    interrupted_raw = session_path.read_bytes()

    for parity_path in parity_paths:
        original = parity_path.read_bytes()
        parity_path.write_bytes(original + b"\n")
        with pytest.raises(ValueError):
            published_apply.recover_apply_attempt(
                session_root=prepared.session_root
            )
        assert session_path.read_bytes() == interrupted_raw
        parity_path.write_bytes(original)

    current_path = output_root / "current.json"
    original_current = current_path.read_bytes()
    alternate_revision, alternate_current = _stage_alternate_publication(
        tmp_path / "alternate-current"
    )
    _copy_alternate_revision(
        source_revision=alternate_revision,
        output_root=output_root,
    )
    current_path.write_bytes(alternate_current)
    with pytest.raises(ValueError):
        published_apply.recover_apply_attempt(session_root=prepared.session_root)
    assert session_path.read_bytes() == interrupted_raw
    current_path.write_bytes(original_current)

    _mutate_one_runtime_json(prepared.runtime_root, "task10_post_commit_mismatch")
    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert _disposition_value(recovered) == "COMMITTED"
    assert recovered.runtime_match_status == "mismatch"
    assert recovered.runtime_match_sha256 is not None
    assert recovered.terminal_status == "APPLIED_BUT_NOT_VERIFIED"
    assert recovered.error_code == "runtime_mismatch"


def test_receipt_or_apply_started_without_admission_is_nonterminal_tamper_and_never_applies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    crashed = Event()

    def crash_after_output_handoff(point: Any) -> None:
        if _point_value(point) == "after_output_operation_admission_unlink":
            crashed.set()
            raise RuntimeError("crash-after-output-handoff")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(RuntimeError, match="^crash-after-output-handoff$"):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_output_handoff,
            ):
                pass
        assert crashed.is_set()

    from hsconfig.runtime_live_admission import (
        load_runtime_live_attempt_admission,
    )

    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    admission.admission_path.unlink()
    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert interrupted.phase is live_start_session.LiveStartPhase.APPLY_STARTED
    assert interrupted.apply_recovery is None
    session_raw = (prepared.session_root / "session.json").read_bytes()
    runtime_tree = _physical_tree(prepared.runtime_root)

    def forbid_recovery(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("physical-recovery-must-not-run")

    monkeypatch.setattr(
        published_apply,
        "recover_runtime_attempt_from_pair",
        forbid_recovery,
    )
    with pytest.raises(
        live_start_session.SessionCapabilityError,
        match="^published_apply_runtime_admission_missing$",
    ):
        published_apply.recover_apply_attempt(session_root=prepared.session_root)

    assert (prepared.session_root / "session.json").read_bytes() == session_raw
    assert _physical_tree(prepared.runtime_root) == runtime_tree
    preserved = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert preserved == interrupted
    assert preserved.result_intent is None
    assert preserved.terminal_status is None


def test_prepared_without_admission_rolls_back_before_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    crashed = Event()

    def crash_after_invocation_prepare(point: Any) -> None:
        if _point_value(point) == "after_invocation_prepared_before_admission":
            crashed.set()
            raise RuntimeError("crash-after-invocation-prepare")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-after-invocation-prepare$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_invocation_prepare,
            ):
                pass
        assert crashed.is_set()

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert interrupted.phase is live_start_session.LiveStartPhase.PUBLICATION_COMMITTED
    assert isinstance(interrupted.pending_transition, Mapping)
    assert interrupted.pending_transition["operation"] == "install_apply_invocation"
    assert interrupted.pending_transition["stage"] == "PREPARED"
    assert interrupted.apply_recovery is None
    from hsconfig.runtime_live_admission import (
        load_runtime_live_attempt_admission,
    )

    assert load_runtime_live_attempt_admission() is None
    runtime_tree = _physical_tree(prepared.runtime_root)

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert isinstance(recovered, published_apply.RecoverApplyNotStarted)
    assert recovered.status == "apply_not_started"
    assert recovered.run_id == interrupted.run_id
    assert recovered.session_root == prepared.session_root
    assert recovered.runtime_write_performed is False
    persisted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert persisted.phase is live_start_session.LiveStartPhase.PUBLICATION_COMMITTED
    assert persisted.pending_transition is None
    assert persisted.apply_invocation_sha256 is None
    assert persisted.runtime_admission_binding is None
    assert persisted.runtime_layout_bootstrap is None
    assert persisted.apply_recovery is None
    assert persisted.result_intent is None
    assert persisted.terminal_status is None
    assert recovered.persisted_session_sha256 == persisted.content_sha256
    assert _physical_tree(prepared.runtime_root) == runtime_tree


def test_prepared_apply_not_started_missing_apply_lock_fails_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_after_invocation_prepare(point: Any) -> None:
        if _point_value(point) == "after_invocation_prepared_before_admission":
            raise RuntimeError("crash-after-invocation-prepare")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-after-invocation-prepare$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_invocation_prepare,
            ):
                pass

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    pending = interrupted.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["stage"] == "PREPARED"
    apply_lock = prepared.runtime_root / ".hsconfig" / "apply.lock"
    assert apply_lock.read_bytes() == b""
    apply_lock.unlink()
    before = _physical_tree(tmp_path)

    with pytest.raises(ValueError, match="^runtime_apply_lock_invalid$"):
        published_apply.recover_apply_attempt(
            session_root=prepared.session_root
        )

    assert _physical_tree(tmp_path) == before
    assert not apply_lock.exists()
    preserved = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert preserved == interrupted


def test_prepared_staged_only_recovery_cleans_and_returns_apply_not_started(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    crashed = Event()

    def crash_after_admission_staging(point: Any) -> None:
        if (
            _point_value(point)
            == "after_runtime_admission_staging_flush_before_staging_bound_cas"
        ):
            crashed.set()
            raise RuntimeError("crash-after-admission-staging")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-after-admission-staging$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_admission_staging,
            ):
                pass
        assert crashed.is_set()

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    pending = interrupted.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["stage"] == "PREPARED"
    staging_path = Path(str(pending["runtime_admission_staging_path"]))
    inner_path = Path(str(pending["runtime_admission_staging_inner_temp_path"]))
    final_path = Path(str(pending["runtime_admission_path"]))
    assert staging_path.is_file()
    assert not inner_path.exists()
    assert not final_path.exists()
    runtime_tree = _physical_tree(prepared.runtime_root)

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert isinstance(recovered, published_apply.RecoverApplyNotStarted)
    assert recovered.runtime_write_performed is False
    assert not staging_path.exists()
    assert not inner_path.exists()
    assert not final_path.exists()
    persisted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert persisted.phase is live_start_session.LiveStartPhase.PUBLICATION_COMMITTED
    assert persisted.pending_transition is None
    assert persisted.apply_invocation_sha256 is None
    assert persisted.runtime_admission_binding is None
    assert persisted.apply_recovery is None
    assert recovered.persisted_session_sha256 == persisted.content_sha256
    assert _physical_tree(prepared.runtime_root) == runtime_tree


def test_public_recovery_returns_closed_apply_not_started_union_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    with _lease_published_capabilities(prepared) as capabilities:
        expected = capabilities.expected_session
        session_root_identity = capabilities.session_lease.session_root_identity
    session_raw = (prepared.session_root / "session.json").read_bytes()
    runtime_tree = _physical_tree(prepared.runtime_root)

    def forbid_profile_load(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("clean-no-start-must-not-load-profile")

    monkeypatch.setattr(
        published_apply,
        "load_operator_profile",
        forbid_profile_load,
    )
    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered == published_apply.RecoverApplyNotStarted(
        status="apply_not_started",
        run_id=expected.run_id,
        session_root=prepared.session_root,
        session_root_identity=session_root_identity,
        persisted_session_sha256=expected.content_sha256,
        runtime_write_performed=False,
    )
    assert (prepared.session_root / "session.json").read_bytes() == session_raw
    assert _physical_tree(prepared.runtime_root) == runtime_tree


def test_public_recovery_rejects_self_derived_foreign_session_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path / "primary", monkeypatch)
    with _lease_published_capabilities(prepared):
        pass
    foreign_root = (
        tmp_path
        / "foreign-local"
        / "HSConfig"
        / "runs"
        / prepared.session_root.name
    )
    shutil.copytree(prepared.session_root, foreign_root)
    foreign_lock = (
        foreign_root.parent.parent
        / "locks"
        / f"live-start-{foreign_root.name}.lock"
    )
    foreign_lock.parent.mkdir(parents=True)
    shutil.copy2(
        prepared.session_root.parent.parent
        / "locks"
        / f"live-start-{prepared.session_root.name}.lock",
        foreign_lock,
    )
    foreign_session_raw = (foreign_root / "session.json").read_bytes()

    with pytest.raises(
        live_start_session.SessionValidationError,
        match="^live_start_session_root_not_canonical$",
    ):
        published_apply.recover_apply_attempt(session_root=foreign_root)

    assert (foreign_root / "session.json").read_bytes() == foreign_session_raw


def test_admission_before_receipt_prepares_one_bound_recovery_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    crashed = Event()

    def crash_after_admission_bound(point: Any) -> None:
        if _point_value(point) == "after_admission_bound_before_invocation_write":
            crashed.set()
            raise RuntimeError("crash-after-admission-bound")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(RuntimeError, match="^crash-after-admission-bound$"):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_admission_bound,
            ):
                pass
        assert crashed.is_set()

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    pending = interrupted.pending_transition
    assert interrupted.phase is live_start_session.LiveStartPhase.PUBLICATION_COMMITTED
    assert isinstance(pending, Mapping)
    assert pending["stage"] == "PRIMARY_APPLIED"
    assert interrupted.runtime_layout_bootstrap is None
    assert not (prepared.session_root / "receipts" / "apply_invocation.json").exists()
    from hsconfig.runtime_live_admission import (
        load_runtime_live_attempt_admission,
    )

    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == _ATTEMPT_A
    observed_attempts: list[str] = []
    real_observe = published_apply.observe_initial_runtime_install_from_pair

    def trace_first_install(*args: Any, **kwargs: Any) -> Any:
        observed_attempts.append(str(kwargs["transaction_id"]))
        return real_observe(*args, **kwargs)

    monkeypatch.setattr(
        published_apply,
        "observe_initial_runtime_install_from_pair",
        trace_first_install,
    )
    monkeypatch.setattr(
        live_start_session,
        "prepare_apply_attempt_under_lock",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("recovery-must-not-prepare-second-apply")
        ),
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered.raw_apply_status == "recovered"
    assert _disposition_value(recovered) == "COMMITTED"
    assert recovered.runtime_match_status == "matched"
    assert observed_attempts == [_ATTEMPT_A]
    persisted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert persisted.phase is live_start_session.LiveStartPhase.RUNTIME_MATCHED
    assert persisted.terminal_status == "LIVE_AND_MATCHED"
    assert persisted.pending_transition is None
    assert persisted.apply_recovery is None
    assert persisted.closed_apply_recovery_commitment is None
    assert isinstance(persisted.result_intent, Mapping)
    assert persisted.result_intent["apply_attempt_id"] == _ATTEMPT_A


@pytest.mark.parametrize(
    "crash_point",
    (
        "after_runtime_admission_staging_bound",
        "after_runtime_admission_bound_commit_before_cas",
    ),
)
def test_persisted_runtime_admission_staging_bound_resumes_exact_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_at_bound_admission(point: Any) -> None:
        if _point_value(point) == crash_point:
            raise RuntimeError(f"crash:{crash_point}")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(RuntimeError, match=f"^crash:{crash_point}$"):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_at_bound_admission,
            ):
                pass

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    pending = interrupted.pending_transition
    assert interrupted.phase is live_start_session.LiveStartPhase.PUBLICATION_COMMITTED
    assert isinstance(pending, Mapping)
    assert pending["operation"] == "install_apply_invocation"
    assert pending["stage"] == "STAGING_BOUND"
    assert pending["apply_attempt_id"] == _ATTEMPT_A
    admission_path = Path(str(pending["runtime_admission_path"]))
    staging_path = Path(str(pending["runtime_admission_staging_path"]))
    if crash_point == "after_runtime_admission_staging_bound":
        assert not admission_path.exists()
        assert staging_path.is_file()
    else:
        assert admission_path.is_file()
        assert not staging_path.exists()

    executed_actions: list[str] = []
    real_execute = published_apply._execute_runtime_admission_file_action_from_pair

    def trace_execute(*args: Any, **kwargs: Any) -> Any:
        authorization = kwargs["admission_authorization"]
        executed_actions.append(str(authorization._opaque.action))
        return real_execute(*args, **kwargs)

    monkeypatch.setattr(
        published_apply,
        "_execute_runtime_admission_file_action_from_pair",
        trace_execute,
    )
    monkeypatch.setattr(
        live_start_session,
        "prepare_apply_attempt_under_lock",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("recovery-must-not-prepare-second-apply")
        ),
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered.raw_apply_status == "recovered"
    assert _disposition_value(recovered) == "COMMITTED"
    assert recovered.runtime_match_status == "matched"
    assert executed_actions[0] == "commit_bound_runtime_admission"
    assert "materialize_runtime_admission_staging" not in executed_actions
    persisted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert persisted.phase is live_start_session.LiveStartPhase.RUNTIME_MATCHED
    assert persisted.terminal_status == "LIVE_AND_MATCHED"
    assert persisted.pending_transition is None
    assert persisted.apply_recovery is None
    assert persisted.closed_apply_recovery_commitment is None
    assert isinstance(persisted.result_intent, Mapping)
    assert persisted.result_intent["apply_attempt_id"] == _ATTEMPT_A


@pytest.mark.parametrize(
    "crash_point",
    (
        "after_runtime_layout_intent",
        "after_runtime_layout_directory_bound",
        "after_invocation_receipt_staging_flush_before_staging_bound_cas",
        "after_invocation_receipt_bound_commit_before_cas",
    ),
)
def test_composite_runtime_layout_bootstrap_precedes_invocation_receipt_and_apply_started(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_during_layout_or_receipt(point: Any) -> None:
        if _point_value(point) == crash_point:
            raise RuntimeError(f"crash:{crash_point}")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(RuntimeError, match=f"^crash:{crash_point}$"):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_during_layout_or_receipt,
            ):
                pass

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    pending = interrupted.pending_transition
    layout = interrupted.runtime_layout_bootstrap
    assert interrupted.phase is live_start_session.LiveStartPhase.PUBLICATION_COMMITTED
    assert isinstance(pending, Mapping)
    assert pending["stage"] == "PRIMARY_APPLIED"
    assert isinstance(layout, Mapping)
    assert layout["next_directory_index"] <= layout["directory_count"]
    if crash_point.startswith("after_invocation_receipt"):
        assert layout["stage"] == "COMPLETE"
        external = pending["external_file_action"]
        assert isinstance(external, Mapping)
        if crash_point.endswith("staging_bound_cas"):
            assert external["stage"] == "PLANNED"
            assert Path(str(external["staging_path"])).is_file()
        else:
            assert external["stage"] == "STAGING_BOUND"
            assert Path(str(external["final_path"])).is_file()

    monkeypatch.setattr(
        live_start_session,
        "prepare_apply_attempt_under_lock",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("recovery-must-not-prepare-second-apply")
        ),
    )
    monkeypatch.setattr(
        live_start_session,
        "prepare_runtime_layout_bootstrap_under_lock",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("recovery-must-not-reprepare-layout")
        ),
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    receipt_was_committed = crash_point == "after_invocation_receipt_bound_commit_before_cas"
    assert recovered.raw_apply_status == (None if receipt_was_committed else "recovered")
    assert _disposition_value(recovered) == ("NOT_COMMITTED" if receipt_was_committed else "COMMITTED")
    assert recovered.runtime_match_status == ("not_run" if receipt_was_committed else "matched")
    persisted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert persisted.phase is (
        live_start_session.LiveStartPhase.APPLY_STARTED if receipt_was_committed
        else live_start_session.LiveStartPhase.RUNTIME_MATCHED
    )
    assert isinstance(persisted.runtime_layout_bootstrap, Mapping)
    assert persisted.runtime_layout_bootstrap["stage"] == "COMPLETE"
    assert persisted.runtime_layout_bootstrap["apply_attempt_id"] == _ATTEMPT_A
    assert persisted.apply_recovery is None
    assert persisted.closed_apply_recovery_commitment is None
    assert persisted.terminal_status == (
        "FAILED_PRESERVED" if receipt_was_committed else "LIVE_AND_MATCHED"
    )
    intent = persisted.result_intent
    retirement = persisted.terminal_retirement
    assert isinstance(intent, Mapping)
    assert isinstance(retirement, Mapping)
    assert intent["apply_attempt_id"] == _ATTEMPT_A
    assert intent["terminal_status"] == persisted.terminal_status
    assert intent["raw_apply_status"] == recovered.raw_apply_status
    assert intent["physical_disposition"] == _disposition_value(recovered)
    assert intent["runtime_match_status"] == recovered.runtime_match_status
    assert retirement["apply_attempt_id"] == _ATTEMPT_A
    assert retirement["result_intent_sha256"] == intent["content_sha256"]
    assert retirement["operation"] == (
        "release_not_committed" if receipt_was_committed else "ack_success"
    )
    assert retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"

    from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
    from hsconfig.runtime_transaction_journal import (
        RuntimeTransactionPhase,
        load_runtime_transaction_journals,
    )

    assert load_runtime_live_attempt_admission() is None
    assert not Path(intent["runtime_admission_path"]).exists()
    journals = load_runtime_transaction_journals(prepared.runtime_root)
    journal_root = prepared.runtime_root / ".hsconfig" / "transactions"
    if receipt_was_committed:
        assert persisted.attempt_acknowledgement is None
        assert journals == ()
        assert list(journal_root.iterdir()) == []
    else:
        acknowledgement = persisted.attempt_acknowledgement
        assert isinstance(acknowledgement, Mapping)
        assert acknowledgement["apply_attempt_id"] == _ATTEMPT_A
        assert len(journals) == 1
        assert journals[0].transaction_id == _ATTEMPT_A
        assert journals[0].phase is RuntimeTransactionPhase.FINALIZED
        assert journals[0].owns_target is True
        assert {path.name for path in journal_root.iterdir()} == {f"{_ATTEMPT_A}.json"}

    session_bytes = (prepared.session_root / "session.json").read_bytes()
    result_pair = {
        name: (prepared.session_root / "result" / name).read_bytes()
        for name in ("summary.json", "summary.md")
    }
    journal_bytes = {path.name: path.read_bytes() for path in journal_root.iterdir()}
    replayed = published_apply.recover_apply_attempt(session_root=prepared.session_root)
    assert replayed == recovered
    assert (prepared.session_root / "session.json").read_bytes() == session_bytes
    assert {
        name: (prepared.session_root / "result" / name).read_bytes()
        for name in result_pair
    } == result_pair
    assert {path.name: path.read_bytes() for path in journal_root.iterdir()} == journal_bytes
    assert load_runtime_live_attempt_admission() is None


def test_recovery_finishes_output_operation_handoff_before_runtime_observation_or_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    historical: Any = None

    def crash_after_apply_started(point: Any) -> None:
        if _point_value(point) == "after_apply_started":
            raise RuntimeError("crash-after-apply-started")

    with _lease_published_capabilities(prepared) as capabilities:
        historical = capabilities.output_operation_admission
        with pytest.raises(RuntimeError, match="^crash-after-apply-started$"):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_apply_started,
            ):
                pass
        assert historical.admission_path.is_file()

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    operation = interrupted.output_operation_admission_binding
    assert interrupted.phase is live_start_session.LiveStartPhase.APPLY_STARTED
    assert interrupted.apply_recovery is None
    assert isinstance(operation, Mapping)
    assert operation["state"] == "RUNTIME_HANDOFF_RELEASE_AUTHORIZED"

    events: list[str] = []
    real_release = published_apply.release_output_operation_admission_under_lease
    real_recover = published_apply.recover_runtime_attempt_from_pair

    def trace_release(**kwargs: Any) -> Any:
        events.append("release")
        result = real_release(**kwargs)
        assert not historical.admission_path.exists()
        return result

    def trace_recovery(*args: Any, **kwargs: Any) -> Any:
        assert not historical.admission_path.exists()
        events.append("runtime_observation")
        return real_recover(*args, **kwargs)

    monkeypatch.setattr(
        published_apply,
        "release_output_operation_admission_under_lease",
        trace_release,
    )
    monkeypatch.setattr(
        published_apply,
        "recover_runtime_attempt_from_pair",
        trace_recovery,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert isinstance(recovered, published_apply.ApplyAndMatchPublishedResult)
    assert events[:2] == ["release", "runtime_observation"]
    assert not historical.admission_path.exists()


def test_recovery_never_creates_or_starts_a_second_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_after_admission_bound(point: Any) -> None:
        if _point_value(point) == "after_admission_bound_before_invocation_write":
            raise RuntimeError("crash-before-same-attempt-recovery")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-same-attempt-recovery$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_admission_bound,
            ):
                pass

    from hsconfig.runtime_live_admission import (
        load_runtime_live_attempt_admission,
    )

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    pending = interrupted.pending_transition
    admission = load_runtime_live_attempt_admission()
    assert isinstance(pending, Mapping)
    assert pending["stage"] == "PRIMARY_APPLIED"
    assert pending["apply_attempt_id"] == _ATTEMPT_A
    assert admission is not None
    assert admission.apply_attempt_id == _ATTEMPT_A
    admission_path = admission.admission_path
    admission_identity = path_identity(admission_path)
    admission_raw = admission_path.read_bytes()
    revisions_before = _runtime_revision_names(prepared.runtime_root)
    authority_attempts: list[str] = []
    prepared_attempts: list[str] = []
    recovery_attempts: list[str] = []
    real_authority = published_apply._build_apply_authority
    real_prepare = published_apply.prepare_package_install_from_lease
    real_recover = published_apply.recover_runtime_attempt_from_pair

    def assert_admission_unchanged() -> None:
        assert path_identity(admission_path) == admission_identity
        assert admission_path.read_bytes() == admission_raw

    def forbid_second_apply(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("recovery-must-not-prepare-second-apply")

    def forbid_second_admission(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("recovery-must-not-claim-second-admission")

    def trace_authority(*args: Any, **kwargs: Any) -> Any:
        authority_attempts.append(str(kwargs["apply_attempt_id"]))
        return real_authority(*args, **kwargs)

    def trace_prepare(*args: Any, **kwargs: Any) -> Any:
        invocation = kwargs["invocation"]
        bound_admission = kwargs["runtime_admission"]
        assert invocation.apply_attempt_id == bound_admission.apply_attempt_id
        prepared_attempts.append(str(invocation.apply_attempt_id))
        assert_admission_unchanged()
        return real_prepare(*args, **kwargs)

    def trace_recovery(*args: Any, **kwargs: Any) -> Any:
        assert kwargs["transaction_id"] == kwargs["runtime_admission"].apply_attempt_id
        recovery_attempts.append(str(kwargs["transaction_id"]))
        assert_admission_unchanged()
        result = real_recover(*args, **kwargs)
        assert_admission_unchanged()
        return result

    monkeypatch.setattr(
        live_start_session,
        "prepare_apply_attempt_under_lock",
        forbid_second_apply,
    )
    monkeypatch.setattr(
        published_apply,
        "_claim_runtime_admission",
        forbid_second_admission,
    )
    monkeypatch.setattr(published_apply, "_build_apply_authority", trace_authority)
    monkeypatch.setattr(
        published_apply,
        "prepare_package_install_from_lease",
        trace_prepare,
    )
    monkeypatch.setattr(
        published_apply,
        "recover_runtime_attempt_from_pair",
        trace_recovery,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    invocation_path = prepared.session_root / "receipts" / "apply_invocation.json"
    invocation = published_apply.load_apply_invocation(
        invocation_path,
        expected_parent_identity=path_identity(invocation_path.parent),
    )
    assert invocation.apply_attempt_id == _ATTEMPT_A
    assert invocation.content_sha256 == pending["apply_invocation_sha256"]
    assert not os.path.lexists(admission_path)
    assert authority_attempts == [_ATTEMPT_A]
    assert prepared_attempts == [_ATTEMPT_A]
    assert recovery_attempts and set(recovery_attempts) == {_ATTEMPT_A}
    assert runtime_transaction_journal_path(
        prepared.runtime_root,
        _ATTEMPT_A,
    ).is_file()
    assert not runtime_transaction_journal_path(
        prepared.runtime_root,
        _ATTEMPT_B,
    ).exists()
    assert len(_runtime_revision_names(prepared.runtime_root) - revisions_before) == 1
    assert recovered.raw_apply_status == "recovered"
    assert _disposition_value(recovered) == "COMMITTED"
    assert recovered.runtime_match_status == "matched"


def test_nonterminal_recovery_rejects_cross_family_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_after_output_handoff(point: Any) -> None:
        if _point_value(point) == "after_output_operation_admission_unlink":
            raise RuntimeError("crash-before-cross-family-recovery")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-cross-family-recovery$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_output_handoff,
            ):
                pass

    import hsconfig.runtime_installer as runtime_installer

    session_path = prepared.session_root / "session.json"
    session_raw = session_path.read_bytes()
    runtime_tree = _physical_tree(prepared.runtime_root)
    requested_families: list[str] = []
    real_authorize = live_start_session._authorize_runtime_observation_under_lock

    def issue_wrong_family(*args: Any, **kwargs: Any) -> Any:
        del args
        requested_families.append(str(kwargs["observation_family"]))
        return real_authorize(
            session_lease=kwargs["session_lease"],
            expected_session=kwargs["expected_session"],
            observation_family="terminal_resolution",
            apply_attempt_id=kwargs["apply_attempt_id"],
        )

    def forbid_observer(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("cross-family-authority-reached-observer")

    def forbid_prepare_cas(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("cross-family-authority-reached-session-cas")

    monkeypatch.setattr(
        live_start_session,
        "_authorize_runtime_observation_under_lock",
        issue_wrong_family,
    )
    monkeypatch.setattr(
        runtime_installer,
        "_observe_exact_paired_runtime_attempt",
        forbid_observer,
    )
    monkeypatch.setattr(
        live_start_session,
        "prepare_nonterminal_apply_recovery_under_lock",
        forbid_prepare_cas,
    )

    with pytest.raises(
        live_start_session.SessionCapabilityError,
        match="^live_start_physical_capability_invalid$",
    ):
        published_apply.recover_apply_attempt(session_root=prepared.session_root)

    assert requested_families == ["nonterminal_apply"]
    assert session_path.read_bytes() == session_raw
    assert _physical_tree(prepared.runtime_root) == runtime_tree


def test_recovery_no_journal_requires_exact_snapshot_to_prove_not_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _install_identical_runtime(prepared, tmp_path / "preinstall")
    crashed = Event()

    def crash_after_output_handoff(point: Any) -> None:
        if _point_value(point) == "after_output_operation_admission_unlink":
            crashed.set()
            raise RuntimeError("crash-before-first-install-observation")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-first-install-observation$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_output_handoff,
            ):
                pass
        assert crashed.is_set()

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert interrupted.phase is live_start_session.LiveStartPhase.APPLY_STARTED
    assert interrupted.apply_recovery is None
    journal_path = runtime_transaction_journal_path(
        prepared.runtime_root,
        _ATTEMPT_A,
    )
    assert not journal_path.exists()
    runtime_tree = _physical_tree(prepared.runtime_root)

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered.raw_apply_status is None
    assert _disposition_value(recovered) == "NOT_COMMITTED"
    assert recovered.runtime_match_status == "not_run"
    assert recovered.runtime_match_sha256 is None
    assert recovered.terminal_status == "FAILED_PRESERVED"
    assert recovered.error_code == "apply_not_committed"
    assert recovered.retained_attempt_record_path is None
    assert recovered.retained_journal_path is None
    assert not journal_path.exists()
    assert _physical_tree(prepared.runtime_root) == runtime_tree
    persisted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert persisted.phase is live_start_session.LiveStartPhase.APPLY_STARTED
    assert persisted.apply_recovery is None
    assert isinstance(persisted.result_intent, Mapping)
    assert persisted.result_intent["physical_disposition"] == "NOT_COMMITTED"
    assert persisted.terminal_status == "FAILED_PRESERVED"
    assert isinstance(persisted.terminal_retirement, Mapping)
    assert persisted.terminal_retirement["operation"] == "release_not_committed"
    assert persisted.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert recovered.runtime_admission_path is not None
    assert not recovered.runtime_admission_path.exists()
    for logical_path in ("result/summary.json", "result/summary.md"):
        payload = (prepared.session_root / logical_path).read_bytes()
        assert persisted.artifact_bindings[logical_path] == (
            "sha256:" + sha256(payload).hexdigest()
        )


def test_composite_recovery_closed_active_to_closed_then_result_consumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            assert held.result.runtime_match_status == "matched"

    closed = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert isinstance(closed.apply_recovery, Mapping)
    assert closed.apply_recovery["recovery_stage"] == "CLOSED"
    assert closed.result_intent is None
    real_advance = live_start_session.advance_nonterminal_apply_recovery_under_lock
    repeated_closures = 0

    def reject_repeated_close(*args: Any, **kwargs: Any) -> Any:
        nonlocal repeated_closures
        if kwargs.get("transition") == "recovery_closed":
            repeated_closures += 1
            raise AssertionError("closed recovery must not be closed again")
        return real_advance(*args, **kwargs)

    monkeypatch.setattr(
        live_start_session,
        "advance_nonterminal_apply_recovery_under_lock",
        reject_repeated_close,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert repeated_closures == 0
    assert recovered.raw_apply_status == "recovered"
    assert _disposition_value(recovered) == "COMMITTED"
    assert recovered.runtime_match_status == "matched"
    persisted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert persisted.terminal_status in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}
    assert persisted.apply_recovery is None
    assert persisted.closed_apply_recovery_commitment is None
    assert isinstance(persisted.terminal_retirement, Mapping)
    assert persisted.terminal_retirement["operation"] == "ack_success"
    assert (
        persisted.terminal_retirement["stage"]
        == "ADMISSION_RELEASE_AUTHORIZED"
    )
    for logical_path in ("result/summary.json", "result/summary.md"):
        payload = (prepared.session_root / logical_path).read_bytes()
        assert persisted.artifact_bindings[logical_path] == (
            "sha256:" + sha256(payload).hexdigest()
        )


@pytest.mark.parametrize("materialized_result", ["none", "json", "both"])
def test_result_intent_completion_resumes_without_reapply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    materialized_result: str,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            intent = published_apply._sealed_result_intent_from_held(
                session_lease=capabilities.session_lease,
                held=held,
            )
            evidence = held.acknowledgement_evidence
            assert evidence is not None
            acknowledgement = published_apply._sealed_attempt_acknowledgement(
                run_id=held.updated_session.run_id,
                evidence=evidence,
            )
            intent_cursor = live_start_session.bind_result_intent_under_lock(
                session_lease=capabilities.session_lease,
                expected_session=held.updated_session,
                result_intent=intent,
                attempt_acknowledgement=acknowledgement,
            )
            assert intent_cursor.terminal_status is None
            summary_json, summary_markdown = (
                live_start_session._live_start_result_payloads(intent)
            )
            if materialized_result != "none":
                result_root = prepared.session_root / "result"
                result_root.mkdir()
                (result_root / "summary.json").write_bytes(summary_json)
                if materialized_result == "both":
                    (result_root / "summary.md").write_bytes(summary_markdown)

    monkeypatch.setattr(
        published_apply,
        "recover_runtime_attempt_from_pair",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("result completion must not re-observe runtime")
        ),
    )
    monkeypatch.setattr(
        live_start_session,
        "advance_nonterminal_apply_recovery_under_lock",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("result completion must not replay recovery CAS")
        ),
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered.runtime_match_status == "matched"
    assert _disposition_value(recovered) == "COMMITTED"
    persisted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert persisted.terminal_status in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}
    assert persisted.result_intent == intent
    for logical_path, expected_payload in (
        ("result/summary.json", summary_json),
        ("result/summary.md", summary_markdown),
    ):
        assert (prepared.session_root / logical_path).read_bytes() == expected_payload
        assert persisted.artifact_bindings[logical_path] == (
            "sha256:" + sha256(expected_payload).hexdigest()
        )


@pytest.mark.parametrize(
    ("crash_edge", "drift_surface"),
    [
        pytest.param("runtime_matched", "target", id="runtime_matched"),
        pytest.param("recovery_closed", "state", id="recovery_closed"),
        pytest.param("success_result_intent", "receipt", id="success_result_intent"),
        pytest.param(
            "runtime_matched", "current_attempt_source",
            id="runtime_matched-current_attempt_source",
        ),
        pytest.param(
            "recovery_closed", "current_attempt_source",
            id="recovery_closed-current_attempt_source",
        ),
    ],
)
def test_success_resume_revalidates_current_runtime_before_terminalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_edge: str,
    drift_surface: str,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _install_identical_runtime(prepared, tmp_path / "preinstall")
    real_advance = live_start_session.advance_nonterminal_apply_recovery_under_lock

    def crash_after_recovery_cas(*args: Any, **kwargs: Any) -> Any:
        successor = real_advance(*args, **kwargs)
        if kwargs.get("transition") == crash_edge:
            raise RuntimeError(f"crash-after-{crash_edge}")
        return successor

    with _lease_published_capabilities(prepared) as capabilities:
        if crash_edge in {"runtime_matched", "recovery_closed"}:
            with monkeypatch.context() as crash_patch:
                crash_patch.setattr(
                    live_start_session,
                    "advance_nonterminal_apply_recovery_under_lock",
                    crash_after_recovery_cas,
                )
                with pytest.raises(
                    RuntimeError,
                    match=f"^crash-after-{crash_edge}$",
                ):
                    with _composite(
                        published_apply,
                        capabilities,
                        apply_attempt_id=_ATTEMPT_B,
                    ):
                        pass
        else:
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_B,
            ) as held:
                assert held.result.runtime_match_status == "matched"
                assert held.result.terminal_status == "ALREADY_LIVE"

    if crash_edge == "success_result_intent":
        real_bind = live_start_session.bind_result_intent_under_lock

        def crash_after_result_intent(*args: Any, **kwargs: Any) -> Any:
            real_bind(*args, **kwargs)
            raise RuntimeError("crash-after-success_result_intent")

        with monkeypatch.context() as crash_patch:
            crash_patch.setattr(
                live_start_session,
                "bind_result_intent_under_lock",
                crash_after_result_intent,
            )
            with pytest.raises(
                RuntimeError,
                match="^crash-after-success_result_intent$",
            ):
                published_apply.recover_apply_attempt(
                    session_root=prepared.session_root
                )

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert interrupted.phase is live_start_session.LiveStartPhase.RUNTIME_MATCHED
    assert interrupted.terminal_status is None
    assert interrupted.terminal_retirement is None
    if crash_edge == "success_result_intent":
        assert interrupted.apply_recovery is None
        recovery = interrupted.closed_apply_recovery_commitment
        assert isinstance(interrupted.result_intent, Mapping)
        assert isinstance(interrupted.attempt_acknowledgement, Mapping)
    else:
        recovery = interrupted.apply_recovery
        assert interrupted.closed_apply_recovery_commitment is None
        assert interrupted.result_intent is None
        assert interrupted.attempt_acknowledgement is None
    assert isinstance(recovery, Mapping)
    assert recovery["recovery_stage"] == (
        "ACTIVE" if crash_edge == "runtime_matched" else "CLOSED"
    )
    assert recovery["runtime_match_status"] == "matched"
    assert isinstance(recovery["runtime_match_sha256"], str)
    admission = published_apply.load_runtime_live_attempt_admission()
    assert admission is not None
    attempt_journal_path = runtime_transaction_journal_path(
        prepared.runtime_root,
        admission.apply_attempt_id,
    )
    owner_path = Path(str(recovery["predecessor_target_owner_journal_path"]))
    assert attempt_journal_path != owner_path
    for retained_path in (
        admission.retention_fence_path,
        attempt_journal_path,
        owner_path,
    ):
        assert retained_path.is_file()
    result_paths = (
        prepared.session_root / "result" / "summary.json",
        prepared.session_root / "result" / "summary.md",
    )
    assert all(not path.exists() for path in result_paths)
    if drift_surface == "current_attempt_source":
        changed_path = attempt_journal_path
        original_raw = changed_path.read_bytes()
        original_identity = path_identity(changed_path)
        original_value = json.loads(original_raw)
        assert original_value["transaction_id"] == admission.apply_attempt_id
        assert original_value["owns_target"] is False
        original_source = original_value["source_manifest_sha256"]
        assert "sha256:" + original_source == (
            interrupted.publication_binding["content_root_sha256"]
        )
        changed_source = ("0" if original_source[0] != "0" else "1") + original_source[1:]
        original_field = f'"source_manifest_sha256": "{original_source}"'.encode()
        changed_field = f'"source_manifest_sha256": "{changed_source}"'.encode()
        assert original_raw.count(original_field) == 1
        changed_raw = original_raw.replace(original_field, changed_field)
        assert len(changed_raw) == len(original_raw)
        # Tamper with the current nonowner only; its authenticated session,
        # fence, receipt, and historical owner remain entirely unchanged.
        changed_path.write_bytes(changed_raw)
        assert path_identity(changed_path) == original_identity
        assert json.loads(changed_path.read_bytes()) == {
            **original_value, "source_manifest_sha256": changed_source,
        }
    elif drift_surface == "target":
        changed_path = _mutate_one_runtime_json(
            prepared.runtime_root,
            "task10_resume_drift_runtime_matched",
        )
    elif drift_surface == "state":
        changed_path = prepared.runtime_root / ".hsconfig" / "state.json"
        assert changed_path.read_bytes() != b"{}\n"
        changed_path.write_bytes(b"{}\n")
    else:
        owner_value = json.loads(owner_path.read_bytes())
        assert isinstance(owner_value, dict)
        state_key = owner_value["state_key"]
        assert isinstance(state_key, str)
        changed_path = (
            prepared.runtime_root
            / ".hsconfig"
            / "receipts"
            / state_key
            / "last_apply_receipt.json"
        )
        changed_path.write_bytes(changed_path.read_bytes() + b" ")
    changed_bytes = changed_path.read_bytes()
    session_tree_before = _physical_tree(prepared.session_root)
    runtime_tree_before = _physical_tree(prepared.runtime_root)
    admission_before = (
        path_identity(admission.admission_path),
        admission.admission_path.read_bytes(),
    )
    forbidden_calls: list[str] = []

    def forbid(label: str) -> Any:
        def blocked(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            forbidden_calls.append(label)
            raise AssertionError(f"drifted-resume-reached-{label}")

        return blocked

    with monkeypatch.context() as resume_patch:
        for name in (
            "advance_nonterminal_apply_recovery_under_lock",
            "bind_result_intent_under_lock",
            "complete_live_start_under_lock",
            "prepare_terminal_retirement_under_lock",
            "advance_terminal_retirement_under_lock",
        ):
            resume_patch.setattr(
                live_start_session,
                name,
                forbid(name),
            )
        for name in (
            "_retire_success_attempt_evidence_step_from_pair",
            "_release_runtime_live_attempt_from_pair",
        ):
            resume_patch.setattr(published_apply, name, forbid(name))

        with pytest.raises(
            ValueError,
            match="^published_apply_success_candidate_current_facts_changed$",
        ):
            published_apply.recover_apply_attempt(
                session_root=prepared.session_root
            )

    assert forbidden_calls == []
    assert changed_path.read_bytes() == changed_bytes
    assert _physical_tree(prepared.session_root) == session_tree_before
    assert _physical_tree(prepared.runtime_root) == runtime_tree_before
    assert (
        path_identity(admission.admission_path),
        admission.admission_path.read_bytes(),
    ) == admission_before


def test_recovery_missing_incomplete_or_conflicting_evidence_is_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _install_identical_runtime(prepared, tmp_path / "preinstall")
    crashed = Event()

    def crash_after_output_handoff(point: Any) -> None:
        if _point_value(point) == "after_output_operation_admission_unlink":
            crashed.set()
            raise RuntimeError("crash-before-conflicting-recovery")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-conflicting-recovery$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_output_handoff,
            ):
                pass
        assert crashed.is_set()

    conflict_path = _mutate_one_runtime_json(
        prepared.runtime_root,
        "task10_conflicting_evidence",
    )
    runtime_tree = _physical_tree(prepared.runtime_root)

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered.raw_apply_status is None
    assert _disposition_value(recovered) == "UNKNOWN_REQUIRES_RECOVERY"
    assert recovered.runtime_match_status == "unknown"
    assert recovered.runtime_match_sha256 is None
    assert recovered.terminal_status == "APPLIED_BUT_NOT_VERIFIED"
    assert recovered.error_code == "apply_recovery_unknown"
    assert _physical_tree(prepared.runtime_root) == runtime_tree
    assert conflict_path.exists()
    persisted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert persisted.phase is live_start_session.LiveStartPhase.APPLY_STARTED
    assert persisted.apply_recovery is None
    assert isinstance(persisted.result_intent, Mapping)
    assert (
        persisted.result_intent["physical_disposition"]
        == "UNKNOWN_REQUIRES_RECOVERY"
    )
    assert persisted.terminal_status == "APPLIED_BUT_NOT_VERIFIED"
    assert persisted.terminal_retirement is None
    assert recovered.runtime_admission_path is not None
    assert recovered.runtime_admission_path.exists()
    for logical_path in ("result/summary.json", "result/summary.md"):
        payload = (prepared.session_root / logical_path).read_bytes()
        assert persisted.artifact_bindings[logical_path] == (
            "sha256:" + sha256(payload).hexdigest()
        )


def test_terminal_pending_recovery_releases_admission_without_rewriting_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _install_identical_runtime(prepared, tmp_path / "preinstall")

    def crash_after_output_handoff(point: Any) -> None:
        if _point_value(point) == "after_output_operation_admission_unlink":
            raise RuntimeError("crash-before-terminal-resolution")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-terminal-resolution$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_output_handoff,
            ):
                pass

    runtime_json = next(
        path
        for path in sorted(
            (prepared.runtime_root / "CustomConfig").rglob("*.json")
        )
        if isinstance(json.loads(path.read_text(encoding="utf-8-sig")), (dict, list))
    )
    original_runtime_json = runtime_json.read_bytes()
    assert (
        _mutate_one_runtime_json(
            prepared.runtime_root,
            "task10_terminal_resolution_conflict",
        )
        == runtime_json
    )

    from hsconfig.operator_profile import (
        lease_operator_profile,
        load_operator_profile,
    )
    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
    )

    with live_start_session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        interrupted = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                with published_apply.recover_apply_attempt_under_lock(
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    output_operation_lease=operation_lease,
                    expected_session=interrupted,
                ) as recovered:
                    held = recovered.held
                    assert _disposition_value(held.result) == (
                        "UNKNOWN_REQUIRES_RECOVERY"
                    )
                    terminal = _terminalize_result(
                        session_lease=session_lease,
                        held=held,
                    )
                    result_intent = terminal.result_intent
                    terminal_status = terminal.terminal_status
                    result_pair = {
                        relative: (
                            prepared.session_root / relative
                        ).read_bytes()
                        for relative in (
                            "result/summary.json",
                            "result/summary.md",
                        )
                    }
                    admission_path = held.runtime_admission_evidence.admission_path
                    admission_bytes = admission_path.read_bytes()
                    historical_result = held.result

                    with pytest.raises(
                        ValueError,
                        match="held_apply_and_match_terminal_release_invalid",
                    ):
                        held.release_admission_after_terminal(
                            session_lease=session_lease,
                            expected_terminal_session=terminal,
                        )
                    assert admission_path.read_bytes() == admission_bytes

    assert terminal is not None
    assert result_intent is not None
    assert terminal_status is not None
    assert admission_path is not None
    assert admission_bytes is not None
    assert historical_result is not None
    runtime_json.write_bytes(original_runtime_json)

    recovered_result = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )
    resolved = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )

    assert recovered_result == historical_result
    assert resolved.result_intent == result_intent
    assert resolved.terminal_status == terminal_status
    assert resolved.attempt_acknowledgement is None
    assert resolved.terminal_retirement is not None
    assert resolved.terminal_retirement["operation"] == (
        "release_resolved_terminal"
    )
    assert resolved.terminal_retirement["stage"] == (
        "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert not admission_path.exists()
    assert {
        relative: (prepared.session_root / relative).read_bytes()
        for relative in result_pair
    } == result_pair


def test_terminal_no_commit_cleanup_resumes_every_inventory_cursor_and_staged_inventory_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_runtime_installer import _real_no_commit_cleanup_cursor

    published_apply = _published_apply()
    prepared = _real_no_commit_cleanup_cursor(
        tmp_path,
        monkeypatch,
        role="candidate",
        stop_at_recovery_prepared=True,
        replay_boundary="planned",
    )
    cursor = prepared.cursor
    intent = cursor.result_intent
    assert isinstance(intent, Mapping)
    assert cursor.terminal_status == "FAILED_PRESERVED"
    result_pair = {
        relative: (prepared.fixture.pipeline.session_root / relative).read_bytes()
        for relative in (
            "result/summary.json",
            "result/summary.md",
        )
    }
    attempt_path = Path(str(intent["retained_attempt_record_path"]))
    journal_path = Path(str(intent["retained_journal_path"]))
    admission_path = prepared.fixture.runtime_admission.admission_path
    assert attempt_path.exists()
    assert journal_path.exists()
    assert admission_path.exists()
    assert prepared.root_path.exists()
    assert not prepared.inventory_path.exists()

    crash_target: dict[str, str | None] = {"event": None}
    observed_events: list[str] = []
    real_publish_inventory = (
        live_start_session.publish_terminal_cleanup_inventory_under_lock
    )
    real_advance_resolution = (
        live_start_session.advance_terminal_resolution_under_lock
    )
    real_advance_retirement = (
        live_start_session.advance_terminal_retirement_under_lock
    )
    real_release_authorization = (
        live_start_session.authorize_terminal_retirement_under_lock
    )
    real_resolved_revalidator = (
        published_apply.revalidate_resolved_terminal_evidence_retired_from_pair
    )
    real_delete_entry = published_apply.delete_runtime_no_commit_entry_from_pair
    real_retire_metadata = (
        published_apply.retire_runtime_no_commit_metadata_from_pair
    )
    real_retire_inventory = (
        live_start_session.retire_terminal_cleanup_inventory_under_lock
    )

    def crash_after(event: str) -> None:
        observed_events.append(event)
        if crash_target["event"] == event:
            crash_target["event"] = None
            raise RuntimeError(f"simulated_terminal_cleanup_crash:{event}")

    def publish_inventory_then_maybe_crash(
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        result = real_publish_inventory(*args, **kwargs)
        crash_after(f"physical:inventory_{kwargs['action']}")
        return result

    def advance_resolution_then_maybe_crash(
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        result = real_advance_resolution(*args, **kwargs)
        crash_after(f"cas:{kwargs['transition']}")
        return result

    def advance_retirement_then_maybe_crash(
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        result = real_advance_retirement(*args, **kwargs)
        crash_after(f"cas:{kwargs['transition']}")
        return result

    def delete_entry_then_maybe_crash(
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        result = real_delete_entry(*args, **kwargs)
        crash_after("physical:delete_cleanup_entry")
        return result

    def retire_metadata_then_maybe_crash(
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        result = real_retire_metadata(*args, **kwargs)
        crash_after(f"physical:retire_cleanup_{kwargs['action']}")
        return result

    def retire_inventory_then_maybe_crash(
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        result = real_retire_inventory(*args, **kwargs)
        crash_after(f"physical:retire_cleanup_{kwargs['action']}")
        return result

    monkeypatch.setattr(
        live_start_session,
        "publish_terminal_cleanup_inventory_under_lock",
        publish_inventory_then_maybe_crash,
    )
    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_resolution_under_lock",
        advance_resolution_then_maybe_crash,
    )
    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        advance_retirement_then_maybe_crash,
    )
    monkeypatch.setattr(
        published_apply,
        "delete_runtime_no_commit_entry_from_pair",
        delete_entry_then_maybe_crash,
    )
    monkeypatch.setattr(
        published_apply,
        "retire_runtime_no_commit_metadata_from_pair",
        retire_metadata_then_maybe_crash,
    )
    monkeypatch.setattr(
        live_start_session,
        "retire_terminal_cleanup_inventory_under_lock",
        retire_inventory_then_maybe_crash,
    )

    def load_cursor() -> live_start_session.LiveStartSession:
        return live_start_session.load_live_start_session(
            prepared.fixture.pipeline.session_root,
            local_app_data_root=prepared.fixture.pipeline.local_app_data,
        )

    def resolution_of(
        current: live_start_session.LiveStartSession,
    ) -> Mapping[str, Any]:
        retirement = current.terminal_retirement
        assert isinstance(retirement, Mapping)
        resolution = retirement["terminal_resolution_evidence"]
        assert isinstance(resolution, Mapping)
        return resolution

    def expect_crash(event: str) -> None:
        assert crash_target["event"] is None
        crash_target["event"] = event
        with pytest.raises(
            RuntimeError,
            match=f"^simulated_terminal_cleanup_crash:{event}$",
        ):
            published_apply.recover_apply_attempt(
                session_root=prepared.fixture.pipeline.session_root
            )
        assert crash_target["event"] is None

    expect_crash("physical:inventory_materialize")
    cursor = load_cursor()
    resolution = resolution_of(cursor)
    external = resolution["external_file_action"]
    assert cursor.terminal_retirement["stage"] == "RECOVERY_PREPARED"
    assert resolution["cleanup_stage"] == "PREPARED"
    assert external["stage"] == "PLANNED"
    assert Path(str(external["staging_path"])).exists()
    assert not prepared.inventory_path.exists()

    expect_crash("cas:cleanup_inventory_staging_bound")
    cursor = load_cursor()
    resolution = resolution_of(cursor)
    external = resolution["external_file_action"]
    assert cursor.terminal_retirement["stage"] == "RECOVERY_PREPARED"
    assert resolution["cleanup_stage"] == "PREPARED"
    assert external["stage"] == "STAGING_BOUND"
    assert "cas:cleanup_inventory_unbound_staging_retired" in observed_events

    expect_crash("physical:inventory_commit")
    cursor = load_cursor()
    resolution = resolution_of(cursor)
    assert cursor.terminal_retirement["stage"] == "RECOVERY_PREPARED"
    assert resolution["external_file_action"]["stage"] == "STAGING_BOUND"
    assert prepared.inventory_path.exists()

    expect_crash("cas:inventory_bound")
    cursor = load_cursor()
    resolution = resolution_of(cursor)
    assert cursor.terminal_retirement["stage"] == "RECOVERY_INVENTORY_BOUND"
    assert resolution["cleanup_stage"] == "INVENTORY_BOUND"
    assert resolution["cleanup_cursor"] == 0

    expect_crash("cas:cleaning_started")
    cursor = load_cursor()
    resolution = resolution_of(cursor)
    assert cursor.terminal_retirement["stage"] == "RECOVERY_CLEANING"
    assert resolution["cleanup_stage"] == "CLEANING"
    assert resolution["cleanup_cursor"] == 0

    roots = {
        str(root["root_role"]): Path(str(root["source_path"]))
        for root in prepared.inventory.value["cleanup_roots"]
    }
    for index, entry in enumerate(prepared.entries):
        relative = str(entry["relative_path"])
        entry_path = roots[str(entry["root_role"])]
        if relative != ".":
            entry_path = entry_path / Path(*relative.split("/"))

        expect_crash("physical:delete_cleanup_entry")
        cursor = load_cursor()
        resolution = resolution_of(cursor)
        assert cursor.terminal_retirement["stage"] == "RECOVERY_CLEANING"
        assert resolution["cleanup_cursor"] == index
        assert not entry_path.exists()

        expect_crash("cas:cleanup_cursor_advanced")
        cursor = load_cursor()
        resolution = resolution_of(cursor)
        assert cursor.terminal_retirement["stage"] == "RECOVERY_CLEANING"
        assert resolution["cleanup_cursor"] == index + 1

    assert not prepared.root_path.exists()

    expect_crash("physical:retire_cleanup_journal")
    cursor = load_cursor()
    assert cursor.terminal_retirement["stage"] == "RECOVERY_CLEANING"
    assert not journal_path.exists()

    expect_crash("cas:journal_retired")
    cursor = load_cursor()
    resolution = resolution_of(cursor)
    assert cursor.terminal_retirement["stage"] == "RECOVERY_JOURNAL_RETIRED"
    assert resolution["cleanup_stage"] == "JOURNAL_RETIRED"

    expect_crash("physical:retire_cleanup_fence")
    cursor = load_cursor()
    assert cursor.terminal_retirement["stage"] == "RECOVERY_JOURNAL_RETIRED"
    assert not attempt_path.exists()

    expect_crash("cas:fence_retired")
    cursor = load_cursor()
    resolution = resolution_of(cursor)
    assert cursor.terminal_retirement["stage"] == "RECOVERY_FENCE_RETIRED"
    assert resolution["cleanup_stage"] == "FENCE_RETIRED"

    expect_crash("physical:retire_cleanup_final_sidecar")
    cursor = load_cursor()
    assert cursor.terminal_retirement["stage"] == "RECOVERY_FENCE_RETIRED"
    assert not prepared.inventory_path.exists()

    expect_crash("cas:inventory_retired")
    cursor = load_cursor()
    resolution = resolution_of(cursor)
    assert cursor.terminal_retirement["stage"] == "RECOVERY_INVENTORY_RETIRED"
    assert resolution["cleanup_stage"] == "INVENTORY_RETIRED"

    expect_crash("cas:stabilized")
    cursor = load_cursor()
    resolution = resolution_of(cursor)
    assert cursor.terminal_retirement["stage"] == "RECOVERY_STABILIZED"
    assert resolution["cleanup_stage"] == "COMPLETE"

    expect_crash("cas:evidence_retired")
    cursor = load_cursor()
    resolution = resolution_of(cursor)
    assert cursor.terminal_retirement["stage"] == "EVIDENCE_RETIRED"
    assert resolution["cleanup_stage"] == "COMPLETE"

    session_path = prepared.fixture.pipeline.session_root / "session.json"
    session_bytes = session_path.read_bytes()
    admission_bytes = admission_path.read_bytes()
    release_authorization_calls: list[str] = []

    def forbid_release_authorization(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        release_authorization_calls.append("terminal")
        raise AssertionError("late-residue-reached-release-authorization")

    monkeypatch.setattr(
        live_start_session,
        "authorize_terminal_retirement_under_lock",
        forbid_release_authorization,
    )
    inventory_staging = prepared.inventory_path.with_name(
        f"{prepared.inventory_path.name}.staged"
    )
    inventory_inner_temp = inventory_staging.with_name(
        f".{inventory_staging.name}.live-start-atomic.tmp"
    )
    for residue_path, residue_kind in (
        (prepared.inventory_path, "file"),
        (inventory_staging, "file"),
        (inventory_inner_temp, "file"),
        (prepared.root_path, "directory"),
    ):
        assert not residue_path.exists()

        def inject_late_cleanup_residue(
            *args: Any,
            _residue_path: Path = residue_path,
            _residue_kind: str = residue_kind,
            **kwargs: Any,
        ) -> Any:
            if _residue_kind == "directory":
                _residue_path.mkdir()
            else:
                _residue_path.write_bytes(
                    b"late-terminal-cleanup-residue\n"
                )
            return real_resolved_revalidator(*args, **kwargs)

        monkeypatch.setattr(
            published_apply,
            "revalidate_resolved_terminal_evidence_retired_from_pair",
            inject_late_cleanup_residue,
        )
        with pytest.raises(
            ValueError,
            match="^runtime_terminal_release_current_facts_changed",
        ) as failure:
            published_apply.recover_apply_attempt(
                session_root=prepared.fixture.pipeline.session_root
            )
        assert failure.value.args == (
            "runtime_terminal_release_current_facts_changed",
        )
        assert release_authorization_calls == []
        assert session_path.read_bytes() == session_bytes
        assert admission_path.read_bytes() == admission_bytes
        assert residue_path.exists()
        if residue_kind == "directory":
            residue_path.rmdir()
        else:
            assert residue_path.read_bytes() == (
                b"late-terminal-cleanup-residue\n"
            )
            residue_path.unlink()

    monkeypatch.setattr(
        published_apply,
        "revalidate_resolved_terminal_evidence_retired_from_pair",
        real_resolved_revalidator,
    )
    monkeypatch.setattr(
        live_start_session,
        "authorize_terminal_retirement_under_lock",
        real_release_authorization,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.fixture.pipeline.session_root
    )
    resolved = live_start_session.load_live_start_session(
        prepared.fixture.pipeline.session_root,
        local_app_data_root=prepared.fixture.pipeline.local_app_data,
    )

    assert recovered.terminal_status == "FAILED_PRESERVED"
    assert resolved.result_intent == intent
    assert resolved.terminal_status == cursor.terminal_status
    assert resolved.terminal_retirement is not None
    assert resolved.terminal_retirement["operation"] == (
        "release_resolved_terminal"
    )
    assert resolved.terminal_retirement["stage"] == (
        "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert not prepared.root_path.exists()
    assert not prepared.inventory_path.exists()
    assert not attempt_path.exists()
    assert not journal_path.exists()
    assert not admission_path.exists()
    assert {
        relative: (prepared.fixture.pipeline.session_root / relative).read_bytes()
        for relative in result_pair
    } == result_pair


def test_competing_mutation_after_match_waits_until_terminal_session_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    contender: tuple[Thread, Event, Event, list[BaseException]] | None = None
    mutation_path = prepared.runtime_root / "task10-after-terminal-cas.txt"
    order: list[str] = []

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            assert held.result.runtime_match_status == "matched"

            def mutate_after_pair_release() -> None:
                mutation_path.write_bytes(b"mutation after terminal\n")
                order.append("mutation")

            contender = _start_lock_contender(
                lock_path=prepared.runtime_root / ".hsconfig" / "apply.lock",
                mutate=mutate_after_pair_release,
            )
            assert not contender[2].wait(0.1)
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            order.append("terminal_cas")
            assert terminal.terminal_status == held.result.terminal_status
            assert not contender[2].is_set()
            acknowledged = held.acknowledge_after_terminal(
                session_lease=capabilities.session_lease,
                expected_terminal_session=terminal,
            )
            assert acknowledged.terminal_status == terminal.terminal_status
            assert not contender[2].is_set()

    assert contender is not None
    _join_contender(contender[0], contender[2], contender[3])
    assert order == ["terminal_cas", "mutation"]
    assert mutation_path.read_bytes() == b"mutation after terminal\n"


def test_held_context_acknowledges_only_bound_evidence_and_expires_on_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    escaped: Any | None = None

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            evidence = held.acknowledgement_evidence
            assert evidence is not None
            assert evidence.journal_owns_target is True
            assert evidence.retention_fence_path.exists()
            assert evidence.journal_path.exists()
            assert evidence.target_owner_journal_path.exists()
            assert evidence.runtime_admission_path.exists()
            owner_raw = evidence.target_owner_journal_path.read_bytes()
            target_names = tuple(
                sorted(
                    path.relative_to(evidence.target_path).as_posix()
                    for path in evidence.target_path.rglob("*")
                )
            )

            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            resolved = held.acknowledge_after_terminal(
                session_lease=capabilities.session_lease,
                expected_terminal_session=terminal,
            )

            assert resolved.terminal_status == terminal.terminal_status
            assert resolved.result_intent == terminal.result_intent
            assert resolved.attempt_acknowledgement == (
                terminal.attempt_acknowledgement
            )
            assert resolved.terminal_retirement is not None
            assert (
                resolved.terminal_retirement["stage"]
                == "ADMISSION_RELEASE_AUTHORIZED"
            )
            assert not evidence.retention_fence_path.exists()
            assert evidence.target_owner_journal_path.read_bytes() == owner_raw
            assert tuple(
                sorted(
                    path.relative_to(evidence.target_path).as_posix()
                    for path in evidence.target_path.rglob("*")
                )
            ) == target_names
            assert not evidence.runtime_admission_path.exists()
            with pytest.raises(ValueError):
                held.acknowledge_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=terminal,
                )
            escaped = held

    assert escaped is not None
    with pytest.raises(ValueError, match="held_apply_and_match_expired"):
        _ = escaped.result


def test_held_context_revalidates_runtime_lease_after_yield_and_expires(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_validate = published_apply._require_active_runtime_apply_lease
    armed = False
    escaped: Any | None = None

    def validate_runtime_lease(lease: Any) -> Any:
        if armed:
            raise live_start_session.SessionCapabilityError(
                "sentinel_post_yield_runtime_lease"
            )
        return real_validate(lease)

    monkeypatch.setattr(
        published_apply,
        "_require_active_runtime_apply_lease",
        validate_runtime_lease,
    )
    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            live_start_session.SessionCapabilityError,
            match="^sentinel_post_yield_runtime_lease$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
            ) as held:
                escaped = held
                assert held.result.runtime_match_status == "matched"
                armed = True

    assert escaped is not None
    with pytest.raises(ValueError, match="held_apply_and_match_expired"):
        _ = escaped.result


def test_held_context_preserves_primary_error_when_post_yield_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_validate = published_apply._require_active_runtime_apply_lease
    armed = False
    escaped: Any | None = None

    def validate_runtime_lease(lease: Any) -> Any:
        if armed:
            raise live_start_session.SessionCapabilityError(
                "sentinel_post_yield_runtime_lease"
            )
        return real_validate(lease)

    monkeypatch.setattr(
        published_apply,
        "_require_active_runtime_apply_lease",
        validate_runtime_lease,
    )
    with pytest.raises(RuntimeError) as caught:
        with _lease_published_capabilities(prepared) as capabilities:
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
            ) as held:
                escaped = held
                armed = True
                raise RuntimeError("primary-held-body-error")

    assert str(caught.value) == "primary-held-body-error"
    assert any(
        "held context validation failed: SessionCapabilityError: "
        "sentinel_post_yield_runtime_lease" in note
        for note in getattr(caught.value, "__notes__", ())
    )
    assert escaped is not None
    with pytest.raises(ValueError, match="held_apply_and_match_expired"):
        _ = escaped.result


def test_terminal_fast_path_accepts_absent_old_admission_without_old_leases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    historical_result: Any | None = None
    release_authorized: Any | None = None
    admission_path: Path | None = None

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            historical_result = held.result
            admission_path = held.runtime_admission_evidence.admission_path
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            release_authorized = held.acknowledge_after_terminal(
                session_lease=capabilities.session_lease,
                expected_terminal_session=terminal,
            )

    assert historical_result is not None
    assert release_authorized is not None
    assert admission_path is not None
    assert release_authorized.terminal_retirement is not None
    assert (
        release_authorized.terminal_retirement["stage"]
        == "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert not admission_path.exists()
    persisted_bytes = (prepared.session_root / "session.json").read_bytes()

    _forbid_terminal_old_capability_reacquisition(
        published_apply=published_apply,
        monkeypatch=monkeypatch,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered == historical_result
    assert (prepared.session_root / "session.json").read_bytes() == persisted_bytes
    assert not admission_path.exists()


def test_fault_after_terminal_before_admission_release_resumes_without_reapply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    historical_result: Any | None = None
    admission_path: Path | None = None

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            historical_result = held.result
            admission_path = held.runtime_admission_evidence.admission_path
            terminal = _terminalize_result(
                session_lease=capabilities.session_lease,
                held=held,
            )
            assert terminal.terminal_status == held.result.terminal_status
            assert terminal.terminal_retirement is None
            assert admission_path.is_file()

    assert historical_result is not None
    assert admission_path is not None
    result_paths = tuple(
        prepared.session_root / relative
        for relative in ("result/summary.json", "result/summary.md")
    )
    result_evidence = {
        path: (
            path.read_bytes(),
            path_identity(path),
            path.stat().st_mtime_ns,
        )
        for path in result_paths
    }
    forbidden_calls: list[str] = []

    def forbid_reapply(label: str) -> Any:
        def forbidden(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            forbidden_calls.append(label)
            raise AssertionError(f"terminal recovery reached {label}")

        return forbidden

    with monkeypatch.context() as terminal_patch:
        terminal_patch.setattr(
            published_apply,
            "recover_runtime_attempt_from_pair",
            forbid_reapply("runtime_recovery"),
        )
        terminal_patch.setattr(
            published_apply,
            "_drive_recovery_rows",
            forbid_reapply("recovery_rows"),
        )
        terminal_patch.setattr(
            published_apply,
            "prepare_package_install_from_lease",
            forbid_reapply("package_install"),
        )
        terminal_patch.setattr(
            published_apply,
            "build_runtime_package_match_report_from_pair",
            forbid_reapply("runtime_match"),
        )
        terminal_patch.setattr(
            live_start_session,
            "complete_live_start_under_lock",
            forbid_reapply("terminal_completion"),
        )

        recovered = published_apply.recover_apply_attempt(
            session_root=prepared.session_root
        )
        repeated = published_apply.recover_apply_attempt(
            session_root=prepared.session_root
        )

    assert recovered == historical_result
    assert repeated == historical_result
    assert forbidden_calls == []
    resolved = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert resolved.terminal_retirement is not None
    assert resolved.terminal_retirement["stage"] == (
        "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert not admission_path.exists()
    assert {
        path: (
            path.read_bytes(),
            path_identity(path),
            path.stat().st_mtime_ns,
        )
        for path in result_paths
    } == result_evidence


def test_terminal_fast_path_rejects_unbound_admission_projection_before_observer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    admission_path: Path | None = None
    historical_admission_bytes: bytes | None = None

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            admission_path = held.runtime_admission_evidence.admission_path
            historical_admission_bytes = admission_path.read_bytes()
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            release_authorized = held.acknowledge_after_terminal(
                session_lease=capabilities.session_lease,
                expected_terminal_session=terminal,
            )

    assert admission_path is not None
    assert historical_admission_bytes is not None
    assert release_authorized.terminal_retirement is not None
    assert (
        release_authorized.terminal_retirement["stage"]
        == "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert not admission_path.exists()
    session_path = prepared.session_root / "session.json"
    session_before = session_path.read_bytes()
    real_admission_path = published_apply.runtime_live_attempt_admission_path
    real_projector = (
        published_apply._project_runtime_live_attempt_admission_bytes
    )
    projection_calls: list[dict[str, Any]] = []

    def mismatched_projection(**kwargs: Any) -> bytes:
        projection_calls.append(kwargs)
        return b'{"not":"the historical admission"}'

    release_calls: list[str] = []

    def forbidden_release(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        release_calls.append("runtime")
        raise AssertionError("invalid-projection-reached-admission-observer")

    monkeypatch.setattr(
        published_apply,
        "release_runtime_live_attempt_exact",
        forbidden_release,
    )
    authority_calls: list[str] = []

    def forbidden_authority(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        authority_calls.append("terminal")
        raise AssertionError("invalid-projection-minted-terminal-authority")

    monkeypatch.setattr(
        live_start_session,
        "authorize_terminal_retirement_under_lock",
        forbidden_authority,
    )
    _forbid_terminal_old_capability_reacquisition(
        published_apply=published_apply,
        monkeypatch=monkeypatch,
    )

    monkeypatch.setattr(
        published_apply,
        "runtime_live_attempt_admission_path",
        lambda: admission_path.with_name("wrong-active-attempt.json"),
    )
    with pytest.raises(
        live_start_session.SessionCapabilityError,
        match="^published_apply_terminal_release_context_invalid$",
    ):
        published_apply.recover_apply_attempt(
            session_root=prepared.session_root
        )

    assert projection_calls == []
    assert release_calls == []
    assert authority_calls == []
    monkeypatch.setattr(
        published_apply,
        "runtime_live_attempt_admission_path",
        real_admission_path,
    )
    monkeypatch.setattr(
        published_apply,
        "_project_runtime_live_attempt_admission_bytes",
        mismatched_projection,
    )
    with pytest.raises(
        live_start_session.SessionCapabilityError,
        match="^published_apply_terminal_release_context_invalid$",
    ):
        published_apply.recover_apply_attempt(
            session_root=prepared.session_root
        )

    assert len(projection_calls) == 1
    assert release_calls == []
    assert authority_calls == []
    assert session_path.read_bytes() == session_before
    assert not admission_path.exists()

    monkeypatch.setattr(
        published_apply,
        "_project_runtime_live_attempt_admission_bytes",
        real_projector,
    )
    from hsconfig.apply_invocation import (
        build_apply_invocation,
        build_pre_apply_runtime_snapshot,
    )

    invocation_path = prepared.session_root / "receipts" / "apply_invocation.json"
    invocation = published_apply.load_apply_invocation(
        invocation_path,
        expected_parent_identity=path_identity(invocation_path.parent),
    )
    snapshot_arguments = invocation.pre_apply_runtime_snapshot.as_build_arguments()
    alternate_snapshot_digest = "sha256:" + "e" * 64
    if snapshot_arguments["runtime_tree_sha256"] == alternate_snapshot_digest:
        alternate_snapshot_digest = "sha256:" + "f" * 64
    snapshot_arguments["runtime_tree_sha256"] = alternate_snapshot_digest
    replacement_snapshot = build_pre_apply_runtime_snapshot(
        **snapshot_arguments
    )
    replacement_invocation = build_apply_invocation(
        apply_attempt_id=invocation.apply_attempt_id,
        run_id=invocation.run_id,
        publication_revision=invocation.publication_revision,
        publication_content_root_sha256=(
            invocation.publication_content_root_sha256
        ),
        output_operation_admission_path=(
            invocation.output_operation_admission_path
        ),
        output_operation_admission_identity=(
            invocation.output_operation_admission_identity
        ),
        output_operation_admission_sha256=(
            invocation.output_operation_admission_sha256
        ),
        output_child_binding_sha256=(
            invocation.output_child_binding_sha256
        ),
        output_child_path=invocation.output_child_path,
        output_child_identity=invocation.output_child_identity,
        operator_profile_sha256=invocation.operator_profile_sha256,
        runtime_root=invocation.runtime_root,
        runtime_root_identity=invocation.runtime_root_identity,
        pre_apply_runtime_snapshot=replacement_snapshot,
    )
    invocation_path.write_bytes(replacement_invocation.canonical_json)
    session_value = release_authorized.to_value()
    session_value.pop("content_sha256", None)
    session_value["apply_invocation_sha256"] = (
        replacement_invocation.content_sha256
    )
    artifact_bindings = dict(session_value["artifact_bindings"])
    artifact_bindings["receipts/apply_invocation.json"] = (
        "sha256:"
        + sha256(replacement_invocation.canonical_json).hexdigest()
    )
    session_value["artifact_bindings"] = artifact_bindings
    replacement_session = live_start_session._seal_session_value(
        session_value,
        session_identity=None,
    )
    session_path.write_bytes(replacement_session.canonical_json)
    tampered_session_bytes = session_path.read_bytes()

    with pytest.raises(
        live_start_session.SessionCapabilityError,
        match="^published_apply_terminal_release_context_invalid$",
    ):
        published_apply.recover_apply_attempt(
            session_root=prepared.session_root
        )

    assert session_path.read_bytes() == tampered_session_bytes
    assert not admission_path.exists()
    assert release_calls == []
    assert authority_calls == []

    foreign_bytes = _foreign_runtime_admission_bytes(
        historical_admission_bytes
    )
    admission_path.write_bytes(foreign_bytes)
    foreign_identity = path_identity(admission_path)
    with pytest.raises(
        live_start_session.SessionCapabilityError,
        match="^published_apply_terminal_release_context_invalid$",
    ):
        published_apply.recover_apply_attempt(
            session_root=prepared.session_root
        )

    assert session_path.read_bytes() == tampered_session_bytes
    assert path_identity(admission_path) == foreign_identity
    assert admission_path.read_bytes() == foreign_bytes
    assert release_calls == []
    assert authority_calls == []


def test_terminal_fast_path_unlinks_present_old_admission_without_old_leases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_release = published_apply.release_runtime_live_attempt_exact
    historical_result: Any | None = None
    admission_path: Path | None = None
    admission_identity: Any | None = None
    admission_bytes: bytes | None = None

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            historical_result = held.result
            admission = held.runtime_admission_evidence
            admission_path = admission.admission_path
            admission_identity = admission.admission_identity
            admission_bytes = admission_path.read_bytes()
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )

            def crash_before_release(*, expected: Any) -> Any:
                assert expected is admission
                raise RuntimeError("crash-before-runtime-admission-release")

            monkeypatch.setattr(
                published_apply,
                "release_runtime_live_attempt_exact",
                crash_before_release,
            )
            with pytest.raises(
                RuntimeError,
                match="^crash-before-runtime-admission-release$",
            ):
                held.acknowledge_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=terminal,
                )
            release_authorized = (
                live_start_session.load_live_start_session_under_lock(
                    session_lease=capabilities.session_lease
                )
            )

    assert historical_result is not None
    assert admission_path is not None
    assert admission_identity is not None
    assert admission_bytes is not None
    assert release_authorized.terminal_retirement is not None
    assert (
        release_authorized.terminal_retirement["stage"]
        == "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert path_identity(admission_path) == admission_identity
    assert admission_path.read_bytes() == admission_bytes
    persisted_bytes = (prepared.session_root / "session.json").read_bytes()
    monkeypatch.setattr(
        published_apply,
        "release_runtime_live_attempt_exact",
        real_release,
    )
    _forbid_terminal_old_capability_reacquisition(
        published_apply=published_apply,
        monkeypatch=monkeypatch,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered == historical_result
    assert (prepared.session_root / "session.json").read_bytes() == persisted_bytes
    assert not admission_path.exists()


def test_terminal_fast_path_preserves_valid_foreign_successor_without_old_leases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    historical_result: Any | None = None
    admission_path: Path | None = None
    historical_identity: Any | None = None
    historical_bytes: bytes | None = None

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            historical_result = held.result
            admission = held.runtime_admission_evidence
            admission_path = admission.admission_path
            historical_identity = admission.admission_identity
            historical_bytes = admission_path.read_bytes()
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            release_authorized = held.acknowledge_after_terminal(
                session_lease=capabilities.session_lease,
                expected_terminal_session=terminal,
            )

    assert historical_result is not None
    assert admission_path is not None
    assert historical_identity is not None
    assert historical_bytes is not None
    assert release_authorized.terminal_retirement is not None
    assert (
        release_authorized.terminal_retirement["stage"]
        == "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert not admission_path.exists()
    foreign_bytes = _foreign_runtime_admission_bytes(historical_bytes)
    admission_path.write_bytes(foreign_bytes)
    foreign_identity = path_identity(admission_path)
    assert foreign_identity != historical_identity
    persisted_bytes = (prepared.session_root / "session.json").read_bytes()
    _forbid_terminal_old_capability_reacquisition(
        published_apply=published_apply,
        monkeypatch=monkeypatch,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered == historical_result
    assert (prepared.session_root / "session.json").read_bytes() == persisted_bytes
    assert path_identity(admission_path) == foreign_identity
    assert admission_path.read_bytes() == foreign_bytes


def test_composite_success_ack_threads_one_receipt_per_deleted_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _install_identical_runtime(prepared, tmp_path / "preinstall")
    real_advance = live_start_session.advance_terminal_retirement_under_lock
    transitions: list[tuple[str, bool, bool]] = []

    def trace_advance(*args: Any, **kwargs: Any) -> Any:
        transitions.append(
            (
                str(kwargs["transition"]),
                kwargs["terminal_authorization"] is not None,
                kwargs["physical_step_receipt"] is not None,
            )
        )
        return real_advance(*args, **kwargs)

    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        trace_advance,
    )

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_B,
        ) as held:
            evidence = held.acknowledgement_evidence
            assert evidence is not None
            assert evidence.journal_owns_target is False
            assert evidence.acknowledgement_action == (
                "delete_nonowning_attempt_and_fence"
            )
            assert evidence.journal_path != evidence.target_owner_journal_path
            owner_raw = evidence.target_owner_journal_path.read_bytes()
            target_surface = _physical_tree(evidence.target_path)

            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            resolved = held.acknowledge_after_terminal(
                session_lease=capabilities.session_lease,
                expected_terminal_session=terminal,
            )

            assert transitions == [
                ("ack_journal_retired", False, True),
                ("evidence_retired", False, True),
                ("admission_release_authorized", True, False),
            ]
            assert resolved.terminal_retirement is not None
            assert (
                resolved.terminal_retirement["stage"]
                == "ADMISSION_RELEASE_AUTHORIZED"
            )
            assert not evidence.journal_path.exists()
            assert not evidence.retention_fence_path.exists()
            assert evidence.target_owner_journal_path.read_bytes() == owner_raw
            assert _physical_tree(evidence.target_path) == target_surface
            assert not evidence.runtime_admission_path.exists()


def test_ack_requires_active_session_lease_and_exact_persisted_terminal_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            preterminal = held.updated_session
            evidence = held.acknowledgement_evidence
            assert evidence is not None
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            preserved = (
                evidence.retention_fence_path.read_bytes(),
                evidence.journal_path.read_bytes(),
                evidence.runtime_admission_path.read_bytes(),
            )

            with pytest.raises(ValueError, match="session_lease_invalid"):
                held.acknowledge_after_terminal(
                    session_lease=object(),
                    expected_terminal_session=terminal,
                )
            with pytest.raises(ValueError, match="terminal_cursor_invalid"):
                held.acknowledge_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=preterminal,
                )

            assert (
                evidence.retention_fence_path.read_bytes(),
                evidence.journal_path.read_bytes(),
                evidence.runtime_admission_path.read_bytes(),
            ) == preserved
            held.acknowledge_after_terminal(
                session_lease=capabilities.session_lease,
                expected_terminal_session=terminal,
            )


def test_ack_rejects_cross_thread_session_capability_without_retiring_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            evidence = held.acknowledgement_evidence
            assert evidence is not None
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            preserved = (
                evidence.retention_fence_path.read_bytes(),
                evidence.journal_path.read_bytes(),
                evidence.runtime_admission_path.read_bytes(),
            )
            errors: list[BaseException] = []

            def cross_thread_ack() -> None:
                try:
                    held.acknowledge_after_terminal(
                        session_lease=capabilities.session_lease,
                        expected_terminal_session=terminal,
                    )
                except BaseException as error:
                    errors.append(error)

            contender = Thread(target=cross_thread_ack, daemon=True)
            contender.start()
            contender.join(_THREAD_TIMEOUT)
            assert not contender.is_alive()
            assert len(errors) == 1
            assert isinstance(errors[0], ValueError)
            assert (
                evidence.retention_fence_path.read_bytes(),
                evidence.journal_path.read_bytes(),
                evidence.runtime_admission_path.read_bytes(),
            ) == preserved

            held.acknowledge_after_terminal(
                session_lease=capabilities.session_lease,
                expected_terminal_session=terminal,
            )


def test_ack_revalidates_exact_current_and_match_before_retiring_attempt_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            evidence = held.acknowledgement_evidence
            assert evidence is not None
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            preserved = {
                path: (path_identity(path), path.read_bytes())
                for path in {
                    evidence.retention_fence_path,
                    evidence.journal_path,
                    evidence.target_owner_journal_path,
                    evidence.runtime_admission_path,
                }
            }
            mutated_path = _mutate_one_runtime_json(
                prepared.runtime_root,
                "task10_runtime_changed_before_ack",
            )

            with pytest.raises(
                ValueError,
                match="runtime_success_ack_current_runtime_facts_changed",
            ):
                held.acknowledge_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=terminal,
                )

            assert mutated_path.is_file()
            assert {
                path: (path_identity(path), path.read_bytes())
                for path in preserved
            } == preserved
            persisted = live_start_session.load_live_start_session_under_lock(
                session_lease=capabilities.session_lease
            )
            assert persisted.terminal_retirement is not None
            assert persisted.terminal_retirement["stage"] == "PREPARED"


@pytest.mark.parametrize("crash_stage", ("PREPARED", "EVIDENCE_RETIRED"))
def test_terminal_retirement_crashes_resume_recovery_evidence_and_release_authorized_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_stage: str,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    historical_result: Any | None = None
    evidence: Any | None = None
    result_payloads: dict[str, bytes] | None = None
    real_prepare = live_start_session.prepare_terminal_retirement_under_lock
    real_advance = live_start_session.advance_terminal_retirement_under_lock

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            historical_result = held.result
            evidence = held.acknowledgement_evidence
            assert evidence is not None
            assert evidence.journal_owns_target is True
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            result_payloads = {
                relative: (prepared.session_root / relative).read_bytes()
                for relative in ("result/summary.json", "result/summary.md")
            }

            if crash_stage == "PREPARED":

                def crash_after_prepare(*args: Any, **kwargs: Any) -> Any:
                    real_prepare(*args, **kwargs)
                    raise RuntimeError("crash-after-terminal-retirement-prepared")

                monkeypatch.setattr(
                    live_start_session,
                    "prepare_terminal_retirement_under_lock",
                    crash_after_prepare,
                )
            else:

                def crash_after_evidence_retired(
                    *args: Any,
                    **kwargs: Any,
                ) -> Any:
                    successor = real_advance(*args, **kwargs)
                    if kwargs.get("transition") == "evidence_retired":
                        raise RuntimeError("crash-after-evidence-retired")
                    return successor

                monkeypatch.setattr(
                    live_start_session,
                    "advance_terminal_retirement_under_lock",
                    crash_after_evidence_retired,
                )

            with pytest.raises(RuntimeError, match="^crash-after-"):
                held.acknowledge_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=terminal,
                )
            crashed = live_start_session.load_live_start_session_under_lock(
                session_lease=capabilities.session_lease
            )
            assert crashed.terminal_retirement is not None
            assert crashed.terminal_retirement["stage"] == crash_stage

    assert historical_result is not None
    assert evidence is not None
    assert result_payloads is not None
    monkeypatch.setattr(
        live_start_session,
        "prepare_terminal_retirement_under_lock",
        real_prepare,
    )
    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        real_advance,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered == historical_result
    persisted = live_start_session.load_live_start_session(
        prepared.session_root
    )
    assert persisted.terminal_retirement is not None
    assert (
        persisted.terminal_retirement["stage"]
        == "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert not evidence.retention_fence_path.exists()
    assert evidence.journal_path.exists()
    assert not evidence.runtime_admission_path.exists()
    assert {
        relative: (prepared.session_root / relative).read_bytes()
        for relative in result_payloads
    } == result_payloads


def test_composite_nonowning_ack_crash_resumes_from_ack_journal_retired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _install_identical_runtime(prepared, tmp_path / "preinstall")
    real_advance = live_start_session.advance_terminal_retirement_under_lock
    historical_result: Any | None = None
    evidence: Any | None = None
    owner_bytes: bytes | None = None

    def crash_after_ack_journal_retired(*args: Any, **kwargs: Any) -> Any:
        successor = real_advance(*args, **kwargs)
        if kwargs.get("transition") == "ack_journal_retired":
            raise RuntimeError("crash-after-ack-journal-retired")
        return successor

    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        crash_after_ack_journal_retired,
    )
    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_B,
        ) as held:
            historical_result = held.result
            evidence = held.acknowledgement_evidence
            assert evidence is not None
            assert evidence.journal_owns_target is False
            owner_bytes = evidence.target_owner_journal_path.read_bytes()
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )

            with pytest.raises(
                RuntimeError,
                match="^crash-after-ack-journal-retired$",
            ):
                held.acknowledge_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=terminal,
                )
            crashed = live_start_session.load_live_start_session_under_lock(
                session_lease=capabilities.session_lease
            )
            assert crashed.terminal_retirement is not None
            assert (
                crashed.terminal_retirement["stage"]
                == "ACK_JOURNAL_RETIRED"
            )
            assert not evidence.journal_path.exists()
            assert evidence.retention_fence_path.exists()

    assert historical_result is not None
    assert evidence is not None
    assert owner_bytes is not None
    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        real_advance,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered == historical_result
    persisted = live_start_session.load_live_start_session(
        prepared.session_root
    )
    assert persisted.terminal_retirement is not None
    assert (
        persisted.terminal_retirement["stage"]
        == "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert not evidence.journal_path.exists()
    assert not evidence.retention_fence_path.exists()
    assert evidence.target_owner_journal_path.read_bytes() == owner_bytes
    assert not evidence.runtime_admission_path.exists()


def test_terminal_evidence_retired_revalidates_current_runtime_before_release_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_advance = live_start_session.advance_terminal_retirement_under_lock
    evidence: Any | None = None

    def crash_after_evidence_retired(*args: Any, **kwargs: Any) -> Any:
        successor = real_advance(*args, **kwargs)
        if kwargs.get("transition") == "evidence_retired":
            raise RuntimeError("crash-after-evidence-retired")
        return successor

    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        crash_after_evidence_retired,
    )
    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
        ) as held:
            evidence = held.acknowledgement_evidence
            assert evidence is not None
            terminal = _terminalize_success(
                session_lease=capabilities.session_lease,
                held=held,
            )
            with pytest.raises(
                RuntimeError,
                match="^crash-after-evidence-retired$",
            ):
                held.acknowledge_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=terminal,
                )

    assert evidence is not None
    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        real_advance,
    )
    session_path = prepared.session_root / "session.json"
    session_bytes = session_path.read_bytes()
    admission_bytes = evidence.runtime_admission_path.read_bytes()
    mutated_path = _mutate_one_runtime_json(
        prepared.runtime_root,
        "task10_runtime_changed_after_evidence_retired",
    )
    authorization_calls: list[str] = []

    def forbid_release_authorization(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        authorization_calls.append("terminal")
        raise AssertionError("changed-runtime-reached-release-authorization")

    monkeypatch.setattr(
        live_start_session,
        "authorize_terminal_retirement_under_lock",
        forbid_release_authorization,
    )

    with pytest.raises(
        ValueError,
        match="^runtime_terminal_release_current_facts_changed$",
    ):
        published_apply.recover_apply_attempt(
            session_root=prepared.session_root
        )

    assert authorization_calls == []
    assert mutated_path.is_file()
    assert session_path.read_bytes() == session_bytes
    assert evidence.runtime_admission_path.read_bytes() == admission_bytes


def test_committed_mismatch_evidence_retired_revalidates_before_release_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_advance = live_start_session.advance_terminal_retirement_under_lock
    mismatch_created = False
    admission_path: Path | None = None

    def create_initial_mismatch(point: Any) -> None:
        nonlocal mismatch_created
        if (
            _point_value(point) == "after_physical_commit_before_installer_return"
            and not mismatch_created
        ):
            _mutate_one_runtime_json(
                prepared.runtime_root,
                "task10_initial_terminal_mismatch",
            )
            mismatch_created = True

    def crash_after_evidence_retired(*args: Any, **kwargs: Any) -> Any:
        successor = real_advance(*args, **kwargs)
        if kwargs.get("transition") == "evidence_retired":
            raise RuntimeError("crash-after-mismatch-evidence-retired")
        return successor

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
            fault_hook=create_initial_mismatch,
        ) as held:
            assert held.result.runtime_match_status == "mismatch"
            admission_path = held.runtime_admission_evidence.admission_path
            terminal = _terminalize_result(
                session_lease=capabilities.session_lease,
                held=held,
            )
            monkeypatch.setattr(
                live_start_session,
                "advance_terminal_retirement_under_lock",
                crash_after_evidence_retired,
            )
            with pytest.raises(
                RuntimeError,
                match="^crash-after-mismatch-evidence-retired$",
            ):
                held.resolve_and_release_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=terminal,
                )

    assert admission_path is not None
    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        real_advance,
    )
    session_path = prepared.session_root / "session.json"
    session_bytes = session_path.read_bytes()
    admission_bytes = admission_path.read_bytes()
    _mutate_one_runtime_json(
        prepared.runtime_root,
        "task10_changed_after_mismatch_evidence_retired",
    )
    authorization_calls: list[str] = []

    def forbid_release_authorization(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        authorization_calls.append("terminal")
        raise AssertionError("changed-mismatch-reached-release-authorization")

    monkeypatch.setattr(
        live_start_session,
        "authorize_terminal_retirement_under_lock",
        forbid_release_authorization,
    )

    with pytest.raises(
        ValueError,
        match="^runtime_terminal_release_current_facts_changed$",
    ):
        published_apply.recover_apply_attempt(session_root=prepared.session_root)

    assert authorization_calls == []
    assert session_path.read_bytes() == session_bytes
    assert admission_path.read_bytes() == admission_bytes


def test_committed_mismatch_evidence_retired_resumes_terminal_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_advance = live_start_session.advance_terminal_retirement_under_lock
    mismatch_created = False
    historical_result: Any | None = None
    historical_intent: Mapping[str, Any] | None = None
    admission_path: Path | None = None
    retained_before: dict[Path, tuple[tuple[int, ...], bytes]] | None = None
    result_payloads: dict[str, bytes] | None = None

    def create_initial_mismatch(point: Any) -> None:
        nonlocal mismatch_created
        if (
            _point_value(point) == "after_physical_commit_before_installer_return"
            and not mismatch_created
        ):
            _mutate_one_runtime_json(
                prepared.runtime_root,
                "task10_resumable_terminal_mismatch",
            )
            mismatch_created = True

    def crash_after_evidence_retired(*args: Any, **kwargs: Any) -> Any:
        successor = real_advance(*args, **kwargs)
        if kwargs.get("transition") == "evidence_retired":
            raise RuntimeError("crash-after-resumable-mismatch-evidence-retired")
        return successor

    with _lease_published_capabilities(prepared) as capabilities:
        with _composite(
            published_apply,
            capabilities,
            apply_attempt_id=_ATTEMPT_A,
            fault_hook=create_initial_mismatch,
        ) as held:
            historical_result = held.result
            assert historical_result.runtime_match_status == "mismatch"
            admission_path = held.runtime_admission_evidence.admission_path
            retained_paths = {
                path
                for path in (
                    historical_result.retained_attempt_record_path,
                    historical_result.retained_journal_path,
                    historical_result.retained_target_owner_journal_path,
                )
                if path is not None
            }
            retained_before = {
                path: (path_identity(path), path.read_bytes())
                for path in retained_paths
            }
            terminal = _terminalize_result(
                session_lease=capabilities.session_lease,
                held=held,
            )
            historical_intent = terminal.result_intent
            assert isinstance(historical_intent, Mapping)
            result_payloads = {
                relative: (prepared.session_root / relative).read_bytes()
                for relative in ("result/summary.json", "result/summary.md")
            }
            monkeypatch.setattr(
                live_start_session,
                "advance_terminal_retirement_under_lock",
                crash_after_evidence_retired,
            )
            with pytest.raises(
                RuntimeError,
                match="^crash-after-resumable-mismatch-evidence-retired$",
            ):
                held.resolve_and_release_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=terminal,
                )

    assert historical_result is not None
    assert historical_intent is not None
    assert admission_path is not None and admission_path.is_file()
    assert retained_before is not None
    assert result_payloads is not None
    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        real_advance,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered == historical_result
    persisted = live_start_session.load_live_start_session(prepared.session_root)
    assert persisted.result_intent == historical_intent
    assert persisted.attempt_acknowledgement is None
    assert persisted.terminal_retirement is not None
    assert persisted.terminal_retirement["operation"] == (
        "release_committed_mismatch"
    )
    assert (
        persisted.terminal_retirement["stage"]
        == "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert not admission_path.exists()
    assert {
        path: (path_identity(path), path.read_bytes())
        for path in retained_before
    } == retained_before
    assert {
        relative: (prepared.session_root / relative).read_bytes()
        for relative in result_payloads
    } == result_payloads


def test_not_committed_evidence_retired_revalidates_pre_apply_snapshot_before_release_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_advance = live_start_session.advance_terminal_retirement_under_lock
    admission_path: Path | None = None

    def crash_after_output_handoff(point: Any) -> None:
        if _point_value(point) == "after_output_operation_admission_unlink":
            raise RuntimeError("crash-before-not-committed-recovery")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-not-committed-recovery$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_output_handoff,
            ):
                pass

    from hsconfig.operator_profile import (
        lease_operator_profile,
        load_operator_profile,
    )
    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
    )

    def crash_after_evidence_retired(*args: Any, **kwargs: Any) -> Any:
        successor = real_advance(*args, **kwargs)
        if kwargs.get("transition") == "evidence_retired":
            raise RuntimeError("crash-after-not-committed-evidence-retired")
        return successor

    with live_start_session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        interrupted = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                with published_apply.recover_apply_attempt_under_lock(
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    output_operation_lease=operation_lease,
                    expected_session=interrupted,
                ) as recovered:
                    held = recovered.held
                    assert _disposition_value(held.result) == "NOT_COMMITTED"
                    assert held.result.runtime_match_status == "not_run"
                    admission_path = held.runtime_admission_evidence.admission_path
                    terminal = _terminalize_result(
                        session_lease=session_lease,
                        held=held,
                    )
                    monkeypatch.setattr(
                        live_start_session,
                        "advance_terminal_retirement_under_lock",
                        crash_after_evidence_retired,
                    )
                    with pytest.raises(
                        RuntimeError,
                        match=(
                            "^crash-after-not-committed-evidence-retired$"
                        ),
                    ):
                        held.release_admission_after_terminal(
                            session_lease=session_lease,
                            expected_terminal_session=terminal,
                        )

    assert admission_path is not None
    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        real_advance,
    )
    session_path = prepared.session_root / "session.json"
    session_bytes = session_path.read_bytes()
    admission_bytes = admission_path.read_bytes()
    changed_state = prepared.runtime_root / ".hsconfig" / "state.json"
    changed_state.write_bytes(b"{}\n")
    authorization_calls: list[str] = []

    def forbid_release_authorization(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        authorization_calls.append("terminal")
        raise AssertionError("changed-pre-apply-reached-release-authorization")

    monkeypatch.setattr(
        live_start_session,
        "authorize_terminal_retirement_under_lock",
        forbid_release_authorization,
    )

    with pytest.raises(
        ValueError,
        match="^runtime_terminal_release_current_facts_changed$",
    ):
        published_apply.recover_apply_attempt(session_root=prepared.session_root)

    assert authorization_calls == []
    assert changed_state.read_bytes() == b"{}\n"
    assert session_path.read_bytes() == session_bytes
    assert admission_path.read_bytes() == admission_bytes


def test_not_committed_releases_admission_only_after_terminal_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_apply = _published_apply()
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    real_advance = live_start_session.advance_terminal_retirement_under_lock
    real_authorize = live_start_session.authorize_terminal_retirement_under_lock
    real_release = published_apply._release_runtime_live_attempt_from_pair
    historical_result: Any | None = None
    historical_intent: Mapping[str, Any] | None = None
    admission_path: Path | None = None
    result_payloads: dict[str, bytes] | None = None

    def crash_after_output_handoff(point: Any) -> None:
        if _point_value(point) == "after_output_operation_admission_unlink":
            raise RuntimeError("crash-before-resumable-not-committed")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(
            RuntimeError,
            match="^crash-before-resumable-not-committed$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_output_handoff,
            ):
                pass

    from hsconfig.operator_profile import (
        lease_operator_profile,
        load_operator_profile,
    )
    from hsconfig.output_operation_admission import (
        lease_output_operation_admission,
    )

    def crash_after_evidence_retired(*args: Any, **kwargs: Any) -> Any:
        successor = real_advance(*args, **kwargs)
        if kwargs.get("transition") == "evidence_retired":
            raise RuntimeError("crash-after-resumable-not-committed-evidence")
        return successor

    with live_start_session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        interrupted = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                with published_apply.recover_apply_attempt_under_lock(
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    output_operation_lease=operation_lease,
                    expected_session=interrupted,
                ) as recovered:
                    held = recovered.held
                    historical_result = held.result
                    assert _disposition_value(historical_result) == "NOT_COMMITTED"
                    assert historical_result.runtime_match_status == "not_run"
                    admission_path = held.runtime_admission_evidence.admission_path
                    terminal = _terminalize_result(
                        session_lease=session_lease,
                        held=held,
                    )
                    historical_intent = terminal.result_intent
                    assert isinstance(historical_intent, Mapping)
                    result_payloads = {
                        relative: (prepared.session_root / relative).read_bytes()
                        for relative in (
                            "result/summary.json",
                            "result/summary.md",
                        )
                    }
                    monkeypatch.setattr(
                        live_start_session,
                        "advance_terminal_retirement_under_lock",
                        crash_after_evidence_retired,
                    )
                    with pytest.raises(
                        RuntimeError,
                        match=(
                            "^crash-after-resumable-not-committed-evidence$"
                        ),
                    ):
                        held.release_admission_after_terminal(
                            session_lease=session_lease,
                            expected_terminal_session=terminal,
                        )

    assert historical_result is not None
    assert historical_intent is not None
    assert admission_path is not None and admission_path.is_file()
    assert result_payloads is not None
    events: list[str] = []

    def trace_authorization(*args: Any, **kwargs: Any) -> Any:
        retirement = kwargs["expected_retirement_session"].terminal_retirement
        assert isinstance(retirement, Mapping)
        events.append(f"authorize:{retirement['stage']}")
        return real_authorize(*args, **kwargs)

    def trace_advance(*args: Any, **kwargs: Any) -> Any:
        successor = real_advance(*args, **kwargs)
        if kwargs.get("transition") == "admission_release_authorized":
            events.append("cas:ADMISSION_RELEASE_AUTHORIZED")
        return successor

    def trace_release(*args: Any, **kwargs: Any) -> Any:
        events.append("release:runtime_admission")
        return real_release(*args, **kwargs)

    monkeypatch.setattr(
        live_start_session,
        "authorize_terminal_retirement_under_lock",
        trace_authorization,
    )
    monkeypatch.setattr(
        live_start_session,
        "advance_terminal_retirement_under_lock",
        trace_advance,
    )
    monkeypatch.setattr(
        published_apply,
        "_release_runtime_live_attempt_from_pair",
        trace_release,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=prepared.session_root
    )

    assert recovered == historical_result
    assert events == [
        "authorize:EVIDENCE_RETIRED",
        "cas:ADMISSION_RELEASE_AUTHORIZED",
        "authorize:ADMISSION_RELEASE_AUTHORIZED",
        "release:runtime_admission",
    ]
    persisted = live_start_session.load_live_start_session(prepared.session_root)
    assert persisted.result_intent == historical_intent
    assert persisted.attempt_acknowledgement is None
    assert persisted.terminal_retirement is not None
    assert persisted.terminal_retirement["operation"] == "release_not_committed"
    assert (
        persisted.terminal_retirement["stage"]
        == "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert not admission_path.exists()
    assert {
        relative: (prepared.session_root / relative).read_bytes()
        for relative in result_payloads
    } == result_payloads


def test_old_success_fast_path_accepts_completed_owner_retirement_tombstone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hsconfig.runtime_installer as runtime_installer
    from hsconfig.runtime_transaction_journal import RuntimeTransactionPhase
    from tests.test_runtime_installer import (
        _changed_single_candidate_request_for_existing_runtime,
        _controller_pair_post_handoff_fixture,
        _exercise_candidate_bound_prefix,
        _filesystem_surface_evidence,
        _prepared_owning_success_ack_cursor,
        _prepared_pipeline_for_existing_runtime,
    )

    published_apply = _published_apply()
    first_context = _prepared_owning_success_ack_cursor(
        tmp_path / "first",
        monkeypatch,
        existing_child_precondition=True,
    )
    first_fixture = first_context.fixture
    first_prepared = first_context.prepared
    first_acknowledgement = first_prepared.attempt_acknowledgement
    assert first_acknowledgement is not None
    old_admission = first_fixture.runtime_admission
    old_owner_path = Path(
        str(first_acknowledgement["target_owner_journal_path"])
    )
    old_target_path = Path(str(first_acknowledgement["target_path"]))

    historical_result = published_apply.recover_apply_attempt(
        session_root=first_fixture.pipeline.session_root
    )

    assert historical_result.last_apply_receipt_sha256 is not None
    assert not old_admission.admission_path.exists()
    assert old_owner_path.is_file()
    assert old_target_path.is_dir()
    first_session_path = first_fixture.pipeline.session_root / "session.json"
    first_terminal = live_start_session.load_live_start_session(
        first_fixture.pipeline.session_root
    )
    assert first_terminal.terminal_retirement is not None
    assert (
        first_terminal.terminal_retirement["stage"]
        == "ADMISSION_RELEASE_AUTHORIZED"
    )

    changed_request = _changed_single_candidate_request_for_existing_runtime(
        root=tmp_path / "successor-authority",
        fixture=first_fixture,
        monkeypatch=monkeypatch,
    )
    second_pipeline = _prepared_pipeline_for_existing_runtime(
        root=tmp_path / "successor-run",
        fixture=first_fixture,
        request=changed_request,
    )
    second_fixture = _controller_pair_post_handoff_fixture(
        tmp_path / "successor-controller",
        monkeypatch,
        prepared_pipeline=second_pipeline,
        expect_existing_runtime=True,
        apply_attempt_id=_ATTEMPT_B,
    )
    second = _exercise_candidate_bound_prefix(
        tmp_path / "successor-route",
        monkeypatch,
        through_owner_bind=True,
        through_committed=True,
        fixture=second_fixture,
    )

    recovery = second.recovery
    retirement = recovery["owner_retirement"]
    assert isinstance(retirement, Mapping)
    assert retirement["stage"] == "OWNER_RETIRED"
    runtime_root = first_fixture.pipeline.runtime_root
    tombstone_path = Path(str(retirement["tombstone_path"]))
    tombstone = runtime_installer._parse_owner_retirement_tombstone_bytes(
        tombstone_path.read_bytes(),
        runtime_root=runtime_root,
    )
    assert tombstone["state"] == "COMPLETED"
    assert (
        tombstone["retired_owner_transaction_id"]
        == old_admission.apply_attempt_id
    )
    assert Path(str(tombstone["initial_owner_journal_path"])) == old_owner_path
    assert tuple(tombstone["initial_owner_journal_identity"]) == tuple(
        first_acknowledgement["target_owner_journal_identity"]
    )
    assert (
        tombstone["initial_owner_journal_sha256"]
        == first_acknowledgement["target_owner_journal_sha256"]
    )
    assert Path(str(tombstone["retired_target_path"])) == old_target_path
    assert tuple(tombstone["retired_target_identity"]) == tuple(
        first_acknowledgement["target_identity"]
    )
    assert not old_owner_path.exists()
    assert not old_target_path.exists()

    successor_owner_path = Path(
        str(tombstone["successor_owner_journal_path"])
    )
    successor_owner = runtime_installer.read_runtime_transaction_journal(
        successor_owner_path
    )
    assert successor_owner.transaction_id == _ATTEMPT_B
    assert successor_owner.phase is RuntimeTransactionPhase.FINALIZED
    assert successor_owner.owns_target is True
    successor_target_path = Path(str(recovery["renamed_target_path"]))
    assert successor_owner.target_path == successor_target_path.relative_to(
        runtime_root
    ).as_posix()

    successor_receipt_path = runtime_installer._receipt_path(
        runtime_root,
        successor_owner.state_key,
    )
    successor_runtime_paths = (
        runtime_root / "CustomConfig" / "deck_config.ini",
        runtime_root / ".hsconfig" / "state.json",
        successor_receipt_path,
    )
    assert all(path.is_file() for path in successor_runtime_paths)
    successor_receipt_sha256 = (
        "sha256:" + sha256(successor_receipt_path.read_bytes()).hexdigest()
    )
    assert (
        successor_receipt_sha256
        != historical_result.last_apply_receipt_sha256
    )
    successor_admission_path = second_fixture.runtime_admission.admission_path
    assert successor_admission_path == old_admission.admission_path
    assert path_identity(successor_admission_path) == (
        second_fixture.runtime_admission.admission_identity
    )
    assert second_fixture.runtime_admission.admission_identity != (
        old_admission.admission_identity
    )
    assert second_fixture.runtime_admission.admission_sha256 != (
        old_admission.admission_sha256
    )

    second_session_path = second_pipeline.session_root / "session.json"
    immutable_files = (
        first_session_path,
        second_session_path,
        tombstone_path,
        successor_owner_path,
        *successor_runtime_paths,
        successor_admission_path,
    )
    immutable_before = {
        path: (path_identity(path), path.read_bytes())
        for path in immutable_files
    }
    successor_target_before = _filesystem_surface_evidence(
        successor_target_path
    )
    _forbid_terminal_old_capability_reacquisition(
        published_apply=published_apply,
        monkeypatch=monkeypatch,
    )

    recovered = published_apply.recover_apply_attempt(
        session_root=first_fixture.pipeline.session_root
    )

    assert recovered == historical_result
    assert recovered.last_apply_receipt_sha256 == (
        historical_result.last_apply_receipt_sha256
    )
    assert recovered.last_apply_receipt_sha256 != successor_receipt_sha256
    assert {
        path: (path_identity(path), path.read_bytes())
        for path in immutable_files
    } == immutable_before
    assert _filesystem_surface_evidence(successor_target_path) == (
        successor_target_before
    )
