"""Canonical, fail-closed orchestration for the local release contract."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import threading
import time
import tomllib
from typing import Any, Literal
import uuid
import zipfile

import yaml

from hsconfig.near100_scorecard import (
    ATOMIC_CHECK_OWNERS,
    HARD_METRIC_IDS,
    SEMANTIC_CARD_MODULE_COUNT,
    SEMANTIC_CLAIM_COUNT,
)
from hsconfig.semantic_inventory import canonical_semantic_claim, validate_semantic_inventory
from hsconfig.version import __version__


TreeMode = Literal["working-pre-cutover", "candidate", "final"]

CHECK_NAMES = (
    "ruff",
    "full_tests_and_coverage",
    "contract_spine",
    "twelve_deck_acceptance",
    "contract_mutations",
    "dependency_audit",
    "distribution",
    "twelve_deck_determinism",
    "publishable_path_scan",
    "output_inventory",
    "package_immutability",
    "transaction_fault_matrix",
    "repository_hygiene",
    "version_consistency",
    "near100_scorecard",
)

_HISTORICAL_PREFIXES = (
    "docs/superpowers/plans/",
    "docs/research/",
    "docs/history/",
)
_PRIVATE_NAMES = re.compile(
    r"(?i)(?:^|[/\\])(?:"
    + "|".join(
        re.escape(name)
        for name in (
            "Power" + ".log",
            "Hearthstone" + ".log",
            "HearthRanger" + ".log",
        )
    )
    + r"|[^/\\]+\.(?:"
    + "|".join(("hdt" + "replay", "hs" + "replay"))
    + r")|runtime[_-]?evidence|private[_-]?runtime|runtime[_-]?exports)(?:$|[/\\])"
)
_ABSOLUTE_USER_PATH = re.compile(
    r"(?i)(?:(?<![a-z])[a-z]:[\\/](?![\\/])[^\s\"'`<>]+|"
    r"/(?:users|home)/[^/\s\"'`<>]+/|"
    r"(?:\\\\|(?<!:)//)(?:[a-z0-9$._-]+[\\/][a-z0-9$._-]+|[?.][\\/][a-z]:[\\/])"
    r"[^\s\"'`<>]*)"
)
_SECRET_PATTERNS = (
    ("secret", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("secret", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("secret", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "secret",
        re.compile(
            r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
        ),
    ),
    (
        "secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|"
            r"credential|private[_-]?key|auth(?:[_-]?(?:token|material))?|session)\b"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9+/=_\-.]{24,}[\"']?"
        ),
    ),
)
_RESIDUE_COMPONENT = re.compile(
    r"(?i)(?:^|[/\\])(?:__pycache__|\.cache|\.hypothesis|\.pytest_cache|"
    r"\.ruff_cache|\.mypy_cache|\.tox|\.nox|\.idea|\.vscode|build|dist|tmp|temp|"
    r"\.staging[^/\\]*|\.codex-qa(?:[-_.][^/\\]+)?|staging|backup|backups|obsolete|old_generation)"
    r"(?:$|[/\\])"
)
_LIVE_RESIDUE_DIRECTORY = re.compile(
    r"(?i)(?:__pycache__|\.cache|\.pytest_cache|\.ruff_cache|\.mypy_cache|\.hypothesis|"
    r"\.tox|\.nox|\.idea|\.vscode|\.codex-qa(?:[-_.][^/\\]+)?|[^/\\]+\.egg-info|build|dist|tmp|temp|"
    r"\.staging[^/\\]*|staging|backup|backups|"
    r"obsolete|old_generation)"
)
_LIVE_RESIDUE_FILE = re.compile(
    r"(?i)(?:\.coverage(?:\..+)?|coverage\.xml|\.DS_Store|[^/\\]+\.(?:pyc|pyo|swp|swo|tmp))$"
)
_RESIDUE_SUFFIX = re.compile(r"(?i)(?:\.bak|\.backup|\.old|\.orig|\.pyc|\.pyo|\.swp|\.swo|\.tmp|~)$")
_PLACEHOLDER_WORDS = ("T" + "BD", "TO" + "DO", "FIX" + "ME")
_PLACEHOLDER = re.compile(
    r"\b(?:" + "|".join(_PLACEHOLDER_WORDS) + r")\b", re.IGNORECASE
)
_EXPLICIT_PLACEHOLDER = re.compile(r"\bPLACE" + r"HOLDER\b", re.IGNORECASE)
_ACTIVE_SOURCE_SUFFIXES = frozenset(
    {
        ".bat", ".c", ".cc", ".cmd", ".cpp", ".cs", ".go", ".h", ".hpp",
        ".java", ".js", ".jsx", ".ps1", ".py", ".pyi", ".rb", ".rs", ".sh",
        ".ts", ".tsx", ".zsh",
    }
)
_PUBLIC_DOC_PREFIXES = (
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/operator/",
)
_SENSITIVE_SUFFIXES = {".jks", ".key", ".keystore", ".p12", ".pem", ".pfx", ".ppk"}
_SECRET_NAME = re.compile(
    r"(?i)(?:^|[._-])(?:id_(?:dsa|ecdsa|ed25519|rsa)|api[-_]?(?:key|token)|"
    r"auth[-_]?(?:key|token)|access[-_]?token|client[-_]?(?:key|secret|token)|"
    r"private[-_]?key|secret|credentials?|password|passwd|token)(?:[._-]|$)"
)
_RUNTIME_COMPACT = {
    "hdt" + "export", "hdt" + "replay", "hearthrangerlog", "hearthrangerlogs",
    "hearthstonelog", "hearthstonelogs", "hs" + "replay", "power" + "log",
    "privateruntime", "runtimeevidence", "runtimeexport", "runtimeexports",
}
_GITHUB_CHECK_IDS = frozenset(
    check_id
    for check_id, owner in ATOMIC_CHECK_OWNERS.items()
    if owner == "github_repository_polish"
)
_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024
_MAX_ARCHIVE_TOTAL_BYTES = 128 * 1024 * 1024
_MAX_ARCHIVE_COMPRESSION_RATIO = 200
_MAX_PUBLISHABLE_FILE_BYTES = 128 * 1024 * 1024
_FINAL_EVIDENCE_MAX_AGE_SECONDS = 300
_SEMANTIC_REPORT_CLAIM_OCCURRENCES = 426

# Every exception is deliberately reviewable and expires at a product version.
# No source-code exceptions are currently required.
SOURCE_TODO_ALLOWLIST: tuple[Mapping[str, Any], ...] = ()

# These are permanent shipped contract references, not deferred work. Every
# exception binds the canonical source path, the canonical one-based line
# number, and the exact stripped-line digest. Archive members normalize back
# to this same source path without changing line numbering.
_EXACT_PLACEHOLDER_REFERENCE_SHA256: Mapping[str, Mapping[int, str]] = {
    ".agents/skills/hsconfig/SKILL.md": {
        75: "e919cd4c4fcaff88b0c1e1226a5701897e8611aeddbc52f26d1ba09fa34f55c0"
    },
    ".agents/skills/hsconfig/references/workflow.md": {
        117: "b857b8d8bdb8e2a79d1974bf6d52889edd9f00785c9e17676cb3d4084bb1a1a0"
    },
    # Completed Task-5 security report: five historical diagnostic-contract statements.
    ".superpowers/sdd/2026-07-26-hsconfig-post-audit-authority-hardening/task-5-report.md":
        {
            7:
                "7495ad25bdcaa4580d09b2f7171a32adb5b573cd95934820198549f6f9e26ad7",
            19:
                "49ae9a4c5e28a3d8fb833ac4dbf7863ec616b9d2065c001dc37b35d28a3608b1",
            108:
                "0243f85d9d6ec32caf9e5e93698a32a3534244ac80a5afae3218b6aa8a58a859",
            189:
                "194f02a9232ed3a4807f6d67750c5da535164526bea4d868a2f29d8dea9f29dd",
            208:
                "2009530620235cfe8b22df63a0a8274d66622fcf13c4852277d41063137b0a0c",
        },
    # Approved design: two explicit apply-ineligible diagnostic-input statements.
    "docs/superpowers/specs/2026-07-26-hsconfig-post-audit-authority-hardening-design.md":
        {
            34: "fe1552c59b642d924c8173dd6744b064bfaf25df525ca41c3638bcfd15ad1ace",
            172:
                "42ee3ed08885fb611c48c08e2c79a729ba7ede87449890d22b248998d7256c26",
            227:
                "b09e213b1b3c5de6a10c926a918910c16492926bc537286f1149ab79cf95a0b0",
    },
    "docs/operator/README.md": {
        623: "d0997da82e0ae641345085fcd2f3a0588c763e75f1c909f1a3826100f82da77b"
    },
    "src/hsconfig/cli_parser.py": {
        61: "6eea5855f7b68a28d9837b43338ef1c9c64370e9f3dae6d583509dfb8dcdcbac",
        79: "d11fe3f4881b01ce66c0f8ef09778e84f182aa2d571c42f9cd4b8fae4bf9eff7",
        112: "ab157ec4b7902309bb5029142aca743511e43587fdf753f52668750b788101cc",
        122: "cace9a43ddb95629998271a922872430b8e5230b0e25c2b335d910c63b08e4dd",
        136: "c601aab16f8d343ec912c1b44d6bbba7832bc43b89a87e92536f3355c2a10e0c",
        149: "ba0492c2907f7e3596bb82298d6eab7bd238c8197c84be310c900d5a1eaf2520",
        167: "eb0b21eea338c4ac38770df1932764f86eb4bc334bf51f2345d7ddca3662d098",
        188: "87078ccbe89f5d5a0aa0a0f7601ce6e71b6b4015b316ad220164abb0151cfd89",
        202: "bc2e3a70c28a3eabbc1bd0747bf8fb7582a68cb66b0e3dc729c3c07b3a7ec78a",
    },
    # Shipped protocol value and the diagnostic preview producer that owns it.
    "src/hsconfig/deck_input_verification.py": {
        33: "c6b238e40c24b6c239e0c07fdb6857cc0cf1e11e3682d50dff5a7be65866af05"
    },
    "src/hsconfig/input_loading.py": {
            54:
            "e516377413d0908ed7d5e0cedea28b5b864dedf3257df578f923d5c6a8e7aa61",
            388:
            "9d7d05b9b495a5faadcdc475bb0a30a7ffda56c392e6c4959f9d14270b66b49d",
            390:
            "2833fa4aeaf243cd7e22b3e1cd39fa3548eaba6da868b82d7b4b64f0c9a0509b",
    },
    "tests/test_configure_workflow.py": {
        114: "b9666c82127a7fa00fc8c7c9806f7b4e258fa1917994dd58ab4b7fcee842a4cd"
    },
    "tests/test_deck_identity.py": {
        165: "e293c155549577185ea2407c53e0b97ae74506b9abced220ae9bae51a2ec3857"
    },
    "tests/test_e2e_preview.py": {
        36: "b9666c82127a7fa00fc8c7c9806f7b4e258fa1917994dd58ab4b7fcee842a4cd"
    },
    "tests/test_skill_files.py": {
        512: "792b647fcd2e76736e07f8165775795cd69324ba4d60abf63be76fc88a80ed95",
        886: "b9666c82127a7fa00fc8c7c9806f7b4e258fa1917994dd58ab4b7fcee842a4cd",
        901: "9d6d9fee8049da1c81a765e9e25ca22717639f52965ed88971f6c6f86f3adf22",
    },
}


class ReleaseGateError(ValueError):
    """Raised when the release gate cannot safely inspect its inputs."""


_CREDENTIAL_KEY_ASSIGNMENT = re.compile(
    r"(?i)(?<![a-z0-9_.\-\"'])(?P<key_quote>[\"']?)"
    r"(?P<name>[a-z][a-z0-9_.-]{0,127})(?P=key_quote)\s*[:=]\s*"
)
_CREDENTIAL_NAME_SUFFIXES = (
    "password",
    "passwd",
    "credential",
    "credentials",
    "clientsecret",
    "secret",
    "accesstoken",
    "token",
    "apikey",
    "accesskey",
    "privatekey",
    "authkey",
    "authmaterial",
    "session",
)
_MAX_STRUCTURED_DEPTH = 128
_MAX_YAML_SCALAR_CHARACTERS = 4_096
_MAX_YAML_ANCHORS = 1_024
_MAX_YAML_DOCUMENT_CHARACTERS = 16 * 1024 * 1024
_MAX_YAML_DOCUMENTS = 32
_MAX_YAML_NODES = 10_000
_MAX_YAML_EVENTS = 20_000
_MAX_YAML_ALIASES = 1_024


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for character in value:
        counts[character] = counts.get(character, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _is_sensitive_credential_name(value: str) -> bool:
    component = value.casefold().rsplit(".", 1)[-1]
    compact = re.sub(r"[^a-z0-9]", "", component)
    return any(compact.endswith(suffix) for suffix in _CREDENTIAL_NAME_SUFFIXES)


def _credential_assignment_values(value: str) -> tuple[str, ...]:
    candidates: list[str] = []
    for match in _CREDENTIAL_KEY_ASSIGNMENT.finditer(value):
        if not _is_sensitive_credential_name(match.group("name")):
            continue
        start = match.end()
        if start >= len(value):
            continue
        quote = value[start] if value[start] in {"\"", "'"} else None
        if quote is None:
            token = re.match(r"\S+", value[start:])
            if token is not None:
                candidate = token.group(0)
                code_expression = (
                    "\"" in candidate
                    or "'" in candidate
                    or re.fullmatch(
                        r"[A-Za-z_][A-Za-z0-9_.]*\([^\s]*\)", candidate
                    )
                    is not None
                )
                if not code_expression:
                    candidates.append(candidate)
            continue
        escaped = False
        characters: list[str] = []
        for character in value[start + 1:]:
            if escaped:
                characters.append(character)
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                break
            else:
                characters.append(character)
        candidates.append("".join(characters))
    return tuple(candidates)


def _python_assignment_target_names(target: ast.expr) -> tuple[str, ...]:
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, ast.Attribute):
        parts: list[str] = [target.attr]
        current = target.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return (".".join(reversed(parts)),)
    if isinstance(target, (ast.Tuple, ast.List)):
        return tuple(
            name
            for child in target.elts
            for name in _python_assignment_target_names(child)
        )
    if isinstance(target, ast.Subscript):
        index = target.slice
        if isinstance(index, ast.Constant) and isinstance(index.value, str):
            return (index.value,)
    return ()


def _static_python_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return node.value
        if isinstance(node.value, bytes):
            return node.value.decode("latin-1")
        return None
    if isinstance(node, ast.JoinedStr) and all(
        isinstance(part, ast.Constant) and isinstance(part.value, str)
        for part in node.values
    ):
        return "".join(str(part.value) for part in node.values)
    return None


def _python_credential_assignment_values(value: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(value)
    except (SyntaxError, ValueError, MemoryError):
        return ()
    candidates: list[str] = []
    for node in ast.walk(tree):
        assignments: tuple[tuple[str, ...], ast.AST] | None = None
        if isinstance(node, ast.Assign):
            assignments = (
                tuple(
                    name
                    for target in node.targets
                    for name in _python_assignment_target_names(target)
                ),
                node.value,
            )
        elif isinstance(node, ast.AnnAssign):
            assignments = (_python_assignment_target_names(node.target), node.value)
        elif isinstance(node, ast.NamedExpr):
            assignments = (_python_assignment_target_names(node.target), node.value)
        if assignments is not None:
            names, assigned = assignments
            literal = _static_python_string(assigned)
            if literal is not None and any(
                _is_sensitive_credential_name(name) for name in names
            ):
                candidates.append(literal)
        if isinstance(node, ast.Dict):
            for key, assigned in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and _is_sensitive_credential_name(key.value)
                ):
                    literal = _static_python_string(assigned)
                    if literal is not None:
                        candidates.append(literal)
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg and _is_sensitive_credential_name(keyword.arg):
                    literal = _static_python_string(keyword.value)
                    if literal is not None:
                        candidates.append(literal)
    return tuple(candidates)


def _json_credential_assignment_values(value: str) -> tuple[str, ...]:
    class DecodedObjectPairs(list[tuple[str, Any]]):
        pass

    try:
        document = json.loads(value, object_pairs_hook=DecodedObjectPairs)
    except (json.JSONDecodeError, UnicodeError, RecursionError, MemoryError) as exc:
        raise ReleaseGateError("invalid structured JSON content") from exc
    candidates: list[str] = []
    pending: list[tuple[Any, int]] = [(document, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > _MAX_STRUCTURED_DEPTH:
            raise ReleaseGateError("structured JSON content exceeds depth limit")
        if isinstance(node, DecodedObjectPairs):
            for key, child in node:
                if (
                    isinstance(key, str)
                    and _is_sensitive_credential_name(key)
                    and isinstance(child, str)
                ):
                    candidates.append(child)
                pending.append((child, depth + 1))
        elif isinstance(node, list):
            for child in node:
                pending.append((child, depth + 1))
    return tuple(candidates)


class _BoundedYamlSafeLoader(yaml.SafeLoader):
    def __init__(self, stream: str) -> None:
        self._yaml_documents = 0
        self._yaml_nodes = 0
        self._yaml_events = 0
        self._yaml_aliases = 0
        self._yaml_anchors = 0
        self._yaml_depth = 0
        super().__init__(stream)

    def get_event(self) -> yaml.events.Event | None:
        event = super().get_event()
        if event is not None:
            self._yaml_events += 1
            if self._yaml_events > _MAX_YAML_EVENTS:
                raise ReleaseGateError("structured YAML event count exceeds limit")
        return event

    def compose_document(self) -> yaml.nodes.Node:
        self._yaml_documents += 1
        if self._yaml_documents > _MAX_YAML_DOCUMENTS:
            raise ReleaseGateError("structured YAML document count exceeds limit")
        return super().compose_document()

    def compose_node(
        self,
        parent: yaml.nodes.Node | None,
        index: int | None,
    ) -> yaml.nodes.Node:
        event = self.peek_event()
        if isinstance(event, yaml.events.AliasEvent):
            self._yaml_aliases += 1
            if self._yaml_aliases > _MAX_YAML_ALIASES:
                raise ReleaseGateError("structured YAML alias count exceeds limit")
        else:
            self._yaml_nodes += 1
            if self._yaml_nodes > _MAX_YAML_NODES:
                raise ReleaseGateError("structured YAML node count exceeds limit")
            anchor = getattr(event, "anchor", None)
            if anchor is not None:
                if len(anchor) > 128:
                    raise ReleaseGateError("structured YAML anchor name exceeds limit")
                self._yaml_anchors += 1
                if self._yaml_anchors > _MAX_YAML_ANCHORS:
                    raise ReleaseGateError("structured YAML anchor count exceeds limit")
            tag = getattr(event, "tag", None)
            if tag is not None and len(tag) > 256:
                raise ReleaseGateError("structured YAML tag exceeds limit")
        self._yaml_depth += 1
        if self._yaml_depth > _MAX_STRUCTURED_DEPTH:
            raise ReleaseGateError("structured YAML content exceeds depth limit")
        try:
            return super().compose_node(parent, index)
        finally:
            self._yaml_depth -= 1

    def compose_scalar_node(self, anchor: str | None) -> yaml.nodes.ScalarNode:
        event = self.peek_event()
        if not isinstance(event, yaml.events.ScalarEvent):
            raise ReleaseGateError("structured YAML scalar event is invalid")
        if len(event.value) > _MAX_YAML_SCALAR_CHARACTERS:
            raise ReleaseGateError("structured YAML scalar exceeds decoded size limit")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in event.value):
            raise ReleaseGateError("structured YAML scalar has an invalid codepoint")
        return super().compose_scalar_node(anchor)


def _yaml_scalar_key_identity(
    loader: _BoundedYamlSafeLoader,
    node: yaml.nodes.ScalarNode,
) -> tuple[str, str]:
    tag = node.tag
    try:
        if tag == "tag:yaml.org,2002:str":
            canonical = loader.construct_yaml_str(node)
        elif tag == "tag:yaml.org,2002:null":
            loader.construct_yaml_null(node)
            canonical = "null"
        elif tag == "tag:yaml.org,2002:bool":
            canonical = "true" if loader.construct_yaml_bool(node) else "false"
        elif tag == "tag:yaml.org,2002:int":
            canonical = str(loader.construct_yaml_int(node))
        elif tag == "tag:yaml.org,2002:float":
            number = loader.construct_yaml_float(node)
            if math.isnan(number):
                canonical = "nan"
            elif math.isinf(number):
                canonical = "-inf" if number < 0 else "+inf"
            elif number == 0.0:
                canonical = "0x0.0p+0"
            else:
                canonical = number.hex()
        else:
            raise ReleaseGateError("structured YAML mapping key tag is unsupported")
    except ReleaseGateError:
        raise
    except (KeyError, ValueError, IndexError) as exc:
        raise ReleaseGateError("structured YAML mapping key scalar is invalid") from exc
    return tag, canonical


def _yaml_credential_assignment_values(value: str) -> tuple[str, ...]:
    if len(value) > _MAX_YAML_DOCUMENT_CHARACTERS:
        raise ReleaseGateError("structured YAML input exceeds size limit")
    candidates: list[str] = []
    visits = 0
    loader = _BoundedYamlSafeLoader(value)
    try:
        while loader.check_node():
            document = loader.get_node()
            if document is None:
                continue
            active: set[int] = set()
            pending: list[tuple[yaml.nodes.Node, int, bool]] = [(document, 0, False)]
            while pending:
                node, depth, leaving = pending.pop()
                identity = id(node)
                if leaving:
                    active.remove(identity)
                    continue
                if depth > _MAX_STRUCTURED_DEPTH:
                    raise ReleaseGateError("structured YAML content exceeds depth limit")
                if identity in active:
                    raise ReleaseGateError("structured YAML recursive alias is invalid")
                visits += 1
                if visits > _MAX_YAML_NODES:
                    raise ReleaseGateError("structured YAML traversal exceeds node limit")
                active.add(identity)
                pending.append((node, depth, True))
                if isinstance(node, yaml.nodes.ScalarNode):
                    continue
                if isinstance(node, yaml.nodes.SequenceNode):
                    for child in reversed(node.value):
                        pending.append((child, depth + 1, False))
                    continue
                if not isinstance(node, yaml.nodes.MappingNode):
                    raise ReleaseGateError("structured YAML node kind is unsupported")
                seen_keys: set[tuple[str, str]] = set()
                for key_node, child in reversed(node.value):
                    if not isinstance(key_node, yaml.nodes.ScalarNode):
                        raise ReleaseGateError("structured YAML mapping key must be scalar")
                    key = key_node.value
                    if len(key) > 128:
                        raise ReleaseGateError(
                            "structured YAML key exceeds decoded size limit"
                        )
                    identity = _yaml_scalar_key_identity(loader, key_node)
                    if identity in seen_keys:
                        raise ReleaseGateError("structured YAML mapping key is duplicated")
                    seen_keys.add(identity)
                    if _is_sensitive_credential_name(key):
                        if not isinstance(child, yaml.nodes.ScalarNode):
                            raise ReleaseGateError(
                                "structured YAML sensitive value must be scalar"
                            )
                        candidates.append(child.value)
                    pending.append((child, depth + 1, False))
    except ReleaseGateError:
        raise
    except (yaml.YAMLError, UnicodeError, RecursionError, MemoryError) as exc:
        raise ReleaseGateError("invalid structured YAML content") from exc
    finally:
        loader.dispose()
    return tuple(candidates)


def _contains_secret(
    value: str,
    *,
    python_source: bool = False,
    structured_suffix: str = "",
) -> bool:
    if any(pattern.search(value) for _reason, pattern in _SECRET_PATTERNS):
        return True
    candidates = list(_credential_assignment_values(value))
    if python_source:
        candidates.extend(_python_credential_assignment_values(value))
    if structured_suffix == ".json":
        candidates.extend(_json_credential_assignment_values(value))
    elif structured_suffix in {".yaml", ".yml"}:
        candidates.extend(_yaml_credential_assignment_values(value))
    for candidate in candidates:
        if len(candidate) >= 40 and _shannon_entropy(candidate) >= 3.5:
            return True
    return False


def _redact_text(value: str) -> str:
    if _contains_secret(value):
        return "[redacted-secret]"
    if _ABSOLUTE_USER_PATH.search(value):
        return "[redacted-local-path]"
    return value


def _portable_value(value: Any) -> Any:
    if isinstance(value, str):
        redacted = _redact_text(value)
        if redacted != value:
            return redacted
        if len(value) > 2_000:
            return {
                "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                "redacted": "oversized-output",
            }
        return value
    if isinstance(value, Mapping):
        portable: dict[str, Any] = {}
        for key, item in value.items():
            original = str(key)
            sensitive_key = _contains_secret(original) or _is_sensitive_credential_name(
                original
            )
            redacted = "[redacted-sensitive-key]" if sensitive_key else _redact_text(original)
            if redacted != original:
                digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:12]
                safe_key = f"{redacted}:{digest}"
            else:
                safe_key = original
            portable[safe_key] = (
                "[redacted-secret]" if sensitive_key else _portable_value(item)
            )
        return portable
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_portable_value(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class _GateSnapshot:
    commit_oid: str
    tree_oid: str
    repository_fingerprint: str
    outputs_inventory_sha256: str
    repository_identity: str


@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    name: str
    passed: bool
    command: tuple[str, ...]
    details: Mapping[str, Any]

    def to_document(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "command": [_portable_value(value) for value in self.command],
            "details": _portable_value(dict(self.details)),
        }


@dataclass(frozen=True, slots=True)
class ReleaseGateResult:
    passed: bool
    final_release_ready: bool
    version: str
    commit_oid: str
    checks: tuple[ReleaseCheck, ...]

    def to_document(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "final_release_ready": self.final_release_ready,
            "version": self.version,
            "commit_oid": self.commit_oid,
            "checks": [check.to_document() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_document(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class _CommandSpec:
    name: str
    command: tuple[str, ...]
    timeout: int


def _base_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        upper = key.upper()
        if upper.startswith("GIT_"):
            environment.pop(key, None)
    return environment


def _git_completed(
    repository: Path, *arguments: str, text: bool = True, check: bool = True
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ("git", *arguments),
            cwd=repository,
            check=check,
            capture_output=True,
            text=text,
            shell=False,
            timeout=60,
            env=_base_environment(),
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReleaseGateError(f"repository inspection failed: {exc}") from exc


def _git(repository: Path, *arguments: str, text: bool = True) -> str | bytes:
    return _git_completed(repository, *arguments, text=text).stdout


def _resolve_git_path(repository: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repository / path
    return path.resolve()


def _validate_git_binding(repository: Path) -> None:
    root = repository.resolve()
    top = Path(str(_git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    git_dir = _resolve_git_path(
        root, str(_git(root, "rev-parse", "--absolute-git-dir")).strip()
    )
    common_dir = _resolve_git_path(
        root, str(_git(root, "rev-parse", "--git-common-dir")).strip()
    )
    inside = str(_git(root, "rev-parse", "--is-inside-work-tree")).strip()
    expected_git = (root / ".git").resolve()
    if top != root or inside != "true" or git_dir != expected_git or common_dir != expected_git:
        raise ReleaseGateError("Git repository/worktree binding does not match requested root")
    metadata = (root / ".git").lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
        raise ReleaseGateError("Git directory is not a private repository directory")
    worktree = _git_completed(root, "config", "--local", "--get", "core.worktree", check=False)
    if worktree.returncode not in {0, 1}:
        raise ReleaseGateError("Git core.worktree inspection failed")
    if worktree.returncode == 0:
        configured = _resolve_git_path(root / ".git", str(worktree.stdout).strip())
        if configured != root:
            raise ReleaseGateError("Git core.worktree does not match requested root")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ReleaseGateError(f"duplicate JSON key: {key}")
        document[key] = value
    return document


def _load_json_bytes(data: bytes, *, source: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except ReleaseGateError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ReleaseGateError(f"invalid JSON evidence: {source}") from exc


def _is_reparse(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _walk_regular_tree(
    root: Path, *, context: str
) -> tuple[tuple[str, Path, os.stat_result], ...]:
    root_metadata = root.lstat()
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or _is_reparse(root_metadata)
    ):
        raise ReleaseGateError(f"{context} root is link/reparse/non-directory")
    rows: list[tuple[str, Path, os.stat_result]] = []

    def visit(directory: Path, prefix: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise ReleaseGateError(f"{context} directory is unreadable") from exc
        seen: dict[str, str] = {}
        for entry in entries:
            key = entry.name.casefold()
            previous = seen.get(key)
            if previous is not None and previous != entry.name:
                raise ReleaseGateError(f"{context} casefold collision: {previous}:{entry.name}")
            seen[key] = entry.name
            relative = prefix / entry.name
            path = Path(entry.path)
            metadata = path.lstat()
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode) and not _is_reparse(metadata):
                visit(path, relative)
            elif (
                stat.S_ISREG(metadata.st_mode)
                and not _is_reparse(metadata)
                and getattr(metadata, "st_nlink", 1) in {0, 1}
            ):
                rows.append((relative.as_posix(), path, metadata))
            else:
                raise ReleaseGateError(f"{context} contains link/hardlink/reparse/non-regular entry: {relative.as_posix()}")

    visit(root, PurePosixPath())
    return tuple(rows)


def _secure_regular_file(root: Path, relative: PurePosixPath) -> Path:
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReleaseGateError(f"non-canonical evidence path: {relative.as_posix()}")
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise ReleaseGateError("evidence root cannot be inspected") from exc
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode) or _is_reparse(root_stat):
        raise ReleaseGateError("evidence root must be a regular directory")
    candidate = root
    for index, part in enumerate(relative.parts):
        candidate = candidate / part
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise ReleaseGateError(f"evidence path is unavailable: {relative.as_posix()}") from exc
        final = index == len(relative.parts) - 1
        expected = stat.S_ISREG(metadata.st_mode) if final else stat.S_ISDIR(metadata.st_mode)
        if not expected or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ReleaseGateError(f"evidence path contains link/reparse/non-regular data: {relative.as_posix()}")
        if final and getattr(metadata, "st_nlink", 1) not in {0, 1}:
            raise ReleaseGateError(f"evidence path must not be a hardlink: {relative.as_posix()}")
    return candidate


def _stat_identity(metadata: os.stat_result) -> tuple[Any, ...]:
    device = getattr(metadata, "st_dev", None)
    inode = getattr(metadata, "st_ino", None)
    if device is None or inode in {None, 0}:
        raise ReleaseGateError("filesystem identity is unavailable")
    return (
        stat.S_IFMT(metadata.st_mode),
        device,
        inode,
        getattr(metadata, "st_file_attributes", None),
        getattr(metadata, "st_reparse_tag", None),
    )


def _stat_content_signature(metadata: os.stat_result) -> tuple[Any, ...]:
    return (
        *_stat_identity(metadata),
        metadata.st_size,
        getattr(metadata, "st_mtime_ns", None),
        getattr(metadata, "st_ctime_ns", None),
        getattr(metadata, "st_nlink", 1),
    )


def _path_snapshots(
    root: Path,
    relative: PurePosixPath,
    *,
    context: str,
) -> tuple[tuple[Path, tuple[Any, ...]], ...]:
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReleaseGateError(f"{context} has a non-canonical path: {relative.as_posix()}")
    snapshots: list[tuple[Path, tuple[Any, ...]]] = []
    candidate = root
    components = (None, *relative.parts)
    for index, part in enumerate(components):
        if part is not None:
            candidate = candidate / part
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise ReleaseGateError(f"{context} path cannot be inspected: {relative.as_posix()}") from exc
        final = index == len(components) - 1
        expected = stat.S_ISREG(metadata.st_mode) if final else stat.S_ISDIR(metadata.st_mode)
        if not expected or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ReleaseGateError(
                f"{context} path contains link/reparse/non-regular data: {relative.as_posix()}"
            )
        if final and getattr(metadata, "st_nlink", 1) not in {0, 1}:
            raise ReleaseGateError(f"{context} path must not be a hardlink: {relative.as_posix()}")
        snapshots.append((candidate, _stat_identity(metadata)))
    return tuple(snapshots)


def _assert_path_snapshots(
    snapshots: tuple[tuple[Path, tuple[Any, ...]], ...],
    *,
    context: str,
) -> None:
    for path, expected in snapshots:
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise ReleaseGateError(f"{context} path changed during inspection") from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or _is_reparse(metadata)
            or _stat_identity(metadata) != expected
        ):
            raise ReleaseGateError(f"{context} path identity changed during inspection")


@contextmanager
def _secure_open_regular(
    root: Path,
    relative: PurePosixPath,
    *,
    context: str,
    max_bytes: int = _MAX_PUBLISHABLE_FILE_BYTES,
    expected_identity: tuple[Any, ...] | None = None,
) -> Any:
    snapshots = _path_snapshots(root, relative, context=context)
    candidate = snapshots[-1][0]
    validated_identity = snapshots[-1][1]
    if expected_identity is not None and validated_identity != expected_identity:
        raise ReleaseGateError(f"{context} path identity changed before inspection")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise ReleaseGateError(f"{context} path cannot be opened safely: {relative.as_posix()}") from exc
    stream: Any | None = None
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_reparse(opened)
            or getattr(opened, "st_nlink", 1) not in {0, 1}
            or _stat_identity(opened) != validated_identity
        ):
            raise ReleaseGateError(f"{context} opened file identity does not match validated path")
        if opened.st_size > max_bytes:
            raise ReleaseGateError(f"{context} file exceeds bounded size limit")
        before = _stat_content_signature(opened)
        _assert_path_snapshots(snapshots, context=context)
        stream = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = -1
        yield stream
        after = os.fstat(stream.fileno())
        if _stat_content_signature(after) != before:
            raise ReleaseGateError(f"{context} file changed during inspection")
        _assert_path_snapshots(snapshots, context=context)
    finally:
        if stream is not None:
            stream.close()
        elif descriptor >= 0:
            os.close(descriptor)


def _secure_read_bytes(
    root: Path,
    relative: PurePosixPath,
    *,
    context: str,
    max_bytes: int = _MAX_PUBLISHABLE_FILE_BYTES,
    expected_identity: tuple[Any, ...] | None = None,
) -> bytes:
    with _secure_open_regular(
        root,
        relative,
        context=context,
        max_bytes=max_bytes,
        expected_identity=expected_identity,
    ) as stream:
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = stream.read(min(1024 * 1024, max_bytes - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise ReleaseGateError(f"{context} file exceeds bounded size limit")
            chunks.append(chunk)
        return b"".join(chunks)


def _load_json_file(root: Path, relative: PurePosixPath) -> Mapping[str, Any]:
    document = _load_json_bytes(
        _secure_read_bytes(root, relative, context="JSON evidence"),
        source=relative.as_posix(),
    )
    if not isinstance(document, Mapping):
        raise ReleaseGateError(f"JSON evidence must be an object: {relative.as_posix()}")
    return document


def _validate_repository(repository: Path, outputs_root: Path, tree_mode: TreeMode) -> tuple[Path, Path, str]:
    root = Path(repository).resolve()
    outputs = Path(outputs_root).resolve()
    if tree_mode not in {"working-pre-cutover", "candidate", "final"}:
        raise ReleaseGateError(f"unsupported tree mode: {tree_mode}")
    if not root.is_dir() or not (root / ".git").exists():
        raise ReleaseGateError(f"repository does not exist or is not a Git worktree: {root}")
    if not outputs.is_dir():
        raise ReleaseGateError(f"verified outputs root does not exist: {outputs}")
    if outputs != root / "outputs":
        raise ReleaseGateError("verified outputs root must be the canonical repository outputs directory")
    _validate_git_binding(root)
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if str(status).strip():
        raise ReleaseGateError("release gate refuses a dirty repository")
    commit_oid = str(_git(root, "rev-parse", "HEAD")).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit_oid):
        raise ReleaseGateError("repository HEAD is not a full commit OID")
    if tree_mode == "candidate":
        symbolic = _git_completed(root, "symbolic-ref", "-q", "HEAD", check=False)
        if symbolic.returncode == 0:
            raise ReleaseGateError("candidate mode requires a detached candidate tree")
        _outputs_inventory_sha256(root, outputs)
    return root, outputs, commit_oid


def _command_specs(root: Path, outputs: Path, tree_mode: TreeMode) -> tuple[_CommandSpec, ...]:
    python = sys.executable
    script = root / "scripts" / "check_release_gate.py"
    build_inputs = root / "src" / "hsconfig" / "resources" / "audited_build_inputs.json"
    score_mode = "pre_cutover" if tree_mode != "final" else "final"
    common_internal = (
        python,
        str(script),
        "--repo",
        str(root),
        "--outputs",
        str(outputs),
        "--tree-mode",
        tree_mode,
        "--json",
        "--internal-check",
    )
    return (
        _CommandSpec("ruff", (python, "-m", "ruff", "check", "--no-cache", "src", "tests", "scripts"), 600),
        _CommandSpec("full_tests_and_coverage", (python, str(root / "scripts" / "run_coverage_gate.py")), 18_000),
        _CommandSpec("contract_spine", (python, "-m", "hsconfig.cli", "contract-spine-sentinel", "--json"), 600),
        _CommandSpec("twelve_deck_acceptance", (python, "-m", "pytest", "tests/test_audited_deck_set_acceptance.py", "-q", "-p", "no:cacheprovider"), 1_800),
        _CommandSpec("contract_mutations", (python, str(root / "scripts" / "run_contract_mutations.py"), "--json"), 1_200),
        _CommandSpec(
            "dependency_audit",
            (
                python,
                "-m",
                "pip_audit",
                "-r",
                str(root / "constraints-ci.txt"),
                "--strict",
                "--progress-spinner",
                "off",
            ),
            1_200,
        ),
        _CommandSpec("distribution", (python, str(root / "scripts" / "verify_distribution.py"), "--json"), 1_200),
        _CommandSpec("twelve_deck_determinism", (python, str(root / "scripts" / "verify_twelve_decks.py"), "--build-inputs", str(build_inputs), "--json"), 1_800),
        _CommandSpec("publishable_path_scan", (*common_internal, "publishable_path_scan"), 1_800),
        _CommandSpec("output_inventory", (python, str(root / "scripts" / "reconcile_outputs.py"), "--outputs", str(outputs), "--check", "--json"), 600),
        _CommandSpec("package_immutability", (python, "-m", "pytest", "tests/test_package_immutability_after_apply.py", "-q", "-p", "no:cacheprovider"), 900),
        _CommandSpec("transaction_fault_matrix", (python, "-m", "pytest", "tests/test_runtime_install_fault_matrix.py", "tests/test_output_publication_fault_matrix.py", "-q", "-p", "no:cacheprovider"), 1_800),
        _CommandSpec("repository_hygiene", (*common_internal, "repository_hygiene"), 300),
        _CommandSpec("version_consistency", (python, "-m", "pytest", "tests/test_version_contract.py", "-q", "-p", "no:cacheprovider"), 300),
        _CommandSpec(
            "near100_scorecard",
            (
                python,
                str(root / "scripts" / "check_near100_scorecard.py"),
                "--repo",
                str(root),
                "--outputs",
                str(outputs),
                "--mode",
                score_mode,
                "--evidence-stdin",
                "--json",
            ),
            600,
        ),
    )


def _canonical_module_text(source: bytes) -> str:
    try:
        text = source.decode("utf-8")
    except UnicodeError as exc:
        raise ReleaseGateError("release gate module is not bound to the requested repository") from exc
    if "\r" not in text:
        return text
    without_crlf = text.replace("\r\n", "")
    if "\r" in without_crlf or "\n" in without_crlf:
        raise ReleaseGateError("release gate module is not bound to the requested repository")
    return text.replace("\r\n", "\n")


def _verify_module_binding(repository: Path) -> None:
    expected = repository / "src" / "hsconfig" / "release_gate.py"
    try:
        metadata = expected.lstat()
        repository_source = _secure_read_bytes(
            repository,
            PurePosixPath("src", "hsconfig", "release_gate.py"),
            context="repository module binding",
        )
        loaded_source = _secure_read_bytes(
            Path(__file__).parent,
            PurePosixPath(Path(__file__).name),
            context="loaded module binding",
        )
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or _is_reparse(metadata)
            or _canonical_module_text(repository_source)
            != _canonical_module_text(loaded_source)
        ):
            raise ReleaseGateError("release gate module is not bound to the requested repository")
    except OSError as exc:
        raise ReleaseGateError("release gate module binding cannot be verified") from exc


def _validate_pre_cutover_local_result(document: Mapping[str, Any]) -> None:
    expected_fields = {
        "schema_version",
        "version",
        "metrics",
        "open_p0_findings",
        "open_p1_findings",
        "overall_score",
        "passed",
    }
    if set(document) != expected_fields:
        raise ReleaseGateError("pre-cutover scorecard result schema mismatch")
    if (
        document.get("schema_version") != 1
        or document.get("version") != __version__
        or document.get("passed") is not False
    ):
        raise ReleaseGateError("pre-cutover scorecard identity/passed state mismatch")
    for finding in ("open_p0_findings", "open_p1_findings"):
        value = document.get(finding)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            raise ReleaseGateError("pre-cutover scorecard has open blocking findings")
    metrics = document.get("metrics")
    if not isinstance(metrics, list) or any(
        not isinstance(metric, Mapping) for metric in metrics
    ):
        raise ReleaseGateError("pre-cutover scorecard metrics schema mismatch")
    expected_metric_ids = (*HARD_METRIC_IDS, "overall_pre_run", "gameplay_quality")
    actual_metric_ids = tuple(metric.get("metric_id") for metric in metrics)
    if actual_metric_ids != expected_metric_ids:
        raise ReleaseGateError("pre-cutover scorecard metric set/order mismatch")
    for metric in metrics:
        metric_id = metric.get("metric_id")
        expected_status = (
            "pending_remote"
            if metric_id == "github_repository_polish"
            else "not_applicable"
            if metric_id == "gameplay_quality"
            else "pass"
        )
        if metric.get("status") != expected_status:
            raise ReleaseGateError(
                f"pre-cutover scorecard metric status mismatch: {metric_id}"
            )
    overall_score = document.get("overall_score")
    try:
        score = Decimal(overall_score) if isinstance(overall_score, str) else None
    except InvalidOperation as exc:
        raise ReleaseGateError("pre-cutover scorecard overall score is invalid") from exc
    if score is None or not score.is_finite() or score < Decimal("98"):
        raise ReleaseGateError("pre-cutover scorecard overall score is below minimum")


def _safe_detail(
    stdout: str,
    stderr: str,
    returncode: int,
    *,
    allow_pre_cutover_local: bool = False,
) -> dict[str, Any]:
    details: dict[str, Any] = {"returncode": returncode}
    stripped = stdout.strip()
    if stripped.startswith("[truncated sha256="):
        raise ReleaseGateError("subprocess stdout exceeded bounded capture")
    if stripped:
        try:
            parsed = _load_json_bytes(stripped.encode("utf-8"), source="subprocess stdout")
        except ReleaseGateError:
            if stripped.startswith(("{", "[")):
                raise
            details["stdout_sha256"] = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
        else:
            if allow_pre_cutover_local:
                if returncode != 0 or not isinstance(parsed, Mapping):
                    raise ReleaseGateError(
                        "pre-cutover scorecard must be a successful JSON subprocess"
                    )
                _validate_pre_cutover_local_result(parsed)
            elif isinstance(parsed, Mapping) and "passed" in parsed:
                reported = parsed["passed"]
                if not isinstance(reported, bool) or reported is not (returncode == 0):
                    raise ReleaseGateError(
                        "subprocess JSON passed value contradicts process return code"
                    )
            if isinstance(parsed, Mapping) and "returncode" in parsed:
                nested_returncode = parsed.get("returncode")
                if (
                    isinstance(nested_returncode, bool)
                    or not isinstance(nested_returncode, int)
                    or nested_returncode != returncode
                ):
                    raise ReleaseGateError(
                        "subprocess JSON returncode contradicts process return code"
                    )
            details["result"] = _portable_value(parsed)
    if stderr.strip():
        details["stderr_sha256"] = hashlib.sha256(stderr.encode("utf-8")).hexdigest()
    return details


def _controlled_environment(repository: Path) -> dict[str, str]:
    environment = _base_environment()
    for key in tuple(environment):
        upper = key.upper()
        if upper.startswith(("COVERAGE_", "HYPOTHESIS_", "PYTHON", "PYTEST_")) or upper in {
            "VIRTUAL_ENV",
            "CONDA_PREFIX",
        }:
            environment.pop(key, None)
        elif upper.startswith("PIP_"):
            environment.pop(key, None)
    environment.update(
        {
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(repository / "src"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTEST_PLUGINS": "pytest_cov.plugin,_hypothesis_pytestplugin",
        }
    )
    return environment


class _BoundedCapture:
    def __init__(self, limit: int = 64 * 1024) -> None:
        self._limit = limit
        self._tail = bytearray()
        self._digest = hashlib.sha256()
        self.total = 0

    def drain(self, stream: Any) -> None:
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    return
                self.total += len(chunk)
                self._digest.update(chunk)
                self._tail.extend(chunk)
                if len(self._tail) > self._limit:
                    del self._tail[: len(self._tail) - self._limit]
        except (OSError, ValueError):
            return

    def text(self) -> str:
        decoded = bytes(self._tail).decode("utf-8", errors="replace")
        if self.total > self._limit:
            return f"[truncated sha256={self._digest.hexdigest()}]\n{decoded}"
        return decoded


_GATED_LAUNCHER = (
    "import json,os,subprocess,sys; header=bytearray(); "
    "[(header.extend(chunk),None)[1] for chunk in iter(lambda:os.read(0,1),b'\\n')]; "
    "argv=json.loads(header); "
    "assert isinstance(argv,list) and argv and all(isinstance(x,str) for x in argv); "
    "raise SystemExit(subprocess.run(argv,stdin=sys.stdin.buffer).returncode)"
)


def _linux_direct_children() -> set[int]:
    if sys.platform != "linux":
        return set()
    children: set[int] = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text(encoding="ascii").split()
            if len(fields) > 4 and int(fields[3]) == os.getpid():
                children.add(int(entry.name))
        except (OSError, UnicodeError, ValueError):
            continue
    return children


class _ProcessTreeLease:
    def __init__(self, process: subprocess.Popen[bytes], baseline: set[int]) -> None:
        self.process = process
        self.baseline = baseline
        self.job_handle: int | None = None
        if os.name == "nt":
            self._assign_windows_job()

    def _assign_windows_job(self) -> None:
        import ctypes
        from ctypes import wintypes

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        job = kernel32.CreateJobObjectW(None, None)
        information = ExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = 0x00002000
        if (
            not job
            or not kernel32.SetInformationJobObject(
                job, 9, ctypes.byref(information), ctypes.sizeof(information)
            )
            or not kernel32.AssignProcessToJobObject(
                job, wintypes.HANDLE(int(self.process._handle))  # noqa: SLF001
            )
        ):
            if job:
                kernel32.CloseHandle(job)
            raise OSError("subprocess job assignment failed")
        self.job_handle = int(job)

    def terminate_remaining(self) -> None:
        if os.name == "nt":
            if self.job_handle is not None:
                import ctypes
                from ctypes import wintypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
                kernel32.CloseHandle.restype = wintypes.BOOL
                kernel32.CloseHandle(wintypes.HANDLE(self.job_handle))
                self.job_handle = None
            elif self.process.poll() is None:
                self.process.kill()
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            if sys.platform == "linux":
                for _ in range(4):
                    escaped = _linux_direct_children() - self.baseline
                    if not escaped:
                        break
                    for pid in escaped:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    for pid in escaped:
                        try:
                            os.waitpid(pid, 0)
                        except ChildProcessError:
                            pass
        if self.process.poll() is None:
            self.process.kill()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=30)


def _enable_posix_subreaper() -> None:
    if sys.platform != "linux":
        return
    import ctypes

    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise OSError("subprocess subreaper setup failed")


def _execute_bounded(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    stdin_data: bytes | None = None,
) -> subprocess.CompletedProcess[str]:
    # Every subprocess receives a unique, disposable tool-state root outside
    # the checkout. This prevents an earlier pytest/Hypothesis/coverage command
    # from poisoning a later repository-hygiene check and cleans the state on
    # both success and exception paths.
    with TemporaryDirectory(prefix="hsconfig-release-gate-tool-") as temporary:
        isolation_root = Path(temporary).resolve()
        checkout = cwd.resolve()
        if isolation_root == checkout or checkout in isolation_root.parents:
            raise ReleaseGateError("subprocess tool-state root is inside the checkout")
        tool_directories = {
            name: isolation_root / name
            for name in (
                "cache",
                "hypothesis",
                "pip-cache",
                "pycache",
                "pytest-cache",
                "pytest-temp",
            )
        }
        for directory in tool_directories.values():
            directory.mkdir(mode=0o700)
        isolated_environment = dict(env)
        isolated_environment.update(
            {
                "COVERAGE_FILE": str(isolation_root / ".coverage"),
                "HYPOTHESIS_STORAGE_DIRECTORY": str(tool_directories["hypothesis"]),
                "PIP_CACHE_DIR": str(tool_directories["pip-cache"]),
                "PYTEST_DEBUG_TEMPROOT": str(tool_directories["pytest-temp"]),
                "PYTHONPYCACHEPREFIX": str(tool_directories["pycache"]),
                "TMP": str(isolation_root),
                "TEMP": str(isolation_root),
                "TMPDIR": str(isolation_root),
                "TOX_ENV_DIR": str(tool_directories["pytest-cache"]),
                "XDG_CACHE_HOME": str(tool_directories["cache"]),
            }
        )
        coverage_report = (
            cwd / "coverage.json"
            if any(Path(argument).name == "run_coverage_gate.py" for argument in command)
            else None
        )
        if coverage_report is not None and (
            coverage_report.exists() or coverage_report.is_symlink()
        ):
            raise ReleaseGateError("coverage report residue exists before execution")
        try:
            return _execute_bounded_process(
                command,
                cwd=cwd,
                env=isolated_environment,
                timeout=timeout,
                stdin_data=stdin_data,
            )
        finally:
            if coverage_report is not None and (
                coverage_report.exists() or coverage_report.is_symlink()
            ):
                metadata = coverage_report.lstat()
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_ISLNK(metadata.st_mode)
                    or _is_reparse(metadata)
                    or getattr(metadata, "st_nlink", 1) not in {0, 1}
                ):
                    raise ReleaseGateError("coverage report cleanup found unsafe residue")
                coverage_report.unlink()


def _execute_bounded_process(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    stdin_data: bytes | None = None,
) -> subprocess.CompletedProcess[str]:
    platform_options: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    stdout_capture: _BoundedCapture | None = None
    stderr_capture: _BoundedCapture | None = None
    capture_threads: tuple[threading.Thread, ...] = ()
    started_capture_threads: list[threading.Thread] = []
    writer_errors: list[BaseException] = []
    writer: threading.Thread | None = None
    writer_started = False
    process: subprocess.Popen[bytes] | None = None
    lease: _ProcessTreeLease | None = None
    returncode = 2
    if os.name != "nt":
        _enable_posix_subreaper()
    baseline = _linux_direct_children()
    try:
        process = subprocess.Popen(
            (sys.executable, "-c", _GATED_LAUNCHER),
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            **platform_options,
        )
        lease = _ProcessTreeLease(process, baseline)
        stdout_capture = _BoundedCapture()
        stderr_capture = _BoundedCapture()
        capture_threads = (
            threading.Thread(target=stdout_capture.drain, args=(process.stdout,), daemon=True),
            threading.Thread(target=stderr_capture.drain, args=(process.stderr,), daemon=True),
        )

        launch_payload = (
            json.dumps(list(command), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            + b"\n"
            + (stdin_data or b"")
        )

        def write_stdin() -> None:
            if process is None or process.stdin is None:
                return
            try:
                process.stdin.write(launch_payload)
                process.stdin.flush()
            except BrokenPipeError:
                pass
            except BaseException as exc:
                writer_errors.append(exc)
            finally:
                process.stdin.close()

        writer = threading.Thread(target=write_stdin, daemon=True)
        if process.stdout is None or process.stderr is None:
            raise OSError("subprocess pipes unavailable")
        for thread in capture_threads:
            try:
                thread.start()
            except BaseException:
                if thread.is_alive():
                    started_capture_threads.append(thread)
                raise
            started_capture_threads.append(thread)
        try:
            writer.start()
        except BaseException:
            writer_started = writer.is_alive()
            raise
        writer_started = True
        returncode = process.wait(timeout=timeout)
        lease.terminate_remaining()
    except BaseException:
        try:
            if lease is not None:
                lease.terminate_remaining()
            elif process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=30)
        except BaseException:
            pass
        raise
    finally:
        deadline = time.monotonic() + 30.0
        joiners = ([writer] if writer is not None and writer_started else []) + started_capture_threads
        for thread in joiners:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        alive = [thread for thread in joiners if thread.is_alive()]
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException:
                        pass
        if alive:
            raise OSError("subprocess transport did not terminate before hard deadline")
    if writer_errors:
        raise OSError("subprocess stdin transport failed") from writer_errors[0]
    if stdout_capture is None or stderr_capture is None:
        raise OSError("subprocess capture unavailable")
    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout=stdout_capture.text(),
        stderr=stderr_capture.text(),
    )


def _run_one(
    spec: _CommandSpec,
    *,
    repository: Path,
    stdin_data: bytes | None = None,
) -> ReleaseCheck:
    print(f"[release-gate] {spec.name}", file=sys.stderr, flush=True)
    environment = _controlled_environment(repository)
    try:
        if spec.name == "dependency_audit":
            _validate_selected_audit_projection(repository)
        effective_stdin = stdin_data
        if any(
            Path(argument).name == "check_release_gate.py" for argument in spec.command
        ) and "--internal-check" in spec.command:
            sentinel = environment.get("HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL", "")
            if re.fullmatch(r"[0-9a-f]{64}", sentinel) is None:
                raise ReleaseGateError("internal release check channel is unavailable")
            effective_stdin = sentinel.encode("ascii") + b"\n"
        completed = _execute_bounded(
            spec.command,
            cwd=repository,
            env=environment,
            timeout=spec.timeout,
            stdin_data=effective_stdin,
        )
    except subprocess.TimeoutExpired:
        return ReleaseCheck(
            name=spec.name,
            passed=False,
            command=spec.command,
            details={"returncode": None, "error": "timeout", "timeout_seconds": spec.timeout},
        )
    except Exception as exc:
        return ReleaseCheck(
            name=spec.name,
            passed=False,
            command=spec.command,
            details={"returncode": None, "error": f"execution_failed:{type(exc).__name__}"},
        )
    try:
        mode_positions = [
            index for index, argument in enumerate(spec.command) if argument == "--mode"
        ]
        pre_cutover_near100 = (
            spec.name == "near100_scorecard"
            and len(mode_positions) == 1
            and mode_positions[0] + 1 < len(spec.command)
            and spec.command[mode_positions[0] + 1] == "pre_cutover"
            and any(
                Path(argument).name == "check_near100_scorecard.py"
                for argument in spec.command
            )
            and "--evidence-stdin" in spec.command
        )
        details = _safe_detail(
            completed.stdout,
            completed.stderr,
            completed.returncode,
            allow_pre_cutover_local=pre_cutover_near100,
        )
    except ReleaseGateError as exc:
        return ReleaseCheck(
            name=spec.name,
            passed=False,
            command=spec.command,
            details={"returncode": completed.returncode, "error": _redact_text(str(exc))},
        )
    return ReleaseCheck(
        name=spec.name,
        passed=completed.returncode == 0,
        command=spec.command,
        details=details,
    )


def _validate_selected_audit_projection(repository: Path) -> None:
    minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    lock_path = repository / f"pylock.{minor}.toml"
    constraints_path = repository / "constraints-ci.txt"
    try:
        lock_document = tomllib.loads(
            _secure_read_bytes(
                repository,
                PurePosixPath(lock_path.name),
                context="selected audit lock",
            ).decode("utf-8")
        )
        constraints_source = _secure_read_bytes(
            repository,
            PurePosixPath(constraints_path.name),
            context="selected audit projection",
        ).decode("utf-8")
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseGateError("selected audit graph cannot be parsed") from exc
    packages = lock_document.get("packages")
    if not isinstance(packages, list) or len(packages) != 43:
        raise ReleaseGateError("selected audit lock must contain exactly 43 packages")
    locked: dict[str, str] = {}
    for row in packages:
        if not isinstance(row, Mapping):
            raise ReleaseGateError("selected audit lock package row is invalid")
        name = row.get("name")
        version = row.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise ReleaseGateError("selected audit lock package row is invalid")
        identity = re.sub(r"[-_.]+", "-", name).casefold()
        if identity in locked:
            raise ReleaseGateError("selected audit lock contains duplicate package")
        locked[identity] = version
    projected: dict[str, str] = {}
    for raw_line in constraints_source.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)", line)
        if match is None:
            raise ReleaseGateError("selected audit projection row is invalid")
        identity = re.sub(r"[-_.]+", "-", match.group(1)).casefold()
        if identity in projected:
            raise ReleaseGateError("selected audit projection contains duplicate package")
        projected[identity] = match.group(2)
    if projected != locked:
        raise ReleaseGateError("selected audit projection differs from selected lock")


def _repository_identity(root: Path) -> str:
    remote = str(_git(root, "remote", "get-url", "origin")).strip().replace("\\", "/")
    if remote.startswith("git@github.com:"):
        remote = remote.removeprefix("git@github.com:")
    elif "github.com/" in remote:
        remote = remote.split("github.com/", 1)[1]
    identity = remote.removesuffix(".git").strip("/")
    if identity.count("/") != 1:
        raise ReleaseGateError("repository identity cannot be derived from origin")
    return identity


def _dirty_tree_fingerprint(root: Path) -> tuple[str, str]:
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", text=False)
    diff = _git(root, "diff", "--binary", "HEAD", "--", text=False)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z", text=False)
    if not all(isinstance(value, bytes) for value in (status, diff, untracked)):
        raise ReleaseGateError("binary repository inspection returned text")
    digest = hashlib.sha256()
    digest.update(b"status\0" + status)
    digest.update(b"diff\0" + diff)
    for encoded in sorted(value for value in untracked.split(b"\0") if value):
        try:
            relative = encoded.decode("utf-8")
        except UnicodeError as exc:
            raise ReleaseGateError("untracked path is not UTF-8") from exc
        pure = PurePosixPath(relative)
        if pure.is_absolute() or "\\" in relative or any(
            part in {"", ".", ".."} for part in pure.parts
        ):
            raise ReleaseGateError("untracked path is non-canonical")
        path = root
        for index, part in enumerate(pure.parts):
            path /= part
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise ReleaseGateError("untracked path cannot be inspected") from exc
            final = index == len(pure.parts) - 1
            expected = stat.S_ISREG(metadata.st_mode) if final else stat.S_ISDIR(metadata.st_mode)
            if not expected or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                raise ReleaseGateError("untracked path contains link/reparse/non-regular data")
            if final and getattr(metadata, "st_nlink", 1) not in {0, 1}:
                raise ReleaseGateError("untracked file must not be a hardlink")
        digest.update(
            b"untracked\0"
            + encoded
            + b"\0"
            + _secure_read_bytes(
                root,
                PurePosixPath(relative),
                context="untracked fingerprint source",
            )
        )
    return ("dirty" if status else "clean", digest.hexdigest())


def _capture_snapshot(repository: Path, outputs_root: Path) -> _GateSnapshot:
    outputs_digest = _outputs_inventory_sha256(repository, outputs_root)
    state, fingerprint = _dirty_tree_fingerprint(repository)
    if state != "clean":
        raise ReleaseGateError("release gate refuses a dirty repository")
    return _GateSnapshot(
        commit_oid=str(_git(repository, "rev-parse", "HEAD")).strip(),
        tree_oid=str(_git(repository, "rev-parse", "HEAD^{tree}")).strip(),
        repository_fingerprint=fingerprint,
        outputs_inventory_sha256=outputs_digest,
        repository_identity=_repository_identity(repository),
    )


def _assert_snapshot_unchanged(
    repository: Path, outputs_root: Path, expected: _GateSnapshot
) -> None:
    try:
        actual = _capture_snapshot(repository, outputs_root)
    except ReleaseGateError as exc:
        raise ReleaseGateError("repository or outputs changed during release gate") from exc
    if actual != expected:
        raise ReleaseGateError("repository or outputs changed during release gate")


def _atomic_release_check(check_id: str) -> str:
    mappings = {
        "contract_spine": "contract_spine",
        "twelve_deck_acceptance": "twelve_deck_acceptance",
        "version_consistency": "version_consistency",
        "owner_policy": "contract_spine",
        "runtime_surface_policy": "contract_spine",
        "lowering_precision": "contract_spine",
        "lowering_recall": "contract_spine",
        "branch_coverage": "full_tests_and_coverage",
        "critical_coverage": "full_tests_and_coverage",
        "contract_mutations": "contract_mutations",
        "determinism": "twelve_deck_determinism",
        "distribution": "distribution",
        "deck_identity": "twelve_deck_acceptance",
        "main_slots": "twelve_deck_acceptance",
        "card_module_dispositions": "contract_spine",
        "claim_dispositions": "contract_spine",
        "globalvalues_dispositions": "contract_spine",
        "architecture_tests": "contract_spine",
        "transaction_fault_matrix": "transaction_fault_matrix",
        "package_immutability": "package_immutability",
        "distribution_contents": "distribution",
        "publishable_path_scan": "publishable_path_scan",
        "output_inventory": "output_inventory",
        "repository_hygiene": "repository_hygiene",
        "workspace_residue": "repository_hygiene",
    }
    try:
        return mappings[check_id]
    except KeyError as exc:
        raise ReleaseGateError(f"no release check owns atomic evidence: {check_id}") from exc


_FINAL_DISPOSITIONS = frozenset(
    {
        "runtime_emitted",
        "bot_delegated",
        "suppressed_unsupported_surface",
        "suppressed_insufficient_authority",
        "analysis_only_sideboard",
    }
)
_LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "deck_fingerprint",
        "content_sha256",
        "authority",
        "normal_apply_authority",
        "apply_blocking",
        "operator_gate_impact",
        "cards",
        "claims",
    }
)
_LEDGER_CARD_FIELDS = frozenset(
    {
        "composite_card_key",
        "deck_fingerprint",
        "zone",
        "physical_owner",
        "official_semantics",
        "claim_ids",
        "authority_lane",
        "disposition",
        "reason_code",
        "runtime_paths",
        "evidence_ids",
    }
)
_LEDGER_CLAIM_FIELDS = frozenset(
    {
        "composite_claim_identity",
        "deck_fingerprint",
        "claim_id",
        "claim_kind",
        "disposition",
        "reason_code",
        "runtime_paths",
        "evidence_id",
    }
)
_AUDIT_FIELDS = frozenset(
    {
        "schema_version",
        "deck_name",
        "authority",
        "normal_apply_authority",
        "apply_blocking",
        "operator_gate_impact",
        "summary",
        "card_rows",
        "claim_rows",
        "claim_lifecycle_rows",
    }
)
_AUDIT_CLAIM_FIELDS = frozenset(
    {
        "claim_id",
        "claim_kind",
        "cards",
        "evidence_text_short",
        "source_title",
        "source_type",
        "source_lane",
        "policy_lane",
        "claim_readiness",
        "evidence_authority",
        "evidence_lane_error",
        "strategic_receipt_verified",
        "trust_ceiling",
        "lane",
        "first_reason",
        "lowered_surfaces",
        "surfaces",
    }
)
_AUDIT_CLAIM_FIELD_VARIANTS = frozenset(
    {
        _AUDIT_CLAIM_FIELDS,
        _AUDIT_CLAIM_FIELDS | {"action", "condition", "selector"},
        _AUDIT_CLAIM_FIELDS | {"operator", "timing_kind"},
    }
)
_AUDIT_SUMMARY_FIELDS = frozenset(
    {
        "cards_total",
        "cards_with_missing_links",
        "cards_with_runtime_lowered_claims",
        "cards_with_suppressed_claims",
        "claim_kind_policy_counts",
        "claim_lifecycle_decision_counts",
        "claims_total",
        "report_only_claims",
        "runtime_evidence_required_claims",
        "runtime_lowered_claims",
        "suppressed_claims",
        "unsupported_or_unmapped_claims",
    }
)
_AUDIT_CARD_FIELDS = frozenset(
    {
        "card_id",
        "claim_lanes",
        "deck_zone",
        "first_missing_link",
        "name",
        "readiness_lane",
        "roles",
        "runtime_eligible",
        "runtime_surfaces",
        "sideboard_memberships",
        "sideboard_owner_card_id",
        "sideboard_owner_card_ids",
    }
)
_AUDIT_LIFECYCLE_FIELDS = frozenset(
    {
        "builder_or_router_decision",
        "claim_id",
        "claim_kind",
        "emitted_files",
        "final_runtime_effect",
        "first_missing_link",
        "operator_impact",
        "policy_lane",
        "quarantine_reason",
        "quarantine_status",
        "runtime_eligibility",
        "runtime_surface",
        "suppressed_reason",
        "surface_gate_decision",
        "surface_gate_reason",
    }
)
_AUDIT_SURFACE_FIELDS = frozenset({"allowed", "claim_kind", "reason", "surface"})
_AUDIT_SIDEBOARD_MEMBERSHIP_FIELDS = frozenset(
    {"count", "owner_card_id", "sideboard_index"}
)
_AUDIT_EVIDENCE_AUTHORITY_FIELDS = frozenset(
    {
        "as_of_date",
        "authority_id",
        "claim_kind",
        "content_sha256",
        "exact_deck_fingerprint",
        "lane",
        "reason",
        "runtime_authorized",
        "source_identity",
    }
)
_CLAIM_KINDS = frozenset(
    {
        "card_role",
        "choose_one_choice",
        "combo_sequence",
        "discover_choice",
        "gameplan_posture",
        "hero_power_transform",
        "known_bad_pattern",
        "mechanic_usage",
        "mulligan_keep",
        "targeting_rule",
    }
)
_FIRST_REASONS = frozenset(
    {
        "attack_owner_not_proven",
        "battlecry_owner_does_not_attack",
        "buff_target_owner_mismatch",
        "choose_one_condition_not_encoded",
        "claim_kind_not_mulligan_surface",
        "claim_not_runtime_lowerable",
        "combo_count_condition_not_encoded",
        "discard_trigger_not_manual_play",
        "discover_condition_not_encoded",
        "dredge_condition_not_encoded",
        "globalvalues_requires_exact_deck_match",
        "hand_position_condition_not_encoded",
        "health_cost_condition_not_encoded",
        "imbue_condition_not_encoded",
        "mulligan_requires_exact_deck_match",
        "outcast_condition_not_encoded",
        "reciprocal_burn_report_only",
        "semantic_surface_not_expressible",
        "semantic_surface_not_proven",
        "shatter_state_not_encoded",
        "spell_cannot_own_on_board",
        "spell_cannot_use_battlecry_target",
        "strategic_provenance_not_live_verified",
        "symmetric_board_condition_not_encoded",
        "symmetric_summon_condition_not_encoded",
        "trigger_owner_does_not_attack",
        "unresolved_option_identity",
        "variable_cost_condition_not_encoded",
    }
)
_SURFACE_REASONS = frozenset(
    {
        "allowed",
        "claim_kind_not_cardid_surface",
        "claim_kind_not_combo_surface",
        "claim_kind_not_globalvalues_surface",
        "claim_kind_not_mulligan_surface",
        "claim_not_runtime_lowerable",
        "combo_requires_public_guide_source",
        "globalvalues_requires_exact_deck_match",
        "mulligan_requires_exact_deck_match",
        "strategic_provenance_not_live_verified",
        "targeting_requires_exact_deck_match",
        "targeting_requires_public_guide_source",
    }
)
_SURFACE_GATE_REASONS = frozenset(
    {
        "allowed",
        "bot_delegated",
        "claim_kind_not_mulligan_surface",
        "claim_not_runtime_lowerable",
        "globalvalues_requires_exact_deck_match",
        "mulligan_requires_exact_deck_match",
        "strategic_provenance_not_live_verified",
        "targeting_requires_public_guide_source",
    }
)
_CARD_FIRST_MISSING_LINKS = frozenset(
    {
        "needs_condition_lowering",
        "needs_runtime_surface",
        "needs_target_scope",
        "none",
        "semantic_surface_not_expressible",
    }
)
_LIFECYCLE_SUPPRESSED_REASONS = _FIRST_REASONS | frozenset(
    {"bot_delegated", "builder_or_router_missing", "source_eligibility"}
)


def _require_closed_fields(
    value: Any,
    fields: frozenset[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ReleaseGateError(f"{label} schema mismatch")
    return value


def _require_closed_audit_claim(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) not in _AUDIT_CLAIM_FIELD_VARIANTS:
        raise ReleaseGateError("semantic source audit claim row schema mismatch")
    return value


def _string_sequence(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and all(isinstance(item, str) for item in value)
    )


def _string_in(value: Any, choices: frozenset[str] | set[str]) -> bool:
    return isinstance(value, str) and value in choices


def _validate_audit_claim_nested(row: Mapping[str, Any]) -> None:
    surfaces = row.get("surfaces")
    if not isinstance(surfaces, Mapping) or set(surfaces) != {
        "cardid",
        "combo",
        "globalvalues",
        "mulligan",
    }:
        raise ReleaseGateError("semantic source audit claim surfaces schema mismatch")
    for surface_name, raw in surfaces.items():
        surface = _require_closed_fields(
            raw, _AUDIT_SURFACE_FIELDS, label="semantic source audit surface"
        )
        if (
            not isinstance(surface.get("allowed"), bool)
            or surface.get("claim_kind") != row.get("claim_kind")
            or surface.get("surface") != surface_name
            or not _string_in(surface.get("reason"), _SURFACE_REASONS)
            or surface.get("allowed") is not (surface.get("reason") == "allowed")
        ):
            raise ReleaseGateError("semantic source audit surface binding mismatch")
    for field in ("cards", "lowered_surfaces"):
        if not _string_sequence(row.get(field)):
            raise ReleaseGateError("semantic source audit claim row schema mismatch")
    if row.get("action") is not None and not isinstance(row.get("action"), str):
        raise ReleaseGateError("semantic source audit claim row schema mismatch")
    if row.get("selector") is not None and not isinstance(row.get("selector"), str):
        raise ReleaseGateError("semantic source audit claim row schema mismatch")
    condition = row.get("condition")
    if condition is not None and not (
        isinstance(condition, str) or (isinstance(condition, Mapping) and not condition)
    ):
        raise ReleaseGateError("semantic source audit claim row schema mismatch")
    if (
        not _string_in(row.get("claim_kind"), _CLAIM_KINDS)
        or not _string_in(row.get("source_type"), {"", "official_card_data", "public_guide"})
        or not _string_in(
            row.get("source_lane"),
            {"", "archetype_matched_public_guide", "deck_matched_public_guide"},
        )
        or not _string_in(
            row.get("policy_lane"), {"runtime_lowerable", "suppressed_or_conditional"}
        )
        or not _string_in(
            row.get("claim_readiness"),
            {
            "explicit_low_confidence",
            "guide_backed",
            "source_backed_static_semantics",
            },
        )
        or not (
            row.get("evidence_lane_error") is None
            or row.get("evidence_lane_error") == "evidence_lane_unclassified"
        )
        or not isinstance(row.get("strategic_receipt_verified"), bool)
        or not _string_in(
            row.get("trust_ceiling"), {"guide", "report_only", "static_semantics"}
        )
        or not _string_in(
            row.get("lane"),
            {
            "report_only",
            "runtime_lowered",
            "suppressed_with_reason",
            "unsupported_or_unmapped",
            },
        )
        or not _string_in(row.get("first_reason"), _FIRST_REASONS)
        or not isinstance(row.get("evidence_text_short"), str)
        or not isinstance(row.get("source_title"), str)
        or ("action" in row and row.get("action") != "hold")
        or ("operator" in row and row.get("operator") != ">>")
        or ("timing_kind" in row and row.get("timing_kind") != "same_turn")
    ):
        raise ReleaseGateError("semantic source audit claim row scalar domain mismatch")


def _validate_evidence_authority(
    row: Mapping[str, Any], deck_fingerprint: str
) -> Mapping[str, Any] | None:
    raw = row.get("evidence_authority")
    if raw is None:
        if row.get("evidence_lane_error") != "evidence_lane_unclassified":
            raise ReleaseGateError("semantic source authority evidence binding mismatch")
        return None
    authority = _require_closed_fields(
        raw,
        _AUDIT_EVIDENCE_AUTHORITY_FIELDS,
        label="semantic source authority evidence",
    )
    strings = (
        "as_of_date",
        "authority_id",
        "claim_kind",
        "content_sha256",
        "reason",
        "source_identity",
    )
    if (
        any(not isinstance(authority.get(field), str) or not authority[field] for field in strings)
        or authority.get("claim_kind") != row.get("claim_kind")
        or row.get("evidence_lane_error") is not None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", authority["content_sha256"]) is None
    ):
        raise ReleaseGateError("semantic source authority evidence binding mismatch")
    lane = authority.get("lane")
    if lane == "C":
        valid_lane = (
            authority.get("runtime_authorized") is False
            and authority.get("exact_deck_fingerprint") is None
            and re.fullmatch(r"C:claim_[0-9a-f]{12}", authority["authority_id"])
            is not None
        )
    elif lane == "B":
        valid_lane = (
            authority.get("runtime_authorized") is True
            and authority.get("exact_deck_fingerprint") == deck_fingerprint
            and row.get("strategic_receipt_verified") is True
            and re.fullmatch(r"B:claim_[0-9a-f]{12}", authority["authority_id"])
            is not None
        )
    else:
        valid_lane = False
    if not valid_lane:
        raise ReleaseGateError("semantic source authority evidence binding mismatch")
    return authority


def _validate_source_audit(
    audit: Mapping[str, Any],
    ledger_cards: Sequence[Any],
    ledger_claims: Sequence[Any],
) -> dict[str, Mapping[str, Any]]:
    summary = _require_closed_fields(
        audit.get("summary"), _AUDIT_SUMMARY_FIELDS, label="semantic source audit summary"
    )
    card_rows = audit.get("card_rows")
    claim_rows = audit.get("claim_rows")
    lifecycle_rows = audit.get("claim_lifecycle_rows")
    if (
        not isinstance(card_rows, Mapping)
        or not isinstance(claim_rows, Mapping)
        or not isinstance(lifecycle_rows, Sequence)
        or isinstance(lifecycle_rows, (str, bytes, bytearray))
        or len(card_rows) != len(ledger_cards)
        or len(claim_rows) != len(ledger_claims)
        or len(lifecycle_rows) != len(ledger_claims)
    ):
        raise ReleaseGateError("semantic source audit row count mismatch")

    for key, raw in card_rows.items():
        row = _require_closed_fields(
            raw, _AUDIT_CARD_FIELDS, label="semantic source audit card row"
        )
        claim_lanes = row.get("claim_lanes")
        if (
            not isinstance(key, str)
            or row.get("card_id") != key
            or not isinstance(claim_lanes, Mapping)
            or any(
                lane not in {"runtime_lowered", "suppressed_with_reason", "unsupported_or_unmapped"}
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 0
                for lane, count in claim_lanes.items()
            )
            or not isinstance(row.get("runtime_eligible"), bool)
            or any(
                not _string_sequence(row.get(field))
                for field in ("roles", "runtime_surfaces", "sideboard_owner_card_ids")
            )
            or any(
                not isinstance(row.get(field), str)
                for field in ("deck_zone", "first_missing_link", "name", "readiness_lane")
            )
            or not _string_in(row.get("deck_zone"), {"main", "sideboard"})
            or not _string_in(row.get("first_missing_link"), _CARD_FIRST_MISSING_LINKS)
            or not _string_in(
                row.get("readiness_lane"),
                {"linked_runtime_source", "report_only_supported", "runtime_emitted"},
            )
            or not row.get("name")
            or not (
                row.get("sideboard_owner_card_id") is None
                or isinstance(row.get("sideboard_owner_card_id"), str)
            )
        ):
            raise ReleaseGateError("semantic source audit card row binding mismatch")
        memberships = row.get("sideboard_memberships")
        if (
            not isinstance(memberships, Sequence)
            or isinstance(memberships, (str, bytes, bytearray))
            or any(
                set(membership) != _AUDIT_SIDEBOARD_MEMBERSHIP_FIELDS
                or not isinstance(membership.get("owner_card_id"), str)
                or not isinstance(membership.get("count"), int)
                or isinstance(membership.get("count"), bool)
                or membership["count"] <= 0
                or not isinstance(membership.get("sideboard_index"), int)
                or isinstance(membership.get("sideboard_index"), bool)
                or membership["sideboard_index"] < 0
                for membership in memberships
                if isinstance(membership, Mapping)
            )
            or any(not isinstance(membership, Mapping) for membership in memberships)
        ):
            raise ReleaseGateError("semantic source audit card row binding mismatch")

    claims_by_id: dict[str, Mapping[str, Any]] = {}
    for key, raw in claim_rows.items():
        row = _require_closed_audit_claim(raw)
        _validate_audit_claim_nested(row)
        if not isinstance(key, str) or row.get("claim_id") != key or key in claims_by_id:
            raise ReleaseGateError("semantic source audit claim identity mismatch")
        claims_by_id[key] = row

    lifecycle_by_id: dict[str, Mapping[str, Any]] = {}
    for raw in lifecycle_rows:
        row = _require_closed_fields(
            raw,
            _AUDIT_LIFECYCLE_FIELDS,
            label="semantic source audit claim lifecycle row",
        )
        claim_id = row.get("claim_id")
        claim = claims_by_id.get(claim_id) if isinstance(claim_id, str) else None
        if (
            claim is None
            or claim_id in lifecycle_by_id
            or row.get("claim_kind") != claim.get("claim_kind")
            or row.get("policy_lane") != claim.get("policy_lane")
            or not _string_sequence(row.get("emitted_files"))
            or not _string_in(
                row.get("builder_or_router_decision"),
                {"bot_delegated", "emitted", "not_seen_by_builder", "suppressed"},
            )
            or not _string_in(
                row.get("runtime_eligibility"), {"report_only", "runtime_candidate"}
            )
            or not _string_in(row.get("surface_gate_decision"), {"allowed", "rejected"})
            or row.get("quarantine_status") != "clear"
            or row.get("quarantine_reason") != ""
            or not (
                row.get("first_missing_link") is None
                or _string_in(
                    row.get("first_missing_link"),
                    {"builder_or_router", "runtime_surface", "source_eligibility"},
                )
            )
            or not _string_in(row.get("surface_gate_reason"), _SURFACE_GATE_REASONS)
            or not (
                row.get("suppressed_reason") is None
                or _string_in(
                    row.get("suppressed_reason"), _LIFECYCLE_SUPPRESSED_REASONS
                )
            )
            or row.get("operator_impact") != "diagnostic_only"
            or not _string_in(
                row.get("final_runtime_effect"),
                {
                "delegated_to_bot",
                "emitted_runtime_row",
                "not_emitted_by_builder_or_router",
                "suppressed_runtime_claim",
                },
            )
            or not (
                row.get("runtime_surface") is None
                or (
                    isinstance(row.get("runtime_surface"), str)
                    and re.fullmatch(r"[A-Za-z0-9_]+\.json", row["runtime_surface"])
                    is not None
                )
            )
        ):
            raise ReleaseGateError("semantic source audit claim lifecycle binding mismatch")
        lifecycle_by_id[claim_id] = row
    if set(lifecycle_by_id) != set(claims_by_id):
        raise ReleaseGateError("semantic source audit claim lifecycle binding mismatch")

    expected_summary = {
        "cards_total": len(card_rows),
        "cards_with_missing_links": sum(
            row["first_missing_link"] != "none" for row in card_rows.values()
        ),
        "cards_with_runtime_lowered_claims": sum(
            row["claim_lanes"].get("runtime_lowered", 0) > 0 for row in card_rows.values()
        ),
        "cards_with_suppressed_claims": sum(
            row["claim_lanes"].get("suppressed_with_reason", 0) > 0
            for row in card_rows.values()
        ),
        "claim_kind_policy_counts": dict(
            sorted(
                {
                    lane: sum(row["policy_lane"] == lane for row in claims_by_id.values())
                    for lane in {row["policy_lane"] for row in claims_by_id.values()}
                }.items()
            )
        ),
        "claim_lifecycle_decision_counts": dict(
            sorted(
                {
                    decision: sum(
                        row["builder_or_router_decision"] == decision
                        for row in lifecycle_by_id.values()
                    )
                    for decision in {
                        row["builder_or_router_decision"] for row in lifecycle_by_id.values()
                    }
                }.items()
            )
        ),
        "claims_total": len(claims_by_id),
        "report_only_claims": sum(row["lane"] == "report_only" for row in claims_by_id.values()),
        "runtime_evidence_required_claims": sum(
            row["policy_lane"] == "runtime_evidence_required" for row in claims_by_id.values()
        ),
        "runtime_lowered_claims": sum(
            row["lane"] == "runtime_lowered" for row in claims_by_id.values()
        ),
        "suppressed_claims": sum(
            row["lane"] == "suppressed_with_reason" for row in claims_by_id.values()
        ),
        "unsupported_or_unmapped_claims": sum(
            row["lane"] == "unsupported_or_unmapped" for row in claims_by_id.values()
        ),
    }
    if dict(summary) != expected_summary:
        raise ReleaseGateError("semantic source audit summary binding mismatch")
    return lifecycle_by_id


def _current_revision_path(outputs: Path, deck_name: str) -> Path:
    current = _load_json_file(outputs, PurePosixPath(deck_name, "current.json"))
    revision = current.get("revision")
    if not isinstance(revision, str):
        raise ReleaseGateError("current output revision is missing")
    pure = PurePosixPath(revision)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ReleaseGateError("current output revision is non-canonical")
    path = outputs / deck_name
    for part in pure.parts:
        path /= part
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ReleaseGateError("current output revision contains unsafe data")
    return path


def _claim_authority_lane(
    audit: Mapping[str, Any],
    disposition: str,
    *,
    deck_fingerprint: str,
    lifecycle: Mapping[str, Any],
) -> str:
    readiness = audit.get("claim_readiness")
    source_lane = audit.get("source_lane")
    policy_lane = audit.get("policy_lane")
    trust_ceiling = audit.get("trust_ceiling")
    source_type = audit.get("source_type")
    lane = audit.get("lane")
    authority = _validate_evidence_authority(audit, deck_fingerprint)
    if (
        policy_lane not in {"runtime_lowerable", "suppressed_or_conditional"}
        or lane
        not in {
            "runtime_lowered",
            "suppressed_with_reason",
            "unsupported_or_unmapped",
            "report_only",
        }
        or not isinstance(audit.get("strategic_receipt_verified"), bool)
    ):
        raise ReleaseGateError("semantic source authority combination mismatch")

    no_runtime_row = (
        not lifecycle.get("emitted_files")
        and lifecycle.get("runtime_surface") is None
        and lifecycle.get("builder_or_router_decision") != "emitted"
    )
    if disposition == "bot_delegated":
        if (
            readiness != "explicit_low_confidence"
            or authority is not None
            or trust_ceiling != "report_only"
            or source_lane
            not in {"", "archetype_matched_public_guide", "deck_matched_public_guide"}
            or source_type not in {"", "public_guide"}
            or policy_lane != "suppressed_or_conditional"
            or lane not in {"report_only", "suppressed_with_reason"}
            or audit.get("strategic_receipt_verified") is not False
            or lifecycle.get("builder_or_router_decision") != "bot_delegated"
            or lifecycle.get("final_runtime_effect") != "delegated_to_bot"
            or lifecycle.get("runtime_eligibility") != "report_only"
            or lifecycle.get("surface_gate_decision") != "rejected"
            or lifecycle.get("surface_gate_reason") != "bot_delegated"
            or lifecycle.get("suppressed_reason") != "bot_delegated"
            or not no_runtime_row
        ):
            raise ReleaseGateError(
                "semantic claim disposition is incompatible with authority lane"
            )
        return "E"

    if (
        readiness == "source_backed_static_semantics"
        and source_lane == ""
        and authority is None
        and trust_ceiling in {"static_semantics", "report_only"}
        and source_type in {"", "official_card_data"}
        and audit.get("strategic_receipt_verified") is False
    ):
        authority_lane = "A"
    elif (
        readiness == "guide_backed"
        and source_lane == "deck_matched_public_guide"
        and authority is not None
        and authority.get("lane") == "B"
        and trust_ceiling == "guide"
        and source_type in {"", "public_guide"}
        and audit.get("strategic_receipt_verified") is True
    ):
        authority_lane = "B"
    elif (
        readiness == "guide_backed"
        and source_lane
        in {"", "archetype_matched_public_guide", "deck_matched_public_guide"}
        and (authority is None or authority.get("lane") == "C")
        and trust_ceiling == "guide"
        and source_type in {"", "public_guide"}
        and audit.get("strategic_receipt_verified") is False
    ):
        authority_lane = "C"
    elif (
        readiness == "explicit_low_confidence"
        and source_lane in {"", "archetype_matched_public_guide"}
        and (authority is None or authority.get("lane") == "C")
        and trust_ceiling == "report_only"
        and source_type in {"", "public_guide"}
        and audit.get("strategic_receipt_verified") is False
    ):
        authority_lane = "C"
    else:
        raise ReleaseGateError("semantic source authority combination mismatch")

    return authority_lane


def _produce_semantic_rows(
    repository: Path, outputs: Path, receipt_relative: str
) -> dict[str, list[dict[str, Any]]]:
    inventory = _load_json_file(
        repository, PurePosixPath("tests/fixtures/near100/current_semantic_inventory.json")
    )
    catalog = _load_json_file(
        repository, PurePosixPath("docs/operator/audited-deck-catalog.json")
    )
    audited_decks = catalog.get("decks")
    if not isinstance(audited_decks, list):
        raise ReleaseGateError("canonical semantic inventory catalog is invalid")
    try:
        validate_semantic_inventory(inventory, audited_catalog=audited_decks)
    except ValueError as exc:
        raise ReleaseGateError("canonical semantic inventory is invalid") from exc
    decks = inventory.get("decks")
    if not isinstance(decks, list) or len(decks) != 12:
        raise ReleaseGateError("canonical semantic inventory deck count mismatch")
    card_rows: list[dict[str, Any]] = []
    semantic_claims = inventory.get("semantic_claims")
    if not isinstance(semantic_claims, list) or len(semantic_claims) != SEMANTIC_CLAIM_COUNT:
        raise ReleaseGateError("canonical semantic claim inventory count mismatch")
    expected_claim_ids: list[str] = []
    for raw in semantic_claims:
        try:
            canonical = canonical_semantic_claim(raw)
        except ValueError as exc:
            raise ReleaseGateError("canonical semantic claim inventory is invalid") from exc
        if not isinstance(raw, Mapping) or dict(raw) != canonical:
            raise ReleaseGateError("canonical semantic claim inventory is invalid")
        expected_claim_ids.append(canonical["claim_key"])
    if len(set(expected_claim_ids)) != SEMANTIC_CLAIM_COUNT:
        raise ReleaseGateError("canonical semantic claim inventory identities are invalid")
    claim_groups: dict[str, dict[str, Any]] = {}
    claim_occurrences = 0
    all_ids: set[str] = set()
    for deck in decks:
        if not isinstance(deck, Mapping) or not isinstance(deck.get("deck_name"), str):
            raise ReleaseGateError("canonical semantic inventory deck schema mismatch")
        deck_name = deck["deck_name"]
        revision = _current_revision_path(outputs, deck_name)
        reports = revision / "04_package" / "reports"
        ledger = _load_json_file(reports, PurePosixPath("disposition_ledger.json"))
        audit = _load_json_file(reports, PurePosixPath("source_contract_audit.json"))
        _require_closed_fields(ledger, _LEDGER_FIELDS, label="semantic disposition ledger")
        _require_closed_fields(audit, _AUDIT_FIELDS, label="semantic source audit")
        if ledger.get("deck_fingerprint") != deck.get("deck_fingerprint"):
            raise ReleaseGateError("semantic disposition ledger deck binding mismatch")
        if audit.get("deck_name") != deck_name:
            raise ReleaseGateError("semantic source audit deck binding mismatch")
        ledger_cards = ledger.get("cards")
        ledger_claims = ledger.get("claims")
        audit_claims = audit.get("claim_rows")
        if not isinstance(ledger_cards, list) or not isinstance(ledger_claims, list) or not isinstance(audit_claims, Mapping):
            raise ReleaseGateError("semantic report schema mismatch")
        lifecycle_by_id = _validate_source_audit(audit, ledger_cards, ledger_claims)
        expected_cards = [
            row["composite_card_key"]
            for row in (*deck.get("main_cards", ()), *deck.get("sideboard_modules", ()))
        ]
        expected_card_surfaces: dict[tuple[str, str], str] = {}
        for expected_row in deck.get("main_cards", ()):
            expected_card_surfaces[("main_deck", expected_row["card_id"])] = expected_row[
                "composite_card_key"
            ]
        for expected_row in deck.get("sideboard_modules", ()):
            expected_card_surfaces[
                ("sideboard_module", expected_row["card_id"])
            ] = expected_row["composite_card_key"]
        if len(ledger_cards) != len(expected_cards):
            raise ReleaseGateError("semantic report row count mismatch")
        cards_by_id: dict[str, Mapping[str, Any]] = {}
        for raw in ledger_cards:
            row = _require_closed_fields(
                raw, _LEDGER_CARD_FIELDS, label="semantic card disposition row"
            )
            official = row.get("official_semantics")
            card_id = official.get("GameCardId") if isinstance(official, Mapping) else None
            zone = row.get("zone")
            reported_identity = row.get("composite_card_key")
            if reported_identity in expected_cards:
                obligation_id = reported_identity
            else:
                obligation_id = (
                    expected_card_surfaces.get((zone, card_id))
                    if isinstance(zone, str) and isinstance(card_id, str)
                    else None
                )
            allowed_reported = {
                obligation_id,
                f"{deck['deck_fingerprint']}:{zone}:{card_id}",
            }
            if (
                not isinstance(obligation_id, str)
                or obligation_id in cards_by_id
                or row.get("deck_fingerprint") != deck.get("deck_fingerprint")
                or not isinstance(row.get("physical_owner"), str)
                or reported_identity not in allowed_reported
            ):
                raise ReleaseGateError("semantic card disposition identity mismatch")
            cards_by_id[obligation_id] = row
        claims_by_id: dict[str, Mapping[str, Any]] = {}
        for raw in ledger_claims:
            row = _require_closed_fields(
                raw, _LEDGER_CLAIM_FIELDS, label="semantic claim disposition row"
            )
            obligation_id = row.get("composite_claim_identity")
            claim_id = row.get("claim_id")
            if (
                not isinstance(obligation_id, str)
                or not isinstance(claim_id, str)
                or obligation_id in claims_by_id
                or row.get("deck_fingerprint") != deck.get("deck_fingerprint")
                or not isinstance(row.get("evidence_id"), str)
                or re.fullmatch(rf"(?:[A-E]:)?{re.escape(claim_id)}", row["evidence_id"])
                is None
            ):
                raise ReleaseGateError("semantic claim disposition identity mismatch")
            claims_by_id[obligation_id] = row
        if len(audit_claims) != len(ledger_claims):
            raise ReleaseGateError("semantic source audit row count mismatch")
        for claim_id, raw in audit_claims.items():
            row = _require_closed_audit_claim(raw)
            if not isinstance(claim_id, str) or row.get("claim_id") != claim_id:
                raise ReleaseGateError("semantic source audit claim identity mismatch")
        claim_ids = {row["claim_id"] for row in claims_by_id.values()}
        if set(audit_claims) != claim_ids:
            raise ReleaseGateError("semantic source audit identities do not match ledger")
        if set(cards_by_id) != set(expected_cards):
            raise ReleaseGateError("semantic report identities do not match canonical inventory")
        for obligation_id in expected_cards:
            row = cards_by_id[obligation_id]
            lane, disposition = row.get("authority_lane"), row.get("disposition")
            if lane not in {"A", "B", "C", "D", "E"} or disposition not in _FINAL_DISPOSITIONS:
                raise ReleaseGateError("card semantic disposition is invalid")
            if obligation_id in all_ids:
                raise ReleaseGateError("duplicate semantic obligation identity")
            all_ids.add(obligation_id)
            card_rows.append(
                {
                    "obligation_id": obligation_id,
                    "authority_lanes": [lane],
                    "final_disposition": True,
                    "evidence_paths": [receipt_relative],
                }
            )
        for row in claims_by_id.values():
            claim_id, disposition = row.get("claim_id"), row.get("disposition")
            audit_row = audit_claims.get(claim_id) if isinstance(claim_id, str) else None
            if disposition not in _FINAL_DISPOSITIONS or not isinstance(audit_row, Mapping):
                raise ReleaseGateError("claim semantic disposition is invalid")
            try:
                canonical = canonical_semantic_claim(audit_row)
            except ValueError as exc:
                raise ReleaseGateError("claim semantic source payload is invalid") from exc
            obligation_id = canonical["claim_key"]
            group = claim_groups.setdefault(
                obligation_id,
                {"authority_lanes": set(), "final_dispositions": []},
            )
            lifecycle = lifecycle_by_id.get(claim_id)
            if lifecycle is None:
                raise ReleaseGateError("semantic source audit claim lifecycle binding mismatch")
            authority_lane = _claim_authority_lane(
                audit_row,
                disposition,
                deck_fingerprint=deck["deck_fingerprint"],
                lifecycle=lifecycle,
            )
            if authority_lane == "E" and (
                lifecycle.get("emitted_files")
                or lifecycle.get("runtime_surface") is not None
                or lifecycle.get("builder_or_router_decision") == "emitted"
            ):
                raise ReleaseGateError(
                    "semantic claim disposition is incompatible with authority lane"
                )
            group["authority_lanes"].add(authority_lane)
            group["final_dispositions"].append(disposition in _FINAL_DISPOSITIONS)
            claim_occurrences += 1
    if claim_occurrences != _SEMANTIC_REPORT_CLAIM_OCCURRENCES:
        raise ReleaseGateError("semantic claim occurrence count mismatch")
    if set(claim_groups) != set(expected_claim_ids):
        raise ReleaseGateError("semantic report identities do not match canonical inventory")
    claim_rows: list[dict[str, Any]] = []
    for obligation_id in expected_claim_ids:
        group = claim_groups[obligation_id]
        lanes = sorted(group["authority_lanes"])
        final_dispositions = group["final_dispositions"]
        if len(lanes) != 1:
            raise ReleaseGateError("canonical semantic claim has ambiguous authority lanes")
        if not final_dispositions or not all(final_dispositions):
            raise ReleaseGateError("canonical semantic claim has a non-final occurrence")
        if obligation_id in all_ids:
            raise ReleaseGateError("duplicate semantic obligation identity")
        all_ids.add(obligation_id)
        claim_rows.append(
            {
                "obligation_id": obligation_id,
                "authority_lanes": lanes,
                "final_disposition": True,
                "evidence_paths": [receipt_relative],
            }
        )
    if len(card_rows) != SEMANTIC_CARD_MODULE_COUNT or len(claim_rows) != SEMANTIC_CLAIM_COUNT:
        raise ReleaseGateError("produced semantic closure count mismatch")
    return {"card_module_rows": card_rows, "claim_rows": claim_rows}


def _gh_json(repository: Path, *arguments: str) -> Any:
    completed = _execute_bounded(
        ("gh", *arguments),
        cwd=repository,
        env=_controlled_environment(repository),
        timeout=60,
    )
    if completed.returncode != 0:
        raise ReleaseGateError("live GitHub verification failed")
    return _load_json_bytes(completed.stdout.encode("utf-8"), source="live GitHub response")


_RULESET_SUMMARY_FIELDS = frozenset(
    {
        "id",
        "node_id",
        "name",
        "target",
        "source_type",
        "source",
        "enforcement",
        "created_at",
        "updated_at",
        "_links",
    }
)
_RULESET_DETAIL_FIELDS = _RULESET_SUMMARY_FIELDS | {
    "bypass_actors",
    "current_user_can_bypass",
    "conditions",
    "rules",
}


def _closed_github_mapping(
    value: Any,
    *,
    allowed: frozenset[str],
    required: frozenset[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReleaseGateError(f"live GitHub {label} response schema mismatch")
    fields = set(value)
    if not required <= fields or not fields <= allowed:
        raise ReleaseGateError(f"live GitHub {label} response schema mismatch")
    return value


def _gh_paginated_rulesets(repository: Path, identity: str) -> tuple[Mapping[str, Any], ...]:
    pages = _gh_json(
        repository,
        "api",
        "--paginate",
        "--slurp",
        f"repos/{identity}/rulesets",
    )
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ReleaseGateError("live GitHub ruleset pagination schema mismatch")
    rows: list[Mapping[str, Any]] = []
    seen_ids: set[int] = set()
    for page in pages:
        for raw in page:
            row = _closed_github_mapping(
                raw,
                allowed=_RULESET_SUMMARY_FIELDS,
                required=frozenset({"id", "name", "target", "enforcement"}),
                label="ruleset summary",
            )
            ruleset_id = row.get("id")
            if not isinstance(ruleset_id, int) or isinstance(ruleset_id, bool):
                raise ReleaseGateError("live GitHub branch ruleset identity is invalid")
            if ruleset_id in seen_ids:
                raise ReleaseGateError("live GitHub ruleset pagination contains duplicate identities")
            seen_ids.add(ruleset_id)
            rows.append(row)
    return tuple(sorted(rows, key=lambda row: (int(row["id"]), str(row["name"]))))


def _collect_live_github_state(repository: Path, snapshot: _GateSnapshot) -> dict[str, Any]:
    identity = snapshot.repository_identity
    settings = _gh_json(repository, "api", f"repos/{identity}")
    rulesets = _gh_paginated_rulesets(repository, identity)
    tag = _gh_json(repository, "api", f"repos/{identity}/git/ref/tags/v{__version__}")
    release = _gh_json(repository, "api", f"repos/{identity}/releases/tags/v{__version__}")
    if not isinstance(tag, Mapping) or not isinstance(tag.get("object"), Mapping):
        raise ReleaseGateError("live GitHub tag response schema mismatch")
    ref_object = tag["object"]
    peeled_oid = ref_object.get("sha")
    if ref_object.get("type") == "tag":
        annotated = _gh_json(repository, "api", f"repos/{identity}/git/tags/{peeled_oid}")
        if not isinstance(annotated, Mapping) or not isinstance(annotated.get("object"), Mapping):
            raise ReleaseGateError("live GitHub annotated tag response schema mismatch")
        peeled_oid = annotated["object"].get("sha")
    active_rulesets = [
        row
        for row in rulesets
        if row.get("enforcement") == "active" and row.get("target") == "branch"
    ]
    if len(active_rulesets) != 1:
        raise ReleaseGateError("live GitHub must expose exactly one active branch ruleset")
    ruleset_id = active_rulesets[0].get("id")
    if not isinstance(ruleset_id, int):
        raise ReleaseGateError("live GitHub branch ruleset identity is invalid")
    ruleset = _closed_github_mapping(
        _gh_json(repository, "api", f"repos/{identity}/rulesets/{ruleset_id}"),
        allowed=_RULESET_DETAIL_FIELDS,
        required=frozenset(
            {
                "id",
                "name",
                "target",
                "enforcement",
                "bypass_actors",
                "conditions",
                "rules",
            }
        ),
        label="ruleset detail",
    )
    if ruleset.get("id") != ruleset_id:
        raise ReleaseGateError("live GitHub ruleset detail identity mismatch")
    return {
        "schema_version": 1,
        "repository": identity,
        "commit_oid": snapshot.commit_oid,
        "tree_oid": snapshot.tree_oid,
        "release_tag": f"v{__version__}",
        "settings": settings,
        "ruleset": ruleset,
        "tag": {
            "ref_object_oid": ref_object.get("sha"),
            "object_type": ref_object.get("type"),
            "peeled_commit_oid": peeled_oid,
        },
        "release": release,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "transaction_id": uuid.uuid4().hex,
    }


def _validate_live_github_state(state: Mapping[str, Any], snapshot: _GateSnapshot) -> None:
    expected_fields = {
        "schema_version", "repository", "commit_oid", "tree_oid", "release_tag",
        "settings", "ruleset", "tag", "release", "observed_at", "transaction_id",
    }
    if set(state) != expected_fields or state.get("schema_version") != 1:
        raise ReleaseGateError("live GitHub transaction schema mismatch")
    if (
        state.get("repository") != snapshot.repository_identity
        or state.get("commit_oid") != snapshot.commit_oid
        or state.get("tree_oid") != snapshot.tree_oid
        or state.get("release_tag") != f"v{__version__}"
    ):
        raise ReleaseGateError("live GitHub transaction repository/release binding mismatch")
    transaction_id = state.get("transaction_id")
    if not isinstance(transaction_id, str) or re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None:
        raise ReleaseGateError("live GitHub transaction identity mismatch")
    try:
        observed = datetime.fromisoformat(str(state.get("observed_at")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseGateError("live GitHub observation time invalid") from exc
    age = abs((datetime.now(timezone.utc) - observed).total_seconds())
    if observed.tzinfo is None or age > _FINAL_EVIDENCE_MAX_AGE_SECONDS:
        raise ReleaseGateError("live GitHub observation is stale")
    settings, ruleset, tag, release = (
        state.get("settings"), state.get("ruleset"), state.get("tag"), state.get("release")
    )
    if not all(isinstance(value, Mapping) for value in (settings, ruleset, tag, release)):
        raise ReleaseGateError("live GitHub transaction payload schema mismatch")
    if (
        settings.get("full_name") != snapshot.repository_identity
        or settings.get("default_branch") != "main"
        or settings.get("archived") is not False
        or settings.get("disabled") is not False
        or settings.get("visibility") != "public"
        or settings.get("has_issues") is not True
        or settings.get("has_projects") is not False
        or settings.get("has_wiki") is not False
        or settings.get("has_discussions") is not False
        or settings.get("allow_squash_merge") is not True
        or settings.get("allow_merge_commit") is not False
        or settings.get("allow_rebase_merge") is not False
        or settings.get("allow_auto_merge") is not False
        or settings.get("delete_branch_on_merge") is not True
    ):
        raise ReleaseGateError("live GitHub repository settings do not satisfy release policy")
    ruleset_conditions = ruleset.get("conditions")
    ruleset_ref_name = (
        ruleset_conditions.get("ref_name")
        if isinstance(ruleset_conditions, Mapping)
        else None
    )
    rules = ruleset.get("rules")
    rule_types = {
        row.get("type") for row in rules if isinstance(row, Mapping)
    } if isinstance(rules, list) else set()
    if (
        not set(ruleset) <= _RULESET_DETAIL_FIELDS
        or
        not isinstance(ruleset.get("id"), int)
        or isinstance(ruleset.get("id"), bool)
        or ruleset.get("name") != "main-linear-signed"
        or ruleset.get("target") != "branch"
        or ruleset.get("enforcement") != "active"
        or ruleset.get("bypass_actors") != []
        or not isinstance(ruleset_conditions, Mapping)
        or set(ruleset_conditions) != {"ref_name"}
        or not isinstance(ruleset_ref_name, Mapping)
        or set(ruleset_ref_name) != {"include", "exclude"}
        or ruleset_ref_name.get("include") != ["refs/heads/main"]
        or ruleset_ref_name.get("exclude") != []
        or not isinstance(rules, list)
        or any(not isinstance(row, Mapping) or set(row) != {"type"} for row in rules)
        or rule_types
        != {"deletion", "non_fast_forward", "required_linear_history", "required_signatures"}
    ):
        raise ReleaseGateError("live GitHub branch ruleset does not satisfy release policy")
    if tag.get("peeled_commit_oid") != snapshot.commit_oid:
        raise ReleaseGateError("live GitHub tag does not resolve to release commit")
    if (
        not isinstance(release.get("id"), int)
        or release.get("tag_name") != f"v{__version__}"
        or release.get("draft") is not False
        or release.get("prerelease") is not False
        or not isinstance(release.get("html_url"), str)
        or not isinstance(release.get("assets"), list)
        or release.get("assets") != []
    ):
        raise ReleaseGateError("live GitHub release payload does not satisfy release policy")


_RECEIPT_BINDING_FIELDS = (
    "repository_identity",
    "commit_oid",
    "tree_oid",
    "tree_state",
    "dirty_tree_fingerprint",
    "generation_mode",
)


def _receipt_binding(
    meta: Mapping[str, Any], *, github_state: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    binding = {field: meta[field] for field in _RECEIPT_BINDING_FIELDS}
    if github_state is not None:
        binding.update(
            {
                "transaction_id": github_state["transaction_id"],
                "observed_at": github_state["observed_at"],
            }
        )
    return binding


def _release_check_receipt(
    *, check_id: str, source: ReleaseCheck, binding: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "producer": "hsconfig.release_gate.base_check",
        "check_id": check_id,
        "binding": dict(binding),
        "result": {"passed": source.passed},
    }


def _validated_success_receipt(
    *, producer: str, check_id: str, binding: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "producer": producer,
        "check_id": check_id,
        "binding": dict(binding),
        "result": {"passed": True},
    }


def _build_base_evidence(
    *, repository: Path, outputs_root: Path, checks: Sequence[ReleaseCheck],
    tree_mode: TreeMode, snapshot: _GateSnapshot,
) -> dict[str, Any]:
    by_name = {check.name: check for check in checks}
    failed_checks = sorted(check.name for check in checks if not check.passed)
    if failed_checks:
        raise ReleaseGateError("base evidence cannot be produced from failed checks")
    score_mode = "final" if tree_mode == "final" else "pre_cutover"
    github_state: Mapping[str, Any] | None = None
    if score_mode == "final":
        collected = _collect_live_github_state(repository, snapshot)
        _validate_live_github_state(collected, snapshot)
        github_state = collected
    state, fingerprint = _dirty_tree_fingerprint(repository)
    evidence_meta: dict[str, Any] = {
        "producer": "hsconfig.release_gate.base_evidence",
        "repository_root": str(repository),
        "repository_identity": snapshot.repository_identity,
        "version": __version__,
        "commit_oid": snapshot.commit_oid,
        "tree_oid": snapshot.tree_oid,
        "tree_state": state,
        "dirty_tree_fingerprint": fingerprint,
        "generation_mode": score_mode,
    }
    if github_state is not None:
        evidence_meta.update(
            {
                "transaction_id": github_state["transaction_id"],
                "observed_at": github_state["observed_at"],
            }
        )
    base_binding = _receipt_binding(evidence_meta)
    check_ids = set(ATOMIC_CHECK_OWNERS)
    if score_mode == "pre_cutover":
        check_ids -= _GITHUB_CHECK_IDS
    atomic: dict[str, Any] = {}
    receipts: dict[str, Any] = {}
    for check_id in sorted(check_ids):
        receipt_id = f"receipts/{check_id}.json"
        if check_id in _GITHUB_CHECK_IDS:
            if github_state is None:
                raise ReleaseGateError("final GitHub transaction evidence is missing")
            passed = True
            receipts[receipt_id] = _validated_success_receipt(
                producer="hsconfig.release_gate.base_check",
                check_id=check_id,
                binding=_receipt_binding(
                    evidence_meta,
                    github_state=github_state,
                ),
            )
        else:
            source = by_name[_atomic_release_check(check_id)]
            passed = source.passed
            receipts[receipt_id] = _release_check_receipt(
                check_id=check_id,
                source=source,
                binding=base_binding,
            )
        atomic[check_id] = {
            "passed": passed,
            "kind": (
                "coverage_json"
                if check_id in {"branch_coverage", "critical_coverage"}
                else "completed_base_check"
            ),
            "evidence_paths": [receipt_id],
            "blocking_reasons": [] if passed else ["release check failed"],
            "non_blocking_reasons": [],
            "scope": "PRE_RUN_CONTRACT",
            "owner": ATOMIC_CHECK_OWNERS[check_id],
        }
    semantic_receipt = "receipts/semantic_obligations.json"
    rows = _produce_semantic_rows(repository, outputs_root, semantic_receipt)
    receipts[semantic_receipt] = _validated_success_receipt(
        producer="hsconfig.semantic_inventory",
        check_id="semantic_obligations",
        binding=base_binding,
    )
    evidence = {
        "_meta": evidence_meta,
        "checks": atomic,
        "semantic_obligations": rows,
        "findings": {"open_p0": 0, "open_p1": 0},
    }
    return {"schema_version": 1, "evidence": evidence, "receipts": receipts}


def run_release_gate(
    *,
    repository: Path,
    outputs_root: Path,
    tree_mode: TreeMode = "final",
) -> ReleaseGateResult:
    """Run every local release check in canonical order and fail closed."""
    root, outputs, commit_oid = _validate_repository(repository, outputs_root, tree_mode)
    _verify_module_binding(root)
    snapshot = _capture_snapshot(root, outputs)
    if snapshot.commit_oid != commit_oid:
        raise ReleaseGateError("repository changed during release gate startup")
    specs = _command_specs(root, outputs, tree_mode)
    checks: list[ReleaseCheck] = []
    for spec in specs[:-1]:
        checks.append(_run_one(spec, repository=root))
    _assert_snapshot_unchanged(root, outputs, snapshot)
    if all(check.passed for check in checks):
        try:
            bundle = _build_base_evidence(
                repository=root,
                outputs_root=outputs,
                checks=checks,
                tree_mode=tree_mode,
                snapshot=snapshot,
            )
            near100 = specs[-1]
            stdin_data = json.dumps(
                bundle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            checks.append(
                _run_one(
                    near100,
                    repository=root,
                    stdin_data=stdin_data,
                )
            )
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            near100 = specs[-1]
            checks.append(
                ReleaseCheck(
                    name=near100.name,
                    passed=False,
                    command=near100.command,
                    details={
                        "returncode": None,
                        "error": _redact_text(f"base_evidence_failed:{exc}"),
                    },
                )
            )
    else:
        near100 = specs[-1]
        checks.append(
            ReleaseCheck(
                name=near100.name,
                passed=False,
                command=near100.command,
                details={"returncode": None, "error": "blocked_by_failed_prerequisite"},
            )
        )
    _assert_snapshot_unchanged(root, outputs, snapshot)
    if tuple(check.name for check in checks) != CHECK_NAMES:
        raise ReleaseGateError("release check composition drifted")
    passed = all(check.passed for check in checks)
    return ReleaseGateResult(
        passed=passed,
        final_release_ready=passed and tree_mode == "final",
        version=__version__,
        commit_oid=commit_oid,
        checks=tuple(checks),
    )


def _tracked_paths(repository: Path) -> tuple[str, ...]:
    raw = _git(repository, "ls-files", "-z", text=False)
    if not isinstance(raw, bytes):
        raise ReleaseGateError("tracked file inspection returned text")
    return tuple(sorted(value.decode("utf-8") for value in raw.split(b"\0") if value))


def _prospective_paths(repository: Path) -> tuple[str, ...]:
    raw = _git(
        repository,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        text=False,
    )
    if not isinstance(raw, bytes):
        raise ReleaseGateError("prospective file inspection returned text")
    return tuple(sorted(value.decode("utf-8") for value in raw.split(b"\0") if value))


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value)
    return tuple(map(int, match.groups())) if match else None


def _placeholder_allowance(relative: str, line_number: int) -> tuple[bool, bool]:
    current = _version_tuple(__version__)
    for entry in SOURCE_TODO_ALLOWLIST:
        if entry.get("file") != relative or entry.get("line") != line_number:
            continue
        reason = entry.get("reason")
        expiry = entry.get("expiry_version")
        parsed = _version_tuple(expiry) if isinstance(expiry, str) else None
        valid = isinstance(reason, str) and bool(reason.strip()) and parsed is not None
        return valid and current is not None and parsed > current, valid
    return False, False


def _secret_like_component(component: str) -> bool:
    lowered = component.casefold()
    suffixes = {f".{part}" for part in lowered.split(".")[1:] if part}
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    return (
        lowered == ".env"
        or lowered.startswith(".env.")
        or bool(suffixes & _SENSITIVE_SUFFIXES)
        or _SECRET_NAME.search(lowered) is not None
        or any(token in compact for token in ("apikey", "accesstoken", "clientsecret", "privatekey"))
    )


def _runtime_evidence_component(component: str) -> bool:
    lowered = component.casefold()
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    return (
        any(marker in compact for marker in _RUNTIME_COMPACT)
        or ("hdt" in compact and "xml" in compact)
        or ({"private", "runtime"} <= tokens)
        or ("runtime" in tokens and bool(tokens & {"evidence", "export", "exports"}))
    )


def _text_violations(relative: str, data: bytes, *, public_doc: bool) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        # Publishable project surfaces are text contracts. Invalid UTF-8 must
        # never turn the content scanner into a silent bypass for ASCII
        # credentials embedded in an otherwise opaque byte stream.
        raw_text = data.decode("latin-1")
        violations = [f"non_utf8_content:{relative}"]
        if _ABSOLUTE_USER_PATH.search(raw_text):
            violations.append(f"absolute_path:{relative}")
        if _contains_secret(raw_text):
            violations.append(f"secret:{relative}")
        return violations
    violations: list[str] = []
    if _ABSOLUTE_USER_PATH.search(text):
        violations.append(f"absolute_path:{relative}")
    if _PRIVATE_NAMES.search(relative):
        violations.append(f"private_runtime_evidence:{relative}")
    suffix = Path(relative).suffix.casefold()
    try:
        secret_found = _contains_secret(
            text,
            python_source=suffix in {".py", ".pyi"},
            structured_suffix=suffix,
        )
    except ReleaseGateError:
        if suffix == ".json":
            violations.append(f"invalid_json_content:{relative}")
        elif suffix in {".yaml", ".yml"}:
            violations.append(f"invalid_yaml_content:{relative}")
        else:
            raise
    else:
        if secret_found:
            violations.append(f"secret:{relative}")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not (_PLACEHOLDER.search(line) or _EXPLICIT_PLACEHOLDER.search(line)):
            continue
        reference_path = relative
        if "!" in reference_path:
            reference_path = reference_path.split("!", 1)[1]
            parts = PurePosixPath(reference_path).parts
            if parts and re.fullmatch(r"hsconfig-[0-9]+(?:\.[0-9]+){2}", parts[0]):
                reference_path = PurePosixPath(*parts[1:]).as_posix()
            elif reference_path.startswith("hsconfig/"):
                reference_path = "src/" + reference_path
        reference_digest = hashlib.sha256(line.strip().encode("utf-8")).hexdigest()
        if (
            _EXACT_PLACEHOLDER_REFERENCE_SHA256.get(reference_path, {}).get(line_number)
            == reference_digest
        ):
            continue
        if public_doc:
            violations.append(f"public_placeholder:{relative}:{line_number}")
            continue
        if Path(relative).suffix.casefold() in _ACTIVE_SOURCE_SUFFIXES:
            allowed, structurally_valid = _placeholder_allowance(relative, line_number)
            if not allowed:
                reason = "expired_source_placeholder" if structurally_valid else "unallowlisted_source_placeholder"
                violations.append(f"{reason}:{relative}:{line_number}")
    return violations


def _path_violations(relative: str) -> list[str]:
    rows: list[str] = []
    parts = tuple(part for part in re.split(r"[/\\]", relative) if part)
    if _PRIVATE_NAMES.search(relative) or any(_runtime_evidence_component(part) for part in parts):
        rows.append(f"private_runtime_evidence:{relative}")
    if any(_secret_like_component(part) for part in parts):
        rows.append(f"secret:{relative}")
    if _RESIDUE_COMPONENT.search(relative) or _RESIDUE_SUFFIX.search(relative):
        rows.append(f"residue:{relative}")
    return rows


def _archive_rows(path: Path) -> tuple[tuple[str, bytes], ...]:
    rows: list[tuple[str, bytes]] = []
    canonical: set[str] = set()
    windows_keys: dict[str, str] = {}

    def record(name: str) -> str:
        if not name or "\\" in name or name.startswith(("/", "//")) or re.match(r"^[A-Za-z]:", name):
            raise ReleaseGateError(f"archive member has non-canonical absolute path: {name}")
        candidate = name[:-1] if name.endswith("/") else name
        parts = candidate.split("/")
        if not candidate or any(part in {"", ".", ".."} for part in parts):
            raise ReleaseGateError(f"archive member has traversal/non-canonical path: {name}")
        if any(part.rstrip(" .") != part or ":" in part for part in parts):
            raise ReleaseGateError(f"archive member has unsafe path: {name}")
        normalized = "/".join(parts)
        folded = "/".join(part.casefold() for part in parts)
        if normalized in canonical:
            raise ReleaseGateError(f"archive duplicate member: {name}")
        previous = windows_keys.get(folded)
        if previous is not None and previous != normalized:
            raise ReleaseGateError(f"archive casefold collision: {previous}:{normalized}")
        canonical.add(normalized)
        windows_keys[folded] = normalized
        return normalized

    def read_bounded(stream: Any, *, expected: int, member_name: str) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = stream.read(min(1024 * 1024, expected - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > expected or size > _MAX_ARCHIVE_MEMBER_BYTES:
                raise ReleaseGateError(f"archive member exceeds declared/size limit: {member_name}")
            chunks.append(chunk)
        if size != expected:
            raise ReleaseGateError(f"archive member size does not match header: {member_name}")
        return b"".join(chunks)

    archive_data = _secure_read_bytes(
        path.parent,
        PurePosixPath(path.name),
        context="distribution archive",
        max_bytes=_MAX_ARCHIVE_TOTAL_BYTES,
    )
    total_declared = 0
    if path.suffix == ".whl":
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            members = archive.infolist()
            if len(members) > _MAX_ARCHIVE_MEMBERS:
                raise ReleaseGateError("archive member count exceeds limit")
            for member in members:
                normalized = record(member.filename)
                mode = member.external_attr >> 16
                member_type = stat.S_IFMT(mode)
                if stat.S_ISLNK(mode) or member_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ReleaseGateError(f"archive non-regular zip member: {member.filename}")
                directory = member.filename.endswith("/")
                if (directory and member_type not in {0, stat.S_IFDIR}) or (
                    not directory and member_type == stat.S_IFDIR
                ):
                    raise ReleaseGateError(f"archive zip member type/name mismatch: {member.filename}")
                if directory:
                    continue
                if member.file_size > _MAX_ARCHIVE_MEMBER_BYTES:
                    raise ReleaseGateError(f"archive member exceeds size limit: {member.filename}")
                total_declared += member.file_size
                if total_declared > _MAX_ARCHIVE_TOTAL_BYTES:
                    raise ReleaseGateError("archive uncompressed content exceeds size limit")
                if member.file_size and member.compress_size == 0:
                    raise ReleaseGateError(f"archive member has invalid compressed size: {member.filename}")
                if member.compress_size and member.file_size / member.compress_size > _MAX_ARCHIVE_COMPRESSION_RATIO:
                    raise ReleaseGateError(f"archive member compression ratio exceeds limit: {member.filename}")
                with archive.open(member, "r") as stream:
                    rows.append(
                        (normalized, read_bounded(stream, expected=member.file_size, member_name=member.filename))
                    )
    else:
        tar_index: list[tuple[str, str, int, bool]] = []
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as archive:
            for member_number, member in enumerate(archive, start=1):
                if member_number > _MAX_ARCHIVE_MEMBERS:
                    raise ReleaseGateError("archive member count exceeds limit")
                normalized = record(member.name)
                if member.issym() or member.islnk():
                    raise ReleaseGateError(f"archive link member is forbidden: {member.name}")
                if member.isdir():
                    tar_index.append((member.name, normalized, 0, True))
                    continue
                if not member.isfile():
                    raise ReleaseGateError(f"archive non-regular tar member: {member.name}")
                if member.size > _MAX_ARCHIVE_MEMBER_BYTES:
                    raise ReleaseGateError(f"archive member exceeds size limit: {member.name}")
                total_declared += member.size
                if total_declared > _MAX_ARCHIVE_TOTAL_BYTES:
                    raise ReleaseGateError("archive uncompressed content exceeds size limit")
                tar_index.append((member.name, normalized, member.size, False))
        compressed_bytes = len(archive_data)
        if total_declared and (
            compressed_bytes <= 0
            or total_declared / compressed_bytes > _MAX_ARCHIVE_COMPRESSION_RATIO
        ):
            raise ReleaseGateError("archive compression ratio exceeds limit")
        # Reopen only after the complete bounded header pass has proved the
        # member count, declared sizes, types, paths and aggregate ratio. This
        # avoids getmembers() materialization and reads no member payload before
        # the resource limits have passed.
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as archive:
            observed = 0
            for member in archive:
                if observed >= len(tar_index):
                    raise ReleaseGateError("archive changed between validation and read")
                expected_name, normalized, expected_size, directory = tar_index[observed]
                observed += 1
                if (
                    member.name != expected_name
                    or member.size != expected_size
                    or member.isdir() is not directory
                    or (not directory and not member.isfile())
                ):
                    raise ReleaseGateError("archive changed between validation and read")
                if directory:
                    continue
                stream = archive.extractfile(member)
                if stream is None:
                    raise ReleaseGateError(f"archive member cannot be read: {member.name}")
                with stream:
                    rows.append(
                        (
                            normalized,
                            read_bounded(
                                stream,
                                expected=member.size,
                                member_name=member.name,
                            ),
                        )
                    )
            if observed != len(tar_index):
                raise ReleaseGateError("archive changed between validation and read")
    if sum(len(data) for _, data in rows) > _MAX_ARCHIVE_TOTAL_BYTES:
        raise ReleaseGateError("archive uncompressed content exceeds size limit")
    return tuple(rows)


def _secure_tracked_path(repository: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ReleaseGateError(f"non-canonical tracked path: {relative}")
    source = repository
    for index, part in enumerate(pure.parts):
        source = source / part
        try:
            metadata = source.lstat()
        except OSError as exc:
            raise ReleaseGateError(f"tracked source cannot be inspected: {relative}") from exc
        final = index == len(pure.parts) - 1
        expected = stat.S_ISREG(metadata.st_mode) if final else stat.S_ISDIR(metadata.st_mode)
        if not expected or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ReleaseGateError(f"tracked source contains link/reparse/non-regular data: {relative}")
        if final and getattr(metadata, "st_nlink", 1) not in {0, 1}:
            raise ReleaseGateError(f"tracked source must not be a hardlink: {relative}")
    return source


def _stage_tracked_source(repository: Path, target: Path) -> None:
    """Copy only regular tracked files into an isolated build source tree."""
    for relative in _tracked_paths(repository):
        pure = PurePosixPath(relative)
        destination = target.joinpath(*pure.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            _secure_read_bytes(
                repository,
                pure,
                context="tracked distribution source",
            )
        )


def _scan_distributions(repository: Path) -> tuple[list[str], int]:
    violations: list[str] = []
    count = 0
    with TemporaryDirectory(prefix="hsconfig-release-distribution-") as temporary:
        target = Path(temporary)
        source = target / "source"
        artifacts_root = target / "artifacts"
        try:
            _stage_tracked_source(repository, source)
        except (OSError, ReleaseGateError) as exc:
            return ([f"distribution_source_staging_failed:{exc}"], 0)
        completed = _execute_bounded(
            (sys.executable, "-m", "build", "--outdir", str(artifacts_root), str(source)),
            cwd=source,
            env=_controlled_environment(source),
            timeout=1_200,
        )
        if completed.returncode != 0:
            return ([f"distribution_build_failed:returncode={completed.returncode}"], 0)
        artifacts = sorted((*artifacts_root.glob("*.whl"), *artifacts_root.glob("*.tar.gz")))
        if len(artifacts) != 2:
            return ([f"distribution_artifact_count:{len(artifacts)}"], 0)
        for artifact in artifacts:
            count += 1
            for member, data in _archive_rows(artifact):
                relative = f"{artifact.name}!{member}"
                violations.extend(_path_violations(relative))
                violations.extend(_text_violations(relative, data, public_doc=False))
    return violations, count


def _catalog_deck_names(repository: Path) -> tuple[str, ...]:
    catalog_document = _load_json_bytes(
        _secure_read_bytes(
            repository,
            PurePosixPath("docs", "operator", "audited-deck-catalog.json"),
            context="current package catalog",
        ),
        source="docs/operator/audited-deck-catalog.json",
    )
    if not isinstance(catalog_document, Mapping):
        raise ReleaseGateError("current package catalog schema mismatch")
    try:
        deck_names = tuple(row["deck_name"] for row in catalog_document["decks"])
    except (KeyError, TypeError) as exc:
        raise ReleaseGateError("current package catalog schema mismatch") from exc
    if len(deck_names) != 12 or len(set(deck_names)) != 12:
        raise ReleaseGateError("current package catalog count mismatch")
    if any(
        not isinstance(name, str)
        or name in {"", ".", ".."}
        or any(character in name for character in "/\\:")
        for name in deck_names
    ):
        raise ReleaseGateError("current package catalog deck name mismatch")
    return deck_names


def _current_package_files(
    repository: Path, outputs_root: Path
) -> tuple[list[tuple[str, bytes]], list[str], int]:
    violations: list[str] = []
    rows: list[tuple[str, bytes]] = []
    try:
        deck_names = _catalog_deck_names(repository)
    except ReleaseGateError as exc:
        return rows, [str(exc)], 0
    try:
        actual_root_entries = {entry.name for entry in os.scandir(outputs_root)}
    except OSError as exc:
        return rows, [f"outputs_root_unreadable:{exc}"], 0
    unexpected = sorted(actual_root_entries - set(deck_names))
    missing = sorted(set(deck_names) - actual_root_entries)
    violations.extend(f"unexpected outputs root entry:{name}" for name in unexpected)
    violations.extend(f"missing outputs deck root:{name}" for name in missing)
    scanned = 0
    for deck_name in deck_names:
        deck_root = outputs_root / deck_name
        try:
            relative_current = PurePosixPath(deck_name, "current.json")
            current_data = _secure_read_bytes(
                outputs_root,
                relative_current,
                context="current package pointer",
            )
            current = _load_json_bytes(current_data, source=relative_current.as_posix())
            required_current = {
                "schema_version", "deck_name", "deck_fingerprint", "content_root_sha256", "revision"
            }
            if not isinstance(current, Mapping) or set(current) != required_current:
                raise ValueError("current pointer schema mismatch")
            if current.get("schema_version") != 1 or current.get("deck_name") != deck_name:
                raise ValueError("current pointer identity mismatch")
            for digest_field in ("deck_fingerprint", "content_root_sha256"):
                if not isinstance(current.get(digest_field), str) or re.fullmatch(r"[0-9a-f]{64}", current[digest_field]) is None:
                    raise ValueError(f"current pointer {digest_field} mismatch")
            revision = current["revision"]
            if not isinstance(revision, str):
                raise ValueError("revision must be a string")
            pure = PurePosixPath(revision)
            if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
                raise ValueError("non-canonical revision")
            if pure.name != f"sha256-{current['content_root_sha256']}":
                raise ValueError("current pointer content root binding mismatch")
            package = deck_root
            for part in pure.parts:
                package = package / part
                metadata = package.lstat()
                if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                    raise ValueError("revision contains link/reparse/non-directory")
            rows.append((relative_current.as_posix(), current_data))
        except (OSError, UnicodeError, KeyError, TypeError, ValueError, ReleaseGateError) as exc:
            violations.append(f"current_package_invalid:{deck_name}:{exc}")
            continue
        try:
            package_rows = _walk_regular_tree(
                package, context=f"current package {deck_name}"
            )
        except (OSError, ReleaseGateError) as exc:
            violations.append(f"current_package_non_regular_or_link:{deck_name}:{exc}")
            continue
        scanned += 1
        for package_relative, path, metadata in package_rows:
            relative = path.relative_to(outputs_root).as_posix()
            try:
                data = _secure_read_bytes(
                    package,
                    PurePosixPath(package_relative),
                    context=f"current package {deck_name}",
                    expected_identity=_stat_identity(metadata),
                )
            except ReleaseGateError as exc:
                violations.append(f"current_package_changed:{deck_name}:{exc}")
                scanned -= 1
                break
            rows.append((relative, data))
    try:
        output_rows = _walk_regular_tree(outputs_root, context="outputs tree")
    except (OSError, ReleaseGateError) as exc:
        violations.append(f"outputs_tree_non_regular_or_link:{exc}")
    else:
        for relative, _path, _metadata in output_rows:
            violations.extend(_path_violations(relative))
    return rows, violations, scanned


def _scan_current_packages(repository: Path, outputs_root: Path) -> tuple[list[str], int]:
    rows, violations, scanned = _current_package_files(repository, outputs_root)
    for relative, data in rows:
        violations.extend(_path_violations(relative))
        violations.extend(_text_violations(relative, data, public_doc=False))
    return violations, scanned


def _outputs_inventory_sha256(repository: Path, outputs_root: Path) -> str:
    rows, violations, count = _current_package_files(repository, outputs_root)
    if violations or count != 12:
        raise ReleaseGateError("outputs inventory cannot be bound safely: " + ";".join(violations[:5]))
    expected = set(_catalog_deck_names(repository))
    inventory: list[tuple[str, str, int, str]] = []

    def hash_file(relative: PurePosixPath, metadata: os.stat_result) -> tuple[int, str]:
        data = _secure_read_bytes(
            outputs_root,
            relative,
            context="outputs inventory file",
            expected_identity=_stat_identity(metadata),
        )
        if len(data) != metadata.st_size:
            raise ReleaseGateError("outputs file changed while inventory was captured")
        return len(data), hashlib.sha256(data).hexdigest()

    def visit(directory: Path, prefix: PurePosixPath) -> tuple[int, str]:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name.casefold())
        except OSError as exc:
            raise ReleaseGateError("outputs directory cannot be inspected") from exc
        seen: set[str] = set()
        child_rows: list[tuple[str, str, int, str]] = []
        total_size = 0
        for entry in entries:
            folded = entry.name.casefold()
            if folded in seen:
                raise ReleaseGateError("outputs tree contains a casefold collision")
            seen.add(folded)
            path = Path(entry.path)
            metadata = path.lstat()
            relative = prefix / entry.name
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                raise ReleaseGateError("outputs tree contains link/reparse data")
            if stat.S_ISDIR(metadata.st_mode):
                size, content_digest = visit(path, relative)
                row = (relative.as_posix(), "directory", size, content_digest)
            elif stat.S_ISREG(metadata.st_mode) and getattr(metadata, "st_nlink", 1) in {0, 1}:
                size, content_digest = hash_file(relative, metadata)
                row = (relative.as_posix(), "file", size, content_digest)
            else:
                raise ReleaseGateError("outputs tree contains hardlink/non-regular data")
            total_size += row[2]
            child_rows.append(row)
            inventory.append(row)
        digest = hashlib.sha256()
        for row in child_rows:
            digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")
        return total_size, digest.hexdigest()

    root_metadata = outputs_root.lstat()
    if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode) or _is_reparse(root_metadata):
        raise ReleaseGateError("outputs root is not a regular directory")
    root_names = {entry.name for entry in os.scandir(outputs_root)}
    unexpected = sorted(root_names - expected)
    missing = sorted(expected - root_names)
    if unexpected:
        raise ReleaseGateError(f"unexpected outputs root entry: {unexpected[0]}")
    if missing:
        raise ReleaseGateError(f"missing outputs deck root: {missing[0]}")
    _size, root_digest = visit(outputs_root, PurePosixPath())
    digest = hashlib.sha256()
    digest.update(root_digest.encode("ascii") + b"\0")
    for row in sorted(inventory):
        digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")
    return digest.hexdigest()


def scan_publishable_content(
    *,
    repository: Path,
    outputs_root: Path,
    tree_mode: TreeMode,
    build_distributions: bool = True,
) -> dict[str, Any]:
    """Scan tracked sources, release archives, and the twelve current packages."""
    root = Path(repository).resolve()
    outputs = Path(outputs_root).resolve()
    violations: list[str] = []
    tracked_count = 0
    paths = _prospective_paths(root) if tree_mode == "working-pre-cutover" else _tracked_paths(root)
    for relative in paths:
        if tree_mode == "working-pre-cutover" and relative.startswith(_HISTORICAL_PREFIXES):
            continue
        try:
            data = _secure_read_bytes(
                root,
                PurePosixPath(relative),
                context="publishable tracked source",
            )
        except ReleaseGateError as exc:
            violations.append(f"tracked_non_regular:{relative}:{exc}")
            continue
        tracked_count += 1
        violations.extend(_path_violations(relative))
        public_doc = (
            relative in _PUBLIC_DOC_PREFIXES
            or relative.startswith(_PUBLIC_DOC_PREFIXES)
            or Path(relative).suffix.casefold() in {".md", ".rst", ".toml", ".yaml", ".yml"}
        )
        violations.extend(_text_violations(relative, data, public_doc=public_doc))
    package_violations, package_count = _scan_current_packages(root, outputs)
    violations.extend(package_violations)
    artifact_count = 0
    if build_distributions:
        artifact_violations, artifact_count = _scan_distributions(root)
        violations.extend(artifact_violations)
    unique = tuple(sorted(set(violations)))
    return {
        "passed": not unique,
        "violations": list(unique),
        "tracked_files_scanned": tracked_count,
        "current_packages_scanned": package_count,
        "distribution_artifacts_scanned": artifact_count,
    }


def check_repository_hygiene(repository: Path, outputs_root: Path) -> dict[str, Any]:
    root = Path(repository).resolve()
    status = str(_git(root, "status", "--porcelain=v1", "--untracked-files=all"))
    violations = [f"dirty:{line}" for line in status.splitlines() if line]
    tracked = _tracked_paths(root)
    violations.extend(
        f"tracked_residue:{path}"
        for path in tracked
        if _RESIDUE_COMPONENT.search(path) or _RESIDUE_SUFFIX.search(path)
    )
    def inspect_workspace(directory: Path, prefix: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError:
            violations.append(f"workspace_unreadable:{prefix.as_posix() or '.'}")
            return
        seen: set[str] = set()
        for entry in entries:
            if not prefix.parts and entry.name == ".git":
                continue
            relative = prefix / entry.name
            key = entry.name.casefold()
            if key in seen:
                violations.append(f"workspace_collision:{relative.as_posix()}")
                continue
            seen.add(key)
            path = Path(entry.path)
            try:
                metadata = path.lstat()
            except OSError:
                violations.append(f"workspace_unreadable:{relative.as_posix()}")
                continue
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                violations.append(f"workspace_unsafe:{relative.as_posix()}")
                continue
            if stat.S_ISDIR(metadata.st_mode):
                if _LIVE_RESIDUE_DIRECTORY.fullmatch(entry.name):
                    violations.append(f"workspace_residue:{relative.as_posix()}")
                inspect_workspace(path, relative)
            elif stat.S_ISREG(metadata.st_mode):
                if getattr(metadata, "st_nlink", 1) not in {0, 1}:
                    violations.append(f"workspace_unsafe:{relative.as_posix()}")
                if _LIVE_RESIDUE_FILE.fullmatch(entry.name):
                    violations.append(f"workspace_residue:{relative.as_posix()}")
            else:
                violations.append(f"workspace_unsafe:{relative.as_posix()}")

    inspect_workspace(root, PurePosixPath())
    output_violations, package_count = _scan_current_packages(root, outputs_root)
    violations.extend(row for row in output_violations if row.startswith("residue:"))
    unique = tuple(sorted(set(violations)))
    return {
        "passed": not unique,
        "violations": list(unique),
        "current_packages": package_count,
    }


__all__ = [
    "CHECK_NAMES",
    "ReleaseCheck",
    "ReleaseGateError",
    "ReleaseGateResult",
    "check_repository_hygiene",
    "run_release_gate",
    "scan_publishable_content",
]
