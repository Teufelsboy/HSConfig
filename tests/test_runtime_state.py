from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

import hsconfig.runtime_state as runtime_state
from hsconfig.runtime_state import (
    RuntimeDeckState,
    RuntimeState,
    read_runtime_state,
    serialize_runtime_state,
)


HEX_A = "a" * 64
HEX_B = "b" * 64


def _deck(**overrides: Any) -> RuntimeDeckState:
    values: dict[str, Any] = {
        "state_key": "shadow-priest",
        "deck_name": "Shadow Priest",
        "config_dir": f"ShadowPriest--sha256-{HEX_A}",
        "package_root_sha256": HEX_A,
        "ini_sha256": HEX_B,
    }
    values.update(overrides)
    return RuntimeDeckState(**values)


def _state_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _make_junction(link: Path, target: Path) -> None:
    if os.name != "nt":
        pytest.skip("Windows junction coverage")
    completed = subprocess.run(
        [
            "cmd.exe",
            "/d",
            "/c",
            "mklink",
            "/J",
            str(link),
            str(target),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip(f"directory junctions unavailable: {completed.stderr}")


class _StatusWithLinkCount:
    def __init__(self, status: os.stat_result, count: int) -> None:
        self._status = status
        self.st_nlink = count

    def __getattr__(self, name: str) -> object:
        return getattr(self._status, name)


def _payload() -> dict[str, Any]:
    return {
        "decks": [
            {
                "config_dir": f"ShadowPriest--sha256-{HEX_A}",
                "deck_name": "Shadow Priest",
                "ini_sha256": HEX_B,
                "package_root_sha256": HEX_A,
                "state_key": "shadow-priest",
            }
        ],
        "schema_version": 1,
    }


def test_read_runtime_state_returns_none_when_state_file_is_missing(
    tmp_path: Path,
) -> None:
    assert read_runtime_state(tmp_path) is None


def test_runtime_state_serializer_is_canonical_and_order_independent() -> None:
    alpha = _deck()
    beta = _deck(
        state_key="zoo-warlock",
        deck_name="Zoo Warlock",
        config_dir=f"ZooWarlock--sha256-{HEX_B}",
        package_root_sha256=HEX_B,
        ini_sha256=HEX_A,
    )

    forward = serialize_runtime_state(RuntimeState(1, (alpha, beta)))
    reverse = serialize_runtime_state(RuntimeState(1, (beta, alpha)))

    assert forward == reverse
    assert forward.endswith(b"\n")
    assert json.loads(forward) == {
        "decks": [
            {
                "config_dir": f"ShadowPriest--sha256-{HEX_A}",
                "deck_name": "Shadow Priest",
                "ini_sha256": HEX_B,
                "package_root_sha256": HEX_A,
                "state_key": "shadow-priest",
            },
            {
                "config_dir": f"ZooWarlock--sha256-{HEX_B}",
                "deck_name": "Zoo Warlock",
                "ini_sha256": HEX_A,
                "package_root_sha256": HEX_B,
                "state_key": "zoo-warlock",
            },
        ],
        "schema_version": 1,
    }


def test_read_runtime_state_round_trips_canonical_unicode_state(
    tmp_path: Path,
) -> None:
    state = RuntimeState(
        schema_version=1,
        decks=(
            _deck(
                state_key="schattenpriester",
                deck_name="Schattenpriester Überfall",
                config_dir=f"Schattenpriester--sha256-{HEX_A}",
            ),
        ),
    )
    path = tmp_path / ".hsconfig" / "state.json"
    path.parent.mkdir()
    path.write_bytes(serialize_runtime_state(state))

    assert read_runtime_state(tmp_path) == state


@pytest.mark.parametrize(
    ("raw", "error_code"),
    [
        (b"\xff", "runtime_state_invalid_encoding"),
        (b"{", "runtime_state_invalid_json"),
        (
            b'{"schema_version":1,"schema_version":1,"decks":[]}',
            "runtime_state_duplicate_json_key",
        ),
        (_state_bytes({"schema_version": 1}), "runtime_state_invalid_schema"),
        (
            _state_bytes(
                {"schema_version": 1, "decks": [], "unexpected": True}
            ),
            "runtime_state_invalid_schema",
        ),
        (
            _state_bytes({"schema_version": True, "decks": []}),
            "runtime_state_invalid_schema",
        ),
        (
            _state_bytes({"schema_version": 2, "decks": []}),
            "runtime_state_invalid_schema",
        ),
        (
            _state_bytes({"schema_version": 1, "decks": {}}),
            "runtime_state_invalid_schema",
        ),
    ],
)
def test_read_runtime_state_rejects_invalid_document_envelopes(
    tmp_path: Path,
    raw: bytes,
    error_code: str,
) -> None:
    path = tmp_path / ".hsconfig" / "state.json"
    path.parent.mkdir()
    path.write_bytes(raw)

    with pytest.raises(ValueError, match=f"^{error_code}$"):
        read_runtime_state(tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("state_key", "", "runtime_state_unsafe_name"),
        ("state_key", "../deck", "runtime_state_unsafe_name"),
        ("state_key", "CON", "runtime_state_unsafe_name"),
        ("deck_name", " Deck", "runtime_state_unsafe_name"),
        ("deck_name", "Deck=Other", "runtime_state_unsafe_name"),
        ("deck_name", ";Deck", "runtime_state_unsafe_name"),
        ("deck_name", "#Deck", "runtime_state_unsafe_name"),
        ("config_dir", "../Config", "runtime_state_unsafe_name"),
        ("config_dir", "Config\\Child", "runtime_state_unsafe_name"),
        ("package_root_sha256", "A" * 64, "runtime_state_invalid_digest"),
        ("package_root_sha256", "a" * 63, "runtime_state_invalid_digest"),
        ("ini_sha256", "0" * 63 + "G", "runtime_state_invalid_digest"),
    ],
)
def test_read_runtime_state_rejects_unsafe_names_and_noncanonical_digests(
    tmp_path: Path,
    field: str,
    value: object,
    error_code: str,
) -> None:
    payload = _payload()
    payload["decks"][0][field] = value
    path = tmp_path / ".hsconfig" / "state.json"
    path.parent.mkdir()
    path.write_bytes(_state_bytes(payload))

    with pytest.raises(ValueError, match=f"^{error_code}$"):
        read_runtime_state(tmp_path)


@pytest.mark.parametrize("field", ["state_key", "deck_name"])
def test_read_runtime_state_rejects_casefolded_duplicate_identities(
    tmp_path: Path,
    field: str,
) -> None:
    payload = _payload()
    duplicate = dict(payload["decks"][0])
    duplicate["state_key"] = "other-key"
    duplicate["deck_name"] = "Other Deck"
    duplicate[field] = str(payload["decks"][0][field]).swapcase()
    duplicate["config_dir"] = f"Other--sha256-{HEX_B}"
    payload["decks"].append(duplicate)
    path = tmp_path / ".hsconfig" / "state.json"
    path.parent.mkdir()
    path.write_bytes(_state_bytes(payload))

    with pytest.raises(ValueError, match="^runtime_state_duplicate_identity$"):
        read_runtime_state(tmp_path)


def test_read_runtime_state_rejects_extra_or_missing_deck_keys(
    tmp_path: Path,
) -> None:
    for mutate in ("missing", "extra"):
        payload = _payload()
        if mutate == "missing":
            del payload["decks"][0]["ini_sha256"]
        else:
            payload["decks"][0]["extra"] = "value"
        path = tmp_path / ".hsconfig" / "state.json"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(_state_bytes(payload))

        with pytest.raises(ValueError, match="^runtime_state_invalid_schema$"):
            read_runtime_state(tmp_path)


def test_read_runtime_state_requires_canonical_serialized_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".hsconfig" / "state.json"
    path.parent.mkdir()
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    with pytest.raises(ValueError, match="^runtime_state_noncanonical$"):
        read_runtime_state(tmp_path)


def test_read_runtime_state_is_bounded(tmp_path: Path) -> None:
    path = tmp_path / ".hsconfig" / "state.json"
    path.parent.mkdir()
    path.write_bytes(b" " * (1024 * 1024 + 1))

    with pytest.raises(ValueError, match="^runtime_state_too_large$"):
        read_runtime_state(tmp_path)


def test_read_runtime_state_never_reads_or_selects_deck_config_ini(
    tmp_path: Path,
) -> None:
    state = RuntimeState(1, (_deck(),))
    state_path = tmp_path / ".hsconfig" / "state.json"
    state_path.parent.mkdir()
    state_path.write_bytes(serialize_runtime_state(state))
    ini_path = tmp_path / "CustomConfig" / "deck_config.ini"
    ini_path.parent.mkdir()
    ini_path.write_bytes(b"\xff invalid and deliberately unrelated")

    assert read_runtime_state(tmp_path) == state


def test_read_runtime_state_rejects_link_count_change_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / ".hsconfig" / "state.json"
    path.parent.mkdir()
    path.write_bytes(serialize_runtime_state(RuntimeState(1, (_deck(),))))
    real_fstat = os.fstat
    regular_calls = 0

    def mutate_final_regular_status(descriptor: int) -> os.stat_result:
        nonlocal regular_calls
        status = real_fstat(descriptor)
        if stat.S_ISREG(status.st_mode):
            regular_calls += 1
            if regular_calls >= 3:
                return _StatusWithLinkCount(status, 2)  # type: ignore[return-value]
        return status

    monkeypatch.setattr(runtime_state.os, "fstat", mutate_final_regular_status)

    with pytest.raises(ValueError, match="^runtime_state_unsafe_path$"):
        read_runtime_state(tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="NTFS junction coverage")
@pytest.mark.parametrize("position", ["direct", "parent", "ancestor"])
def test_read_runtime_state_rejects_ntfs_junctions_at_every_path_level(
    tmp_path: Path,
    position: str,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    canonical = serialize_runtime_state(RuntimeState(1, (_deck(),)))
    junction: Path
    if position == "direct":
        actual = external / "target-directory"
        actual.mkdir()
        runtime_root = tmp_path / "runtime"
        state_dir = runtime_root / ".hsconfig"
        state_dir.mkdir(parents=True)
        junction = state_dir / "state.json"
        _make_junction(junction, actual)
    elif position == "parent":
        actual = external / ".hsconfig"
        actual.mkdir()
        (actual / "state.json").write_bytes(canonical)
        runtime_root = tmp_path / "runtime"
        runtime_root.mkdir()
        junction = runtime_root / ".hsconfig"
        _make_junction(junction, actual)
    else:
        actual = external / "root"
        state_dir = actual / "runtime" / ".hsconfig"
        state_dir.mkdir(parents=True)
        (state_dir / "state.json").write_bytes(canonical)
        junction = tmp_path / "alias"
        _make_junction(junction, actual)
        runtime_root = junction / "runtime"
    try:
        with pytest.raises(ValueError, match="^runtime_state_unsafe_path$"):
            read_runtime_state(runtime_root)
    finally:
        junction.rmdir()


def test_read_runtime_state_rejects_symlink_or_hardlink_state_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(serialize_runtime_state(RuntimeState(1, (_deck(),))))
    state_dir = tmp_path / ".hsconfig"
    state_dir.mkdir()
    state_path = state_dir / "state.json"
    try:
        os.link(source, state_path)
    except OSError as exc:
        pytest.skip(f"hardlinks unavailable: {exc}")

    with pytest.raises(ValueError, match="^runtime_state_unsafe_path$"):
        read_runtime_state(tmp_path)


def test_read_runtime_state_rejects_reparse_state_parent_even_when_file_missing(
    tmp_path: Path,
) -> None:
    actual = tmp_path / "actual-state-dir"
    actual.mkdir()
    state_dir = tmp_path / ".hsconfig"
    try:
        state_dir.symlink_to(actual, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    with pytest.raises(ValueError, match="^runtime_state_unsafe_path$"):
        read_runtime_state(tmp_path)


def test_serialize_runtime_state_rejects_invalid_or_duplicate_models() -> None:
    with pytest.raises(ValueError, match="^runtime_state_duplicate_identity$"):
        serialize_runtime_state(
            RuntimeState(
                1,
                (
                    _deck(),
                    _deck(
                        state_key="SHADOW-PRIEST",
                        deck_name="Other Deck",
                    ),
                ),
            )
        )

    with pytest.raises(ValueError, match="^runtime_state_invalid_digest$"):
        serialize_runtime_state(
            RuntimeState(1, (_deck(package_root_sha256="A" * 64),))
        )

    with pytest.raises(ValueError, match="^runtime_state_invalid_digest$"):
        serialize_runtime_state(
            RuntimeState(1, (_deck(package_root_sha256=123),))  # type: ignore[arg-type]
        )
