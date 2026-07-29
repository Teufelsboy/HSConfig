"""Immutable input boundary for diagnostic package-quality evaluation."""

from __future__ import annotations

import json
from fnmatch import fnmatchcase
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from hsconfig.package_domain import canonical_relative_path
from hsconfig.package_derivation_receipt import (
    verify_package_derivation_receipt_from_view,
)
from hsconfig.package_model import DirectoryPackageView, PackageView
from hsconfig.runtime_surface_ledger import (
    rederive_runtime_surface_ledger_from_view,
)


_DISPOSITION_LEDGER_PATH = "reports/disposition_ledger.json"
_SOURCE_CLOSURE_PATH = "reports/layered_evidence_contract.json"
_SOURCE_ACQUISITION_PATH = "reports/source_acquisition_closure.json"
_SOURCE_CONTRACT_AUDIT_PATH = "reports/source_contract_audit.json"
_GLOBALVALUES_LEDGER_PATH = "reports/globalvalues_decision_ledger.json"
_DECK_IDENTITY_PATH = "reports/deck_identity.json"


@dataclass(frozen=True, slots=True)
class FrozenPackageSnapshot:
    """A complete, stable byte copy of one package view."""

    package_label: str
    _names: tuple[str, ...]
    _files: Mapping[str, bytes]
    derivation_receipt_verified: bool = False
    rederived_runtime_surface_ledger: Mapping[str, Any] | None = None

    def file_names(self) -> tuple[str, ...]:
        return self._names

    def read_bytes(self, relative_path: str) -> bytes:
        path = canonical_relative_path(relative_path)
        try:
            return self._files[path]
        except KeyError as error:
            raise FileNotFoundError(path) from error

    def read_json(self, relative_path: str) -> Any:
        return _canonicalize_json_value(
            json.loads(
                self.read_bytes(relative_path).decode("utf-8-sig")
            )
        )

    def exists(self, relative_path: str) -> bool:
        try:
            path = canonical_relative_path(relative_path)
        except ValueError:
            return False
        return path in self._files

    def root_path(self) -> FrozenPackagePath:
        return FrozenPackagePath(self, "")


@dataclass(frozen=True, slots=True)
class FrozenPackagePath:
    """The pathlib subset used by legacy diagnostic checks, backed by memory."""

    package: FrozenPackageSnapshot
    relative_path: str

    def __truediv__(self, value: object) -> FrozenPackagePath:
        child = str(value).replace("\\", "/")
        joined = "/".join(part for part in (self.relative_path, child) if part)
        return FrozenPackagePath(self.package, canonical_relative_path(joined))

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, FrozenPackagePath):
            return NotImplemented
        return self.relative_path < other.relative_path

    def __str__(self) -> str:
        if not self.relative_path:
            return self.package.package_label
        return f"{self.package.package_label.rstrip('/')}/{self.relative_path}"

    @property
    def name(self) -> str:
        return PurePosixPath(self.relative_path).name

    def as_posix(self) -> str:
        return self.relative_path

    def is_file(self) -> bool:
        return self.relative_path in self.package._files

    def is_dir(self) -> bool:
        prefix = f"{self.relative_path}/" if self.relative_path else ""
        return any(name.startswith(prefix) for name in self.package._names)

    def read_text(self, *, encoding: str = "utf-8") -> str:
        return self.package.read_bytes(self.relative_path).decode(encoding)

    def iterdir(self) -> tuple[FrozenPackagePath, ...]:
        if not self.is_dir():
            return ()
        prefix = f"{self.relative_path}/" if self.relative_path else ""
        children = {
            name[len(prefix) :].split("/", 1)[0]
            for name in self.package._names
            if name.startswith(prefix) and name != self.relative_path
        }
        return tuple(self / child for child in sorted(children))

    def glob(self, pattern: str) -> tuple[FrozenPackagePath, ...]:
        return tuple(
            child
            for child in self.iterdir()
            if child.is_file() and fnmatchcase(child.name, pattern)
        )

    def rglob(self, pattern: str) -> tuple[FrozenPackagePath, ...]:
        prefix = f"{self.relative_path}/" if self.relative_path else ""
        return tuple(
            FrozenPackagePath(self.package, name)
            for name in self.package._names
            if name.startswith(prefix)
            and fnmatchcase(PurePosixPath(name).name, pattern)
        )

    def relative_to(self, root: FrozenPackagePath) -> PurePosixPath:
        if self.package is not root.package:
            raise ValueError("config_quality_package_root_mismatch")
        if not root.relative_path:
            return PurePosixPath(self.relative_path)
        prefix = f"{root.relative_path}/"
        if not self.relative_path.startswith(prefix):
            raise ValueError("config_quality_package_root_mismatch")
        return PurePosixPath(self.relative_path[len(prefix) :])


@dataclass(frozen=True, slots=True)
class ConfigQualityInputs:
    """All data permitted to influence one quality evaluation."""

    package: FrozenPackageSnapshot
    semantic_inventory: Mapping[str, Any]
    disposition_ledger: Mapping[str, Any]
    source_closure: Mapping[str, Any]
    globalvalues_ledger: Mapping[str, Any]


def load_config_quality_inputs(package: PackageView) -> ConfigQualityInputs:
    """Materialize a complete package view without retaining live references."""

    names = _canonical_file_names(package.file_names())
    files: dict[str, bytes] = {}
    for relative_path in names:
        value = package.read_bytes(relative_path)
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError("config_quality_package_bytes_invalid")
        files[relative_path] = memoryview(value).tobytes()

    snapshot = FrozenPackageSnapshot(
        package_label=_package_label(package),
        _names=names,
        _files=MappingProxyType(files),
    )
    receipt = _read_optional_mapping(
        snapshot,
        "package_derivation_receipt.json",
    )
    ledger = _read_optional_mapping(
        snapshot,
        "reports/runtime_surface_ledger.json",
    )
    receipt_verified = False
    rederived_ledger: Mapping[str, Any] | None = None
    if receipt:
        receipt_verified, _reasons = (
            verify_package_derivation_receipt_from_view(
                snapshot,
                receipt,
            )
        )
    if receipt_verified and ledger:
        try:
            rederived_ledger = _freeze(
                rederive_runtime_surface_ledger_from_view(snapshot)
            )
        except (OSError, TypeError, ValueError):
            rederived_ledger = None
    snapshot = FrozenPackageSnapshot(
        package_label=snapshot.package_label,
        _names=snapshot._names,
        _files=snapshot._files,
        derivation_receipt_verified=receipt_verified,
        rederived_runtime_surface_ledger=rederived_ledger,
    )
    deck_identity = _read_optional_mapping(snapshot, _DECK_IDENTITY_PATH)
    source_contract_audit = _read_optional_mapping(
        snapshot,
        _SOURCE_CONTRACT_AUDIT_PATH,
    )
    disposition = _read_optional_mapping(snapshot, _DISPOSITION_LEDGER_PATH)
    layered_evidence = _read_optional_mapping(
        snapshot,
        _SOURCE_CLOSURE_PATH,
    )
    source_acquisition = _read_optional_mapping(
        snapshot,
        _SOURCE_ACQUISITION_PATH,
    )
    source_closure = {
        key: value
        for key, value in (
            ("source_contract_audit", source_contract_audit),
            ("layered_evidence_contract", layered_evidence),
            ("source_acquisition_closure", source_acquisition),
        )
        if value
    }
    globalvalues = _read_optional_mapping(snapshot, _GLOBALVALUES_LEDGER_PATH)
    semantic_inventory = _semantic_inventory(
        deck_identity=deck_identity,
        source_closure=source_closure,
        globalvalues_ledger=globalvalues,
    )
    return ConfigQualityInputs(
        package=snapshot,
        semantic_inventory=_freeze(semantic_inventory),
        disposition_ledger=_freeze(disposition),
        source_closure=_freeze(source_closure),
        globalvalues_ledger=_freeze(globalvalues),
    )


def _canonical_file_names(values: Sequence[str]) -> tuple[str, ...]:
    try:
        names = tuple(values)
        canonical = tuple(canonical_relative_path(value) for value in names)
    except (TypeError, ValueError) as error:
        raise ValueError("config_quality_package_file_names_invalid") from error
    if len(set(canonical)) != len(canonical):
        raise ValueError("config_quality_package_file_names_invalid")
    return tuple(sorted(canonical))


def _package_label(package: PackageView) -> str:
    if isinstance(package, DirectoryPackageView):
        return str(Path(package.root))
    value = getattr(package, "package_label", None)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("config_quality_package_label_invalid")
    return value


def _read_optional_mapping(
    package: FrozenPackageSnapshot,
    relative_path: str,
) -> dict[str, Any]:
    if not package.exists(relative_path):
        return {}
    try:
        value = package.read_json(relative_path)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _semantic_inventory(
    *,
    deck_identity: Mapping[str, Any],
    source_closure: Mapping[str, Any],
    globalvalues_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    card_identity_rows = _deck_card_identity_rows(deck_identity)
    (
        claim_identity_rows,
        source_claim_inventory_drift,
    ) = _source_claim_inventory(source_closure)
    claim_identity_rows = tuple(
        sorted(claim_identity_rows)
    )
    globalvalue_key_rows = tuple(sorted(_identity_rows(
        globalvalues_ledger.get("decisions"),
        "key",
    )))
    return {
        "card_ids": tuple(sorted(set(card_identity_rows))),
        "card_identity_rows": card_identity_rows,
        "claim_ids": tuple(sorted(set(claim_identity_rows))),
        "claim_identity_rows": claim_identity_rows,
        "source_claim_inventory_drift": source_claim_inventory_drift,
        "globalvalue_keys": tuple(sorted(set(globalvalue_key_rows))),
        "globalvalue_key_rows": globalvalue_key_rows,
    }


def _identity_rows(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return ()
    return tuple(
        str(row[key]).strip()
        for row in value
        if isinstance(row, Mapping) and str(row.get(key, "")).strip()
    )


def _deck_card_identity_rows(
    deck_identity: Mapping[str, Any],
) -> tuple[str, ...]:
    card_ids = {
        card_id
        for key in ("cards", "main_deck")
        for card_id in _identity_rows(deck_identity.get(key), "card_id")
    }
    sideboards = deck_identity.get("sideboards")
    if isinstance(sideboards, Sequence) and not isinstance(
        sideboards,
        (str, bytes, bytearray),
    ):
        for sideboard in sideboards:
            if not isinstance(sideboard, Mapping):
                continue
            card_ids.update(
                _identity_rows(
                    sideboard.get("cards"),
                    "card_id",
                )
            )
    return tuple(sorted(card_ids))


def _source_claim_inventory(
    value: Mapping[str, Any],
) -> tuple[list[str], dict[str, dict[str, tuple[str, ...]]]]:
    sources: dict[str, list[str]] = {}
    for key in (
        "source_contract_audit",
        "layered_evidence_contract",
        "source_acquisition_closure",
    ):
        nested = value.get(key)
        if not isinstance(nested, Mapping):
            continue
        identities = _closure_claim_id_rows(nested)
        if identities:
            sources[key] = identities
    if not sources:
        return _closure_claim_id_rows(value), {}

    canonical_key = next(iter(sources))
    canonical = Counter(sources[canonical_key])
    drift: dict[str, dict[str, tuple[str, ...]]] = {}
    for key, identities in sources.items():
        if key == canonical_key:
            continue
        observed = Counter(identities)
        missing = tuple(sorted((canonical - observed).elements()))
        unexpected = tuple(sorted((observed - canonical).elements()))
        if missing or unexpected:
            drift[key] = {
                "missing_claim_ids": missing,
                "unexpected_claim_ids": unexpected,
            }
    return sources[canonical_key], drift


def _closure_claim_id_rows(value: Mapping[str, Any]) -> list[str]:
    identities: list[str] = []
    for key in ("claims", "claim_rows", "source_claims"):
        rows = value.get(key)
        if isinstance(rows, Mapping):
            identities.extend(
                str(item).strip()
                for item in rows
                if str(item).strip()
            )
        else:
            identities.extend(_identity_rows(rows, "claim_id"))
    identities.extend(_identity_rows(value.get("authorities"), "claim_id"))
    for key in ("acquisition_closure",):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            identities.extend(_closure_claim_id_rows(nested))
    return identities


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze(nested)
                for key, nested in sorted(
                    value.items(),
                    key=lambda item: str(item[0]),
                )
            }
        )
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


def _canonicalize_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize_json_value(nested)
            for key, nested in sorted(
                value.items(),
                key=lambda item: str(item[0]),
            )
        }
    if isinstance(value, list):
        return [_canonicalize_json_value(item) for item in value]
    return value


__all__ = (
    "ConfigQualityInputs",
    "FrozenPackagePath",
    "FrozenPackageSnapshot",
    "load_config_quality_inputs",
)
