from __future__ import annotations

import json
from collections.abc import Mapping
from collections import Counter
from typing import Any

import pytest

from hsconfig.config_quality_inputs import load_config_quality_inputs


class _MutableMemoryPackageView:
    package_label = "memory://quality-inputs"

    def __init__(self, files: Mapping[str, bytes | bytearray]) -> None:
        self.files = dict(files)
        self.poisoned = False
        self.file_names_calls = 0
        self.read_bytes_calls: Counter[str] = Counter()
        self.read_json_calls = 0
        self.exists_calls = 0

    def file_names(self) -> tuple[str, ...]:
        self._require_live()
        self.file_names_calls += 1
        return tuple(self.files)

    def read_bytes(self, relative_path: str) -> bytes:
        self._require_live()
        self.read_bytes_calls[relative_path] += 1
        return self.files[relative_path]  # type: ignore[return-value]

    def read_json(self, relative_path: str) -> Any:
        self.read_json_calls += 1
        return json.loads(self.read_bytes(relative_path).decode("utf-8-sig"))

    def exists(self, relative_path: str) -> bool:
        self._require_live()
        self.exists_calls += 1
        return relative_path in self.files

    def _require_live(self) -> None:
        if self.poisoned:
            raise AssertionError("the source view was consulted after loading")


def _json_bytes(value: Any, *, bom: bool = False) -> bytes:
    payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    return (b"\xef\xbb\xbf" + payload) if bom else payload


def test_loader_materializes_a_complete_deeply_immutable_byte_snapshot() -> None:
    source_bytes = bytearray(b'{"GameCardId":"CARD_001"}')
    source = _MutableMemoryPackageView(
        {
            "reports/deck_identity.json": _json_bytes(
                {"cards": [{"card_id": "CARD_001"}]},
                bom=True,
            ),
            "reports/disposition_ledger.json": _json_bytes(
                {"items": [{"claim_id": "claim_001", "status": "resolved"}]}
            ),
            "reports/source_acquisition_closure.json": _json_bytes(
                {"claims": [{"claim_id": "claim_001", "evidence_sha256": "sha256:a"}]}
            ),
            "reports/globalvalues_decision_ledger.json": _json_bytes(
                {"decisions": [{"key": "GlobalMinionAttack", "decision": "baseline"}]}
            ),
            "CustomConfig/deck/CARD_001.json": source_bytes,
        }
    )

    inputs = load_config_quality_inputs(source)
    source_bytes[:] = b"poisoned"
    source.files.clear()
    source.poisoned = True

    assert inputs.package.package_label == "memory://quality-inputs"
    assert inputs.package.file_names() == (
        "CustomConfig/deck/CARD_001.json",
        "reports/deck_identity.json",
        "reports/disposition_ledger.json",
        "reports/globalvalues_decision_ledger.json",
        "reports/source_acquisition_closure.json",
    )
    assert inputs.package.read_bytes("CustomConfig/deck/CARD_001.json") == (
        b'{"GameCardId":"CARD_001"}'
    )
    assert inputs.semantic_inventory["card_ids"] == ("CARD_001",)
    assert source.file_names_calls == 1
    assert source.read_bytes_calls == Counter(
        {
            "reports/deck_identity.json": 1,
            "reports/disposition_ledger.json": 1,
            "reports/source_acquisition_closure.json": 1,
            "reports/globalvalues_decision_ledger.json": 1,
            "CustomConfig/deck/CARD_001.json": 1,
        }
    )
    assert source.read_json_calls == 0
    assert source.exists_calls == 0

    with pytest.raises(TypeError):
        inputs.semantic_inventory["card_ids"] = ()  # type: ignore[index]
    with pytest.raises(TypeError):
        inputs.disposition_ledger["items"][0]["status"] = "poisoned"  # type: ignore[index]


@pytest.mark.parametrize(
    "file_names",
    [
        ("reports/operator_summary.json", "reports/operator_summary.json"),
        ("reports\\operator_summary.json",),
        ("../reports/operator_summary.json",),
    ],
)
def test_loader_rejects_noncanonical_or_duplicate_file_names_deterministically(
    file_names: tuple[str, ...],
) -> None:
    class _InvalidNamesView(_MutableMemoryPackageView):
        def file_names(self) -> tuple[str, ...]:
            return file_names

    source = _InvalidNamesView({"reports/operator_summary.json": b"{}"})

    with pytest.raises(
        ValueError,
        match="config_quality_package_file_names_invalid",
    ):
        load_config_quality_inputs(source)


def test_loader_snapshots_every_declared_artifact_and_unrelated_file_once() -> None:
    paths = (
        "reports/operator_summary.json",
        "reports/card_behavior_plan_report.json",
        "reports/source_to_runtime_explainability.json",
        "reports/deck_identity.json",
        "reports/semantic_enrichment_report.json",
        "reports/surface_intent.json",
        "reports/gameplan_contract.json",
        "reports/guide_claim_bundle.json",
        "reports/globalvalues_profile.json",
        "reports/mulligan_plan_report.json",
        "reports/source_contract_audit.json",
        "package_derivation_receipt.json",
        "reports/runtime_surface_ledger.json",
        "reports/disposition_ledger.json",
        "reports/layered_evidence_contract.json",
        "reports/source_acquisition_closure.json",
        "reports/globalvalues_decision_ledger.json",
        "CustomConfig/deck/GlobalValues.json",
        "CustomConfig/deck/Mulligan.json",
        "CustomConfig/deck/CARD_001.json",
        "notes/unrelated.txt",
    )
    source = _MutableMemoryPackageView(
        {
            path: (
                b"unrelated"
                if path == "notes/unrelated.txt"
                else b"{}"
            )
            for path in reversed(paths)
        }
    )

    inputs = load_config_quality_inputs(source)

    assert inputs.package.file_names() == tuple(sorted(paths))
    assert source.file_names_calls == 1
    assert source.read_bytes_calls == Counter({path: 1 for path in paths})
    assert source.read_json_calls == 0
    assert source.exists_calls == 0
    assert inputs.package.read_bytes("notes/unrelated.txt") == b"unrelated"


def test_loader_preserves_bom_bytes_while_decoding_utf8_sig() -> None:
    raw = b'\xef\xbb\xbf{"cards":[{"card_id":"CARD_001"}]}'
    source = _MutableMemoryPackageView(
        {"reports/deck_identity.json": raw}
    )

    inputs = load_config_quality_inputs(source)

    assert inputs.package.read_bytes("reports/deck_identity.json") == raw
    assert inputs.semantic_inventory["card_ids"] == ("CARD_001",)


def test_loader_deduplicates_repeated_and_cross_zone_card_membership() -> None:
    source = _MutableMemoryPackageView(
        {
            "reports/deck_identity.json": _json_bytes(
                {
                    "cards": [{"card_id": "MAIN_001"}],
                    "sideboards": [
                        {
                            "cards": [
                                {"card_id": "MAIN_001"},
                                {"card_id": "SIDE_001"},
                            ]
                        },
                        {"cards": [{"card_id": "SIDE_001"}]},
                    ],
                }
            )
        }
    )

    inputs = load_config_quality_inputs(source)

    assert inputs.semantic_inventory["card_identity_rows"] == (
        "MAIN_001",
        "SIDE_001",
    )


def test_loader_requires_an_explicit_stable_memory_label() -> None:
    class _UnlabelledView(_MutableMemoryPackageView):
        package_label = ""

    with pytest.raises(
        ValueError,
        match="config_quality_package_label_invalid",
    ):
        load_config_quality_inputs(_UnlabelledView({}))


def test_loader_propagates_a_listed_file_read_failure() -> None:
    class _ReadFailureView(_MutableMemoryPackageView):
        def read_bytes(self, relative_path: str) -> bytes:
            raise RuntimeError("quality-view-boom")

    with pytest.raises(RuntimeError, match="quality-view-boom"):
        load_config_quality_inputs(
            _ReadFailureView({"reports/operator_summary.json": b"{}"})
        )
